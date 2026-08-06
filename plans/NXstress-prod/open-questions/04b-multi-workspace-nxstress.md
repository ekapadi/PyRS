# Open Questions — 04b Multi-workspace NXstress I/O

**Spec:** [04b-multi-workspace-nxstress.md](../04b-multi-workspace-nxstress.md)
**Blocking:** No — Q1 was originally a hard gate; downgraded below to a
tracked follow-up now that a precedent for the underlying mechanism is
confirmed to already exist in the codebase. Nothing here blocks starting
implementation.

---

## Q1 — RESOLVED (downgraded): does `NXreflections` permit additional index columns at all? {#q1}

Originally generalized `open-questions/05-strain-stress-viewer.md` Q1 into a
hard implementation gate, on the assumption that no precedent existed for
extending `NXreflections` beyond the schema's required columns.

That assumption doesn't hold: `_peaks.py::_init` already writes `mask`,
`scan_point`, `center`, `center_errors`, `center_type`, and `sx`/`sy`/`sz`
onto `NXreflections` (`_peaks.py:100-172`), and the module's own docstring
(`_peaks.py:37-40`) states only `h`/`k`/`l`/`phase_name` (plus the unused
`qx`/`qy`/`qz`) are schema-required — `mask` explicitly was not part of
`PeakCollection` before this implementation added it. A discriminator column
is the same category of extension `NXreflections` already tolerates in
practice.

**Status:** downgraded from a blocking gate to a tracked follow-up.
`NXstress.html` (the canonical schema doc) and the `nexusformat`-org
validator are being added to the repo separately; once both are present,
verify against them and record the outcome here and in the plan's Decisions
Log (README.md §4). If that verification later disagrees with the
`mask`/`scan_point` precedent, revisit — but implementation proceeds now
rather than waiting on it.

---

## Q2 — What is the exact discriminator field set? — mechanism now decided, names still deferred

Deliberately deferred at the story-scoping stage: "workspaces will be
separated by an explicit combined-index field (possible multiple fields) ...
It should be possible to write the spec without yet having the specifics."

The **mechanism** is now settled (see the spec's Overview, Scope, and
NXstress Changes sections): field names come from a new PyRS config key,
`nxstress.discriminator_fields: list[str]`, resolved via
`pyrs.utilities.config.load_config()` inside NXstress itself — not from
NXstress's own defaults and not from a per-`write()`-call argument. Values
are resolved per workspace via a property-or-`SampleLogs`-fallback resolver,
and carried internally name-keyed (not positionally), so config reordering
between write and read can't cause silent misattribution. What remains
**deferred** is only the actual field names any given deployment configures.

Known candidates so far:
- `direction` (spec 05: `"11"`, `"22"`, `"33"`) — the StrainStressViewer case.
- Something CombineRuns-shaped, if spec 03's export path adopts
  `NXstress.write([ws_a, ws_b, ...], peakss)` directly (see Q3) — possibly
  `run_number`, if CombineRuns' inputs are guaranteed disjoint by run.

**Why it matters:** the field-set decision determines whether one generic
discriminator column suffices, or whether the mechanism needs to support
multiple simultaneous discriminator columns (per the "possible multiple
fields" framing) — which affects `sort_key`'s ordering tuple and the
uniqueness-key logic in `validateNoDuplicatePeaks`. The mechanism already
supports multiple fields (name-keyed, not a fixed-arity tuple), so this is
now purely a config-value decision, not an implementation-shape one.

**Next step:** resolve at 04b implementation kickoff, informed by whichever
concrete consumer (spec 05's `direction`, or a CombineRuns discriminator) is
implemented first.

---

## Q3 — RESOLVED: does CombineRunsModel drop its in-PyRS pre-merge once 04b lands?

Spec 03 currently merges N `HidraProjectFile`s into one `HidraWorkspace` via
repeated `HidraWorkspace.append_hidra_project` calls
(`combine_runs_model.py:14-23`) *before* calling `NXstress.write`. Once
`NXstress.write` accepts `list[HidraWorkspace]` directly, that pre-merge step
is redundant for the NXstress export path — but `CombineRunsModel` might
still need the merged single-workspace form for its existing `.h5` export
path (`export_project_files`), which is unaffected by this spec.

**Decided: no, keep the pre-merge.** `HidraWorkspace.append_hidra_project`
already discards per-run boundaries the same way `nxstress.merge_workspaces:
true` would — same resulting semantics, just already implemented at the
PyRS layer. Since the `.h5` export path still needs the merged single
workspace regardless, dropping the pre-merge only for `.nxs` would mean
`CombineRunsModel` carrying two separate data paths (N raw workspaces for
`.nxs`, one merged workspace for `.h5`) to produce an *identical* resulting
`.nxs` file either way — a net complexity increase for no behavioral gain.
04b's own Scope item ("Update the spec-02/03 call sites... to pass/receive a
length-1... list") is therefore just that: **wrap the existing merged
workspace in a length-1 list**, not a restructuring of `combine_project_files`
itself. See `03-combine-runs-nxstress.md` ("Pre-merge stays" section) for
the full writeup.

---

## Q4 — What happens if a configured discriminator name collides with a reserved `NXreflections` column?

`_peaks.py::_init` already reserves `h`, `k`, `l`, `mask`, `scan_point`,
`center`, `center_errors`, `center_type`, `sx`, `sy`, `sz`, `qx`, `qy`, `qz`
as column names. If `nxstress.discriminator_fields` is configured with a
name that collides with one of these, the writer must not silently overwrite
or shadow the reserved column.

**Why it matters:** a silent collision would corrupt either the reserved
column's meaning or the discriminator's, with no error to signal it — the
kind of bug that only surfaces much later, when a round-trip produces
subtly wrong values.

**Next step:** implement a collision guard (raise at config-load time or at
first `write()` call, whichever is more useful to a caller who mistypes a
config value) and cover it with a unit test. Recommendation: raise — no
known use case needs a discriminator name to shadow a reserved column.

---

## Q5 — What should the property-or-log resolver helper be named / where does it live?

The spec's "Discriminator value resolution" section sketches the resolver's
logic but leaves its exact module and function name to implementation (it is
NXstress-internal — no new `HidraWorkspace` method, per the spec's PyRS
Changes section).

**Why it matters:** purely cosmetic — doesn't affect behavior — but worth
settling once so it isn't reinvented per call site inside `_peaks.py`,
`_sample.py`, etc.

**Next step:** decide at implementation time; a reasonable default is a
private function in `_peaks.py` (where discriminator values are consumed)
or a new small `_discriminator.py` module if the logic ends up shared across
more than one of `_peaks.py`/`_sample.py`/`_instrument.py`.
