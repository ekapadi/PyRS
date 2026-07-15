# 09 — Fit Spectrum & Calibration Fidelity (NXstress)

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** 5 (NXstress side)
**Depends on:**
- [07 — Append support & ManualReduction hookup](07-append-and-manual-reduction-nxstress.md)
- [08 — Fit spectrum & calibration fidelity (PyRS)](08-fit-spectrum-prereqs.md)

---

## Overview

Wire the PyRS capabilities added in spec 08 into the NXstress writer and
reader, replacing the last remaining NaN placeholders with real data.
After this spec, NXstress files produced by PyRS will be fully populated:
fit spectra, correct detector geometry, and (if available) the beam-intensity
profile.

---

## Scope

**In scope:**
- Populate `diffractogram/fit` and `diffractogram/fit_errors` from the fit
  engine's new reconstructed-spectrum method (`_fit.py:426-429, 486-487`)
- Fix the L2 arm-shift round-trip in `_instrument.py:138-140` using the new
  `DENEXDetectorGeometry.arm_shift_applied` property
- Populate NXbeam intensity profile in `_instrument.py:127` if the workspace
  carries one (or confirm and close as "not applicable" per spec 08 findings)
- Fix `_sample.py:107` STRESS_FIELD dimensions using the confirmed shape
  from spec 08
- Update user-facing docs and release notes to remove NaN-placeholder warnings
  added in spec 02

**Out of scope:**
- Any remaining `NotImplementedError` in `fields.py` not exercised by the
  test suite at this point
- GUI changes (all viewers already wired; no new actions needed)

---

## PyRS Changes

_None_ — all PyRS-side changes were made in spec 08.

---

## NXstress Changes

### `pyrs/utilities/NXstress/_fit.py` — fit spectrum (L426-429, L486-487)

In `_Diffractogram.init_group(ws, maskName, peakss)`:
- Call the new fit-engine method (from spec 08) to obtain
  `model_intensity` and `model_variance` for each `(mask, scan_point)`.
- Write these into the `diffractogram/fit` and `diffractogram/fit_errors`
  NXfields instead of initializing to `NaN`.
- If the method is unavailable for a given scan point (e.g., fit did not
  converge), fall back to `NaN` for that point only with a logged warning.

In `_Diffractogram.diffractogramFromNexus(dg)`:
- Read `fit` and `fit_errors` fields if present; expose them in the return
  value so callers can use the reconstructed spectrum (e.g., for residual
  visualization in a future viewer feature).

### `pyrs/utilities/NXstress/_instrument.py` — L2 arm-shift (L138-140)

Use `DENEXDetectorGeometry.arm_shift_applied` (from spec 08) to determine
whether to write the raw L2 or the arm-shift-corrected L2 into the
`NXdetector`. Update `instrumentFromNexus` correspondingly so the
round-trip is lossless.

### `pyrs/utilities/NXstress/_instrument.py` — NXbeam profile (L127)

Per the spec-08 finding: either populate the NXbeam field from the workspace
attribute identified in spec 08, or add a one-line comment closing the TODO
as "not applicable — no beam profile data path exists in PyRS" and remove the
TODO marker.

### `pyrs/utilities/NXstress/_sample.py` — STRESS_FIELD shape (L107)

Apply the confirmed shape from spec 08 and remove the TODO comment.

---

## Tests

`tests/unit/pyrs/utilities/NXstress/test_fit.py` (extend):
- Write a `.nxs` file with a fitted workspace where the fit engine returns
  a reconstructed spectrum; assert `diffractogram/fit` is not all-NaN and
  has shape `(n_sub_runs, n_2theta)`.
- Write a workspace where one sub-run did not converge; assert that sub-run's
  `fit` row is NaN but others are not.

`tests/unit/pyrs/utilities/NXstress/test_instrument.py` (extend):
- Round-trip a calibrated `DENEXDetectorGeometry` through NXstress;
  assert the read-back geometry has `arm_shift_applied == True` and the
  L2 value matches the original.

---

## Delivered Feature

> **For end users and downstream NXstress consumers:**
> NXstress files produced by PyRS are now fully populated — no NaN placeholders
> remain for data that PyRS actually computes:
>
> - **Reconstructed fit spectra** (`diffractogram/fit`, `diffractogram/fit_errors`)
>   are written for every sub-run where the peak fit converged. These can be
>   used by external tools for residual analysis and quality assessment.
> - **Calibrated detector geometry** (L2, arm shift) round-trips correctly —
>   a calibrated measurement read back from NXstress gives the same geometry
>   as the original.
>
> PyRS NXstress files are now fully compatible with external NXstress-aware
> analysis software.

---

## Verification

- `pytest tests/unit/pyrs/utilities/NXstress/` — all pass.
- `pytest tests/integration/` — all pass (no regression in earlier specs).
- Write a `.nxs` from a real HB2B dataset and inspect in a NeXus browser:
  confirm `diffractogram/fit` contains a plausible model profile.
- Run the `nexusformat` NXstress validator (with
  `nxstress.use_production_names = true`) on the output file — no errors.
- Cross-check with `tests/scripts/cis_tests/NXstress_demo_script.py` —
  update it to use the fully-populated output and confirm it runs cleanly.
