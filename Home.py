import streamlit as st
import pandas as pd
import os
import plotly.express as px
from app_theme import apply_water_theme

st.set_page_config(layout="wide")
apply_water_theme()

@st.cache_data
def load_data():
    file_path = "data_wide.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, parse_dates=["ActivityStartDate"])
        return df
    else:
        # Fallback dictionary of dummy data mirroring the CSV headers
        dummy_data = {
            "ActivityStartDate": pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03"]),
            "MonitoringLocationIdentifier": ["LocA", "LocB", "LocC"],
            "ActivityLocation/LatitudeMeasure": [40.0, 40.1, 40.2],
            "ActivityLocation/LongitudeMeasure": [-104.0, -104.1, -104.2],
            "Nitrate, dissolved (mg/L as N)": [1.0, 2.0, 1.5],
            "Nitrite, dissolved (mg/L as N)": [0.1, 0.2, 0.15],
            "Orthophosphate, dissolved (mg/L as P)": [0.05, 0.06, 0.04],
            "Oxygen, dissolved (% saturation)": [90.0, 85.0, 88.0],
            "Oxygen, dissolved (mg/L)": [8.0, 7.5, 7.8],
            "Temperature, water (deg C)": [15.0, 16.0, 14.5],
            "Turbidity (NTU)": [2.0, 3.0, 1.5],
            "pH (standard units)": [7.2, 7.4, 7.3]
        }
        return pd.DataFrame(dummy_data)

df = load_data()
WATER_SCALE = [
    [0.0, "#dbeafe"],
    [0.25, "#93c5fd"],
    [0.5, "#38bdf8"],
    [0.75, "#0ea5e9"],
    [1.0, "#0b5ed7"],
]
WATER_LINE_COLORS = ["#0b5ed7", "#0284c7", "#06b6d4"]

st.title('💧 FieldOps Groundwater Validator')

tab1, tab2, tab3 = st.tabs([
    '📊 Executive Dashboard', 
    '🗺️ Spatial Distribution', 
    '📈 Time-Series Visualizations'
])

with tab1:
    st.header('📊 Executive Dashboard')
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Samples", len(df))
    col2.metric("Active Wells", df['MonitoringLocationIdentifier'].nunique())
    col3.metric("Average pH", round(df['pH (standard units)'].mean(), 2))
    col4.metric("Average Temperature", round(df['Temperature, water (deg C)'].mean(), 2))

with tab2:
    st.header('🗺️ Spatial Distribution')
    
    param_mapping = {
        "pH": "pH (standard units)",
        "Temperature": "Temperature, water (deg C)",
        "Nitrate": "Nitrate, dissolved (mg/L as N)",
        "Turbidity": "Turbidity (NTU)"
    }
    
    opt_col1, opt_col2, opt_col3 = st.columns(3)
    
    with opt_col1:
        selected_param = st.selectbox("Select Parameter to Visualize:", options=list(param_mapping.keys()))
        target_col = param_mapping[selected_param]
        
    with opt_col2:
        st.write("") # Spacer
        st.write("") # Spacer
        compare_mode = st.checkbox("Enable side-by-side comparison")
        
    with opt_col3:
        if compare_mode:
            selected_param2 = st.selectbox("Select 2nd Parameter:", options=list(param_mapping.keys()), index=1)
            target_col2 = param_mapping[selected_param2]
            
    def create_map(param_name, column_name):
        df_map = df.dropna(subset=[column_name, "ActivityLocation/LatitudeMeasure", "ActivityLocation/LongitudeMeasure"])
        fig = px.scatter_mapbox(
            df_map,
            lat="ActivityLocation/LatitudeMeasure",
            lon="ActivityLocation/LongitudeMeasure",
            color=column_name,
            size=df_map[column_name].abs(),
            hover_name="MonitoringLocationIdentifier",
            color_continuous_scale=WATER_SCALE,
            size_max=15,
            zoom=7,
            mapbox_style="carto-positron",
            title=f"Spatial Distribution of {param_name}",
            height=800
        )
        fig.update_layout(
            margin={"r": 0, "t": 40, "l": 0, "b": 0},
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font={"color": "#0f172a"},
            coloraxis_colorbar={"title": param_name},
        )
        return fig
        
    if compare_mode:
        map_col1, map_col2 = st.columns(2)
        with map_col1:
            st.plotly_chart(create_map(selected_param, target_col), use_container_width=True, config={'scrollZoom': True})
        with map_col2:
            st.plotly_chart(create_map(selected_param2, target_col2), use_container_width=True, config={'scrollZoom': True})
    else:
        st.plotly_chart(create_map(selected_param, target_col), use_container_width=True, config={'scrollZoom': True})

with tab3:
    st.header('📈 Time-Series Visualizations')
    
    col1, col2 = st.columns(2)
    with col1:
        fig_ph = px.line(
            df,
            x="ActivityStartDate",
            y="pH (standard units)",
            title="pH Over Time",
            color_discrete_sequence=[WATER_LINE_COLORS[0]],
            markers=True,
        )
        fig_ph.update_layout(
            template="plotly_white",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font={"color": "#0f172a"},
        )
        st.plotly_chart(fig_ph, use_container_width=True)
        
    with col2:
        fig_temp = px.line(
            df,
            x="ActivityStartDate",
            y="Temperature, water (deg C)",
            title="Temperature Over Time",
            color_discrete_sequence=[WATER_LINE_COLORS[1]],
            markers=True,
        )
        fig_temp.update_layout(
            template="plotly_white",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font={"color": "#0f172a"},
        )
        st.plotly_chart(fig_temp, use_container_width=True)
        
    fig_scatter = px.scatter(
        df,
        x="Temperature, water (deg C)",
        y="Oxygen, dissolved (mg/L)",
        title="Temperature vs Dissolved Oxygen",
        color_discrete_sequence=[WATER_LINE_COLORS[2]],
    )
    fig_scatter.update_traces(marker={"size": 10, "opacity": 0.85})
    fig_scatter.update_layout(
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"color": "#0f172a"},
    )
    st.plotly_chart(fig_scatter, use_container_width=True)


