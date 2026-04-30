from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import streamlit as st


# These must match the backend/database schema EXACTLY (spelling, punctuation, spacing).
SCHEMA_HEADERS = [
    "ActivityStartDate",
    "MonitoringLocationIdentifier",
    "ActivityLocation/LatitudeMeasure",
    "ActivityLocation/LongitudeMeasure",
    "Temperature, water (deg C)",
    "Turbidity (NTU)",
    "pH (standard units)",
    "Oxygen, dissolved (mg/L)",
]

INBOX_DIR = Path(__file__).resolve().parents[1] / "edge_app" / "inbox"
BASELINE_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "processed_water_data.csv"
EDGE_HMAC_ENV = "EDGE_HMAC_SECRET"


@dataclass
class Reading:
    activity_start_date: dt.date
    monitoring_location_identifier: str
    latitude: float | None
    longitude: float | None
    temperature_c: float | None
    turbidity_ntu: float | None
    ph: float | None
    dissolved_oxygen_mg_l: float | None

    def to_row(self) -> dict[str, str]:
        # Store as strings; gateway sync will validate headers and forward to central store.
        return {
            "ActivityStartDate": self.activity_start_date.isoformat(),
            "MonitoringLocationIdentifier": self.monitoring_location_identifier.strip(),
            "ActivityLocation/LatitudeMeasure": "" if self.latitude is None else f"{self.latitude}",
            "ActivityLocation/LongitudeMeasure": "" if self.longitude is None else f"{self.longitude}",
            "Temperature, water (deg C)": "" if self.temperature_c is None else f"{self.temperature_c}",
            "Turbidity (NTU)": "" if self.turbidity_ntu is None else f"{self.turbidity_ntu}",
            "pH (standard units)": "" if self.ph is None else f"{self.ph}",
            "Oxygen, dissolved (mg/L)": "" if self.dissolved_oxygen_mg_l is None else f"{self.dissolved_oxygen_mg_l}",
        }


