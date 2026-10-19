export type TileDTO = {
  q: number;
  r: number;
  terrain: string;
  resource: string | null;
  feature: string | null;
  river: boolean;
  improvement: string | null;
  food: number;
  production: number;
  gold: number;
};
export type WorkOrderDTO = {
  q: number;
  r: number;
  improvement: string;
  turns_remaining: number;
};
export type UnitDTO = {
  id: number;
  owner: number;
  type: string;
  q: number;
  r: number;
  health: number;
  moves_remaining: number;
  work_order: WorkOrderDTO | null;
};
export type WorkedTileDTO = { q: number; r: number };
export type CityDTO = {
  id: number;
  owner: number;
  name: string;
  q: number;
  r: number;
  population: number;
  food_stored: number;
  production_stored: number;
  health: number;
  max_health: number;
  is_capital: boolean;
  buildings: string[];
  production_queue: string[];
  border_radius: number;
  culture_stored: number;
  worked_tiles: WorkedTileDTO[];
  purchased_structures: string[];
};
export type CityStructureDTO = {
  city_id: number;
  owner: number;
  category: string;
  q: number;
  r: number;
};
export type CivDTO = {
  id: number;
  name: string;
  leader_name: string;
  is_human: boolean;
  gold: number;
  gold_income: number;
  gold_upkeep: number;
  science: number;
  culture: number;
  known_techs: string[];
  researching: string | null;
  score: number;
};
export type TileOwnerDTO = {
  q: number;
  r: number;
  city_id: number;
};
export type MessageDTO = {
  from_civ_id: number;
  to_civ_id: number;
  turn: number;
  kind: string;
  text: string;
};
export type StanceDTO = {
  other_civ_id: number;
  stance: string;
  relationship: number;
  truce_active: boolean;
  truce_until: number | null;
};

export type StancePairDTO = {
  civ_a_id: number;
  civ_b_id: number;
  stance: string;
  relationship: number;
  truce_active: boolean;
  truce_until: number | null;
};

export type DiplomaticEventDTO = {
  turn: number;
  kind: string;
  actor_civ_id: number;
  target_civ_id: number;
  summary: string;
  relationship_delta: number;
};

export type StandingDTO = {
  civ_id: number;
  name: string;
  score: number;
};
export type CivRosterEntryDTO = {
  id: number;
  name: string;
  leader_name: string;
  is_human: boolean;
};
export type GameStateDTO = {
  id: number;
  turn: number;
  current_civ_id: number;
  map_radius: number;
  tiles: TileDTO[];
  civs: CivDTO[];
  // Full civ identity list (every civ in the game, fog-of-war-independent).
  // Used by the asset resolver to pre-generate art for civs not yet met.
  civ_roster: CivRosterEntryDTO[];
  cities: CityDTO[];
  structures: CityStructureDTO[];
  units: UnitDTO[];
  known_civ_ids: number[];
  messages: MessageDTO[];
  inbox: MessageDTO[];
  stances: StanceDTO[];
  visible_tile_keys: string[];
  tile_owner: TileOwnerDTO[];
  diplomatic_events: DiplomaticEventDTO[];
  standings: StandingDTO[];
  score_threshold: number;
  spectator_stances: StancePairDTO[];
};

export type SpectateStatusDTO = {
  game_id: number;
  mode: string;
  status: string;
  turn: number;
  current_civ_id: number | null;
  max_turns: number;
  winner_civ_id: number | null;
  victory_kind: string | null;
  error: string | null;
  source_labels: Record<string, string>;
  last_event_id: number;
};

export type SpectatorEventDTO = {
  id: number;
  kind: string;
  turn: number;
  civ_id: number | null;
  civ_name: string | null;
  source_label: string | null;
  message: string;
  created_at: string;
};

export type SpectateResponseDTO = {
  state: GameStateDTO;
  status: SpectateStatusDTO;
  events: SpectatorEventDTO[];
};

export type LLMPlayerConfigInput = {
  model?: string;
  base_url?: string;
  api_key?: string;
  temperature?: number;
  label?: string;
};

