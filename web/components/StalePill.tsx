import { isStale } from "@/lib/data";

interface StalePillProps {
  asof: string | undefined | null;
  /** Freshness budget in hours. Hourly feeds: 3h. Daily feeds: 26h. */
  hours: number;
}

export default function StalePill({ asof, hours }: StalePillProps) {
  if (!isStale(asof, hours)) return null;
  return <span className="pill-stale">stale</span>;
}
