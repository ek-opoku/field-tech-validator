from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


RAW_TO_CLEAN_COLUMNS: dict[str, str] = {
    "ActivityStartDate": "activity_start_date",
    "MonitoringLocationIdentifier": "monitoring_location_id",
    "ActivityLocation/LatitudeMeasure": "latitude",
    "ActivityLocation/LongitudeMeasure": "longitude",
    "Nitrate, dissolved (mg/L as N)": "nitrate_mg_l_as_n",
    "Nitrite, dissolved (mg/L as N)": "nitrite_mg_l_as_n",
    "Orthophosphate, dissolved (mg/L as P)": "orthophosphate_mg_l_as_p",
    "Oxygen, dissolved (% saturation)": "dissolved_oxygen_percent_sat",
    "Oxygen, dissolved (mg/L)": "dissolved_oxygen_mg_l",
    "Temperature, water (deg C)": "water_temp_c",
    "Turbidity (NTU)": "turbidity_ntu",
    "pH (standard units)": "ph",
}


def _coerce_numeric(series: pd.Series) -> pd.Series:
    # Robust numeric conversion for messy CSVs (e.g., "", "ND", "NA", " <0.02").
    s = series.astype("string").str.strip()
    s = s.replace(
        {
            "": pd.NA,
            "NA": pd.NA,
            "N/A": pd.NA,
            "NULL": pd.NA,
            "null": pd.NA,
            "NaN": pd.NA,
            "nan": pd.NA,
            "ND": pd.NA,
            "nd": pd.NA,
            "None": pd.NA,
        }
    )
    # Drop common non-numeric adornments while keeping signs/decimals/exponents.
    s = s.str.replace(r"^[<>\s]+", "", regex=True)
    s = s.str.replace(r"[,\s]+", "", regex=True)
    return pd.to_numeric(s, errors="coerce")


def clean_water_data(df_raw: pd.DataFrame) -> pd.DataFrame:
    # Keep only expected columns if present; ignore extras.
    present = [c for c in RAW_TO_CLEAN_COLUMNS.keys() if c in df_raw.columns]
    missing = [c for c in RAW_TO_CLEAN_COLUMNS.keys() if c not in df_raw.columns]
    if missing:
        print(
            "Warning: missing expected columns:\n- " + "\n- ".join(missing),
            file=sys.stderr,
        )
    df = df_raw.loc[:, present].rename(columns=RAW_TO_CLEAN_COLUMNS).copy()

    if "monitoring_location_id" in df.columns:
        df["monitoring_location_id"] = df["monitoring_location_id"].astype("string").str.strip()

    if "activity_start_date" in df.columns:
        df["activity_start_date"] = pd.to_datetime(df["activity_start_date"], errors="coerce", utc=False)

    for col in [
        "latitude",
        "longitude",
        "nitrate_mg_l_as_n",
        "nitrite_mg_l_as_n",
        "orthophosphate_mg_l_as_p",
        "dissolved_oxygen_percent_sat",
        "dissolved_oxygen_mg_l",
        "water_temp_c",
        "turbidity_ntu",
        "ph",
    ]:
        if col in df.columns:
            df[col] = _coerce_numeric(df[col])

    # Basic validity filters for safety-check testing (keep rows that can be geolocated & dated).
    if "activity_start_date" in df.columns:
        df = df[df["activity_start_date"].notna()]
    if "monitoring_location_id" in df.columns:
        df = df[df["monitoring_location_id"].notna() & (df["monitoring_location_id"] != "")]

    if "latitude" in df.columns:
        df = df[df["latitude"].between(-90, 90, inclusive="both") | df["latitude"].isna()]
    if "longitude" in df.columns:
        df = df[df["longitude"].between(-180, 180, inclusive="both") | df["longitude"].isna()]

    # Replace physically impossible values with NaN (don’t drop the row).
    if "ph" in df.columns:
        df.loc[~df["ph"].between(0, 14, inclusive="both"), "ph"] = pd.NA
    for non_negative in [
        "nitrate_mg_l_as_n",
        "nitrite_mg_l_as_n",
        "orthophosphate_mg_l_as_p",
        "dissolved_oxygen_mg_l",
        "turbidity_ntu",
    ]:
        if non_negative in df.columns:
            df.loc[df[non_negative] < 0, non_negative] = pd.NA
    if "dissolved_oxygen_percent_sat" in df.columns:
        df.loc[
            ~df["dissolved_oxygen_percent_sat"].between(0, 300, inclusive="both"),
            "dissolved_oxygen_percent_sat",
        ] = pd.NA
    if "water_temp_c" in df.columns:
        df.loc[~df["water_temp_c"].between(-20, 60, inclusive="both"), "water_temp_c"] = pd.NA

    # Helpful time features for downstream tests/models (derived from date only).
    if "activity_start_date" in df.columns:
        df["date"] = df["activity_start_date"].dt.date.astype("string")
        df["year"] = df["activity_start_date"].dt.year
        df["month"] = df["activity_start_date"].dt.month
        df["dayofyear"] = df["activity_start_date"].dt.dayofyear

    # Stable ordering for diffs/reproducibility
    sort_cols = [c for c in ["monitoring_location_id", "activity_start_date"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=True, kind="mergesort")

    df = df.reset_index(drop=True)
    return df


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clean groundwater sampling data and export processed_water_data.csv (raw input is never modified)."
    )
    parser.add_argument("--input", default="data_wide.csv", help="Path to raw CSV (default: data_wide.csv)")
    parser.add_argument(
        "--output",
        default="processed_water_data.csv",
        help="Path to write cleaned CSV (default: processed_water_data.csv)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        return 2

    df_raw = pd.read_csv(input_path, dtype="string", keep_default_na=False)
    df_clean = clean_water_data(df_raw)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_csv(output_path, index=False)

    print(f"Read rows: {len(df_raw):,}")
    print(f"Wrote rows: {len(df_clean):,}")
    print(f"Output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

