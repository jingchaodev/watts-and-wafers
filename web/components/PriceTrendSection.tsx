import { loadGpuTrend } from "@/lib/history";
import PriceTrend from "./PriceTrend";

export default function PriceTrendSection() {
  const payload = loadGpuTrend();
  if (!Object.keys(payload.gpus).length) return null;
  return (
    <section className="block">
      <h2 className="section-title">GPU price trend</h2>
      <p className="section-sub">
        All providers on one tape, per GPU class — is today&apos;s price high or low vs its own
        history?
      </p>
      <div className="card">
        <PriceTrend payload={payload} />
      </div>
    </section>
  );
}
