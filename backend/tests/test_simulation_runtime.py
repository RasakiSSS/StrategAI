from __future__ import annotations

from threading import Event

from app.api.game_factory import new_game
from app.api.store import GameRuntime


def test_runtime_pause_resume_and_stop() -> None:
    runtime = GameRuntime(1, mode="ai_battle", max_turns=10, source_labels={0: "seat"})
    entered = Event()
    release = Event()
    done = Event()

    def worker() -> None:
        entered.set()
        if runtime.wait_until_running():
            release.wait(timeout=1)
        runtime.finish(status="stopped")
        done.set()

    assert runtime.start(worker)
    assert entered.wait(timeout=1)
    assert runtime.pause()
    assert runtime.status == "paused"
    assert runtime.resume()
    assert runtime.status == "running"
    assert runtime.stop()
    assert runtime.status == "stopping"
    release.set()
    assert done.wait(timeout=1)
    assert runtime.status == "stopped"
    assert not runtime.stop()

    ready = GameRuntime(3, mode="ai_battle", max_turns=1)
    assert ready.stop()
    assert ready.status == "stopped"
    assert not ready.stop()


def test_runtime_event_cursor_and_status_exposes_safe_labels() -> None:
    runtime = GameRuntime(
        2,
        mode="ai_battle",
        max_turns=3,
        source_labels={0: "private-model-label"},
    )
    runtime.add_event(
        kind="game_started",
        turn=1,
        message="started",
        civ_id=0,
        source_label="private-model-label",
    )
    runtime.add_event(kind="turn_completed", turn=2, message="done")

    events = runtime.events_since(1)
    assert [event["id"] for event in events] == [2]
    snapshot = runtime.status_snapshot(new_game(radius=3, seed=1, num_civs=2, include_human=False))
    assert snapshot["source_labels"] == {"0": "private-model-label"}
    assert "api_key" not in snapshot
