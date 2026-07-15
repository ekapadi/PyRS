# 06 — Manual Reduction PyRS Prerequisites

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** 4 (PyRS side)
**Depends on:** — (independent of all NXstress specs; can be worked in parallel)

---

## Overview

Before NXstress can be wired into the ManualReductionViewer, two PyRS-side
gaps must be closed:

1. `HB2BReductionManager.save_project` is currently `NotImplementedError`
   (`manual_reduction/pyrs_api.py:211`). The manual-reduction save path
   does not work at all today.
2. Two branches in `pyrs/core/nexus_conversion.py` (L118, L374) are also
   `NotImplementedError`. Their relationship to the manual-reduction save
   path must be confirmed and resolved if they are in scope.

This spec is **PyRS-only** — no NXstress code is touched. It can be
developed independently of specs 01–05 and merged whenever it is ready;
spec 07 blocks on it.

---

## Scope

**In scope:**
- Implement `HB2BReductionManager.save_project` in
  `manual_reduction/pyrs_api.py:211`
- Audit `nexus_conversion.py:118` and `nexus_conversion.py:374` —
  determine whether either branch is reachable from the manual-reduction
  save path; resolve (implement or safely guard) whichever is
- Unit and integration tests for the newly-implemented save path

**Out of scope:**
- Any NXstress code
- The NXstress hookup for ManualReductionViewer (spec 07)
- Manual-reduction load paths (already working)

---

## PyRS Changes

### `pyrs/interface/manual_reduction/pyrs_api.py` — `save_project` (L211)

Implement the method. The surrounding context (`HB2BReductionManager`) holds
a `HidraWorkspace`; the save should write it out via `HidraProjectFile` (the
existing pattern used by all other viewers). The method signature and
expected output path convention should match what `ManualReductionViewer`
expects.

Specifically check how `ReductionApp.save_diffraction_data` (L348) is
currently called and whether `save_project` should delegate to it, wrap it,
or replace it.

### `pyrs/core/nexus_conversion.py` — L118 and L374

Audit each `NotImplementedError`:
- If the branch is reachable from the manual-reduction save path: implement
  it as part of this spec.
- If the branch is unreachable from the save path but reachable from other
  paths: file a separate issue and add a clear comment pointing to it.
- If the branch is dead code: remove it.

---

## NXstress / GUI Changes

_None._

---

## Tests

- `tests/unit/pyrs/interface/manual_reduction/test_pyrs_api.py` (new or
  extend): unit test `save_project` with a minimal `HidraWorkspace` —
  assert a valid `.h5` file is written.
- `tests/integration/test_manual_reduction_save.py` (new): run a minimal
  reduction workflow end-to-end and confirm the output file is loadable by
  `HidraProjectFile`.

---

## Delivered Feature

> **For end users:**
> Manual reduction now correctly saves its output to a project file. Previously,
> the **Save project** action in the Manual Reduction viewer raised an internal
> error. After this fix, reduced data is written to a `.h5` project file that
> can be loaded in the Peak Fitting and Strain/Stress viewers.

---

## Verification

- GUI smoke test: run a manual reduction in ManualReductionViewer; use
  **Save project**; confirm a `.h5` file is written and loadable in
  PeakFittingViewer.
- `pytest tests/unit/pyrs/interface/manual_reduction/` — all pass.
- `pytest tests/integration/test_manual_reduction_save.py` — all pass.
