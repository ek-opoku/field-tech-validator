from __future__ import annotations

import gzip

import csv
import datetime as dt
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import sys
import pandas as pd
import streamlit as st
from streamlit_geolocation import streamlit_geolocation
import io
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None
try:
    import docx
except ImportError:
    docx = None

# Add the project root to sys.path to import local modules
project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.append(project_root)

from utils.geo_helpers import parse_sites_from_dataframe, find_nearest_site, solve_tsp, haversine_distance, Site
from utils.qc_guard import check_sanity_limits, load_historical_bounds, evaluate_historical_bounds, check_compliance, COMPLIANCE_STANDARDS
from app_theme import apply_water_theme

apply_water_theme()
st.markdown(
    """
    <style>
      /* Field Collection Specific: Larger Input fields */
      [data-testid="stNumberInput"] input,
      [data-testid="stTextInput"] input,
      [data-testid="stForm"] input,
      [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
      [data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
      [data-testid="stDateInput"] input {
        border: 2px solid #cbd5e1 !important;
        min-height: 80px !important;
        font-size: 1.5rem !important;
        padding: 1rem 1.2rem !important;
      }
      /* Labels for inputs */
      .stNumberInput label p,
      .stTextInput label p,
      .stSelectbox label p {
         font-size: 1.3rem !important;
         font-weight: 600 !important;
         margin-bottom: 0.5rem !important;
      }
      
      /* Field Collection Specific: Larger Buttons */
      .stButton > button,
      button[kind="primary"],
      button[kind="secondary"] {
        border-radius: 20px !important;
        min-height: 80px !important;
        padding: 18px 24px !important;
        font-size: 1.35rem !important;
      }
    </style>
    """,
    unsafe_allow_html=True
)

# Gateway imports for cloud sync
from gateway_sync.gateway_bridge import is_online, post_batch_json, process_inbox_once, try_sync_once, Config, load_expected_headers, iter_incoming_csv_files
from cloud_analytics.chain_of_custody_report import render_coc_pdf, red_flags, compute_lta_from_processed

# These must match the backend/database schema EXACTLY
SCHEMA_HEADERS = [
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

INBOX_DIR = Path(__file__).resolve().parents[1] / "edge_app" / "inbox"
BUFFER_PATH = Path(__file__).resolve().parents[1] / "gateway_sync" / "offline_buffer.csv"
BASELINE_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "data_wide_imputed.csv.gz"
EDGE_HMAC_ENV = "EDGE_HMAC_SECRET"


@dataclass
class Reading:
    activity_start_date: dt.datetime
    monitoring_location_identifier: str
    latitude: float | None
    longitude: float | None
    temperature_c: float | None
    turbidity_ntu: float | None
    ph: float | None
    dissolved_oxygen_mg_l: float | None
    dissolved_oxygen_sat: float | None
    nitrate: float | None
    nitrite: float | None
    orthophosphate: float | None
    conductivity: float | None
    depth_to_water: float | None
    edge_qc_flags: str | None = None

    def to_row(self) -> dict[str, str]:
        return {
            "Date": self.activity_start_date.isoformat(),
            "SiteID": self.monitoring_location_identifier.strip(),
            "Latitude": "" if self.latitude is None else f"{self.latitude}",
            "Longitude": "" if self.longitude is None else f"{self.longitude}",
            "Temperature, water (deg C)": "" if self.temperature_c is None else f"{self.temperature_c}",
            "Turbidity (NTU)": "" if self.turbidity_ntu is None else f"{self.turbidity_ntu}",
            "pH (standard units)": "" if self.ph is None else f"{self.ph}",
            "Dissolved Oxygen (mg/L)": "" if self.dissolved_oxygen_mg_l is None else f"{self.dissolved_oxygen_mg_l}",
            "Dissolved Oxygen (% saturation)": "" if self.dissolved_oxygen_sat is None else f"{self.dissolved_oxygen_sat}",
            "Nitrate, dissolved (mg/L as N)": "" if self.nitrate is None else f"{self.nitrate}",
            "Nitrite, dissolved (mg/L as N)": "" if self.nitrite is None else f"{self.nitrite}",
            "Phosphate, dissolved (mg/L as P)": "" if self.orthophosphate is None else f"{self.orthophosphate}",
            "Conductivity (uS/cm)": "" if self.conductivity is None else f"{self.conductivity}",
            "Depth to water table (m)": "" if self.depth_to_water is None else f"{self.depth_to_water}",
            "EdgeQCFlags": self.edge_qc_flags or "",
        }





def try_ocr_text_from_image(image_bytes: bytes) -> tuple[str | None, str | None]:
    try:
        from PIL import Image
    except Exception:
        return None, "OCR requires Pillow (PIL)."
    try:
        import pytesseract
    except Exception:
        return None, "OCR requires pytesseract."
    try:
        from io import BytesIO
        img = Image.open(BytesIO(image_bytes))
        text = pytesseract.image_to_string(img)
        return text, None
    except Exception as e:
        return None, f"OCR failed: {e}"


def parse_meter_ocr(ocr_text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    t = ocr_text.replace("\r\n", "\n")
    patterns = [
        ("Temperature, water (deg C)", r"(?:temp|temperature)\s*[:=]?\s*(-?\d+(?:\.\d+)?)"),
        ("Turbidity (NTU)", r"(?:turb|turbidity)\s*[:=]?\s*(-?\d+(?:\.\d+)?)"),
        ("pH (standard units)", r"(?:\bph\b)\s*[:=]?\s*(-?\d+(?:\.\d+)?)"),
        ("Dissolved Oxygen (mg/L)", r"(?:\bdo\b|oxygen)\s*[:=]?\s*(-?\d+(?:\.\d+)?)"),
        ("Dissolved Oxygen (% saturation)", r"(?:sat|saturation)\s*[:=]?\s*(-?\d+(?:\.\d+)?)"),
        ("Conductivity (uS/cm)", r"(?:cond|conductivity)\s*[:=]?\s*(-?\d+(?:\.\d+)?)"),
    ]
    for header, pat in patterns:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if m:
            try: out[header] = float(m.group(1))
            except Exception: pass
    return out


def append_to_inbox(reading: Reading) -> Path:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_site = re.sub(r"[^a-zA-Z0-9_-]+", "-", reading.monitoring_location_identifier.strip())[:40] or "site"
    out_path = INBOX_DIR / f"reading_{safe_site}_{ts}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SCHEMA_HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerow(reading.to_row())
    secret = os.environ.get(EDGE_HMAC_ENV, "").encode("utf-8")
    if secret:
        try:
            import hmac
            sig = hmac.new(secret, out_path.read_bytes(), hashlib.sha256).hexdigest()
            out_path.with_suffix(out_path.suffix + ".sig").write_text(sig, encoding="utf-8")
        except Exception:
            pass
    return out_path


def _safe_float(s: str) -> float | None:
    try: return float(str(s).strip())
    except Exception: return None


def load_long_term_averages(schema_csv_path: Path) -> dict[str, float]:
    if not schema_csv_path.exists():
        return {}
    numeric_headers = ["Temperature, water (deg C)", "Turbidity (NTU)", "pH (standard units)", "Dissolved Oxygen (mg/L)"]
    sums = {h: 0.0 for h in numeric_headers}
    counts = {h: 0 for h in numeric_headers}
    
    if schema_csv_path.suffix.lower() == '.gz':
        f = gzip.open(schema_csv_path, "rt", encoding="utf-8", newline="")
    else:
        f = schema_csv_path.open("r", newline="", encoding="utf-8")
        
    with f:
        reader = csv.DictReader(f)
        if not reader.fieldnames: return {}
        available = [h for h in numeric_headers if h in reader.fieldnames]
        if not available: return {}
        for row in reader:
            for h in available:
                v = _safe_float(row.get(h, ""))
                if v is not None:
                    sums[h] += v
                    counts[h] += 1
    avgs = {h: sums[h] / counts[h] for h in numeric_headers if counts[h] > 0}
    return avgs


@st.cache_resource(show_spinner=False)
def _load_vosk_model(model_path: str):
    from vosk import Model
    return Model(model_path)


def transcribe_audio_offline(audio_bytes: bytes, *, model_dir: Path) -> tuple[Optional[str], Optional[str]]:
    try:
        from vosk import KaldiRecognizer
    except Exception:
        return None, "Voice SOP requires an offline STT engine. Install Vosk."
    if not model_dir.exists():
        return None, f"Offline STT model not found at `{model_dir}`."
    import wave
    from io import BytesIO
    try:
        wf = wave.open(BytesIO(audio_bytes), "rb")
        sample_rate, pcm = wf.getframerate(), wf.readframes(wf.getnframes())
    except Exception:
        sample_rate, pcm = 16000, audio_bytes
    try:
        model = _load_vosk_model(str(model_dir))
        rec = KaldiRecognizer(model, sample_rate)
        rec.SetWords(False)
        rec.AcceptWaveform(pcm)
        result = json.loads(rec.FinalResult() or "{}")
        text = (result.get("text") or "").strip()
        if not text: return None, "No speech detected."
        return text, None
    except Exception as e:
        return None, f"Voice transcription failed: {e}"


def qc_warnings(*, ph: float | None, temperature_c: float | None, turbidity_ntu: float | None, dissolved_oxygen_mg_l: float | None, long_term_avgs: dict[str, float], warn_if_above_pct_of_avg: float) -> list[str]:
    warnings = []
    if ph is not None and (ph < 6.0 or ph > 9.5):
        warnings.append("pH (standard units) is outside 6.0–9.5.")
    if temperature_c is not None and temperature_c < 0.0:
        warnings.append("Temperature, water (deg C) is below freezing (0°C).")
    factor = max(1.0, float(warn_if_above_pct_of_avg) / 100.0)
    def _avg_warn(header: str, value: float):
        avg = long_term_avgs.get(header)
        if avg is not None and abs(avg) > 1e-9 and value > avg * factor:
            warnings.append(f"{header} is unusually high vs long-term avg ({value:.2f} > {avg * factor:.2f}).")
    if temperature_c is not None: _avg_warn("Temperature, water (deg C)", float(temperature_c))
    if turbidity_ntu is not None: _avg_warn("Turbidity (NTU)", float(turbidity_ntu))
    if dissolved_oxygen_mg_l is not None: _avg_warn("Dissolved Oxygen (mg/L)", float(dissolved_oxygen_mg_l))
    return warnings


# ---------------- APP LOGIC ----------------

st.set_page_config(page_title="Field Data Collection", layout="centered", initial_sidebar_state="collapsed")
apply_water_theme()

# Session State Initialization
if "trip_started" not in st.session_state: st.session_state.trip_started = False
if "preloaded_sites" not in st.session_state: st.session_state.preloaded_sites = []
if "ordered_sites" not in st.session_state: st.session_state.ordered_sites = []
if "completed_sites" not in st.session_state: st.session_state.completed_sites = []
if "ingest_url" not in st.session_state: st.session_state.ingest_url = ""
if "pending_end_trip" not in st.session_state: st.session_state.pending_end_trip = False
if "save_status" not in st.session_state: st.session_state.save_status = None
if "saved_site" not in st.session_state: st.session_state.saved_site = None
if "trip_data" not in st.session_state: st.session_state.trip_data = []
if "prompt_early_end" not in st.session_state: st.session_state.prompt_early_end = False
if "compliance_standard" not in st.session_state: st.session_state.compliance_standard = "None"
if "historical_bounds" not in st.session_state: st.session_state.historical_bounds = {}
if "gatekeeper_override" not in st.session_state: st.session_state.gatekeeper_override = False
if "show_gatekeeper" not in st.session_state: st.session_state.show_gatekeeper = False
if "sop_text" not in st.session_state: st.session_state.sop_text = ""
if "sop_filename" not in st.session_state: st.session_state.sop_filename = ""

# Parameter List
ALL_PARAMS = [
    "pH", "Temperature", "Turbidity", 
    "DO (Dissolved Oxygen)", "DOsat (DO Saturation)", 
    "Nitrate", "Nitrite", "Phosphate", 
    "Conductivity", "Depth to Water"
]
if "selected_params" not in st.session_state:
    st.session_state.selected_params = ALL_PARAMS.copy()

st.title("Field Data Collection")

if not st.session_state.trip_started:
    # ---------------- PHASE 1: PREP ----------------
    st.header("Phase 1: Field Trip Prep")
    st.caption("Plan your route, configure parameters, and prepare for the field.")
    
    tab_route, tab_params, tab_sop = st.tabs(["Route & Sites", "Parameters & Settings", "Instructions"])
    
    with tab_route:
        st.write("Upload a CSV file with sites for your trip (Must contain 'SiteID', 'Latitude', and 'Longitude' headers) OR select from pre-existing sites below.")
        uploaded_file = st.file_uploader("Upload Sites CSV", type=["csv"])
        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file)
                st.session_state.preloaded_sites = parse_sites_from_dataframe(df)
                st.success(f"Loaded {len(st.session_state.preloaded_sites)} sites from uploaded file.")
            except Exception as e: st.error(f"Error loading CSV: {e}")
        else:
            try:
                default_csv = Path(project_root) / "data_wide_imputed.csv.gz"
                if default_csv.exists() and not st.session_state.preloaded_sites:
                    df = pd.read_csv(default_csv)
                    st.session_state.preloaded_sites = parse_sites_from_dataframe(df)
            except Exception: pass
                
        site_options = [s.id for s in st.session_state.preloaded_sites]
        selected_site_ids = st.multiselect("Choose sites for today:", options=site_options, default=[])
        
        with st.expander("Add New Site Manually", expanded=False):
            col_c1, col_c2, col_c3 = st.columns([2, 1, 1])
            with col_c1:
                custom_id = st.text_input("New Site ID", placeholder="e.g. WELL-999")
            with col_c2:
                custom_lat = st.number_input("Lat (optional)", format="%.6f", value=None, key="c_lat")
            with col_c3:
                custom_lon = st.number_input("Lon (optional)", format="%.6f", value=None, key="c_lon")
                
            if st.button("Add Custom Site"):
                if custom_id:
                    if custom_id not in [s.id for s in st.session_state.preloaded_sites]:
                        st.session_state.preloaded_sites.append(Site(id=custom_id, lat=custom_lat if custom_lat else 0.0, lon=custom_lon if custom_lon else 0.0))
                        st.success(f"Added '{custom_id}'! You can now select it above.")
                    else:
                        st.warning(f"Site '{custom_id}' already exists.")
                else:
                    st.error("Please provide a Site ID to add.")
        
        st.write("Capture your current GPS location as the starting point:")
        start_location = streamlit_geolocation()
        start_lat, start_lon = 40.0, -104.0
        if start_location and start_location.get('latitude') and start_location.get('longitude'):
            start_lat = start_location['latitude']
            start_lon = start_location['longitude']
            st.success(f"Start Point: {start_lat:.4f}, {start_lon:.4f}")
        
        if st.button("Optimize Route"):
            site_dict = {s.id: s for s in st.session_state.preloaded_sites}
            selected_sites = [site_dict[sid] for sid in selected_site_ids]
            if selected_sites:
                st.session_state.ordered_sites = solve_tsp(selected_sites, start_lat, start_lon)
                st.success("Route Optimized! Your itinerary is saved.")
            else:
                st.error("Select at least one site.")
                
        if st.session_state.ordered_sites:
            st.info(f"Route optimized for {len(st.session_state.ordered_sites)} sites. Ready to begin trip.")
                
    with tab_params:
        st.subheader("Parameter Configuration")
        st.info("All parameters are enabled by default. You do not need to configure anything here unless you want to exclude specific parameters from your field trip.")
        st.write("Select which parameters you will collect on this trip:")
        selected = []
        col_p1, col_p2 = st.columns(2)
        for i, p in enumerate(ALL_PARAMS):
            col = col_p1 if i % 2 == 0 else col_p2
            if col.checkbox(p, value=p in st.session_state.selected_params):
                selected.append(p)
        st.session_state.selected_params = selected
        
        with st.expander("Advanced Configuration", expanded=False):
            st.write("Provide your central database Ingest URL. Data will save automatically to cloud if internet is available.")
            st.session_state.ingest_url = st.text_input("Cloud Ingest URL:", value=st.session_state.ingest_url, placeholder="https://api.example.com/ingest")
            
            st.write("Select Compliance Standard for Real-Time Checking:")
            standard_opts = list(COMPLIANCE_STANDARDS.keys())
            st.session_state.compliance_standard = st.selectbox(
                "Compliance Standard", 
                standard_opts,
                index=standard_opts.index(st.session_state.compliance_standard) if st.session_state.compliance_standard in standard_opts else 0
            )
        
    with tab_sop:
        st.subheader("Field Assistant & SOP")
        st.write("Upload Standard Operating Procedures (SOPs) or field instructions here. They will be available for quick reference and audio read-out during data collection.")
        
        sop_file = st.file_uploader("Upload Instructions Document", type=["txt", "md", "pdf", "docx"])
        if sop_file:
            if sop_file.name != st.session_state.sop_filename:
                with st.spinner("Parsing document..."):
                    extracted_text = ""
                    try:
                        ext = Path(sop_file.name).suffix.lower()
                        if ext in [".txt", ".md"]:
                            extracted_text = sop_file.getvalue().decode("utf-8", errors="ignore")
                        elif ext == ".pdf" and PdfReader is not None:
                            reader = PdfReader(io.BytesIO(sop_file.getvalue()))
                            for page in reader.pages:
                                extracted_text += page.extract_text() + "\n\n"
                        elif ext == ".docx" and docx is not None:
                            doc = docx.Document(io.BytesIO(sop_file.getvalue()))
                            extracted_text = "\n".join([p.text for p in doc.paragraphs])
                        else:
                            st.error(f"Cannot parse {ext} files (missing dependency or unsupported format).")
                    except Exception as e:
                        st.error(f"Error parsing document: {e}")
                    
                    if extracted_text.strip():
                        st.session_state.sop_text = extracted_text.strip()
                        st.session_state.sop_filename = sop_file.name
                        st.success(f"Successfully loaded {sop_file.name}")
            else:
                st.success(f"Loaded: {st.session_state.sop_filename}")
                
        with st.expander("Voice Dictation Tool (Optional)", expanded=False):
            if "voice_on" not in st.session_state: st.session_state.voice_on = False
            if "voice_transcript" not in st.session_state: st.session_state.voice_transcript = ""
            v1, v2 = st.columns(2)
            if v1.button("Voice SOP (mic)", type="primary", use_container_width=True): st.session_state.voice_on = True
            if v2.button("Close mic", type="secondary", use_container_width=True, disabled=not st.session_state.voice_on): st.session_state.voice_on = False
            if st.session_state.voice_on:
                audio = st.audio_input("Record audio") if hasattr(st, "audio_input") else st.file_uploader("Upload audio (WAV)", type=["wav"])
                if audio:
                    mdir = Path(os.environ.get("VOSK_MODEL_DIR", str(Path(__file__).resolve().parents[1] / "edge_app" / "models" / "vosk")))
                    with st.spinner("Transcribing..."):
                        text, err = transcribe_audio_offline(audio.getvalue(), model_dir=mdir)
                    if err: st.error(err)
                    else: st.session_state.voice_transcript = text or ""
            st.text_area("Voice SOP transcript", value=st.session_state.voice_transcript, height=110)

    st.divider()
    if st.button("Begin Trip", type="primary", use_container_width=True):
        if not st.session_state.get("ordered_sites", []):
            st.error("Please define sites or locations for your trip by selecting them and clicking 'Optimize Route' before starting.")
        else:
            st.session_state.trip_started = True
            st.session_state.pending_end_trip = False
            st.session_state.trip_data = []
            st.rerun()

else:
    # ---------------- PHASE 2: ACTIVE TRIP ----------------
    st.header("Phase 2: Active Trip")
    
    if st.session_state.save_status:
        if st.session_state.prompt_early_end:
            pending = [s for s in st.session_state.ordered_sites if s.id not in st.session_state.completed_sites]
            if pending:
                st.warning(f"You still have {len(pending)} unvisited sites in your itinerary. Are you sure you want to end the trip early?")
                col_ea1, col_ea2 = st.columns(2)
                with col_ea1:
                    if st.button("Return and Continue Data Collection", use_container_width=True):
                        st.session_state.prompt_early_end = False
                        st.rerun()
                with col_ea2:
                    if st.button("Proceed to End Trip", type="primary", use_container_width=True):
                        st.session_state.prompt_early_end = False
                        st.session_state.save_status = None
                        st.session_state.saved_site = None
                        st.session_state.pending_end_trip = True
                        st.rerun()
                st.stop()
            else:
                st.session_state.prompt_early_end = False
                st.session_state.save_status = None
                st.session_state.saved_site = None
                st.session_state.pending_end_trip = True
                st.rerun()
                
        st.success(f"Data for **{st.session_state.saved_site}** was successfully saved {'directly to the Cloud' if st.session_state.save_status == 'cloud' else 'offline to your device'}.")
        
        col_sp1, col_sp2, col_sp3 = st.columns(3)
        with col_sp1:
            if st.button("Proceed to Next Recommended Site", type="primary", use_container_width=True):
                st.session_state.save_status = None
                st.session_state.saved_site = None
                st.rerun()
        with col_sp2:
            if st.button("Override & Select Different Site", type="secondary", use_container_width=True):
                st.session_state.save_status = None
                st.session_state.saved_site = None
                st.rerun()
        with col_sp3:
            if st.button("End Trip", type="secondary", use_container_width=True):
                st.session_state.prompt_early_end = True
                st.rerun()
        st.stop()

    # Auto-sync check on page load if online
    if st.session_state.ingest_url and is_online(st.session_state.ingest_url, timeout_seconds=1.5):
        try:
            cfg = Config(INBOX_DIR, BUFFER_PATH, BASELINE_SCHEMA_PATH, st.session_state.ingest_url, 5.0, 500)
            expected_headers = SCHEMA_HEADERS
            if not BASELINE_SCHEMA_PATH.exists():
                with BASELINE_SCHEMA_PATH.open("w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(SCHEMA_HEADERS)
            process_inbox_once(cfg, expected_headers)
            if try_sync_once(cfg, expected_headers):
                pass # Sync successful silently
        except Exception:
            pass # Suppress sync errors so we don't break UI workflow

    # End Trip Logic
    if st.session_state.pending_end_trip:
        st.subheader("End of Trip Summary")
        if st.session_state.trip_data:
            st.info(f"You have collected {len(st.session_state.trip_data)} readings today.")
            
            all_df = pd.DataFrame(st.session_state.trip_data)
            all_df = all_df.reindex(columns=SCHEMA_HEADERS)
            csv_data_all = all_df.to_csv(index=False).encode('utf-8')
            
            reports_dir = Path(project_root) / "cloud_analytics" / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            report_name = f"past_trip_coc_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
            temp_pdf = reports_dir / report_name
            temp_batch = Path(f"batch_temp.csv")
            temp_batch.write_bytes(csv_data_all)
            lta = compute_lta_from_processed(BASELINE_SCHEMA_PATH)
            flags = red_flags(st.session_state.trip_data, lta=lta, spike_warn_pct=250.0)
            try:
                render_coc_pdf(pdf_path=temp_pdf, batch_path=temp_batch, rows=st.session_state.trip_data, flags=flags)
                pdf_bytes = temp_pdf.read_bytes()
            except Exception as e:
                pdf_bytes = b""
                st.error(f"Failed to generate COC PDF: {e}")
            try:
                temp_batch.unlink()
            except Exception: pass
            
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.download_button(label="Download ALL Today's Data (CSV)", data=csv_data_all, file_name=f"all_trip_data_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv", use_container_width=True)
            with col_d2:
                if pdf_bytes:
                    st.download_button(label="Download COC Report (PDF)", data=pdf_bytes, file_name=f"coc_report_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf", mime="application/pdf", use_container_width=True)
        else:
            st.info("No data was collected during this trip.")
            
        st.divider()

        unsynced_files = list(iter_incoming_csv_files(INBOX_DIR))
        buffer_exists = BUFFER_PATH.exists() and os.path.getsize(BUFFER_PATH) > 0
        if unsynced_files or buffer_exists:
            st.error("WARNING: You have unsynced offline data! Ensure internet is connected to sync before ending.")
            
            # Compile offline data for download backup
            all_dfs = []
            if buffer_exists:
                try: all_dfs.append(pd.read_csv(BUFFER_PATH))
                except Exception: pass
            for f in unsynced_files:
                try: all_dfs.append(pd.read_csv(f))
                except Exception: pass
            
            if all_dfs:
                combined_df = pd.concat(all_dfs, ignore_index=True)
                csv_data = combined_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download Offline Data Backup (CSV)",
                    data=csv_data,
                    file_name=f"field_trip_backup_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
            col_end1, col_end2 = st.columns(2)
            with col_end1:
                if st.button("Force Sync Now", type="primary", use_container_width=True):
                    with st.spinner("Syncing..."):
                        try:
                            cfg = Config(INBOX_DIR, BUFFER_PATH, BASELINE_SCHEMA_PATH, st.session_state.ingest_url, 5.0, 500)
                            if not is_online(cfg.ingest_url, timeout_seconds=3.0):
                                st.error("No internet connection or Ingest URL unreachable.")
                            else:
                                process_inbox_once(cfg, SCHEMA_HEADERS)
                                if try_sync_once(cfg, SCHEMA_HEADERS):
                                    st.success("Successfully synced all data!")
                                    st.session_state.pending_end_trip = False
                        except Exception as e:
                            st.error(f"Sync failed: {e}")
            with col_end2:
                if st.button("End Trip Anyway", type="secondary", use_container_width=True):
                    st.session_state.trip_started = False
                    st.session_state.pending_end_trip = False
                    st.session_state.trip_data = []
                    st.rerun()
            st.stop()
        else:
            if st.button("Confirm End Trip", type="primary"):
                st.session_state.trip_started = False
                st.session_state.pending_end_trip = False
                st.session_state.trip_data = []
                st.rerun()
            st.stop()
    else:
        if st.button("End Trip & Return to Prep", type="secondary"):
            st.session_state.pending_end_trip = True
            st.rerun()

    if st.session_state.sop_text:
        with st.expander("SOP Quick Reference", expanded=False):
            st.write("You can read the uploaded SOP below or have it read aloud to you.")
            import json
            safe_text = json.dumps(st.session_state.sop_text)
            tts_html = f"""
            <script>
            function readAloud() {{
                const text = {safe_text};
                const utterance = new SpeechSynthesisUtterance(text);
                window.speechSynthesis.speak(utterance);
            }}
            function stopAloud() {{
                window.speechSynthesis.cancel();
            }}
            </script>
            <button onclick="readAloud()" style="padding:8px 12px; border-radius:5px; background-color:#0284c7; color:white; border:none; cursor:pointer; margin-right:10px;">Read Aloud</button>
            <button onclick="stopAloud()" style="padding:8px 12px; border-radius:5px; background-color:#ef4444; color:white; border:none; cursor:pointer;">⏹ Stop Audio</button>
            """
            st.components.v1.html(tts_html, height=40)
            
            st.markdown(st.session_state.sop_text)

    st.divider()
    
    # Recommend next site
    pending_sites = [s for s in st.session_state.ordered_sites if s.id not in st.session_state.completed_sites]
    recommended_site = pending_sites[0] if pending_sites else None
    
    if recommended_site: 
        st.info(f"Recommended Next Site: **{recommended_site.id}**")
    else: 
        st.info("No more sites in your itinerary. You can manually enter a new site.")
        
    st.write("Capture current GPS to begin data collection for the site:")
    location = streamlit_geolocation()
    current_lat, current_lon = None, None
    if location and location.get('latitude') and location.get('longitude'):
        current_lat, current_lon = location['latitude'], location['longitude']
        st.success("GPS Captured!")
    
    with st.container():
        st.subheader("Data Collection Form")
        
        all_site_ids = [s.id for s in st.session_state.preloaded_sites]
        
        if "site_select_key" not in st.session_state:
            st.session_state.site_select_key = recommended_site.id if recommended_site and recommended_site.id in all_site_ids else None

        # Render a custom clear button above the selectbox if something is selected
        if st.session_state.site_select_key is not None:
            if st.button("Clear Selection", key="clear_site"):
                st.session_state.site_select_key = None
                st.rerun()
                
        options_list = ["(New Site)"] + all_site_ids
        monitoring_location_identifier = st.selectbox(
            "MonitoringLocationIdentifier", 
            options=options_list, 
            index=options_list.index(st.session_state.site_select_key) if st.session_state.site_select_key in options_list else None,
            key="site_select_key",
            placeholder="Search or select a site..."
        ) if all_site_ids else st.text_input("MonitoringLocationIdentifier", placeholder="e.g., WELL-102A")
            
        if monitoring_location_identifier and monitoring_location_identifier in all_site_ids:
            site_dict = {s.id: s for s in st.session_state.preloaded_sites}
            selected_site = site_dict[monitoring_location_identifier]
            nav_url = f"https://www.google.com/maps/dir/?api=1&destination={selected_site.lat},{selected_site.lon}"
            st.markdown(f"<a href='{nav_url}' target='_blank'><button style='width: 100%; min-height: 50px; border-radius: 12px; background-color: #28a745; color: white; font-weight: bold; font-size: 1.1rem; border: none; margin-bottom: 1rem;'>🗺️ Navigate to {monitoring_location_identifier}</button></a>", unsafe_allow_html=True)

        if monitoring_location_identifier == "(New Site)":
            monitoring_location_identifier = st.text_input("Enter New Site ID:", placeholder="e.g. WELL-102B")
            if not monitoring_location_identifier:
                st.info("Please manually input a new site ID. GPS coordinates have been grabbed from your device automatically.")
                
        if current_lat and current_lon and monitoring_location_identifier and monitoring_location_identifier != "(New Site)":
            site_dict = {s.id: s for s in st.session_state.preloaded_sites}
            if monitoring_location_identifier in site_dict:
                target_site = site_dict[monitoring_location_identifier]
                dist = haversine_distance(current_lat, current_lon, target_site.lat, target_site.lon)
                if dist > 0.5:
                    st.error(f"**🚨 GPS VERIFICATION FAILED:** You are {dist:.2f} miles away from {target_site.id}. Please verify you are at the correct location!")
                else: 
                    st.success(f"**GPS Verified:** You are physically at {target_site.id}.")
                    
        with st.expander("View/Edit Metadata & GPS", expanded=False):
            activity_start_date = st.date_input("Activity Date (Auto-Captured on Save)", value=dt.date.today(), disabled=True)
            default_lat, default_lon = float(current_lat) if current_lat else None, float(current_lon) if current_lon else None
            
            # If pre-existing site and no GPS, fallback to site's known coordinates
            if monitoring_location_identifier and monitoring_location_identifier in all_site_ids:
                site_dict = {s.id: s for s in st.session_state.preloaded_sites}
                selected_site = site_dict[monitoring_location_identifier]
                if default_lat is None: default_lat = selected_site.lat
                if default_lon is None: default_lon = selected_site.lon

            col_lat, col_lon = st.columns([1, 1])
            with col_lat: latitude = st.number_input("Latitude", value=default_lat, format="%.6f")
            with col_lon: longitude = st.number_input("Longitude", value=default_lon, format="%.6f")

        if "camera_on" not in st.session_state: st.session_state.camera_on = False
        col_cam_a, col_cam_b = st.columns(2)
        if col_cam_a.button("Capture meter photo", type="primary", use_container_width=True): st.session_state.camera_on = True
        if col_cam_b.button("Close camera", type="secondary", use_container_width=True, disabled=not st.session_state.camera_on): st.session_state.camera_on = False

        if "ocr_suggestions" not in st.session_state: st.session_state.ocr_suggestions = {}
        if st.session_state.camera_on:
            photo = st.camera_input("Camera")
            if photo is not None:
                ocr_text, ocr_err = try_ocr_text_from_image(photo.getvalue())
                if ocr_err: st.warning(ocr_err)
                else:
                    st.text_area("OCR text", value=ocr_text, height=100)
                    st.session_state.ocr_suggestions = parse_meter_ocr(ocr_text)
                    if st.button("✨ Apply OCR Values", use_container_width=True, type="primary"):
                        st.success("OCR Loaded into Inputs!")
                        st.session_state.camera_on = False
                        st.rerun()

        ocr = st.session_state.get("ocr_suggestions", {}) or {}

        st.write("Enter values for your selected parameters:")
        params_map = {}
        if not st.session_state.historical_bounds:
            st.session_state.historical_bounds = load_historical_bounds(BASELINE_SCHEMA_PATH)
            
        all_warnings = []
        all_dangers = []
        
        def _render_param(p_label: str, p_dict_key: str, default_val: float | None, step: float = 0.1):
            val = st.number_input(p_label, value=default_val, step=step)
            params_map[p_dict_key] = val
            if val is not None:
                c_stat, c_msg = check_compliance(val, p_dict_key, st.session_state.compliance_standard)
                h_stat, h_msg = evaluate_historical_bounds(val, p_dict_key, monitoring_location_identifier, st.session_state.historical_bounds)
                
                badges = []
                if c_stat == "Pass": badges.append(f"<span style='color: #2e7d32; font-size: 0.85rem;'>Compliance: Pass · {c_msg}</span>")
                elif c_stat == "Flag": badges.append(f"<span style='color: #ed6c02; font-size: 0.85rem;'>Compliance: Flag · {c_msg}</span>")
                elif c_stat == "None": badges.append(f"<span style='color: #6c757d; font-size: 0.85rem;'>Compliance: No standard</span>")
                
                if h_stat == "Safe": badges.append(f"<span style='color: #2e7d32; font-size: 0.85rem; border: 1px solid #2e7d32; padding: 2px 6px; border-radius: 4px; margin-left: 10px;'>Safe</span>")
                elif h_stat == "Warning":
                    badges.append(f"<span style='color: #ed6c02; font-size: 0.85rem; border: 1px solid #ed6c02; padding: 2px 6px; border-radius: 4px; margin-left: 10px;'>Warning: {h_msg}</span>")
                    all_warnings.append(f"{p_label}: {h_msg}")
                elif h_stat == "Danger":
                    badges.append(f"<span style='color: #d32f2f; font-size: 0.85rem; border: 1px solid #d32f2f; padding: 2px 6px; border-radius: 4px; margin-left: 10px;'>Critical: {h_msg}</span>")
                    all_dangers.append(f"{p_label}: {h_msg}")
                    
                st.markdown(f"<div style='margin-top: -15px; margin-bottom: 15px;'>{''.join(badges)}</div>", unsafe_allow_html=True)
                
        tab_phys, tab_chem, tab_nutr = st.tabs(["🌡️ Physical", "🧪 Chemical", "🌱 Nutrients"])
        
        with tab_phys:
            for p in st.session_state.selected_params:
                if p == "Temperature": _render_param("Temperature, water (deg C)", "temperature_c", float(ocr.get("Temperature, water (deg C)")) if "Temperature, water (deg C)" in ocr else None, 0.1)
                elif p == "Turbidity": _render_param("Turbidity (NTU)", "turbidity_ntu", float(ocr.get("Turbidity (NTU)")) if "Turbidity (NTU)" in ocr else None, 0.1)
                elif p == "Depth to Water": _render_param("Depth to water table (m)", "depth_to_water", None, 0.1)
                
        with tab_chem:
            for p in st.session_state.selected_params:
                if p == "pH": _render_param("pH (standard units)", "ph", float(ocr.get("pH (standard units)")) if "pH (standard units)" in ocr else None, 0.01)
                elif p == "DO (Dissolved Oxygen)": _render_param("Dissolved Oxygen (mg/L)", "dissolved_oxygen_mg_l", float(ocr.get("Dissolved Oxygen (mg/L)")) if "Dissolved Oxygen (mg/L)" in ocr else None, 0.1)
                elif p == "DOsat (DO Saturation)": _render_param("Dissolved Oxygen (% saturation)", "dissolved_oxygen_sat", float(ocr.get("Dissolved Oxygen (% saturation)")) if "Dissolved Oxygen (% saturation)" in ocr else None, 0.1)
                elif p == "Conductivity": _render_param("Conductivity (uS/cm)", "conductivity", float(ocr.get("Conductivity (uS/cm)")) if "Conductivity (uS/cm)" in ocr else None, 1.0)
                
        with tab_nutr:
            for p in st.session_state.selected_params:
                if p == "Nitrate": _render_param("Nitrate, dissolved (mg/L as N)", "nitrate", None, 0.1)
                elif p == "Nitrite": _render_param("Nitrite, dissolved (mg/L as N)", "nitrite", None, 0.1)
                elif p == "Phosphate": _render_param("Phosphate, dissolved (mg/L as P)", "orthophosphate", None, 0.1)

        st.markdown("""
        <style>
        @keyframes flash {
            0% { background-color: #ffebee; border-left: 5px solid #d32f2f; }
            50% { background-color: #ffcdd2; border-left: 5px solid #b71c1c; }
            100% { background-color: #ffebee; border-left: 5px solid #d32f2f; }
        }
        .flashing-error {
            animation: flash 1s infinite;
            padding: 10px;
            border-radius: 4px;
            color: #b71c1c;
            font-weight: bold;
            margin-bottom: 10px;
        }
        </style>
        """, unsafe_allow_html=True)

        hard_stops = check_sanity_limits(params_map)
        if hard_stops:
            for hs in hard_stops:
                st.markdown(f"<div class='flashing-error'>🚨 PHYSICAL BOUNDS VIOLATED: {hs}</div>", unsafe_allow_html=True)

        has_warnings = len(all_warnings) > 0 or len(all_dangers) > 0
        is_disabled = len(hard_stops) > 0
        
        # Level 4: Haptic Feedback
        import streamlit.components.v1 as components
        if is_disabled:
            components.html("<script>if(navigator.vibrate) navigator.vibrate([200, 100, 200, 100, 500]);</script>", height=0)
        elif has_warnings:
            if len(all_dangers) > 0:
                components.html("<script>if(navigator.vibrate) navigator.vibrate([100, 50, 100, 50, 200]);</script>", height=0)
            else:
                components.html("<script>if(navigator.vibrate) navigator.vibrate([100, 50, 100]);</script>", height=0)
                
        # Level 5: Pre-submission Gatekeeper
        if st.session_state.show_gatekeeper:
            st.warning("QA/QC Warnings detected. Review before submitting:")
            for w in all_warnings + all_dangers:
                st.write(f"- {w}")
            col_gk1, col_gk2 = st.columns(2)
            with col_gk1:
                if st.button("Cancel", use_container_width=True):
                    st.session_state.show_gatekeeper = False
                    st.rerun()
            with col_gk2:
                if st.button("Submit Anyway (Override)", type="primary", use_container_width=True):
                    st.session_state.gatekeeper_override = True
                    st.session_state.show_gatekeeper = False
                    st.rerun()
            st.stop()

        if is_disabled:
            st.button("Save Data (Disabled)", type="primary", use_container_width=True, disabled=True)
        elif has_warnings and not st.session_state.gatekeeper_override:
            if st.button("Review Warnings (Save Data)", type="primary", use_container_width=True):
                st.session_state.show_gatekeeper = True
                st.rerun()
        else:
            if st.button("Save Data (Overridden)" if st.session_state.gatekeeper_override else "Save Data", type="primary", use_container_width=True):
                if not monitoring_location_identifier or not monitoring_location_identifier.strip() or monitoring_location_identifier == "(New Site)":
                    st.error("Valid Site ID required.")
                else:
                    reading = Reading(
                        activity_start_date=dt.datetime.now(),
                        monitoring_location_identifier=monitoring_location_identifier,
                        latitude=latitude,
                        longitude=longitude,
                        temperature_c=params_map.get("temperature_c"),
                        turbidity_ntu=params_map.get("turbidity_ntu"),
                        ph=params_map.get("ph"),
                        dissolved_oxygen_mg_l=params_map.get("dissolved_oxygen_mg_l"),
                        dissolved_oxygen_sat=params_map.get("dissolved_oxygen_sat"),
                        nitrate=params_map.get("nitrate"),
                        nitrite=params_map.get("nitrite"),
                        orthophosphate=params_map.get("orthophosphate"),
                        conductivity=params_map.get("conductivity"),
                        depth_to_water=params_map.get("depth_to_water"),
                        edge_qc_flags="|".join(all_warnings + all_dangers) if st.session_state.gatekeeper_override else ""
                    )
                    st.session_state.gatekeeper_override = False
                    row_data = reading.to_row()
                    saved = False
                    
                    if st.session_state.ingest_url:
                        with st.spinner("Attempting to save directly to Cloud..."):
                            if is_online(st.session_state.ingest_url, timeout_seconds=3.0):
                                try:
                                    post_batch_json(st.session_state.ingest_url, [row_data])
                                    st.success("Saved directly to Cloud!")
                                    saved = True
                                except Exception as e:
                                    st.error(f"Cloud push failed: {e}. Falling back to offline save.")
                    
                    if not saved:
                        out_path = append_to_inbox(reading)
                        st.session_state.save_status = "offline"
                    else:
                        st.session_state.save_status = "cloud"
                    
                    if monitoring_location_identifier not in st.session_state.completed_sites:
                        st.session_state.completed_sites.append(monitoring_location_identifier)
                        
                    st.session_state.trip_data.append(row_data)
                    st.session_state.saved_site = monitoring_location_identifier
                    st.rerun()

