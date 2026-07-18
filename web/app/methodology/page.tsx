import Link from "next/link";

export const metadata = { title: "Methodology — Watts & Wafers" };

const REPO = "https://github.com/jingchaodev/watts-and-wafers";

export default function Methodology() {
  return (
    <div className="wrap">
      <header className="site-header">
        <div>
          <h1 className="wordmark">Watts &amp; Wafers</h1>
          <p className="tagline">Methodology — how every number is made</p>
        </div>
        <div className="header-meta">
          <Link href="/">← Dashboard</Link>
          <a href={REPO}>GitHub ↗</a>
        </div>
      </header>
      <main>
        <section className="block">
          <h2 className="section-title">Principles</h2>
          <p>
            Every number on the dashboard is computed by open-source collectors from public data,
            committed to a public git repository. The git history <em>is</em> the audit trail: any
            value can be traced to the commit that recorded it and the code that parsed it. Nothing
            here is investment advice; the site describes the state of the compute market, it does
            not tell you what to do about it.
          </p>
        </section>

        <section className="block">
          <h2 className="section-title">The five signals</h2>
          <div className="card">
            <h3>H100 market price</h3>
            <p>
              Median $/GPU-hr of rentable H100-class offers (SXM and NVL folded by median) on the
              Vast.ai public marketplace API, per-GPU normalized (whole-machine price ÷ GPU count).
              Collected hourly. The percentile badge compares today against a 90-day window; until
              our own series reaches 90 days (~Oct 2026), the window is spliced with the same
              statistic recorded daily by the open{" "}
              <a href="https://github.com/cherielilili/gpu-pricing-tracker">gpu-pricing-tracker</a>{" "}
              (same API, same normalization, ~5-10% level offset from filter differences) — cards
              disclose this while active.
            </p>
            <h3>Availability</h3>
            <p>
              Count of rentable H100-class offers on Vast.ai — the sold-out proxy. Falling offers
              with rising prices = demand absorbing capacity. Headline value is the 7-day change.
              This measures the consumer/marginal segment, which typically moves before list
              prices do.
            </p>
            <h3>Spot discount</h3>
            <p>
              Azure H100 spot price ÷ on-demand price, cheapest US-region SKU, same-provider
              pairing only (a discount is only meaningful within one provider&apos;s capacity
              pool). Spot is auction-style clearance pricing for idle machines: a deep discount
              means idle capacity; a ratio approaching 1 means the spot pool is exhausted.
            </p>
            <h3>Generational ratio (perf-adjusted)</h3>
            <p>
              (B200 blended on-demand $/hr ÷ 3.2) ÷ H100 blended $/hr. The 3.2 coefficient is the
              conservative measured B200-vs-H100 inference throughput ratio derived from{" "}
              <a href="https://docs.mlcommons.org/inference_results_v5.0/">MLPerf Inference v5.0</a>{" "}
              (FP4 vs FP8, Llama2-70B class). Measured MoE workloads on the latest software stack
              (<a href="https://github.com/SemiAnalysisAI/InferenceX">SemiAnalysis InferenceX</a>)
              show up to ~11x — so treat 3.2 as the floor of Blackwell&apos;s advantage, not the
              ceiling. Below 1.0 means Blackwell is the cheaper way to buy compute. Both
              generations falling in absolute terms is the historical glut signature.
            </p>
            <h3>Token volume growth</h3>
            <p>
              30-day growth of the 7-day moving average of daily tokens routed through OpenRouter
              (official rankings dataset, history to Jan 2025). The 7-day average removes weekly
              seasonality. OpenRouter is one router among many: treat the level as a sample and
              the trend as the signal.
            </p>
          </div>
        </section>

        <section className="block">
          <h2 className="section-title">Validation</h2>
          <p>
            Values pass per-GPU-class plausibility bands at ingest (wide on purpose: they catch
            unit errors like per-node-vs-per-GPU, not market moves). Anything excluded lands in an
            append-only quarantine file — nothing fails silently. A daily cross-check compares each
            provider against the cohort median per GPU class and flags &gt;2.5x deviations. Line
            charts break across &gt;35-day data gaps rather than drawing fake interpolated
            segments. All collectors degrade gracefully: a failing source records an error and the
            page shows staleness, never invented values.
          </p>
        </section>

        <section className="block">
          <h2 className="section-title">Known limitations</h2>
          <p>
            <strong>No contract prices.</strong> Enterprise 1-3 year GPU contracts — the majority
            of real-world compute spend — are private. This site measures the public tape: listed
            rates, marketplace prices, spot pools. In early 2024 the marketplace crashed while
            enterprise contracts stayed tight; single-layer reads mislead, which is why the
            signals span marketplace, neocloud rate cards, and hyperscaler quotes.{" "}
            <strong>Vast.ai skews consumer/prosumer</strong> — it is the marginal-demand
            thermometer, not an enterprise price benchmark. <strong>History is young</strong> for
            some series; percentile badges show null rather than pretending. The{" "}
            <strong>composite index is experimental</strong>: its weights are priors ordered by
            Gavin Baker&apos;s signal ranking (availability &gt; tokens &gt; memory &gt; price),
            not fitted to outcomes.
          </p>
        </section>

        <section className="block">
          <h2 className="section-title">Data &amp; code</h2>
          <p>
            Everything is in <a href={REPO}>the repository</a>: collectors (
            <code>collectors/</code>, stdlib Python, 125+ tests), the{" "}
            <a href={`${REPO}/blob/main/docs/DATA_CONTRACT.md`}>data contract</a>, raw series (
            <code>data/history/</code>), backfill{" "}
            <a href={`${REPO}/blob/main/data/history/BACKFILL_PROVENANCE.md`}>provenance</a>, and
            the event annotation list (<code>data/events.jsonl</code>). Collection runs on public
            GitHub Actions; every run&apos;s log is public for 90 days.
          </p>
        </section>
      </main>
    </div>
  );
}
