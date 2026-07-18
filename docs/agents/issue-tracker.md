# Issue tracker

GitHub Issues on jingchaodev/watts-and-wafers. No `gh` CLI on the collector host —
use the REST API with the stored PAT (never print it).

## Wayfinding operations

- The map: issue labelled `wayfinder:map`.
- Tickets: plain issues titled `[type] Question`, body starts `Child of #<map>`.
- Blocking: body line `Blocked by: #N, #M` (no native dependency graph via API here).
- Frontier: open issues whose `Blocked by` issues are all closed and with no assignee.
- Claim: assign the issue before working it.