export type CreateGameOptions = {
  mode?: "human" | "ai_battle";
  num_civs?: number;
  max_turns?: number;
  llm_players?: LLMPlayerConfigInput[];
  auto_start?: boolean;
};
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return (await res.json()) as T;
}

async function reqBlob(path: string, init?: RequestInit): Promise<Blob> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return await res.blob();
}

export const api = {
  createGame: (
    radius = 5,
    seed = 0,
    human_name = "Athens",
    options: CreateGameOptions = {},
  ) =>
    req<GameStateDTO>("/games", {
      method: "POST",
      body: JSON.stringify({ radius, seed, human_name, ...options }),
    }),
  getGame: (id: number) => req<GameStateDTO>(`/games/${id}`),
  getSpectate: (id: number, since?: number) => {
    const query = since !== undefined ? `?since=${encodeURIComponent(since)}` : "";
    return req<SpectateResponseDTO>(`/games/${id}/spectate${query}`);
  },
  getSpectateStatus: (id: number) =>
    req<SpectateStatusDTO>(`/games/${id}/status`),
  runGame: (id: number) =>
    req<SpectateStatusDTO>(`/games/${id}/run`, { method: "POST" }),
  pauseGame: (id: number) =>
    req<SpectateStatusDTO>(`/games/${id}/pause`, { method: "POST" }),
  resumeGame: (id: number) =>
    req<SpectateStatusDTO>(`/games/${id}/resume`, { method: "POST" }),
  stopGame: (id: number) =>
    req<SpectateStatusDTO>(`/games/${id}/stop`, { method: "POST" }),
  endTurn: (id: number) =>
    req<GameStateDTO>(`/games/${id}/turn`, { method: "POST" }),
  resolveTurn: (id: number) =>
    req<GameStateDTO>(`/games/${id}/turn/resolve`, { method: "POST" }),
  move: (id: number, unit_id: number, q: number, r: number) =>
    req<GameStateDTO>(`/games/${id}/actions/move`, {
      method: "POST",
      body: JSON.stringify({ unit_id, q, r }),
    }),
  attack: (id: number, attacker_id: number, defender_id: number) =>
    req<GameStateDTO>(`/games/${id}/actions/attack`, {
      method: "POST",
      body: JSON.stringify({ attacker_id, defender_id }),
    }),
  foundCity: (id: number, unit_id: number, name: string) =>
    req<GameStateDTO>(`/games/${id}/actions/found`, {
      method: "POST",
      body: JSON.stringify({ unit_id, name }),
    }),
  research: (id: number, civ_id: number, tech_id: string) =>
    req<GameStateDTO>(`/games/${id}/actions/research`, {
      method: "POST",
      body: JSON.stringify({ civ_id, tech_id }),
    }),
  build: (id: number, civ_id: number, city_id: number, unit_type: string) =>
    req<GameStateDTO>(`/games/${id}/actions/build`, {
      method: "POST",
      body: JSON.stringify({ civ_id, city_id, unit_type }),
    }),
  cancelBuild: (id: number, civ_id: number, city_id: number, index: number) =>
    req<GameStateDTO>(`/games/${id}/actions/cancel-build`, {
      method: "POST",
      body: JSON.stringify({ civ_id, city_id, index }),
    }),
  purchaseStructure: (
    id: number,
    civ_id: number,
    city_id: number,
    category: string,
    q: number,
    r: number,
  ) =>
    req<GameStateDTO>(`/games/${id}/actions/purchase-structure`, {
      method: "POST",
      body: JSON.stringify({ civ_id, city_id, category, q, r }),
    }),
  improve: (id: number, unit_id: number, improvement: string) =>
    req<GameStateDTO>(`/games/${id}/actions/improve`, {
      method: "POST",
      body: JSON.stringify({ unit_id, improvement }),
    }),
  sendMessage: (
    id: number,
    from_civ_id: number,
    to_civ_id: number,
    kind: string,
    text: string,
  ) =>
    req<GameStateDTO>(`/games/${id}/actions/message`, {
      method: "POST",
      body: JSON.stringify({ from_civ_id, to_civ_id, kind, text }),
    }),
  generateIntroNarration: (text: string) =>
    reqBlob("/audio/intro", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
};
