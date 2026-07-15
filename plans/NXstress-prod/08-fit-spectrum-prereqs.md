# 08 — Reconstructed Fit Spectrum & Calibration Fidelity (PyRS)

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** 5 (PyRS side)
**Depends on:** — (independent of NXstress; can be worked in parallel with specs 01–07)

---

## Overview

This spec closes the PyRS-side gaps that block spec 09 from replacing the
final NaN placeholders in NXstress files:

1. **Reconstructed fit spectrum** — PyRS's peak-fit engine returns parameter
   values but does not currently produce a full-length reconstructed
   model profile on the original two-theta grid. NXstress requires
   `diffractogram/fit` and `diffractogram/fit_errors` datasets; without a
   model spectrum these are NaN.
2. **Calibrated instrument geometry round-trip** — `DENEXDetectorGeometry`
   has no accessor that reports whether the arm shift has been applied.
   `HidraProjectFile.read_instrument_geometry` (L510 FIXME) returns the same
   type for calibrated and uncalibrated geometries, so the calibration state
   is silently lost when round-tripping through NXstress.
3. **Beam-intensity profile** — currently no data path carries this from the
   reduction pipeline to NXstress.
4. **`STRESS_FIELD` shape verification** — the shape of the `SampleLogs`
   `STRESS_FIELD` entry written by `_sample.py:107` has never been verified
   against a real dataset.

Like spec 06, this is **PyRS-only** and can be developed independently.

---

## Scope

**In scope:**
- Fit engine: new method returning reconstructed model spectrum per
  `PeakCollection` × mask × scan_point
- `DENEXDetectorGeometry`: new property/accessor indicating arm-shift state
- `HidraProjectFile.read_instrument_geometry` (L510 FIXME): return correct
  calibrated type when calibration data is present
- Beam-intensity profile: identify or create a data path from reduction;
  mark optional if unmeasured
- `STRESS_FIELD` shape: verify against a real HB2B dataset and document

**Out of scope:**
- Any NXstress code (that is spec 09)
- GUI changes

---

## PyRS Changes

### Fit engine — reconstructed spectrum

Files: `pyrs/peaks/` (fit-engine implementations), likely
`pyrs/core/peak_profile_utility.py`.

Add a method (on the fit-engine base class or on `PeakCollection` itself)
that, given the original two-theta axis, evaluates the fitted peak model
+ background and returns:
- `model_intensity: np.ndarray` — shape `(n_scan_points, n_2theta)`
- `model_variance: np.ndarray` — same shape (propagated from fit
  parameter uncertainties, or `NaN` if not computable)

The method should be callable after `fit_multiple_peaks` without re-running
the fit.

### `pyrs/core/instrument_geometry.py::DENEXDetectorGeometry`

Add a boolean property `arm_shift_applied: bool` (or equivalent) that
records whether `DENEXDetectorShift` has been folded into the geometry.
This must be set correctly by the existing code paths that apply shifts.

### `pyrs/projectfile/file_object.py::read_instrument_geometry` (L510)

Fix the FIXME: when the project file contains calibration data, return
a type (or a tagged tuple) that preserves the calibrated state, so the
NXstress writer (spec 09) can interrogate `arm_shift_applied`.

### Beam-intensity profile

Trace the reduction pipeline to determine if a beam-intensity profile
(monitor counts or equivalent) is ever stored in `HidraWorkspace` or
`SampleLogs`. If it is: document the attribute name so spec 09 can read it.
If it is not: mark `NXbeam` intensity profile as permanently optional and
close `_instrument.py:127` as "not applicable".

### `STRESS_FIELD` shape

Load a real HB2B dataset that includes a `STRESS_FIELD` sample-log entry.
Check the shape and dtype `_sample.py:107` would receive. Update the
docstring/comment with the confirmed shape. If the shape is wrong, fix
the write/read code in `_sample.py`.

---

## NXstress / GUI Changes

_None._

---

## Tests

- `tests/unit/pyrs/peaks/test_peak_collection.py` (extend): after fitting a
  synthetic diffractogram, call the new reconstructed-spectrum method and
  assert the output shape is `(n_sub_runs, n_2theta)` and values are
  finite.
- `tests/unit/pyrs/core/test_instrument_geometry.py` (extend): construct a
  `DENEXDetectorGeometry`, apply a shift, assert `arm_shift_applied` is
  `True`; assert it is `False` before the shift.
- `tests/unit/pyrs/projectfile/test_file_object.py` (extend): write a
  calibrated geometry to a project file, read it back, assert the returned
  object indicates calibrated state.

---

## Delivered Feature

> **Internal / contributor-facing:**
> The PyRS fit engine now exposes the reconstructed fitted spectrum, making
> it available for export to NXstress and for other potential uses (e.g.,
> residual plots). Instrument geometry now correctly preserves calibration
> state through a read/write cycle. These are infrastructure improvements;
> the user-visible payoff arrives in spec 09.

---

## Verification

- `pytest tests/unit/pyrs/peaks/` — all pass including new spectrum test.
- `pytest tests/unit/pyrs/core/test_instrument_geometry.py` — all pass.
- `pytest tests/unit/pyrs/projectfile/test_file_object.py` — all pass.
- Manual inspection: fit a peak on a real dataset; print the reconstructed
  spectrum; overlay with the raw data to confirm it is plausible.
