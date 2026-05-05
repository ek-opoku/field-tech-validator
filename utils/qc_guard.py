import csv
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import gzip

# =====================================================================
# LEVEL 1: Sanity Limits (Hard Bounds)
# =====================================================================
SANITY_LIMITS = {
    "ph": {"min": 6.0, "max": 9.5, "name": "pH (standard units)"},
    "temperature_c": {"min": 2.0, "max": 32.0, "name": "Temperature, water (deg C)"},
    "turbidity_ntu": {"min": 0.0, "max": 500.0, "name": "Turbidity (NTU)"},
    "dissolved_oxygen_mg_l": {"min": 0.0, "max": 20.0, "name": "Oxygen, dissolved (mg/L)"},
    "dissolved_oxygen_sat": {"min": 0.0, "max": 230.0, "name": "Oxygen, dissolved (% saturation)"},
    "nitrate": {"min": 0.0, "max": 45.0, "name": "Nitrate, dissolved (mg/L as N)"},
    "nitrite": {"min": 0.0, "max": 1.0, "name": "Nitrite, dissolved (mg/L as N)"},
    "orthophosphate": {"min": 0.0, "max": 1.5, "name": "Orthophosphate, dissolved (mg/L as P)"},
    "conductivity": {"min": 0.0, "max": 1500.0, "name": "Conductivity (uS/cm)"},
    "depth_to_water": {"min": 0.0001, "max": 100.0, "name": "Depth to water table (m)"},
}

def check_sanity_limits(params_map: Dict[str, Optional[float]]) -> List[str]:
    """Returns a list of hard stop error messages if any value violates sanity bounds."""
    errors = []
    for key, val in params_map.items():
        if val is None:
            continue
        limits = SANITY_LIMITS.get(key)
        if not limits:
            continue
        if val < limits["min"] or val > limits["max"]:
            errors.append(f"{limits['name']} ({val}) exceeds physical sanity bounds ({limits['min']} - {limits['max']})!")
    return errors

