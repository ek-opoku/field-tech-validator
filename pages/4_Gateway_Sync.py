import streamlit as st
from app_theme import apply_water_theme
import datetime as dt
from pathlib import Path
from gateway_sync.gateway_bridge import (
    Config, DEFAULT_EDGE_INBOX, DEFAULT_BUFFER_PATH, DEFAULT_PROCESSED_SCHEMA,
    load_expected_headers, iter_incoming_csv_files, process_inbox_once, try_sync_once, is_online, load_buffer_rows
)

st.set_page_config(page_title="Gateway Sync", layout="wide")
apply_water_theme()
st.title("Gateway Sync & Buffering")
st.write("Monitor offline readings and manually trigger sync to the central cloud database.")

cfg = Config(
    edge_inbox=Path("edge_app/inbox"),
    buffer_path=Path("gateway_sync/offline_buffer.csv"),
    processed_schema_path=Path("data_wide_imputed.csv"),
    ingest_url=st.session_state.get("ingest_url", ""),
    poll_seconds=5.0,
    max_batch_rows=500
)

try:
    expected_headers = load_expected_headers(cfg.processed_schema_path)
except Exception as e:
    st.error(f"Error loading schema: {e}")
    st.stop()

st.subheader("Offline Storage")
col1, col2 = st.columns(2)
with col1:
    st.metric("Incoming Edge Files", len(list(iter_incoming_csv_files(cfg.edge_inbox))))
with col2:
    try:
        rows = load_buffer_rows(cfg.buffer_path, expected_headers)
        buffered_count = len(rows)
    except Exception:
        buffered_count = 0
    st.metric("Offline Buffered Rows", buffered_count)

st.divider()

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    if st.button("Process Inbox into Buffer", use_container_width=True):
        with st.spinner("Processing inbox..."):
            try:
                ingested = process_inbox_once(cfg, expected_headers)
                if ingested > 0:
                    st.success(f"Buffered {ingested} row(s) from edge app!")
                else:
                    st.info("No valid rows found in inbox.")
            except Exception as e:
                st.error(f"Failed processing inbox: {e}")
        st.rerun()

with col_btn2:
    ingest_url = st.text_input("Cloud Ingest URL (leave blank to test connection handling)", value=cfg.ingest_url)
    st.session_state["ingest_url"] = ingest_url
    
    if st.button("Attempt Sync to Cloud", use_container_width=True, type="primary"):
        if not ingest_url:
            st.error("Please provide an Ingest URL above.")
        else:
            with st.spinner("Syncing to cloud..."):
                cfg = Config(
                    edge_inbox=Path("edge_app/inbox"),
                    buffer_path=Path("gateway_sync/offline_buffer.csv"),
                    processed_schema_path=Path("data_wide_imputed.csv"),
                    ingest_url=ingest_url,
                    poll_seconds=5.0,
                    max_batch_rows=500
                )
                if not is_online(ingest_url, timeout_seconds=2.0):
                    st.error("Device appears to be offline or Ingest URL is unreachable.")
                else:
                    try:
                        if try_sync_once(cfg, expected_headers):
                            st.success("Successfully synced buffered data to the cloud!")
                        else:
                            st.info("Nothing to sync.")
                    except Exception as e:
                        st.error(f"Sync failed: {e}")
