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
    # Fallback to the original ones if the granular ones didn't generate
    fallback = filename.replace("_route", "").replace("_params", "").replace("_sop", "")
    fallback_path = project_root / "assets" / fallback
    if fallback_path.exists():
        return Image.open(fallback_path)
    return None

if "tutorial_step" not in st.session_state:
    st.session_state.tutorial_step = 0

steps = [
    {"title": "Welcome to Field Tech Validator", "content": "intro"},
    {"title": "1. Executive Dashboard", "content": "dashboard"},
    {"title": "2. Phase 1: Route Planning", "content": "route"},
    {"title": "3. Phase 1: Parameters & Cloud Config", "content": "params"},
    {"title": "4. Phase 1: SOP Document Upload", "content": "sop"},
    {"title": "5. Phase 2: Active Data Collection", "content": "sampling"},
    {"title": "6. Phase 2: Field Assistant", "content": "assistant"},
    {"title": "7. Gateway Sync & Cloud Upload", "content": "sync"},
    {"title": "8. Chain of Custody", "content": "coc"}
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
        st.write("Welcome to the **Interactive Field Tech Validator Tutorial**! This app is your daily companion, designed to streamline your workflow from route planning to active field sampling, ensuring all data is validated and safely synced to the cloud.")
        st.info("Click **Next** below to start the comprehensive guide.")
        
    elif step_data["content"] == "dashboard":
        st.markdown("""
        The **Dashboard** is your high-level overview. Always check this first.
        *   **Active Field Trip Status:** Located at the very top. If you have an ongoing trip, you'll see a live progress pie chart tracking your completed vs remaining sites. If no trip is active, it will prompt you to start one.
        *   **Spatial Distribution:** View a heatmap of historical sampling locations to understand the geographic spread of the wells.
        *   **Time-Series Visualizations:** Track long-term trends for specific parameters.
        """)
        img = load_image("tutorial_dashboard.png")
        if img: st.image(img, use_container_width=True, caption="Executive Dashboard Overview")
        
    elif step_data["content"] == "route":
        st.markdown("""
        To begin a new field trip, navigate to **Field Data Collection**. The first step is defining your route:
        *   **Upload CSV:** You can drop a CSV containing your site list.
        *   **Select Existing Sites:** Use the multiselect box to pick sites that are already loaded in the database.
        *   **Add New Site Manually:** If you are visiting a brand new well, expand the `➕ Add New Site Manually` section. Type in the Site ID, Latitude, and Longitude, and click "Add Custom Site". It will immediately appear in your selection box!
        *   **Optimize:** Once your sites have been uploaded, selected or added manually, hit **Optimize Route** to let the app calculate the most efficient driving path.
        """)
        img = load_image("tutorial_prep_route.png")
        if img: st.image(img, use_container_width=True, caption="Route & Sites Configuration")
        
    elif step_data["content"] == "params":
        st.markdown("""
        Next, move to the **⚙️ Parameters & Settings** tab.
        *   **Select Parameters:** By default, ALL parameters are pre-selected so you don't have to check them manually. You can uncheck any that you won't be testing today.
        *   **Advanced Configuration:** Expand this section to set up your cloud connection!
            *   Enter your **Cloud Ingest URL** (e.g., your central database endpoint).
            *   Select your **Compliance Standard** (like EPA or WHO). This standard will be used by the Ground-Truth-Guard to validate your inputs in real-time.
        """)
        img = load_image("tutorial_prep_params.png")
        if img: st.image(img, use_container_width=True, caption="Parameters & Advanced Configuration")
        
    elif step_data["content"] == "sop":
        st.markdown("""
        The final prep step is the **📝 Instructions** tab.
        *   **SOP Upload:** You can upload your Standard Operating Procedures as a `PDF`, `Word Doc (.docx)`, `Markdown`, or `TXT` file.
        *   The app will parse the document text and save it into the system so that it can be read aloud to you while you are physically taking samples.
        *   Once your route, parameters, and SOP are set, you are ready to hit **Begin Trip**.
        """)
        img = load_image("tutorial_prep_sop.png")
        if img: st.image(img, use_container_width=True, caption="SOP Document Upload")
        
    elif step_data["content"] == "sampling":
        st.markdown("""
        Welcome to **Phase 2: Active Data Collection**. The app now operates fully offline.
        *   **Selecting a Site:** Pick your current physical location from the dropdown. The app will load the historical averages for that specific well.
        *   **Ground-Truth-Guard (QA/QC):** As you type in parameter values, the app checks them instantly. 
            *   If you type a value that is unusually high compared to the historical average (e.g. a massive spike in Turbidity), the input field will turn red and throw a **WARNING**. 
            *   This prevents typos and catches bad sensor calibrations right there in the field!
        *   **Saving:** Hitting 'Save' drops the validated data into a secure offline queue.
        """)
        img = load_image("tutorial_sampling.png")
        if img: st.image(img, use_container_width=True, caption="Active Data Collection & QA/QC Guard")
        
    elif step_data["content"] == "assistant":
        st.markdown("""
        Also in Phase 2, you have access to the **Field Assistant**.
        *   Look for the `📖 SOP Quick Reference` expander near the top of the collection screen.
        *   **Read Aloud Feature:** Expand the section and click the **🔊 Read Aloud** button. Your device will use offline text-to-speech to read the SOP instructions you uploaded earlier. 
        *   This allows you to keep your gloves on and focus entirely on sampling the water without having to look back at the screen!
        """)
        img = load_image("tutorial_sampling.png")
        if img: st.image(img, use_container_width=True, caption="Field Assistant with Read-Aloud")
        
    elif step_data["content"] == "sync":
        st.markdown("""
        When your trip is complete and you drive back into cell service, head to the **Gateway Sync** page.
        *   **Auto-Sync Mode:** Toggle the **🔄 Auto-Sync Mode** switch to ON. The app will automatically detect your internet connection and push your offline queue securely to the cloud ingest URL you configured.
        *   **Visual Audit:** Expand the `🔍 View Buffered Records` section to see a spreadsheet-like view of exactly what records are waiting to be uploaded.
        *   **Emergency Export:** If you are permanently offline, you can use the **Download Buffer to USB Backup** button to manually export the pending queue.
        """)
        img = load_image("tutorial_sync.png")
        if img: st.image(img, use_container_width=True, caption="Gateway Sync Dashboard")
        
    elif step_data["content"] == "coc":
        st.markdown("""
        The **Chain of Custody** page is for generating official compliance reports.
        *   Select the Active Trip (or a past completed trip) from the dropdown.
        *   The app will compile all coordinates, user data, timestamps, and readings into a formalized table.
        *   Clicking **Generate PDF Report** will instantly create a formal, printable Chain of Custody document for legal and regulatory tracking.
        """)
        img = load_image("tutorial_coc.png")
        if img: st.image(img, use_container_width=True, caption="Chain of Custody Generator")

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
