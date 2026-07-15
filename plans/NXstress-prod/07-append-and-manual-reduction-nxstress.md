# 07 — NXstress Append Support & ManualReduction Hookup

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** 4 (NXstress side)
**Depends on:**
- [05 — StrainStressViewer hookup](05-strain-stress-viewer.md)
- [06 — Manual reduction PyRS prerequisites](06-manual-reduction-prereqs.md)

---

## Overview

Two related items are bundled here because they share a common primitive —
append-to-existing-NXentry:

1. **Append support** — lift the `NotImplementedError` guards in
   `NXstress.py`, `_input_data.py`, and `_peaks.py` that prevent writing
   to an existing NXentry. After this, a second reduction run can be
   accumulated into the same `.nxs` file.
2. **ManualReductionViewer hookup** — wire NXstress into
   `ManualReductionModel.save_project` (now implemented in spec 06) so that
   reduced data can be saved as `.nxs` in addition to `.h5`.

---

## Scope

**In scope:**
- Implement `_input_data.py:44-46` — append `detector_counts` on write
- Implement `_input_data.py:63-72` — append `detector_counts` to workspace on read
- Remove the `NotImplementedError` guard in `NXstress.py:151-152` once
  the subgroup-level appends are working
- Implement the compound-index append path in `_peaks.py:180-181`
- Wire NXstress into `ManualReductionModel.save_project` (suffix dispatch
  on `.nxs` vs `.h5`)
- Add `NXstress (*.nxs)` option to the ManualReductionViewer save dialog
- Round-trip test: two reductions appended into one file

**Out of scope:**
- Fit-spectrum data (spec 09)
- Detector-calibration fidelity fixes (spec 09)

---

## PyRS Changes

_None_ — spec 06 covers the PyRS prerequisites.

---

## NXstress Changes

### `pyrs/utilities/NXstress/_input_data.py`

- `init_group(ws, data=None)` — when the NXdata group already exists in
  the file (append mode), extend the `detector_counts` dataset along the
  scan-point axis rather than raising.
- `readSubruns(ws, data)` — when the workspace already has detector counts
  loaded, merge the new scan points rather than raising.

### `pyrs/utilities/NXstress/_peaks.py`

- `init_group(peakss, logs)` — implement the scan-point append path
  described in the `# TODO` at L180-181: sort the incoming `PeakIndex`
  entries, locate the insertion point in the existing sorted index, and
  extend the HDF5 datasets accordingly.

### `pyrs/utilities/NXstress/NXstress.py`

- `write(ws, peakss)` — remove the guard at L151-152 that raised on
  an existing NXentry. Instead, delegate to the append-aware
  `init_group` / `_InputData` / `_Peaks` methods.

### `pyrs/interface/manual_reduction/pyrs_api.py` (or model layer)

- In `HB2BReductionManager.save_project` (or the model it delegates to):
  add a suffix-dispatch branch — if the requested output path ends in
  `.nxs`, call `NXstress(path, "w" or "a").write(ws, peakss)`.

### `pyrs/interface/manual_reduction/manual_reduction_viewer.py`

- Extend the save-file dialog to offer `"NXstress (*.nxs)"` as a filter
  option alongside `"HiDRA project (*.h5)"`.

---

## Tests

`tests/integration/test_nxstress_append.py` (new):
- Reduce a minimal dataset; write to a new `.nxs` file.
- Reduce a second (distinct sub-run) dataset; append to the same file.
- Read back; assert combined sub-run count equals sum of both reductions;
  assert peak-index entries from both reductions are present and ordered.

`tests/integration/test_nxstress_viewer_roundtrip.py` (extend):
- Manual-reduction save-as-NXstress round-trip using the spec-01 fixtures.

---

## Delivered Feature

> **For end users:**
> Two improvements ship together:
>
> 1. **Incremental NXstress accumulation** — after reducing a run and saving
>    it to a `.nxs` file, you can reduce a subsequent run and append it to the
>    same file. This allows a single NXstress file to accumulate data across
>    multiple reduction sessions without creating separate files per run.
>
> 2. **Manual Reduction saves to NXstress** — the Manual Reduction viewer's
>    **Save project** action now supports the `.nxs` format in addition to
>    `.h5`:
>
>    *Manual Reduction → Save project → NXstress (*.nxs)*

---

## Verification

- GUI smoke test: reduce two runs in ManualReductionViewer; save the first
  as `.nxs`; reduce the second and **append** to the same `.nxs` file.
  Open the file with a NeXus browser and confirm both sub-run blocks are
  present.
- `pytest tests/integration/test_nxstress_append.py` — all pass.
- `pytest tests/integration/test_nxstress_viewer_roundtrip.py` — all pass
  (no regression in earlier specs).
