import streamlit as st
import pandas as pd
from app_theme import apply_water_theme
import datetime as dt
from pathlib import Path
from streamlit_autorefresh import st_autorefresh
from gateway_sync.gateway_bridge import (
    Config, DEFAULT_EDGE_INBOX, DEFAULT_BUFFER_PATH, DEFAULT_PROCESSED_SCHEMA,
    load_expected_headers, iter_incoming_csv_files, process_inbox_once, try_sync_once, is_online, load_buffer_rows
)

st.set_page_config(page_title="Gateway Sync", layout="wide", initial_sidebar_state="collapsed")
apply_water_theme()

st.title("Gateway Sync Dashboard")

# Determine connectivity status
if "ingest_url" not in st.session_state:
    st.session_state["ingest_url"] = ""

cfg = Config(
    edge_inbox=Path("edge_app/inbox"),
    buffer_path=Path("gateway_sync/offline_buffer.csv"),
    processed_schema_path=Path("data_wide_imputed.csv.gz"),
    ingest_url=st.session_state.get("ingest_url", ""),
    poll_seconds=5.0,
    max_batch_rows=500
)

try:
    expected_headers = load_expected_headers(cfg.processed_schema_path)
except Exception as e:
    st.error(f"Error loading schema: {e}")
    st.stop()

# ---------------- Connectivity & Auto-Sync ----------------
col_status, col_auto = st.columns([2, 1])

with col_status:
    if not cfg.ingest_url:
        st.warning("⚠️ No Cloud Ingest URL configured.")
        online_status = False
    else:
        online_status = is_online(cfg.ingest_url, timeout_seconds=1.5)
        if online_status:
            st.success("🟢 Online: Connected to Cloud Database")
        else:
            st.error("🔴 Offline: Cloud Database Unreachable")

with col_auto:
    auto_sync = st.toggle("🔄 Enable Auto-Sync Mode", value=st.session_state.get("auto_sync", False))
    st.session_state.auto_sync = auto_sync

if auto_sync:
    st.caption("Auto-syncing every 10 seconds while enabled...")
    st_autorefresh(interval=10000, limit=None, key="autosync_refresh")
    
    # Auto logic
    try:
        # 1. Always process inbox into buffer
        process_inbox_once(cfg, expected_headers)
        # 2. Sync to cloud if online
        if online_status and cfg.ingest_url:
            try_sync_once(cfg, expected_headers)
    except Exception as e:
        pass # Silently fail auto-sync to avoid spamming the UI, will retry next tick

st.divider()

# ---------------- Offline Storage Stats ----------------
st.subheader("Offline Storage Queue")
col1, col2 = st.columns(2)
with col1:
    incoming_files = list(iter_incoming_csv_files(cfg.edge_inbox))
    st.metric("Incoming Edge Files", len(incoming_files))
with col2:
    try:
        rows = load_buffer_rows(cfg.buffer_path, expected_headers)
        buffered_count = len(rows)
    except Exception:
        rows = []
        buffered_count = 0
    st.metric("Offline Buffered Rows", buffered_count)

# ---------------- Visual Audit & Export ----------------
with st.expander("🔍 View Buffered Records & Export", expanded=False):
    if buffered_count > 0:
        df_buffer = pd.DataFrame(rows)
        st.dataframe(df_buffer, use_container_width=True)
        
        csv_data = df_buffer.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="💾 Download Buffer to USB Backup",
            data=csv_data,
            file_name=f"gateway_buffer_backup_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
            type="primary"
        )
    else:
        st.info("The buffer is currently empty. No records waiting for sync.")

st.divider()

# ---------------- Manual Controls ----------------
st.subheader("Manual Controls")
col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    if st.button("Process Inbox into Buffer (Manual)", use_container_width=True):
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
    
    if st.button("Attempt Sync to Cloud (Manual)", use_container_width=True, type="primary"):
        if not ingest_url:
            st.error("Please provide an Ingest URL above.")
        else:
            with st.spinner("Syncing to cloud..."):
                cfg = Config(
                    edge_inbox=Path("edge_app/inbox"),
                    buffer_path=Path("gateway_sync/offline_buffer.csv"),
                    processed_schema_path=Path("data_wide_imputed.csv.gz"),
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
