from datetime import datetime

import pytest

from app.config import get_settings
from app.services.transport import TransportData, day_type_for, detect_day_type


@pytest.fixture(scope="module")
def transport():
    return TransportData(get_settings().data_dir)


@pytest.mark.parametrize("text, expected", [
    ("How do I go from CIDCO to SGGS college?", ["CIDCO", "SGGS Institute"]),
    ("bus from vazirbad to airport", ["Vazirabad", "Airport"]),  # typo
    ("from the bus station to the railway station", ["Central Bus Stand", "Railway Station"]),
    ("itwara market to university", ["Itwara Market", "SRTM University"]),
    ("what concessions do students get?", []),
    ("hingoli gate to deglur naka", ["Hingoli Gate", "Degloor Naka"]),
])
def test_find_stops_in_text(transport, text, expected):
    assert transport.find_stops_in_text(text) == expected


def test_resolve_stop(transport):
    assert transport.resolve_stop("cidco") == "CIDCO"
    assert transport.resolve_stop("Shivaji nagr") == "Shivaji Nagar"
    assert transport.resolve_stop("Mumbai") is None


def test_detect_route_and_day_type(transport):
    assert transport.detect_route_no("route 7n timings") == "7N"
    assert transport.detect_route_no("bus no. 5 from CIDCO") == "5"
    assert transport.detect_route_no("route 99") is None
    assert detect_day_type("buses on Sunday") == "Sunday/Holiday"
    assert detect_day_type("on diwali") == "Sunday/Holiday"
    assert detect_day_type("saturday timetable") == "Saturday"
    assert detect_day_type("next bus") is None
    assert day_type_for(datetime(2026, 10, 17)) == "Saturday"
    assert day_type_for(datetime(2026, 10, 19)) == "Weekday"


def test_fare_chart(transport):
    assert transport.fare_for(1, "Ordinary") == 10
    assert transport.fare_for(3, "Ordinary") == 15
    assert transport.fare_for(4, "AC") == 25
    assert transport.fare_for(5, "Night") == 25


def test_direct_journey(transport):
    journeys = transport.find_journeys("Railway Station", "Shivaji Nagar", "Weekday")
    leg = journeys[0].legs[0]
    assert (leg.route_no, leg.direction, leg.stops_travelled, leg.fare) == ("1", "Up", 3, 15)
    assert leg.stops == ["Railway Station", "Vazirabad", "Kalamandir", "Shivaji Nagar"]


def test_return_direction(transport):
    leg = transport.find_journeys("SGGS Institute", "Railway Station", "Weekday")[0].legs[0]
    assert (leg.route_no, leg.direction) == ("1", "Down")
    assert leg.departures[0] == "06:15"  # Down trips start 15 minutes after Up trips


def test_transfer_journey(transport):
    journeys = transport.find_journeys("Itwara Market", "SRTM University", "Weekday")
    assert journeys and all(j.transfers == 1 for j in journeys)
    first = journeys[0]
    assert first.legs[0].alight == first.legs[1].board
    assert first.fare == sum(leg.fare for leg in first.legs)


def test_new_routes(transport):
    leg = transport.find_journeys("Railway Station", "Waghala", "Weekday")[0].legs[0]
    assert (leg.route_no, leg.stops_travelled) == ("8", 5)
    leg = transport.find_journeys("Railway Station", "SRTM University", "Weekday")[0].legs[0]
    assert (leg.route_no, leg.bus_type, leg.fare) == ("13", "AC", 30)
    assert transport.routes_serving("Airport") == ["3", "10"]


def test_daytime_service_preferred_over_night(transport):
    journeys = transport.find_journeys("Central Bus Stand", "Railway Station", "Weekday")
    assert journeys[0].legs[0].bus_type != "Night"


def test_daytime_transfer_offered_when_only_night_bus_is_direct(transport):
    journeys = transport.find_journeys("CIDCO", "Railway Station", "Weekday")
    assert journeys[0].transfers == 1 and journeys[0].legs[0].bus_type != "Night"
    assert any(j.legs[0].route_no == "7N" and not j.transfers for j in journeys)
    late = transport.find_journeys("CIDCO", "Railway Station", "Weekday", now=datetime(2026, 10, 16, 23, 0))
    assert late[0].legs[0].route_no == "7N"


def test_next_departures(transport):
    morning = transport.find_journeys("CIDCO", "SGGS Institute", "Weekday", now=datetime(2026, 10, 16, 9, 10))
    assert morning[0].next_departures == ["09:15", "09:45", "10:15"]
    # night service crossing midnight: at 00:10 the next buses are 00:30 and 01:30
    night = transport.find_journeys("Railway Station", "Hadco", "Weekday", now=datetime(2026, 10, 16, 0, 10))
    night_bus = next(j for j in night if j.legs[0].route_no == "7N")
    assert night_bus.next_departures == ["00:30", "01:30"]


def test_timetable(transport):
    table = transport.timetable("2", "Sunday/Holiday", "Up")
    assert len(table) == 1
    assert table[0]["frequency_min"] == 30
    assert table[0]["departures"][:2] == ["05:45", "06:15"]


def test_analyse(transport):
    now = datetime(2026, 10, 16, 9, 10)
    result = transport.analyse("What is the fare from Railway Station to Shivaji Nagar?", now)
    assert result.intent == "fare" and result.found
    assert "Rs. 15" in result.facts
    result = transport.analyse("route 3 timings on sunday", now)
    assert result.route_no == "3" and result.day_type == "Sunday/Holiday"
    assert len(result.data["timetable"]) == 2
    assert not transport.analyse("what concessions do students get?", now).found
