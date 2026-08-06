# 04c — NXstress Append Mode (library only)

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** 3
**Depends on:** [04b — Multi-workspace NXstress I/O](04b-multi-workspace-nxstress.md)

---

## Overview

Add the ability to extend an **already-written** `NXentry` with more scan
points, rather than requiring every write to create a fresh entry.

This is a different capability than it may first appear: `NXstress.write`
already supports accumulating multiple reductions into one `.nxs` file today
— each call adds a new, auto-numbered `NXentry`
([NXstress.py:149](../../pyrs/utilities/NXstress/NXstress.py#L149)), and the
guard at [NXstress.py:151-152](../../pyrs/utilities/NXstress/NXstress.py#L151)
only fires on an accidental name collision. What's missing is the ability to
grow *one* `NXentry`'s data — e.g., a second reduction pass whose scan points
belong to the same combined index as an earlier write, not a new
data-reduction condition. Per the plan's own semantics
(README.md §2.4, "Multi-NXentry semantics"), separate conditions still get
separate `NXentry`s; append is for adding more of the *same* condition's data.

This was originally bundled with the ManualReductionViewer hookup (the old
spec 07) on the rationale that append and that hookup "share a common
primitive." That primitive is no longer shared: the reduction pathway is
decided to always create a fresh file (see
`open-questions/07-manual-reduction-nxstress.md`), so append gains **no GUI
entry point in this pass**. This spec delivers append as a tested library
capability only — usable by future callers (tests, scripts, or a future GUI
action) without a corresponding menu action anywhere in the GUI today.

### Architecture: in-place resize/insert, not read-merge-rewrite

Two designs were considered:
1. Read the existing entry back into `HidraWorkspace`/`PeakCollection`
   objects (reusing `NXstress.read()`), append the new data to that list in
   memory, and rewrite the entry using 04b's N-workspace merge-and-write path
   wholesale.
2. Resize and insert directly into each affected on-disk dataset, computing
   insertion positions from the existing arrays without ever reconstructing
   the existing entry as `HidraWorkspace`/`PeakCollection` objects.

**Decided: (2).** The concern driving this is that a normal reduction/append
cycle should not have to round-trip the *existing* entry's data through
PyRS's outer types just to grow it — particularly raw detector counts, which
can be large. Append therefore operates directly against the on-disk
`NXfield` arrays (via `.nxdata`) to determine conflicts and insertion points,
and resizes/inserts in place. The **new** data being appended is still
supplied the normal way — `list[HidraWorkspace]` + `list[PeakCollection]`,
matching 04b's `write()` signature — only the *existing* side of the merge
avoids the round-trip.

### Scope: all position-aligned groups, not just input_data and peaks

An entry's on-disk groups fall into two position-aligned families, plus one
family that isn't position-sensitive at all:

| Family | Groups | Aligned by |
|---|---|---|
| Peak-index family | `_peaks.py` (`PEAKS`/`NXreflections`), `_fit.py::_PeakParameters`, `_fit.py::_BackgroundParameters` (`peak_parameters`/`background_parameters` under `FIT`) | The compound `PeakIndex` sort key. `_PeakParameters.init_group`/`_BackgroundParameters.init_group` build their rows via `sorted(peakss, key=_Peaks.PeakIndex.sort_key)` ([_fit.py:87](../../pyrs/utilities/NXstress/_fit.py#L87)) — **the exact same order as the peaks index**, so their rows are positionally aligned with it, not independently keyed. |
| Scan-point family | `_input_data.py` (`detector_counts`), `_sample.py` (`SAMPLE_DESCRIPTION` per-scan-point logs), `_fit.py::_Diffractogram` (`diffractogram`/`diffractogram_errors`) | `scan_point`. |
| Name-keyed, no insertion needed | `_instrument.py::_Masks` | Mask *name*, not position — `init_group` already accepts an existing `masks` group and extends it by name ([_instrument.py:317](../../pyrs/utilities/NXstress/_instrument.py#L317)); no new work needed here. |

**Decided:** this spec covers the full peak-index family and the full
scan-point family, coordinated so that append never leaves one group's rows
inserted without the corresponding rows in every other group in its family.
A partial append (e.g., growing `detector_counts` without growing the
diffractogram) would leave the entry internally inconsistent — not an
acceptable interim state for a correctness-focused library feature.

### Entry targeting

`NXstress(path, "a")` with no further argument targets the **last** existing
`NXentry` in the file — the common case (one entry being grown over time)
needs no extra argument. An optional `entry_number` targets a specific
earlier entry instead: `NXstress(path, "a", entry_number=N)`.

### Conflict policy

If any scan point (scan-point family) or full compound-index row
(peak-index family) in the new data would duplicate one already present in
the target entry, the append is rejected: raise `RuntimeError` — not the
`ValueError` `validateNoDuplicatePeaks` raises for the analogous fresh-write
duplicate case, since this represents a violated invariant on already-
committed data, not an expected/anticipated bad-input case a caller would
routinely hit and want to catch. The conflict check runs against **all**
affected groups before any resize/insert call is made, so a rejected append
is a true no-op — the on-disk entry is left byte-for-byte unchanged.

After raising, the `NXstress` instance is left unusable for any further
`write()` call in the same session — the caller must re-open rather than
continue against a session that already detected a corrupted assumption
about the target entry's contents.

---

## Scope

**In scope:**
- Peak-index family: implement the append/insertion path for `_peaks.py`'s
  compound index (the `# TODO` at `_peaks.py:180-181`) and, in lockstep, for
  `_fit.py::_PeakParameters.init_group` / `_BackgroundParameters.init_group` —
  the same computed insertion positions must be applied to all three.
- Scan-point family: implement the append/insertion path for
  `_input_data.py:44-46,63-72` (`detector_counts`, on both write and read),
  `_sample.py`'s per-scan-point logs, and `_fit.py::_Diffractogram.init_group`
  — the same computed insertion positions must be applied to all three.
- `NXstress.py`: remove the guard at `NXstress.py:151-152` for the append
  case; add entry targeting (`entry_number`, defaulting to the last entry);
  dispatch `write()` to the append-in-place path when opened with mode `"a"`.
- Conflict detection: compare new scan points / index rows against the
  existing on-disk arrays (read via `.nxdata`, not reconstructed as
  `HidraWorkspace`/`PeakCollection`) before any mutation; raise `RuntimeError`
  and invalidate the instance on conflict, per the policy above.
- Round-trip test: write, then append, into the same entry; verify all five
  groups' contents are combined and mutually consistent.

**Out of scope:**
- Any GUI menu action, file-dialog filter, or viewer wiring. No viewer in
  this plan calls append in this pass.
- ManualReductionViewer hookup (now a fresh-write-only spec: see
  [07 — ManualReduction hookup](07-manual-reduction-nxstress.md)).
- `_instrument.py::_Masks` — already append-capable, name-keyed, no change
  needed.
- Fit-spectrum data (spec 09).
- Detector-calibration fidelity fixes (spec 09).

---

## PyRS Changes

_None._ Append operates entirely within `pyrs/utilities/NXstress/`, against
on-disk NXstress structures and the new data's `HidraWorkspace`/
`PeakCollection` objects — no change to PyRS's own data-object classes.

---

## NXstress Changes

### `pyrs/utilities/NXstress/_peaks.py`

- `init_group` — implement the insertion path described in the `# TODO` at
  L180-181: given the existing on-disk `PeakIndex` arrays (read via
  `.nxdata`, using 04b's name-keyed discriminator resolution to reconstruct
  each existing row's sort key) and the new, sorted incoming index entries,
  compute insertion positions via the shared sort key (`PeakIndex.sort_key`,
  extended for discriminators per 04b) and resize/insert at those positions.
- Expose the computed insertion positions (or an equivalent shared helper)
  so `_fit.py`'s peak-index-family groups can apply the identical positions.

### `pyrs/utilities/NXstress/_fit.py`

- `_PeakParameters.init_group`, `_BackgroundParameters.init_group` — accept
  an existing `NXparameters` group and the insertion positions computed by
  `_peaks.py`; resize and insert each parameter dataset at those same
  positions.
- `_Diffractogram.init_group` — accept an existing `NXdata` group and the
  scan-point-family insertion positions; resize and insert
  `diffractogram`/`diffractogram_errors`/`scan_point` at those positions.

### `pyrs/utilities/NXstress/_sample.py`

- `init_group` — accept an existing `NXsample` group; compute scan-point
  insertion positions (shared with `_input_data.py` and `_Diffractogram`)
  and resize/insert each per-scan-point log field at those positions.

### `pyrs/utilities/NXstress/_input_data.py`

- `init_group(ws, data=None)` — when `data` is an existing `NXdata` group
  (append mode), compute scan-point insertion positions and extend
  `detector_counts`/`scan_point` at those positions rather than raising.
- `readSubruns(ws, data)` — unaffected by this spec's write-side scope, but
  confirm it still reads a post-append file correctly (the on-disk layout
  after append is just a larger, still-sorted array — no reader change
  should be needed).

### `pyrs/utilities/NXstress/NXstress.py`

- `__init__(path, mode, *, entry_number: int | None = None)` — `entry_number`
  is only meaningful with `mode="a"`; defaults to the last existing entry.
- `write(wss, peakss)` — when opened in append mode, resolve the target
  entry, run the conflict check across all affected groups first (raise
  `RuntimeError` and mark the instance invalid on any conflict, before any
  mutation), then delegate to the append-aware `init_group` methods for both
  families, passing the shared computed insertion positions where required.
  When opened in `"w"` mode, behavior is unchanged from 04b.

---

## Tests

`tests/integration/test_nxstress_append.py` (new):
- Write a minimal dataset to a new `.nxs` file; append a second,
  non-overlapping dataset to the same entry (default "last entry" target).
- Read back; assert combined scan-point count equals the sum of both writes;
  assert peak-index entries from both writes are present, correctly ordered,
  and that `peak_parameters`/`background_parameters`/`diffractogram` rows
  are still positionally aligned with the peaks index after the insert.
- `entry_number` override: write two entries, append to the first (not the
  last) via explicit `entry_number`; confirm only the targeted entry grew.
- Conflict case: attempt to append a scan point (or peak-index row, under
  the same discriminator value) that duplicates one already in the target
  entry; assert `RuntimeError` is raised, the on-disk entry is unchanged
  (byte-for-byte, or field-by-field equality check), and a subsequent
  `write()` call on the same `NXstress` instance also raises.

`tests/unit/pyrs/utilities/NXstress/test_peaks.py`, `test_fit.py`,
`test_sample.py`, `test_input_data.py` (extend):
- Insertion-point correctness for each family, independent of the
  integration-level round-trip (e.g., inserting into the middle of an
  existing sorted array, not just at the end).

---

## Delivered Feature

> **For downstream NXstress consumers (not yet user-facing):**
> An `NXentry` can now be incrementally grown: `NXstress(path, "a")` extends
> the last-written entry (or a specifically targeted one, via
> `entry_number`) with more scan points, rather than requiring a fresh file
> or a fresh entry per write. All five position-aligned data groups (raw
> counts, sample logs, diffractogram, peak index, and fit parameters) stay
> mutually consistent after an append. This pass ships the capability as a
> tested library feature only — no PyRS viewer currently exposes an "append"
> action. Wiring a GUI entry point (if a future use case needs one) is a
> separate, not-yet-scheduled follow-up.

---

## Verification

- `pytest tests/integration/test_nxstress_append.py` — all pass.
- `pytest tests/unit/pyrs/utilities/NXstress/` — all pass, no regression
  from 04b.
- Confirm (by inspection, not test) that no GUI file exists that calls
  `NXstress(..., "a")` — this spec is library-only by design.
- Manual check: append into the middle of an existing sorted index (not
  just the end) and confirm ordering and family-alignment are preserved —
  the integration test above should cover this, but is worth a direct
  `h5dump`/`nexusformat` inspection at least once during implementation.
