# NXstress hookup: phase 1

**Changes to the PyRS codebase:**

- `HidraWorkspace.load_hidra_project` loads instrument geometry independently of `load_raw_counts`, logging a warning when the project file has none.

- Added `PyRsCore.register_hidra_workspace()` to register an in-memory `HidraWorkspace` as a session data source.

- `TextureFittingModel.save_fit_result` no longer references the undefined `self.parent` (previously always raised `AttributeError`); `load_hidra_project_file` now closes its project-file handle and returns `None`.

- `TextureFittingViewer`: the *Save* and *Save as* actions no longer share one attribute.

- `CombineRunsViewer`: fixed a `TypeError` in the "Run Numbers" input path, ignored a cancelled save dialog, and removed the unused `set_text_values`.

- Added `gui_helper.impose_extension()`; every save/export dialog, `.h5` included, now forces its format's configured extension onto the chosen filename (see config settings in [`application.yml`](../../pyrs/resources/application.yml)).

- Added type hints to the peak-fitting, texture-fitting, and combine-runs model/viewer classes.

- Tests: `tests/conftest.py` performs the first `pyrs.utilities.config` import under a throwaway `HOME`; added `tests/util/project_file_helpers.py` and conftest re-exports of the shared NXstress fixtures for `tests/integration` and `tests/ui`.

**Phase 1 implementation:**

- PeakFitting and TextureFitting viewers: added *File → Save as NXstress…* and an `NXstress (*.nxs)` load filter; the models dispatch on the `.nxs` suffix to `NXstress.write`/`read`.

- CombineRuns viewer: added an NXstress export prompt that writes the merged workspace with no peaks (`NXstress.write(ws, [])`); it is skipped when the workspace has no instrument geometry.

- Save/export actions are enabled from `Config["nxstress.enable"]` / `Config["legacy_io.enable"]`.

- The NXstress reader returns no peaks for files written with an empty peak list (`UNDEFINED_PEAK_TAG`).

- `PeakFittingCrtl.plot_diff_and_fitted_data` tolerates an NXstress load with no fitted spectrum; an `.nxs` load also registers its workspace with `PyRsCore`.

- Tests: model-level `.nxs` round-trip and `.h5` routing tests for all three viewers (integration), plus GUI tests for the new save/export actions and the `fitted=None` guard.
