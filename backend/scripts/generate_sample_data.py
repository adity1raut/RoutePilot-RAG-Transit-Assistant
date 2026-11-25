"""Generate the sample transport dataset used by RoutePilot.

Creates, under backend/data/raw/:
  * routes.csv         - structured timetable data (route, stops, timings, fare, day type)
  * fare_chart.csv     - stage-based fare chart used for stop-to-stop fares
  * stops.csv          - stop locations (latitude/longitude), area and landmark for the network map
  * route_shapes.json  - the road path between consecutive stops of every route, for the map
  * docs/*.pdf         - transport documents (fare policy, passenger guide, notices)

The stop positions are real places in Nanded (taken from OpenStreetMap), and the road paths, route
lengths and running times come from routing each route over the OpenStreetMap road network with OSRM.
The routes, timetables, fares and documents are SYNTHETIC demo data for the academic project: Nanded
has no official city bus timetable to copy. Replace the files in data/raw/ with real data from your
transport operator and re-run the ingestion.

Usage:  python scripts/generate_sample_data.py            (fetches road paths from OSRM when needed)
        python scripts/generate_sample_data.py --offline  (reuses route_shapes.json, never goes online)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
import urllib.request
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
DOCS_DIR = RAW_DIR / "docs"
SHAPES_FILE = RAW_DIR / "route_shapes.json"

OPERATOR = "RoutePilot Demo Transit"
DISCLAIMER = "SAMPLE DATA - created for an academic demonstration, not an official timetable."

DAY_TYPES = ["Weekday", "Saturday", "Sunday/Holiday"]

# Fare chart: number of stops travelled -> fare (Rs.) per bus type.
FARE_CHART = [
    # min_stops, max_stops, ordinary, ac, night
    (1, 2, 10, 15, 15),
    (3, 4, 15, 25, 20),
    (5, 6, 20, 30, 25),
    (7, 8, 25, 40, 30),
    (9, 11, 30, 45, 35),
    (12, 14, 35, 50, 40),
    (15, 20, 40, 60, 45),
]

# Running-time model: average speed between stops (traffic, signals) plus a fixed halt at every stop.
BUS_SPEED_KMH = {"Ordinary": 18, "AC": 22, "Night": 26}
DWELL_MIN = 0.5
DOWN_SHIFT_MIN = 15  # Down trips leave this many minutes after the matching Up trip

# Stop positions: (latitude, longitude, area, landmark, source).
# "OpenStreetMap": placed on a named OpenStreetMap feature at that place (a road, junction, landmark or
# a cluster of mapped buildings whose address names the locality). "approximate": OpenStreetMap has
# nothing named there, so the stop was placed by hand on the right road; good for a city-scale map only.
STOPS = {
    # Central Nanded: station, bus stand, Vazirabad and the Shivaji Nagar - ITI spine
    "Railway Station": (19.1593, 77.3099, "Central Nanded", "Hazur Sahib Nanded railway station", "OpenStreetMap"),
    "Central Bus Stand": (19.1595, 77.3067, "Central Nanded", "MSRTC Nanded bus stand, Mill Gate Road", "OpenStreetMap"),
    "Kalamandir": (19.1575, 77.3076, "Central Nanded", "Kalamandir chowk at the head of Doctor Lane", "OpenStreetMap"),
    "Vazirabad": (19.1547, 77.3097, "Central Nanded",
                  "Vazirabad chowk by the SP office, near the Shivaji Maharaj statue (Shivaji Putla)", "OpenStreetMap"),
    "Government Hospital": (19.1552, 77.3114, "Central Nanded",
                            "Shri Guru Gobind Singh Ji Memorial Government Hospital, Station Road", "OpenStreetMap"),
    "Govardhan Ghat": (19.1490, 77.3085, "Central Nanded", "Govardhan Ghat bridge road over the Godavari",
                       "OpenStreetMap"),
    "Shivaji Nagar": (19.1625, 77.3056, "Central Nanded", "Shivaji Nagar main road (Guru Gobind Singh Ji Road)",
                      "OpenStreetMap"),
    "Lalbadi": (19.1633, 77.3020, "Central Nanded", "Lalbadi, Mahavir Society", "OpenStreetMap"),
    "ITI Corner": (19.1689, 77.3055, "Central Nanded", "ITI Corner and Mahatma Phule Market, start of VIP Road",
                   "OpenStreetMap"),
    "Yeshwant College": (19.1689, 77.3083, "Central Nanded", "Yeshwant Mahavidyalaya on VIP Road", "OpenStreetMap"),
    "Vivek Nagar": (19.1727, 77.3046, "Central Nanded", "Vivek Nagar corner on Vazirabad Road", "OpenStreetMap"),
    "Shrinagar": (19.1770, 77.3044, "Central Nanded", "Shrinagar market on Vazirabad Road", "OpenStreetMap"),
    # Old City around Takht Sachkhand Sri Hazur Sahib
    "Chikhalwadi Corner": (19.1529, 77.3144, "Old City", "Chikhalwadi Corner on the Gurudwara road", "OpenStreetMap"),
    "Gurudwara Gate": (19.1518, 77.3164, "Old City", "Gate No. 2 of Takht Sachkhand Sri Hazur Sahib", "OpenStreetMap"),
    "Juna Mondha": (19.1497, 77.3206, "Old City", "Old grain market near the Clock Tower", "approximate"),
    "Nagina Ghat": (19.1470, 77.3190, "Old City", "Gurudwara Nagina Ghat on the Godavari bank", "approximate"),
    "Itwara Market": (19.1485, 77.3244, "Old City", "Itwara bazaar near the banana market", "OpenStreetMap"),
    "Degloor Naka": (19.1518, 77.3316, "Old City", "Madina Chowk on the Degloor road, near Hyder Bagh",
                     "OpenStreetMap"),
    # East Nanded: Hingoli Gate, Bhagya Nagar Road, Hingoli Naka and the airport
    "Hingoli Gate": (19.1624, 77.3167, "East Nanded", "Hingoli Gate flyover and subway", "OpenStreetMap"),
    "Samrat Nagar": (19.1623, 77.3195, "East Nanded", "Annabhau Sathe Chowk, Samrat Nagar", "OpenStreetMap"),
    "Nava Mondha": (19.1646, 77.3178, "East Nanded", "Nava Mondha market, opposite the MSEB office", "approximate"),
    "Maltekdi": (19.1661, 77.3298, "East Nanded", "Gurudwara Maltekdi Sahib, near Maltekdi railway station",
                 "OpenStreetMap"),
    "Vasant Nagar": (19.1715, 77.3177, "East Nanded", "Vasant Nagar main road", "OpenStreetMap"),
    "Hingoli Naka": (19.1713, 77.3219, "East Nanded", "Maharana Pratap Chowk on the Hingoli road", "OpenStreetMap"),
    "Anand Nagar": (19.1730, 77.3155, "East Nanded", "Anand Nagar chowk on Bhagya Nagar Road", "OpenStreetMap"),
    "Vidyut Nagar": (19.1742, 77.3138, "East Nanded", "Vidyut Nagar, near Raj Mall", "OpenStreetMap"),
    "Bhagya Nagar": (19.1769, 77.3096, "East Nanded", "Bhagya Nagar kaman (arch)", "OpenStreetMap"),
    "MGM College": (19.1790, 77.3270, "East Nanded", "MGM's College of Engineering", "OpenStreetMap"),
    "Airport": (19.1792, 77.3224, "East Nanded", "Shri Guru Gobind Singh Ji Airport, terminal approach road",
                "OpenStreetMap"),
    # North Nanded: Workshop Corner, Taroda and Malegaon Road
    "Workshop Corner": (19.1804, 77.3043, "North Nanded", "Junction of Vazirabad Road and Bhagya Nagar Road",
                        "OpenStreetMap"),
    "Jangamwadi": (19.1812, 77.3028, "North Nanded", "Jangamwadi municipal hospital on Malegaon Road", "OpenStreetMap"),
    "Raj Corner": (19.1839, 77.3050, "North Nanded", "Raj Corner, opposite Shri Shivaji High School", "OpenStreetMap"),
    "Taroda Naka": (19.1846, 77.2999, "North Nanded", "Taroda Naka, where Purna Road meets Malegaon Road",
                    "OpenStreetMap"),
    "Malegaon Road": (19.1923, 77.2972, "North Nanded", "Malegaon Road at Sarpanch Nagar", "OpenStreetMap"),
    "Chaitanya Nagar": (19.1850, 77.3102, "North Nanded", "Chaitanya Nagar road near the Sai Baba temple",
                        "OpenStreetMap"),
    "Balaji Nagar": (19.1915, 77.3090, "North Nanded", "Balaji Nagar on the Taroda back road", "OpenStreetMap"),
    "Sangvi": (19.1841, 77.3168, "North Nanded", "Sangvi Road (NH61) near Kendriya Vidyalaya", "OpenStreetMap"),
    # West Nanded
    "Ganesh Nagar": (19.1684, 77.2983, "West Nanded", "Ganesh Nagar road", "OpenStreetMap"),
    "Yeshwant Nagar": (19.1726, 77.2960, "West Nanded", "Yeshwant Nagar, near Nanded Agricultural College",
                       "OpenStreetMap"),
    "Pharande Nagar": (19.1796, 77.2881, "West Nanded", "Pharande Nagar on Pawadewadi Road", "OpenStreetMap"),
    "Wadi Bk": (19.1842, 77.2708, "West Nanded", "Wadi Budruk village", "OpenStreetMap"),
    "Chhatrapati Chowk": (19.1858, 77.2920, "West Nanded", "Chhatrapati Chowk on Purna Road", "OpenStreetMap"),
    # New Nanded, across the Godavari
    "Kautha": (19.1417, 77.3069, "New Nanded", "Kautha chowk, south of the Govardhan Ghat bridge", "OpenStreetMap"),
    "Navi Kautha": (19.1352, 77.3036, "New Nanded", "MHADA Colony, Navi Kautha", "OpenStreetMap"),
    "Wasarni": (19.1330, 77.3220, "New Nanded", "Wasarni, Kautha", "OpenStreetMap"),
    "Latur Phata": (19.1300, 77.3270, "New Nanded", "Junction of the Latur highway (NH361) and the CIDCO road",
                    "approximate"),
    "HUDCO": (19.1200, 77.3270, "New Nanded", "HUDCO colony, New Nanded", "approximate"),
    "CIDCO": (19.1108, 77.3254, "New Nanded", "CIDCO colony, New Nanded (Waghala)", "OpenStreetMap"),
    # Vishnupuri education and medical hub
    "SGGS Institute": (19.1126, 77.2923, "Vishnupuri", "SGGS Institute of Engineering and Technology main gate",
                       "OpenStreetMap"),
    "Medical College Vishnupuri": (19.1114, 77.2904, "Vishnupuri",
                                   "Dr. Shankarrao Chavan Government Medical College and Hospital", "OpenStreetMap"),
    "Vishnupuri": (19.1093, 77.2872, "Vishnupuri", "Vishnupuri village, near the rural hospital", "OpenStreetMap"),
    "SRTM University": (19.1043, 77.2819, "Vishnupuri", "Swami Ramanand Teerth Marathwada University main gate",
                        "approximate"),
    # Outskirts
    "Wajegaon": (19.1428, 77.3491, "Outskirts", "Wajegaon village on the Degloor road", "approximate"),
    "Tuppa": (19.1026, 77.3524, "Outskirts", "Tuppa road, off the Nanded - Narsi highway", "OpenStreetMap"),
}

# Every route is listed in its Up direction; the Down direction runs the same stops in reverse.
ROUTES = [
    {
        "route_no": "1",
        "route_name": "Railway Station - Vishnupuri (via Kautha)",
        "stops": ["Railway Station", "Central Bus Stand", "Kalamandir", "Vazirabad", "Govardhan Ghat",
                  "Kautha", "Navi Kautha", "SGGS Institute", "Medical College Vishnupuri", "Vishnupuri"],
        "bus_type": "Ordinary", "first": "06:00", "last": "22:00",
        "frequency": {"Weekday": 20, "Saturday": 30, "Sunday/Holiday": 40},
    },
    {
        "route_no": "2",
        "route_name": "Central Bus Stand - CIDCO (via Gurudwara)",
        "stops": ["Central Bus Stand", "Kalamandir", "Vazirabad", "Chikhalwadi Corner",
                  "Gurudwara Gate", "Juna Mondha", "Nagina Ghat", "Wasarni", "Latur Phata", "HUDCO", "CIDCO"],
        "bus_type": "Ordinary", "first": "05:45", "last": "22:15",
        "frequency": {"Weekday": 15, "Saturday": 20, "Sunday/Holiday": 30},
    },
    {
        "route_no": "3",
        "route_name": "Airport Express (AC)",
        "stops": ["Central Bus Stand", "Railway Station", "Hingoli Gate", "Hingoli Naka", "MGM College", "Airport"],
        "bus_type": "AC", "first": "05:30", "last": "21:30",
        "frequency": {"Weekday": 60, "Saturday": 60, "Sunday/Holiday": 90},
    },
    {
        "route_no": "4",
        "route_name": "Taroda Naka - SRTM University (Main Line)",
        "stops": ["Taroda Naka", "Raj Corner", "Workshop Corner", "Shrinagar", "Vivek Nagar", "ITI Corner",
                  "Shivaji Nagar", "Central Bus Stand", "Kalamandir", "Vazirabad", "Govardhan Ghat",
                  "Kautha", "Navi Kautha", "SGGS Institute", "Medical College Vishnupuri", "Vishnupuri",
                  "SRTM University"],
        "bus_type": "Ordinary", "first": "05:45", "last": "22:00",
        "frequency": {"Weekday": 15, "Saturday": 20, "Sunday/Holiday": 30},
    },
    {
        "route_no": "5",
        "route_name": "CIDCO - Vishnupuri (via Latur Phata)",
        "stops": ["CIDCO", "HUDCO", "Latur Phata", "SGGS Institute", "Medical College Vishnupuri", "Vishnupuri"],
        "bus_type": "Ordinary", "first": "06:15", "last": "21:15",
        "frequency": {"Weekday": 30, "Saturday": 45, "Sunday/Holiday": 60},
    },
    {
        "route_no": "6",
        "route_name": "Old City Circle (Railway Station - Hingoli Gate)",
        "stops": ["Railway Station", "Government Hospital", "Gurudwara Gate", "Juna Mondha", "Itwara Market",
                  "Degloor Naka", "Maltekdi", "Samrat Nagar", "Hingoli Gate"],
        "bus_type": "Ordinary", "first": "06:00", "last": "21:30",
        "frequency": {"Weekday": 25, "Saturday": 25, "Sunday/Holiday": 35},
    },
    {
        "route_no": "7N",
        "route_name": "Night Service Railway Station - CIDCO",
        "stops": ["Railway Station", "Central Bus Stand", "Vazirabad", "Govardhan Ghat", "Kautha",
                  "Latur Phata", "HUDCO", "CIDCO"],
        "bus_type": "Night", "first": "22:30", "last": "01:30",
        "frequency": {"Weekday": 60, "Saturday": 60, "Sunday/Holiday": 60},
    },
    {
        "route_no": "8",
        "route_name": "Railway Station - Malegaon Road (via Bhagya Nagar)",
        "stops": ["Railway Station", "Hingoli Gate", "Nava Mondha", "Vasant Nagar", "Anand Nagar", "Vidyut Nagar",
                  "Bhagya Nagar", "Workshop Corner", "Raj Corner", "Taroda Naka", "Malegaon Road"],
        "bus_type": "Ordinary", "first": "06:00", "last": "21:30",
        "frequency": {"Weekday": 20, "Saturday": 30, "Sunday/Holiday": 40},
    },
    {
        "route_no": "9",
        "route_name": "Central Bus Stand - Balaji Nagar (via Shivaji Nagar)",
        "stops": ["Central Bus Stand", "Shivaji Nagar", "ITI Corner", "Vivek Nagar", "Shrinagar", "Workshop Corner",
                  "Raj Corner", "Chaitanya Nagar", "Balaji Nagar"],
        "bus_type": "Ordinary", "first": "06:15", "last": "21:45",
        "frequency": {"Weekday": 20, "Saturday": 30, "Sunday/Holiday": 40},
    },
    {
        "route_no": "9N",
        "route_name": "Night Service Railway Station - Taroda Naka",
        "stops": ["Railway Station", "Central Bus Stand", "Shivaji Nagar", "ITI Corner", "Shrinagar",
                  "Workshop Corner", "Raj Corner", "Taroda Naka"],
        "bus_type": "Night", "first": "22:45", "last": "00:45",
        "frequency": {"Weekday": 60, "Saturday": 60, "Sunday/Holiday": 60},
    },
    {
        "route_no": "10",
        "route_name": "Gurudwara Gate - Airport (via Samrat Nagar)",
        "stops": ["Gurudwara Gate", "Hingoli Gate", "Samrat Nagar", "Hingoli Naka", "MGM College", "Airport"],
        "bus_type": "Ordinary", "first": "06:30", "last": "21:00",
        "frequency": {"Weekday": 30, "Saturday": 30, "Sunday/Holiday": 45},
    },
    {
        "route_no": "11",
        "route_name": "Wadi Bk - Vazirabad (via Ganesh Nagar)",
        "stops": ["Wadi Bk", "Pharande Nagar", "Yeshwant Nagar", "Ganesh Nagar", "Lalbadi", "Shivaji Nagar",
                  "Central Bus Stand", "Kalamandir", "Vazirabad"],
        "bus_type": "Ordinary", "first": "06:00", "last": "21:00",
        "frequency": {"Weekday": 30, "Saturday": 40, "Sunday/Holiday": 60},
    },
    {
        "route_no": "12",
        "route_name": "Central Bus Stand - Wajegaon (via Degloor Naka)",
        "stops": ["Central Bus Stand", "Kalamandir", "Vazirabad", "Chikhalwadi Corner",
                  "Gurudwara Gate", "Itwara Market", "Degloor Naka", "Wajegaon"],
        "bus_type": "Ordinary", "first": "06:00", "last": "21:30",
        "frequency": {"Weekday": 30, "Saturday": 30, "Sunday/Holiday": 45},
    },
    {
        "route_no": "13",
        "route_name": "University Express (AC)",
        "stops": ["Railway Station", "Vazirabad", "Kautha", "SGGS Institute", "Vishnupuri", "SRTM University"],
        "bus_type": "AC", "first": "06:00", "last": "21:00",
        "frequency": {"Weekday": 45, "Saturday": 45, "Sunday/Holiday": 60},
    },
    {
        "route_no": "14",
        "route_name": "ITI Corner - Malegaon Road (via Jangamwadi)",
        "stops": ["ITI Corner", "Vivek Nagar", "Shrinagar", "Jangamwadi", "Taroda Naka", "Malegaon Road"],
        "bus_type": "Ordinary", "first": "06:30", "last": "21:00",
        "frequency": {"Weekday": 30, "Saturday": 40, "Sunday/Holiday": 60},
    },
    {
        "route_no": "15",
        "route_name": "Sangvi - Wadi Bk (via Purna Road)",
        "stops": ["Sangvi", "Chaitanya Nagar", "Raj Corner", "Taroda Naka", "Chhatrapati Chowk", "Pharande Nagar",
                  "Wadi Bk"],
        "bus_type": "Ordinary", "first": "06:30", "last": "20:30",
        "frequency": {"Weekday": 40, "Saturday": 40, "Sunday/Holiday": 60},
    },
    {
        "route_no": "16",
        "route_name": "Kautha - Tuppa (via CIDCO)",
        "stops": ["Kautha", "Wasarni", "Latur Phata", "HUDCO", "CIDCO", "Tuppa"],
        "bus_type": "Ordinary", "first": "06:30", "last": "20:30",
        "frequency": {"Weekday": 40, "Saturday": 60, "Sunday/Holiday": 60},
    },
    {
        "route_no": "17",
        "route_name": "Central Bus Stand - Hingoli Naka (College Line)",
        "stops": ["Central Bus Stand", "Shivaji Nagar", "ITI Corner", "Yeshwant College", "Vidyut Nagar",
                  "Anand Nagar", "Vasant Nagar", "Hingoli Naka"],
        "bus_type": "Ordinary", "first": "06:30", "last": "21:30",
        "frequency": {"Weekday": 20, "Saturday": 30, "Sunday/Holiday": 45},
    },
]


def to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def to_hhmm(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def departures(first: str, last: str, every: int) -> list[str]:
    start, end = to_minutes(first), to_minutes(last)
    if end < start:  # service runs past midnight
        end += 24 * 60
    return [to_hhmm(t) for t in range(start, end + 1, every)]


def fare_for(stops_travelled: int, bus_type: str) -> int:
    column = {"Ordinary": 2, "AC": 3, "Night": 4}[bus_type]
    for row in FARE_CHART:
        if row[0] <= stops_travelled <= row[1]:
            return row[column]
    return FARE_CHART[-1][column]


# --------------------------------------------------------------------------- road paths

OSRM_URL = "https://router.project-osrm.org/route/v1/driving/"
SHAPES_ATTRIBUTION = "Road paths: OSRM routing over OpenStreetMap data (c) OpenStreetMap contributors, ODbL"


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def simplify(points: list[list[float]], tolerance: float = 0.00005) -> list[list[float]]:
    """Douglas-Peucker line simplification (tolerance in degrees, about 5 m) to keep the map data small."""
    if len(points) < 3:
        return points
    (y1, x1), (y2, x2) = points[0], points[-1]
    length = math.hypot(x2 - x1, y2 - y1) or 1e-12
    distances = [abs((x2 - x1) * (y1 - y) - (x1 - x) * (y2 - y1)) / length for y, x in points[1:-1]]
    i = max(range(len(distances)), key=distances.__getitem__)
    if distances[i] <= tolerance:
        return [points[0], points[-1]]
    return simplify(points[:i + 2], tolerance)[:-1] + simplify(points[i + 1:], tolerance)


def bearing(a: tuple[float, float], b: tuple[float, float]) -> int:
    """Compass bearing (degrees) from a to b."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return round(math.degrees(math.atan2(y, x))) % 360


