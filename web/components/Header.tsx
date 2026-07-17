import { formatAsof } from "@/lib/data";

export default function Header({ asof }: { asof: string | null }) {
  return (
    <header className="site-header">
      <div>
        <h1 className="wordmark">Watts &amp; Wafers</h1>
        <p className="tagline">AI compute demand, on one tape</p>
      </div>
      <div className="header-meta">
        <span title="Latest of all data-source asof timestamps">
          asof {formatAsof(asof)}
        </span>
        <a
          href="https://github.com/jingchaodev/watts-and-wafers"
          target="_blank"
          rel="noopener noreferrer"
        >
          GitHub ↗
        </a>
      </div>
    </header>
  );
}
