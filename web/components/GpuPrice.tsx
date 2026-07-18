import type { VastData, NeocloudsData, HyperscalerData } from "@/lib/types";
import StalePill from "./StalePill";
import { fmtUsd } from "@/lib/format";

/** Normalize a vast.ai GPU key ("H100 SXM") to the neocloud/azure key ("H100"). */
function normalizeGpuName(name: string): string {
  return name.replace(/\s*(SXM|PCIe)\s*$/i, "").trim();
}

export default function GpuPrice({
  vast,
  neoclouds,
  hyperscaler,
}: {
  vast: VastData;
  neoclouds: NeocloudsData;
  hyperscaler: HyperscalerData;
}) {
  const vastGpus = vast.gpus ?? {};
  const providers = neoclouds.providers ?? {};
  const azure = hyperscaler.azure ?? {};

  // Union of GPU classes across all sources, keyed by normalized name.
  const gpuSet = new Set<string>();
  Object.keys(vastGpus).forEach((g) => gpuSet.add(normalizeGpuName(g)));
  Object.values(providers).forEach((p) => Object.keys(p ?? {}).forEach((g) => gpuSet.add(g)));
  Object.values(azure).forEach((sku) => {
    if (sku.gpu) gpuSet.add(sku.gpu);
  });

  const gpuList = Array.from(gpuSet).sort();

  function vastMedianFor(gpu: string): number | undefined {
    // Prefer an exact match, else find a vast key whose normalized name matches.
    if (vastGpus[gpu]) return vastGpus[gpu].median_dph;
    const match = Object.entries(vastGpus).find(([k]) => normalizeGpuName(k) === gpu);
    return match?.[1]?.median_dph;
  }

  function azureFor(gpu: string): { od?: number; spot?: number | null } {
    const sku = Object.values(azure).find((s) => s.gpu === gpu);
    return { od: sku?.ondemand_gpu_hr, spot: sku?.spot_vm_hr && sku.gpus_per_vm ? sku.spot_vm_hr / sku.gpus_per_vm : sku?.spot_vm_hr };
  }

  const providerNames = Object.keys(providers).sort();

  return (
    <section className="block" id="gpu-price-comparison">
      <h2 className="section-title">
        GPU price comparison
        <StalePill asof={neoclouds.asof} hours={3} />
      </h2>
      <p className="section-sub">$/GPU-hr on-demand across marketplace, neoclouds, and hyperscaler.</p>
      <div className="card">
        {gpuList.length === 0 ? (
          <p className="note-muted">No price data.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>GPU class</th>
                  <th>Vast median</th>
                  {providerNames.map((p) => (
                    <th key={p}>{p}</th>
                  ))}
                  <th>Azure OD</th>
                  <th>Azure spot</th>
                </tr>
              </thead>
              <tbody>
                {gpuList.map((gpu) => {
                  const az = azureFor(gpu);
                  return (
                    <tr key={gpu}>
                      <td>{gpu}</td>
                      <td className="num">{fmtUsd(vastMedianFor(gpu))}</td>
                      {providerNames.map((p) => (
                        <td className="num" key={p}>
                          {fmtUsd(providers[p]?.[gpu])}
                        </td>
                      ))}
                      <td className="num">{fmtUsd(az.od)}</td>
                      <td className="num">{az.spot ? fmtUsd(az.spot) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {(neoclouds.errors?.length || hyperscaler.errors?.length) ? (
          <p className="note-muted">
            Collector errors: {[...(neoclouds.errors ?? []), ...(hyperscaler.errors ?? [])].join("; ")}
          </p>
        ) : null}
      </div>
    </section>
  );
}
