# 10 — Flip Defaults: NXstress Becomes Primary

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** 6
**Depends on:** [09 — Fit spectrum & calibration fidelity (NXstress)](09-fit-spectrum-nxstress.md)

---

## Overview

Complete the phased-replacement decision (README Section 4, Q2): promote
NXstress to the default save format across all NXstress-aware viewers, and
demote `HidraProjectFile` (`.h5`) to a legacy-read-only path. Users can still
open existing `.h5` files; they can no longer save to `.h5` from the affected
viewers (unless the config flag is explicitly set).

**Trigger criteria** for entering this spec (to be confirmed at the end of
spec 02 / start of spec 03):
- All NXstress round-trip tests pass.
- At least one real-data smoke test has been run by a scientist and signed off.
- No open correctness bugs against the NXstress writer or reader.

---

## Scope

**In scope:**
- Flip `nxstress.default_extension` to `".nxs"` and
  `nxstress.use_production_names` to `true` in `config/pyrs.default.yml`
- Remove `.h5` save options from the file-dialog filters of the viewers
  that have been NXstress-wired (PeakFitting, Texture, CombineRuns,
  StrainStress, ManualReduction)
- Keep `.h5` in all *load* dialog filters (legacy read-only)
- Deprecation note in the GUI (e.g., tooltip or status-bar message) when a
  user opens a `.h5` file
- Release notes / migration guide for existing users

**Out of scope:**
- DetectorCalibrationViewer (not NXstress-wired; unchanged)
- Removing the `HidraProjectFile` code itself (a separate cleanup, not part
  of this plan)

---

## PyRS Changes

_None._

---

## NXstress / GUI Changes

### `config/pyrs.default.yml`

```yaml
nxstress:
  use_production_names: true
  default_extension: ".nxs"
```

### Viewer file-dialog filters (five viewers)

For each NXstress-wired viewer, remove `H5 (*.h5)` / `HDF (*.hdf)` /
`HDF5 (*.hdf5)` from the **save** dialog filter. Keep them in the **load**
dialog filter. Affected files:
- `pyrs/interface/peak_fitting/peak_fitting_viewer.py`
- `pyrs/interface/texture_fitting/texture_fitting_viewer.py`
- `pyrs/interface/combine_runs/combine_runs_viewer.py`
- `pyrs/interface/strainstressviewer/strain_stress_view.py`
- `pyrs/interface/manual_reduction/manual_reduction_viewer.py`

### Deprecation hint

When a user successfully opens a `.h5` file in any of the above viewers,
display a one-time status-bar message (or tooltip):
> "This file is in the legacy HiDRA format (.h5). Use **File → Save as
> NXstress…** to save in the current NXstress format."

---

## Tests

- Regression suite: `pytest tests/` — full test run, all specs. No failures.
- Smoke test: open a legacy `.h5` file in PeakFittingViewer; confirm it loads;
  confirm the deprecation hint appears; confirm **Save** now defaults to `.nxs`.
- Smoke test: attempt to save as `.h5` (by typing the extension manually in
  the save dialog); confirm the viewer either rejects it with a clear message
  or routes it through the NXstress writer regardless.

---

## Delivered Feature

> **For end users:**
> NXstress (`.nxs`) is now the default save format across all PyRS viewers.
> You no longer need to choose "Save as NXstress…" — the standard **Save**
> action produces a `.nxs` file.
>
> Existing `.h5` project files can still be opened (they will continue to
> work). When you do open a legacy `.h5` file, PyRS will remind you to save
> it in the new NXstress format.
>
> **Migration:** to convert an existing `.h5` project to NXstress format,
> open it in the appropriate viewer and use **File → Save** (or **Save As**).
> The resulting `.nxs` file is equivalent and can be used in place of the
> original `.h5` file going forward.

---

## Verification

- `pytest tests/` — full suite passes.
- Open a `.h5` file in each of the five affected viewers — confirm load
  succeeds and deprecation hint is shown.
- **Save** in each viewer — confirm a `.nxs` file is written by default.
- Open the written `.nxs` files in a NeXus browser and run the
  `nexusformat` NXstress validator — no errors.
- `tests/scripts/cis_tests/NXstress_demo_script.py` — runs cleanly.
