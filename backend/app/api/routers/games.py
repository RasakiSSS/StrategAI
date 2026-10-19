from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.game_factory import build_goal_sources, new_game
from app.api.schemas import (
    CreateGameRequest,
    GameStateOut,
    GameStatusOut,
    SimulationEventOut,
    SpectatorResponse,
    state_to_out,
    state_to_spectator_out,
)
from app.api.simulation import (
    pause_game,
    resume_game,
    source_labels,
    start_game,
    stop_game,
)
from app.api.store import GameRuntime, store
from app.engine.llm_config import LLMPlayerConfig

router = APIRouter(prefix="/games", tags=["games"])


def _status(game_id: int) -> GameStatusOut:
    try:
        state = store.get(game_id)
        runtime = store.get_runtime(game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="game not found")
    return GameStatusOut(**runtime.status_snapshot(state))


def _llm_configs(req: CreateGameRequest, state) -> dict[int, LLMPlayerConfig]:
    ai_civs = [civ for civ in state.civs if not civ.is_human]
    if len(req.llm_players) > len(ai_civs):
        raise HTTPException(
            status_code=422,
            detail=f"received {len(req.llm_players)} LLM players for {len(ai_civs)} AI civs",
        )

    configs: dict[int, LLMPlayerConfig] = {}
    for civ, config in zip(ai_civs, req.llm_players):
        try:
            configs[civ.id] = LLMPlayerConfig(
                model=config.model,
                base_url=config.base_url,
                api_key=(
                    config.api_key.get_secret_value()
                    if config.api_key is not None
                    else None
                ),
                temperature=config.temperature,
                label=config.label,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return configs


@router.post("", response_model=GameStateOut)
def create_game(req: CreateGameRequest) -> GameStateOut:
    state = new_game(
        radius=req.radius,
        seed=req.seed,
        num_civs=req.num_civs,
        include_human=req.mode == "human",
        human_name=req.human_name,
    )
    llm_configs = _llm_configs(req, state)
    goal_sources = build_goal_sources(state, llm_configs)
    game_id = store.create(state)
    store.put_goal_sources(game_id, goal_sources)
    store.put_runtime(
        game_id,
        GameRuntime(
            game_id,
            mode=req.mode,
            max_turns=req.max_turns,
            source_labels=source_labels(goal_sources),
        ),
    )
    if req.mode == "ai_battle" and req.auto_start:
        start_game(game_id)
    return state_to_out(game_id, state)


@router.get("/{game_id}", response_model=GameStateOut)
def get_game(game_id: int) -> GameStateOut:
    try:
        state = store.get(game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="game not found")
    return state_to_out(game_id, state)


@router.get("/{game_id}/status", response_model=GameStatusOut)
def get_game_status(game_id: int) -> GameStatusOut:
    return _status(game_id)


@router.get("/{game_id}/spectate", response_model=SpectatorResponse)
def spectate_game(
    game_id: int,
    since: int = 0,
) -> SpectatorResponse:
    try:
        state = store.get(game_id)
        runtime = store.get_runtime(game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="game not found")
    return SpectatorResponse(
        state=state_to_spectator_out(game_id, state),
        status=GameStatusOut(**runtime.status_snapshot(state)),
        events=[SimulationEventOut(**event) for event in runtime.events_since(since)],
    )


@router.post("/{game_id}/run", response_model=GameStatusOut)
def run_game(game_id: int) -> GameStatusOut:
    try:
        runtime = store.get_runtime(game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="game not found")
    if runtime.mode != "ai_battle":
        raise HTTPException(status_code=400, detail="only AI battle games can be run")
    start_game(game_id)
    return _status(game_id)


@router.post("/{game_id}/pause", response_model=GameStatusOut)
def pause_ai_game(game_id: int) -> GameStatusOut:
    try:
        runtime = store.get_runtime(game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="game not found")
    if runtime.mode != "ai_battle":
        raise HTTPException(status_code=400, detail="only AI battle games can be paused")
    if not pause_game(game_id):
        raise HTTPException(status_code=409, detail="game is not running")
    return _status(game_id)


@router.post("/{game_id}/resume", response_model=GameStatusOut)
def resume_ai_game(game_id: int) -> GameStatusOut:
    try:
        runtime = store.get_runtime(game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="game not found")
    if runtime.mode != "ai_battle":
        raise HTTPException(status_code=400, detail="only AI battle games can be resumed")
    if not resume_game(game_id):
        raise HTTPException(status_code=409, detail="game is not paused")
    return _status(game_id)


@router.post("/{game_id}/stop", response_model=GameStatusOut)
def stop_ai_game(game_id: int) -> GameStatusOut:
    try:
        runtime = store.get_runtime(game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="game not found")
    if runtime.mode != "ai_battle":
        raise HTTPException(status_code=400, detail="only AI battle games can be stopped")
    stop_game(game_id)
    return _status(game_id)
