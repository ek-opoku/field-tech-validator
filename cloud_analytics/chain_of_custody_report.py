from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import smtplib
import ssl
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable


"""
Automated Chain of Custody (CoC) reporting + notifications

How "new batch synced to cloud" is detected:
- This script monitors a local folder (default: cloud_analytics/incoming/) where your sync pipeline drops batch CSVs.
- It only processes files it hasn't seen before (tracked via a small state file with SHA256 hashes).
- After successful processing, the batch is renamed to *.processed to prevent reprocessing.

What it enforces:
- The incoming batch MUST contain the exact expected headers (order + spelling), otherwise it's rejected.
- A professional CoC PDF is generated and written to cloud_analytics/reports/.

QA/QC red flags:
- Applies the same key checks as the edge app:
  - pH < 6.0 or > 9.5
  - Temperature < 0°C
- Also adds “spike vs long-term average” checks using processed_water_data.csv (optional, if present):
  - Warn if a value exceeds a configurable percent of the long-term average for that parameter.

Notifications (optional):
- Slack: set SLACK_WEBHOOK_URL to a Slack Incoming Webhook URL.
- Email (SMTP): set SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS and EMAIL_TO (comma-separated).
"""


DEFAULT_INCOMING_DIR = Path(__file__).resolve().parent / "incoming"
DEFAULT_REPORTS_DIR = Path(__file__).resolve().parent / "reports"
DEFAULT_STATE_PATH = Path(__file__).resolve().parent / ".coc_state.json"
DEFAULT_PROCESSED_WATER_PATH = Path(__file__).resolve().parents[1] / "data_wide_imputed.csv.gz"


EXPECTED_HEADERS = [
    "Date",
    "SiteID",
    "Latitude",
    "Longitude",
    "Temperature, water (deg C)",
    "Turbidity (NTU)",
    "pH (standard units)",
    "Dissolved Oxygen (mg/L)",
    "Dissolved Oxygen (% saturation)",
    "Nitrate, dissolved (mg/L as N)",
    "Nitrite, dissolved (mg/L as N)",
    "Phosphate, dissolved (mg/L as P)",
    "Conductivity (uS/cm)",
    "Depth to water table (m)",
    "EdgeQCFlags",
]


@dataclass(frozen=True)
class Config:
    incoming_dir: Path
    reports_dir: Path
    state_path: Path
    processed_water_path: Path
    spike_warn_pct: float


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"seen_hashes": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"seen_hashes": {}}


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def iter_new_batches(cfg: Config) -> Iterable[Path]:
    cfg.incoming_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(cfg.state_path)
    seen = state.get("seen_hashes", {})

    for p in sorted(cfg.incoming_dir.iterdir()):
        if not (p.is_file() and p.suffix.lower() == ".csv"):
            continue
        if p.name.endswith(".processed.csv") or p.name.endswith(".rejected.csv"):
            continue
        digest = sha256_file(p)
        if digest in seen:
            continue
        yield p


def read_rows_strict(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"{path.name}: missing header row")
        if list(reader.fieldnames) != EXPECTED_HEADERS:
            raise ValueError(
                "Header mismatch.\n"
                f"- expected: {EXPECTED_HEADERS}\n"
                f"- actual:   {list(reader.fieldnames)}"
            )
        return [dict(r) for r in reader]


def safe_float(s: str) -> float | None:
    try:
        x = str(s).strip()
        if x == "":
            return None
        # Handle common lab formatting like "<0.02"
        x = x.lstrip("<>").strip()
        return float(x)
    except Exception:
        return None


