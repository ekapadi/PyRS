# 04 — NXstress Internal Cleanup (Phase 2 TODOs)

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** 2
**Depends on:** [02](02-peak-and-texture-nxstress.md), [03](03-combine-runs-nxstress.md)

---

## Overview

Close the NXstress-internal TODOs from Section 2.1 of the README that require
no PyRS data-model changes. After this spec, NXstress files produced by the
GUI viewers will contain correct sample positions, consistent mask naming, a
parameterized instrument name, and verified scan-orientation data. The `NaN`
placeholders for sx/sy/sz are replaced with real values.

---

## Scope

**In scope:**
- Restore `sx`/`sy`/`sz` from `SampleLogs` in `_peaks.py:235-239`
- Reconcile default vs. named mask storage convention (`_fit.py:546-549`)
- Complete disallowed-character coverage in `_definitions.py::allowed_identifier` (L229)
- Parameterize instrument name in `_instrument.py:70`
- Detector rotation-order cross-check and fix in `_instrument.py:165`
- Audit `HidraProjectFile` legacy log-name patches (`file_object.py:404`, `:494`)
  and confirm / update the key names NXstress emits

**Out of scope:**
- Flipping `nxstress.use_production_names` default to `true` — deferred until
  the upstream `nexusformat` validator bug is resolved; when it is, simply
  update `pyrs/resources/application.yml`.
- Any PyRS data-model changes.
- Any GUI viewer changes.

---

## PyRS Changes

- `pyrs/projectfile/file_object.py` — audit lines 404 and 494 (legacy
  log-name FIXMEs). Determine the canonical log names the reduction pipeline
  emits. No code changes required if the audit confirms NXstress already uses
  the correct names; otherwise patch the relevant `_sample.py` or
  `_peaks.py` key lookups.

---

## NXstress Changes

### `pyrs/utilities/NXstress/_peaks.py` — restore sx/sy/sz (L235-239)

Uncomment and fix the `logs['sx']`/`logs['sy']`/`logs['sz']` block.
Reconcile the log-key names against what the reduction pipeline actually
stores in `SampleLogs`. If the keys differ from `'sx'`/`'sy'`/`'sz'`,
use the correct names (or fall back to `NaN` gracefully if the keys are
absent, with a logged warning rather than a hard failure).

### `pyrs/utilities/NXstress/_fit.py` — mask naming convention (L546-549)

Define a single convention for storing default vs. named masks:
- The default mask always uses the key `DEFAULT_TAG`
  (`HidraConstants.DEFAULT_MASK`) in the diffractogram dict.
- Named masks use the mask name directly.
Apply this convention consistently in both the writer (`init_group`) and the
reader (`diffractogramFromNexus`, `masksFromNexus`). Add a test that writes
a file with both default and named masks and reads it back.

### `pyrs/utilities/NXstress/_definitions.py` — allowed_identifier (L229)

Extend `allowed_identifier` to cover at minimum `$`, whitespace, and any
other characters disallowed by the NXstress/HDF5 group-name rules. Add unit
tests for all newly-covered cases.

### `pyrs/utilities/NXstress/_instrument.py` — instrument name (L70)

Replace the hardcoded `"HB2B"` with a value drawn from the `HidraWorkspace`
(e.g., from a sample-log entry or a new workspace attribute). If no instrument
name is available, fall back to `"HB2B"` with a logged warning. This makes
the writer usable at other beamlines without a code change.

### `pyrs/utilities/NXstress/_instrument.py` — rotation order (L165)

Cross-check the rotation sequence used in `NXtransformations` against the
`DENEXDetectorGeometry` conventions in `pyrs/core/instrument_geometry.py`.
Fix the order if it is wrong. Add a regression test that writes a geometry,
reads it back, and asserts the rotation components are numerically equal
(within floating-point tolerance).

---

## Tests

- Add / extend tests in `tests/unit/pyrs/utilities/NXstress/test_instrument.py`
  for rotation-order correctness and instrument-name parameterization.
- Add tests in `tests/unit/pyrs/utilities/NXstress/test_sample.py` for
  sx/sy/sz round-trip.
- Add tests in `tests/unit/pyrs/utilities/NXstress/test_fit.py` for the
  unified mask-naming convention.
- Add tests in `tests/unit/pyrs/utilities/NXstress/test_definitions.py` for
  the extended `allowed_identifier`.

---

## Delivered Feature

> **For end users and downstream NXstress consumers:**
> NXstress files produced by PyRS now contain more complete and correct data:
>
> - **Sample positions** (sx, sy, sz) are populated from the measurement logs
>   rather than being left as `NaN`.
> - **Mask naming** is consistent — the same mask name means the same thing
>   in every part of the file, whether the default mask or a named user mask.
> - **Instrument name** is taken from the workspace rather than being hardcoded,
>   making PyRS NXstress files usable at beamlines other than HB2B.
> - **Detector orientation** has been verified against the reduction pipeline's
>   rotation convention.
>
> These improvements make PyRS NXstress files more reliably readable by
> external NXstress-aware software.

---

## Verification

- `pytest tests/unit/pyrs/utilities/NXstress/` — all tests pass including new
  ones added in this spec.
- Write a `.nxs` file from a real HB2B dataset; inspect sx/sy/sz fields
  with `h5dump` or the `nexusformat` Python API — confirm they are non-NaN.
- Write a `.nxs` file and open it in the `nexusformat` validator
  (with `nxstress.use_production_names = true` temporarily, to exercise
  the production-name path even before it becomes the default).
