import { loadGpuTrend, loadAnnotationEvents } from "@/lib/history";
import PriceTrend from "./PriceTrend";

export default function PriceTrendSection() {
  const payload = loadGpuTrend();
  const events = loadAnnotationEvents();
  if (!Object.keys(payload.gpus).length) return null;
  return (
    <section className="block" id="gpu-price-trend">
      <h2 className="section-title">GPU price trend</h2>
      <p className="section-sub">
        All providers on one tape, per GPU class — is today&apos;s price high or low vs its own
        history?
      </p>
      <div className="card">
        <PriceTrend payload={payload} events={events} />
      </div>
    </section>
  );
}
