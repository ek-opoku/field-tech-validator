import streamlit as st


def apply_water_theme() -> None:
    st.markdown(
        """
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

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

          /* Sidebar: professional light rail (enterprise dashboard style) */
          [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 55%, #eef2f7 100%) !important;
            border-right: 1px solid #e2e8f0 !important;
            box-shadow: inset -1px 0 0 rgba(15, 23, 42, 0.04) !important;
          }
          [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding: 1.15rem 0.85rem 1.5rem 0.85rem !important;
          }
          [data-testid="stSidebar"] .block-container {
            padding-top: 0.35rem !important;
            padding-bottom: 1rem !important;
          }
          [data-testid="stSidebar"] label,
          [data-testid="stSidebar"] .stMarkdown,
          [data-testid="stSidebar"] .stMarkdown p {
            color: #475569 !important;
          }
          [data-testid="stSidebar"] .stCaption {
            color: #64748b !important;
          }

          [data-testid="stSidebar"] .stTextInput input,
          [data-testid="stSidebar"] .stNumberInput input,
          [data-testid="stSidebar"] [data-baseweb="select"] > div,
          [data-testid="stSidebar"] [data-baseweb="base-input"] > div {
            background: #ffffff !important;
            color: #0f172a !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 8px !important;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04) !important;
          }
          [data-testid="stSidebar"] [data-baseweb="select"] input,
          [data-testid="stSidebar"] [data-baseweb="select"] span,
          [data-testid="stSidebar"] [data-baseweb="select"] svg,
          [data-testid="stSidebar"] [data-baseweb="radio"] label,
          [data-testid="stSidebar"] [data-baseweb="checkbox"] label {
            color: #0f172a !important;
            fill: #0f172a !important;
          }
          [data-testid="stSidebar"] .stTextInput input::placeholder {
            color: #94a3b8 !important;
          }
          [data-testid="stSidebar"] [data-baseweb="tag"] {
            background: #e0e7ff !important;
            color: #1e3a8a !important;
            border: 1px solid #a5b4fc !important;
          }

          /* Multipage navigation */
          [data-testid="stSidebarNav"] {
            margin: 0 -0.15rem 0.75rem -0.15rem !important;
            padding: 0.35rem 0 0.85rem 0 !important;
            border-bottom: 1px solid #e2e8f0 !important;
          }
          [data-testid="stSidebarNav"] ul {
            gap: 0.2rem !important;
          }
          [data-testid="stSidebarNav"] li {
            margin: 0 !important;
          }
          [data-testid="stSidebarNav"] a {
            color: #334155 !important;
            font-weight: 500 !important;
            font-size: 0.9375rem !important;
            letter-spacing: -0.01em !important;
            padding: 0.62rem 0.85rem 0.62rem 0.75rem !important;
            margin: 0.1rem 0.2rem !important;
            border-radius: 8px !important;
            border-left: 3px solid transparent !important;
            transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease !important;
          }
          [data-testid="stSidebarNav"] a:hover {
            background: #ffffff !important;
            color: #0b5ed7 !important;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.07) !important;
          }
          [data-testid="stSidebarNav"] a[aria-current="page"] {
            background: #ffffff !important;
            color: #0b5ed7 !important;
            font-weight: 600 !important;
            border-left-color: #0b5ed7 !important;
            box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08) !important;
          }

          [data-testid="stSidebar"] .stButton > button {
            background: #0b5ed7 !important;
            color: #ffffff !important;
            border: 1px solid #0a53be !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            font-size: 0.9375rem !important;
            min-height: 2.5rem !important;
            padding: 0.45rem 0.85rem !important;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05) !important;
          }
          [data-testid="stSidebar"] .stButton > button:hover {
            background: #0a53be !important;
            border-color: #0848a4 !important;
            color: #ffffff !important;
          }

          /* Buttons: blue theme + white text */
          .stButton > button,
          button[kind="primary"],
          button[kind="secondary"] {
            background: #0b5ed7 !important;
            color: #ffffff !important;
            border: 1px solid #0a53be !important;
            border-radius: 10px !important;
            min-height: 2.75rem !important;
            padding: 0.6rem 1rem !important;
            font-weight: 600 !important;
          }
          .stButton > button:hover,
          button[kind="primary"]:hover,
          button[kind="secondary"]:hover {
            background: #0a53be !important;
            border-color: #0848a4 !important;
          }

          /* Tabs — room inside each label + space between tabs */
          .stTabs [role="tablist"],
          .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem !important;
            padding: 0.2rem 0 0.35rem 0 !important;
            flex-wrap: wrap !important;
          }
          button[data-baseweb="tab"],
          [data-testid="stTab"] {
            background: #eff6ff !important;
            color: #0f172a !important;
            border-radius: 10px !important;
            padding: 0.65rem 1.25rem !important;
            min-height: 2.75rem !important;
            line-height: 1.35 !important;
            box-sizing: border-box !important;
            margin: 0 !important;
          }
          button[data-baseweb="tab"] span,
          [data-testid="stTab"] span {
            padding: 0 !important;
            margin: 0 !important;
          }
          button[data-baseweb="tab"]:not([aria-selected="true"]) *,
          [data-testid="stTab"]:not([aria-selected="true"]) * {
            color: #0f172a !important;
            -webkit-text-fill-color: #0f172a !important;
          }
          button[data-baseweb="tab"][aria-selected="true"],
          [data-testid="stTab"][aria-selected="true"] {
            background: #0b5ed7 !important;
            color: #ffffff !important;
          }
          button[data-baseweb="tab"][aria-selected="true"] *,
          [data-testid="stTab"][aria-selected="true"] * {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
          }

          /* Blue pills/chips/badges should always use white text */
          [data-baseweb="tag"],
          [data-baseweb="tag"] span {
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
          [data-baseweb="popover"] [role="listbox"],
          [data-baseweb="popover"] [role="option"] {
            background: #ffffff !important;
            color: #0f172a !important;
          }
          [data-baseweb="menu"] li,
          [data-baseweb="menu"] li *,
          [data-baseweb="select"] [role="option"],
          [data-baseweb="select"] [role="option"] * {
            color: #0f172a !important;
          }

          /* Prevent font override for material icons */
          span.material-symbols-rounded, 
          span.material-icons,
          .material-symbols-rounded,
          .material-icons {
            font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
          }

          /* Metric Bubbles - Visually Neat */
          [data-testid="stMetric"] {
            background-color: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 16px !important;
            padding: 1.25rem !important;
            box-shadow: 0 4px 6px rgba(15, 23, 42, 0.05), 0 10px 15px rgba(15, 23, 42, 0.03) !important;
            text-align: center !important;
            transition: transform 0.2s ease, box-shadow 0.2s ease !important;
          }
          [data-testid="stMetric"]:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 6px 12px rgba(15, 23, 42, 0.08), 0 12px 20px rgba(15, 23, 42, 0.05) !important;
          }
          [data-testid="stMetricValue"] {
            color: #0b5ed7 !important;
            font-weight: 700 !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

