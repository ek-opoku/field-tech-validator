import streamlit as st
from app_theme import apply_water_theme
import datetime as dt
from pathlib import Path
from cloud_analytics.chain_of_custody_report import (
    Config, DEFAULT_INCOMING_DIR, DEFAULT_REPORTS_DIR, 
    DEFAULT_STATE_PATH, DEFAULT_PROCESSED_WATER_PATH,
    load_state, save_state, iter_new_batches, process_one_batch, sha256_file
)

st.set_page_config(page_title="Chain of Custody Reports", layout="wide")
apply_water_theme()
st.title("📄 Chain of Custody Reporting")
st.write("Generate and download automated Chain of Custody PDFs with QA/QC flags for synced batch CSVs.")

cfg = Config(
    incoming_dir=DEFAULT_INCOMING_DIR,
    reports_dir=DEFAULT_REPORTS_DIR,
    state_path=DEFAULT_STATE_PATH,
    processed_water_path=DEFAULT_PROCESSED_WATER_PATH,
    spike_warn_pct=250.0,
)

st.subheader("Incoming Batches")
incoming_batches = list(iter_new_batches(cfg))

if incoming_batches:
    st.info(f"Found {len(incoming_batches)} new batch(es) waiting for processing.")
    if st.button("Generate Reports for New Batches", type="primary"):
        with st.spinner("Processing batches and generating PDFs..."):
            processed = 0
            state = load_state(cfg.state_path)
            seen = state.get("seen_hashes", {})
            for batch in incoming_batches:
                digest = sha256_file(batch)
                try:
                    pdf_path = process_one_batch(cfg, batch)
                    st.success(f"Generated: {pdf_path.name}")
                    seen[digest] = {"file": batch.name, "processed_at": dt.datetime.now().isoformat(timespec="seconds")}
                    batch.replace(batch.with_suffix(".processed.csv"))
                    processed += 1
                except Exception as e:
                    st.error(f"Failed to process {batch.name}: {e}")
                    seen[digest] = {"file": batch.name, "rejected_at": dt.datetime.now().isoformat(timespec="seconds"), "error": str(e)}
                    try:
                        batch.replace(batch.with_suffix(".rejected.csv"))
                    except Exception:
                        pass
            
            state["seen_hashes"] = seen
            save_state(cfg.state_path, state)
            
            if processed > 0:
                st.balloons()
else:
    st.success("No new batches waiting for processing.")

st.divider()
st.subheader("Generated Reports")
if cfg.reports_dir.exists():
    pdfs = sorted([p for p in cfg.reports_dir.iterdir() if p.suffix.lower() == ".pdf"], reverse=True)
    if pdfs:
        for pdf in pdfs:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"📄 **{pdf.name}**")
            with col2:
                with open(pdf, "rb") as f:
                    st.download_button("Download PDF", data=f.read(), file_name=pdf.name, mime="application/pdf", key=pdf.name)
    else:
        st.write("No reports generated yet.")
else:
    st.write("No reports generated yet.")
