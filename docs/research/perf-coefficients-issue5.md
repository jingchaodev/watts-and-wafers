## Resolution (research subagent, 2026-07-18)

**Recommended source: SemiAnalysis InferenceX** (formerly InferenceMAX, `github.com/SemiAnalysisAI/InferenceX`, Apache-2.0), with MLPerf Inference as the conservative cross-check.

- InferenceX: continuously re-run via CI; covers H100/H200/B200/B300/GB200 NVL72/GB300 NVL72/MI300X/MI325X/MI355X; publishes tokens/s/GPU per model. Machine-readable path: **full DB dumps published as GitHub Releases on `InferenceX-app`** (cleanest cron-pull target) + `/api/v1/*` JSON routes behind the dashboard.
- MLPerf Inference v5.0: audited + machine-readable (`github.com/mlcommons/inference_results_v5.0`), but ~2 rounds/year and per-GPU numbers must be derived.

**Proposed coefficient table (H100 = 1.0; decode-heavy LLM serving, FP8 on Hopper / FP4 on Blackwell):**

| GPU | Coefficient | Basis |
|---|---|---|
| A100 | ~0.35 | spec-based estimate (absent from current benchmarks) |
| H100 | 1.00 | MLPerf v5.0 Llama2-70B ≈3,905 tok/s/GPU |
| H200 | ~1.15 | MLPerf v5.0 ≈4,400 tok/s/GPU |
| B200 | **~3.2 conservative / ~11 best-case (MoE, latest stack)** | MLPerf FP4 ≈12,357 tok/s/GPU → 3.16x; InferenceX gpt-oss-120B → ~11.2x |
| GB200 / MI300X | pull from InferenceX DB dump (follow-up) | |

**Dashboard recommendation:** ship MLPerf-derived ~3.2x as the default B200 coefficient, expose the InferenceX ~11x as a "latest-software / MoE" upper band; never average them — the spread is real workload dependence. Example read: B200 $7/hr ÷ 3.2 = $2.19 H100-equivalent ≈ parity with H100 at $2/hr on the conservative basis.

**Caveats:** (1) workload dependence dominates (3x↔11x swing); (2) FP4 vs FP8 is not iso-precision — this answers "cheapest way to serve today", not "how fast is the silicon"; (3) never build coefficients from TFLOPS spec ratios — decode is HBM-bandwidth-bound.

Sources: [InferenceX](https://github.com/SemiAnalysisAI/InferenceX) · [InferenceX-app (DB dumps in Releases)](https://github.com/SemiAnalysisAI/InferenceX-app) · [MLPerf v5.0 results](https://docs.mlcommons.org/inference_results_v5.0/) · [SemiAnalysis announcement](https://newsletter.semianalysis.com/p/inferencemax-open-source-inference)

Follow-up before implementation: pull one InferenceX DB dump for GB200/MI300X per-GPU numbers; confirm `/api/v1/*` query shapes from `InferenceX-app` source.
