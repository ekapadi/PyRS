# 11 — Defer to Second Pass

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** — (cross-cutting; not part of the phased schedule)
**Depends on:** all subspecs implemented so far (currently: 01, 02, 03)

---

## Overview

Each subspec's own text narrows scope in specific places — decisions to
leave something unwired, disabled, or otherwise incomplete on purpose, made
during implementation rather than anticipated by the original spec drafts.
Those decisions are individually reasonable and were each discussed/agreed
at the time, but they're scattered across commit messages and one-off
conversations. This document collects them in one place so a second pass —
which will need to revisit most or all of them fairly soon after the first
full pass through specs 01-10 lands — has a concrete checklist instead of
having to rediscover each issue by re-reading diffs or code.

Add a new numbered item here (not a new file) each time a subspec's
implementation consciously narrows scope or leaves something for later.
Cross-reference the originating subspec and its
[PR-implementation-notes.md](PR-implementation-notes.md) entry.

---

## Deferred items

### 1. `TextureFittingViewer`'s legacy Save/Save As stay permanently disabled

**From:** [02](02-peak-and-texture-nxstress.md) /
[PR-implementation-notes.md § Spec 02](PR-implementation-notes.md#spec-02--nxstress-io-for-peakfitting--texture-viewers).

`self.saveAction`/`self.saveAsAction` are `.setEnabled(False)` at `__init__`
and never re-enabled anywhere else in `texture_fitting_viewer.py` — found
during spec 02, predates it, and it's unclear whether this was a deliberate
design choice (e.g. Texture Fitting's `.h5` save path was never considered
production-ready) or a plain oversight. Spec 02 left it exactly as-is —
commented, not wired to `Config` — rather than guessing at a fix; only the
new `Save as NXstress…` action is `Config["nxstress.enable"]`-driven.

**Second pass needs to:** determine the original intent (check with the
team/git blame beyond this branch's history if possible). If it was an
oversight, add proper enable-on-successful-load logic, `Config`-gated the
same way `PeakFittingViewer`'s `_init_widgets` pattern already works.

### 2. `TextureFittingModel`'s `.nxs` load is model/NXstress-round-trip only

**From:** [02](02-peak-and-texture-nxstress.md) /
[PR-implementation-notes.md § Spec 02](PR-implementation-notes.md#spec-02--nxstress-io-for-peakfitting--texture-viewers).

Loading a `.nxs` file populates `TextureFittingModel.ws`/`self.fit_result`
but is **not** wired into `fit_table_operator`/the plot overlay — a
deliberate, discussed narrowing of scope, not a bug. Root cause: the
"current fit result" the Save/plot-overlay machinery actually reads lives on
the *view* (`TextureFittingViewer.fit_summary.fit_table_operator.fit_result`),
populated only by interactively running a fit; there's no clean hook
analogous to `PeakFittingModel`'s `PyRsCore.register_hidra_workspace` fix
(item 3 below) for this case.

**Second pass needs to:** decide the mechanism for surfacing
NXstress-loaded peaks through the existing fit-table/plot-overlay path (or
decide that a different UI affordance — e.g. a distinct "view NXstress
results" mode — fits better than forcing it through the interactive-fit
machinery).

### 3. `PeakFittingModel`'s `.nxs` load leaves `fitted`/`difference` as `None`

**From:** [02](02-peak-and-texture-nxstress.md) /
[PR-implementation-notes.md § Spec 02](PR-implementation-notes.md#spec-02--nxstress-io-for-peakfitting--texture-viewers).

Guarded in `PeakFittingCrtl.plot_diff_and_fitted_data` (`fit_result.fitted is
not None`) rather than crashing, but the fitted spectrum itself isn't
reconstructed. This is the *same* gap already tracked as Phase 5 in the
[overview plan](README.md) (specs
[08](08-fit-spectrum-prereqs.md)/[09](09-fit-spectrum-nxstress.md)) — not a
new finding — flagged here too since spec 02 is the first place a permanent
code guard for it landed, so it's easy to forget this is the same work item.

**Second pass needs to:** nothing new beyond what 08/09 already schedule;
this entry exists purely as a cross-reference so the guard in
`peak_fitting_crtl.py` isn't mistaken for a separate, unscheduled gap.

### 4. NXstress multi-file load explicitly rejected

**From:** [02](02-peak-and-texture-nxstress.md).

`PeakFittingModel.load_hidra_project` raises `ValueError` if more than one
file is given and the first is `.nxs`. Matches spec 02's stated Phase-1
scope and spec [04c](04c-nxstress-append.md)'s future append work. Noted
here for completeness/cross-reference, not a new finding — no second-pass
action beyond what 04c already schedules.

### 5. Adjacent pre-existing bugs found but deliberately not touched

**From:** [02](02-peak-and-texture-nxstress.md).

Found while reading the surrounding code, confirmed broken, explicitly left
alone as unrelated to spec 02's scope:

- `TextureFittingViewer`'s "Load state" menu action —
  `self.controller.load()` → `TextureFittingModel.from_json(filename)`,
  which requires a second positional argument (`fit_range_table`) that's
  never supplied. This is an unrelated peak-range-JSON feature, not the
  Hidra-project load path (that goes through `FileLoad`/`load_projectfile`
  instead, which spec 02 did wire up NXstress support into).
- `PeakFittingViewer`'s orphaned `do_save_fit` method — not connected to any
  signal/action anywhere in the codebase (confirmed by grep); looks like
  dead code from a prior refactor.

**Second pass (or a dedicated cleanup pass) needs to:** decide whether to
fix `TextureFittingViewer`'s "Load state" action (supply the missing
`fit_range_table`, or remove the action if it's truly obsolete) and whether
`do_save_fit` should be wired up or deleted.

### 6. `PeakFittingViewer`/`TextureFittingViewer`'s "Save as NXstress…" don't check for instrument geometry

**From:** [03](03-combine-runs-nxstress.md) /
[PR-implementation-notes.md § Spec 03](PR-implementation-notes.md#spec-03--nxstress-io-for-combineruns-viewer).

Spec 03 found and fixed a real bug: `HidraWorkspace.load_hidra_project`
only loaded instrument geometry when `load_raw_counts=True` — an
unintentional coupling, now decoupled (geometry loading is always
attempted, tolerating absence with a logged warning). `CombineRunsViewer`'s
auto-prompt was updated to check
`self._parent.model._hidra_ws.get_instrument_setup() is not None` before
offering the NXstress dialog, since `NXstress.write()` requires geometry
unconditionally. `PeakFittingViewer`/`TextureFittingViewer`'s persistent
"Save as NXstress…" `QAction`s (added in spec 02) have no equivalent check —
they're currently gated only on `Config["nxstress.enable"]`, not on whether
the *currently loaded* workspace actually has geometry. Since
`PeakFittingModel._load_multiple_file` passes the same
`load_detector_counts=False` to the same now-fixed method, a `.h5` file
genuinely lacking geometry (confirmed to exist — `tests/data/HB2B_1327.h5`)
loaded via Browse, followed by "Save as NXstress…", will still crash.

**Second pass needs to:** add a geometry-presence check to
`PeakFittingViewer`/`TextureFittingViewer`'s NXstress-action enablement —
likely re-checked at the point a project finishes loading (`load_and_plot`/
`load_hidra_project_file` completion), toggling
`actionSaveAsNXstress`/`saveAsNXstressAction`'s `.setEnabled(...)` in
combination with the existing `Config["nxstress.enable"]` check, the same
way `CombineRunsViewer`'s auto-prompt does it for the auto-prompt case.
