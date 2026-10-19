"""In-memory game and simulation store.

The game state remains immutable at the engine boundary. Runtime metadata is
mutable and protected by a condition so a background AI runner can coordinate
with pause/resume/stop requests without leaking credentials into GameState.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import itertools
import threading
from typing import Callable, Iterator

from app.engine.models import GameState


class GameRuntime:
    """Thread-safe lifecycle and event metadata for one game."""

    def __init__(
        self,
        game_id: int,
        *,
        mode: str,
        max_turns: int,
        source_labels: dict[int, str] | None = None,
    ) -> None:
        self.game_id = game_id
        self.mode = mode
        self.max_turns = max_turns
        self.source_labels = dict(source_labels or {})
        self.status = "ready"
        self.error: str | None = None
        self.winner_civ_id: int | None = None
        self.victory_kind: str | None = None
        self._stop_requested = False
        self._events: deque[dict[str, object]] = deque(maxlen=300)
        self._next_event_id = 1
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None

    def start(self, target: Callable[[], None]) -> bool:
        """Start the runner once. Return false if it is already active/finished."""
        with self._condition:
            if self.status == "paused":
                self.status = "running"
                self._condition.notify_all()
                return False
            if self.status != "ready":
                return False
            self.status = "running"
            self._thread = threading.Thread(
                target=target,
                name=f"strategai-game-{self.game_id}",
                daemon=True,
            )
            thread = self._thread
        thread.start()
        return True

    def pause(self) -> bool:
        with self._condition:
            if self.status != "running":
                return False
            self.status = "paused"
            return True

    def resume(self) -> bool:
        with self._condition:
            if self.status != "paused":
                return False
            self.status = "running"
            self._condition.notify_all()
            return True

    def stop(self) -> bool:
        with self._condition:
            if self.status in {"finished", "stopped", "error"}:
                return False
            self._stop_requested = True
            if self.status == "ready":
                self.status = "stopped"
            else:
                self.status = "stopping"
            self._condition.notify_all()
            return True

    def wait_until_running(self) -> bool:
        """Block while paused; return false when the runner should stop."""
        with self._condition:
            while self.status == "paused" and not self._stop_requested:
                self._condition.wait()
            return self.status == "running" and not self._stop_requested

    @property
    def stop_requested(self) -> bool:
        with self._condition:
            return self._stop_requested

    def add_event(
        self,
        *,
        kind: str,
        turn: int,
        message: str,
        civ_id: int | None = None,
        civ_name: str | None = None,
        source_label: str | None = None,
    ) -> None:
        with self._condition:
            self._events.append(
                {
                    "id": self._next_event_id,
                    "kind": kind,
                    "turn": turn,
                    "civ_id": civ_id,
                    "civ_name": civ_name,
                    "source_label": source_label,
                    "message": message,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            self._next_event_id += 1

    def events_since(self, event_id: int = 0) -> list[dict[str, object]]:
        with self._condition:
            return [event for event in self._events if int(event["id"]) > event_id]

    def finish(
        self,
        *,
        status: str,
        winner_civ_id: int | None = None,
        victory_kind: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._condition:
            self.status = status
            self.winner_civ_id = winner_civ_id
            self.victory_kind = victory_kind
            self.error = error
            self._condition.notify_all()

    def status_snapshot(self, state: GameState) -> dict[str, object]:
        with self._condition:
            return {
                "game_id": self.game_id,
                "mode": self.mode,
                "status": self.status,
                "turn": state.turn,
                "current_civ_id": state.current_civ().id if state.civs else None,
                "max_turns": self.max_turns,
                "winner_civ_id": self.winner_civ_id,
                "victory_kind": self.victory_kind,
                "error": self.error,
                "source_labels": {str(k): v for k, v in self.source_labels.items()},
                "last_event_id": self._next_event_id - 1,
            }


class GameStore:
    def __init__(self) -> None:
        self._games: dict[int, GameState] = {}
        self._goal_sources: dict[int, object] = {}
        self._runtimes: dict[int, GameRuntime] = {}
        self._lock = threading.Lock()
        self._ids: Iterator[int] = itertools.count(1)

    def create(self, state: GameState) -> int:
        with self._lock:
            game_id = next(self._ids)
            self._games[game_id] = state
            return game_id

    def get(self, game_id: int) -> GameState:
        with self._lock:
            if game_id not in self._games:
                raise KeyError(game_id)
            return self._games[game_id]

    def put(self, game_id: int, state: GameState) -> None:
        with self._lock:
            if game_id not in self._games:
                raise KeyError(game_id)
            self._games[game_id] = state

    def put_goal_sources(self, game_id: int, goal_sources: object) -> None:
        with self._lock:
            if game_id not in self._games:
                raise KeyError(game_id)
            self._goal_sources[game_id] = goal_sources

    def get_goal_sources(self, game_id: int) -> object:
        with self._lock:
            if game_id not in self._goal_sources:
                raise KeyError(game_id)
            return self._goal_sources[game_id]

    def put_runtime(self, game_id: int, runtime: GameRuntime) -> None:
        with self._lock:
            if game_id not in self._games:
                raise KeyError(game_id)
            self._runtimes[game_id] = runtime

    def get_runtime(self, game_id: int) -> GameRuntime:
        with self._lock:
            if game_id not in self._runtimes:
                raise KeyError(game_id)
            return self._runtimes[game_id]

    def clear(self) -> None:
        with self._lock:
            runtimes = list(self._runtimes.values())
            self._games.clear()
            self._goal_sources.clear()
            self._runtimes.clear()
            self._ids = itertools.count(1)
        for runtime in runtimes:
            runtime.stop()


store = GameStore()
