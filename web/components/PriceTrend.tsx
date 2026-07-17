"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkAreaComponent,
  MarkLineComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import type { GpuTrendPayload } from "../lib/history";

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkAreaComponent,
  MarkLineComponent,
  SVGRenderer,
]);

const PALETTE: Record<string, string> = {
  "Vast median": "#D97757",
  RunPod: "#788C5D",
  "RunPod (ext)": "#9DB183",
  DataCrunch: "#5B7DA3",
  Lambda: "#B8860B",
  Nebius: "#3E8E8C",
  Crusoe: "#A0522D",
  CoreWeave: "#6B5B95",
  "Vast on-demand (ext)": "#E0A18C",
  "Azure on-demand": "#8E63CE",
  "Azure spot": "#C4A5EE",
  "Spot floor (backfill)": "#8F8A7D",
};

function quantile(sorted: number[], q: number): number {
  if (!sorted.length) return NaN;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  return sorted[lo] + (sorted[Math.min(lo + 1, sorted.length - 1)] - sorted[lo]) * (pos - lo);
}

export default function PriceTrend({ payload }: { payload: GpuTrendPayload }) {
  const gpus = Object.keys(payload.gpus);
  const [gpu, setGpu] = useState<string>(() => {
    if (typeof window !== "undefined") {
      const q = new URLSearchParams(window.location.search).get("gpu");
      if (q && payload.gpus[q]) return q;
    }
    return gpus.includes("H100") ? "H100" : gpus[0];
  });
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  const option = useMemo(() => {
    const seriesMap = payload.gpus[gpu] ?? {};
    // percentile band from the union of marketplace/neocloud points for this
    // class — Azure on-demand list prices sit 3-6x above and would skew it
    const all = Object.entries(seriesMap)
      .filter(([name]) => name !== "Azure on-demand" && !name.includes("backfill"))
      .flatMap(([, pts]) => pts)
      .map((p) => p[1])
      .sort((a, b) => a - b);
    const p25 = quantile(all, 0.25);
    const p50 = quantile(all, 0.5);
    const p75 = quantile(all, 0.75);

    // break lines across real data gaps (>35 days) instead of drawing a
    // fake interpolated segment through months with no observations
    const GAP_MS = 35 * 24 * 3600 * 1000;
    const withGaps = (pts: [string, number][]): [string, number | null][] => {
      const outPts: [string, number | null][] = [];
      for (let j = 0; j < pts.length; j++) {
        if (j > 0) {
          const prev = Date.parse(pts[j - 1][0]);
          const cur = Date.parse(pts[j][0]);
          if (cur - prev > GAP_MS)
            outPts.push([new Date(prev + GAP_MS / 2).toISOString(), null]);
        }
        outPts.push(pts[j]);
      }
      return outPts;
    };

    // markArea/markLine must anchor to a default-VISIBLE series or they vanish
    const HIDDEN = new Set(["Azure on-demand", "Vast on-demand (ext)", "Spot floor (backfill)"]);
    const names = Object.keys(seriesMap);
    const anchorIdx = Math.max(0, names.findIndex((n) => !HIDDEN.has(n)));

    const series = Object.entries(seriesMap).map(([name, pts], i) => ({
      name,
      type: "line" as const,
      data: withGaps(pts),
      // sparse young series still need visible marks; hide symbols once dense
      showSymbol: pts.length < 50,
      symbolSize: 4,
      connectNulls: false,
      lineStyle: { width: name.includes("backfill") ? 1.4 : 1.8, color: PALETTE[name] },
      itemStyle: { color: PALETTE[name] },
      ...(i === anchorIdx && isFinite(p25)
        ? {
            markArea: {
              silent: true,
              itemStyle: { color: "rgba(135,134,127,0.08)" },
              data: [[{ yAxis: p25 }, { yAxis: p75 }]],
            },
            markLine: {
              silent: true,
              symbol: "none",
              lineStyle: { color: "#87867F", type: "dashed", width: 1 },
              label: {
                formatter: "P50 ${c}",
                position: "insideEndTop",
                color: "#87867F",
                fontSize: 10,
                fontFamily: "ui-monospace, monospace",
              },
              data: isFinite(p50) ? [{ yAxis: Math.round(p50 * 100) / 100 }] : [],
            },
          }
        : {}),
    }));

    return {
      backgroundColor: "transparent",
      animation: false,
      grid: { left: 48, right: 16, top: 64, bottom: 64 },
      legend: {
        top: 0,
        textStyle: { color: "#3D3D3A", fontSize: 12 },
        itemWidth: 14,
        itemHeight: 2,
        icon: "rect",
        // Azure on-demand quotes 3-6x above marketplace and crush the y-axis;
        // keep the series one click away instead of on by default.
        selected: {
          "Azure on-demand": false,
          "Vast on-demand (ext)": false,
          "Spot floor (backfill)": false,
        },
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#FFFFFF",
        borderColor: "#D1CFC5",
        textStyle: { color: "#1F1F1F", fontSize: 12 },
        valueFormatter: (v: unknown) => (typeof v === "number" ? `$${v.toFixed(2)}/hr` : "—"),
      },
      xAxis: {
        type: "time" as const,
        axisLine: { lineStyle: { color: "#D1CFC5" } },
        axisLabel: { color: "#87867F", fontSize: 11, fontFamily: "ui-monospace, monospace" },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value" as const,
        scale: true,
        axisLabel: {
          color: "#87867F",
          fontSize: 11,
          fontFamily: "ui-monospace, monospace",
          formatter: "${value}",
        },
        splitLine: { lineStyle: { color: "#F0EEE6" } },
      },
      dataZoom: [
        { type: "inside" as const, throttle: 50 },
        {
          type: "slider" as const,
          height: 22,
          bottom: 8,
          borderColor: "#D1CFC5",
          fillerColor: "rgba(217,119,87,0.12)",
          handleStyle: { color: "#D97757" },
          textStyle: { color: "#87867F", fontSize: 10 },
        },
      ],
      series,
    };
  }, [payload, gpu]);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "svg" });
    chartRef.current = chart;
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: true });
  }, [option]);

  const selectGpu = (g: string) => {
    setGpu(g);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("gpu", g);
      window.history.replaceState(null, "", url.toString());
    }
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
        {gpus.map((g) => (
          <button
            key={g}
            onClick={() => selectGpu(g)}
            style={{
              padding: "4px 12px",
              borderRadius: 999,
              border: `1px solid ${g === gpu ? "#D97757" : "#D1CFC5"}`,
              background: g === gpu ? "rgba(217,119,87,0.12)" : "#FFFFFF",
              color: g === gpu ? "#B14A3A" : "#3D3D3A",
              fontSize: 13,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            {g}
          </button>
        ))}
      </div>
      <div ref={ref} style={{ width: "100%", height: 380 }} />
      <p style={{ fontSize: 11, color: "#87867F", fontFamily: "ui-monospace, monospace", marginTop: 6 }}>
        Gray band = P25–P75 of on-demand history (spot/backfill excluded) · legend toggles providers ·
        drag to zoom
      </p>
      <p style={{ fontSize: 11, color: "#87867F", fontFamily: "ui-monospace, monospace", marginTop: 4 }}>
        Sources: Vast.ai marketplace API (median $/GPU-hr of rentable offers) · RunPod &amp; DataCrunch
        public pricing (lowest on-demand $/GPU-hr) · Azure Retail Prices API (cheapest US-region
        ND-series, per-GPU) · Lambda/Nebius/Crusoe/CoreWeave/RunPod history May–Jul 2026 via{" "}
        <a href="https://github.com/cherielilili/gpu-pricing-tracker" style={{ color: "#87867F" }}>
          gpu-pricing-tracker
        </a>{" "}
        (on-demand rate cards) · RunPod H1-2025 points from Internet Archive snapshots of
        runpod.io/pricing · Spot floor backfill = lowest spot/on-demand price across providers,
        from our pre-launch tracker (Jul 8–17, 2026). Full provenance in the repo. Collected
        hourly/daily by{" "}
        <a href="https://github.com/jingchaodev/watts-and-wafers" style={{ color: "#87867F" }}>
          open collectors
        </a>
        .
      </p>
    </div>
  );
}
