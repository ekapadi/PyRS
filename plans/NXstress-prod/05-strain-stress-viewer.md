# 05 — StrainStressViewer NXstress Hookup

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** 3
**Depends on:** [04 — NXstress internal cleanup](04-nxstress-internal-cleanup.md)

---

## Overview

Wire NXstress into the StrainStressViewer so that multi-direction stress
measurements (directions 11, 22, 33) can be saved and loaded as a single
`.nxs` file.

The current viewer loads N separate `HidraProjectFile`s per direction into
three parallel slots (`filenames_11/22/33`). The NXstress equivalent is a
single NXentry whose `NXreflections` compound peak index is extended with a
`direction` axis, so all three directions coexist within one entry.

> **⚠ Schema check required before implementation begins.**
> Before modifying `_peaks.py::PeakIndex`, verify against the canonical
> NXstress.xml schema whether adding a `direction` axis to `NXreflections`
> is conformant, or whether a different mechanism (multi-NXentry, dedicated
> stress-field subgroup, etc.) is the schema-intended approach. Update
> the decision in README.md Section 4 (Q3) accordingly and revise the
> implementation items below if needed.

---

## Scope

**In scope:**
- NXstress.xml schema review (decision gate — must happen first)
- Extend `_peaks.py::PeakIndex` with a `direction` field (or adopt the
  schema-preferred alternative)
- Update `sort_key`, `validateNoDuplicatePeaks`, `_init`, `init_group`,
  and `peakCollectionsFromNexus` in `_peaks.py`
- Wire NXstress read path into `strainstressviewer/model.py` —
  `load_hidra_project_file` / `load_hidra_project_files` — so a single
  `.nxs` file replaces the N-files-per-direction pattern
- Add **Save as NXstress…** action on the StrainStressViewer that writes
  all three directions into one `.nxs` file
- Round-trip integration test

**Out of scope:**
- Resolving `NotImplementedError` methods in `fields.py` beyond those
  actually hit on the read path (fix only what the test exercises)
- Append support (spec 07)
- Any change to the existing JSON state-save or CSV export paths

---

## PyRS Changes

- `pyrs/dataobjects/fields.py` — resolve any `NotImplementedError` in
  `StrainField` / `StressField` that is exercised by the read-back path
  (i.e., when reconstructing a `StressField` from the direction-indexed
  peak collections returned by `NXstress.read()`). Fix only the methods
  the round-trip test actually calls.
- `pyrs/core/workspaces.py` — confirm `HidraWorkspace` can represent
  (or cleanly hold) sample-log content from a direction-merged measurement.
  If a direction-aware container is needed, design it here.

---

## NXstress Changes

### Schema-driven PeakIndex extension

_Subject to the schema check outcome._

Assumed baseline (direction axis on `NXreflections`):
- Add `direction: str` field to `_peaks.py::PeakIndex` (e.g., `"11"`,
  `"22"`, `"33"`).
- Update `sort_key` to include direction in the ordering tuple.
- Update `validateNoDuplicatePeaks` to treat direction as part of the
  uniqueness key.
- Add `direction` dataset to `NXreflections` in `_init` and `init_group`.
- Update `peakCollectionsFromNexus` to reconstruct per-direction
  `PeakCollection` lists.

### `pyrs/interface/strainstressviewer/model.py`

- `load_hidra_project_file(filename, direction)`: if `*.nxs`, call
  `NXstress(filename, "r").read()` and extract the subset of peak
  collections matching the requested direction.
- `load_hidra_project_files(filenames, direction)`: if a single `.nxs`
  file is supplied (rather than N `.h5` files), read all directions in
  one call and populate the three direction slots.
- Add a method `save_as_nxstress(filename)` that assembles all three
  direction workspaces and peak collections, attaches direction labels,
  and calls `NXstress(filename, "w").write(...)`.

### `pyrs/interface/strainstressviewer/strain_stress_view.py`

- Add **File → Save as NXstress…** action with filter `"NXstress (*.nxs)"`.
- Extend the load file dialog to include `"NXstress (*.nxs)"`.

---

## Tests

`tests/integration/test_nxstress_viewer_roundtrip.py` (extend):

- Construct minimal workspaces and peak-collection lists for all three
  directions using spec-01 fixtures.
- Call `model.save_as_nxstress(path)`.
- Load back with `model.load_hidra_project_files([path], direction)` for
  each direction.
- Assert that the reconstructed `StressField` matches the CSV-summary
  output produced from the original inputs.

---

## Delivered Feature

> **For end users:**
> Multi-direction stress measurements can now be saved and loaded as a single
> NXstress (`.nxs`) file from the Strain/Stress viewer:
>
> - *Strain/Stress → File → Save as NXstress…*
>
> Instead of managing three separate `.h5` files (one per direction), the
> entire stress dataset — all three measurement directions — is stored in one
> NXstress-compliant file. This file can be shared with other NXstress-aware
> analysis tools.
>
> Existing `.h5` project files and the JSON state-save continue to work
> as before.

---

## Verification

- GUI smoke test: load three `.h5` files (one per direction) in
  StrainStressViewer, compute stress, **File → Save as NXstress…**, confirm
  a single `.nxs` file is written; then load the `.nxs` back and confirm
  the stress field is reproduced.
- `pytest tests/integration/test_nxstress_viewer_roundtrip.py` — all pass.
- `pytest tests/unit/pyrs/utilities/NXstress/` — all pass including updated
  `test_peaks.py` / `test_peaks_read.py` for the direction axis.
