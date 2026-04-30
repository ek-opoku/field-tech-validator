from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


"""
Gateway Bridge (offline buffering + sync)

This script is designed to run on a gateway device that receives field readings while offline.

Offline flow:
- Read incoming CSV files dropped by the edge app into /edge_app (or a subfolder).
- Validate that each incoming file has the exact same headers as processed_water_data.csv.
- Append valid rows into a local buffer CSV (gateway_sync/offline_buffer.csv).

Online flow:
- When internet connectivity is restored, push buffered rows to a central ingest endpoint.
- Only clear the buffer after a successful upload (atomic write to avoid data loss).

Central database:
- This script posts to an HTTP ingest endpoint (e.g., your cloud API) that writes to the database.
- Configure via env var CLOUD_INGEST_URL or --ingest-url.
"""


DEFAULT_EDGE_INBOX = Path("edge_app") / "inbox"
DEFAULT_BUFFER_PATH = Path("gateway_sync") / "offline_buffer.csv"
DEFAULT_PROCESSED_SCHEMA = Path("processed_water_data.csv")

EDGE_HMAC_ENV = "EDGE_HMAC_SECRET"
EDGE_HMAC_STRICT_ENV = "EDGE_HMAC_STRICT"  # if "1", reject unsigned/missing sig

SNAKE_TO_RAW_HEADERS = {
    "activity_start_date": "ActivityStartDate",
    "monitoring_location_id": "MonitoringLocationIdentifier",
    "water_temp_c": "Temperature, water (deg C)",
    "turbidity_ntu": "Turbidity (NTU)",
    "ph": "pH (standard units)",
    "dissolved_oxygen_mg_l": "Oxygen, dissolved (mg/L)",
    "latitude": "ActivityLocation/LatitudeMeasure",
    "longitude": "ActivityLocation/LongitudeMeasure",
}


class SchemaError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    edge_inbox: Path
    buffer_path: Path
    processed_schema_path: Path
    ingest_url: str
    poll_seconds: float
    max_batch_rows: int


def is_online(url: str, timeout_seconds: float = 3.0) -> bool:
    """
    Connectivity check.
    We check reachability of the ingest endpoint rather than a generic host so "online"
    means "can actually reach the central sync service".
    """
    if not url:
        return False
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds):
            return True
    except Exception:
        return False


def load_expected_headers(processed_schema_path: Path) -> list[str]:
    """
    Source of truth for schema: the first row (headers) of processed_water_data.csv.
    This keeps the gateway aligned with the real-world dataset schema.
    """
    if not processed_schema_path.exists():
        raise FileNotFoundError(
            f"processed schema file not found: {processed_schema_path}. "
            "Generate it first (or place it here) so the gateway can enforce the exact schema."
        )

    with processed_schema_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader, None)
    if not headers:
        raise SchemaError(f"processed schema file has no headers: {processed_schema_path}")

    # If schema CSV uses cleaned snake_case, map to raw header equivalents when possible.
    mapped = [SNAKE_TO_RAW_HEADERS.get(h, h) for h in headers]
    return mapped


def validate_headers_exact(actual: list[str], expected: list[str]) -> None:
    if actual != expected:
        raise SchemaError(
            "Header mismatch.\n"
            f"- expected ({len(expected)}): {expected}\n"
            f"- actual   ({len(actual)}): {actual}\n"
            "Rejecting file to protect schema integrity."
        )


def iter_incoming_csv_files(edge_inbox: Path) -> Iterable[Path]:
    if not edge_inbox.exists():
        return []
    # Only immediate CSV files; avoids accidentally traversing arbitrary paths.
    return sorted([p for p in edge_inbox.iterdir() if p.is_file() and p.suffix.lower() == ".csv"])


def append_rows_to_buffer(buffer_path: Path, headers: list[str], rows: list[dict]) -> None:
    buffer_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = buffer_path.exists()
    with buffer_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        for r in rows:
            writer.writerow(r)


def read_csv_rows_strict(path: Path, expected_headers: list[str]) -> list[dict]:
    """
    Reads an incoming edge CSV and validates:
    - Exact headers
    - Optional HMAC signature sidecar (path.csv.sig) if EDGE_HMAC_SECRET is set
    """
    secret = os.environ.get(EDGE_HMAC_ENV, "").encode("utf-8")
    strict = os.environ.get(EDGE_HMAC_STRICT_ENV, "").strip() == "1"
    if secret or strict:
        sig_path = path.with_suffix(path.suffix + ".sig")
        if not sig_path.exists():
            if strict:
                raise SchemaError(f"{path.name}: missing signature sidecar {sig_path.name}")
        else:
            try:
                import hmac

                expected_sig = sig_path.read_text(encoding="utf-8").strip().lower()
                payload = path.read_bytes()
                actual_sig = hmac.new(secret, payload, hashlib.sha256).hexdigest().lower() if secret else ""
                if not secret:
                    raise SchemaError(f"{path.name}: signature present but {EDGE_HMAC_ENV} not set on gateway")
                if not hmac.compare_digest(actual_sig, expected_sig):
                    raise SchemaError(f"{path.name}: signature mismatch (possible tamper/corruption)")
            except Exception as e:
                raise SchemaError(str(e)) from e

    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SchemaError(f"{path} has no header row.")
        validate_headers_exact(list(reader.fieldnames), expected_headers)
        rows = []
        for i, row in enumerate(reader, start=2):
            # Reject rows missing required keys (shouldn't happen if DictReader is aligned).
            if any(k not in row for k in expected_headers):
                raise SchemaError(f"{path}: row {i} missing required columns.")
            rows.append(row)
        return rows


