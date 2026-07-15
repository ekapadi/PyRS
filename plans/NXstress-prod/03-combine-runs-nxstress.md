# 03 — NXstress I/O for CombineRuns Viewer

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** 1
**Depends on:** [01 — Config infrastructure & test framework](01-config-and-test-infra.md)

---

## Overview

Wire `NXstress` into the CombineRunsViewer's export path. After combining
multiple `HidraProjectFile`s into a merged workspace, users can now export the
result as a `.nxs` file in addition to the existing `.h5` export.

Because NXstress does not yet support appending to an existing NXentry (that
arrives in spec 07), the CombineRuns integration is **fresh-write only**:
the user must combine first, then export as a single NXstress file.

---

## Scope

**In scope:**
- New `Export as NXstress…` action in `combine_runs_viewer.py` with a
  `NXstress (*.nxs)` file-dialog filter.
- New export path in `combine_runs_model.py` that calls
  `NXstress.write(merged_ws, peakss)` when the destination is `*.nxs`.
- Round-trip integration test.

**Out of scope:**
- Append-to-existing-NXentry (spec 07).
- Any change to the existing `.h5` export path.
- Loading a `.nxs` file into CombineRunsViewer (not a supported workflow —
  the viewer only combines inputs, not reads back a combined result).

---

## PyRS Changes

_None._

---

## NXstress / GUI Changes

### `pyrs/interface/combine_runs/combine_runs_model.py`

- `export_project_files(filename, merged_ws, peakss)`: add a suffix-dispatch
  branch — if `Path(filename).suffix == ".nxs"`, write via
  `NXstress(filename, "w").write(merged_ws, peakss)` instead of the
  `HidraProjectFile` path.
- Note: the merged workspace passed to `NXstress.write` must have already
  had `save_experimental_data` / `save_reduced_diffraction_data` resolved
  in-memory. Verify that the merge step (`combine_project_files`) populates
  the workspace fields NXstress expects.

### `pyrs/interface/combine_runs/combine_runs_viewer.py`

- Add `Export as NXstress…` button / `QAction`, wired to a
  `export_as_nxstress` slot that opens a `QFileDialog` with filter
  `"NXstress (*.nxs)"` and calls `model.export_project_files`.

---

## Tests

`tests/integration/test_nxstress_viewer_roundtrip.py` (extend):

- **CombineRuns round-trip:** create two minimal workspaces using spec-01
  fixtures; merge via `CombineRunsModel.combine_project_files`; export to a
  `.nxs` path; read back with `NXstress.read()`; assert sub-run counts and
  sample-log arrays match the merged workspace.
- **Suffix routing:** assert `.h5` export still goes through `HidraProjectFile`
  (no regression).

---

## Delivered Feature

> **For end users:**
> Combined runs can now be exported as a NXstress (`.nxs`) file:
>
> *Combine Runs → Export as NXstress…*
>
> This allows combined datasets from multiple `.h5` project files to be
> archived in a single NeXus-compliant NXstress file. Existing `.h5` export
> is unaffected.
>
> **Note:** the NXstress format currently requires a complete combined
> workspace to be exported in one step. Incrementally appending additional
> runs to an existing `.nxs` file will be supported in a later release (spec 07).

---

## Verification

- GUI smoke test: load two `.h5` files in CombineRunsViewer, combine,
  **Export as NXstress…**, confirm a `.nxs` file is written.
- Confirm existing **Export** (`.h5`) works without regression.
- `pytest tests/integration/test_nxstress_viewer_roundtrip.py` — all pass.
