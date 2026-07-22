# Open Questions — 03 NXstress I/O for CombineRuns Viewer

**Spec:** [03-combine-runs-nxstress.md](../03-combine-runs-nxstress.md)
**Blocking:** No

## Q1 — Read-back completeness for the CombineRuns case

Same plan-level caveat as spec 02 (README.md:237-241): `NXstress.read()`
doesn't reconstruct raw counts unless `input_data` was written. This spec is
explicitly export-only (loading a `.nxs` back into CombineRunsViewer is
out of scope), but the round-trip *test* in this spec does read the file
back via `NXstress.read()` to assert equality.

**Why it matters:** if the merged workspace's raw counts are expected to
match after read-back in the round-trip test, and `input_data` isn't written
by `NXstress.write` for combined runs, the test will need to special-case
which fields it compares (sub-run counts and sample-log arrays only, per the
spec's own Tests section) rather than a full workspace equality check.

**Next step:** confirm the round-trip test's assertion scope matches what
`NXstress.read()` can actually reconstruct — the spec's Tests section
already narrows this to "sub-run counts and sample-log arrays," which
suggests this was anticipated but not stated as a deliberate scoping
decision.

**Reponse from Chris:** What prevents us from testing that `NXstress.read()`
will reconstruct raw counts when `input_data` are present?