def atomic_write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def load_buffer_rows(buffer_path: Path, expected_headers: list[str]) -> list[dict]:
    if not buffer_path.exists():
        return []
    with buffer_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []
        validate_headers_exact(list(reader.fieldnames), expected_headers)
        return list(reader)


def post_batch_json(url: str, rows: list[dict], timeout_seconds: float = 10.0) -> None:
    """
    Push to central database via an ingest endpoint.
    The cloud service should validate + persist rows server-side.
    """
    body = json.dumps({"rows": rows}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            if resp.status < 200 or resp.status >= 300:
                raise RuntimeError(f"Upload failed with HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Upload failed with HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Upload failed: {e.reason}") from e


def process_inbox_once(cfg: Config, expected_headers: list[str]) -> int:
    """
    Aggregate incoming edge files into the offline buffer.
    Successfully processed files are renamed to *.processed to prevent re-ingestion.
    """
    count_rows = 0
    for csv_path in iter_incoming_csv_files(cfg.edge_inbox):
        try:
            rows = read_csv_rows_strict(csv_path, expected_headers)
            if rows:
                append_rows_to_buffer(cfg.buffer_path, expected_headers, rows)
                count_rows += len(rows)
            csv_path.replace(csv_path.with_suffix(csv_path.suffix + ".processed"))
            # Signature sidecar follows the CSV rename if present.
            sig = csv_path.with_suffix(csv_path.suffix + ".sig")
            if sig.exists():
                try:
                    sig.replace(sig.with_suffix(sig.suffix + ".processed"))
                except Exception:
                    pass
        except Exception as e:
            # Quarantine on errors so the gateway doesn't loop on a bad file forever.
            quarantine = csv_path.with_suffix(csv_path.suffix + ".rejected")
            try:
                csv_path.replace(quarantine)
            except Exception:
                pass
            sig = csv_path.with_suffix(csv_path.suffix + ".sig")
            if sig.exists():
                try:
                    sig.replace(sig.with_suffix(sig.suffix + ".rejected"))
                except Exception:
                    pass
            print(f"[REJECTED] {csv_path.name}: {e}")
    return count_rows


def try_sync_once(cfg: Config, expected_headers: list[str]) -> bool:
    """
    If online, push buffered rows in batches to central ingest.
    Buffer is only truncated after a successful upload, protecting against data loss.
    """
    if not cfg.ingest_url:
        return False
    if not is_online(cfg.ingest_url):
        return False

    rows = load_buffer_rows(cfg.buffer_path, expected_headers)
    if not rows:
        return True

    # Batch uploads so we don't send huge payloads.
    idx = 0
    while idx < len(rows):
        batch = rows[idx : idx + cfg.max_batch_rows]
        post_batch_json(cfg.ingest_url, batch)
        idx += len(batch)

    # Clear buffer after successful upload.
    atomic_write_csv(cfg.buffer_path, expected_headers, [])
    return True


def parse_args() -> Config:
    p = argparse.ArgumentParser(description="Gateway bridge: offline buffer + sync to central database.")
    p.add_argument("--edge-inbox", default=str(DEFAULT_EDGE_INBOX), help="Folder where edge app drops CSV files")
    p.add_argument("--buffer", default=str(DEFAULT_BUFFER_PATH), help="Local offline buffer CSV path")
    p.add_argument(
        "--schema",
        default=str(DEFAULT_PROCESSED_SCHEMA),
        help="processed_water_data.csv used as schema source of truth",
    )
    p.add_argument(
        "--ingest-url",
        default=os.environ.get("CLOUD_INGEST_URL", ""),
        help="Central ingest endpoint URL (or set CLOUD_INGEST_URL)",
    )
    p.add_argument("--poll-seconds", type=float, default=5.0, help="How often to poll inbox/sync")
    p.add_argument("--max-batch-rows", type=int, default=500, help="Max rows per upload batch")
    args = p.parse_args()
    return Config(
        edge_inbox=Path(args.edge_inbox),
        buffer_path=Path(args.buffer),
        processed_schema_path=Path(args.schema),
        ingest_url=args.ingest_url,
        poll_seconds=max(0.5, float(args.poll_seconds)),
        max_batch_rows=max(1, int(args.max_batch_rows)),
    )


def main() -> int:
    cfg = parse_args()
    expected_headers = load_expected_headers(cfg.processed_schema_path)

    # The user called out specific columns; ensure they exist in the schema we enforce.
    must_include = [
        "ActivityStartDate",
        "MonitoringLocationIdentifier",
        "Temperature, water (deg C)",
        "Turbidity (NTU)",
        "pH (standard units)",
    ]
    missing = [c for c in must_include if c not in expected_headers]
    if missing:
        raise SchemaError(
            "Your processed schema is missing required headers:\n- " + "\n- ".join(missing) + "\n"
            "Fix processed_water_data.csv schema first so gateway enforcement matches the real dataset."
        )

    print(f"Schema columns: {len(expected_headers)}")
    print(f"Edge inbox: {cfg.edge_inbox}")
    print(f"Offline buffer: {cfg.buffer_path}")
    print(f"Ingest URL: {cfg.ingest_url or '(not set)'}")

    while True:
        ingested = process_inbox_once(cfg, expected_headers)
        if ingested:
            print(f"[BUFFERED] +{ingested} rows")

        try:
            synced = try_sync_once(cfg, expected_headers)
            if synced and cfg.ingest_url:
                print("[SYNC] ok")
        except Exception as e:
            print(f"[SYNC] failed: {e}")

        time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

