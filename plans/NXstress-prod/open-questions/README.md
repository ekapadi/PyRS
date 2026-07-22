# Open Questions — Index

Companion to the [NXstress GUI Hookup plan](../README.md). Each file here
lists the open questions specific to the correspondingly-numbered sub-spec —
things the spec text flags as unresolved, ambiguous, or contingent on an
audit/decision that hasn't happened yet. Resolved decisions already live in
the plan's own [Decisions Log](../README.md#4-decisions-log); this index is
for what's still outstanding.

| # | Spec | Blocking? | Question count |
|---|---|---|---|
| [02](02-peak-and-texture-nxstress.md) | NXstress I/O for PeakFitting & Texture viewers | No | 1 |
| [03](03-combine-runs-nxstress.md) | NXstress I/O for CombineRuns viewer | No | 1 |
| [04](04-nxstress-internal-cleanup.md) | NXstress internal cleanup (Phase 2 TODOs) | Partially | 4 |
| [05](05-strain-stress-viewer.md) | StrainStressViewer NXstress hookup | **Yes** | 3 |
| [06](06-manual-reduction-prereqs.md) | Manual reduction PyRS prerequisites | No | 2 |
| [07](07-append-and-manual-reduction-nxstress.md) | NXstress append support & ManualReduction hookup | No | 3 |
| [08](08-fit-spectrum-prereqs.md) | Reconstructed fit spectrum & calibration fidelity (PyRS) | No | 3 |
| [09](09-fit-spectrum-nxstress.md) | Fit spectrum & calibration fidelity (NXstress) | No | 2 |
| [10](10-flip-defaults.md) | Flip defaults — NXstress becomes primary | Partially | 2 |

**Highest priority:** [05, Q1](05-strain-stress-viewer.md#q1) — the
NXstress.xml schema check for the `direction` axis. It's the only item
marked as a hard implementation gate in the plan text itself, and it
determines the shape of all of Phase 3.
