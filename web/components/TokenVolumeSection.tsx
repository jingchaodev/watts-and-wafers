import fs from "node:fs";
import path from "node:path";
import TokenVolume from "./TokenVolume";

type TokenDay = { date: string; total_b_tokens: number; top_models?: { slug: string; b_tokens: number }[] };

function loadTokenDays(): TokenDay[] {
  try {
    const p = path.join(process.cwd(), "..", "data", "history", "openrouter_tokens.jsonl");
    return fs
      .readFileSync(p, "utf8")
      .split("\n")
      .filter(Boolean)
      .map((l) => {
        try {
          return JSON.parse(l) as TokenDay;
        } catch {
          return null;
        }
      })
      .filter((x): x is TokenDay => x !== null && typeof x.total_b_tokens === "number")
      .sort((a, b) => a.date.localeCompare(b.date));
  } catch {
    return [];
  }
}

export default function TokenVolumeSection() {
  const days = loadTokenDays();
  if (days.length < 10) return null;
  const latest = days[days.length - 1];
  const d30 = days[Math.max(0, days.length - 31)];
  const growth30 = d30.total_b_tokens > 0 ? ((latest.total_b_tokens / d30.total_b_tokens - 1) * 100).toFixed(0) : null;
  const points: [string, number][] = days.map((d) => [`${d.date}T00:00:00Z`, d.total_b_tokens]);

  return (
    <section className="block" id="token-volume">
      <h2 className="section-title">Token consumption</h2>
      <p className="section-sub">
        Daily tokens routed through OpenRouter, all models — the most direct public read on AI
        inference demand. Latest: {(latest.total_b_tokens / 1000).toFixed(2)}T tokens/day
        {growth30 ? ` (${growth30 !== "0" && !growth30.startsWith("-") ? "+" : ""}${growth30}% vs 30d ago)` : ""}.
      </p>
      <div className="card">
        <TokenVolume points={points} />
        <p style={{ fontSize: 11, color: "#87867F", fontFamily: "ui-monospace, monospace", marginTop: 6 }}>
          Log scale — a straight line means constant growth rate; flattening = deceleration. Source:
          OpenRouter official rankings-daily dataset (API, history since 2025-01), updated daily.
          OpenRouter is one router among many, so treat levels as a sample and the trend as the signal.
        </p>
      </div>
    </section>
  );
}
