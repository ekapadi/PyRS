# Open Questions — 07 NXstress Append Support & ManualReduction Hookup

**Spec:** [07-append-and-manual-reduction-nxstress.md](../07-append-and-manual-reduction-nxstress.md)
**Blocking:** No — but Q1 and Q2 should be settled before writing the
append-path code, since they affect its API shape.

---

## Q1 — Write mode: does the caller pick `"w"` vs `"a"`, or does NXstress auto-detect?

The spec's own NXstress Changes section writes the suffix-dispatch call as:
> `NXstress(path, "w" or "a").write(ws, peakss)`

— literally leaving the mode as an unresolved either/or in the spec text,
rather than specifying the actual logic for choosing between them.

**Why it matters:** two very different designs are implied:
- **Caller decides:** `ManualReductionModel.save_project` must itself check
  whether the target `.nxs` file already exists and pick `"w"` vs `"a"`
  accordingly — pushing file-existence logic into the GUI/model layer.
- **NXstress decides:** `NXstress.__init__` inspects the target path itself
  and silently appends if it exists, writes fresh otherwise — simpler for
  callers but means "Save" and "Save As" may behave differently than users
  expect (accidentally appending to a same-named file instead of
  overwriting).

**Next step:** decide this explicitly and update both this spec and
`NXstress.py`'s docstring — the current guard removal at L151-152 changes
meaning substantially depending on which design is chosen.

**Chris:** My inital thought is that we an data reduction pathway should create a fresh file.

---

## Q2 — What happens when an appended reduction's scan points overlap an existing entry's?

The spec covers the *ordered-insertion* case (§NXstress Changes,
`_peaks.py::init_group`: "sort the incoming `PeakIndex` entries, locate the
insertion point in the existing sorted index, and extend the HDF5 datasets
accordingly") but never addresses what happens if the incoming scan points
**duplicate** ones already in the file — e.g., re-running the same reduction
twice and appending both times, or appending a sub-run number that was
already written.

**Why it matters:** without an explicit conflict policy (reject on
duplicate index, overwrite in place, or silently allow duplicate entries
with the same key), a re-run mistake could silently corrupt the compound
index's uniqueness invariant that `validateNoDuplicatePeaks` is supposed to
enforce elsewhere in the codebase.

**Next step:** decide the conflict policy explicitly and cover it in the
round-trip test (`test_nxstress_append.py`) with a case that attempts to
append an overlapping scan point.

**Chris:** My inital thought is that we an data reduction pathway should create a fresh file.

---

## Q3 — Does the suffix-dispatch branch live in `pyrs_api.py` or a separate model layer?

The spec itself hedges: *"In `HB2BReductionManager.save_project` (or the
model it delegates to): add a suffix-dispatch branch..."* — leaving open
exactly where this logic should sit, which is directly downstream of
spec 06's Q1 (delegate/wrap/replace) not yet being resolved at the time
this spec was drafted.

**Why it matters:** if spec 06 concludes `save_project` delegates to
`ReductionApp.save_diffraction_data`, the NXstress suffix-dispatch might
belong in `ReductionApp` instead of `HB2BReductionManager`, changing which
file this spec actually touches.

**Next step:** resolve spec 06 Q1 first; then place the suffix-dispatch
branch at whichever layer ends up owning the actual write call.

**Chris:** Should `HB2BReductionManager` should coordinate how data are written into the NX file 
