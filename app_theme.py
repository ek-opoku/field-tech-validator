import streamlit as st


def apply_water_theme() -> None:
    st.markdown(
        """
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

          /* Global white surface + readable text */
          .stApp,
          [data-testid="stAppViewContainer"],
          [data-testid="stHeader"],
          section.main,
          section.main > div {
            background: #ffffff !important;
          }

          /* Safely apply font to text elements without overriding icons */
          html, body, [class*="css"], p, a, h1, h2, h3, h4, h5, h6, label, li {
            font-family: 'Inter', sans-serif !important;
          }

          .stApp,
          .stApp p,
          .stApp span,
          .stApp div,
          .stApp label,
          .stMarkdown,
          .stCaption {
            color: #0f172a !important;
          }

          h1, h2, h3 {
            color: #0b5ed7 !important;
          }

          /* Sidebar: solid blue with white text */
          [data-testid="stSidebar"] {
            background: #0b5ed7 !important;
            border-right: 1px solid #0a53be !important;
          }
          [data-testid="stSidebar"] * {
            color: #ffffff !important;
          }
          [data-testid="stSidebar"] .stTextInput input,
          [data-testid="stSidebar"] .stNumberInput input,
          [data-testid="stSidebar"] [data-baseweb="select"] > div {
            background: #0a53be !important;
            color: #ffffff !important;
            border-color: #ffffff !important;
          }
          [data-testid="stSidebar"] .stTextInput input::placeholder {
            color: rgba(255, 255, 255, 0.85) !important;
          }
          [data-testid="stSidebar"] [data-baseweb="tag"] {
            background: #0848a4 !important;
            color: #ffffff !important;
            border: 1px solid rgba(255, 255, 255, 0.6) !important;
          }

          /* Multipage nav links in sidebar */
          [data-testid="stSidebarNav"] a {
            color: #ffffff !important;
            border-radius: 8px !important;
          }
          [data-testid="stSidebarNav"] a:hover {
            background: rgba(255, 255, 255, 0.18) !important;
          }
          [data-testid="stSidebarNav"] a[aria-current="page"] {
            background: rgba(255, 255, 255, 0.25) !important;
            font-weight: 700 !important;
          }

          /* Buttons: blue theme + white text */
          .stButton > button,
          button[kind="primary"],
          button[kind="secondary"] {
            background: #0b5ed7 !important;
            color: #ffffff !important;
            border: 1px solid #0a53be !important;
            border-radius: 10px !important;
          }
          .stButton > button:hover,
          button[kind="primary"]:hover,
          button[kind="secondary"]:hover {
            background: #0a53be !important;
            border-color: #0848a4 !important;
          }

          /* Tabs */
          button[data-baseweb="tab"] {
            background: #eff6ff !important;
            color: #0f172a !important;
            border-radius: 10px !important;
          }
          button[data-baseweb="tab"][aria-selected="true"] {
            background: #0b5ed7 !important;
            color: #ffffff !important;
          }

          /* Blue pills/chips/badges should always use white text */
          [data-baseweb="tag"],
          [data-baseweb="tag"] span,
          .stTabs [role="tablist"] [aria-selected="true"],
          .stTabs [role="tablist"] [aria-selected="true"] * {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
          }
          [data-baseweb="tag"] {
            background: #0a53be !important;
            border-color: rgba(255, 255, 255, 0.55) !important;
          }

          /* Input fields in main area */
          [data-testid="stForm"] input,
          [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
          [data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
          [data-testid="stDateInput"] input {
            background-color: #f8fafc !important;
            color: #0f172a !important;
            border: 1px solid #cbd5e1 !important;
          }
          [data-baseweb="popover"] > div {
            background-color: #ffffff !important;
          }

          /* Prevent font override for material icons */
          span.material-symbols-rounded, 
          span.material-icons,
          .material-symbols-rounded,
          .material-icons {
            font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )
