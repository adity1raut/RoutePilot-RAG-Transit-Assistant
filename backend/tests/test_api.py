import os

os.environ["LLM_PROVIDER"] = "none"  # tests never call a paid LLM

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["provider"] == "none"
    assert body["chunks_indexed"] > 0 and body["routes"] == 13


def test_stops_and_routes(client):
    assert "CIDCO" in client.get("/api/stops").json()
    routes = client.get("/api/routes").json()
    assert [r["route_no"] for r in routes] == ["1", "2", "3", "4", "5", "6", "7N", "8", "9", "10", "11", "12", "13"]


def test_map(client):
    body = client.get("/api/map").json()
    stops = {s["name"]: s for s in body["stops"]}
    assert set(stops) == set(client.get("/api/stops").json())  # every stop can be drawn
    assert all(19.0 < s["lat"] < 19.3 and 77.2 < s["lon"] < 77.4 for s in stops.values())  # inside Nanded
    assert stops["Airport"]["routes"] == ["3", "10"] and not stops["Airport"]["approximate"]
    assert len(body["routes"]) == 13 and all(stop in stops for r in body["routes"] for stop in r["stops"])


def test_timetable(client):
    res = client.get("/api/routes/3/timetable", params={"day_type": "Weekday", "direction": "Up"})
    assert res.status_code == 200 and res.json()[0]["bus_type"] == "AC"
    assert client.get("/api/routes/99/timetable").status_code == 404
    assert client.get("/api/routes/3/timetable", params={"day_type": "Friday"}).status_code == 422


def test_journeys_and_fares(client):
    body = client.get("/api/journeys", params={"source": "cidco", "destination": "sggs", "day_type": "Weekday"}).json()
    assert body["source"] == "CIDCO" and body["destination"] == "SGGS Institute"
    assert body["journeys"][0]["legs"][0]["route_no"] == "5"
    fares = client.get("/api/fares", params={"source": "Railway Station", "destination": "Shivaji Nagar"}).json()
    assert fares["options"][0]["fare"] == 15
    assert client.get("/api/journeys", params={"source": "Mars", "destination": "CIDCO"}).status_code == 404


def test_chat_route_question(client):
    body = client.post("/api/chat", json={"question": "How do I go from CIDCO to SGGS Institute?"}).json()
    assert "Route 5" in body["answer"]
    assert body["sources"][0]["kind"] == "structured"
    assert body["provider"] == "none" and body["intent"] == "route"


def test_chat_document_question(client):
    body = client.post("/api/chat", json={"question": "What concessions do students get?"}).json()
    assert "50 percent" in body["answer"]
    assert any(s["source"] == "fare_policy_and_concessions.pdf" for s in body["sources"])


def test_chat_follow_up(client):
    history = [{"role": "user", "content": "bus from Railway Station to Airport"},
               {"role": "assistant", "content": "Take Route 3."}]
    body = client.post("/api/chat", json={"question": "and on Sunday?", "history": history}).json()
    assert body["day_type"] == "Sunday/Holiday" and "Route 3" in body["answer"]
    # a new, unrelated question must not inherit the previous journey
    body = client.post("/api/chat", json={"question": "What concessions do students get?", "history": history}).json()
    assert body["stops"] == [] and "Route 3" not in body["answer"] and "50 percent" in body["answer"]


def test_chat_validation(client):
    assert client.post("/api/chat", json={"question": ""}).status_code == 422


def test_chat_with_llm(client):
    pipeline = app.state.pipeline
    original = pipeline.llm, pipeline.chain
    seen = {}

    def capture(prompt_value):
        seen["prompt"] = prompt_value.to_string()
        return prompt_value

    try:
        pipeline.llm = FakeListChatModel(responses=["Take **Route 5** from CIDCO [S1]."])
        pipeline.chain = pipeline.prompt | RunnableLambda(capture) | pipeline.llm | StrOutputParser()
        body = client.post("/api/chat", json={"question": "CIDCO to SGGS Institute?"}).json()
        assert body["answer"] == "Take **Route 5** from CIDCO [S1]."
        assert "[S1] Route, timetable and fare lookup" in seen["prompt"]
        assert "Never invent routes" in seen["prompt"]

        def broken(_):
            raise ConnectionError("network down")

        pipeline.chain = RunnableLambda(broken)
        body = client.post("/api/chat", json={"question": "CIDCO to SGGS Institute?"}).json()
        assert body["warning"] and "Route 5" in body["answer"] and body["provider"] == "none"
    finally:
        pipeline.llm, pipeline.chain = original
