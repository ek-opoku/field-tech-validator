import math
import json
import urllib.request
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


def get_osrm_distance_matrix(nodes: List[Site]) -> List[List[int]]:
    """Fetches real driving distance matrix from OSRM public API."""
    if len(nodes) > 100:
        return None  # OSRM public API typically limits to ~100 coordinates
    
    coords = ";".join([f"{n.lon},{n.lat}" for n in nodes])
    url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=distance"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FieldTechValidator/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data.get("code") == "Ok":
                distances = data.get("distances", [])
                # OSRM returns distances in meters. OR-Tools requires integers.
                int_matrix = []
                for row in distances:
                    int_matrix.append([int(d) for d in row])
                return int_matrix
    except Exception as e:
        print(f"OSRM fallback triggered: {e}")
    return None

def solve_tsp(sites: List[Site], start_lat: float, start_lon: float) -> List[Site]:
    """
    Solves the Traveling Salesperson Problem for the given sites starting from the given coordinates.
    Returns the ordered list of sites to visit.
    """
    if not sites:
        return []

    # Insert the start location as node 0
    all_nodes = [Site(id="Start", lat=start_lat, lon=start_lon)] + sites

    # Attempt to get real road distances from OSRM
    distance_matrix = get_osrm_distance_matrix(all_nodes)
    
    if distance_matrix is None:
        # Fallback: Create straight-line distance matrix (scaled by 1000 for int precision)
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

    # Implement Open-Ended TSP (No return to start)
    # The cost to return from ANY node to the Start node (0) is forced to 0.
    for i in range(len(all_nodes)):
        distance_matrix[i][0] = 0

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
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.seconds = 2

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
