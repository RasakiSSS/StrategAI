"""Background runner for all-AI games."""

from __future__ import annotations

import logging

from app.api.store import GameRuntime, store
from app.engine.playthrough import (
    _advance_civ,
    _execute_current_civ_turn,
)
from app.engine.victory import check_victory

logger = logging.getLogger(__name__)


def source_labels(goal_sources: object) -> dict[int, str]:
    """Return safe per-civ labels without exposing provider credentials."""
    if not isinstance(goal_sources, dict):
        return {}
    labels: dict[int, str] = {}
    for civ_id, source in goal_sources.items():
        label = getattr(source, "public_label", None)
        labels[civ_id] = str(label or type(source).__name__)
    return labels


def start_game(game_id: int) -> bool:
    runtime = store.get_runtime(game_id)
    return runtime.start(lambda: _run_game(game_id))


def pause_game(game_id: int) -> bool:
    return store.get_runtime(game_id).pause()


def resume_game(game_id: int) -> bool:
    return store.get_runtime(game_id).resume()


def stop_game(game_id: int) -> bool:
    return store.get_runtime(game_id).stop()


def _run_game(game_id: int) -> None:
    runtime = store.get_runtime(game_id)
    feedback_by_civ: dict[int, list[str]] = {}
    try:
        state = store.get(game_id)
        goal_sources = store.get_goal_sources(game_id)
        runtime.add_event(
            kind="game_started",
            turn=state.turn,
            message="AI battle started",
        )

        while True:
            if not runtime.wait_until_running():
                runtime.add_event(
                    kind="game_stopped",
                    turn=state.turn,
                    message="AI battle stopped",
                )
                runtime.finish(status="stopped")
                return

            state = store.get(game_id)
            victory = check_victory(state)
            if victory is not None:
                runtime.add_event(
                    kind="victory",
                    turn=state.turn,
                    civ_id=victory.winner_id,
                    civ_name=next(
                        (civ.name for civ in state.civs if civ.id == victory.winner_id),
                        None,
                    ),
                    message=f"Victory by civ {victory.winner_id} ({victory.kind.value})",
                )
                runtime.finish(
                    status="finished",
                    winner_civ_id=victory.winner_id,
                    victory_kind=victory.kind.value,
                )
                return
            if state.turn > runtime.max_turns:
                runtime.add_event(
                    kind="turn_limit",
                    turn=state.turn,
                    message="Maximum turn limit reached",
                )
                runtime.finish(status="finished")
                return
            if not state.civs:
                runtime.finish(status="finished")
                return

            civ = state.current_civ()
            source = goal_sources[civ.id] if isinstance(goal_sources, dict) else goal_sources
            source_label = getattr(source, "public_label", type(source).__name__)
            runtime.add_event(
                kind="civ_turn_started",
                turn=state.turn,
                civ_id=civ.id,
                civ_name=civ.name,
                source_label=str(source_label),
                message=f"{civ.name} is deciding its turn",
            )

            state, applied, rejected = _execute_current_civ_turn(
                state,
                goal_sources,
                feedback_by_civ,
            )
            provider_error = getattr(source, "last_error", None)
            if provider_error:
                runtime.add_event(
                    kind="llm_error",
                    turn=state.turn,
                    civ_id=civ.id,
                    civ_name=civ.name,
                    source_label=str(source_label),
                    message=str(provider_error),
                )
            store.put(game_id, state)
            runtime.add_event(
                kind="civ_turn_completed",
                turn=state.turn,
                civ_id=civ.id,
                civ_name=civ.name,
                source_label=str(source_label),
                message=f"{civ.name} completed a turn ({applied} applied, {rejected} rejected)",
            )

            previous_turn = state.turn
            state = _advance_civ(state)
            store.put(game_id, state)
            if state.turn != previous_turn:
                runtime.add_event(
                    kind="turn_completed",
                    turn=state.turn,
                    message=f"Turn {previous_turn} completed",
                )
    except Exception as exc:  # pragma: no cover - defensive worker boundary
        logger.exception("AI battle %d failed", game_id)
        runtime.add_event(
            kind="game_error",
            turn=store.get(game_id).turn if _game_exists(game_id) else 0,
            message="AI battle failed",
        )
        runtime.finish(status="error", error=str(exc))


def _game_exists(game_id: int) -> bool:
    try:
        store.get(game_id)
    except KeyError:
        return False
    return True
