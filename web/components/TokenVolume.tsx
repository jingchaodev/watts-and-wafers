"use client";

import { useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";

echarts.use([LineChart, GridComponent, TooltipComponent, DataZoomComponent, SVGRenderer]);

export default function TokenVolume({ points }: { points: [string, number][] }) {
  const ref = useRef<HTMLDivElement>(null);

  const option = useMemo(
    () => ({
      backgroundColor: "transparent",
      animation: false,
      grid: { left: 56, right: 16, top: 20, bottom: 60 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#FFFFFF",
        borderColor: "#D1CFC5",
        textStyle: { color: "#1F1F1F", fontSize: 12 },
        valueFormatter: (v: unknown) =>
          typeof v === "number" ? `${v >= 1000 ? (v / 1000).toFixed(2) + "T" : v.toFixed(0) + "B"} tokens/day` : "—",
      },
      xAxis: {
        type: "time" as const,
        axisLine: { lineStyle: { color: "#D1CFC5" } },
        axisLabel: { color: "#87867F", fontSize: 11, fontFamily: "ui-monospace, monospace" },
        splitLine: { show: false },
      },
      yAxis: {
        // log axis: constant growth rate reads as a straight line, so
        // acceleration/deceleration is visible across a 200x range
        type: "log" as const,
        logBase: 10,
        axisLabel: {
          color: "#87867F",
          fontSize: 11,
          fontFamily: "ui-monospace, monospace",
          formatter: (v: number) => (v >= 1000 ? `${v / 1000}T` : `${v}B`),
        },
        splitLine: { lineStyle: { color: "#F0EEE6" } },
      },
      dataZoom: [
        { type: "inside" as const, throttle: 50 },
        {
          type: "slider" as const,
          height: 20,
          bottom: 8,
          borderColor: "#D1CFC5",
          fillerColor: "rgba(217,119,87,0.12)",
          handleStyle: { color: "#D97757" },
          textStyle: { color: "#87867F", fontSize: 10 },
        },
      ],
      series: [
        {
          name: "Tokens/day",
          type: "line" as const,
          data: points,
          showSymbol: false,
          lineStyle: { width: 1.8, color: "#D97757" },
          itemStyle: { color: "#D97757" },
          areaStyle: { color: "rgba(217,119,87,0.07)" },
        },
      ],
    }),
    [points]
  );

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "svg" });
    chart.setOption(option);
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [option]);

  return <div ref={ref} style={{ width: "100%", height: 320 }} />;
}
