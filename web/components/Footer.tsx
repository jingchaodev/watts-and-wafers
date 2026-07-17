export default function Footer() {
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
    </footer>
  );
}
