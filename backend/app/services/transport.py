"""Structured transport data: stop matching, route finding, timetables and fares.

Semantic search is good at "what does the fare policy say about students?" but unreliable for
exact lookups such as "which bus goes from CIDCO to SGGS Institute and how much does it cost?".
This module answers those precisely from routes.csv / fare_chart.csv. Its output is added to the
RAG context, so the LLM receives exact facts alongside the retrieved document chunks.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

DAY_TYPES = ["Weekday", "Saturday", "Sunday/Holiday"]
ROUTES_FILE = "routes.csv"
FARE_CHART_FILE = "fare_chart.csv"
STOPS_FILE = "stops.csv"  # optional: stop coordinates for the network map
SHAPES_FILE = "route_shapes.json"  # optional: road geometry between consecutive stops, for the map

# Extra names people use for stops (lowercase). Stop names themselves are always matched.
STOP_ALIASES = {
    "Railway Station": ["station", "railway", "rly station", "train station", "nanded station"],
    "Central Bus Stand": ["bus stand", "cbs", "bus station", "bus depot", "st stand", "msrtc"],
    "Kalamandir": ["kala mandir", "doctor lane", "doctors lane"],
    "Vazirabad": ["shivaji putla", "shivaji putala", "sp office", "wazirabad"],
    "Government Hospital": ["hospital", "govt hospital", "civil hospital", "sggs memorial hospital"],
    "Govardhan Ghat": ["gowardhan ghat", "goverdhan ghat"],
    "Shivaji Nagar": ["shivajinagar", "vishnu nagar"],
    "ITI Corner": ["iti", "iti chowk", "phule market", "mahatma phule market", "vip road"],
    "Yeshwant College": ["yeshwant", "yeshwant mahavidyalaya"],
    "Gurudwara Gate": ["gurudwara", "gurdwara", "sachkhand", "hazur sahib"],
    "Chikhalwadi Corner": ["chikhalwadi"],
    "Juna Mondha": ["old mondha"],
    "Nagina Ghat": ["nagina"],
    "Itwara Market": ["itwara"],
    "Degloor Naka": ["deglur naka", "degloor", "deglur", "hyder bagh", "madina chowk"],
    "Hingoli Gate": ["hingoli"],
    "Nava Mondha": ["new mondha", "navamondha"],
    "Hingoli Naka": ["maharana pratap chowk"],
    "Maltekdi": ["mal tekdi", "maltekdi gurudwara"],
    "Bhagya Nagar": ["bhagyanagar"],
    "Workshop Corner": ["workshop"],
    "Taroda Naka": ["taroda"],
    "Malegaon Road": ["malegaon"],
    "Chhatrapati Chowk": ["chatrapati chowk", "purna road"],
    "Wadi Bk": ["wadi", "wadi budruk"],
    "Yeshwant Nagar": ["agricultural college"],
    "MGM College": ["mgm", "mgm college of engineering"],
    "Airport": ["airport", "air port"],
    "Navi Kautha": ["nava kautha", "new kautha", "navakotha"],
    "Latur Phata": ["latur fata", "latur road"],
    "HUDCO": ["hadco", "hudco colony"],
    "CIDCO": ["cidco colony", "new nanded", "waghala"],
    "SGGS Institute": ["sggs", "sggs college", "sggsiet", "sggs ie t"],
    "Medical College Vishnupuri": ["medical college", "gmc", "government medical college"],
    "SRTM University": ["university", "srtmu", "srtm", "swami ramanand teerth"],
    "Tuppa": ["tuppa phata"],
}

FARE_WORDS = r"\b(fare|fares|cost|price|ticket|charge|charges|how much|rs|rupees|concession|pass)\b"
TIME_WORDS = (r"\b(time|times|timing|timings|schedule|timetable|when|first bus|last bus|next bus|"
              r"frequency|departure|departures|leave|leaves|arrive|every)\b")
ROUTE_WORDS = r"\b(route|routes|which bus|how (?:do|can) i (?:go|get|reach)|reach|travel|go to|get to|from)\b"
STOPWORDS = {"which", "where", "there", "their", "about", "from", "bus", "buses", "route", "routes",
             "today", "timing", "timings", "fare", "fares", "price", "student", "students"}


def _norm(text: str) -> str:
    return " " + re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip() + " "


def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _to_hhmm(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _service_minutes(times: list[str]) -> list[int]:
    """Convert HH:MM departures to monotonically increasing minutes (handles services past midnight)."""
    result, offset, previous = [], 0, -1
    for t in times:
        m = _to_minutes(t) + offset
        if m < previous:
            offset += 24 * 60
            m += 24 * 60
        result.append(m)
        previous = m
    return result


def _stop_offsets(row: pd.Series) -> list[int]:
    """Minutes from the first stop to each stop: from stop_offsets_min, else spread evenly over the journey."""
    n = len(row.stop_list)
    raw = row.get("stop_offsets_min")
    offsets = [int(x) for x in raw.split()] if isinstance(raw, str) else []
    if len(offsets) == n:
        return offsets
    return [int(round(row.duration_min * i / (n - 1))) for i in range(n)]


def day_type_for(moment: datetime) -> str:
    return {5: "Saturday", 6: "Sunday/Holiday"}.get(moment.weekday(), "Weekday")


def detect_day_type(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\b(sunday|holiday|holidays|diwali)\b", t):
        return "Sunday/Holiday"
    if re.search(r"\bsaturday\b", t):
        return "Saturday"
    if re.search(r"\b(weekday|weekdays|monday|tuesday|wednesday|thursday|friday)\b", t):
        return "Weekday"
    return None


@dataclass
class Leg:
    route_no: str
    route_name: str
    direction: str
    bus_type: str
    board: str
    alight: str
    stops_travelled: int
    travel_min: int
    fare: int
    stops: list[str]
    departures: list[str]  # departure times at the boarding stop

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Journey:
    legs: list[Leg]
    day_type: str
    next_departures: list[str] = field(default_factory=list)

    @property
    def fare(self) -> int:
        return sum(leg.fare for leg in self.legs)

    @property
    def travel_min(self) -> int:
        return sum(leg.travel_min for leg in self.legs)

    @property
    def transfers(self) -> int:
        return len(self.legs) - 1

    def to_dict(self) -> dict:
        return {
            "legs": [leg.to_dict() for leg in self.legs],
            "day_type": self.day_type,
            "fare": self.fare,
            "travel_min": self.travel_min,
            "transfers": self.transfers,
            "next_departures": self.next_departures,
        }

    def describe(self) -> str:
        parts = []
        for leg in self.legs:
            parts.append(
                f"Route {leg.route_no} ({leg.route_name}, {leg.direction} direction, {leg.bus_type} bus) "
                f"from {leg.board} to {leg.alight}: {leg.stops_travelled} stops, about {leg.travel_min} min, "
                f"fare Rs. {leg.fare}. Stops: {' -> '.join(leg.stops)}."
            )
        text = " Then change to ".join(parts)
        first = self.legs[0]
        summary = (f"{'Direct' if not self.transfers else f'{self.transfers} transfer'} journey on "
                   f"{self.day_type}: total fare Rs. {self.fare}, total travel time about {self.travel_min} min. ")
        timing = (f"First bus from {first.board}: {first.departures[0]}, last bus: {first.departures[-1]}."
                  if first.departures else "")
        if self.next_departures:
            timing += f" Next departures from {first.board}: {', '.join(self.next_departures)}."
        return summary + text + " " + timing


@dataclass
class StructuredResult:
    intent: str
    day_type: str
    stops: list[str]
    route_no: str | None
    facts: str | None
    data: dict

    @property
    def found(self) -> bool:
        return bool(self.facts)


class TransportData:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.routes = pd.read_csv(self.data_dir / ROUTES_FILE, dtype={"route_no": str, "stop_offsets_min": str})
        self.routes["stop_list"] = self.routes["stops"].apply(lambda s: [x.strip() for x in s.split("|")])
        self.routes["time_list"] = self.routes["departure_times"].apply(str.split)
        self.routes["offset_list"] = self.routes.apply(_stop_offsets, axis=1)
        self.fare_chart = pd.read_csv(self.data_dir / FARE_CHART_FILE)
        stops_file = self.data_dir / STOPS_FILE
        self.stop_locations: dict[str, dict] = (
            {r["stop_name"]: r for r in pd.read_csv(stops_file).fillna("").to_dict(orient="records")}
            if stops_file.exists() else {})
        shapes_file = self.data_dir / SHAPES_FILE
        shapes = json.loads(shapes_file.read_text(encoding="utf-8")) if shapes_file.exists() else {}
        self.shapes: dict[str, dict] = shapes.get("routes", {})
        self.shapes_attribution: str = shapes.get("attribution", "")

        seen: dict[str, None] = {}
        for stops in self.routes["stop_list"]:
            seen.update(dict.fromkeys(stops))
        self.stops: list[str] = sorted(seen)
        self.route_numbers: list[str] = list(dict.fromkeys(self.routes["route_no"]))

        self._alias_to_stop: dict[str, str] = {s.lower(): s for s in self.stops}
        for stop, aliases in STOP_ALIASES.items():
            if stop in seen:
                for alias in aliases:
                    self._alias_to_stop.setdefault(alias, stop)
        # longest alias first so "bus station" wins over "station"
        self._aliases = sorted(self._alias_to_stop, key=len, reverse=True)

    # ------------------------------------------------------------------ parsing
    def resolve_stop(self, name: str) -> str | None:
        """Map a user-typed stop name (possibly misspelled or an alias) to a canonical stop."""
        key = _norm(name).strip()
        if not key:
            return None
        if key in self._alias_to_stop:
            return self._alias_to_stop[key]
        match = difflib.get_close_matches(key, self._aliases, n=1, cutoff=0.75)
        return self._alias_to_stop[match[0]] if match else None

    def find_stops_in_text(self, text: str) -> list[str]:
        """Return the stops mentioned in free text, in the order they appear."""
        t = _norm(text)
        taken = [False] * len(t)
        found: list[tuple[int, str]] = []
        for alias in self._aliases:
            for m in re.finditer(rf"(?<= ){re.escape(alias)}(?= )", t):
                if any(taken[m.start():m.end()]):
                    continue
                taken[m.start():m.end()] = [True] * (m.end() - m.start())
                found.append((m.start(), self._alias_to_stop[alias]))

        # Fuzzy pass for typos ("vazirbad", "cidko") over the words that were not matched.
        words = [(m.start(), m.group()) for m in re.finditer(r"[a-z0-9]+", t)
                 if not any(taken[m.start():m.end()])]
        for size in (2, 1):
            for i in range(len(words) - size + 1):
                chunk = words[i:i + size]
                if size == 2 and chunk[1][0] != chunk[0][0] + len(chunk[0][1]) + 1:
                    continue  # the two words are not adjacent in the text
                phrase = " ".join(w for _, w in chunk)
                if len(phrase) < 5 or phrase in STOPWORDS:
                    continue
                start = chunk[0][0]
                if any(taken[start:start + len(phrase)]):
                    continue
                match = difflib.get_close_matches(phrase, self._aliases, n=1, cutoff=0.85)
                if match:
                    taken[start:start + len(phrase)] = [True] * len(phrase)
                    found.append((start, self._alias_to_stop[match[0]]))

        ordered = [stop for _, stop in sorted(found)]
        return list(dict.fromkeys(ordered))

    def detect_route_no(self, text: str) -> str | None:
        m = re.search(r"\b(?:route|bus|service)\s*(?:no\.?|number|#)?\s*(\d{1,2}[a-z]?)\b", text.lower())
        if m and m.group(1).upper() in self.route_numbers:
            return m.group(1).upper()
        return None

    @staticmethod
    def detect_intent(text: str) -> str:
        t = text.lower()
        if re.search(FARE_WORDS, t):
            return "fare"
        if re.search(TIME_WORDS, t):
            return "timetable"
        if re.search(ROUTE_WORDS, t):
            return "route"
        return "general"

    # ------------------------------------------------------------------ fares
    def fare_for(self, stops_travelled: int, bus_type: str) -> int:
        column = {"Ordinary": "ordinary_fare", "AC": "ac_fare", "Night": "night_fare"}.get(bus_type, "ordinary_fare")
        row = self.fare_chart[(self.fare_chart.min_stops <= stops_travelled) & (self.fare_chart.max_stops >= stops_travelled)]
        if row.empty:
            row = self.fare_chart.tail(1)
        return int(row.iloc[0][column])

    # ------------------------------------------------------------------ routes
    def _leg(self, row: pd.Series, i: int, j: int) -> Leg:
        stops, offsets = row.stop_list, row.offset_list
        return Leg(
            route_no=row.route_no,
            route_name=row.route_name,
            direction=row.direction,
            bus_type=row.bus_type,
            board=stops[i],
            alight=stops[j],
            stops_travelled=j - i,
            travel_min=offsets[j] - offsets[i],
            fare=self.fare_for(j - i, row.bus_type),
            stops=stops[i:j + 1],
            departures=[_to_hhmm(m + offsets[i]) for m in _service_minutes(row.time_list)],
        )

    def find_journeys(self, source: str, destination: str, day_type: str = "Weekday",
                      now: datetime | None = None, max_results: int = 4) -> list[Journey]:
        """Direct journeys between two stops, or one-transfer journeys when no direct bus exists."""
        if source == destination:
            return []
        rows = self.routes[self.routes.day_type == day_type]
        journeys: list[Journey] = []
        for _, row in rows.iterrows():
            stops = row.stop_list
            if source in stops and destination in stops and stops.index(source) < stops.index(destination):
                journeys.append(Journey([self._leg(row, stops.index(source), stops.index(destination))], day_type))

        # look for one-change journeys when there is no direct bus, or only a Night service
        if all(leg.bus_type == "Night" for j in journeys for leg in j.legs):
            seen = set()
            for _, first in rows.iterrows():
                s1 = first.stop_list
                if source not in s1:
                    continue
                i = s1.index(source)
                for k in range(i + 1, len(s1)):
                    hub = s1[k]
                    for _, second in rows.iterrows():
                        s2 = second.stop_list
                        if second.route_no == first.route_no or hub not in s2 or destination not in s2:
                            continue
                        a, b = s2.index(hub), s2.index(destination)
                        key = (first.route_no, second.route_no, hub)
                        if a < b and key not in seen:
                            seen.add(key)
                            journeys.append(Journey([self._leg(first, i, k), self._leg(second, a, b)], day_type))

        # Night buses run only after 22:30: rank them last during the day and first late at night,
        # then prefer direct, fastest and cheapest journeys.
        late = now is not None and (now.hour >= 22 or now.hour < 4)

        def rank(j: Journey):
            return any(leg.bus_type == "Night" for leg in j.legs) != late, j.transfers, j.travel_min, j.fare

        # always keep direct journeys; fill the remaining slots with the best one-change journeys
        direct = [j for j in journeys if not j.transfers]
        changes = sorted((j for j in journeys if j.transfers), key=rank)[:max(0, max_results - len(direct))]
        journeys = sorted(direct + changes, key=rank)
        if now is not None and day_type == day_type_for(now):
            for journey in journeys:
                journey.next_departures = self._next(journey.legs[0].departures, now)
        return journeys

    @staticmethod
    def _next(departures: list[str], now: datetime, count: int = 3) -> list[str]:
        current = now.hour * 60 + now.minute
        minutes = _service_minutes(departures)
        # a service that crosses midnight is still "tonight" in the early hours
        if minutes and minutes[-1] >= 24 * 60 and current < minutes[-1] - 24 * 60:
            current += 24 * 60
        return [_to_hhmm(m) for m in minutes if m >= current][:count]

    def routes_serving(self, stop: str) -> list[str]:
        mask = self.routes.stop_list.apply(lambda stops: stop in stops)
        return list(dict.fromkeys(self.routes[mask].route_no))

    def route_summaries(self) -> list[dict]:
        up = self.routes[(self.routes.direction == "Up") & (self.routes.day_type == "Weekday")]
        return [
            {
                "route_no": r.route_no,
                "route_name": r.route_name,
                "source": r.source,
                "destination": r.destination,
                "bus_type": r.bus_type,
                "stops": r.stop_list,
                "stop_offsets": r.offset_list,
                "distance_km": float(r.distance_km),
                "duration_min": int(r.duration_min),
                "fare": int(r.fare),
                "first_departure": r.first_departure,
                "last_departure": r.last_departure,
            }
            for r in up.itertuples()
        ]

    def map_data(self) -> dict:
        """Stops with coordinates (from stops.csv) and every route's stops and road path, for the network map.

        A route's "segments" are the road paths between its consecutive Up-direction stops (from route_shapes.json),
        or None when there is no path for exactly these stops; the map then joins the stops with straight lines.
        """
        stops = [
            {
                "name": name,
                "lat": float(loc["latitude"]),
                "lon": float(loc["longitude"]),
                "area": loc.get("area", ""),
                "landmark": loc.get("landmark", ""),
                "approximate": loc.get("position") != "OpenStreetMap",
                "routes": self.routes_serving(name),
            }
            for name in self.stops if (loc := self.stop_locations.get(name))
        ]
        routes = []
        for route in self.route_summaries():
            shape = self.shapes.get(route["route_no"])
            matches = shape and shape["stops"] == route["stops"] and len(shape["segments"]) == len(route["stops"]) - 1
            routes.append({**route, "segments": shape["segments"] if matches else None})
        return {"stops": stops, "routes": routes, "attribution": self.shapes_attribution}

    def timetable(self, route_no: str, day_type: str | None = None, direction: str | None = None) -> list[dict]:
        rows = self.routes[self.routes.route_no.str.upper() == route_no.upper()]
        if day_type:
            rows = rows[rows.day_type == day_type]
        if direction:
            rows = rows[rows.direction.str.lower() == direction.lower()]
        return [
            {
                "route_no": r.route_no,
                "route_name": r.route_name,
                "direction": r.direction,
                "day_type": r.day_type,
                "bus_type": r.bus_type,
                "source": r.source,
                "destination": r.destination,
                "stops": r.stop_list,
                "stop_offsets": r.offset_list,
                "frequency_min": int(r.frequency_min),
                "first_departure": r.first_departure,
                "last_departure": r.last_departure,
                "departures": r.time_list,
                "duration_min": int(r.duration_min),
                "fare": int(r.fare),
            }
            for r in rows.itertuples()
        ]

    # ------------------------------------------------------------------ for the RAG pipeline
    def analyse(self, query: str, now: datetime | None = None) -> StructuredResult:
        """Extract stops / route / day type from a question and look up the exact facts."""
        now = now or datetime.now()
        intent = self.detect_intent(query)
        day_type = detect_day_type(query) or day_type_for(now)
        stops = self.find_stops_in_text(query)
        route_no = self.detect_route_no(query)
        lines: list[str] = []
        data: dict = {}

        if len(stops) >= 2:
            if intent == "general":
                intent = "route"
            source, destination = stops[0], stops[1]
            journeys = self.find_journeys(source, destination, day_type, now)
            data["journeys"] = [j.to_dict() for j in journeys]
            if journeys:
                lines.append(f"Journey options from {source} to {destination} ({day_type} timetable):")
                lines += [f"Option {n}: {j.describe()}" for n, j in enumerate(journeys, 1)]
            else:
                lines.append(f"No direct or one-transfer bus service was found from {source} to {destination}.")
        elif route_no:
            table = self.timetable(route_no, day_type)
            data["timetable"] = table
            for t in table:
                lines.append(
                    f"Route {t['route_no']} {t['route_name']} - {t['direction']} direction ({t['source']} to "
                    f"{t['destination']}), {t['day_type']}: {t['bus_type']} bus, every {t['frequency_min']} min, "
                    f"first bus {t['first_departure']}, last bus {t['last_departure']}, journey time "
                    f"{t['duration_min']} min, full-route fare Rs. {t['fare']}. Departures: {' '.join(t['departures'])}. "
                    f"Stops: {' -> '.join(t['stops'])}."
                )
        elif len(stops) == 1:
            serving = self.routes_serving(stops[0])
            data["routes_serving"] = serving
            if serving:
                lines.append(f"{stops[0]} is served by route(s): {', '.join(serving)}.")
                for t in (t for no in serving for t in self.timetable(no, day_type)):
                    s = t["stops"]
                    if stops[0] in s[:-1]:
                        offset = t["stop_offsets"][s.index(stops[0])]
                        times = [_to_hhmm(m + offset) for m in _service_minutes(t["departures"])]
                        lines.append(
                            f"Route {t['route_no']} towards {t['destination']} ({t['day_type']}): departs "
                            f"{stops[0]} from {times[0]} to {times[-1]} every {t['frequency_min']} min."
                        )

        return StructuredResult(intent, day_type, stops, route_no, "\n".join(lines) or None, data)