# =====================================================================
# LEVEL 2: Historical Well Limits (Contextual Bounds)
# =====================================================================
def load_historical_bounds(schema_csv_path: Path) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    Returns nested dict: { location_id: { param_key: { "min": x, "max": y, "avg": z } } }
    param_key matches the keys in params_map (e.g. 'ph', 'temperature_c')
    """
    if not schema_csv_path.exists():
        return {}
        
    # Map raw headers to our internal param keys
    header_map = {
        "pH (standard units)": "ph",
        "Temperature, water (deg C)": "temperature_c",
        "Turbidity (NTU)": "turbidity_ntu",
        "Oxygen, dissolved (mg/L)": "dissolved_oxygen_mg_l",
        "Oxygen, dissolved (% saturation)": "dissolved_oxygen_sat",
        "Nitrate, dissolved (mg/L as N)": "nitrate",
        "Nitrite, dissolved (mg/L as N)": "nitrite",
        "Orthophosphate, dissolved (mg/L as P)": "orthophosphate",
        "Conductivity (uS/cm)": "conductivity",
        "Depth to water table (m)": "depth_to_water"
    }
    
    well_data: Dict[str, Dict[str, List[float]]] = {}
    
    if schema_csv_path.suffix.lower() == '.gz':
        f = gzip.open(schema_csv_path, "rt", encoding="utf-8", newline="")
    else:
        f = schema_csv_path.open("r", newline="", encoding="utf-8")
        
    with f:
        reader = csv.DictReader(f)
        if not reader.fieldnames: 
            return {}
            
        for row in reader:
            loc_id = row.get("SiteID", "").strip()
            if not loc_id: continue
            
            if loc_id not in well_data:
                well_data[loc_id] = {k: [] for k in header_map.values()}
                
            for raw_h, key in header_map.items():
                val_str = str(row.get(raw_h, "")).strip()
                try:
                    val = float(val_str)
                    well_data[loc_id][key].append(val)
                except Exception:
                    pass
                    
    # Compute bounds
    bounds = {}
    for loc_id, params in well_data.items():
        bounds[loc_id] = {}
        for key, vals in params.items():
            if vals:
                bounds[loc_id][key] = {
                    "min": min(vals),
                    "max": max(vals),
                    "avg": sum(vals) / len(vals)
                }
    return bounds

def evaluate_historical_bounds(val: float, key: str, loc_id: str, historical_data: Dict[str, Dict[str, Dict[str, float]]]) -> Tuple[str, str]:
    """
    Returns (status, message). 
    Status is one of: "Safe", "Warning", "Danger", "None"
    """
    if loc_id not in historical_data or key not in historical_data[loc_id]:
        return "None", ""
        
    bounds = historical_data[loc_id][key]
    b_min, b_max, b_avg = bounds["min"], bounds["max"], bounds["avg"]
    
    # If there's no variance in historical data (min == max), add a small buffer for checks
    range_span = b_max - b_min
    if range_span == 0:
        safe_min = b_min * 0.9
        safe_max = b_max * 1.1
    else:
        safe_min = b_min
        safe_max = b_max
        
    # Check bounds
    if val < safe_min * 0.7 or val > safe_max * 1.3:
        return "Danger", f"Critical: {val} is >30% outside historical bounds ({b_min:.2f} - {b_max:.2f})"
    elif val < safe_min or val > safe_max:
        return "Warning", f"Unusual: {val} is outside historical bounds ({b_min:.2f} - {b_max:.2f})"
    else:
        return "Safe", f"Within normal range (avg {b_avg:.2f})"

# =====================================================================
# LEVEL 3: Compliance Standards (Regulatory Bounds)
# =====================================================================
COMPLIANCE_STANDARDS = {
    "None": {},
    "USGS/EPA Groundwater Standards": {
        "ph": {"min": 6.5, "max": 8.5, "rule": "EPA Secondary (6.5 - 8.5)"},
        "nitrate": {"max": 10.0, "rule": "EPA MCL (10.0 mg/L as N)"},
        "nitrite": {"max": 1.0, "rule": "EPA MCL (1.0 mg/L as N)"},
        "orthophosphate": {"max": 0.10, "rule": "USGS High Concern (>0.1 mg/L)"},
        "dissolved_oxygen_mg_l": {"min": 1.0, "rule": "USGS Hypoxia Limit (<1.0 mg/L)"},
        "dissolved_oxygen_sat": {"min": 80.0, "max": 120.0, "rule": "USGS Healthy Saturation (80-120%)"},
        "turbidity_ntu": {"max": 5.0, "rule": "Clear Water Target (<5 NTU)"},
    },
    "Drinking Water (EPA)": {
        "ph": {"min": 6.5, "max": 8.5, "rule": "EPA Secondary"},
        "nitrate": {"max": 10.0, "rule": "EPA MCL 10 mg/L as N"},
        "turbidity_ntu": {"max": 1.0, "rule": "EPA MCL 1 NTU"},
    },
    "Agricultural (FAO)": {
        "nitrate": {"max": 30.0, "rule": "FAO Irrigation"},
        "orthophosphate": {"max": 2.0, "rule": "FAO Livestock"},
    },
    "Industrial": {
        "temperature_c": {"max": 40.0, "rule": "Process Water Cap"},
        "conductivity": {"max": 1000.0, "rule": "Process Water Cap"},
    }
}

def check_compliance(val: float, key: str, standard: str) -> Tuple[str, str]:
    """Returns (status, message) where status is 'Pass', 'Flag', or 'None'"""
    if standard not in COMPLIANCE_STANDARDS or key not in COMPLIANCE_STANDARDS[standard]:
        return "None", "No standard"
        
    rules = COMPLIANCE_STANDARDS[standard][key]
    r_min = rules.get("min", float('-inf'))
    r_max = rules.get("max", float('inf'))
    r_name = rules.get("rule", "Standard")
    
    if val < r_min or val > r_max:
        if r_min != float('-inf') and r_max != float('inf'):
            return "Flag", f"Outside {r_min}-{r_max} ({r_name})"
        elif r_max != float('inf'):
            return "Flag", f"Outside ≤ {r_max} ({r_name})"
        else:
            return "Flag", f"Outside ≥ {r_min} ({r_name})"
    else:
        if r_min != float('-inf') and r_max != float('inf'):
            return "Pass", f"Within {r_min}-{r_max} ({r_name})"
        elif r_max != float('inf'):
            return "Pass", f"Within ≤ {r_max} ({r_name})"
        else:
            return "Pass", f"Within ≥ {r_min} ({r_name})"
