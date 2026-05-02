import math
import pandas as pd
from typing import List, Dict, Tuple
from dataclasses import dataclass
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp


@dataclass
class Site:
    id: str
    lat: float
    lon: float


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance in miles between two points on the earth."""
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    r = 3956  # Radius of earth in miles
    return c * r


def find_nearest_site(current_lat: float, current_lon: float, sites: List[Site]) -> Tuple[Site, float]:
    """Find the nearest site from a list of sites given current coordinates."""
    if not sites:
        return None, float('inf')
    
    nearest = None
    min_dist = float('inf')
    
    for site in sites:
        if site.lat is None or site.lon is None:
            continue
        dist = haversine_distance(current_lat, current_lon, site.lat, site.lon)
        if dist < min_dist:
            min_dist = dist
            nearest = site
            
    return nearest, min_dist


def parse_sites_from_dataframe(df: pd.DataFrame) -> List[Site]:
    """
    Intelligently extracts sites from a DataFrame.
    Looks for standard coordinate and ID columns.
    """
    cols = [c.lower() for c in df.columns]
    
    # Heuristics for ID
    id_col = None
    for candidate in ['monitoringlocationidentifier', 'id', 'site_id', 'location_id', 'name', 'site']:
        for i, c in enumerate(cols):
            if candidate in c:
                id_col = df.columns[i]
                break
        if id_col:
            break
            
    # Heuristics for Latitude
    lat_col = None
    for candidate in ['activitylocation/latitudemeasure', 'lat', 'latitude']:
        for i, c in enumerate(cols):
            if candidate in c:
                lat_col = df.columns[i]
                break
        if lat_col:
            break

    # Heuristics for Longitude
    lon_col = None
    for candidate in ['activitylocation/longitudemeasure', 'lon', 'lng', 'longitude']:
        for i, c in enumerate(cols):
            if candidate in c:
                lon_col = df.columns[i]
                break
        if lon_col:
            break

    sites = []
    if not (id_col and lat_col and lon_col):
        # Return empty if columns couldn't be guessed
        return sites

    df = df.dropna(subset=[lat_col, lon_col])
    # Drop duplicates by ID
    df = df.drop_duplicates(subset=[id_col])

    for _, row in df.iterrows():
        try:
            site_id = str(row[id_col])
            lat = float(row[lat_col])
            lon = float(row[lon_col])
            sites.append(Site(id=site_id, lat=lat, lon=lon))
        except (ValueError, TypeError):
            continue

    return sites


def solve_tsp(sites: List[Site], start_lat: float, start_lon: float) -> List[Site]:
    """
    Solves the Traveling Salesperson Problem for the given sites starting from the given coordinates.
    Returns the ordered list of sites to visit.
    """
    if not sites:
        return []

    # Insert the start location as node 0
    all_nodes = [Site(id="Start", lat=start_lat, lon=start_lon)] + sites

    # Create distance matrix (using integers as required by OR-Tools, e.g., distance in feet or scaled miles)
    # Scale by 1000 to keep precision
    distance_matrix = []
    for i in range(len(all_nodes)):
        row = []
        for j in range(len(all_nodes)):
            if i == j:
                row.append(0)
            else:
                dist = haversine_distance(all_nodes[i].lat, all_nodes[i].lon, all_nodes[j].lat, all_nodes[j].lon)
                row.append(int(dist * 1000))
        distance_matrix.append(row)

    manager = pywrapcp.RoutingIndexManager(len(distance_matrix), 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC

    solution = routing.SolveWithParameters(search_parameters)

    if not solution:
        # Fallback to simple nearest neighbor if OR-tools fails
        return sites

    ordered_sites = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node_index = manager.IndexToNode(index)
        if node_index != 0: # skip the start node itself
            ordered_sites.append(all_nodes[node_index])
        index = solution.Value(routing.NextVar(index))

    return ordered_sites
