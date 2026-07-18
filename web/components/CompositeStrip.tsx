import type { CompositeData, CompositeHistoryLine } from "@/lib/types";
import Sparkline from "./Sparkline";
import { directionArrow } from "@/lib/format";

const LABEL_COLORS: Record<string, string> = {
  GLUT: "#B14A3A",
  SOFTENING: "#C98A5E",
  NEUTRAL: "#6B6A62",
  TIGHTENING: "#5F7A4A",
  SURGING: "#788C5D",
};

const ARROW_CLASS: Record<string, string> = {
  up: "arrow-up",
  down: "arrow-down",
  flat: "arrow-flat",
};

export default function CompositeStrip({
  composite,
  history,
}: {
  composite: CompositeData;
  history: CompositeHistoryLine[];
}) {
  const index = typeof composite.index === "number" ? Math.round(composite.index) : null;
  const label = composite.label ?? "—";
  const color = LABEL_COLORS[label] ?? "#6B6A62";
  const sparkValues = history
    .map((h) => h.index)
    .filter((v): v is number => typeof v === "number");

  return (
    <details className="composite-strip">
      <summary>
        <span>Composite (experimental):</span>
        <span className="composite-strip-index">{index === null ? "—" : index}</span>
        <span
          className="pill-label"
          style={{ background: color + "22", color, border: `1px solid ${color}55`, fontSize: 11 }}
        >
          {label}
        </span>
      </summary>
      <div className="composite-strip-body">
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
          <Sparkline values={sparkValues} width={140} height={32} tone="clay" />
        </div>
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
    </details>
  );
}
