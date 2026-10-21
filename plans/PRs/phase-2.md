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

- NXstress write and append: workspaces that share one discriminator value, and would read back as one workspace with scan points out of increasing order (such as `[4, 5, 6]` + `[1, 2, 3]`), are refused with `NotImplementedError`. It used to be written and then could not be read. The rows are not re-sorted, since that would break the round trip. The ordering requirement itself is arbitrary, and DD-2 in [`deferred-defects.md`](../PR_review/deferred-defects.md) recommends dropping it.

- NXstress no longer merges workspaces: the `nxstress.merge_workspaces` configuration key is removed (Decisions Log row 45 in [`plans/NXstress-prod/README.md`](../NXstress-prod/README.md)). With it set, several workspaces were written with no boundary and read back as one workspace built from all their rows, so the round trip was not symmetric. It also refused two workspaces measuring the same peak, and left a decreasing-order write unreadable. Writing more than one workspace with no discriminator field configured is now always refused. The message says to merge in PyRS first, as CombineRuns does. No production code set the key.

- A workspace merged in PyRS, whose `direction` log varies across sub-runs, failed with a bare `AssertionError` ("Single log direction ... is a np array with multiple items") when written under a `direction` discriminator, and when `ws.direction` was read. Both now raise `ValueError` naming the cause. Written with no discriminator, the workspace round-trips as one, with its log intact.

- Configuration: a key that PyRS does not define, in `application.yml` or an `env` override file, now stops PyRS at start-up with a message naming the key. It used to be ignored, so a misspelled key, one in the wrong section, or the removed `merge_workspaces` changed nothing and the setting kept its default (Decisions Log row 46). The sections `neutrons_standard` adds itself are exempt.

- NXstress read: a file whose `peaks` group carries a reflection field PyRS does not know (for example, from another NXstress producer) is now readable. Every unknown column used to be taken for a discriminator, so the read was refused as "written under different configuration". The rules that replace this are in [Discriminator columns on read and append](#discriminator-columns-on-read-and-append) below.

- Comments and docstrings: `application.yml` names the real decorator for restorable discriminator fields (`@restores`, in `pyrs.utilities.restorable_property`), and three stale test and fixture-script comments are corrected.

**Test-suite defects fixed:**

- Every GUI test module now builds its window per test, on pytest-qt's `qtbot`, instead of sharing one session-scoped window, and the shared `my_qtbot` fixture is gone. Shared windows made tests order-dependent: two TextureFitting tests failed only when run after one that left plot axes selected. The segfault cited as the reason for sharing cannot be reproduced (see `tests/ui/conftest.py`).

- `test_workspace_read.py` is updated to phase 2's list-based `write`/`read` API.

**Defects recorded, not fixed:**

- DD-2 in [`deferred-defects.md`](../PR_review/deferred-defects.md): the sub-run ordering requirement, and about ten sites that use a sub-run number as an array position. These break on any workspace whose sub-runs do not run 1..N. Each has a strict `xfail` test.

## Discriminator columns on read and append

When several workspaces share one NXstress entry, each `peaks` row carries one **discriminator column** per field in `nxstress.discriminator_fields` (e.g. `direction`), and `read` uses those columns to split the entry back into workspaces. Which columns are discriminators is decided as follows (Decisions Log row 43 in [`plans/NXstress-prod/README.md`](../NXstress-prod/README.md)).

**Configuration is the authority.** The fields in `nxstress.discriminator_fields` are the discriminators; nothing is inferred from the file's columns. To read a file written with other fields, configure those fields.

**The file records its fields.** Every write sets a `discriminator_fields` attribute on the `peaks` group, listing the fields it was written with. An empty list means the entry holds no workspace boundary: it was written from a single workspace with no discriminator field configured, or with no peak collections. (A file written with the since-removed `nxstress.merge_workspaces` has one too.)

**Reading an entry that has the record:**

| Record | Result |
|---|---|
| empty | Read as one workspace, whatever is configured. |
| same fields as configured | Split by those fields. |
| different fields | Refused; the message names the fields to configure. |
| a recorded field has no column | Refused as damaged. |

**Reading an entry without the record** (a file from another producer, or one written before the attribute existed):

| Configured fields with a column | Result |
|---|---|
| none | Read as one workspace. |
| all | Split by those fields. |
| some, not all | Refused. |

**Any other column is ignored on read**, with a log message. It may be another producer's reflection field, and cannot be told apart from an unconfigured discriminator.

**An append refuses** an entry that has any column which is neither PyRS's own nor a configured discriminator, before anything is written. An append grows only the columns it knows, so such a column would be left short. The append's other rules are unchanged: the target must already record a workspace boundary, and its fields must match configuration.

**What this costs.** For an entry *without* the record, a configuration that omits a discriminator is not detected. Usually the read is then refused anyway (repeated or out-of-order peak blocks), but when each workspace has one peak and their scan points increase across workspaces, two workspaces silently read back as one. Every file PyRS writes carries the record, so this affects only files from other producers and files written before this change.

Covered by `tests/unit/pyrs/utilities/NXstress/test_recorded_discriminators.py`, one test per rule above, the silent-merge case included.
