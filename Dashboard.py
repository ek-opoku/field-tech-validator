import streamlit as st
import pandas as pd
import os
import plotly.express as px
from app_theme import apply_water_theme

st.set_page_config(page_title="Dashboard", layout="wide")
apply_water_theme()

@st.cache_data(show_spinner="Loading data...")
def load_data():
    file_path = "data_wide_imputed.csv.gz"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, parse_dates=["Date"])
        return df
    else:
        # Fallback dictionary of dummy data mirroring the CSV headers
        dummy_data = {
            "Date": pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03"]),
            "SiteID": ["LocA", "LocB", "LocC"],
            "Latitude": [40.0, 40.1, 40.2],
            "Longitude": [-104.0, -104.1, -104.2],
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
WATER_LINE_COLORS = ["#0b5ed7", "#0284c7", "#06b6d4"]


def _spatial_colorscale_for_param(param_display_name: str):
    """Continuous colorscale per spatial parameter (points + color bar), distinct from each other."""
    scales: dict[str, list[str]] = {
        "pH": px.colors.diverging.RdYlBu,
        "Temperature": px.colors.sequential.YlOrRd,
        "Turbidity": px.colors.sequential.YlGn,
        "Dissolved Oxygen (mg/L)": px.colors.sequential.Mint,
        "Dissolved Oxygen (% sat)": px.colors.sequential.Purples,
        "Nitrate": px.colors.sequential.OrRd,
        "Nitrite": px.colors.sequential.Reds,
        "Orthophosphate": px.colors.sequential.PuRd,
        "Conductivity": px.colors.sequential.Plasma,
        "Depth to Water": px.colors.sequential.Cividis,
    }
    return scales.get(param_display_name, px.colors.sequential.Viridis)

# Executive KPIs: short titles + units parsed from schema column names
_PARAM_SHORT_NAMES: dict[str, str] = {
    "pH (standard units)": "pH",
    "Temperature, water (deg C)": "Temperature",
    "Turbidity (NTU)": "Turbidity",
    "Oxygen, dissolved (mg/L)": "Dissolved oxygen",
    "Oxygen, dissolved (% saturation)": "DO saturation",
    "Nitrate, dissolved (mg/L as N)": "Nitrate",
    "Nitrite, dissolved (mg/L as N)": "Nitrite",
    "Orthophosphate, dissolved (mg/L as P)": "Orthophosphate",
    "Conductivity (uS/cm)": "Conductivity",
    "Depth to water table (m)": "Depth to water",
    "Latitude": "Latitude",
    "Longitude": "Longitude",
}


def _unit_from_column_name(col: str) -> str:
    if "(" in col and col.rstrip().endswith(")"):
        return col[col.index("(") + 1 : col.rindex(")")].strip()
    return ""


def _short_param_name(col: str) -> str:
    if col in _PARAM_SHORT_NAMES:
        return _PARAM_SHORT_NAMES[col]
    if "(" in col:
        base = col.split(" (")[0].strip()
        return base.split(",")[0].strip()[:22] if len(base) > 22 else base.split(",")[0].strip()
    return col[:22]


def executive_metric_label_value(col: str, val) -> tuple[str, str]:
    """Return (metric label with unit in parentheses, numeric value only) for executive metrics."""
    short = _short_param_name(col)
    unit = _unit_from_column_name(col)
    label = f"{short} ({unit})" if unit else short
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return label, "N/A"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return label, str(val)
    formatted = f"{v:,.2f}" if abs(v) >= 1000 else f"{v:.2f}"
    return label, formatted


st.title('FieldOps Groundwater Validator')

tab1, tab2, tab3 = st.tabs([
    'Executive Dashboard', 
    'Spatial Distribution', 
    'Time-Series Visualizations'
])

with tab1:
    st.header('Executive Dashboard')
    
    if st.session_state.get("trip_started", False):
        st.subheader("Active Field Trip Status")
        
        ordered = st.session_state.get("ordered_sites", [])
        completed = st.session_state.get("completed_sites", [])
        trip_data = st.session_state.get("trip_data", [])
        
        total_sites = len(ordered)
        completed_count = len(completed)
        remaining_count = max(0, total_sites - completed_count)
        
        if total_sites == 0:
            total_sites = max(1, completed_count)
            
        col_pie, col_stats, col_resume = st.columns([1.5, 1, 1.5])
        with col_pie:
            pie_data = pd.DataFrame({
                "Status": ["Completed", "Remaining"],
                "Count": [completed_count, remaining_count]
            })
            fig_pie = px.pie(
                pie_data, 
                values="Count", 
                names="Status", 
                title="Trip Progress", 
                color="Status", 
                color_discrete_map={"Completed": "#28a745", "Remaining": "#ffc107"}, 
                hole=0.4
            )
            fig_pie.update_layout(height=220, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with col_stats:
            st.metric("Sites completed (count)", f"{completed_count:,}")
            st.metric("Sites remaining (count)", f"{remaining_count:,}")
            
        with col_resume:
            st.write("") 
            st.write("")
            if st.button("Resume Data Collection", type="primary", use_container_width=True):
                st.switch_page("pages/1_Field_Data_Collection.py")
                
        if trip_data:
            st.write("**Current Trip Averages**")
            trip_df = pd.DataFrame(trip_data)
            for c in trip_df.columns:
                if c not in ["Date", "SiteID", "EdgeQCFlags"]:
                    trip_df[c] = pd.to_numeric(trip_df[c], errors="coerce")
            
            numeric_cols = [c for c in trip_df.columns if pd.api.types.is_numeric_dtype(trip_df[c]) and c not in ["Latitude", "Longitude"]]
            if numeric_cols:
                # Filter out columns that are completely NaN
                valid_cols = [c for c in numeric_cols if trip_df[c].notna().any()]
                if valid_cols:
                    rows = [st.columns(5) for _ in range((len(valid_cols) + 4) // 5)]
                    for i, c in enumerate(valid_cols):
                        val = trip_df[c].mean()
                        label, value_s = executive_metric_label_value(c, val)
                        rows[i // 5][i % 5].metric(label, value_s)
    else:
        st.info("💤 No active field trips currently ongoing.")
                    
    st.divider()

    st.subheader('Overall Database Metrics')
    st.metric("Active monitoring wells (count)", f"{df['SiteID'].nunique():,}")
    
    st.write("**Global averages (mean)**")
    all_params = [
        "pH (standard units)", "Temperature, water (deg C)", "Turbidity (NTU)", 
        "Oxygen, dissolved (mg/L)", "Oxygen, dissolved (% saturation)",
        "Nitrate, dissolved (mg/L as N)", "Nitrite, dissolved (mg/L as N)",
        "Orthophosphate, dissolved (mg/L as P)", "Conductivity (uS/cm)", "Depth to water table (m)"
    ]
    
    metric_cols = [st.columns(5) for _ in range(2)]
    for i, p in enumerate(all_params):
        if p in df.columns:
            val = df[p].mean()
            label, value_s = executive_metric_label_value(p, val)
            metric_cols[i // 5][i % 5].metric(label, value_s)

with tab2:
    st.header('Spatial Distribution')
    
    param_mapping = {
        "pH": "pH (standard units)",
        "Temperature": "Temperature, water (deg C)",
        "Turbidity": "Turbidity (NTU)",
        "Dissolved Oxygen (mg/L)": "Oxygen, dissolved (mg/L)",
        "Dissolved Oxygen (% sat)": "Oxygen, dissolved (% saturation)",
        "Nitrate": "Nitrate, dissolved (mg/L as N)",
        "Nitrite": "Nitrite, dissolved (mg/L as N)",
        "Orthophosphate": "Orthophosphate, dissolved (mg/L as P)",
        "Conductivity": "Conductivity (uS/cm)",
        "Depth to Water": "Depth to water table (m)"
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

    # Date filtering (use dataset min/max as defaults)
    min_date = df["Date"].min().date()
    max_date = df["Date"].max().date()
    date_range = st.date_input(
        "Date Range (applies to maps):",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_d, end_d = date_range
    else:
        start_d, end_d = min_date, max_date
            
    def create_map(param_name, column_name):
        df_map = df[(df["Date"].dt.date >= start_d) & (df["Date"].dt.date <= end_d)].dropna(
            subset=[column_name, "Latitude", "Longitude"]
        )
        # Aggregate to prevent plotting 1M points on the map
        df_map = df_map.groupby(["SiteID", "Latitude", "Longitude"], as_index=False)[column_name].mean()
        cmap = _spatial_colorscale_for_param(param_name)
        fig = px.scatter_mapbox(
            df_map,
            lat="Latitude",
            lon="Longitude",
            color=column_name,
            size=df_map[column_name].abs(),
            hover_name="SiteID",
            color_continuous_scale=cmap,
            size_max=15,
            zoom=7,
            mapbox_style="carto-positron",
            title=f"Spatial Distribution of {param_name} ({start_d}–{end_d})",
            height=800
        )
        fig.update_layout(
            margin={"r": 0, "t": 40, "l": 0, "b": 0},
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font={"color": "#0f172a"},
            coloraxis_colorbar={"title": param_name},
        )
        fig.update_traces(marker=dict(opacity=0.88))
        return fig
        
    if compare_mode:
        map_col1, map_col2 = st.columns(2)
        with map_col1:
            st.plotly_chart(create_map(selected_param, target_col), use_container_width=True, config={'scrollZoom': True}, theme=None)
        with map_col2:
            st.plotly_chart(create_map(selected_param2, target_col2), use_container_width=True, config={'scrollZoom': True}, theme=None)
    else:
        st.plotly_chart(create_map(selected_param, target_col), use_container_width=True, config={'scrollZoom': True}, theme=None)

with tab3:
    st.header('Time-Series Visualizations')
    st.write("Analyze temporal trends across the entire groundwater dataset or specific monitoring locations.")
    
    # 1. Filters
    # Site Filter
    all_sites = sorted(df["SiteID"].dropna().unique().tolist())
    
    if "ts_selected_sites" not in st.session_state:
        st.session_state.ts_selected_sites = []

    def clear_ts_selection():
        st.session_state.ts_selected_sites = []

    ms_col, clr_col = st.columns([4, 1])
    with ms_col:
        selected_sites = st.multiselect(
            "Select Monitoring Sites (leave empty for global average):", 
            options=all_sites, 
            key="ts_selected_sites",
            placeholder="Search and select sites..."
        )
    with clr_col:
        st.write("") # Vertical spacing
        st.write("") 
        st.button("❌ Clear Selection", key="clear_ts_btn", use_container_width=True, on_click=clear_ts_selection)

    filter_col1, filter_col2, filter_col3 = st.columns(3)
    
    # Parameters to choose from
    all_ts_params = [
        "pH (standard units)", "Temperature, water (deg C)", "Turbidity (NTU)", 
        "Oxygen, dissolved (mg/L)", "Oxygen, dissolved (% saturation)",
        "Nitrate, dissolved (mg/L as N)", "Nitrite, dissolved (mg/L as N)",
        "Orthophosphate, dissolved (mg/L as P)", "Conductivity (uS/cm)", "Depth to water table (m)"
    ]
    # Filter only available columns
    available_ts_params = [p for p in all_ts_params if p in df.columns]
    
    with filter_col1:
        selected_ts_param = st.selectbox("Select Parameter:", options=available_ts_params, index=0)
        
    with filter_col2:
        agg_level = st.selectbox("Aggregation Level:", options=["Daily", "Weekly", "Monthly"], index=0)
        
    with filter_col3:
        min_date = df["Date"].min().date()
        max_date = df["Date"].max().date()
        date_range = st.date_input("Date Range:", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_d, end_d = date_range
    else:
        start_d, end_d = min_date, max_date
        
    # 2. Data Preparation
    # Filter by date
    df_filtered = df[(df["Date"].dt.date >= start_d) & (df["Date"].dt.date <= end_d)].copy()
    
    if selected_sites:
        df_filtered = df_filtered[df_filtered["SiteID"].isin(selected_sites)]
        color_col = "SiteID"
    else:
        color_col = None

    # Aggregate
    if agg_level == "Daily":
        df_filtered["AggDate"] = df_filtered["Date"].dt.date
    elif agg_level == "Weekly":
        df_filtered["AggDate"] = df_filtered["Date"].dt.to_period("W").dt.start_time
    else:
        df_filtered["AggDate"] = df_filtered["Date"].dt.to_period("M").dt.start_time
        
    if color_col:
        df_agg = df_filtered.groupby(["AggDate", "SiteID"])[selected_ts_param].mean().reset_index()
    else:
        df_agg = df_filtered.groupby("AggDate")[selected_ts_param].mean().reset_index()
        
    df_agg.rename(columns={"AggDate": "Date"}, inplace=True)
    
    def make_publication_ready(fig, x_title, y_title):
        fig.update_layout(
            template="simple_white",
            plot_bgcolor="white",
            paper_bgcolor="white",
            font=dict(family="Inter, sans-serif", size=14, color="black"),
            title=dict(font=dict(size=18, family="Inter, sans-serif", color="black"), x=0.5),
            showlegend=True,
            legend=dict(title_text=""),
            margin=dict(l=60, r=20, t=60, b=50),
            hovermode="x unified"
        )
        fig.update_xaxes(
            title_text=x_title,
            showgrid=False,
            showline=True, linewidth=1.5, linecolor='black',
            ticks="outside", tickwidth=1.5, tickcolor='black', ticklen=6
        )
        fig.update_yaxes(
            title_text=y_title,
            showgrid=False,
            showline=True, linewidth=1.5, linecolor='black',
            ticks="outside", tickwidth=1.5, tickcolor='black', ticklen=6
        )
        return fig

    # 3. Chart Generation
    if df_agg.empty or df_agg[selected_ts_param].isna().all():
        st.warning("No data available for the selected filters.")
    else:
        y_col = selected_ts_param
        title_str = f"Temporal Trend: {y_col}" if color_col else f"Global Average: {y_col}"
        
        # If no sites selected, use specialized area charts for some parameters. If sites selected, use multiple lines.
        if not color_col and any(n in y_col for n in ["Nitrate", "Nitrite", "Orthophosphate", "Turbidity"]):
            fig_ts = px.area(
                df_agg, x="Date", y=y_col, title=title_str,
                color_discrete_sequence=["#10b981"]
            )
            fig_ts.update_traces(line=dict(width=2.5))
        elif not color_col and "Depth" in y_col:
            fig_ts = px.area(
                df_agg, x="Date", y=y_col, title=title_str,
                color_discrete_sequence=["#6366f1"]
            )
            fig_ts.update_yaxes(autorange="reversed")
            fig_ts.update_traces(line=dict(width=2.5))
        else:
            # Use line charts
            colors = px.colors.qualitative.Safe if color_col else (["#3b82f6"] if "Oxygen" in y_col else ["#0b5ed7"])
            fig_ts = px.line(
                df_agg, x="Date", y=y_col, color=color_col, title=title_str,
                color_discrete_sequence=colors
            )
            fig_ts.update_traces(line=dict(width=2.5))
            if "Depth" in y_col:
                fig_ts.update_yaxes(autorange="reversed")
            
        # Add danger zones/limits based on USGS/EPA thresholds
        if "Nitrate" in y_col:
            fig_ts.add_hline(y=2.0, line_dash="dash", line_color="green", annotation_text="Background (<2.0)", annotation_font_color="green")
            fig_ts.add_hline(y=10.0, line_dash="dash", line_color="red", annotation_text="EPA MCL (10.0)", annotation_font_color="red")
            
        if "Nitrite" in y_col:
            fig_ts.add_hline(y=1.0, line_dash="dash", line_color="red", annotation_text="EPA MCL (1.0)", annotation_font_color="red")
            
        if "Orthophosphate" in y_col:
            fig_ts.add_hline(y=0.03, line_dash="dash", line_color="green", annotation_text="Background (0.03)", annotation_font_color="green")
            fig_ts.add_hline(y=0.10, line_dash="dash", line_color="red", annotation_text="High Concern (>0.1)", annotation_font_color="red")
            
        if "Oxygen, dissolved (% saturation)" in y_col:
            fig_ts.add_hrect(y0=80, y1=120, line_width=0, fillcolor="green", opacity=0.1, annotation_text="Healthy (80-120%)", annotation_position="top left")
            
        if "Oxygen, dissolved (mg/L)" in y_col:
            fig_ts.add_hrect(
                y0=0, y1=1.0, line_width=0, fillcolor="red", opacity=0.15,
                annotation_text="Anoxic/Hypoxic (<1.0 mg/L)", annotation_position="top left",
                annotation_font=dict(color="red", size=12)
            )
            fig_ts.add_hline(y=5.0, line_dash="dash", line_color="green", annotation_text="Oxic (>5.0)", annotation_font_color="green")
            
        if "Turbidity" in y_col:
            fig_ts.add_hline(y=5.0, line_dash="dash", line_color="green", annotation_text="Clear Water (<5.0)", annotation_font_color="green")
            fig_ts.add_hline(y=10.0, line_dash="dash", line_color="orange", annotation_text="Stability Limit (10.0)", annotation_font_color="orange")
            
        if "pH" in y_col:
            fig_ts.add_hline(y=6.5, line_dash="dash", line_color="#d97706", line_width=2, annotation_text="Lower Limit (6.5)", annotation_font_color="#d97706")
            fig_ts.add_hline(y=8.5, line_dash="dash", line_color="#d97706", line_width=2, annotation_text="Upper Limit (8.5)", annotation_font_color="#d97706")
            
        fig_ts = make_publication_ready(fig_ts, "Date", y_col)
        st.plotly_chart(fig_ts, use_container_width=True, theme=None)
        
    st.divider()
    
    # 4. Cross-Parameter Correlation
    st.subheader("Explore Correlations")
    sc_col1, sc_col2, sc_col3 = st.columns(3)
    with sc_col1:
        x_param = st.selectbox("X-Axis Parameter:", options=available_ts_params, index=available_ts_params.index("Temperature, water (deg C)") if "Temperature, water (deg C)" in available_ts_params else 0)
    with sc_col2:
        y_param = st.selectbox("Y-Axis Parameter:", options=available_ts_params, index=available_ts_params.index("Oxygen, dissolved (mg/L)") if "Oxygen, dissolved (mg/L)" in available_ts_params else min(1, len(available_ts_params)-1))
    with sc_col3:
        scatter_site = st.selectbox("Select Site for Correlation:", options=["All Sites"] + all_sites, index=0)
        
    if x_param and y_param:
        # Filter raw data for scatter plot to preserve independent point distribution
        df_corr = df[(df["Date"].dt.date >= start_d) & (df["Date"].dt.date <= end_d)].copy()
        
        if scatter_site != "All Sites":
            df_corr = df_corr[df_corr["SiteID"] == scatter_site]
            sc_color_col = None
        else:
            if selected_sites:
                df_corr = df_corr[df_corr["SiteID"].isin(selected_sites)]
                sc_color_col = "SiteID"
            else:
                sc_color_col = None
            
        df_corr = df_corr.dropna(subset=[x_param, y_param])
        if len(df_corr) > 5000:
            df_corr = df_corr.sample(n=5000, random_state=42)
            
        if df_corr.empty:
            st.warning("No correlation data available for the selected parameters and filters.")
        else:
            try:
                import statsmodels.api as sm
                has_sm = True
            except ImportError:
                has_sm = False
                
            fig_scatter = px.scatter(
                df_corr, x=x_param, y=y_param, color=sc_color_col,
                title=f"Correlation: {x_param} vs {y_param} ({scatter_site})",
                color_discrete_sequence=px.colors.qualitative.Safe if sc_color_col else ["#0ea5e9"],
                opacity=0.7 if sc_color_col else 0.5,
                trendline="ols" if has_sm and len(df_corr) > 5 else None
            )
            fig_scatter.update_traces(marker=dict(size=8, line=dict(width=1, color='DarkSlateGrey')))
            fig_scatter = make_publication_ready(fig_scatter, x_param, y_param)
            st.plotly_chart(fig_scatter, use_container_width=True, theme=None)


