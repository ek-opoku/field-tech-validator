from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st
from app_theme import apply_water_theme


APP_TITLE = "Centralized Field Data Dashboard"
DATA_PATH = Path(__file__).resolve().parents[1] / "processed_water_data.csv"
WATER_DEEP_BLUE = "#0b5ed7"
WATER_MID_BLUE = "#0284c7"
WATER_AQUA = "#06b6d4"


RAW_TO_CLEAN = {
    "ActivityStartDate": "activity_start_date",
    "MonitoringLocationIdentifier": "monitoring_location_id",
    "ActivityLocation/LatitudeMeasure": "latitude",
    "ActivityLocation/LongitudeMeasure": "longitude",
    "Temperature, water (deg C)": "water_temp_c",
    "Turbidity (NTU)": "turbidity_ntu",
    "pH (standard units)": "ph",
    "Oxygen, dissolved (mg/L)": "dissolved_oxygen_mg_l",
}


def powerbi_css() -> None:
    st.markdown(
        """
        <style>
          .stApp {
            background: linear-gradient(180deg, #f6f7fb, #ffffff 65%);
          }
          section.main > div { max-width: 1200px; padding-top: 1.1rem; padding-bottom: 2.5rem; }

          .pbi-header {
            background: #ffffff;
            border: 1px solid rgba(16,24,40,0.10);
            border-radius: 16px;
            padding: 16px 16px;
            box-shadow: 0 12px 30px rgba(16,24,40,0.08);
            margin-bottom: 12px;
          }
          .pbi-title { font-size: 1.25rem; font-weight: 800; color: #101828; }
          .pbi-sub { font-size: 0.95rem; color: rgba(16,24,40,0.65); margin-top: 4px; }

          .metric-card {
            background: #ffffff;
            border: 1px solid rgba(16,24,40,0.10);
            border-radius: 16px;
            padding: 14px 14px;
            box-shadow: 0 12px 30px rgba(16,24,40,0.08);
          }
          .metric-label { font-size: 0.9rem; color: rgba(16,24,40,0.65); font-weight: 650; }
          .metric-value { font-size: 1.6rem; color: #101828; font-weight: 900; margin-top: 6px; }
          .metric-foot { font-size: 0.85rem; color: rgba(16,24,40,0.55); margin-top: 2px; }

          .panel {
            background: #ffffff;
            border: 1px solid rgba(16,24,40,0.10);
            border-radius: 16px;
            padding: 14px 14px;
            box-shadow: 0 12px 30px rgba(16,24,40,0.08);
          }
          .panel-title { font-size: 1.02rem; font-weight: 800; color: #101828; margin-bottom: 8px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def load_data(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    return df


def resolve_col(df: pd.DataFrame, raw_name: str) -> str | None:
    """
    Be resilient: `processed_water_data.csv` may have either raw headers (as supplied)
    or cleaned snake_case headers (from `prepare_water_data.py`).
    """
    if raw_name in df.columns:
        return raw_name
    clean = RAW_TO_CLEAN.get(raw_name)
    if clean and clean in df.columns:
        return clean
    return None


def coerce_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance between two points in kilometers.
    Kept dependency-free for a lightweight dashboard.
    """
    import math

    r = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_neighbor_route(points: list[tuple[float, float]]) -> tuple[list[int], float]:
    """
    Simple routing heuristic:
    - Start from the first point
    - Repeatedly visit the nearest unvisited point
    Returns (visit_order_indices, total_km).
    """
    if len(points) <= 1:
        return list(range(len(points))), 0.0

    unvisited = set(range(1, len(points)))
    order = [0]
    total = 0.0

    while unvisited:
        i = order[-1]
        lat1, lon1 = points[i]
        j = min(
            unvisited,
            key=lambda k: haversine_km(lat1, lon1, points[k][0], points[k][1]),
        )
        lat2, lon2 = points[j]
        total += haversine_km(lat1, lon1, lat2, lon2)
        order.append(j)
        unvisited.remove(j)

    return order, total


def ortools_route(points: list[tuple[float, float]]) -> tuple[list[int], float] | None:
    """
    Optional: use OR-Tools to solve a TSP-style route.
    Returns None if OR-Tools isn't installed or if problem size is too large.
    """
    if len(points) <= 1:
        return list(range(len(points))), 0.0
    if len(points) > 25:
        return None
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2  # type: ignore
    except Exception:
        return None

    # Build distance matrix in meters (integer costs).
    n = len(points)
    dist = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            dist[i][j] = int(haversine_km(points[i][0], points[i][1], points[j][0], points[j][1]) * 1000)

    manager = pywrapcp.RoutingIndexManager(n, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_cb(from_index: int, to_index: int) -> int:
        a = manager.IndexToNode(from_index)
        b = manager.IndexToNode(to_index)
        return dist[a][b]

    transit = routing.RegisterTransitCallback(distance_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(2)

    solution = routing.SolveWithParameters(params)
    if solution is None:
        return None

    order: list[int] = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        order.append(node)
        index = solution.Value(routing.NextVar(index))

    # Compute total km for reporting
    total_km = 0.0
    for a, b in zip(order, order[1:]):
        total_km += haversine_km(points[a][0], points[a][1], points[b][0], points[b][1])
    return order, total_km


st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="expanded")
apply_water_theme()
powerbi_css()

st.markdown(
    f"""
    <div class="pbi-header">
      <div class="pbi-title">{APP_TITLE}</div>
      <div class="pbi-sub">Review synced groundwater field readings (filtered by monitoring location).</div>
    </div>
    """,
    unsafe_allow_html=True,
)

df = load_data(DATA_PATH)
if df.empty:
    st.error(f"Could not find data at `{DATA_PATH}`. Place `processed_water_data.csv` at the repo root.")
    st.stop()

col_date = resolve_col(df, "ActivityStartDate") or resolve_col(df, "activity_start_date")
col_loc = resolve_col(df, "MonitoringLocationIdentifier") or resolve_col(df, "monitoring_location_id")
col_lat = resolve_col(df, "ActivityLocation/LatitudeMeasure") or resolve_col(df, "latitude")
col_lon = resolve_col(df, "ActivityLocation/LongitudeMeasure") or resolve_col(df, "longitude")
col_ph = resolve_col(df, "pH (standard units)") or resolve_col(df, "ph")
col_turb = resolve_col(df, "Turbidity (NTU)") or resolve_col(df, "turbidity_ntu")
col_do = resolve_col(df, "Oxygen, dissolved (mg/L)") or resolve_col(df, "dissolved_oxygen_mg_l")
col_temp = resolve_col(df, "Temperature, water (deg C)") or resolve_col(df, "water_temp_c")

needed = {
    "ActivityStartDate": col_date,
    "MonitoringLocationIdentifier": col_loc,
    "pH (standard units)": col_ph,
    "Turbidity (NTU)": col_turb,
    "Oxygen, dissolved (mg/L)": col_do,
    "Temperature, water (deg C)": col_temp,
}
missing = [k for k, v in needed.items() if v is None]
if missing:
    st.error("Missing required columns in `processed_water_data.csv`:\n- " + "\n- ".join(missing))
    st.stop()

df = df.copy()
df["_date"] = coerce_datetime(df[col_date])
df["_loc"] = df[col_loc].astype("string").fillna("").str.strip()
df["_lat"] = coerce_numeric(df[col_lat]) if col_lat else pd.Series([pd.NA] * len(df))
df["_lon"] = coerce_numeric(df[col_lon]) if col_lon else pd.Series([pd.NA] * len(df))
df["_ph"] = coerce_numeric(df[col_ph])
df["_turb"] = coerce_numeric(df[col_turb])
df["_do"] = coerce_numeric(df[col_do])
df["_temp"] = coerce_numeric(df[col_temp])

df = df[df["_date"].notna() & (df["_loc"] != "")]

with st.sidebar:
    st.header("Filters")
    locations = sorted([x for x in df["_loc"].dropna().unique().tolist() if str(x).strip() != ""])
    selected_locs = st.multiselect("MonitoringLocationIdentifier", options=locations, default=locations[: min(8, len(locations))])

    min_d = df["_date"].min().date()
    max_d = df["_date"].max().date()
    date_range = st.date_input("Date range", value=(min_d, max_d), min_value=min_d, max_value=max_d)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_d, end_d = date_range
    else:
        start_d, end_d = min_d, max_d

    recent_points = st.slider("Sparkline points", min_value=10, max_value=200, value=60, step=10)
    use_ortools = st.toggle(
        "Optimize route (OR-Tools)",
        value=False,
        help="Uses OR-Tools for a better route (if installed). Falls back to nearest-neighbor.",
    )

f = df.copy()
if selected_locs:
    f = f[f["_loc"].isin(selected_locs)]
f = f[(f["_date"].dt.date >= start_d) & (f["_date"].dt.date <= end_d)]

# Metric cards
avg_ph = float(f["_ph"].mean()) if f["_ph"].notna().any() else float("nan")
max_turb = float(f["_turb"].max()) if f["_turb"].notna().any() else float("nan")
samples = len(f)
date_span = f"{start_d.isoformat()} → {end_d.isoformat()}"

mc1, mc2, mc3 = st.columns([1, 1, 1])
with mc1:
    avg_ph_label = "—" if avg_ph != avg_ph else f"{avg_ph:.2f}"
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-label">Average pH (standard units)</div>
          <div class="metric-value">{avg_ph_label}</div>
          <div class="metric-foot">{date_span}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with mc2:
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-label">Max Turbidity (NTU)</div>
          <div class="metric-value">{("—" if max_turb != max_turb else f"{max_turb:.2f}")}</div>
          <div class="metric-foot">{date_span}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with mc3:
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-label">Samples in view</div>
          <div class="metric-value">{samples:,}</div>
          <div class="metric-foot">{len(selected_locs) if selected_locs else 0} location(s) selected</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

# Sparklines (recent trends)
import altair as alt  # noqa: E402


def sparkline(data: pd.DataFrame, y: str, title: str):
    s = data.sort_values("_date").dropna(subset=[y]).tail(int(recent_points))
    if s.empty:
        st.info(f"No data for {title} in the current filter.")
        return
    c = (
        alt.Chart(s)
        .mark_line(color=WATER_DEEP_BLUE, strokeWidth=2)
        .encode(
            x=alt.X("_date:T", title=None, axis=alt.Axis(labels=False, ticks=False, domain=False)),
            y=alt.Y(f"{y}:Q", title=None),
            tooltip=[alt.Tooltip("_date:T", title="Date"), alt.Tooltip(f"{y}:Q", title=title)],
        )
        .properties(height=120)
    )
    st.altair_chart(c, use_container_width=True)


left, right = st.columns([1, 1])
with left:
    st.markdown("<div class='panel'><div class='panel-title'>Recent dissolved oxygen trend</div>", unsafe_allow_html=True)
    sparkline(f, "_do", "Oxygen, dissolved (mg/L)")
    st.markdown("</div>", unsafe_allow_html=True)
with right:
    st.markdown("<div class='panel'><div class='panel-title'>Recent temperature trend</div>", unsafe_allow_html=True)
    sparkline(f, "_temp", "Temperature, water (deg C)")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

st.markdown("<div class='panel'><div class='panel-title'>GIS map + route optimization + risk</div>", unsafe_allow_html=True)

# Risk score derived from historical distributions:
# - We compute robust-ish normalization using median & IQR for turbidity and pH deviation from neutral,
#   and "low dissolved oxygen" and "high temperature" pressure.
# - Score is 0–100; markers are color-coded by risk.
hist = df.dropna(subset=["_loc"]).copy()

def _series_iqr(s: pd.Series) -> tuple[float, float, float]:
    s2 = s.dropna()
    if s2.empty:
        return 0.0, 0.0, 1.0
    q1 = float(s2.quantile(0.25))
    q2 = float(s2.quantile(0.50))
    q3 = float(s2.quantile(0.75))
    iqr = max(1e-9, q3 - q1)
    return q1, q2, iqr


_, turb_med, turb_iqr = _series_iqr(hist["_turb"])
_, do_med, do_iqr = _series_iqr(hist["_do"])
_, temp_med, temp_iqr = _series_iqr(hist["_temp"])

# Latest sample per location within current filter window.
latest = (
    f.sort_values("_date")
    .groupby("_loc", as_index=False)
    .tail(1)
    .copy()
)

latest = latest.dropna(subset=["_lat", "_lon"])
latest = latest[(latest["_lat"].between(-90, 90)) & (latest["_lon"].between(-180, 180))]

if latest.empty:
    st.info("No mappable locations in the current filter (missing/invalid latitude/longitude).")
else:
    # Compute risk (0–100) from historical stats; higher turbidity / higher temp / low DO / extreme pH => higher risk.
    def clamp01(x: float) -> float:
        return max(0.0, min(1.0, x))

    def risk_row(row: pd.Series) -> float:
        turb = float(row["_turb"]) if pd.notna(row["_turb"]) else turb_med
        do = float(row["_do"]) if pd.notna(row["_do"]) else do_med
        temp = float(row["_temp"]) if pd.notna(row["_temp"]) else temp_med
        phv = float(row["_ph"]) if pd.notna(row["_ph"]) else 7.0

        # Normalized components (rough, interpretable):
        turb_r = clamp01((turb - turb_med) / (3.0 * turb_iqr))
        do_r = clamp01((do_med - do) / (3.0 * do_iqr))  # lower DO => higher risk
        temp_r = clamp01((temp - temp_med) / (3.0 * temp_iqr))
        ph_r = clamp01(abs(phv - 7.0) / 2.0)  # far from neutral => risk

        score = 100.0 * (0.38 * turb_r + 0.26 * do_r + 0.22 * temp_r + 0.14 * ph_r)
        return float(max(0.0, min(100.0, score)))

    latest["risk_score"] = latest.apply(risk_row, axis=1)

    def color_for(score: float) -> list[int]:
        # Water-themed risk ramp (light aqua -> deep blue)
        if score >= 70:
            return [11, 94, 215, 220]  # deep blue
        if score >= 40:
            return [2, 132, 199, 220]  # medium blue
        return [6, 182, 212, 220]  # aqua

    latest["color"] = latest["risk_score"].apply(color_for)

    # Build a route for the visible points.
    pts = list(zip(latest["_lat"].astype(float).tolist(), latest["_lon"].astype(float).tolist()))
    ort = ortools_route(pts) if use_ortools else None
    if ort is not None:
        order, total_km = ort
        route_method = "OR-Tools"
    else:
        order, total_km = nearest_neighbor_route(pts)
        route_method = "Nearest-neighbor"
    route_df = latest.iloc[order].copy().reset_index(drop=True)
    route_path = [
        [float(lon), float(lat)] for lat, lon in zip(route_df["_lat"].astype(float), route_df["_lon"].astype(float))
    ]

    st.caption(f"Route estimate ({route_method}): **{total_km:,.1f} km** across **{len(route_df)}** location(s).")

    import pydeck as pdk  # noqa: E402

    view = pdk.ViewState(
        latitude=float(route_df["_lat"].mean()),
        longitude=float(route_df["_lon"].mean()),
        zoom=8,
        pitch=0,
    )

    scatter = pdk.Layer(
        "ScatterplotLayer",
        data=route_df,
        get_position=["_lon", "_lat"],
        get_fill_color="color",
        get_radius=220,
        radius_min_pixels=6,
        radius_max_pixels=18,
        pickable=True,
    )

    path = pdk.Layer(
        "PathLayer",
        data=[{"path": route_path}],
        get_path="path",
        get_width=4,
        width_min_pixels=2,
        get_color=[11, 94, 215, 190],
    )

    tooltip = {
        "html": "<b>{_loc}</b><br/>Risk: {risk_score}<br/>pH: {_ph}<br/>Turbidity: {_turb}<br/>DO: {_do}<br/>Temp: {_temp}",
        "style": {"backgroundColor": "white", "color": "#101828"},
    }

    st.pydeck_chart(pdk.Deck(layers=[path, scatter], initial_view_state=view, tooltip=tooltip), use_container_width=True)

    with st.expander("Route order & risk table", expanded=False):
        show_cols = ["_loc", "_date", "_lat", "_lon", "_ph", "_turb", "_do", "_temp", "risk_score"]
        out = route_df[show_cols].rename(
            columns={
                "_loc": "MonitoringLocationIdentifier",
                "_date": "ActivityStartDate",
                "_lat": "Latitude",
                "_lon": "Longitude",
                "_ph": "pH (standard units)",
                "_turb": "Turbidity (NTU)",
                "_do": "Oxygen, dissolved (mg/L)",
                "_temp": "Temperature, water (deg C)",
                "risk_score": "Recent risk score (0-100)",
            }
        )
        st.dataframe(out, use_container_width=True, hide_index=True)

st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div class='panel'><div class='panel-title'>Data preview</div>", unsafe_allow_html=True)
preview_cols = ["_date", "_loc", "_ph", "_turb", "_do", "_temp"]
st.dataframe(
    f[preview_cols].rename(
        columns={
            "_date": "ActivityStartDate",
            "_loc": "MonitoringLocationIdentifier",
            "_ph": "pH (standard units)",
            "_turb": "Turbidity (NTU)",
            "_do": "Oxygen, dissolved (mg/L)",
            "_temp": "Temperature, water (deg C)",
        }
    ),
    use_container_width=True,
    hide_index=True,
)
st.markdown("</div>", unsafe_allow_html=True)

