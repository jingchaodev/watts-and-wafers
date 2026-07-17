import type { VastData, VastHistoryLine } from "@/lib/types";
import Sparkline from "./Sparkline";
import StalePill from "./StalePill";
import { fmtNum, fmtUsd } from "@/lib/format";

/**
 * Falling offers over the trailing history = tightening demand — highlight that
 * sparkline in clay (matches the "up = demand strength" convention used across the
 * app). Rising offers = loosening = olive is arguably "good" for renters, but for a
 * demand-signal dashboard we still key strictly on offers trend direction: down = clay.
 */
function trendTone(values: number[]): "clay" | "olive" | "muted" {
  const clean = values.filter((v) => typeof v === "number" && !Number.isNaN(v));
  if (clean.length < 2) return "muted";
  const first = clean[0];
  const last = clean[clean.length - 1];
  if (first === 0) return "muted";
  const pctChange = (last - first) / Math.abs(first);
  if (Math.abs(pctChange) < 0.02) return "muted";
  // Falling offers -> demand tightening -> clay. Rising offers -> olive.
  return pctChange < 0 ? "clay" : "olive";
}

export default function GpuAvailability({
  vast,
  history,
}: {
  vast: VastData;
  history: VastHistoryLine[];
}) {
  const gpuEntries = Object.entries(vast.gpus ?? {});

  return (
    <section className="block">
      <h2 className="section-title">
        GPU availability
        <StalePill asof={vast.asof} hours={3} />
      </h2>
      <p className="section-sub">
        Offer count is the sold-out proxy — falling offers + rising median price =
        demand tightening. Source: Vast.ai public API.
      </p>
      <div className="card">
        {gpuEntries.length === 0 ? (
          <p className="note-muted">No availability data.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>GPU class</th>
                  <th>Offers</th>
                  <th>Total GPUs</th>
                  <th>Median $/hr</th>
                  <th>P25 $/hr</th>
                  <th>Min $/hr</th>
                  <th>Offers trend (30d)</th>
                </tr>
              </thead>
              <tbody>
                {gpuEntries.map(([gpu, stat]) => {
                  const series = history
                    .map((h) => h.gpus?.[gpu]?.offers)
                    .filter((v): v is number => typeof v === "number");
                  const tone = trendTone(series);
                  return (
                    <tr key={gpu}>
                      <td>{gpu}</td>
                      <td className={`num ${tone === "clay" ? "tone-clay" : tone === "olive" ? "tone-olive" : ""}`}>
                        {fmtNum(stat.offers)}
                      </td>
                      <td className="num">{fmtNum(stat.total_gpus)}</td>
                      <td className="num">{fmtUsd(stat.median_dph)}</td>
                      <td className="num">{fmtUsd(stat.p25_dph)}</td>
                      <td className="num">{fmtUsd(stat.min_dph)}</td>
                      <td className="num">
                        <div className="cell-with-spark">
                          <Sparkline values={series} tone={tone} />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {vast.errors && vast.errors.length > 0 && (
          <p className="note-muted">Collector errors: {vast.errors.join("; ")}</p>
        )}
      </div>
    </section>
  );
}
