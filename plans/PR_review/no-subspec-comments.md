# PR review — files with no subspec

Two batches of the walk cover files changed in the PR range that belong to **no
NXstress subspec**: they came from `61389b28` ("integration-test fixups"), which
landed between 04b and 04c as a fix for a defect the NXstress work exposed rather
than caused.

They have no `## Follow-up` section to record against, because they have no
specification document. This file is that record. Findings here are numbered in
the same `D<n>` sequence as the subspec comment documents, so a reference to a
defect number is unambiguous across the whole review.

| Batch | Files | Commit |
|---|---|---|
| 9 | `pyrs/core/reduction_manager.py` | `61389b28` |
| 22 | `tests/integration/test_pyrscore.py` | `61389b28` |

---

## Batch 9 — `pyrs/core/reduction_manager.py`

28 insertions, 16 deletions, all inside `load_hidra_project`. Two changes, and
the comment explaining them is better than most in this PR — it states the
defect, the mechanism, and the evidence.

**The mode no longer comes from the file's permissions.** It was
`READWRITE if os.access(path, os.W_OK) else READONLY` -- derived from what the
*file* allowed rather than what the *operation* needed. HDF5 marks the superblock
on a read-write open, so merely loading a writable project file modified it on
disk; committed fixtures showed up as modified in `git status` because of it.

**The handle is closed in a `finally`.** `close()` previously sat after the load,
so a load that raised left it open -- and under pytest a traceback keeps the
frame alive for the rest of the session, so the on-disk modification persisted
with it.

Both are already in [docs/ground_truths.md](../../docs/ground_truths.md), with a
regression test in `tests/integration/test_pyrscore.py` (batch 22).

### No defects in the change

Each of the comment's claims was checked rather than taken:

- *"this method only ever reads"* -- holds.
- *"every save path opens its own READWRITE handle by filename"* -- holds;
  verified at `peak_fitting_model.py:244`, `texture_fitting_model.py:217` and
  `powder_pattern.py:246,250`.
- **The same pattern elsewhere** -- swept for. `os.access(..., os.W_OK)` survives
  in four places (`pyrs_api.py`, `checkdatatypes.py`, `file_util.py`,
  `mantid_peakfit_calibration.py`), and every one is a permission *pre-check*
  before writing, not a mode derivation. The defect was fixed everywhere it
  existed.

### D30 — the comment named one save path twice

It listed *"`ReductionApp.save_diffraction_data`, `TextureFittingModel.save_fit_result`,
`powder_pattern`"*, but `ReductionApp` **is** the class in `powder_pattern.py` --
two names for one path, reading as broader evidence than it was. Corrected, and
`PeakFittingModel.save_fit_result` added, which is a genuine third.

### D31 — `HidraWorkspace._project_file`, a dead attribute **(outside this PR's scope)**

`HidraWorkspace.load_hidra_project` stored the handle this method closes:

```python
self._project_file_name = hidra_file.name
self._project_file = hidra_file
```

Three mentions in the whole repository -- one `None` in `__init__`, two
assignments -- and **no readers** in `pyrs/`, `tests/` or `scripts/`.
`hidra_project_file` answers from `_project_file_name`, set on the adjacent line.

**What it actually held, measured** -- because the first description of it was
wrong, and the correction matters:

```console
ws._project_file type      : HidraProjectFile
is it the same object?     : True
its ._project_h5 (open)    : File | h5py says open: True
after close(), attr type   : HidraProjectFile
its ._project_h5 now       : None
```

I had called it "a stale handle". It is not: `HidraProjectFile.close()` closes
the h5py `File` **and sets `_project_h5 = None`**, and since the workspace holds
the same object that clears through. What survived was a drained wrapper -- no
file descriptor, nothing to leak. Dead weight, not a resource leak.

**Reviewer:** *"what happens if we just delete the `_project_file` attribute? You
mention deleting the two assignments -- I guess this just leaves an uninitialized
attribute?"*

