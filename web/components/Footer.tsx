import type { AllData } from "@/lib/types";
import { freshnessTier } from "@/lib/data";

const HOURLY_HOURS = 3;
const DAILY_HOURS = 26;

function buildFiles(data: AllData) {
  return [
    { label: "vast", asof: data.vast.asof, hours: HOURLY_HOURS },
    { label: "neoclouds", asof: data.neoclouds.asof, hours: HOURLY_HOURS },
    { label: "hyperscaler", asof: data.hyperscaler.asof, hours: DAILY_HOURS },
    { label: "openrouter", asof: data.openrouter.asof, hours: DAILY_HOURS },
    { label: "memory", asof: data.memory.asof, hours: DAILY_HOURS },
    { label: "signals", asof: data.signals.asof, hours: DAILY_HOURS },
  ];
}

export default function Footer({ data }: { data: AllData }) {
  const files = buildFiles(data);
  return (
    <footer className="site-footer">
      <p>
        Composite index = 50 + 12.5 × Σ(weight·z), z-scores computed from trailing
        history windows. No database — git history is the time series. See the{" "}
        <a
          href="https://github.com/jingchaodev/watts-and-wafers/blob/main/docs/DATA_CONTRACT.md"
          target="_blank"
          rel="noopener noreferrer"
        >
          data contract
        </a>{" "}
        for full methodology.
      </p>
      <p>Data updates hourly (GPU availability, neocloud price) / daily (hyperscaler, tokens, memory) via VPS cron.</p>
      <div className="health-strip">
        {files.map((f) => (
          <span className="health-item" key={f.label}>
            <span className={`health-dot ${freshnessTier(f.asof, f.hours)}`} />
            {f.label}
          </span>
        ))}
      </div>
    </footer>
  );
}
