# PR Implementation Notes

Companion to the [NXstress GUI Hookup plan](README.md). One entry per
subspec, added as each is implemented — this is where findings, corrected
assumptions, and fixed-along-the-way bugs get recorded (not
`docs/ground_truths.md`, which is reserved for a different purpose). See
[11-defer-to-second-pass.md](11-defer-to-second-pass.md) for the companion
list of narrow-scope/deferred decisions made along the way.

---

## Spec 02 — NXstress I/O for PeakFitting & Texture viewers

Implemented in commit `c2deb2b6` ("subspec 02"). Wired `.nxs` save/load into
`PeakFittingViewer`/`TextureFittingViewer` per
[02-peak-and-texture-nxstress.md](02-peak-and-texture-nxstress.md), alongside
three findings and three prerequisite bug fixes surfaced during
implementation.

### Findings

**`NXstress` must always be used as a context manager.** `NXstress.write()`/
`.read()` (`pyrs/utilities/NXstress/NXstress.py`) both raise `RuntimeError`
unless entered via `with NXstress(path, mode) as nx: nx.write(...)` /
`nx.read()`. There is no bare `NXstress(path, mode).write(...)` form, even
though it appears that way in the original phase-plan pseudocode — every
call site in specs 02 onward needs the `with` form.

**An NXstress-loaded `PeakFittingModel` session needs explicit registration
with `PyRsCore`'s session dict, or plotting crashes.** `PeakFittingCrtl`'s
plotting path routes through `PyRsCore._reduction_service`
(`HB2BReductionManager`) `self._session_dict[project_name]`, populated today
only by the `.h5` load path's `init_session(project_name)` (no workspace)
followed by its own file-based load. Simply setting `self.hidra_workspace`
after an `NXstress.read()` leaves that registry empty, and the first plot
attempt raises `KeyError`. Fix:
`HB2BReductionManager.init_session(session_name, hidra_ws=...)`
(`pyrs/core/reduction_manager.py:129-153`) already accepts a pre-built
workspace — wrapped as `PyRsCore.register_hidra_workspace(project_name, hidra_ws)`
(`pyrs/core/pyrscore.py`) and called from `PeakFittingModel.load_hidra_project`'s
`.nxs` branch. `TextureFittingModel` has no equivalent registry (it holds a
raw `HidraWorkspace` directly), so this doesn't apply there — see
[11-defer-to-second-pass.md](11-defer-to-second-pass.md) item 2 for what that
means for Texture's `.nxs` load.

**Importing `pyrs.utilities.config` writes to the real `$HOME` at import
time, not lazily.** `neutrons_standard.Config` is a process-wide singleton
constructed at module-import time (`Config = _Config()` in the installed
`neutrons_standard` package), and its `__init__` unconditionally calls
`reload()` → `persistBackup()`, which writes `~/.pyrs/application.yml.bak` to
whatever `HOME` is set at that moment — confirmed by reading the installed
package directly, not inferred. Before this spec, only NXstress-specific
tests imported `pyrs.utilities.config`, always behind the `default_config`
fixture (`HOME` → `tmp_path`). Once a production module imports it (as
`peak_fitting_model.py`/`texture_fitting_model.py` now do), *any* test that
imports that module — including pre-existing GUI tests with no such
isolation — transitively imports it too, and pytest imports test modules
during collection, *before* any fixture (even autouse) runs, so a
fixture-based guard cannot intercept whichever test file's collection
happens to trigger the first import. Fixed with a one-time, narrowly-scoped
sandbox at the top of `tests/conftest.py`
(`_presandbox_neutrons_standard_config_home`): redirect `HOME` to a throwaway
directory, import `pyrs.utilities.config` once, restore the real `HOME`
immediately after — not a session-wide `HOME` remap, which would risk
breaking Mantid/Qt/matplotlib config-dir assumptions elsewhere in this
GUI+scientific-computing suite. Any new production module that starts
importing `pyrs.utilities.config` for the first time doesn't need any
additional change — this sandbox already covers the first-import moment
regardless of which module triggers it.

### Pre-existing bugs found and fixed as prerequisites

Spec 02's own "no regression to the existing `.h5` path" requirement was
untestable while these were live, since they sit directly on the methods the
spec needed to extend. All three predate this spec and are unrelated to
NXstress itself.

