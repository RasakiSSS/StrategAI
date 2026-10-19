"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { api, LLMPlayerConfigInput } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type SeatConfig = LLMPlayerConfigInput & { id: number };

const DEFAULT_SEATS: SeatConfig[] = [
  {
    id: 0,
    label: "DeepSeek",
    model: "deepseek-flash",
    base_url: "https://api.deepseek.com",
    api_key: "",
  },
  {
    id: 1,
    label: "GLM",
    model: "glm-5.3",
    base_url: "https://api.muzeai.top/v1/",
    api_key: "",
  },
  {
    id: 2,
    label: "Luna",
    model: "gpt-6-luna",
    base_url: "https://ai.yuhuantin.icu/v1",
    api_key: "",
  },
  {
    id: 3,
    label: "Codex auto-review",
    model: "codex-auto-review",
    base_url: "https://ai.yuhuantin.icu/v1",
    api_key: "",
  },
];

function randomSeed(): number {
  const values = new Uint32Array(1);
  window.crypto.getRandomValues(values);
  return values[0] % 1_000_000_000;
}

export default function NewSpectatorBattlePage() {
  const router = useRouter();
  const { t } = useI18n();
  const [seatCount, setSeatCount] = useState(3);
  const [maxTurns, setMaxTurns] = useState(50);
  const [seats, setSeats] = useState<SeatConfig[]>(DEFAULT_SEATS);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const visibleSeats = useMemo(() => seats.slice(0, seatCount), [seatCount, seats]);

  const updateSeat = (index: number, field: keyof SeatConfig, value: string) => {
    setSeats((current) =>
      current.map((seat, seatIndex) =>
        seatIndex === index ? { ...seat, [field]: value } : seat,
      ),
    );
  };

  const launch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const llmPlayers = visibleSeats.map(({ id: _id, ...seat }) => {
        const config: LLMPlayerConfigInput = {
          model: seat.model?.trim(),
          base_url: seat.base_url?.trim(),
          api_key: seat.api_key?.trim() || undefined,
          label: seat.label?.trim() || undefined,
        };
        return config;
      });
      const created = await api.createGame(8, randomSeed(), "Spectator", {
        mode: "ai_battle",
        num_civs: seatCount,
        max_turns: Math.max(1, Math.min(1000, maxTurns)),
        llm_players: llmPlayers,
        auto_start: true,
      });
      router.push(`/spectate/${created.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(false);
    }
  };

  return (
    <main className="spectator-setup">
      <section className="spectator-setup__panel">
        <div className="plate-label">{t("spectator.setup")}</div>
        <h1>{t("spectator.title")}</h1>
        <p className="spectator-setup__subtitle">{t("spectator.subtitle")}</p>

        <form onSubmit={launch}>
          <div className="spectator-setup__controls">
            <label className="field">
              <span className="field-label">{t("spectator.civCount")}</span>
              <select
                value={seatCount}
                onChange={(event) => setSeatCount(Number(event.target.value))}
                disabled={busy}
              >
                {[2, 3, 4].map((count) => (
                  <option key={count} value={count}>
                    {count}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">{t("spectator.maxTurns")}</span>
              <input
                type="number"
                min={1}
                max={1000}
                value={maxTurns}
                onChange={(event) => setMaxTurns(Number(event.target.value) || 1)}
                disabled={busy}
              />
            </label>
          </div>

          <div className="spectator-seat-list">
            {visibleSeats.map((seat, index) => (
              <fieldset className="spectator-seat" key={seat.id}>
                <legend>{t("spectator.civConfig", { index: index + 1 })}</legend>
                <div className="spectator-seat__grid">
                  <label className="field">
                    <span className="field-label">{t("spectator.label")}</span>
                    <input
                      type="text"
                      value={seat.label ?? ""}
                      onChange={(event) => updateSeat(index, "label", event.target.value)}
                      disabled={busy}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">{t("spectator.model")}</span>
                    <input
                      type="text"
                      required
                      value={seat.model ?? ""}
                      onChange={(event) => updateSeat(index, "model", event.target.value)}
                      disabled={busy}
                    />
                  </label>
                  <label className="field spectator-seat__wide">
                    <span className="field-label">{t("spectator.baseUrl")}</span>
                    <input
                      type="url"
                      required
                      value={seat.base_url ?? ""}
                      onChange={(event) => updateSeat(index, "base_url", event.target.value)}
                      disabled={busy}
                    />
                  </label>
                  <label className="field spectator-seat__wide">
                    <span className="field-label">{t("spectator.apiKey")}</span>
                    <input
                      type="password"
                      value={seat.api_key ?? ""}
                      onChange={(event) => updateSeat(index, "api_key", event.target.value)}
                      autoComplete="off"
                      disabled={busy}
                    />
                  </label>
                </div>
              </fieldset>
            ))}
          </div>

          <p className="spectator-setup__hint">{t("spectator.apiKeyHint")}</p>
          {error && <p className="spectator-error">{error}</p>}
          <div className="spectator-setup__actions">
            <a className="button-secondary" href="/">
              {t("spectator.backToGame")}
            </a>
            <button className="button-primary" type="submit" disabled={busy}>
              {busy ? t("spectator.loading") : t("spectator.create")}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
