# Deferred defects

Defects in the PyRS codebase that were found and reproduced, but deliberately not fixed in the change
that found them. Each PR's commit message lists the ones it found, under "Defects recorded, not fixed".

Each defect starts with one line: its number, the date it was found, and enough of a description to
identify it. Its details follow, indented beneath that line: where it was found, what happens, with the
measurement, why it was deferred, and what to do if it is picked up. Numbers are never reused. When a
defect is fixed, mark its line fixed and say how in its details, rather than deleting it.

Code is cited by symbol name, not line number. Plan documents cited below (`plans/...`) are developer
metadata kept outside this repository.

- **DD-1**, 2026-10-11: `validate_config()` runs only at import, so a configuration installed later with
  `Config.loadEnv` is never validated. The gap is in `neutrons_standard.Config`, which has no validation hook.

  **Found during:** the PR review of NXstress subspecs 04b and 04c, part 7.
  **Owner:** `neutrons_standard.Config`, not PyRS.

  **What happens.** `pyrs/utilities/config.py` calls `validate_config()` once, at import, so a malformed
  configuration fails at the first import rather than at the first I/O call site. That works for the
  configuration that exists at import. `Config.loadEnv(<path>)` installs a new configuration at any later
  point, and nothing re-validates it:

  ```console
  >>> Config.loadEnv("bad.yml")            # nxstress: {use_production_names: "yes"}
  >>> Config["nxstress.use_production_names"]
  'yes'                                     # a truthy string, never checked
  ```

  `validate_config()` is public and can be called again by hand, but nothing in `Config` invites it: there
  is no validation hook, no post-refresh callback, and `_Config.validate` is a documented no-op. So the
  guarantee that a malformed configuration is rejected before it is acted on holds only at import.

  **Why it is deferred.** Closing the gap means `neutrons_standard.Config` growing a validation hook that
  `refresh`/`loadEnv` invoke. PyRS cannot add that from outside, and it wants its own review with the
  package's owners. The PyRS-side workarounds are all worse than the gap:
  - calling `validate_config()` from every consumer, the scattering `config.py` exists to prevent;
  - wrapping `Config` in a PyRS proxy that re-validates on access, a second `Config`, where the module
    docstring says there must be exactly one way to reach it;
  - re-validating inside `_discriminator.field_names()` and the like, which validates some keys at some
    call sites and reads as coverage when it is not.

  It is tolerable for now because the runtime-override path is test-only by decision (subspec 04b,
  part 2): the `env` OS variable is the documented production mechanism, and it is read at import.
  Production never calls `loadEnv`, but nothing says so and nothing stops a future caller.

  **Partially mitigated in tests (2026-10-16).** The reproduction still held when re-verified:

  ```console
  before override: False
  after loadEnv  : 'yes'   (type str, truthy=True)
  validate_config(): RuntimeError -- so it WOULD catch it, if called
  ```

  The `config_override` fixture (now in `tests/conftest.py`) calls `validate_config()` after each merge,
  so a test cannot install a configuration production would reject. A first version of this claimed the
  guarantee was measured, which was true of a standalone script but not of the suite: an independent test
  review deleted the hook and every test stayed green. The hook had also made `test_config.py`'s own
  `validate_config()` call unreachable, so the tests in `TestValidateConfigRejectsMalformedValues` were
  asserting against the fixture's exception, not the subject's. Both were closed:
  `test_config.py::TestConfigOverrideRefusesMalformedConfig` pins the hook, and deleting it now fails 11
  tests. Measuring a guarantee once is not the same as constraining it.

  **What the mitigation uncovered: three consumer checks production cannot reach.** Adding validation
  broke three uses of `config_override`. Each installed a malformed configuration to test that a consumer
  rejects it: `_discriminator.field_names()` on a blank and on a repeated discriminator name, and
  `_Instrument._instrument_names()` on a blank instrument name. Measured against `ConfigSchema` directly:

  ```console
  blank discriminator   : rejected by schema -> consumer check NOT reachable in production
  repeated discriminator: rejected by schema -> consumer check NOT reachable in production
  blank instrument_name : rejected by schema -> consumer check NOT reachable in production
  ```

  `NonBlankText` and `_distinct` refuse all three at import, and the `env` override is merged before
  `validate_config()` runs, so no production path delivers such a configuration to a consumer. The three
  tests passed only because nothing validated the override. They now call `override(..., validate=False)`,
  each with a comment saying why. Whether the consumers' own re-checks should stay is a layering question
  that means touching `_discriminator.py` and `_instrument.py`, and is left open.

  **If picked up.** Ask `neutrons_standard` for a validation hook that `refresh`/`loadEnv` invoke. Not yet
  raised with the package's owners.

