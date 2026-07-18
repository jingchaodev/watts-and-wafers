## Resolution (research subagent, 2026-07-18) — issue #7

**Format verdict:** hand-curated `data/events.jsonl`, one line per event:
`{"date","label","category":"model|capex|policy|market|supply","impact":1-3,"url"}`.
`impact` lets the renderer hide impact-1 markers at wide zoom; same-day events (two on
2025-10-29) require label stacking in the renderer.

**Seed:** 24 events 2025-01 → 2026-07, dates verified via WebSearch, committed at `data/events.jsonl`.

**Curation:** monthly manual sweep (fixed prompt: scan past month for AI-compute events in the
5 categories that moved markets/capex narratives; verify dates via primary sources; append) +
an event-driven append after each hyperscaler earnings date. No structured public source exists;
full automation would produce noise.

**Flagged uncertainties:** Grok 4 date (livestream 07-09 vs x.ai post 07-14; slug inferred);
Nov-2025 selloff anchored to 11-04 but is a multi-day grind; no single GB200 volume-ramp event
exists (GTC GB300 unveil used as the Blackwell supply milestone); SK Hynix + Meta URLs are
secondary sources — swap to IR primaries for strict discipline; Kimi K2 date is the HF license date.