def inject_glove_ui_css() -> None:
    st.markdown(
        """
        <style>
          /* Mobile-friendly layout */
          section.main > div { max-width: 860px; padding-top: 1rem; padding-bottom: 2.5rem; }

          /* Big, glove-friendly buttons */
          .stButton > button,
          button[kind="primary"],
          button[kind="secondary"] {
            min-height: 72px !important;
            font-size: 1.15rem !important;
            font-weight: 750 !important;
            border-radius: 18px !important;
            padding: 14px 18px !important;
          }

          /* Make inputs easier to hit */
          div[data-baseweb="input"] input,
          div[data-baseweb="textarea"] textarea {
            min-height: 56px !important;
            border-radius: 16px !important;
            font-size: 1.05rem !important;
          }

          /* Slightly larger labels */
          label { font-size: 1.02rem !important; }

          /* Bright red warning "popup" banner */
          .qc-popup {
            position: sticky;
            top: 0;
            z-index: 9999;
            margin: 0.5rem 0 1rem 0;
            padding: 16px 16px;
            border-radius: 18px;
            border: 2px solid rgba(255, 255, 255, 0.25);
            background: #b00020;
            color: white;
            font-weight: 850;
            font-size: 1.08rem;
            box-shadow: 0 16px 40px rgba(176, 0, 32, 0.38);
          }

          /* Reduce cramped columns on narrow screens */
          @media (max-width: 640px) {
            .stButton > button { min-height: 78px !important; font-size: 1.18rem !important; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def try_ocr_text_from_image(image_bytes: bytes) -> tuple[str | None, str | None]:
    """
    Offline OCR helper.

    - Uses local Tesseract via `pytesseract` if installed.
    - If OCR isn't available on the edge device, return a friendly error message.
    """
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return None, "OCR requires Pillow (PIL). Install: `python -m pip install pillow`."

    try:
        import pytesseract  # type: ignore
    except Exception:
        return (
            None,
            "OCR requires pytesseract + a local Tesseract install. "
            "Install Python package: `python -m pip install pytesseract` and install Tesseract on the device.",
        )

    try:
        from io import BytesIO

        img = Image.open(BytesIO(image_bytes))
    except Exception:
        return None, "Could not open the captured image for OCR."

    try:
        text = pytesseract.image_to_string(img)
        return text, None
    except Exception as e:
        return None, f"OCR failed: {e}"


def parse_meter_ocr(ocr_text: str) -> dict[str, float]:
    """
    Very lightweight extraction:
    - Supports either labeled lines (e.g., 'Temp 12.3', 'pH 7.4', 'DO 8.1')
    - Or unlabeled display dumps; in that case we pick the first number for each field only if labeled.
    """
    out: dict[str, float] = {}
    t = ocr_text.replace("\r\n", "\n")

    patterns: list[tuple[str, str]] = [
        ("Temperature, water (deg C)", r"(?:temp|temperature)\s*[:=]?\s*(-?\d+(?:\.\d+)?)"),
        ("Turbidity (NTU)", r"(?:turb|turbidity)\s*[:=]?\s*(-?\d+(?:\.\d+)?)"),
        ("pH (standard units)", r"(?:\bph\b)\s*[:=]?\s*(-?\d+(?:\.\d+)?)"),
        ("Oxygen, dissolved (mg/L)", r"(?:\bdo\b|oxygen)\s*[:=]?\s*(-?\d+(?:\.\d+)?)"),
    ]
    for header, pat in patterns:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if m:
            try:
                out[header] = float(m.group(1))
            except Exception:
                pass
    return out


def append_to_inbox(reading: Reading) -> Path:
    """
    Offline buffering for the edge app:
    - Each submission is written as a single-row CSV file in `edge_app/inbox/`.
    - The gateway bridge will later aggregate these files and sync them upstream.
    """
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_site = re.sub(r"[^a-zA-Z0-9_-]+", "-", reading.monitoring_location_identifier.strip())[:40] or "site"
    out_path = INBOX_DIR / f"reading_{safe_site}_{ts}.csv"

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SCHEMA_HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerow(reading.to_row())

    # Optional integrity: create a sidecar signature file without changing CSV schema.
    # Gateway can verify this signature offline using the same shared secret.
    secret = os.environ.get(EDGE_HMAC_ENV, "").encode("utf-8")
    if secret:
        try:
            import hmac

            payload = out_path.read_bytes()
            sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
            out_path.with_suffix(out_path.suffix + ".sig").write_text(sig, encoding="utf-8")
        except Exception:
            # Do not block data capture if signing fails on-device.
            pass

    return out_path


def _safe_float(s: str) -> float | None:
    try:
        return float(str(s).strip())
    except Exception:
        return None


def load_long_term_averages(schema_csv_path: Path) -> dict[str, float]:
    """
    Compute long-term averages from the local processed schema CSV (offline).

    This is intentionally lightweight (stdlib CSV, streaming sums) so it can run on edge devices.
    """
    if not schema_csv_path.exists():
        return {}

    numeric_headers = [
        "Temperature, water (deg C)",
        "Turbidity (NTU)",
        "pH (standard units)",
        "Oxygen, dissolved (mg/L)",
    ]
    sums: dict[str, float] = {h: 0.0 for h in numeric_headers}
    counts: dict[str, int] = {h: 0 for h in numeric_headers}

    with schema_csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return {}

        # Only compute on columns that actually exist in the file.
        available = [h for h in numeric_headers if h in reader.fieldnames]
        if not available:
            return {}

        for row in reader:
            for h in available:
                v = _safe_float(row.get(h, ""))
                if v is None:
                    continue
                sums[h] += v
                counts[h] += 1

    avgs: dict[str, float] = {}
    for h in numeric_headers:
        if counts[h] > 0:
            avgs[h] = sums[h] / counts[h]
    return avgs


@st.cache_resource(show_spinner=False)
def _load_vosk_model(model_path: str):
    """
    Load the local speech-to-text model once per session/device.
    Kept fully offline: the model must exist on disk.
    """
    from vosk import Model  # type: ignore

    return Model(model_path)


def transcribe_audio_offline(audio_bytes: bytes, *, model_dir: Path) -> tuple[Optional[str], Optional[str]]:
    """
    Offline speech-to-text (on-device).

    Current lightweight implementation uses Vosk (Kaldi-based) if installed.
    - No network calls
    - Requires a local model directory on disk
    """
    try:
        from vosk import KaldiRecognizer  # type: ignore
    except Exception:
        return (
            None,
            "Voice SOP requires an offline STT engine. Install Vosk: `python -m pip install vosk` "
            "and download an offline model into `edge_app/models/vosk/` (or set VOSK_MODEL_DIR).",
        )

    if not model_dir.exists():
        return (
            None,
            f"Offline STT model not found at `{model_dir}`. "
            "Place a Vosk model there (or set VOSK_MODEL_DIR).",
        )

    # Vosk expects 16kHz mono PCM WAV for best results. Streamlit audio capture usually provides WAV.
    # We'll attempt to decode WAV header if present; otherwise, pass raw bytes through (may reduce accuracy).
    import wave
    from io import BytesIO

    try:
        wf = wave.open(BytesIO(audio_bytes), "rb")
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        if channels != 1 or sampwidth not in (2,):
            # We keep logic offline + lightweight; if device audio isn't mono 16-bit, warn but still try.
            pass
        pcm = wf.readframes(wf.getnframes())
    except Exception:
        # Not a WAV; can't parse header. Try as-is.
        sample_rate = 16000
        pcm = audio_bytes

    try:
        model = _load_vosk_model(str(model_dir))
        rec = KaldiRecognizer(model, sample_rate)
        rec.SetWords(False)
        rec.AcceptWaveform(pcm)
        result = json.loads(rec.FinalResult() or "{}")
        text = (result.get("text") or "").strip()
        if not text:
            return None, "No speech detected (or audio too noisy). Try speaking closer to the mic."
        return text, None
    except Exception as e:
        return None, f"Voice transcription failed: {e}"


def qc_warnings(
    *,
    ph: float | None,
    temperature_c: float | None,
    turbidity_ntu: float | None,
    dissolved_oxygen_mg_l: float | None,
    long_term_avgs: dict[str, float],
    warn_if_above_pct_of_avg: float,
) -> list[str]:
    """
    On-device QA/QC checks (offline).
    These are evaluated in real-time as the user edits fields.
    """
    warnings: list[str] = []
    if ph is not None and (ph < 6.0 or ph > 9.5):
        warnings.append("pH (standard units) is outside 6.0–9.5.")
    if temperature_c is not None and temperature_c < 0.0:
        warnings.append("Temperature, water (deg C) is below freezing (0°C).")

    # Additional "spike" checks relative to long-term average (offline, local-only).
    # Example: if threshold is 200%, warn when value > 2.0 * long_term_average.
    factor = max(1.0, float(warn_if_above_pct_of_avg) / 100.0)

    def _avg_warn(header: str, value: float) -> None:
        avg = long_term_avgs.get(header)
        if avg is None:
            return
        # Avoid odd behavior when average is ~0 (e.g., sparse/blank datasets).
        if abs(avg) < 1e-9:
            return
        if value > avg * factor:
            warnings.append(f"{header} is unusually high vs long-term avg ({value:.2f} > {avg * factor:.2f}).")

    if temperature_c is not None:
        _avg_warn("Temperature, water (deg C)", float(temperature_c))
    if turbidity_ntu is not None:
        _avg_warn("Turbidity (NTU)", float(turbidity_ntu))
    if dissolved_oxygen_mg_l is not None:
        _avg_warn("Oxygen, dissolved (mg/L)", float(dissolved_oxygen_mg_l))
    return warnings


st.set_page_config(page_title="Edge Field Entry", layout="centered", initial_sidebar_state="collapsed")
inject_glove_ui_css()

st.title("Edge Field Entry (Offline)")
st.caption("This form writes schema-valid CSV drops to `edge_app/inbox/` for later gateway sync.")

with st.expander("Schema (exact headers)", expanded=False):
    st.code("\n".join(SCHEMA_HEADERS))

st.subheader("Voice SOP (offline)")
st.write("Hands-free: record a protocol question and get an offline transcript you can read back.")

if "voice_on" not in st.session_state:
    st.session_state.voice_on = False
if "voice_transcript" not in st.session_state:
    st.session_state.voice_transcript = ""

voice_col_a, voice_col_b = st.columns(2)
with voice_col_a:
    if st.button("Voice SOP (mic)", type="primary", use_container_width=True):
        st.session_state.voice_on = True
with voice_col_b:
    if st.button("Close mic", type="secondary", use_container_width=True, disabled=not st.session_state.voice_on):
        st.session_state.voice_on = False

if st.session_state.voice_on:
    st.info("Record a short question like: “What are the SOP steps for calibrating pH?”")
    audio_bytes = None
    if hasattr(st, "audio_input"):
        audio = st.audio_input("Record audio")
        if audio is not None:
            audio_bytes = audio.getvalue()
    else:
        st.warning("This Streamlit version doesn't support `audio_input`. Upload a short WAV instead.")
        up = st.file_uploader("Upload audio (WAV)", type=["wav"])
        if up is not None:
            audio_bytes = up.getvalue()

    if audio_bytes:
        model_dir = Path(os.environ.get("VOSK_MODEL_DIR", str(Path(__file__).resolve().parents[1] / "edge_app" / "models" / "vosk")))
        with st.spinner("Transcribing locally (offline)..."):
            text, err = transcribe_audio_offline(audio_bytes, model_dir=model_dir)
        if err:
            st.error(err)
        else:
            st.session_state.voice_transcript = text or ""
            st.success("Transcribed (offline).")

st.text_area("Voice SOP transcript", value=st.session_state.voice_transcript, height=110)


if "ocr_suggestions" not in st.session_state:
    st.session_state.ocr_suggestions = {}

st.subheader("Camera OCR (optional)")
st.write(
    "Capture a photo of your analog/digital meter. If offline OCR is available on this device, "
    "the app will extract readings and you can apply them to the form."
)

if "camera_on" not in st.session_state:
    st.session_state.camera_on = False

col_cam_a, col_cam_b = st.columns(2)
with col_cam_a:
    if st.button("Capture meter photo", type="primary", use_container_width=True):
        st.session_state.camera_on = True
with col_cam_b:
    if st.button("Close camera", type="secondary", use_container_width=True, disabled=not st.session_state.camera_on):
        st.session_state.camera_on = False

if st.session_state.camera_on:
    photo = st.camera_input("Camera")
    if photo is not None:
        ocr_text, ocr_err = try_ocr_text_from_image(photo.getvalue())
        if ocr_err:
            st.warning(ocr_err)
        else:
            assert ocr_text is not None
            st.text_area("OCR text (for review)", value=ocr_text, height=160)
            suggestions = parse_meter_ocr(ocr_text)
            if suggestions:
                st.session_state.ocr_suggestions = suggestions
                st.success("Detected values. Use “Apply OCR values” below to fill the form.")
            else:
                st.info("No labeled values detected (try including labels like Temp/pH/DO/Turbidity in the photo).")


st.divider()
st.subheader("Field reading (schema-locked)")

if st.button("Grab Location & Time Automatically", use_container_width=True):
    st.session_state.auto_date = dt.date.today()
    st.session_state.auto_lat = 40.04360556
    st.session_state.auto_lon = -104.823575
    st.success("Automatically populated Time and GPS Coordinates (simulated)")

col_a, col_b = st.columns([1, 1])
with col_a:
    activity_start_date = st.date_input("ActivityStartDate", value=st.session_state.get("auto_date", dt.date.today()))
with col_b:
    monitoring_location_identifier = st.text_input(
        "MonitoringLocationIdentifier",
        placeholder="e.g., WELL-102A",
    )

col_lat, col_lon = st.columns([1, 1])
with col_lat:
    latitude = st.number_input("Latitude", value=st.session_state.get("auto_lat", 40.0), format="%.6f")
with col_lon:
    longitude = st.number_input("Longitude", value=st.session_state.get("auto_lon", -104.0), format="%.6f")

# If OCR found values, show them as defaults (but user can override).
ocr = st.session_state.get("ocr_suggestions", {}) or {}

st.caption("Tip: mark a parameter as “Not measured” to leave it blank in the buffered CSV.")

nm1, nm2 = st.columns(2)
with nm1:
    nm_temp = st.checkbox("Not measured: Temperature", value=False)
    nm_turb = st.checkbox("Not measured: Turbidity", value=False)
with nm2:
    nm_ph = st.checkbox("Not measured: pH", value=False)
    nm_do = st.checkbox("Not measured: Dissolved oxygen", value=False)

temperature_c: float | None
turbidity_ntu: float | None
ph: float | None
dissolved_oxygen_mg_l: float | None

if nm_temp:
    st.text_input("Temperature, water (deg C)", value="", disabled=True)
    temperature_c = None
else:
    temperature_c = st.number_input(
        "Temperature, water (deg C)",
        value=float(ocr.get("Temperature, water (deg C)", 0.0)) if "Temperature, water (deg C)" in ocr else 0.0,
        step=0.1,
        format="%.2f",
    )

if nm_turb:
    st.text_input("Turbidity (NTU)", value="", disabled=True)
    turbidity_ntu = None
else:
    turbidity_ntu = st.number_input(
        "Turbidity (NTU)",
        value=float(ocr.get("Turbidity (NTU)", 0.0)) if "Turbidity (NTU)" in ocr else 0.0,
        step=0.1,
        format="%.2f",
    )

if nm_ph:
    st.text_input("pH (standard units)", value="", disabled=True)
    ph = None
else:
    ph = st.number_input(
        "pH (standard units)",
        value=float(ocr.get("pH (standard units)", 7.0)) if "pH (standard units)" in ocr else 7.0,
        step=0.01,
        format="%.2f",
    )

if nm_do:
    st.text_input("Oxygen, dissolved (mg/L)", value="", disabled=True)
    dissolved_oxygen_mg_l = None
else:
    dissolved_oxygen_mg_l = st.number_input(
        "Oxygen, dissolved (mg/L)",
        value=float(ocr.get("Oxygen, dissolved (mg/L)", 0.0)) if "Oxygen, dissolved (mg/L)" in ocr else 0.0,
        step=0.1,
        format="%.2f",
    )

# Real-time QA/QC sanity checks (offline).
with st.expander("QA/QC thresholds (offline)", expanded=False):
    warn_if_above_pct_of_avg = st.slider(
        "Warn if value exceeds this % of long-term average",
        min_value=110,
        max_value=600,
        value=250,
        step=10,
        help="Example: 250% means warn if value > 2.5× the long-term average (computed from local processed_water_data.csv).",
    )
    st.caption(f"Long-term averages source (offline): `{BASELINE_SCHEMA_PATH}`")

if "long_term_avgs" not in st.session_state:
    st.session_state.long_term_avgs = load_long_term_averages(BASELINE_SCHEMA_PATH)

long_term_avgs: dict[str, float] = st.session_state.long_term_avgs
warnings = qc_warnings(
    ph=ph,
    temperature_c=temperature_c,
    turbidity_ntu=turbidity_ntu,
    dissolved_oxygen_mg_l=dissolved_oxygen_mg_l,
    long_term_avgs=long_term_avgs,
    warn_if_above_pct_of_avg=float(warn_if_above_pct_of_avg),
)
if warnings:
    st.markdown(
        "<div class='qc-popup'>"
        + "QA/QC WARNING — Review before saving:<br/>"
        + "<br/>".join([f"• {w}" for w in warnings])
        + "</div>",
        unsafe_allow_html=True,
    )

col1, col2 = st.columns(2)
with col1:
    apply_ocr = st.button("Apply OCR values", use_container_width=True)
with col2:
    save = st.button("Save offline CSV", type="primary", use_container_width=True, disabled=bool(warnings))

if apply_ocr:
    # The numeric widgets already use OCR values as defaults; this button is mainly a glove-friendly UX affordance.
    if not st.session_state.get("ocr_suggestions"):
        st.info("No OCR values available yet. Capture a meter photo above.")
    else:
        st.success("OCR values are loaded into the fields above. Adjust if needed, then save.")

if save:
    if not monitoring_location_identifier.strip():
        st.error("MonitoringLocationIdentifier is required.")
    else:
        reading = Reading(
            activity_start_date=activity_start_date,
            monitoring_location_identifier=monitoring_location_identifier,
            latitude=latitude,
            longitude=longitude,
            temperature_c=temperature_c,
            turbidity_ntu=turbidity_ntu,
            ph=ph,
            dissolved_oxygen_mg_l=dissolved_oxygen_mg_l,
        )
        out_path = append_to_inbox(reading)
        st.success(f"Saved offline drop: {out_path.name}")
        if os.environ.get(EDGE_HMAC_ENV, "").strip():
            st.caption("Saved integrity signature sidecar (*.sig).")