1. **`TextureFittingModel.save_fit_result` crashed unconditionally.** It
   referenced `self.parent._curr_file_name` three times
   (`texture_fitting_model.py`, was lines 156-160), but `TextureFittingModel`
   is constructed as `TextureFittingModel(peak_fit_core)` (`pyrs_main.py:75`,
   `texture_fitting/start.py:16`) and never sets `self.parent` anywhere —
   confirmed by direct grep, not speculative. Fixed by tracking
   `self._curr_file_name` directly (set in `load_hidra_project_file`,
   mirroring `PeakFittingModel`'s already-working equivalent).
2. **`texture_fitting_viewer.py`'s `__init__` assigned `self.saveAction`
   twice** — once for "Save", again for "Save as" — so only the "Save as"
   `QAction` object was retained under that name; the "Save" action's
   reference was lost. Fixed by splitting into `self.saveAction`/
   `self.saveAsAction`, each with its own attribute.
3. **`TextureFittingModel.load_hidra_project_file` never closed its
   `HidraProjectFile` read handle.** Discovered while testing the fix for
   bug 1: a subsequent `save_fit_result(out_file_name == filename)` (update
   in place) failed with `OSError: Unable to synchronously open file (file
   is already open for read-only)`. `load_hidra_project` reads eagerly, so
   closing the handle right after is safe — matches the established pattern
   elsewhere (`PyRsCore.load_hidra_project`,
   `PeakFittingModel._load_multiple_file`).

### Files touched

- `pyrs/interface/peak_fitting/{peak_fitting_model,peak_fitting_viewer,peak_fitting_crtl}.py`
- `pyrs/interface/texture_fitting/{texture_fitting_model,texture_fitting_viewer}.py`
- `pyrs/interface/designer/peakfitwindow.ui` (new `actionSaveAsNXstress`)
- `pyrs/interface/gui_helper.py` (new `impose_extension` helper)
- `pyrs/core/pyrscore.py` (new `register_hidra_workspace`)
- `tests/conftest.py` (HOME sandboxing)
- New: `tests/unit/pyrs/interface/{conftest.py,peak_fitting/,texture_fitting/}`,
  `tests/integration/{conftest.py,test_nxstress_viewer_roundtrip.py}`
- Extended: `tests/ui/{test_peak_fitting,test_texture_fitting}.py`

### Test results

293 unit + 85 integration + 5 gui tests passing (20 new), full suite;
`~/.pyrs` confirmed untouched in the real home directory before and after
every run.

---

## Spec 03 — NXstress I/O for CombineRuns Viewer

Implemented per [03-combine-runs-nxstress.md](03-combine-runs-nxstress.md).
Wired `.nxs` export into `CombineRunsViewer`, alongside the existing `.h5`
export, which continues to work unchanged. Surfaced one real architecture
mismatch in the spec's draft text, two adjacent pre-existing bugs, and one
genuinely blocking `pyrs/core`/NXstress-internals finding — all resolved
through direct discussion before/during implementation.

### Finding: no persistent "Export" action exists to mirror

Spec 03's draft assumed a persistent, independently-`.setEnabled()`-able
"Export" `QAction`/button already existed for `.h5`, alongside which a new
NXstress one would sit (mirroring spec 02's PeakFitting/TextureFitting
pattern). `CombineRunsViewer` has no such control — export happens through
`FileLoad.saveFileDialog()`, auto-triggered right after combining (gated by
`self._auto_prompt_export`, added specifically so the GUI test can suppress
it and drive the dialog manually). **Decided (user): no redesign of the
existing GUI structure.** Added a second, matching auto-prompt dialog for
NXstress that fires right after the first — each format's appearance gated
by its own config flag at the call site
(`Config["legacy_io.enable"]`/`Config["nxstress.enable"]`), realizing
"enablement" as "does this dialog get offered at all," the natural analog
for an auto-prompt UI with no persistent button to grey out.

### Blocking finding: instrument-geometry loading was coupled to `load_raw_counts`

`HidraWorkspace.load_hidra_project` (`pyrs/core/workspaces.py`) only called
`self._load_instrument(hidra_file)` when `load_raw_counts=True` — an
apparently unintentional coupling. `CombineRunsModel.combine_project_files`
always calls with `load_raw_counts=False` (a deliberate, already-documented
choice — see `open-questions/03-combine-runs-nxstress.md` Q1), so the merged
workspace it produces **never had instrument geometry, in any real usage**.
`NXstress.write()` requires geometry unconditionally (no `None` fallback,
`_instrument.py:109`), so `export_project_files(".nxs")` would have crashed
on every real combine-then-export attempt — discovered via this spec's own
round-trip test, not a hypothetical. **This is not scoped to spec 03 either**:
`PeakFittingModel._load_multiple_file` passes the same `load_detector_counts=False`
to the same underlying method, so a real user loading an existing `.h5` file
via Browse in PeakFittingViewer (spec 02, already shipped) and clicking
"Save as NXstress…" likely hits the same crash today — spec 02's own NXstress
tests never caught it because they all build workspaces in-memory rather
than exercising the real load-then-export path.

**Fix (user-directed, root cause):** decoupled instrument-geometry loading
from `load_raw_counts` in `HidraWorkspace.load_hidra_project` — geometry is
now always attempted, independent of the flag, and **no caller's
`load_raw_counts`/`load_detector_counts` value needed to change** (per the
user's explicit requirement — this was not to become a lever any GUI code
needs to touch). Not every project file necessarily has geometry recorded
(confirmed directly: `tests/data/HB2B_1327.h5`, used by this suite's own
existing GUI test, genuinely has none), so absence is tolerated with a
logged warning (`_logger.warning(...)`, catching the `KeyError`
`HidraProjectFile.read_instrument_geometry()` raises when the group is
missing) rather than raising. Per the user's direction, the NXstress
auto-prompt in `CombineRunsViewer.load_project_files` additionally checks
`self._parent.model._hidra_ws.get_instrument_setup() is not None` before
offering the NXstress dialog — the dialog is silently skipped (not popped,
analogous to a disabled/greyed-out action) when the merged workspace has no
geometry, regardless of `Config["nxstress.enable"]`.
**Follow-up needed**: `PeakFittingViewer`/`TextureFittingViewer`'s "Save as
NXstress…" menu actions (persistent, unlike CombineRuns' auto-prompt) don't
yet have an equivalent geometry-presence check on their enablement — tracked
in [11-defer-to-second-pass.md](11-defer-to-second-pass.md).

### Second finding: NXstress's own reader couldn't handle its own "no peaks" sentinel

`CombineRunsModel` always calls `NXstress.write(ws, [])` — CombineRuns has no
`PeakCollection` concept at all. The *writer* already has a documented
sentinel for this (`UNDEFINED_PEAK_TAG = "_undefined_"`,
`_PeakParameters.init_group`/`_BackgroundParameters.init_group`), but the
*reader* (`_Peaks.peakCollectionsFromNexus`) never checked for it before
trying to parse the title as a real `PeakShape`/`BackgroundFunction` name,
crashing with `KeyError: Cannot determine peak shape from "_undefined_"` on
any file written with zero peaks — i.e., unconditionally, on every CombineRuns
NXstress export, the moment anything reads it back (surfaced by this spec's
own round-trip test, which — per spec 03's own Tests section — does read the
file back to assert equality). Fixed directly (narrow, self-contained,
`pyrs/utilities/NXstress/_peaks.py` only, no effect on the non-empty-peaks
case used by every other spec): recognize the sentinel and return `[]`
immediately, bypassing the shape-parsing attempt.

### Adjacent pre-existing bugs found and fixed (per direct discussion)

1. **`FileLoad.loadRunNumbers()` called `self.saveFileDialog(combined_files)`**,
   but `saveFileDialog(self)` takes no extra argument — a real `TypeError`,
   only reachable via the "Run Numbers:" text-entry path (the existing GUI
   test only drives "Browse Exp Data", so this was never caught). Fixed by
   delegating to `load_project_files()` (which already does
   combine-then-auto-prompt correctly for the other input path) — this also
   means the new dual-format sequencing applies to this input path for free.
2. **`FileLoading.set_text_values(self, direction, text)` referenced a
   nonexistent attribute pattern** (`file_load_e{direction}`) with zero
   callers anywhere. Traced the exact origin:
   `pyrs/interface/strainstressviewer/strain_stress_view.py:331-341` has a
   genuinely-used `FileLoading` with real `file_load_e11`/`e22`/`e33`
   attributes (strain-tensor-direction loaders) and its own, correctly-working
   `set_text_values` — confirmed this was verbatim copy-paste residue
   referencing a concept (per-direction loading) that doesn't exist in
   CombineRuns at all, not a fixable bug (there's no correct behavior for it
   to have here). Deleted outright.

### Files touched

- `pyrs/interface/combine_runs/{combine_runs_model,combine_runs_viewer}.py`
- `pyrs/core/workspaces.py` (geometry/`load_raw_counts` decoupling)
- `pyrs/utilities/NXstress/_peaks.py` (empty-peaks read-path fix)
- `tests/integration/test_nxstress_viewer_roundtrip.py` (extended: new
  `TestCombineRunsViewerRoundtrip`; `write_minimal_h5_project` fixture
  extended to also write instrument geometry/wavelength/default mask)
- New: `tests/ui/conftest.py` (re-exports `minimal_HidraWorkspace`)
- Extended: `tests/ui/test_merge_projectfiles.py`

### Test results

4 new tests (2 model-level round-trip in
`test_nxstress_viewer_roundtrip.py`, 2 GUI in `test_merge_projectfiles.py`).
Full suite: 285 unit (unchanged from the prior marker-policy pass) + 95
integration (was 93) + 13 gui (repo-wide, was implicitly 11) passing, no
regressions. `pixi run mypy pyrs scripts tests` clean throughout (typed
proactively, no retroactive pass needed).
