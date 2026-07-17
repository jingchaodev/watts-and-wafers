import type { OpenRouterData, OpenRouterHistoryLine } from "@/lib/types";
import Sparkline from "./Sparkline";
import StalePill from "./StalePill";
import { fmtContext, fmtNum, fmtUsd } from "@/lib/format";

export default function TokenEconomics({
  openrouter,
  history,
}: {
  openrouter: OpenRouterData;
  history: OpenRouterHistoryLine[];
}) {
  const models = (openrouter.models ?? []).slice(0, 12);
  const sparkValues = history
    .map((h) => h.frontier_median_completion_usd_per_m)
    .filter((v): v is number => typeof v === "number");

  return (
    <section className="block">
      <h2 className="section-title">
        Token economics
        <StalePill asof={openrouter.asof} hours={26} />
      </h2>
      <div className="card">
        <div className="card-grid" style={{ marginBottom: 20 }}>
          <div>
            <div className="section-sub" style={{ margin: "0 0 4px" }}>
              Models tracked
            </div>
            <div className="hero-number" style={{ fontSize: 32 }}>
              {fmtNum(openrouter.n_models)}
            </div>
          </div>
          <div>
            <div className="section-sub" style={{ margin: "0 0 4px" }}>
              Frontier median $/M (completion)
            </div>
            <div className="cell-with-spark" style={{ justifyContent: "flex-start" }}>
              <span className="hero-number" style={{ fontSize: 32 }}>
                {fmtUsd(openrouter.frontier_median_completion_usd_per_m)}
              </span>
              <Sparkline values={sparkValues} tone="clay" />
            </div>
          </div>
        </div>

        {!openrouter.tokens_daily && (
          <p className="note-muted">Token volume feed pending API key.</p>
        )}

        {models.length === 0 ? (
          <p className="note-muted">No model pricing data.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>$/M in</th>
                  <th>$/M out</th>
                  <th>Context</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m) => (
                  <tr key={m.id ?? m.name}>
                    <td>{m.name ?? m.id ?? "—"}</td>
                    <td className="num">{fmtUsd(m.prompt_usd_per_m)}</td>
                    <td className="num">{fmtUsd(m.completion_usd_per_m)}</td>
                    <td className="num">{fmtContext(m.context)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {openrouter.errors && openrouter.errors.length > 0 && (
          <p className="note-muted">Collector errors: {openrouter.errors.join("; ")}</p>
        )}
      </div>
    </section>
  );
}
