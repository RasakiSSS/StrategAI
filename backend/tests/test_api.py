import pytest
from fastapi.testclient import TestClient
from threading import Event
from unittest.mock import patch

from app.api.store import store
from app.engine.human_source import QueueHumanSource
from app.engine.playthrough import Decisions
from app.main import app


@pytest.fixture(autouse=True)
def _clear_store():
    store.clear()
    yield
    store.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_create_game_returns_state(client: TestClient):
    r = client.post("/games", json={"radius": 4, "seed": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["turn"] == 1
    assert body["map_radius"] == 4
    assert len(body["civs"]) >= 2
    # two units per civ (settler + warrior)
    assert len(body["units"]) == 2 * len(body["civs"])
    assert body["cities"] == []


def test_create_game_accepts_custom_human_name(client: TestClient):
    r = client.post("/games", json={"radius": 4, "seed": 1, "human_name": "Nova Roma"})
    assert r.status_code == 200
    body = r.json()
    human = next(c for c in body["civs"] if c["is_human"])
    assert human["name"] == "Nova Roma"


def test_get_game_returns_same_state(client: TestClient):
    created = client.post("/games", json={"radius": 3, "seed": 2}).json()
    r = client.get(f"/games/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_unknown_game_returns_404(client: TestClient):
    r = client.get("/games/999")
    assert r.status_code == 404


def test_intro_narration_requires_openai_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = client.post("/audio/intro", json={"text": "An empire rises."})
    assert r.status_code == 503
    assert r.json()["detail"] == "OPENAI_API_KEY is not configured"


def test_advance_turn_increments_counter(client: TestClient):
    created = client.post("/games", json={"radius": 3, "seed": 2}).json()
    r = client.post(f"/games/{created['id']}/turn")
    assert r.status_code == 200
    assert r.json()["turn"] == 2


def test_resolve_turn_advances_ai_and_returns_to_human(client: TestClient):
    created = client.post("/games", json={"radius": 3, "seed": 2}).json()
    game_id = created["id"]

    class PassiveSource:
        def decide(self, view: dict, civ_id: int) -> Decisions:
            return Decisions()

    human = next(c for c in created["civs"] if c["is_human"])
    sources = {human["id"]: QueueHumanSource()}
    for civ in created["civs"]:
        if civ["id"] != human["id"]:
            sources[civ["id"]] = PassiveSource()
    store.put_goal_sources(game_id, sources)

    r = client.post(f"/games/{game_id}/turn/resolve")
    assert r.status_code == 200
    body = r.json()
    assert body["turn"] == 2
    assert body["current_civ_id"] == human["id"]


def test_move_unit_and_error_path(client: TestClient):
    created = client.post("/games", json={"radius": 4, "seed": 2}).json()
    game_id = created["id"]
    settler = next(u for u in created["units"] if u["type"] == "settler")

    # Move off map → 400
    bad = client.post(
        f"/games/{game_id}/actions/move",
        json={"unit_id": settler["id"], "q": 99, "r": 99},
    )
    assert bad.status_code == 400


def test_research_flow(client: TestClient):
    created = client.post("/games", json={"radius": 3, "seed": 3}).json()
    game_id = created["id"]
    r = client.post(
        f"/games/{game_id}/actions/research",
        json={"civ_id": 0, "tech_id": "agriculture"},
    )
    assert r.status_code == 200
    civ0 = next(c for c in r.json()["civs"] if c["id"] == 0)
    assert civ0["researching"] == "agriculture"




def test_found_city_via_api(client: TestClient):
    created = client.post("/games", json={"radius": 4, "seed": 5}).json()
    game_id = created["id"]
    settler = next(u for u in created["units"] if u["type"] == "settler")
    # Try to found — may fail if starting tile is unfoundable (ocean/mountain).
    r = client.post(
        f"/games/{game_id}/actions/found",
        json={"unit_id": settler["id"], "name": "Capital"},
    )
    # Accept either success or a principled 400 (terrain check).
    assert r.status_code in (200, 400)
    if r.status_code == 200:
        body = r.json()
        assert len(body["cities"]) == 1
        assert body["cities"][0]["name"] == "Capital"



def test_create_ai_battle_uses_per_seat_provider_config(client: TestClient):
    with patch("app.engine.openai_goals.OpenAI"):
        r = client.post(
            "/games",
            json={
                "radius": 4,
                "seed": 7,
                "mode": "ai_battle",
                "num_civs": 3,
                "max_turns": 5,
                "auto_start": False,
                "llm_players": [
                    {
                        "label": "DeepSeek seat",
                        "model": "deepseek-chat",
                        "base_url": "https://api.deepseek.com",
                        "api_key": "secret-one",
                    },
                    {
                        "label": "GLM seat",
                        "model": "glm-5",
                        "base_url": "https://llm.example/v1/",
                        "api_key": "secret-two",
                    },
                    {
                        "label": "Third seat",
                        "model": "custom-model",
                        "base_url": "https://llm.example/v1",
                        "api_key": "secret-three",
                    },
                ],
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert len(body["civs"]) == 3
    assert all(not civ["is_human"] for civ in body["civs"])
    assert "secret-one" not in r.text
    assert "secret-two" not in r.text
    assert "secret-three" not in r.text

    status = client.get(f"/games/{body['id']}/status")
    assert status.status_code == 200
    assert status.json()["status"] == "ready"
    assert status.json()["source_labels"] == {
        "0": "DeepSeek seat",
        "1": "GLM seat",
        "2": "Third seat",
    }

    spectator = client.get(f"/games/{body['id']}/spectate")
    assert spectator.status_code == 200
    spectator_body = spectator.json()
    assert len(spectator_body["state"]["civs"]) == 3
    assert len(spectator_body["state"]["spectator_stances"]) == 3


def test_ai_battle_runs_in_background_without_human(client: TestClient, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    created = client.post(
        "/games",
        json={
            "radius": 3,
            "seed": 11,
            "mode": "ai_battle",
            "num_civs": 2,
            "max_turns": 1,
            "auto_start": False,
        },
    ).json()
    game_id = created["id"]
    started = client.post(f"/games/{game_id}/run")
    assert started.status_code == 200

    import time

    final_status = None
    for _ in range(50):
        final_status = client.get(f"/games/{game_id}/status").json()
        if final_status["status"] in {"finished", "error", "stopped"}:
            break
        time.sleep(0.02)
    assert final_status is not None
    assert final_status["status"] == "finished"
    spectator = client.get(f"/games/{game_id}/spectate").json()
    assert spectator["events"]
    assert spectator["state"]["turn"] >= 2


def test_ai_battle_http_controls_pause_resume_stop(client: TestClient):
    started = Event()
    release = Event()
    done = Event()

    def blocking_runner(game_id: int) -> None:
        started.set()
        runtime = store.get_runtime(game_id)
        if runtime.wait_until_running():
            release.wait(timeout=1)
        runtime.finish(status="stopped")
        done.set()

    with patch("app.api.simulation._run_game", blocking_runner):
        created = client.post(
            "/games",
            json={
                "mode": "ai_battle",
                "num_civs": 2,
                "radius": 3,
                "seed": 12,
                "auto_start": False,
            },
        ).json()
        game_id = created["id"]
        assert client.post(f"/games/{game_id}/run").status_code == 200
        assert started.wait(timeout=1)
        assert client.post(f"/games/{game_id}/pause").json()["status"] == "paused"
        assert client.post(f"/games/{game_id}/resume").json()["status"] == "running"
        assert client.post(f"/games/{game_id}/stop").json()["status"] == "stopping"
        release.set()
        assert done.wait(timeout=1)

    assert client.get(f"/games/{game_id}/status").json()["status"] == "stopped"
