# 04b — Multi-workspace NXstress I/O

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** 2/3 (bridges NXstress internal cleanup and the StrainStressViewer hookup)
**Depends on:**
- [01 — Config infrastructure & test framework](01-config-and-test-infra.md)
- [04 — NXstress internal cleanup](04-nxstress-internal-cleanup.md)

---

## Overview

Generalize `NXstress.write` / `NXstress.read` from a single `HidraWorkspace`
to a `list[HidraWorkspace]`, round-trip symmetric: `write` accepts N
workspaces and merges them into one `NXentry`'s combined peak index; `read`
returns the same N workspaces back out.

This relies on the existing invariant that each input workspace covers only
unique scan points (and/or other index fields) — no overlap between inputs —
and requires NXstress to record enough on disk to recover the boundary
between inputs at read time. Workspace boundaries are recovered from
**explicit discriminator field(s) on the combined peak index**
(`_peaks.py::PeakIndex`), named by a new config key,
`nxstress.discriminator_fields: list[str]` (default `[]`) — see
[01](01-config-and-test-infra.md), which this spec now depends on directly.
The specific field names in use for any given deployment are a config-level
policy decision, not a per-call argument, and are deliberately not fixed by
this spec — see `open-questions/04b-multi-workspace-nxstress.md` Q2.

This spec retires `open-questions/05-strain-stress-viewer.md` Q2:
StrainStressViewer's "one `HidraWorkspace` per direction in; one `.nxs` file
with provenance out" is exactly this mechanism, with `direction` as one
instance of a discriminator field. Spec 05 depends on this spec and declares
`direction` as a discriminator rather than inventing its own index-extension
machinery.