- **DD-2**, 2026-10-20: a workspace's sub-runs must be in increasing order, which nothing needs, and about ten
  sites use a sub-run number as an array position, so they break on any workspace whose sub-runs do not run
  1..N. Each site has a strict `xfail` test.

  **Found during:** phase-2 PR assembly (post-review probe D7).
  **Owner:** `pyrs.dataobjects.sample_logs.SubRuns`, and the sites below that treat a sub-run number as an
  array position.

  **Recommendation: drop the requirement that a workspace's sub-runs be in increasing order.** What PyRS
  needs is that sub-run numbers are unique within a workspace, and disjoint between workspaces that share an
  NXstress entry. Both are already checked, and neither depends on order. The increasing order is enforced
  in one place, protects one lookup that can be rewritten without it, and is otherwise never used. It makes
  a correct NXstress round trip impossible for workspaces that share a discriminator value and are not
  already in increasing order, and it hides a separate class of real bugs (item 4 below) behind the
  appearance of a sorted, contiguous axis.

  **What happens.** An entry whose workspaces share one discriminator value is read back as one workspace,
  with the rows in on-disk order, which is the inputs' order. So was a merged write, until the
  `nxstress.merge_workspaces` key was removed (Decisions Log row 45, `plans/NXstress-prod/README.md`).
  Writing `[4, 5, 6]` then `[1, 2, 3]` produced a file that `read` refused, from `SubRuns.set`. Measured
  with the merged write:

  ```console
  D7 write merged [4,5,6]+[1,2,3] -> [4, 5, 6, 1, 2, 3]
  D7 read RAISES RuntimeError subruns are not sorted in increasing order
  D7 increasing order (control) -> (1, [1, 2, 3, 4, 5, 6])
  ```

  The same happened on an append of lower scan points under a discriminator value the entry already held.

  **What was done instead: refuse, don't re-sort.** `NXstress/_validation.py`'s
  `refuse_unreadable_scan_point_order` (and `_append.py`'s `refuse_unreadable_append_order` for an append)
  refuses, with `NotImplementedError`, any write or append that would read back a workspace whose scan
  points are not strictly increasing. It groups the rows the way `read` does, so interleaved inputs
  separated by a discriminator are unaffected. Nothing is written. The rows are deliberately not re-sorted:
  the on-disk order is the inputs' order, and sorting it would leave no way to re-assign the rows to their
  workspaces on read. Removing the refusal is the first step once this is fixed, and the strict xfail
  `test_multi_workspace.py::TestReadBackScanPointOrder::test_shared_value_in_decreasing_order_round_trips`
  will say so.

  **What actually depends on the order** (a survey of the whole codebase, 2026-10-20; the key sites were
  re-read against the code, and each defect was reproduced on a synthetic workspace):

  1. **Where the order is used: one place.** `SubRuns.get_indices` finds the positions of several sub-runs
     with `np.searchsorted`, a binary search, which is correct only on a sorted axis.
     - On an unsorted axis it returns wrong positions without raising. `SubRuns.append` skips the ordering
       check, so this is reachable: `[4,5,6]` appended with `[1,2,3]`, then `get_indices([5, 2])` gives
       `[6, 4]`.
     - Even when sorted, it checks only that a query's first and last values exist:
       `SubRuns([1,2,4]).get_indices([1,3,4])` gives `[0, 2, 2]`, so the missing 3 maps to the position of 4.
     - Single-value lookups use `np.nonzero(value == x)` and need only uniqueness.
     - It is reached through `SampleLogs.__getitem__((name, subruns))`, `get_pointlist(subruns)` (including
       NXstress `_Peaks._sample_positions`), `HidraWorkspace.get_sample_log_values`,
       `save_experimental_data(sub_runs=subset)` and the peak-fitting plot.
  2. **Where the order is checked, but not used.**
     - `SubRuns.set` checks `value[:-1] < value[1:]`. Every `SubRuns` is built through it: a project-file
       read, `HidraWorkspace._set_subruns`, `PeakCollection.set_peak_fitting_values` and NXstress
       `_Sample.sampleLogsFromNexus`, which is where the D7 read failed. What it guarantees downstream is
       that values do not repeat.
     - `_Peaks.peakCollectionRanges` checks that scan points increase within each peak-collection block.
       It exists only because the `PeakCollection` built from the block would fail `SubRuns.set` anyway.
     - `HidraWorkspace._set_subruns` sorts (with `sort=True`) only so that its input passes the check.
     - The checks that enforce the real invariant are already order-free: `_validation.py`'s
       `validate_multi_workspace` (a dict of seen scan points); `_append.py`'s
       `reject_scan_point_collisions` and `classify_compound_keys` (set intersections);
       `_Peaks.validateNoDuplicatePeaks`; and the reader's partition check in `_read.py`'s
       `workspace_selections` (`np.isin`, plus the overlap and unclaimed checks).
  3. **Places that need only one consistent order.** These pair a sub-run array with data rows by
     position, and work in any order all the arrays share:
     - reduced-data rows and sample-log columns;
     - `PeakCollection` parameter rows and its exclude list;
     - the Mantid FitPeaks spectrum index;
     - NXstress's `input_data` axis check, diffractogram rows, wavelength-dict order, and the block order
       shared by PEAKS, `peak_parameters` and `background_parameters` (`IndexedPeaks.sort_key` never
       sorts by scan point);
     - `SubRuns.__eq__` and `matching_subruns` compare element-wise, which needs the same order, not
       sorted order.

     One exception would surface once the requirement is dropped: `HidraWorkspace.set_wavelength`
     compares `sorted(dict_keys)` to the sub-runs element-wise, so it would refuse a valid dictionary for
     unsorted sub-runs. It fails loudly, and comparing as sets fixes it. There is no test, because it is
     unreachable while `SubRuns` is sorted.
  4. **Places that assume sub-runs are exactly 1..N.** These treat the sub-run number as a position. They
     break on a gap, or a first sub-run other than 1, even when sorted, so they are defects whether or not
     the requirement is dropped. Sortedness never protected them; a 1..N test workspace hides them.

     | Location | What goes wrong | Test |
     |---|---|---|
     | `HidraWorkspace.save_reduced_diffraction_data` (`pyrs/core/workspaces.py`) | Selects rows as `sub_runs_array - 1`. With no raw counts loaded it always takes this branch, so saving any workspace whose sub-runs do not start at 1 raises `IndexError`. | `test_workspaces.py::TestSubRunNumbersAreNotPositions` |
     | `HidraWorkspace.set_sample_log` | Discards the result of `matching_subruns`, so values given for other sub-runs, or in another order, are stored by position | same class, two tests |
     | `HB2BReductionManager.setup_reduction_engine` (`pyrs/core/reduction_manager.py`) | Decides whether to rebuild the 2θ map by comparing with sub-run `n - 1`, not the one reduced last. A gap or a start above 1 raises; iterating out of order would reuse the wrong engine silently. | `test_reduction_manager.py` |
     | `fit_peaks` in `pyrs/calibration/mantid_peakfit_calibration.py` | `get_diff_peaks(sub_run - 1)` against position-indexed powder tables | `tests/unit/pyrs/calibration/test_mantid_peakfit_calibration.py` |
     | `get_fitted_diffraction_data` in `detector_calibration_model.py` | `fitted_ws[sub_run - 1]`, while `fit_peaks` fills `fitted_ws` by position | `test_detector_calibration_model.py` |
     | `update_diff_view` in `detector_calibration_crtl.py` | `exclude_list[sub_run - 1]`, the same pattern | `test_detector_calibration_crtl.py` |
     | `plot_scan` in `peak_fitting_crtl.py` | One typed sub-run is used as a 1-based position in the sub-run list | `tests/ui/test_peak_fitting_crtl.py::TestSubRunNumbersAreNotPositions` |
     | `parse_sub_run_list` in `peak_fitting_crtl.py` | Typed sub-runs are used as 0-based positions, and the range `[1, N)` drops the first position and sub-run N | same class |
     | `trim_data` in `texture_fitting_crtl.py` | Included sub-runs are used as 0-based positions, and a single included sub-run is ignored (`len(...) > 1`) | `test_texture_fitting_crtl.py` |
     | `fit_peaks` in `texture_fitting_crtl.py` | The first sub-run number is used as a spectrum index | `test_texture_fitting_crtl.py::test_fit_peaks_sub_runs_not_starting_at_one` |

     `parse_sub_run_list`'s `(x >= 1) == (x < N)` reads like a typo for `&`, but it is equivalent for
     `N >= 1`, since both conditions cannot be false together. The defect is the number-as-position use.
  5. **Display order only.** `rstables.py` and `manual_reduction_viewer.py` sort for display. The browse
     order of sliders and tables is also display-only.

  Also noted, outside the ordering question: `nexus_conversion` would silently overwrite a repeated
  sub-run's counts, which is a uniqueness issue.

  **The xfail tests.** Each is `strict=True`, so a fix turns it into a failing XPASS until its marker is
  removed. Each names DD-2 in its `reason` and pins `raises=` to the exception the defect produces
  (`AssertionError`, or `pytest.fail.Exception` for "did not raise"), so a broken arrangement errors rather
  than passing as an xfail. None needs Mantid or a widget: the collaborators are plain stand-ins, each
  checked to pass with 1..N sub-runs.
  - `tests/unit/pyrs/dataobjects/test_sample_logs.py::TestSubRunOrdering`: unique unsorted values are
    accepted (the recommendation itself); `get_indices` with a missing interior value; `get_indices` on an
    unsorted axis; plus a passing test pinning that repeated values are still refused.
  - `tests/unit/pyrs/core/test_workspaces.py::TestSubRunNumbersAreNotPositions`
  - `tests/unit/pyrs/core/test_reduction_manager.py`
  - `tests/unit/pyrs/calibration/test_mantid_peakfit_calibration.py`
  - `tests/unit/pyrs/interface/texture_fitting/test_texture_fitting_crtl.py`
  - `tests/unit/pyrs/interface/detector_calibration/test_detector_calibration_model.py` and
    `test_detector_calibration_crtl.py`
  - `tests/ui/test_peak_fitting_crtl.py::TestSubRunNumbersAreNotPositions`
  - `tests/unit/pyrs/utilities/NXstress/test_multi_workspace.py::TestReadBackScanPointOrder::test_shared_value_in_decreasing_order_round_trips`

  **Why it is deferred.** `SubRuns` is used across the whole data model, so relaxing it touches every loader
  and every view, and it deserves its own review. The phase-2 NXstress PR contains it with the refusal above.

  **If picked up.**
  1. In `SubRuns.set`, check uniqueness only (`np.unique(value).size == value.size`).
  2. Replace the `searchsorted` in `get_indices` with an order-free lookup, such as a value-to-position
     dictionary, that raises `IndexError` for any missing value, not only the first and last.
  3. Compare as sets in `set_wavelength`. Make `set_sample_log` act on `matching_subruns`: either refuse a
     mismatch, or reorder the values to the workspace's axis.
  4. Remove `_Peaks.peakCollectionRanges`'s within-block ordering check, `_set_subruns`'s `sort`, and
     NXstress's `refuse_unreadable_scan_point_order` and `refuse_unreadable_append_order`, then remove the
     xfail markers above.
  5. Separately, fix the item-4 sites to look sub-runs up through `get_indices` rather than by
     `sub_run - 1`. These are independent of steps 1-4, and each has its own xfail test.

  See also [ground_truths.md](ground_truths.md), "Two data-model limits that bite any multi-record NeXus
  write", which first recorded that `SubRuns` cannot hold a non-monotonic array.

- **DD-3**, 2026-10-21: strain/stress viewer: loading a project file with no peak collections as e22 or e33
  raises `IndexError`. **Fixed** in NXstress hookup phase 3.

  **Found during:** the phase-2 PR, checking its strain/stress GUI steps.
  **Owner:** `pyrs/interface/strainstressviewer/model.py`.

  **Fixed** in phase 3 (subspec 05's PR review, Follow-up 6 F6.2). A file's empty peak dictionary is now
  kept, so `check_peak_for_direction` answers False and the setter never builds the strain; the viewer
  reports "Peak … is not in e22" instead. Pinned by
  `tests/integration/test_strain_stress_model_json.py::test_a_file_with_no_peaks_loads_as_e22`.

  **What happened.** `Model.check_peak_for_direction` answered "does every file carry the selected peak?"
  by looping over the files' peak dictionaries, so with none it returned True. The `e22`/`e33` setters then
  called `create_strain`, which built an empty strain list and indexed its first element. The
  `selectedPeak` setter took the same path for every loaded direction. e11 was not affected, because its
  setter does not build a strain. Measured on `tests/data/HB2B_1320.h5` with its `peaks/peak0` group
  deleted, through `Controller.filesSelected("e22", [path])`:

  ```
  e22 -> IndexError: list index out of range
    File "/home/ux0/workspaces/PyRS/pyrs/interface/strainstressviewer/model.py", line 134, in create_strain
      setattr(self, f"_e{direction}_strain", sum(strain_list[1:], strain_list[0]))
                                                                  ~~~~~~~~~~~^^^
  IndexError: list index out of range
  ```

  In the viewer the exception left the **Browse** button's slot uncaught. It was deferred from phase 2
  because it predated phase 2, which did not change what it depends on.

- **DD-4**, 2026-10-21: strain/stress viewer: `Controller.fileSelected` is never called, and calls
  `Model.set_workspace`, which does not exist.

  **Found during:** the phase-2 PR, fixing `Controller.filesSelected`'s success check.
  **Owner:** `pyrs/interface/strainstressviewer/controller.py`.

  **What happens.** `Controller.fileSelected(name, filename)` calls `self._model.set_workspace(...)`, which
  `Model` does not define (`hasattr(Model(), "set_workspace")` is False), so any call raises
  `AttributeError`. A `grep` over `pyrs/` and `tests/` finds only its definition; the plural
  `filesSelected` is the one the viewer uses. The method dates from af206107 (2020-06-25).

  **Why it is deferred.** Dead code has no symptom, and removing it was unrelated to phase 2.

  **If picked up.** Delete `fileSelected`.

- **DD-5**, 2026-11-05: detector calibration viewer: a recipe saved before any data were loaded cannot be
  loaded back. `PeakLinesSetupView.save_json` writes `nexus_file` only when a file is loaded, but `load_json`
  reads it unconditionally and raises `KeyError`.

  **Found during:** the rebase of NXstress hookup phase 2 onto `next`.
  **Owner:** `pyrs/interface/detector_calibration/detector_calibration_viewer.py`, `PeakLinesSetupView`.

  **What happens.** `load_json` compares the loaded file with the recipe's before anything else:

  ```
  >       if self._parent._nexus_file != input_dict["nexus_file"]:
  E       KeyError: 'nexus_file'
  pyrs/interface/detector_calibration/detector_calibration_viewer.py:732: KeyError
  ```

  It was hidden by the GUI tests' shared session-scoped window: an earlier test had always loaded data.
  Phase 2 builds each window per test, so `tests/ui/test_calibration_ui.py::test_recipe_keeps_method_and_strips`
  (the #1045 recipe test) failed, and now loads its data explicitly first.

  **Why it is deferred.** It predates phase 2, and the fix is a change to the calibration viewer.

  **If picked up.** In `load_json`, treat a missing `nexus_file` as "no data to load" (`input_dict.get`),
  and add a regression test that saves and loads a recipe with no data loaded.

- **DD-6**, 2026-10-29: a workspace whose file carries no instrument geometry cannot be saved as NXstress
  (*Save as NXstress…* is disabled). Reading the geometry from Mantid's instrument definition is deferred.

  **Found during:** subspec 05's implementation pass. Planned as F-1
  (`plans/NXstress-prod/F-1-mantid-instrument-geometry.md`), not scheduled.

  **What happens.** `NXstress.write` requires instrument geometry: the `instrument` group's detector size,
  pixel size and arm length come from `HidraWorkspace.get_instrument_setup()`, with no fallback. A
  workspace loaded from a project file with no usable geometry has `get_instrument_setup() is None`, and
  every viewer's *Save as NXstress…* is disabled for it (`gui_helper.nxstress_save_available`). Every
  strain/stress project file in `tests/data` is in that state: its `instrument/geometry setup/detector`
  group exists and is empty, `HidraProjectFile.read_instrument_geometry` raises
  `KeyError: object 'detector size' doesn't exist`, and `HidraWorkspace.load_hidra_project` logs a warning
  and continues without geometry. `HB2B_1327_with_instrument.h5`, the same run re-saved with geometry, holds
  `L2 = 0.985`, `detector size = [1024, 1024]` and `pixel dimension = [0.0003, 0.0003]`. So the strain/stress
  workflow cannot save NXstress from most real files.

  **If picked up.** When a project file has no usable geometry, build a `DENEXDetectorGeometry` from the
  installed Mantid's `HB2B_Definition.xml` (cached per instrument), name the default instrument in `Config`,
  and log a warning naming the file and the definition. The result is the nominal geometry, not a
  calibrated one, and the NXstress file must not present it as calibrated.

- **DD-7**, 2026-10-29: the model tests in `tests/ui/test_stress_strain_viewer.py` carry only the
  `integration` marker, but the module cannot be imported without a display.

  **Found during:** subspec 05's implementation pass.

  **What happens.** The module imports the viewer, which pulls in mantidqt and matplotlib's `QtAgg` backend
  at module scope, so by `CLAUDE.md`'s tier rules it is a `gui` module. Its model tests are marked
  `integration` only, so `test-integration` selects them though they need a display. Since phase 3,
  `tests/ui/conftest.py` creates an offscreen `QApplication` when there is no display, so collection no
  longer fails, but a bare `python -c 'import tests.ui.test_stress_strain_viewer'` still does. Phase 3's new
  model tests are in `tests/integration/test_strain_stress_model_json.py` instead.

  **Why it is deferred.** It predates phase 3.

  **If picked up.** Move the model tests to `tests/integration/`, against the model alone, and mark what
  remains `gui` and `integration`.

- **DD-8**, 2026-10-29: the developer documentation does not build (`pixi run build-dev-docs`): autodoc fails
  with `AttributeError: __name__` on a `unittest.mock` stand-in that `docs/developer/source/conf.py` installs.

  **Found during:** subspec 05's vendored NeXus definitions work.

  **What happens.** autodoc reaches one of the stand-ins in `conf.py`'s `MOCK_MODULES` and fails with
  `AttributeError: __name__`. The same failure occurs at the commit before phase 3's changes.

  **Why it is deferred.** It predates phase 3.

  **If picked up.** Find which mocked module autodoc reaches, and replace the hand-rolled stand-ins with
  Sphinx's `autodoc_mock_imports`, whose mocks carry `__name__`.

- **DD-9**, 2026-11-05: `StressField.__init__` and `StressField._stack_strains` annotate `strain33` as
  `StrainField`, but `None` is how an in-plane case is built, so a fully type-checked caller fails mypy.

  **Found during:** the rebase of NXstress hookup phase 3 onto `next`, when `pixi run mypy pyrs scripts
  tests` checked the new demo scripts.
  **Owner:** `pyrs/dataobjects/fields.py`, `StressField`.

  **What happens.** `StressField(strain11, strain22, None, ..., stress_type="in-plane-strain")` is how the
  in-plane cases are built, and the code handles `None`, but mypy reports `arg-type` against the annotation.
  `tests/scripts/cis_tests/NXstress/viewer_defects.py` carries a `type: ignore[arg-type]` for it.

  **Why it is deferred.** `StressField` is scientific production code, and the annotation predates phase 3.

  **If picked up.** Annotate `strain33` as `Optional[StrainField]` in both places, then remove the
  `type: ignore` from `viewer_defects.py`.
