export type SparklineTone = "clay" | "olive" | "rust" | "muted";

interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  tone?: SparklineTone;
}

const TONE_COLORS: Record<SparklineTone, string> = {
  clay: "#D97757",
  olive: "#788C5D",
  rust: "#B14A3A",
  muted: "#9C9A8F",
};

/**
 * Minimal inline SVG sparkline — no chart library. Renders a polyline over the
 * min/max range of `values`, plus a filled dot on the last point.
 */
export default function Sparkline({
  values,
  width = 120,
  height = 32,
  tone = "muted",
}: SparklineProps) {
  const clean = values.filter((v) => typeof v === "number" && !Number.isNaN(v));

  if (clean.length < 2) {
    return (
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="#D1CFC5"
          strokeWidth={1}
          strokeDasharray="2,2"
        />
      </svg>
    );
  }

  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const range = max - min || 1;
  const pad = 3;
  const innerH = height - pad * 2;
  const stepX = width / (clean.length - 1);

  const points = clean.map((v, i) => {
    const x = i * stepX;
    const y = pad + innerH - ((v - min) / range) * innerH;
    return [x, y] as const;
  });

  const pathD = points
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");

  const color = TONE_COLORS[tone];
  const [lastX, lastY] = points[points.length - 1];

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <path d={pathD} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lastX} cy={lastY} r={2} fill={color} />
    </svg>
  );
}
