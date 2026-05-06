import streamlit as st
from app_theme import apply_water_theme
from PIL import Image
from pathlib import Path

st.set_page_config(page_title="App Tutorial", layout="centered", initial_sidebar_state="expanded")
apply_water_theme()

project_root = Path(__file__).resolve().parents[1]

def load_image(filename):
    path = project_root / "assets" / filename
    if path.exists():
        return Image.open(path)
    return None

if "tutorial_step" not in st.session_state:
    st.session_state.tutorial_step = 0

steps = [
    {"title": "Welcome to Field Tech Validator", "content": "intro"},
    {"title": "1. Executive Dashboard", "content": "dashboard"},
    {"title": "2. Phase 1: Route Planning & Prep", "content": "prep"},
    {"title": "3. Phase 2: Active Data Collection", "content": "sampling"},
    {"title": "4. Gateway Sync & Cloud Upload", "content": "sync"},
    {"title": "5. Chain of Custody", "content": "coc"}
]

current_step = st.session_state.tutorial_step

if current_step == -1:
    st.title("📚 Tutorial Concluded")
    st.success("You're ready for the field! Head over to **Field Data Collection** from the sidebar to start your first trip.")
    if st.button("Restart Tutorial"):
        st.session_state.tutorial_step = 0
        st.rerun()
else:
    step_data = steps[current_step]
    st.title(step_data["title"])
    
    # Progress bar
    st.progress(current_step / max(1, len(steps) - 1))
    
    st.write("") # spacer
    
    if step_data["content"] == "intro":
        st.write("Welcome to the interactive Field Tech Validator tutorial! This app is designed to streamline your workflow from route planning to active field sampling, ensuring all data is validated and safely synced to the cloud.")
        st.info("Click **Next** below to start learning how to use the app.")
        
    elif step_data["content"] == "dashboard":
        img = load_image("tutorial_dashboard.png")
        if img: st.image(img, use_container_width=True, caption="Executive Dashboard (Mobile View)")
        st.markdown("""
        The **Dashboard** is your high-level overview. 
        *   **Active Field Trip Status:** Located at the top. If a trip is active, you'll see a live progress pie chart. If not, it will prompt you to start one.
        *   **Spatial Distribution:** View a heatmap of historical sampling locations.
        *   **Time-Series Visualizations:** Track long-term trends for specific parameters.
        """)
        
    elif step_data["content"] == "prep":
        img = load_image("tutorial_prep.png")
        if img: st.image(img, use_container_width=True, caption="Field Data Collection - Phase 1")
        st.markdown("""
        Before heading into the field, you must start in **Field Data Collection**.
        *   **📍 Route:** Upload your daily route CSV or select a default site.
        *   **⚙️ Params:** Select which water quality parameters you are measuring.
        *   **📝 SOP:** Upload your Standard Operating Procedures (TXT, PDF, Word). The app will load them into the **Field Assistant** so they can be read aloud to you.
        """)
        
    elif step_data["content"] == "sampling":
        img = load_image("tutorial_sampling.png")
        if img: st.image(img, use_container_width=True, caption="Field Data Collection - Phase 2")
        st.markdown("""
        Once you click **Begin Trip**, the app locks into offline-first mode.
        *   **Ground-Truth-Guard:** As you type in parameter values, the app checks them in real-time against historical averages. If a value is suspicious, you'll be warned.
        *   **SOP Audio Reader:** Expand the `📖 SOP Quick Reference` at the top and hit **🔊 Read Aloud**.
        *   **Saving:** Hitting 'Save' drops the data into a secure offline queue. No internet required!
        """)
        
    elif step_data["content"] == "sync":
        img = load_image("tutorial_sync.png")
        if img: st.image(img, use_container_width=True, caption="Gateway Sync Dashboard")
        st.markdown("""
        When you drive back into cell service, head to the **Gateway Sync** page.
        *   **Auto-Sync Mode:** Toggle the **🔄 Auto-Sync** switch ON. The app will automatically push your offline queue securely to the cloud.
        *   **Visual Audit:** Expand the section to see exactly what records are waiting to be uploaded.
        *   **Emergency Export:** Export the entire pending queue directly to a USB drive from here.
        """)
        
    elif step_data["content"] == "coc":
        img = load_image("tutorial_coc.png")
        if img: st.image(img, use_container_width=True, caption="Chain of Custody Generator")
        st.markdown("""
        The **Chain of Custody** page is for generating compliance reports.
        *   You can select any active or completed trip.
        *   Clicking **Generate PDF Report** will instantly create a formal, printable Chain of Custody document containing all your timestamps, coordinates, and signatures.
        """)

    st.divider()
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if current_step > 0:
            if st.button("⬅️ Previous", use_container_width=True):
                st.session_state.tutorial_step -= 1
                st.rerun()
    with col2:
        if st.button("❌ End Tutorial", use_container_width=True, type="secondary"):
            st.session_state.tutorial_step = -1
            st.rerun()
    with col3:
        if current_step < len(steps) - 1:
            if st.button("Next ➡️", use_container_width=True, type="primary"):
                st.session_state.tutorial_step += 1
                st.rerun()
        else:
            if st.button("Finish ✅", use_container_width=True, type="primary"):
                st.session_state.tutorial_step = -1
                st.rerun()
