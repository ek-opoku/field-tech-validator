import streamlit as st
from app_theme import apply_water_theme
from PIL import Image
from pathlib import Path

st.set_page_config(page_title="App Tutorial", layout="wide", initial_sidebar_state="expanded")
apply_water_theme()

project_root = Path(__file__).resolve().parents[1]

def load_image(filename):
    path = project_root / "assets" / filename
    if path.exists():
        return Image.open(path)
    return None

st.title("📚 Field Tech Validator Tutorial")
st.write("Welcome to the Field Tech Validator! This app is designed to streamline your workflow from route planning to active field sampling, ensuring all data is validated and safely synced to the cloud.")

st.divider()

# --- Section 1: Dashboard ---
st.header("1. Executive Dashboard")
col1a, col1b = st.columns([1, 1.5])
with col1a:
    img_dash = load_image("tutorial_dashboard.png")
    if img_dash: st.image(img_dash, use_container_width=True)
with col1b:
    st.markdown("""
    The **Dashboard** is your high-level overview. 
    *   **Active Field Trip Status:** Located right at the top. If a trip is active, you'll see a live progress pie chart showing how many sites you've completed vs how many remain. If no trip is active, it will prompt you to start one.
    *   **Spatial Distribution:** View a heatmap of historical sampling locations.
    *   **Time-Series Visualizations:** Track long-term trends for specific parameters.
    """)

st.divider()

# --- Section 2: Preparation ---
st.header("2. Phase 1: Route Planning & Prep")
col2a, col2b = st.columns([1.5, 1])
with col2a:
    st.markdown("""
    Before heading into the field, you must start in **Field Data Collection**.
    *   **📍 Route:** Upload your daily route CSV. The app will use advanced OSRM routing to optimize your path and save you driving time.
    *   **⚙️ Params:** Select which water quality parameters you are measuring. (All parameters are enabled by default).
    *   **📝 SOP:** Upload your Standard Operating Procedures (TXT, PDF, Word). The app will load them into the **Field Assistant** so they can be read aloud to you while you work.
    """)
with col2b:
    img_prep = load_image("tutorial_prep.png")
    if img_prep: st.image(img_prep, use_container_width=True)

st.divider()

# --- Section 3: Active Collection ---
st.header("3. Phase 2: Active Data Collection")
col3a, col3b = st.columns([1, 1.5])
with col3a:
    img_samp = load_image("tutorial_sampling.png")
    if img_samp: st.image(img_samp, use_container_width=True)
with col3b:
    st.markdown("""
    Once you click **Begin Trip**, the app locks into offline-first mode.
    *   **Ground-Truth-Guard:** As you type in parameter values (pH, Turbidity, etc.), the app checks them in real-time. If a value is suspiciously high compared to historical averages, the box turns red and you will be warned.
    *   **SOP Audio Reader:** Expand the `📖 SOP Quick Reference` at the top and hit **🔊 Read Aloud**. Your device will read the instructions to you so you can keep your gloves on.
    *   **Saving:** Hitting 'Save' drops the data into a secure offline queue. You do not need internet access to collect data.
    """)

st.divider()

# --- Section 4: Gateway Sync ---
st.header("4. Gateway Sync & Cloud Upload")
col4a, col4b = st.columns([1.5, 1])
with col4a:
    st.markdown("""
    When you drive back into cell service, head to the **Gateway Sync** page.
    *   **Auto-Sync Mode:** Toggle the **🔄 Auto-Sync** switch ON. The app will automatically detect when you have internet and push your offline queue securely to the cloud.
    *   **Visual Audit:** You can expand the `🔍 View Buffered Records` section to see exactly what records are waiting to be uploaded.
    *   **Emergency Export:** If your device is broken or stuck offline, you can export the entire pending queue directly to a USB drive from here.
    """)
with col4b:
    img_sync = load_image("tutorial_sync.png")
    if img_sync: st.image(img_sync, use_container_width=True)

st.divider()

st.success("You're ready for the field! Head over to **Field Data Collection** to start your first trip.")