> **Schema precedent already exists — not a hard blocker.** `_peaks.py::_init`
> already writes `mask`, `scan_point`, `center`, `center_errors`,
> `center_type`, and `sx`/`sy`/`sz` onto `NXreflections`
> ([_peaks.py:100-172](../../pyrs/utilities/NXstress/_peaks.py#L100)), and the
> module's own docstring
> ([_peaks.py:37-40](../../pyrs/utilities/NXstress/_peaks.py#L37)) states only
> `h`/`k`/`l`/`phase_name` (plus the unused `qx`/`qy`/`qz`) are
> schema-required — `mask` explicitly was not part of `PeakCollection` before
> this implementation added it. A discriminator column is the same category
> of extension `NXreflections` already tolerates in practice. Verify against
> `NXstress.html` (the canonical schema doc) and the `nexusformat`-org
> validator once both are added to the repo, and record the outcome — but
> that verification is confirmatory, not a precondition for starting this
> spec. See `open-questions/04b-multi-workspace-nxstress.md` Q1.

---

## Scope

**In scope:**
- Two new config keys under `nxstress` (land in whichever file spec 01
  delivers, e.g. `pyrs/config/pyrs.default.yml`):
  - `discriminator_fields: list[str]` (default `[]`) — names of the fields
    that discriminate input workspaces from one another.
  - `merge_workspaces: bool` (default `false`) — see the empty-config policy
    below.
- Change `NXstress.write` to accept `list[HidraWorkspace]` in place of a
  single `HidraWorkspace` (a length-1 list remains valid, so existing
  single-workspace callers from specs 02/03 continue to work with a trivial
  call-site change).
- Change `NXstress.read` to return `list[HidraWorkspace]` in place of a
  single `HidraWorkspace`.
- A generic, NXstress-internal resolver that, for each configured
  discriminator field name, resolves a value from a given `HidraWorkspace`:
  prefer a matching `@property` on `HidraWorkspace` when one exists, else
  fall back to `HidraWorkspace.get_sample_log_value(name)`. See "Discriminator
  value resolution" under NXstress Changes below.
- Design and implement the discriminator-field mechanism in
  `_peaks.py::PeakIndex` (extend `sort_key`, `validateNoDuplicatePeaks`,
  `_init`, `init_group`, `peakCollectionsFromNexus` to be discriminator-aware,
  and split on read), with discriminator values carried **name-keyed**
  (e.g. a sorted tuple of `(name, value)` pairs), not positionally — see
  "Discriminator representation" below.
- Empty-config policy: `write()` raises if called with more than one
  workspace while `discriminator_fields` is empty, unless
  `merge_workspaces: true` — in which case the workspaces are silently
  merged into one combined index with no discriminator columns at all, and
  `read()` returns a single merged workspace rather than N. This flag is a
  no-op whenever `discriminator_fields` is non-empty; `N == 1` is unaffected
  by either key.
- Merge logic across workspaces in `_InputData.init_group` (concatenate raw
  counts, if present, across inputs), `_Sample.init_group` (concatenate
  sample logs), `_Instrument.init_group` (single shared instrument geometry /
  wavelength — validate consistency across inputs rather than silently
  picking one), and `_Fit.init_group` (concatenate reduced diffraction data
  per mask, filling `NaN` for scan points a given input doesn't contribute to
  a given mask, consistent with existing single-workspace behavior).
- Extend `_validateWorkspaceAndPeaksData` to validate across the full set of
  input workspaces (no-overlap invariant; required logs present in each).
- Update the spec-02/03 call sites (`PeakFittingModel`, `TextureFittingModel`,
  `CombineRunsModel`) to pass/receive a length-1 list. For `CombineRuns`
  specifically, this is a trivial wrap — `write([self._hidra_ws], [])` — not
  a restructuring: **decided** (see
  `open-questions/04b-multi-workspace-nxstress.md` Q3) that
  `combine_project_files`'s in-PyRS pre-merge stays, since it already
  produces the same indistinguishable-merge semantics
  `nxstress.merge_workspaces: true` would, and the `.h5` export path still
  needs the single merged workspace regardless.
- Round-trip test: write N workspaces, read back, assert the N reconstructed
  workspaces equal the N inputs (order-independent).

**Out of scope:**
- Append mode (spec 04c).
- Any GUI wiring beyond the call-site updates above needed to keep specs
  02/03 working as before.
- Deciding discriminator fields beyond what's needed to support `direction`
  (spec 05) and CombineRuns-style merges (spec 03) — further discriminators
  may be added by later specs using the same mechanism.
- Adding any dedicated `@property` accessor for a specific field name (e.g.
  `direction`) to `HidraWorkspace` — the resolver falls back to `SampleLogs`
  until/unless a later spec adds one, per the existing property convention
  (see PyRS Changes below).

---

## PyRS Changes

_None required._ `HidraWorkspace` and `PeakCollection` are consumed as-is, N
at a time instead of one at a time. This was reconsidered mid-design (an
earlier draft proposed a new `HidraWorkspace.get_discriminator_value(name)`
method) and reverted: the property-or-log resolution logic lives entirely in
NXstress's own code (see "Discriminator value resolution" below), which
already works against whatever `HidraWorkspace` exposes today with zero
changes to that class.

**Forward note for later specs:** `HidraWorkspace` already uses plain
`@property` for this exact shape of accessor — `name`, `hidra_project_file`,
`reduction_masks`, `calibration_file`, `sample_log_names`
(`pyrs/core/workspaces.py:55-1155`) are all properties, none are
`()`-called methods. If a later spec (e.g. 05, for `direction`) wants a
first-class dedicated accessor rather than relying on the `SampleLogs`
fallback, it should add a `@property` matching that convention — NXstress's
resolver picks it up automatically, with no change to NXstress itself.

---

## NXstress Changes

### `pyrs/utilities/NXstress/_peaks.py`

- Extend `PeakIndex` with a discriminator slot carrying values **name-keyed**
  — e.g. a sorted tuple of `(name, value)` pairs — not a bare positional
  tuple. This matters: `discriminator_fields` in config could in principle be
  reordered between when a file is written and when it's later read; a
  positional tuple would silently misattribute values in that case, while a
  name-keyed representation resolves correctly regardless of list order.
- `sort_key` includes the discriminator tuple in the ordering key.
- `validateNoDuplicatePeaks` treats the discriminator tuple as part of the
  uniqueness key, so the same `(phase, h, k, l, mask)` arriving from two
  different input workspaces is not flagged as a duplicate as long as their
  discriminator values differ (and their scan points don't overlap).
- `init_group` accepts the peak collections for all N input workspaces and
  writes the combined, sorted index (exact call shape — one flattened list
  with discriminator values attached, vs. one list per workspace — TBD).
  On-disk, each discriminator field becomes one `NXfield` on `NXreflections`,
  named via the existing `allowed_identifier()` sanitizer
  (`_definitions.py:221-231`).
- `peakCollectionsFromNexus` reconstructs the flattened index as today, plus
  a new method that splits the result by discriminator value into N
  per-workspace peak-collection lists.
- Collision guard: raise if a configured discriminator field name collides
  with an existing reserved `NXreflections` column (`h`, `k`, `l`, `mask`,
  `scan_point`, `center`, `center_errors`, `center_type`, `sx`, `sy`, `sz`,
  `qx`, `qy`, `qz`) — see
  `open-questions/04b-multi-workspace-nxstress.md`.

### Discriminator value resolution (new, NXstress-internal)

A small, **bidirectional** resolver, living in `pyrs/utilities/NXstress/`
(exact module/name left to implementation — see open questions): a "get"
half used at write time, and a symmetric "set" half used at read time so a
caller can tell reconstructed workspaces apart by inspecting the same
field it originally supplied.

Get, used at write time for each configured discriminator field name and a
given `HidraWorkspace`:

```python
def _resolve_discriminator_value(ws: HidraWorkspace, name: str):
    if name.isidentifier() and isinstance(getattr(type(ws), name, None), property):
        return getattr(ws, name)
    return ws.get_sample_log_value(name)  # raises if missing or non-constant
```

Set, used at read time on each newly-reconstructed `HidraWorkspace`, mirroring
the get path exactly (property if the type defines a *settable* property,
else a sample log):

```python
def _apply_discriminator_value(ws: HidraWorkspace, name: str, value):
    prop = getattr(type(ws), name, None) if name.isidentifier() else None
    if isinstance(prop, property) and prop.fset is not None:
        setattr(ws, name, value)
    else:
        ws.set_sample_log(name, ws.get_sub_runs(), np.full(len(ws.get_sub_runs()), value))
```

- The `isinstance(..., property)` check (not a bare `hasattr`) matters: it
  guards against a discriminator name accidentally colliding with an
  unrelated method name already defined on `HidraWorkspace` (e.g.
  `save_experimental_data`) and being mismatched as an accessor, which would
  return a bound method instead of a value. The set half additionally checks
  `prop.fset is not None`, so a read-only property with the same name as a
  discriminator field falls back to the log path rather than raising on
  `setattr`.
- The get fallback reuses `HidraWorkspace.get_sample_log_value(name)`
  (`pyrs/core/workspaces.py:693-724`) as-is — it already returns the single
  value when every sub-run agrees, and raises otherwise. No new
  constancy-checking code is needed. The set fallback reuses the existing
  `HidraWorkspace.set_sample_log(name, sub_runs, values, units="")`
  (`pyrs/core/workspaces.py:981`).
- This bidirectional shape exists so that any later spec adding a dedicated
  `@property` (get **and** set — see 05's `direction` property) gets
  round-trip behavior for free: `write()` reads the property off each input
  workspace, and `read()` writes it back onto each reconstructed one, with
  no NXstress-side special-casing per field name.
- `NXstress.py`/`_peaks.py` resolve `discriminator_fields` (and
  `merge_workspaces`) by calling `pyrs.utilities.config.load_config()`
  directly — this module is PyRS's own implementation of NXstress and
  already imports `HidraWorkspace`, `PeakCollection`, and `SampleLogs`
  throughout, so a direct dependency on PyRS's config module is consistent
  with the existing coupling, not a new architectural boundary crossing.

### `pyrs/utilities/NXstress/_input_data.py`, `_sample.py`, `_instrument.py`, `_fit.py`

- `init_group` methods change from accepting one `ws` to accepting
  `list[HidraWorkspace]`; concatenate along the scan-point axis. Reuse the
  merge logic `HidraWorkspace.append_hidra_project` already implements
  in-memory (`pyrs/core/workspaces.py:497`) rather than re-deriving it.
- `_Instrument.init_group` additionally validates that instrument geometry,
  detector shift (if calibrated), and wavelength are consistent across all N
  input workspaces; raise a clear error if they are not (mixed-instrument or
  mixed-calibration merges are not supported by this spec).

### `pyrs/utilities/NXstress/NXstress.py`

- `write(wss: list[HidraWorkspace], peakss: ...)` — exact `peakss` shape
  (flattened vs. per-workspace) TBD in implementation.
- `read(entry_number) -> (list[HidraWorkspace], list[PeakCollection])`.
- `_validateWorkspaceAndPeaksData` extended to the N-workspace case,
  including the empty-`discriminator_fields`/`merge_workspaces` branch: raise
  on `len(wss) > 1` with no discriminator fields configured, unless
  `merge_workspaces` is `true`.

---

## Tests

`tests/unit/pyrs/utilities/NXstress/test_peaks.py`, `test_NXstress.py` (extend):
- Discriminator round-trip: two minimal workspaces with disjoint scan points
  and distinct discriminator values; write, read, assert both are recovered
  exactly.
- No-overlap violation: two workspaces sharing a scan point under the same
  discriminator value raise a clear error at write time.
- Single-workspace back-compat: a length-1 list round-trips identically to
  the pre-04b `HidraWorkspace`-only behavior (regression guard for specs
  02/03).
- Empty-config policy: `write()` with N>1 workspaces and
  `discriminator_fields = []` raises by default; with `merge_workspaces =
  true`, it merges silently and `read()` returns one workspace, not N.
- Resolver behavior: a discriminator name matching a `HidraWorkspace`
  `@property` uses the property; a name matching an unrelated *method* name
  (not a property) falls through to the `SampleLogs` fallback rather than
  returning a bound method; a name absent from both raises via
  `get_sample_log_value`; a name present but non-constant across a
  workspace's scan points raises.
- Resolver symmetry: for a discriminator name backed by a get/set property,
  write then read recovers the value via the property on each reconstructed
  workspace; for a name with no matching property (or a read-only one),
  write then read recovers the value via `get_sample_log_value` instead.
- Discriminator-field-reorder regression: write with
  `discriminator_fields = ["a", "b"]`, then read with
  `discriminator_fields = ["b", "a"]` (simulating config drift between write
  and read) — assert values still resolve correctly by name, not position.

`tests/integration/test_nxstress_viewer_roundtrip.py` (extend):
- CombineRuns regression: confirm `export_project_files`'s `.nxs` branch
  still works once wrapped in a length-1 list —
  `NXstress.write([self._hidra_ws], [])` — per the resolved Q3 (pre-merge
  stays; no restructuring of `combine_project_files`).

---

## Delivered Feature

> **For downstream NXstress consumers (not yet user-facing):**
> `NXstress` can now write and read multiple `HidraWorkspace` instances
> within a single `.nxs` `NXentry`, provided their scan points (and/or other
> index fields) don't overlap, and provided the deployment's config names at
> least one discriminator field (or explicitly opts into merging them
> indistinguishably). This is a library-level capability in this pass — no
> new GUI action is added; existing viewers continue to pass a single
> workspace. It is the foundation for spec 05 (StrainStressViewer,
> discriminating by `direction`). Spec 03 (CombineRuns) evaluated switching
> to this mechanism and decided against it — its existing PyRS-level
> pre-merge already produces equivalent indistinguishable-merge semantics,
> and is needed regardless for the unaffected `.h5` export path.

---

## Verification

- Cross-check against `NXstress.html` and the `nexusformat`-org validator
  once both land in the repo; record the outcome in
  `open-questions/04b-multi-workspace-nxstress.md` Q1. Not a precondition for
  starting implementation — see the schema-precedent note above.
- `pytest tests/unit/pyrs/utilities/NXstress/` — all pass, including new
  multi-workspace cases.
- `pytest tests/integration/test_nxstress_viewer_roundtrip.py` — all pass, no
  regression in specs 02/03.
