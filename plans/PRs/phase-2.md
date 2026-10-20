# NXstress hookup: phase 2

<!-- Draft: the "Changes to the PyRS codebase", "Phase 2 implementation" and
"How to test" sections follow once the demo scripts are written. -->

**PyRS defects fixed:**

Found and fixed while assembling this PR. Each behaviour fix has a regression test that fails without it.

- TextureFitting: loading a file that cannot be read (not HDF5, or an NXstress file with more than one entry) now shows an error and keeps the previously loaded workspace. The model used to swallow the error into a signal nothing was connected to, so nothing was reported, and on a first load the plotting that followed aborted the application.

- TextureFitting: choosing a sample-log plot axis (`vx`, `phi`, …) before fitting, or loading a file while a fit-parameter axis is selected, aborted the application with a `TypeError`. Before a fit, sample-log axes are now plotted from the workspace, and an axis with nothing to show clears the plot.

- PeakFitting: loading a non-HDF5 `.h5`, a malformed `.nxs`, or a multi-file selection that includes a `.nxs` now shows an error. These raised exceptions the load handler did not catch, which aborted the application.

- Strain/stress viewer: a project file opened to read its `direction` log is now closed explicitly. It was left to `HidraProjectFile.__del__`, so it stayed open for as long as anything else referenced it.

- NXstress `read`: an `entry_number` of 0 or less is refused with `ValueError`; it silently read entry 1.

- NXstress append: a batch with raw detector counts on some workspaces and not others is refused before anything is written. It used to pass the pre-flight checks and fail part-way through, leaving a damaged entry that read back without error.

- NXstress append: a workspace whose sample name or chemical formula differs from the entry's is refused. The entry's sample description is written once, so the appended rows were recorded under the first write's sample.

- NXstress write and append: detector masks are compared by contents, not only by name. A workspace's mask with a different array under the same name was silently replaced by the first workspace's.

- NXstress append: a sample log or discriminator value whose type the entry's existing column cannot hold is refused up front. A text log appended to a numeric column used to raise inside h5py part-way through, and a float discriminator appended to an integer column was silently truncated.

- NXstress append: a refusal from the instrument, input-data, sample or fit group now invalidates the `NXstress` instance, as `write` documents for every violated invariant.

- NXstress write and append: an entry that would read back a workspace with scan points out of increasing order — a merged write such as `[4, 5, 6]` + `[1, 2, 3]`, or workspaces sharing one discriminator value — is refused with `NotImplementedError`. It used to be written and then could not be read. The rows are not re-sorted, since that would break the round trip. The ordering requirement itself is arbitrary, and DD-2 in [`deferred-defects.md`](../PR_review/deferred-defects.md) recommends dropping it.

- Comments and docstrings: `application.yml` names the real decorator for restorable discriminator fields (`@restores`, in `pyrs.utilities.restorable_property`), and three stale test and fixture-script comments are corrected.

**Test-suite defects fixed:**

- Every GUI test module now builds its window per test, on pytest-qt's `qtbot`, instead of sharing one session-scoped window, and the shared `my_qtbot` fixture is gone. Shared windows made tests order-dependent: two TextureFitting tests failed only when run after one that left plot axes selected. The segfault cited as the reason for sharing cannot be reproduced (see `tests/ui/conftest.py`).

- `test_workspace_read.py` is updated to phase 2's list-based `write`/`read` API.

**Defects recorded, not fixed:**

- DD-2 in [`deferred-defects.md`](../PR_review/deferred-defects.md): the sub-run ordering requirement, and about ten sites that use a sub-run number as an array position. These break on any workspace whose sub-runs do not run 1..N. Each has a strict `xfail` test.
