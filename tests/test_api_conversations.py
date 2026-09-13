"""Conversation lifecycle: create, ask (SSE), persist across a simulated
restart, and escalation caching -- a second escalation must not pay for it
again (spec: unwanted behavior)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from raglab.api.app import build_app
from raglab.providers.base import Chunk, OverContextError
from tests.conftest import CHUNK_ID, make_app, make_state
from tests.fakes import FakeProvider, text_completion


def test_create_conversation_requires_known_collection(tmp_path):
    client = TestClient(make_app(tmp_path))

    ok = client.post("/api/conversations", json={"collection": "docs"})
    assert ok.status_code == 200
    assert ok.json()["collection"] == "docs"

    bad = client.post("/api/conversations", json={"collection": "nope"})
    assert bad.status_code == 400

    missing = client.post("/api/conversations", json={})
    assert missing.status_code == 422


def test_reserved_collection_is_refused_identically_to_unknown(tmp_path):
    # config.toml's collections never reach the API (spec amendment) -- a
    # conversation can't be scoped to a fixture collection the app hides.
    client = TestClient(make_app(tmp_path, collections={"rules": ["fb_rules.pdf"]}))

    reserved = client.post("/api/conversations", json={"collection": "rules"})
    unknown = client.post("/api/conversations", json={"collection": "nope"})

    assert reserved.status_code == unknown.status_code == 400


def test_ask_a_question_streams_tokens_then_citations_then_done(tmp_path):
    provider = FakeProvider([text_completion(f"16 years old.\n<citations>{CHUNK_ID}</citations>")])
    client = TestClient(make_app(tmp_path, baseline_provider=provider))
    conversation_id = client.post("/api/conversations", json={"collection": "docs"}).json()["id"]

    response = client.post(
        f"/api/conversations/{conversation_id}/turns", json={"question": "What is the minimum age?"}
    )

    assert response.status_code == 200
    body = response.text
    assert "event: token" in body
    assert "16 years old." in body
    assert "<citations>" not in body
    assert f'event: citations\ndata: {{"cited": ["{CHUNK_ID}"]}}' in body
    assert "event: done" in body


def test_provider_error_mid_stream_preserves_partial_answer(tmp_path):
    class _FailingProvider(FakeProvider):
        async def stream(self, messages, *, tools=None, max_tokens=4096):
            yield Chunk(text="partial answer")
            raise OverContextError("fake", 999_999, 1000)

    provider = _FailingProvider([])
    client = TestClient(make_app(tmp_path, baseline_provider=provider))
    conversation_id = client.post("/api/conversations", json={"collection": "docs"}).json()["id"]

    response = client.post(f"/api/conversations/{conversation_id}/turns", json={"question": "Q?"})

    assert response.status_code == 200
    body = response.text
    assert "event: token" in body and "partial answer" in body
    assert "event: error" in body
    assert "event: done" in body

    conversation = client.get(f"/api/conversations/{conversation_id}").json()
    assert conversation["turns"][0]["baseline"]["text"] == "partial answer"
    assert conversation["turns"][0]["baseline"]["error"] is not None


def test_conversation_survives_simulated_restart(tmp_path):
    provider = FakeProvider([text_completion("16.")])
    state = make_state(tmp_path, baseline_provider=provider)
    conversation_id = TestClient(build_app(state)).post(
        "/api/conversations", json={"collection": "docs"}
    ).json()["id"]

    first_app = build_app(state)
    TestClient(first_app).post(f"/api/conversations/{conversation_id}/turns", json={"question": "Q?"})

    # A fresh AppState over the same tmp_path conversations dir stands in
    # for a server restart -- nothing is shared but the files on disk.
    reloaded_state = make_state(tmp_path)
    second_app = build_app(reloaded_state)
    conversation = TestClient(second_app).get(f"/api/conversations/{conversation_id}").json()

    assert len(conversation["turns"]) == 1
    assert conversation["turns"][0]["question"] == "Q?"


def test_escalation_is_cached_after_first_call(tmp_path):
    baseline_provider = FakeProvider([text_completion("16.")])
    agentic_provider = FakeProvider([text_completion(f"16, more thoroughly.\n<citations>{CHUNK_ID}</citations>")])
    client = TestClient(make_app(tmp_path, baseline_provider=baseline_provider, agentic_provider=agentic_provider))
    conversation_id = client.post("/api/conversations", json={"collection": "docs"}).json()["id"]
    client.post(f"/api/conversations/{conversation_id}/turns", json={"question": "Q?"})

    first = client.post(f"/api/conversations/{conversation_id}/turns/0/escalate")
    second = client.post(f"/api/conversations/{conversation_id}/turns/0/escalate")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["pipeline"] == "agentic"
    assert len(agentic_provider.calls) == 1  # the second escalation made no provider call


def test_escalating_unknown_turn_is_404(tmp_path):
    client = TestClient(make_app(tmp_path))
    conversation_id = client.post("/api/conversations", json={"collection": "docs"}).json()["id"]

    response = client.post(f"/api/conversations/{conversation_id}/turns/0/escalate")

    assert response.status_code == 404