def compute_lta_from_processed(processed_path: Path) -> dict[str, float]:
    """
    Long-term average computed from processed_water_data.csv if available.
    If your processed file uses cleaned snake_case headers, this will only compute
    for the columns that match the raw header names in EXPECTED_HEADERS.
    """
    if not processed_path.exists():
        return {}

    numeric_headers = [
        "Nitrate, dissolved (mg/L as N)",
        "Nitrite, dissolved (mg/L as N)",
        "Phosphate, dissolved (mg/L as P)",
        "Dissolved Oxygen (% saturation)",
        "Dissolved Oxygen (mg/L)",
        "Temperature, water (deg C)",
        "Turbidity (NTU)",
        "pH (standard units)",
    ]
    sums = {h: 0.0 for h in numeric_headers}
    counts = {h: 0 for h in numeric_headers}

    import gzip
    if processed_path.suffix == '.gz':
        f = gzip.open(processed_path, "rt", newline="", encoding="utf-8")
    else:
        f = processed_path.open("r", newline="", encoding="utf-8")
        
    with f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return {}
        available = [h for h in numeric_headers if h in reader.fieldnames]
        if not available:
            return {}
        for row in reader:
            for h in available:
                v = safe_float(row.get(h, ""))
                if v is None:
                    continue
                sums[h] += v
                counts[h] += 1

    out: dict[str, float] = {}
    for h in numeric_headers:
        if counts[h] > 0:
            out[h] = sums[h] / counts[h]
    return out


def red_flags(rows: list[dict[str, str]], *, lta: dict[str, float], spike_warn_pct: float) -> list[str]:
    """
    QA/QC flags intended for compliance reporting (human-readable).
    """
    flags: list[str] = []
    factor = max(1.0, spike_warn_pct / 100.0)

    out_of_range_ph = 0
    below_freezing = 0
    spikes: dict[str, int] = {}

    for r in rows:
        ph = safe_float(r.get("pH (standard units)", ""))
        temp = safe_float(r.get("Temperature, water (deg C)", ""))
        if ph is not None and (ph < 6.0 or ph > 9.5):
            out_of_range_ph += 1
        if temp is not None and temp < 0.0:
            below_freezing += 1

        for h, avg in lta.items():
            if abs(avg) < 1e-9:
                continue
            v = safe_float(r.get(h, ""))
            if v is None:
                continue
            if v > avg * factor:
                spikes[h] = spikes.get(h, 0) + 1

    if out_of_range_ph:
        flags.append(f"{out_of_range_ph} row(s) have pH outside 6.0–9.5.")
    if below_freezing:
        flags.append(f"{below_freezing} row(s) have temperature below 0°C.")

    for h, n in sorted(spikes.items(), key=lambda kv: (-kv[1], kv[0])):
        flags.append(f"{n} row(s) exceed {spike_warn_pct:.0f}% of long-term avg for “{h}”.")

    if not flags:
        flags.append("No QA/QC red flags detected for configured rules.")
    return flags