A fair correction of imprecise wording. It is *initialised*, at `workspaces.py:56`,
so deleting only the assignments would leave a declared attribute that is
permanently `None` -- the worst of the three options, since it reads as though
something used to set it and invites a future reader to start using it again. All
three mentions were deleted instead.

**This is outside the PR's scope** and is called out in the commit message
accordingly. `pyrs/core/workspaces.py` is already modified by this PR (the
`direction` restorable property, batch 2), but removing a `HidraWorkspace`
attribute is a change to a core data class that no subspec asked for. The one
caveat, stated rather than assumed: "nothing reads it" is a claim about *this*
repository, and the attribute is single-underscore private and undocumented, so
anything downstream poking at workspace internals would break.

### Verification

526 unit / 112 integration / 16 GUI; `ruff` and `mypy` clean; probe sweep 19 OK,
1 SKIPPED (retired), 0 FAIL.

---

## Batch 22 — `tests/integration/test_pyrscore.py`

68 lines from `61389b28`, the commit reviewed in batch 9. No subspec.

`TestLoadDoesNotModifyTheFile` states the mechanism well and gets two things
right: it covers **both** paths, noting that only one leaked; and it makes a
writable copy first, with the reason -- *"the bug cannot reproduce on a
read-only file, which is exactly why it went unnoticed on archive-mounted
data."*

### D41 — relative paths, the same fault as batch 20's D40

`Path("tests/data/Hidra_16-1_cor_log.h5")` at line 38 (new) and a second at
line 116 (pre-existing), both resolved against the process working directory in
a module that already receives `test_data_dir` elsewhere. The new test now uses
that fixture; `test_main`, being outside a test function's fixture scope for
this purpose, resolves from `__file__`. The filename is a single
`LEGACY_SCHEMA_FIXTURE` constant, so the `xfail` reason, `test_main` and this
class cannot drift about which file they mean.

### O32 — a bare `pytest.raises(RuntimeError)`

Now `match=r'non-empty "reduced diffraction data" entry'`. The comment states
why it matters: the closure assertion is only meaningful if the load reached
the point where a handle is open, and a `RuntimeError` raised earlier would
satisfy a bare `pytest.raises` while exercising none of it.

### D42 — the regression test did not regress

Adding that `match` prompted checking what the test caught. It caught nothing.
Reverting `reduction_manager` to the **full pre-fix state** -- READWRITE *and*
no `finally` -- left it green.

The mechanism, measured on h5py 3.16.0 / HDF5 1.14.6:

```console
r+ open, handle OPEN : changed
r+ after close       : unchanged
r  open, handle OPEN : unchanged
```

`docs/ground_truths.md` is right that a read-write open changes the bytes -- but
only **while the handle is open**; a clean close reverts the mark. By the time
the test takes its digest the `HidraProjectFile` is unreferenced and CPython has
closed it. The original symptom needed the handle held across the session, which
a digest taken after the call can never observe.

Same shape as O12 and O20 -- an assertion that cannot fail -- but worse: this is
the designated guard for a defect that reached committed files, and it is named
`test_..._leaves_the_file_unchanged`.

**Resolved by asserting what the fix changed**, through a recording
`HidraProjectFile` patched into `reduction_manager`: the **mode** each open uses,
and that every handle is **closed** even when the load raises. The digests stay
alongside, as the statement of intent -- they say what the code is for -- but
they no longer carry the guarantee alone.

Each half now fails independently:

| mutation | before | after |
|---|---|---|
| `READONLY` -> `READWRITE` | passed | **2 failed** |
| `try/finally` -> plain close | passed | **1 failed** |

**Incidental, and evidence in its own right:** with the `finally` removed, the
two tests run together *hung* rather than merely failing -- a leaked HDF5 handle
has consequences past the superblock mark, which is consistent with this repo's
"segfault at interpreter shutdown" ground truth. Run singly the mutant fails
cleanly in 0.12s.

### Verification

534 unit / 112 integration / 16 GUI; `ruff` clean.
