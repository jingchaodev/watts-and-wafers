import type { CompositeData, CompositeHistoryLine } from "@/lib/types";
import Sparkline from "./Sparkline";
import StalePill from "./StalePill";
import { directionArrow } from "@/lib/format";

const LABEL_COLORS: Record<string, string> = {
  GLUT: "#B14A3A",
  SOFTENING: "#C98A5E",
  NEUTRAL: "#6B6A62",
  TIGHTENING: "#5F7A4A",
  SURGING: "#788C5D",
};

function labelBg(label: string): string {
  const c = LABEL_COLORS[label] ?? "#6B6A62";
  return c;
}

const ARROW_CLASS: Record<string, string> = {
  up: "arrow-up",
  down: "arrow-down",
  flat: "arrow-flat",
};

export default function Hero({
  composite,
  history,
}: {
  composite: CompositeData;
  history: CompositeHistoryLine[];
}) {
  const index = typeof composite.index === "number" ? composite.index : null;
  const label = composite.label ?? "—";
  const clamped = index === null ? 50 : Math.max(0, Math.min(100, index));
  const sparkValues = history
    .map((h) => h.index)
    .filter((v): v is number => typeof v === "number");

  return (
    <section className="block">
      <h2 className="section-title">
        Composite demand index
        <StalePill asof={composite.asof} hours={26} />
      </h2>
      <div className="card">
        <div className="hero-top">
          <div className="hero-number">{index === null ? "—" : Math.round(index)}</div>
          <span
            className="pill-label"
            style={{
              background: labelBg(label) + "22",
              color: labelBg(label),
              border: `1px solid ${labelBg(label)}55`,
            }}
          >
            {label}
          </span>
          <div style={{ marginLeft: "auto" }}>
            <Sparkline values={sparkValues} width={140} height={36} tone="clay" />
          </div>
        </div>

        <div className="gauge">
          <div className="gauge-marker" style={{ left: `${clamped}%` }} />
        </div>
        <div className="gauge-scale">
          <span>0 GLUT</span>
          <span>35</span>
          <span>50 NEUTRAL</span>
          <span>65</span>
          <span>100 SURGING</span>
        </div>

        <div style={{ marginTop: 20 }}>
          {(composite.signals ?? []).map((s, i) => (
            <div className="signal-row" key={s.key ?? i}>
              <span className="signal-key">{(s.key ?? "—").replace(/_/g, " ")}</span>
              <span className="signal-weight">
                {typeof s.weight === "number" ? `w ${s.weight.toFixed(2)}` : "—"}
                {typeof s.z === "number" ? ` · z ${s.z.toFixed(1)}` : ""}
              </span>
              <span className={`signal-arrow ${ARROW_CLASS[s.direction ?? "flat"] ?? ""}`}>
                {directionArrow(s.direction)}
              </span>
              <span className="signal-detail">{s.detail ?? "—"}</span>
            </div>
          ))}
          {(!composite.signals || composite.signals.length === 0) && (
            <p className="note-muted">No signal breakdown available.</p>
          )}
        </div>
      </div>
    </section>
  );
}