def render_coc_pdf(
    *,
    pdf_path: Path,
    batch_path: Path,
    rows: list[dict[str, str]],
    flags: list[str],
) -> None:
    """
    Professional-looking Chain of Custody PDF.
    Uses reportlab for a single-file, dependency-light approach.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    title = styles["Title"]
    h2 = styles["Heading2"]
    body = styles["BodyText"]

    batch_hash = sha256_file(batch_path)
    report_id = hashlib.sha256(f"{batch_hash}:{pdf_path.name}".encode("utf-8")).hexdigest()[:16]

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title="Chain of Custody",
        author="Field Tech Validator",
    )

    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    locations = sorted({(r.get("SiteID") or "").strip() for r in rows if (r.get("SiteID") or "").strip()})
    loc_summary = ", ".join(locations[:15]) + ("…" if len(locations) > 15 else "")

    parsed_dates = []
    for r in rows:
        d_str = r.get("Date", "")
        if d_str:
            try:
                parsed_dates.append(dt.datetime.fromisoformat(d_str))
            except Exception:
                pass
    
    trip_start = min(parsed_dates).strftime("%Y-%m-%d %H:%M:%S") if parsed_dates else "Unknown"
    trip_end = max(parsed_dates).strftime("%Y-%m-%d %H:%M:%S") if parsed_dates else "Unknown"

    numeric_headers = [
        "Temperature, water (deg C)",
        "Turbidity (NTU)",
        "pH (standard units)",
        "Dissolved Oxygen (mg/L)",
        "Dissolved Oxygen (% saturation)",
        "Nitrate, dissolved (mg/L as N)",
        "Nitrite, dissolved (mg/L as N)",
        "Phosphate, dissolved (mg/L as P)",
        "Conductivity (uS/cm)",
        "Depth to water table (m)",
    ]

    param_stats = []
    for h in numeric_headers:
        vals = []
        for r in rows:
            try:
                v = float(r.get(h, ""))
                vals.append(v)
            except Exception:
                pass
        if vals:
            param_stats.append([
                h.split(" (")[0],
                f"{min(vals):.2f}",
                f"{max(vals):.2f}",
                f"{sum(vals)/len(vals):.2f}"
            ])

    story = []
    story.append(Paragraph("Chain of Custody Report", title))
    story.append(Paragraph(f"Generated: <b>{now}</b>", body))
    story.append(Paragraph(f"Report ID: <b>{report_id}</b>", body))
    story.append(Paragraph(f"Batch file: <b>{batch_path.name}</b>", body))
    story.append(Paragraph(f"Batch SHA256: <b>{batch_hash}</b>", body))
    story.append(Paragraph(f"Trip Start: <b>{trip_start}</b>", body))
    story.append(Paragraph(f"Trip End: <b>{trip_end}</b>", body))
    story.append(Paragraph(f"Sites Visited: <b>{len(locations)}</b>", body))
    story.append(Paragraph(f"Total Samples (Rows): <b>{len(rows)}</b>", body))
    story.append(Paragraph(f"Locations: <b>{loc_summary or '—'}</b>", body))
    story.append(Spacer(1, 0.18 * inch))

    if param_stats:
        story.append(Paragraph("Parameter Summary", h2))
        stat_tbl_data = [["Parameter", "Min", "Max", "Average"]] + param_stats
        stat_tbl = Table(stat_tbl_data, colWidths=[3.0 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch])
        stat_tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F4F7")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#101828")),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D0D5DD")),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FCFCFD")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(stat_tbl)
        story.append(Spacer(1, 0.18 * inch))

    story.append(Paragraph("QA/QC red flags", h2))
    for f in flags:
        story.append(Paragraph(f"• {f}", body))
    story.append(Spacer(1, 0.18 * inch))

    story.append(Paragraph("Submission schema (headers)", h2))
    schema_tbl = Table([[h] for h in EXPECTED_HEADERS], colWidths=[6.6 * inch])
    schema_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F4F7")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#101828")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D0D5DD")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#FCFCFD")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(schema_tbl)
    story.append(Spacer(1, 0.18 * inch))

    # Small preview table (first N rows) so managers can sanity-check quickly
    story.append(Paragraph("Batch preview (first 12 rows)", h2))
    preview_n = min(12, len(rows))
    preview_headers = [
        "Date",
        "SiteID",
        "Nitrate, dissolved (mg/L as N)",
        "Temperature, water (deg C)",
        "Turbidity (NTU)",
        "pH (standard units)",
    ]
    table_data = [preview_headers]
    for r in rows[:preview_n]:
        table_data.append([str(r.get(h, "") or "")[:42] for h in preview_headers])

    tbl = Table(table_data, colWidths=[1.1 * inch, 1.35 * inch, 1.25 * inch, 1.15 * inch, 1.0 * inch, 0.9 * inch])
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#101828")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D0D5DD")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(tbl)

    from reportlab.pdfgen import canvas

    def _footer(c: canvas.Canvas, _doc) -> None:
        c.saveState()
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#667085"))
        page = c.getPageNumber()
        footer = f"Field Tech Validator • CoC Report {report_id} • Batch SHA256 {batch_hash[:12]}… • Page {page}"
        c.drawString(doc.leftMargin, 0.45 * inch, footer)
        c.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)


def notify_slack(webhook_url: str, *, pdf_path: Path, batch_path: Path, flags: list[str]) -> None:
    if not webhook_url:
        return
    payload = {
        "text": f"Chain of Custody report ready: {pdf_path.name} (batch: {batch_path.name})\n"
        + "\n".join([f"- {f}" for f in flags[:8]]),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status < 200 or resp.status >= 300:
            raise RuntimeError(f"Slack notification failed with HTTP {resp.status}")


def notify_email(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    to_addrs: list[str],
    pdf_path: Path,
    batch_path: Path,
    flags: list[str],
) -> None:
    if not (smtp_host and smtp_port and to_addrs):
        return
    msg = EmailMessage()
    msg["Subject"] = f"Chain of Custody report ready: {pdf_path.name}"
    msg["From"] = smtp_user or "coc-reporter@local"
    msg["To"] = ", ".join(to_addrs)
    msg.set_content(
        "Your Chain of Custody report is ready.\n\n"
        f"Batch: {batch_path.name}\n"
        f"PDF: {pdf_path}\n\n"
        "QA/QC summary:\n"
        + "\n".join([f"- {f}" for f in flags])
        + "\n"
    )

    # Attach PDF
    msg.add_attachment(pdf_path.read_bytes(), maintype="application", subtype="pdf", filename=pdf_path.name)

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as s:
        s.starttls(context=context)
        if smtp_user and smtp_pass:
            s.login(smtp_user, smtp_pass)
        s.send_message(msg)


def process_one_batch(cfg: Config, batch_path: Path) -> Path:
    rows = read_rows_strict(batch_path)
    lta = compute_lta_from_processed(cfg.processed_water_path)
    flags = red_flags(rows, lta=lta, spike_warn_pct=cfg.spike_warn_pct)

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = cfg.reports_dir / f"chain_of_custody_{batch_path.stem}_{ts}.pdf"
    render_coc_pdf(pdf_path=pdf_path, batch_path=batch_path, rows=rows, flags=flags)

    # Notifications are optional and only triggered after PDF exists.
    slack_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if slack_url:
        notify_slack(slack_url, pdf_path=pdf_path, batch_path=batch_path, flags=flags)

    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    smtp_port = int(os.environ.get("SMTP_PORT", "587").strip() or "587")
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASS", "").strip()
    email_to = [x.strip() for x in os.environ.get("EMAIL_TO", "").split(",") if x.strip()]
    if smtp_host and email_to:
        notify_email(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_pass=smtp_pass,
            to_addrs=email_to,
            pdf_path=pdf_path,
            batch_path=batch_path,
            flags=flags,
        )

    return pdf_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate Chain of Custody PDFs for newly-synced batch CSVs.")
    ap.add_argument("--incoming", default=str(DEFAULT_INCOMING_DIR), help="Folder containing synced batch CSVs")
    ap.add_argument("--reports", default=str(DEFAULT_REPORTS_DIR), help="Folder to write CoC PDFs")
    ap.add_argument("--state", default=str(DEFAULT_STATE_PATH), help="State file tracking processed batches")
    ap.add_argument(
        "--processed-water",
        default=str(DEFAULT_PROCESSED_WATER_PATH),
        help="processed_water_data.csv used to compute long-term averages (optional)",
    )
    ap.add_argument(
        "--spike-warn-pct",
        type=float,
        default=250.0,
        help="Warn if values exceed this percent of long-term average in the red-flag summary",
    )
    args = ap.parse_args()

    cfg = Config(
        incoming_dir=Path(args.incoming),
        reports_dir=Path(args.reports),
        state_path=Path(args.state),
        processed_water_path=Path(args.processed_water),
        spike_warn_pct=float(args.spike_warn_pct),
    )

    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(cfg.state_path)
    seen = state.get("seen_hashes", {})
    processed_any = False

    for batch in iter_new_batches(cfg):
        digest = sha256_file(batch)
        try:
            pdf_path = process_one_batch(cfg, batch)
            processed_any = True
            print(f"[OK] {batch.name} -> {pdf_path.name}")
            # Mark as processed (both hash + rename file)
            seen[digest] = {"file": batch.name, "processed_at": dt.datetime.now().isoformat(timespec="seconds")}
            batch.replace(batch.with_suffix(".processed.csv"))
        except Exception as e:
            print(f"[REJECTED] {batch.name}: {e}")
            seen[digest] = {"file": batch.name, "rejected_at": dt.datetime.now().isoformat(timespec="seconds"), "error": str(e)}
            try:
                batch.replace(batch.with_suffix(".rejected.csv"))
            except Exception:
                pass

    state["seen_hashes"] = seen
    save_state(cfg.state_path, state)

    if not processed_any:
        print("No new batches found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

