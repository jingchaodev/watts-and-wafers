"use client";

import type { SignalCard } from "@/lib/types";
import Sparkline from "./Sparkline";
import { directionArrow } from "@/lib/format";

// Where each card scrolls to when clicked. See DATA_CONTRACT ordering:
// h100_price, availability, spot_discount, gen_ratio, token_growth.
//   - h100_price -> the GPU price trend chart (id="gpu-price-trend")
//   - availability -> the GPU availability table (id="gpu-availability")
//   - spot_discount -> the multi-provider price comparison table, since it's
//     an Azure spot/on-demand RATIO and GpuPrice is the section that shows
//     Azure OD + spot side by side (id="gpu-price-comparison")
//   - gen_ratio -> also the price trend chart: it's a cross-generation
//     $/perf comparison and the trend chart is where GPU-class pricing over
//     time lives; GpuPrice doesn't carry a B200-vs-H100 perf angle so the
//     trend chart (where you can flip between GPU classes) is the better fit
//   - token_growth -> the token volume section (id="token-volume")
const ANCHORS: Record<string, string> = {
  h100_price: "gpu-price-trend",
  availability: "gpu-availability",
  spot_discount: "gpu-price-comparison",
  gen_ratio: "gpu-price-trend",
  token_growth: "token-volume",
};

const ARROW_CLASS: Record<string, string> = {
  up: "arrow-up",
  down: "arrow-down",
  flat: "arrow-flat",
};

function scrollToAnchor(id: string) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function SignalCardView({ card }: { card: SignalCard }) {
  const tone = card.tone ?? "neutral";
  const sparkValues = (card.spark ?? [])
    .map((p) => p[1])
    .filter((v): v is number => typeof v === "number");
  const sparkTone = tone === "hot" ? "clay" : tone === "cold" ? "muted" : "muted";
  const anchor = ANCHORS[card.key ?? ""] ?? "";

  return (
    <button
      type="button"
      className={`signal-card tone-${tone}`}
      onClick={() => anchor && scrollToAnchor(anchor)}
      aria-label={`Jump to ${card.title ?? card.key ?? "signal"} detail`}
    >
      <div className="signal-card-title">
        <span>{card.title ?? (card.key ?? "").replace(/_/g, " ")}</span>
        {card.percentile !== null && card.percentile !== undefined && (
          <span className="signal-percentile">
            P{Math.round(card.percentile)} · {card.window_days ?? "?"}d
          </span>
        )}
      </div>

      <div className="signal-card-value-row">
        <span className="signal-card-value">
          {card.value === null || card.value === undefined ? "—" : card.value_fmt ?? "—"}
        </span>
        <span className={`signal-card-delta ${ARROW_CLASS[card.direction ?? "flat"] ?? ""}`}>
          {directionArrow(card.direction)}
          {typeof card.delta_7d_pct === "number"
            ? ` ${card.delta_7d_pct > 0 ? "+" : ""}${card.delta_7d_pct.toFixed(1)}%`
            : ""}
        </span>
      </div>

      <p className="signal-card-read">{card.read ?? "—"}</p>

      <div className="signal-card-spark">
        <Sparkline values={sparkValues} width={110} height={28} tone={sparkTone} />
      </div>

      {card.provenance && <p className="signal-card-provenance">{card.provenance}</p>}
    </button>
  );
}

export default function SignalGrid({ cards }: { cards: SignalCard[] }) {
  if (!cards || cards.length === 0) return null;
  return (
    <section className="block" style={{ marginBottom: 24 }}>
      <div className="signal-grid">
        {cards.map((c, i) => (
          <SignalCardView card={c} key={c.key ?? i} />
        ))}
      </div>
    </section>
  );
}