# How strictly a stop is snapped to a road running in the bus's direction of travel (allowed deviation in degrees);
# None snaps it to the nearest road whatever its direction.
SNAP_CHOICES = (90, 45, 20, None)


def _osrm(stops: list[str], tolerances: list[int | None], steps: bool = False) -> dict | None:
    points = [STOPS[s][:2] for s in stops]
    headings = [bearing(points[max(i - 1, 0)], points[min(i + 1, len(points) - 1)]) for i in range(len(points))]
    coords = ";".join(f"{lon},{lat}" for lat, lon in points)
    bearings = ";".join("" if t is None else f"{h},{t}" for h, t in zip(headings, tolerances))
    url = f"{OSRM_URL}{coords}?overview=false&bearings={bearings}" + ("&steps=true&geometries=geojson" if steps else "")
    request = urllib.request.Request(url, headers={"User-Agent": "RoutePilot-academic-project/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    time.sleep(1)  # the public OSRM server allows about one request per second
    return body if body.get("code") == "Ok" else None


def _detour_stops(stops: list[str], body: dict) -> list[int]:
    """Stops at either end of a leg that is much longer by road than in a straight line."""
    found: set[int] = set()
    for i, leg in enumerate(body["routes"][0]["legs"]):
        if leg["distance"] / 1000 > 1.3 * haversine_km(STOPS[stops[i]][:2], STOPS[stops[i + 1]][:2]) + 0.15:
            found |= {i, i + 1}
    return sorted(found)


def fetch_route_shape(stops: list[str]) -> dict:
    """Route the stops in order over the road network: one road path and length per pair of consecutive stops.

    Every stop is snapped to the side of the road the bus travels on; otherwise a stop on a dual carriageway can land on
    the opposite carriageway, and the route drives past it and U-turns back. Where a leg is still much longer than the
    straight line, the other snapping choices are tried for the stops at its ends and the shortest route is kept.
    """
    tolerances: list[int | None] = [SNAP_CHOICES[0]] * len(stops)
    body = _osrm(stops, tolerances)
    if body is None:  # no road in the travel direction near some stop: snap every stop to the nearest road
        tolerances = [None] * len(stops)
        body = _osrm(stops, tolerances)
    if body is None:
        raise RuntimeError(f"OSRM could not route {' - '.join(stops)}")
    for _ in range(2):
        improved = False
        for i in _detour_stops(stops, body):
            for choice in SNAP_CHOICES:
                trial = tolerances[:i] + [choice] + tolerances[i + 1:]
                candidate = _osrm(stops, trial) if choice != tolerances[i] else None
                if candidate and candidate["routes"][0]["distance"] < body["routes"][0]["distance"] - 20:
                    body, tolerances, improved = candidate, trial, True
        if not improved:
            break
    body = _osrm(stops, tolerances, steps=True)
    for stop, waypoint in zip(stops, body["waypoints"]):
        if waypoint["distance"] > 150:
            print(f"  warning: {stop} is {waypoint['distance']:.0f} m from the nearest road")
    segments = []
    for leg in body["routes"][0]["legs"]:
        points = [[round(lat, 5), round(lon, 5)] for step in leg["steps"] for lon, lat in step["geometry"]["coordinates"]]
        # consecutive steps share their joining point; keep it once
        segments.append(simplify([p for i, p in enumerate(points) if i == 0 or p != points[i - 1]]))
    return {
        "stops": stops,
        "positions": [list(STOPS[s][:2]) for s in stops],
        "legs_km": [round(leg["distance"] / 1000, 2) for leg in body["routes"][0]["legs"]],
        "segments": segments,
    }


def build_route_shapes(offline: bool) -> dict:
    """Road paths for every route. Cached in route_shapes.json and fetched again only when a route's stops change."""
    cached = json.loads(SHAPES_FILE.read_text(encoding="utf-8")).get("routes", {}) if SHAPES_FILE.exists() else {}
    shapes = {}
    for route in ROUTES:
        no, stops = route["route_no"], route["stops"]
        shape = cached.get(no)
        if shape and shape["stops"] == stops and shape["positions"] == [list(STOPS[s][:2]) for s in stops]:
            shapes[no] = shape
            continue
        if offline:
            print(f"Route {no}: no road path cached, the map will draw straight lines")
            continue
        print(f"Route {no}: fetching the road path from OSRM")
        shapes[no] = fetch_route_shape(stops)
    SHAPES_FILE.write_text(json.dumps({"attribution": SHAPES_ATTRIBUTION, "routes": shapes}, separators=(",", ":")),
                           encoding="utf-8")
    return shapes


def leg_lengths(route: dict, shapes: dict) -> list[float]:
    """Road distance (km) between consecutive stops: from the road path, else the straight line plus 30 percent."""
    shape = shapes.get(route["route_no"])
    if shape:
        return shape["legs_km"]
    stops = route["stops"]
    return [round(haversine_km(STOPS[a][:2], STOPS[b][:2]) * 1.3, 2) for a, b in zip(stops, stops[1:])]


def stop_offsets(legs_km: list[float], bus_type: str) -> list[int]:
    """Minutes from the first stop to every stop: running time at the average bus speed plus a halt at each stop."""
    offsets, elapsed = [0], 0.0
    for i, km in enumerate(legs_km):
        elapsed += km / BUS_SPEED_KMH[bus_type] * 60 + (DWELL_MIN if i else 0)
        offsets.append(max(offsets[-1] + 1, round(elapsed)))
    return offsets


def write_routes_csv(shapes: dict) -> list[dict]:
    rows = []
    for route in ROUTES:
        legs = leg_lengths(route, shapes)
        distance = round(sum(legs), 1)
        for direction, stops, leg_km, shift in (("Up", route["stops"], legs, 0),
                                                ("Down", route["stops"][::-1], legs[::-1], DOWN_SHIFT_MIN)):
            offsets = stop_offsets(leg_km, route["bus_type"])
            for day_type in DAY_TYPES:
                first = to_hhmm(to_minutes(route["first"]) + shift)
                last = to_hhmm(to_minutes(route["last"]) + shift)
                times = departures(first, last, route["frequency"][day_type])
                rows.append({
                    "route_no": route["route_no"],
                    "route_name": route["route_name"],
                    "direction": direction,
                    "source": stops[0],
                    "destination": stops[-1],
                    "stops": " | ".join(stops),
                    "day_type": day_type,
                    "bus_type": route["bus_type"],
                    "first_departure": times[0],
                    "last_departure": times[-1],
                    "frequency_min": route["frequency"][day_type],
                    "departure_times": " ".join(times),
                    "duration_min": offsets[-1],
                    "distance_km": distance,
                    "fare": fare_for(len(stops) - 1, route["bus_type"]),
                    "stop_offsets_min": " ".join(map(str, offsets)),
                })
    with open(RAW_DIR / "routes.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def write_fare_chart_csv() -> None:
    with open(RAW_DIR / "fare_chart.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["min_stops", "max_stops", "ordinary_fare", "ac_fare", "night_fare"])
        writer.writerows(FARE_CHART)


def write_stops_csv() -> None:
    with open(RAW_DIR / "stops.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["stop_name", "area", "landmark", "latitude", "longitude", "position", "routes"])
        for name, (lat, lon, area, landmark, source) in STOPS.items():
            routes = [r["route_no"] for r in ROUTES if name in r["stops"]]
            writer.writerow([name, area, landmark, lat, lon, source, " ".join(routes)])


# --------------------------------------------------------------------------- PDFs

styles = getSampleStyleSheet()
H1, H2, BODY = styles["Title"], styles["Heading2"], styles["BodyText"]


def _header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(2 * cm, A4[1] - 1.2 * cm, f"{OPERATOR}  |  {DISCLAIMER}")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {doc.page}")
    canvas.restoreState()


def _table(data: list[list[str]]) -> Table:
    table = Table(data, hAlign="LEFT", repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def build_pdf(filename: str, title: str, sections: list[tuple[str, list]]) -> None:
    doc = SimpleDocTemplate(str(DOCS_DIR / filename), pagesize=A4, title=title, author=OPERATOR,
                            topMargin=2 * cm, bottomMargin=2 * cm)
    story: list = [Paragraph(title, H1), Spacer(1, 8)]
    for heading, items in sections:
        story.append(Paragraph(heading, H2))
        for item in items:
            story.append(Paragraph(item, BODY) if isinstance(item, str) else item)
            story.append(Spacer(1, 4))
    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)


def _route(no: str) -> dict:
    return next(r for r in ROUTES if r["route_no"] == no)


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def write_fare_policy_pdf() -> None:
    chart = [["Stops travelled", "Ordinary (Rs.)", "AC (Rs.)", "Night (Rs.)"]] + [
        [f"{lo} - {hi}", str(o), str(a), str(n)] for lo, hi, o, a, n in FARE_CHART
    ]
    passes = [
        ["Pass type", "Validity", "Price (Rs.)", "Valid on"],
        ["Student Monthly Pass", "30 days", "300", "Ordinary buses"],
        ["General Monthly Pass", "30 days", "750", "Ordinary and Night buses"],
        ["Premium Monthly Pass", "30 days", "1200", "All buses including AC Airport and University Express"],
        ["Daily Travel Card", "Until 23:59 of the day", "60", "Ordinary buses, unlimited rides"],
    ]
    ac = [f"the Route {r['route_no']} {r['route_name'].removesuffix(' (AC)')}" for r in ROUTES if r["bus_type"] == "AC"]
    night = [r["route_no"] for r in ROUTES if r["bus_type"] == "Night"]
    main = _route("1")
    short = main["stops"].index("Vazirabad")
    build_pdf("fare_policy_and_concessions.pdf", "Fare Policy and Concessions", [
        ("1. How fares are calculated", [
            f"{OPERATOR} uses a stage-based fare system. The fare depends on the number of stops "
            "travelled between the boarding stop and the alighting stop, and on the type of bus. "
            f"There are three bus types: Ordinary, AC (used on {_join(ac)}) "
            f"and Night (Routes {_join(night)}, which run after 22:30).",
            _table(chart),
            f"Example: travelling from {main['stops'][0]} to Vazirabad on Route 1 covers {short} stops, so the "
            f"Ordinary fare is Rs. {fare_for(short, 'Ordinary')}. The full Route 1 journey from {main['stops'][0]} to "
            f"{main['stops'][-1]} covers {len(main['stops']) - 1} stops and costs "
            f"Rs. {fare_for(len(main['stops']) - 1, 'Ordinary')}.",
        ]),
        ("2. Concessions", [
            "Students: 50 percent concession on Ordinary buses on production of a valid college ID "
            "card or Student Monthly Pass. Student concession is not available on AC or Night buses.",
            "Senior citizens (age 65 and above): 50 percent concession on all bus types with a "
            "government photo ID showing date of birth.",
            "Children: travel is free for children below 5 years. Children aged 5 to 12 years pay "
            "half fare.",
            "Persons with disabilities: free travel on all buses with a valid disability certificate. "
            "One escort travels at half fare.",
            "Concession fares are rounded up to the nearest Rs. 5.",
        ]),
        ("3. Passes and travel cards", [_table(passes),
            "Passes are issued at the Central Bus Stand and Railway Station pass counters between "
            "08:00 and 20:00. Student passes require a bonafide certificate from the institution."]),
        ("4. Payment methods", [
            "Tickets can be bought from the conductor using cash or UPI. Passengers holding the "
            "RoutePilot Smart Card get a 5 percent discount on every single-journey ticket. Smart "
            "cards can be recharged at any pass counter or through the mobile app.",
        ]),
        ("5. Refunds and penalties", [
            "Tickets are valid only for the journey and bus on which they are issued and are not "
            "refundable. If a trip is cancelled by the operator, passengers may travel on the next "
            "bus of the same route with the same ticket.",
            "Travelling without a valid ticket attracts a penalty of Rs. 100 in addition to the "
            "fare for the full route.",
        ]),
    ])


def interchanges(min_routes: int = 4) -> list[tuple[str, list[str]]]:
    """Stops served by at least min_routes routes, busiest first."""
    serving = {stop: [r["route_no"] for r in ROUTES if stop in r["stops"]] for stop in STOPS}
    hubs = [(stop, routes) for stop, routes in serving.items() if len(routes) >= min_routes]
    return sorted(hubs, key=lambda hub: -len(hub[1]))


def write_passenger_guide_pdf(shapes: dict) -> None:
    routes_table = [["Route", "Name", "Bus type", "Length", "Service hours"]] + [
        [r["route_no"], r["route_name"], r["bus_type"], f"{sum(leg_lengths(r, shapes)):.1f} km",
         f'{r["first"]} - {r["last"]}'] for r in ROUTES
    ]
    areas: dict[str, list[str]] = {}
    for name, (_, _, area, _, _) in STOPS.items():
        areas.setdefault(area, []).append(name)
    areas_table = [["Area", "Bus stops"]] + [[area, Paragraph(", ".join(stops), BODY)] for area, stops in areas.items()]
    busiest = min(ROUTES, key=lambda r: (r["frequency"]["Weekday"], -len(r["stops"])))  # most frequent, then longest
    night = [r for r in ROUTES if r["bus_type"] == "Night"]
    build_pdf("passenger_guide.pdf", "Passenger Guide", [
        ("1. About the service", [
            f"{OPERATOR} operates {len(ROUTES)} city bus routes and {len(STOPS)} bus stops across Nanded: the "
            "Railway Station and Central Bus Stand, the Old City around Takht Sachkhand Sri Hazur Sahib, Shivaji "
            "Nagar and Taroda in the north, Bhagya Nagar and the Airport in the east, Wadi Bk in the west, Kautha, "
            "HUDCO and CIDCO (New Nanded) across the Godavari, and the Vishnupuri education and medical hub with "
            "SGGS Institute, the Government Medical College and SRTM University. "
            "Every route runs in two directions: Up (from the first stop listed) and Down (the return "
            f"journey). Down trips start {DOWN_SHIFT_MIN} minutes after the corresponding Up trip time.",
            _table(routes_table),
        ]),
        ("2. Areas and bus stops", [
            "The network is organised by area. Each area below lists the bus stops in it; the network map in "
            "the RoutePilot app shows every stop with its landmark and the routes that serve it.",
            _table(areas_table),
        ]),
        ("3. Timetables and day types", [
            "Each route has three timetables: Weekday (Monday to Friday), Saturday, and "
            "Sunday/Holiday. The Sunday/Holiday timetable also applies on public holidays. Buses run "
            f"more frequently on weekdays: for example Route {busiest['route_no']} runs every "
            f"{busiest['frequency']['Weekday']} minutes on weekdays, every {busiest['frequency']['Saturday']} minutes "
            f"on Saturdays and every {busiest['frequency']['Sunday/Holiday']} minutes on Sundays and holidays.",
            " ".join(f"Night Service {r['route_no']} ({r['route_name'].removeprefix('Night Service ')}) runs every "
                     f"{r['frequency']['Weekday']} minutes from {r['first']} to {r['last']} on all days." for r in night),
            "Journey times in the timetable are based on the road distance between stops at an average "
            f"Ordinary bus speed of {BUS_SPEED_KMH['Ordinary']} km/h, including a short halt at every stop.",
        ]),
        ("4. Important interchanges", [
            " ".join(f"{stop} connects Routes {_join(routes)}." for stop, routes in interchanges())
            + " Passengers travelling from CIDCO to the Railway Station can take Route 2 to Vazirabad "
            "and change to Route 1, or use the Night Service 7N after 22:30.",
        ]),
        ("5. Bus stop facilities", [
            "All major stops (Railway Station, Central Bus Stand, Vazirabad, Gurudwara Gate, Kautha, Workshop "
            "Corner, ITI Corner and CIDCO) have shelters, seating, digital arrival boards and drinking water. "
            "Railway Station and Central Bus Stand also have pass counters and enquiry desks.",
        ]),
        ("6. Luggage and accessibility", [
            "Each passenger may carry one bag of up to 20 kg free of charge. Bulky luggage is charged "
            "at Rs. 10 per item. AC Airport Express buses have a dedicated luggage rack.",
            "All AC buses and 60 percent of Ordinary buses are low-floor with a wheelchair ramp. "
            "Seats near the front door are reserved for women, senior citizens and persons with "
            "disabilities.",
        ]),
        ("7. Lost and found, helpline and complaints", [
            "Items left on buses are deposited at the Central Bus Stand lost-and-found office, "
            "open 09:00 to 18:00, and are kept for 30 days.",
            "Helpline (demo): 1800-000-0000, available 06:00 to 23:00. Complaints and suggestions "
            "can also be submitted through the RoutePilot app or at any enquiry desk; complaints are "
            "answered within 3 working days.",
        ]),
        ("8. Safety rules", [
            "Smoking, alcohol and travelling on the footboard are prohibited. Every bus has a panic "
            "button and CCTV cameras. In an emergency, inform the conductor or call the helpline.",
        ]),
    ])


def write_service_notices_pdf() -> None:
    build_pdf("service_notices_oct_2026.pdf", "Service Notices - October 2026", [
        ("Notice 1: Route 12 diversion near Gurudwara Gate", [
            "From 20 October to 5 November 2026, during the festival period, Route 12 buses will not "
            "stop at Gurudwara Gate or Chikhalwadi Corner. Route 12 will run from Vazirabad directly to "
            "Itwara Market. Passengers for Gurudwara Gate may use Route 2, Route 6 or Route 10.",
        ]),
        ("Notice 2: Extra Airport Express trips", [
            "Two additional Route 3 Airport Express trips will run on weekdays at 06:15 and 18:15 "
            "from the Central Bus Stand to meet the new morning and evening flights.",
        ]),
        ("Notice 3: Exam special trips to SGGS Institute", [
            "During university examinations (1 to 15 November 2026), Route 1 and Route 5 will run "
            "every 15 minutes between 07:00 and 10:00 on weekdays to serve students travelling to "
            "SGGS Institute, the Medical College and Vishnupuri.",
        ]),
        ("Notice 4: Smart card offer", [
            "Passengers who recharge the RoutePilot Smart Card with Rs. 500 or more in October 2026 "
            "receive a bonus of Rs. 50 in travel credit.",
        ]),
        ("Notice 5: Holiday timetable", [
            "On Diwali (public holiday) all routes will follow the Sunday/Holiday timetable. Night "
            "Services 7N and 9N will be extended until 02:30 on the night of Diwali.",
        ]),
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="reuse route_shapes.json; never call OSRM")
    args = parser.parse_args()
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    shapes = build_route_shapes(args.offline)
    rows = write_routes_csv(shapes)
    write_fare_chart_csv()
    write_stops_csv()
    write_fare_policy_pdf()
    write_passenger_guide_pdf(shapes)
    write_service_notices_pdf()
    print(f"Wrote {len(rows)} timetable rows ({len(ROUTES)} routes, {len(STOPS)} stops) to {RAW_DIR / 'routes.csv'}")
    print(f"Wrote road paths for {len(shapes)} of {len(ROUTES)} routes to {SHAPES_FILE}")
    print(f"Wrote fare chart and {len(list(DOCS_DIR.glob('*.pdf')))} PDF documents to {RAW_DIR}")


if __name__ == "__main__":
    main()
