"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";

import { SquareMap } from "@/components/SquareMap";
import {
  api,
  SpectateResponseDTO,
  SpectateStatusDTO,
  SpectatorEventDTO,
} from "@/lib/api";
import { tileKey } from "@/lib/hex";
import { TranslationKey, useI18n } from "@/lib/i18n";

const STATUS_KEYS: Record<string, TranslationKey> = {
  ready: "spectator.status.ready",
  running: "spectator.status.running",
  paused: "spectator.status.paused",
  stopping: "spectator.status.stopping",
  stopped: "spectator.status.stopped",
  finished: "spectator.status.finished",
  error: "spectator.status.error",
};

function statusKey(status: string): TranslationKey {
  return STATUS_KEYS[status] ?? "spectator.status.error";
}

function eventTime(event: SpectatorEventDTO): string {
  const date = new Date(event.created_at);
  if (Number.isNaN(date.valueOf())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function SpectatorPage() {
  const params = useParams<{ gameId: string }>();
  const { t } = useI18n();
  const gameId = Number(params?.gameId);
  const [snapshot, setSnapshot] = useState<SpectateResponseDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [controlBusy, setControlBusy] = useState(false);
  const cursorRef = useRef(0);

  const poll = useCallback(async () => {
    if (!Number.isInteger(gameId) || gameId <= 0) {
      setError(t("spectator.invalidGame"));
      setLoading(false);
      return;
    }
    try {
      const next = await api.getSpectate(gameId, cursorRef.current);
      cursorRef.current = next.status.last_event_id;
      setSnapshot((current) => {
        if (!current) return next;
        const byId = new Map<number, SpectatorEventDTO>();
        for (const event of [...current.events, ...next.events]) byId.set(event.id, event);
        return {
          ...next,
          events: [...byId.values()].sort((a, b) => a.id - b.id).slice(-120),
        };
      });
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [gameId, t]);

  useEffect(() => {
    void poll();
    const timer = window.setInterval(() => void poll(), 1500);
    return () => window.clearInterval(timer);
  }, [poll]);

  const control = async (action: "run" | "pause" | "resume" | "stop") => {
    if (controlBusy || !Number.isInteger(gameId)) return;
    setControlBusy(true);
    try {
      const nextStatus: SpectateStatusDTO =
        action === "run"
          ? await api.runGame(gameId)
          : action === "pause"
            ? await api.pauseGame(gameId)
            : action === "resume"
              ? await api.resumeGame(gameId)
              : await api.stopGame(gameId);
      setSnapshot((current) => (current ? { ...current, status: nextStatus } : current));
      await poll();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setControlBusy(false);
    }
  };

  const state = snapshot?.state ?? null;
  const status = snapshot?.status ?? null;
  const visibleTiles = useMemo(
    () => new Set(state?.tiles.map((tile) => tileKey(tile.q, tile.r)) ?? []),
    [state],
  );
  const currentCiv = state?.civs.find((civ) => civ.id === state.current_civ_id) ?? null;
  const currentSource = currentCiv
    ? status?.source_labels[String(currentCiv.id)] ?? null
    : null;
  const sortedStandings = useMemo(
    () => [...(state?.standings ?? [])].sort((a, b) => a.score - b.score),
    [state],
  ).reverse();
  const events = snapshot?.events ?? [];

  if (loading && !snapshot) {
    return (
      <main className="spectator-page spectator-page--loading">
        <div className="spinner" />
        <p>{t("spectator.loading")}</p>
      </main>
    );
  }

  return (
    <main className="spectator-page">
      <header className="spectator-page__header">
        <div>
          <div className="plate-label">{t("spectator.title")}</div>
          <h1>{t("spectator.subtitle")}</h1>
        </div>
        <div className="spectator-page__header-actions">
          <a className="button-secondary" href="/spectate/new">
            {t("spectator.newBattle")}
          </a>
          <a className="button-secondary" href="/">
            {t("spectator.backToGame")}
          </a>
        </div>
      </header>

      {error && <div className="spectator-error">{error}</div>}
      {!state || !status ? (
        <section className="spectator-empty">
          <p>{error ?? t("spectator.connectionError")}</p>
        </section>
      ) : (
        <>
          <section className="spectator-page__toolbar">
            <div className={`spectator-status spectator-status--${status.status}`}>
              {t(statusKey(status.status))}
            </div>
            <div className="spectator-page__turn">
              {t("spectator.turn", { turn: state.turn, max: status.max_turns })}
            </div>
            <div className="spectator-page__actor">
              <span>{t("spectator.currentCiv")}</span>
              <strong>{currentCiv?.name ?? t("spectator.unknown")}</strong>
              {currentSource && <small>{currentSource}</small>}
            </div>
            <div className="spectator-page__controls">
              {status.status === "running" && (
                <button type="button" onClick={() => void control("pause")} disabled={controlBusy}>
                  {t("spectator.pause")}
                </button>
              )}
              {status.status === "paused" && (
                <button type="button" onClick={() => void control("resume")} disabled={controlBusy}>
                  {t("spectator.resume")}
                </button>
              )}
              {status.status === "ready" && (
                <button type="button" onClick={() => void control("run")} disabled={controlBusy}>
                  {t("spectator.resume")}
                </button>
              )}
              {!["finished", "stopped", "error"].includes(status.status) && (
                <button
                  className="button-danger"
                  type="button"
                  onClick={() => void control("stop")}
                  disabled={controlBusy}
                >
                  {t("spectator.stop")}
                </button>
              )}
            </div>
          </section>

          {status.victory_kind && (
            <div className="spectator-victory">
              {t("spectator.victory", { kind: status.victory_kind })}
            </div>
          )}
          {status.error && (
            <div className="spectator-error">
              {t("spectator.errorDetail", { error: status.error })}
            </div>
          )}

          <section className="spectator-page__layout">
            <section className="spectator-page__map">
              <SquareMap
                state={state}
                selectedUnitId={null}
                reachable={new Set()}
                focusHex={null}
                humanCivId={null}
                visibleTiles={visibleTiles}
                t={t}
              />
            </section>
            <aside className="spectator-page__rail">
              <section className="spectator-panel">
                <div className="panel__title">{t("spectator.standings")}</div>
                <div className="spectator-standings">
                  {sortedStandings.map((standing, index) => (
                    <div className="spectator-standing" key={standing.civ_id}>
                      <span>{index + 1}</span>
                      <strong>{standing.name}</strong>
                      <b>{standing.score}</b>
                    </div>
                  ))}
                </div>
              </section>
              <section className="spectator-panel spectator-panel--events">
                <div className="panel__title">{t("spectator.events")}</div>
                {events.length === 0 ? (
                  <p className="spectator-muted">{t("spectator.noEvents")}</p>
                ) : (
                  <div className="spectator-events">
                    {[...events].reverse().map((event) => (
                      <article className="spectator-event" key={event.id}>
                        <div className="spectator-event__meta">
                          <span>{t("spectator.turnShort", { turn: event.turn })}</span>
                          <time>{eventTime(event)}</time>
                        </div>
                        <strong>{event.civ_name ?? t("spectator.eventFallback")}</strong>
                        {event.source_label && <small>{event.source_label}</small>}
                        <p>{event.message}</p>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            </aside>
          </section>
        </>
      )}
    </main>
  );
}
