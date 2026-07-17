import type { MemoryData } from "@/lib/types";
import StalePill from "./StalePill";
import { fmtPct, fmtUsd, toneForChange } from "@/lib/format";

export default function Memory({ memory }: { memory: MemoryData }) {
  const dram = memory.dram_spot ?? [];
  const proxies = Object.entries(memory.proxies ?? {});

  return (
    <section className="block">
      <h2 className="section-title">
        Memory
        <StalePill asof={memory.asof} hours={26} />
      </h2>
      <p className="section-sub">
        DRAM spot rising = demand strength — priced clay when positive, rust when negative.
      </p>
      <div className="card">
        {dram.length === 0 ? (
          <p className="note-muted">No DRAM spot data.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Avg ($)</th>
                  <th>Chg %</th>
                </tr>
              </thead>
              <tbody>
                {dram.map((d, i) => {
                  const tone = toneForChange(d.chg_pct);
                  return (
                    <tr key={d.item ?? i}>
                      <td>{d.item ?? "—"}</td>
                      <td className="num">{fmtUsd(d.avg)}</td>
                      <td className={`num tone-${tone}`}>{fmtPct(d.chg_pct)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {memory.nand_note && (
          <p style={{ marginTop: 16, fontSize: 14 }}>
            <strong>NAND:</strong> {memory.nand_note.summary ?? "—"}
            {memory.nand_note.url && (
              <>
                {" "}
                <a href={memory.nand_note.url} target="_blank" rel="noopener noreferrer">
                  source ↗
                </a>
              </>
            )}
          </p>
        )}

        {proxies.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div className="section-sub" style={{ margin: "0 0 8px" }}>
              Proxies
            </div>
            <div className="card-grid">
              {proxies.map(([ticker, p]) => {
                const tone = toneForChange(p.chg_pct);
                return (
                  <div key={ticker}>
                    <span style={{ fontWeight: 600 }}>{ticker}</span>{" "}
                    <span className="num">{fmtUsd(p.price)}</span>{" "}
                    <span className={`num tone-${tone}`}>{fmtPct(p.chg_pct)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {memory.errors && memory.errors.length > 0 && (
          <p className="note-muted">Collector errors: {memory.errors.join("; ")}</p>
        )}
      </div>
    </section>
  );
}
