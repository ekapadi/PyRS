# 07 — ManualReductionViewer NXstress Hookup

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** 4
**Depends on:** — (none within this plan; see Overview)

---

## Overview

Wire NXstress into `reduce_hidra_workflow`'s existing, automatic save step,
so a reduction can produce a `.nxs` file in addition to (or instead of) the
current `.h5` output.

**Corrected hookup point.** Earlier drafts of this spec targeted
`HB2BReductionManager.save_project` (via spec 06). Both parts of that were
wrong: the class is `ReductionController`
(`pyrs/interface/manual_reduction/pyrs_api.py`), not `HB2BReductionManager`
(an unrelated class elsewhere); and `save_project` has **zero callers
anywhere in the codebase** — it isn't where saving actually happens. The
real, currently-functional save path is `reduce_hidra_workflow`'s automatic
`reducer.save_diffraction_data(project_file_name)` call
(`pyrs_api.py:348`), which runs as an inherent side effect of every
reduction — there is no separate "Save"/"Save as…" dialog or menu action in
this viewer at all. **This spec no longer depends on spec 06** — neither of
spec 06's items (the orphaned `save_project` stub; two unrelated
`nexus_conversion.py` input-parsing gaps) touches this save step.

**No GUI action, therefore no auto-write-both-formats concern.** The other
four NXstress-wired viewers (specs 02, 03, 05) each gate two independent,
manually-clicked actions ("Save" for `.h5`, "Save as NXstress…" for `.nxs`)
by `legacy_io.enable`/`nxstress.enable`, and a single click never writes
both formats — that rule exists to protect a user's expectation of what
*their click* does. `reduce_hidra_workflow` has no click to protect the
meaning of: it writes automatically, so it simply **writes once per
currently-enabled format** — one file if only one format is enabled, both
files (same basename) if both are. This is not an ambiguity requiring a
tie-break; it's the direct, correct consequence of "both formats are
currently enabled" applied to a path with no per-click choice.

**Extension is never caller-controlled**, exactly as in the GUI viewers —
only the *basename* varies with `project_file_name` (auto-derived from the
input NeXus filename when `None`, or whatever base a caller supplies when
given explicitly). Any extension on a caller-supplied `project_file_name`
is stripped and ignored, never validated against and never a reason to
raise — the extension(s) actually written are always exactly whichever of
`nxstress.extension`/`legacy_io.extension` are currently enabled.

---

## Scope

**In scope:**
- `reduce_hidra_workflow` (`pyrs/interface/manual_reduction/pyrs_api.py`):
  replace the hardcoded `+ ".h5"` default-extension logic and the single
  `reducer.save_diffraction_data(project_file_name)` call with: derive the
  basename (from `project_file_name` if given, stripping any extension; or
  from the input NeXus filename if `None`), then write once per
  currently-enabled format (`legacy_io.enable` → `.h5` via
  `reducer.save_diffraction_data`; `nxstress.enable` → `.nxs` via
  `NXstress(path, "w").write(hidra_ws, [])`).
- Config validation reuse: `load_config()`'s existing "at least one format
  enabled" rule (spec 01) already guarantees this function always writes
  at least one file.
- Round-trip test: reduce a run with only `nxstress.enable: true`, confirm
  `.nxs` is written and readable; with both enabled, confirm both files are
  written with the same basename.

**Out of scope:**
- Any change to `ReductionController.save_project` (spec 06 — independent,
  not required here).
- Any new GUI dialog, menu action, or file-dialog filter — none exists to
  extend; this hookup is entirely inside `reduce_hidra_workflow`.
- Append mode (spec 04c) — not used by this pathway.
- Multi-workspace input (spec 04b) — manual reduction produces one
  workspace per save.
- Fit-spectrum data (spec 09).
- Detector-calibration fidelity fixes (spec 09).

---

## PyRS Changes

_None._ `reduce_hidra_workflow` is itself a PyRS/GUI-boundary function
(`pyrs/interface/manual_reduction/pyrs_api.py`), not a PyRS-core data-object
change — the edit lives entirely in the "NXstress Changes" section below.

---

## NXstress Changes

### `pyrs/interface/manual_reduction/pyrs_api.py`

- `reduce_hidra_workflow(nexus, output_dir, progressbar, ..., project_file_name=None)`:

  ```python
  cfg = load_config()

  if project_file_name is None:
      basename = os.path.basename(nexus).split(".")[0]
  else:
      basename = os.path.splitext(os.path.basename(project_file_name))[0]
  base_path = os.path.join(output_dir, basename)

  # ... existing NeXus conversion + reduction unchanged ...

  if cfg.legacy_io.enable:
      reducer.save_diffraction_data(base_path + cfg.legacy_io.extension)
  if cfg.nxstress.enable:
      with NXstress(base_path + cfg.nxstress.extension, "w") as nxs:
          nxs.write(hidra_ws, [])
  ```

  (Illustrative — the existing file-exists/overwrite-permission checks at
  `pyrs_api.py:292-311` apply per resolved path, once per enabled format.)
- `peakss` is always `[]`: `ManualReductionModel`/`ReductionController` has
  no `PeakCollection` concept at all — reduction produces a `HidraWorkspace`
  only. This is a fully valid, already-supported input to `NXstress.write`
  (see spec 03's identical finding for `CombineRunsModel`).

---

## Tests

`tests/integration/test_nxstress_viewer_roundtrip.py` (extend):
- Manual-reduction save-as-NXstress round-trip: `nxstress.enable: true`,
  `legacy_io.enable: false` — confirm only a `.nxs` file is written and is
  readable via `NXstress.read()`.
- Both-enabled case: `nxstress.enable: true`, `legacy_io.enable: true` —
  confirm both a `.h5` and a `.nxs` file are written, same basename, both
  independently valid/readable.
- Legacy-only regression: `nxstress.enable: false`, `legacy_io.enable: true`
  (today's default) — confirm behavior is unchanged from the current
  hardcoded-`.h5` path.
- Extension-stripping: pass an explicit `project_file_name` with a
  mismatched extension (e.g. `"foo.nxs"` while only `legacy_io.enable` is
  true); confirm the extension is ignored and a correctly-suffixed `.h5`
  file is written under basename `foo` — no error raised.

---

## Delivered Feature

> **For end users and instrument scientists:**
> Reduction can now produce NeXus-compliant NXstress (`.nxs`) output, in
> addition to or instead of the existing `.h5` output — controlled purely
> by config (`nxstress.enable`, `legacy_io.enable`), not by any new button
> or menu action. With both formats enabled, every reduction writes both
> files automatically, under the same base name — useful for validating
> NXstress output against the established `.h5` format during the
> transition period.

---

## Verification

- Reduce a run with `nxstress.enable: true`, `legacy_io.enable: false`;
  confirm a `.nxs` file is written and readable.
- Reduce a run with both enabled; confirm both `.h5` and `.nxs` files are
  written, same basename.
- Reduce a run with the current default (`legacy_io.enable: true`,
  `nxstress.enable: false`); confirm behavior is unchanged from today.
- `pytest tests/integration/test_nxstress_viewer_roundtrip.py` — all pass
  (no regression in earlier specs).
