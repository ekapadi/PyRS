# 04c — NXstress Append Mode (library only)

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** 3
**Depends on:** [04b — Multi-workspace NXstress I/O](04b-multi-workspace-nxstress.md)

---

## Overview

Add the ability to extend an **already-written** `NXentry` with more scan
points, rather than requiring every write to create a fresh entry.

This is a different capability than it may first appear: `NXstress.write`
already supports accumulating multiple reductions into one `.nxs` file today
— each call adds a new, auto-numbered `NXentry`
([NXstress.py:149](../../pyrs/utilities/NXstress/NXstress.py#L149)), and the
guard at [NXstress.py:151-152](../../pyrs/utilities/NXstress/NXstress.py#L151)
only fires on an accidental name collision. What's missing is the ability to
grow *one* `NXentry`'s data — e.g., a second reduction pass whose scan points
belong to the same combined index as an earlier write, not a new
data-reduction condition. Per the plan's own semantics
(README.md §2.4, "Multi-NXentry semantics"), separate conditions still get
separate `NXentry`s; append is for adding more of the *same* condition's data.

This was originally bundled with the ManualReductionViewer hookup (the old
spec 07) on the rationale that append and that hookup "share a common
primitive." That primitive is no longer shared: the reduction pathway is
decided to always create a fresh file (see
`open-questions/07-manual-reduction-nxstress.md`), so append gains **no GUI
entry point in this pass**. This spec delivers append as a tested library
capability only — usable by future callers (tests, scripts, or a future GUI
action) without a corresponding menu action anywhere in the GUI today.

### Relaxed sortedness: "locally sorted, globally segmented," not globally sorted

04b established that the reader (`_Peaks.peakCollectionRanges`,
`_peaks.py:425-535`) only ever required two invariants — each compound key
occupies one contiguous run (R1), and `scan_point` increases within a run
(R2, already guaranteed upstream by `SubRuns.set`,
`sample_logs.py:167-168`) — never global lexicographic order. Sortedness
beyond that was incidental, not a schema requirement.

This spec adopts that directly: a **single-step write** (all
`HidraWorkspace`/`PeakCollection` present at the `write()` call, 04b's
existing case) still produces a fully sorted combined index, exactly as
today — there's no reason to give that up when everything is available at
once. **Append does not re-sort the file.** It sorts only the incoming
batch internally (so the new data's own rows are self-consistent) and adds
it to the file without reordering what's already on disk. A file that has
been appended to is therefore "locally sorted, globally segmented" rather
than globally sorted — R1 and R2 still hold throughout, which is all the
reader has ever required.

**The non-overlapping-scan-points/index-rows invariant is unchanged and
still fully enforced** — relaxing global sortedness is not a relaxation of
that invariant; see Conflict policy below.

### Architecture: in-place tail-append, not read-merge-rewrite, and not general insertion

Two designs were considered for how append touches the *existing* entry:
1. Read the existing entry back into `HidraWorkspace`/`PeakCollection`
   objects (reusing `NXstress.read()`), append the new data to that list in
   memory, and rewrite the entry using 04b's N-workspace merge-and-write path
   wholesale.
2. Operate directly against the on-disk `NXfield` arrays (via `.nxdata`) to
   determine conflicts, without ever reconstructing the existing entry as
   `HidraWorkspace`/`PeakCollection` objects.

**Decided: (2).** The concern driving this is that a normal reduction/append
cycle should not have to round-trip the *existing* entry's data through
PyRS's outer types just to grow it — particularly raw detector counts, which
can be large.

Relaxed sortedness (above) further narrows what "(2)" needs to do. R1
(contiguity) splits append into two cases:
- **Case A — the incoming data introduces compound keys not already on
  disk** (the normal case: a new workspace, distinguished by a new
  discriminator value per 04b's ordering rule, or a genuinely new
  phase/hkl/mask). A **tail-append** — grow each affected array and write
  the new rows after the current end — satisfies both R1 and R2 without
  touching any existing row.
- **Case B — the incoming data extends a compound key already present on
  disk** (more scan points for a workspace/key that's already in the
  file). R1 forces those new rows into the middle of that key's existing
  run — a true insertion, not a tail-append.

**Decided (scope cut): this spec implements Case A only.** Case B is
detected (see Conflict policy) and rejected with `NotImplementedError` —
not silently mishandled, but explicitly deferred as a follow-up, since it
is a different and more invasive operation than what a normal
reduction/append cycle needs today. This falls directly out of relaxing
global sortedness (above): without a global-sort obligation, the common
case that actually needs to work — "append a new workspace's worth of
data" — reduces to code that already exists (see
`_Peaks._append_peak`, `_fit.py`'s `_PeakParameters._append_peak`, both
already written as `cur = shape[0]; resize(cur+N); arr[cur:] = …`, per the
`# TODO` that stood at `_peaks.py` lines 180-181, now resolved -- see Follow-up 2 F2.11). No new insertion-position machinery is
needed for the case this spec actually delivers.

The **new** data being appended is still supplied the normal way —
`list[HidraWorkspace]` + `list[PeakCollection]`, matching 04b's `write()`
signature — sorted internally among themselves as 04b already does; only
the *existing* side of the operation avoids both the round-trip and any
mid-array mutation.

### Scope: all position-aligned groups, not just input_data and peaks

An entry's on-disk groups fall into two position-aligned families, plus one
family that isn't position-sensitive at all:

| Family | Groups | Aligned by |
|---|---|---|
| Peak-index family | `_peaks.py` (`PEAKS`/`NXreflections`), `_fit.py::_PeakParameters`, `_fit.py::_BackgroundParameters` (`peak_parameters`/`background_parameters` under `FIT`) | The compound `PeakIndex` sort key. `_PeakParameters.init_group`/`_BackgroundParameters.init_group` build their rows via `sorted(peakss, key=_Peaks.PeakIndex.sort_key)` ([_fit.py:87](../../pyrs/utilities/NXstress/_fit.py#L87)) — **the exact same order as the peaks index**, so their rows are positionally aligned with it, not independently keyed. |
| Scan-point family | `_input_data.py` (`detector_counts`), `_sample.py` (`SAMPLE_DESCRIPTION` per-scan-point logs), `_fit.py::_Diffractogram` (`diffractogram`/`diffractogram_errors`) | `scan_point`. |
| Name-keyed, no insertion needed | `_instrument.py::_Masks` | Mask *name*, not position — `init_group` already accepts an existing `masks` group and extends it by name ([_instrument.py:317](../../pyrs/utilities/NXstress/_instrument.py#L317)); no new work needed here. |

**Decided:** this spec covers the full peak-index family and the full
scan-point family, coordinated so that append never leaves one group's rows
grown without the corresponding rows in every other group in its family.
A partial append (e.g., growing `detector_counts` without growing the
diffractogram) would leave the entry internally inconsistent — not an
acceptable interim state for a correctness-focused library feature. Per
the Case-A-only scope decision above, "grown" means **tail-appended**, not
inserted — both families' new rows are added after each dataset's current
end, in lockstep across every group in the family.

### Entry targeting

`NXstress(path, "a")` with no further argument targets the **last** existing
`NXentry` in the file — the common case (one entry being grown over time)
needs no extra argument. An optional `entry_number` targets a specific
earlier entry instead: `NXstress(path, "a", entry_number=N)`.

### Conflict policy, and Case A/Case B classification

The same pass that reads the existing on-disk key arrays to check for
conflicts also classifies each incoming compound key, at no extra cost:

- **New key relative to what's on disk (Case A):** no conflict — proceeds
  as a tail-append, **subject to two preconditions inherited directly from
  04b's Q7** (never previously carried into this spec's own text):
  1. **The new workspace must itself contribute at least one
     `PeakCollection`.** Exactly 04b's write-time invariant, restated for
     append: without one, this workspace's discriminator value can't be
     recovered on a later `read()`, and the resulting file would be
     silently unsplittable. Raise `RuntimeError` if violated, before any
     mutation — same failure mode as the fresh-write case, just checked
     here too.
  2. **The target entry must already have a discriminator scheme
     established** — i.e., its `PEAKS` group already carries discriminator
     column(s) from an earlier 04b-mechanism write. Appending a
     genuinely new, distinguishable workspace to an entry that was
     originally written as a bare `N == 1`/no-discriminator write would
     require adding a new on-disk column. That is mechanically possible —
     see [`probes/a4_h5py_nexusformat_append.py`](probes/a4_h5py_nexusformat_append.py)
     — but it is schema restructuring, which this spec deliberately
     excludes; a later spec could lift the restriction cheaply. Raise
     `RuntimeError` if the target entry has no discriminator columns at
     all. *(Reworded per Follow-up 1 F1.3 and Decisions Log row 22; the
     original wording, which implied a format limit, is quoted in F1.3.)*
- **Key already present on disk, new scan point(s) under it (Case B):**
  **rejected**, distinctly from a true duplicate — raise
  `NotImplementedError` (not `RuntimeError`; see below), since this isn't
  a corrupted-data condition, it's a real operation this spec deliberately
  doesn't implement (see the Architecture section above). The on-disk
  entry is left unchanged; the instance is *not* invalidated for this
  case specifically, since nothing was detected to be wrong with it —
  only unsupported.
- **Exact duplicate** (same key *and* same scan point, or the same
  peak-index row) already present in the target entry: the true conflict
  case. Raise `RuntimeError` — not the `ValueError`
  `validateNoDuplicatePeaks` raises for the analogous fresh-write duplicate
  case, since this represents a violated invariant on already-committed
  data, not an expected/anticipated bad-input case a caller would
  routinely hit and want to catch.

The classification/conflict check runs against **all** affected groups
before any resize/append call is made — including the two Case-A
preconditions above (≥1 `PeakCollection` for the new workspace; a
discriminator scheme already established in the target entry) — so a
rejected (`RuntimeError`) and an unsupported (`NotImplementedError`)
append are both true no-ops — the on-disk entry is left byte-for-byte
unchanged either way.

After a `RuntimeError` (an exact duplicate, or either of Case A's two
preconditions failing), the `NXstress` instance is left unusable for any
further `write()` call in the same session — the caller must re-open
rather than continue against a session that already detected a corrupted
assumption about the target entry's contents. A `NotImplementedError`
(Case B) does **not** invalidate the instance — the caller may still make
other, Case-A-only, append calls in the same session.

---

## Scope

**In scope:**
- Peak-index family: implement the **tail-append** path for `_peaks.py`'s
  compound index (the `# TODO` that stood at `_peaks.py` lines 180-181 already
  described code written in a form that allows this; see Follow-up 2 F2.11) and, in lockstep, for
  `_fit.py::_PeakParameters.init_group` / `_BackgroundParameters.init_group` —
  all three grow by the same new-row count, appended after their current end.
- Scan-point family: implement the tail-append path for
  `_input_data.py:60-79` (`detector_counts`, on both write and read),
  `_sample.py`'s per-scan-point logs, and `_fit.py::_Diffractogram.init_group`
  — all three grow by the same new-row count, appended after their current
  end.
- `NXstress.py`: remove the guard at `NXstress.py:232` for the append
  case; add entry targeting (`entry_number`, defaulting to the last entry);
  dispatch `write()` to the tail-append path when opened with mode `"a"`.
- Conflict/classification: compare new scan points / index rows against the
  existing on-disk arrays (read via `.nxdata`, not reconstructed as
  `HidraWorkspace`/`PeakCollection`) before any mutation; classify each
  incoming key as Case A (new — proceed, subject to its two preconditions:
  ≥1 `PeakCollection` for the new workspace, and a discriminator scheme
  already established in the target entry), Case B (extends an existing
  key — raise `NotImplementedError`), or exact duplicate (raise
  `RuntimeError`, invalidate the instance), per the policy above.
- Round-trip test: write, then append a new (Case A) workspace, into the
  same entry; verify all five groups' contents are combined and mutually
  consistent.

**Out of scope:**
- Any GUI menu action, file-dialog filter, or viewer wiring. No viewer in
  this plan calls append in this pass.
- ManualReductionViewer hookup (now a fresh-write-only spec: see
  [07 — ManualReduction hookup](07-manual-reduction-nxstress.md)).
- `_instrument.py::_Masks` — already append-capable, name-keyed, no change
  needed.
- **Case B (extending a compound key already present in the file with more
  scan points)** — genuinely different from Case A: it requires a true
  mid-array insertion, not a tail-append, since contiguity (R1) forces the
  new rows into the middle of that key's existing run. Raises
  `NotImplementedError`; not silently mishandled, but deferred as a
  follow-up should a future caller need it.
- Fit-spectrum data (spec 09).
- Detector-calibration fidelity fixes (spec 09).

---

## PyRS Changes

_None._ Append operates entirely within `pyrs/utilities/NXstress/`, against
on-disk NXstress structures and the new data's `HidraWorkspace`/
`PeakCollection` objects — no change to PyRS's own data-object classes.

---

## NXstress Changes

### `pyrs/utilities/NXstress/_peaks.py`

- `init_group` — implement the tail-append path described in the `# TODO`
  that stood at `_peaks.py` lines 180-181, reusing the existing `_append_peak`
  (`_peaks.py:315-390`)
  against an existing on-disk `PeakIndex` group instead of a freshly
  `_init`-ed one: read the existing on-disk `PeakIndex` arrays (via
  `.nxdata`, using 04b's name-keyed discriminator resolution to reconstruct
  each existing row's key) to classify the incoming, sorted batch as Case
  A/B/duplicate (see Conflict policy above); for Case A rows, `_append_peak`
  already does `cur = shape[0]; resize(cur+N); arr[cur:] = …` — no change
  to its resize/assign logic, only to what group it's called against.
- No insertion-position computation or cross-module position-sharing is
  needed — tail-append means every peak-index-family group grows by the
  same row count, from its own current end.

### `pyrs/utilities/NXstress/_fit.py`

- `_PeakParameters.init_group`, `_BackgroundParameters.init_group` — accept
  an existing `NXparameters` group; their existing `_append_peak` methods
  (already the same `resize(cur+N); arr[cur:] = …` shape, e.g.
  `_fit.py:~92-137`) tail-append the new (Case A) rows after the current
  end — same row count and order as `_peaks.py`'s append, so positional
  alignment is preserved automatically.
- `_Diffractogram.init_group` — accept an existing `NXdata` group; tail-append
  `diffractogram`/`diffractogram_errors`/`scan_point` after the current end.

### `pyrs/utilities/NXstress/_sample.py`

- `init_group` — accept an existing `NXsample` group; tail-append each
  per-scan-point log field after the current end.

### `pyrs/utilities/NXstress/_input_data.py`

- `init_group(wss, data=None)` — by this phase (Phase 3, after 04b's
  Phase 2/3 bridge) this already takes `list[HidraWorkspace]`, not a
  single `ws` — an earlier draft of this bullet cited the pre-04b
  signature. When `data` is an existing `NXdata` group (append mode),
  tail-append `detector_counts`/`scan_point` after the current end,
  rather than raising; the new data being appended is still `wss`, per
  04b's own signature (a length-1 list for the common single-new-workspace
  append case).
- `readSubruns(ws, data)` — this one keeps its single-`ws` signature
  unchanged, since it's called once per *reconstructed* workspace against
  an already-sliced `data` view (04b's Q7 value-set-membership split
  happens in the caller, before `readSubruns` is invoked per workspace —
  not inside this method). Unaffected by this spec's write-side scope, but
  confirm it still reads a post-append file correctly (the on-disk layout
  after append is a larger array, locally sorted per key but not globally
  re-sorted — no reader change should be needed, since the reader never
  required global order; see the Relaxed sortedness section above).

### `pyrs/utilities/NXstress/NXstress.py`

- `__init__(path, mode, *, entry_number: int | None = None)` — `entry_number`
  is only meaningful with `mode="a"`; defaults to the last existing entry.
- `write(wss, peakss)` — when opened in append mode, resolve the target
  entry, run the conflict/classification check across all affected groups
  first (Case A/B/duplicate per the policy above — raise `NotImplementedError`
  for Case B or `RuntimeError` and mark the instance invalid for a
  duplicate, before any mutation), then delegate to the append-aware
  `init_group` methods for both families, each simply tail-appending its
  own new rows. When opened in `"w"` mode, behavior is unchanged from 04b.

---

## Tests

`tests/integration/test_nxstress_append.py` (new):
- Write a minimal dataset to a new `.nxs` file; append a second (Case A —
  a new discriminator value/workspace), non-overlapping dataset to the
  same entry (default "last entry" target).
- Read back; assert combined scan-point count equals the sum of both writes;
  assert peak-index entries from both writes are present — file is "locally
  sorted, globally segmented" (each write's own rows sorted among
  themselves; the second write's block simply follows the first's, not
  interleaved into it) — and that `peak_parameters`/`background_parameters`/
  `diffractogram` rows are still positionally aligned with the peaks index
  after the tail-append.
- `entry_number` override: write two entries, append to the first (not the
  last) via explicit `entry_number`; confirm only the targeted entry grew.
- Case B rejection: attempt to append more scan points under a compound key
  (discriminator value + phase/hkl/mask) that's already present in the
  target entry; assert `NotImplementedError` is raised, the on-disk entry
  is unchanged (byte-for-byte, or field-by-field equality check), and the
  same `NXstress` instance can still make a subsequent Case-A append.
- Exact-duplicate conflict case: attempt to append a scan point (or
  peak-index row, under the same discriminator value) that duplicates one
  already in the target entry; assert `RuntimeError` is raised, the
  on-disk entry is unchanged, and a subsequent `write()` call on the same
  `NXstress` instance also raises.
- Case-A precondition 1 (empty `PeakCollection`s): attempt to append a
  new workspace with `peakss=[]` to an entry that already holds another
  workspace; assert `RuntimeError` is raised (its discriminator value
  would be unrecoverable on a later `read()`), the on-disk entry is
  unchanged, and the instance is invalidated (same treatment as an exact
  duplicate — a violated invariant, not an unsupported operation).
- Case-A precondition 2 (no discriminator scheme in target entry): write
  a fresh entry with `N == 1` (no discriminators engaged, per 04b's
  empty-config policy), then attempt to append a second, distinguishable
  workspace to it; assert `RuntimeError` is raised (the target has no
  discriminator columns to attach the new workspace's value to) rather
  than silently merging or corrupting the entry.

`tests/unit/pyrs/utilities/NXstress/test_peaks.py`, `test_fit.py`,
`test_sample.py`, `test_input_data.py` (extend):
- Tail-append correctness for each family, independent of the
  integration-level round-trip: appending to an existing (non-empty) group
  grows each dataset by exactly the new row count, with existing rows
  byte-for-byte unchanged and new rows correctly appended after them.
- Case A/B/duplicate classification, given a small existing on-disk index
  and various incoming batches.

---

## Delivered Feature

> **For downstream NXstress consumers (not yet user-facing):**
> An `NXentry` can now be incrementally grown: `NXstress(path, "a")` extends
> the last-written entry (or a specifically targeted one, via
> `entry_number`) with a new workspace's worth of scan points, rather than
> requiring a fresh file or a fresh entry per write. All five
> position-aligned data groups (raw counts, sample logs, diffractogram,
> peak index, and fit parameters) stay mutually consistent after an
> append, via a tail-append that never re-sorts what's already on disk.
> Growing an already-present workspace/key with more scan points (rather
> than adding a new one) is not yet supported (`NotImplementedError`) —
> that's a genuinely different, insertion-shaped operation, deferred as a
> follow-up. This pass ships the capability as a tested library feature
> only — no PyRS viewer currently exposes an "append" action. Wiring a GUI
> entry point (if a future use case needs one) is a separate,
> not-yet-scheduled follow-up.

---

## Verification

- `pytest tests/integration/test_nxstress_append.py` — all pass.
- `pytest tests/unit/pyrs/utilities/NXstress/` — all pass, no regression
  from 04b.
- Confirm (by inspection, not test) that no GUI file exists that calls
  `NXstress(..., "a")` — this spec is library-only by design.
- Manual check: append a new workspace, then open the resulting file with
  `nexusformat`/`h5dump` and confirm each group is "locally sorted,
  globally segmented" — the first write's rows sorted among themselves,
  the appended batch's rows sorted among themselves and following as a
  second contiguous block, not interleaved into the first — and that no
  group claims or implies a single global sort across the whole file.

---

## Follow-up 1 — 2026-09-25 (first seven-axis pass)

**F1.1** (A4) — **This spec's central mechanism is confirmed.** The claims that
tail-append "reduces to code that already exists" — `cur = shape[0];
resize(cur+N); arr[cur:] = …` — were, until now, asserted only from reading:
every landed use of that shape runs against **in-memory** `NXfield`s during
`init_group`, while append runs it against a **reopened, file-backed** group.
Those are different objects with different backing stores.
- Referent: `h5py` 3.16.0 / `nexusformat` 1.0.8, probed by
  [`probes/a4_h5py_nexusformat_append.py`](probes/a4_h5py_nexusformat_append.py).
- Verdict: **works, including the two cases most likely to have failed** — a
  genuinely zero-sized dataset, and variable-length UTF-8 string fields
  (`phase_name`, `mask`):

  ```console
    CLAIM   resize(cur+N); arr[cur:] = ... works on a ZERO-SIZED reopened dataset
    RESULT  3 row(s) appended at offset 0; read back {'scan_point': [1, 2, 3],
            'phase_name': ['Fe', 'Fe', 'Fe'], 'center': [1.1, 1.2, 1.3]}

    CLAIM   grows by exactly N, existing rows unchanged, new rows after them
    RESULT  2 row(s) appended at offset 3; scan_point now [1, 2, 3, 4, 5];
            existing rows preserved: True; vlen strings: ['Fe','Fe','Fe','Ni','Ni']
  ```
- Action: none. The design stands, now on evidence.

**F1.2** (A4) — "a rejected (`RuntimeError`) and an unsupported
(`NotImplementedError`) append are both true no-ops — the on-disk entry is left
byte-for-byte unchanged either way".
- Verdict: **confirmed**, for the stated precondition (the classification check
  runs before any resize):

  ```console
    CLAIM   opening 'rw' and raising BEFORE any resize leaves the file unchanged
    RESULT  sha256[:16] before=cf489122b1f81fd2 after=cf489122b1f81fd2
            identical=True (simulated conflict detected before any resize)
  ```
- Action: none — but note what this does **and does not** establish. It confirms
  that merely opening in `"rw"` and raising is byte-neutral. It does **not**
  establish atomicity across a *partial* append, which is why this spec's
  "check all affected groups **before any resize/append call is made**"
  ordering requirement is load-bearing and must survive implementation.

**F1.3** (A4) — "Appending a genuinely new, distinguishable workspace to an entry
… isn't possible without adding a new on-disk column, which this spec's
tail-append design does not do".
- Verdict: **the sentence is literally true and its framing misleads.** Adding a
  new column to an existing group *succeeds*:

  ```console
    CLAIM   adding a NEW on-disk column to an existing group -- 04c says its design
            does not do this; is it even possible?
    RESULT  SUCCEEDED -- group now has ['center', 'direction', 'fit', 'h',
            'phase_name', 'scan_point']
  ```

  So the restriction is a **scope decision, not a technical limit**. As written
  ("isn't possible without …, which this design does not do") a reader
  reasonably concludes the format forbids it and stops looking.
- Action (for the implementing PR): reword to "…would require adding a new
  on-disk column. That is mechanically possible — see
  `probes/a4_h5py_nexusformat_append.py` — but it is schema restructuring, which
  this spec deliberately excludes; a later spec could lift the restriction
  cheaply." This matters because it changes what a future spec can assume.

**F1.4** (A3) — the bare line reference in the peak-index bullet, preceding
"reusing the existing `_append_peak`".
- Verdict: that bare line reference had no resolvable antecedent — no filename
  appears anywhere in that paragraph, and the file (`_peaks.py`) was implied only by the
  enclosing section. The parallel prose at `04b:40-41` writes it explicitly.
  Reported rather than guessed, per the toolkit's rule.
- Action: qualified in place to `` `_peaks.py:180-181` ``.

**F1.5** (A3) — `sample_logs.py:164-166` corrected in place to `:167-168`; see
`04b-multi-workspace-nxstress.md`'s Follow-up 1 F1.1 for the evidence.

**Checked and accurate — no action.** `_peaks.py:180-181`,
`_input_data.py:44-46,63-72`, `NXstress.py:151-152`, `_peaks.py:190-244`,
`_peaks.py:246-338` all land exactly on their claimed targets. The premise at
`:14-21` — that `write` already accumulates entries and the guard "only fires on
an accidental name collision" — is confirmed against the landed library
([`probes/a5_nxstress_roundtrip.py`](probes/a5_nxstress_roundtrip.py)):

```console
  CLAIM   what mode 'a' actually does today: does it EXTEND the existing entry,
          or add a new one?
  RESULT  no exception raised; NXentry count 2 -> 3 ['entry', 'entry_2', 'entry_3'].
          So a write never extends an existing entry -- it appends a new one.
```

**A5 gap, recorded rather than assumed.** This spec's conflict classification,
Case-A/Case-B dispatch and `entry_number` targeting **cannot be probed** —
none of it exists yet. A5-**uncovered**, not A5-verified. The *mechanism* they
rest on is covered by F1.1–F1.3; the dispatch logic is not.

---

## Follow-up 2 — 2026-10-01 (implementation pass)

Ten findings. Two of them change the design, one of those decisively: the
mechanism this spec is built on was available for **half** the groups it covers
and for the other half was not available at all.

**F2.1** (A5) — **"Tail-append reduces to code that already exists" is true of
the peak-index family and false of the scan-point family.** Follow-up 1 F1.1
recorded this spec's central mechanism as "confirmed", on
[`probes/a4_h5py_nexusformat_append.py`](probes/a4_h5py_nexusformat_append.py).
That probe is sound and its verdict is correctly stated — but it built **its
own** fixtures, and gave every one of them `maxshape=(None,)` + `chunks`. It
therefore established that `resize(cur+N); arr[cur:] = …` works *on a resizable
dataset*, which is a different claim from "the datasets the NXstress writer
emits are resizable". An HDF5 dataset created without `maxshape` is contiguous
and cannot be extended by any mechanism.
- Referent: the writer's real output, built and traversed by
  [`probes/a5_scan_point_family_resizable.py`](probes/a5_scan_point_family_resizable.py).
  A grep over the source would have shown the same thing, but only if one
  already knew to look for an absent kwarg; building the artifact and walking it
  reports the state rather than the intent.
- Verdict against the writer as 04b left it: **86 datasets, 32 extendable, 54
  fixed-size.** The peak-index family was 22 of 24 extendable (the two
  exceptions, `peak_parameters/title` and `peaks/center_type`, are per-entry
  scalars and correct as they are). The scan-point family was almost entirely
  fixed:

  ```console
    CLAIM   claims 2-4: is every named scan-point-family dataset tail-appendable?
    RESULT  /entry/start_time: shape=(3,) maxshape=(3,) chunks=None -> FIXED
            /entry/end_time: shape=(3,) maxshape=(3,) chunks=None -> FIXED
            /entry/input_data/detector_counts: maxshape=(None, None) -> extendable
            /entry/input_data/scan_point: shape=(3,) maxshape=(3,) chunks=None -> FIXED
            /entry/instrument/monochromator/wavelength: maxshape=(3,) -> FIXED
            /entry/SAMPLE_DESCRIPTION/scan_point: maxshape=(None,) -> extendable
            /entry/SAMPLE_DESCRIPTION/vx: maxshape=(3,) chunks=None -> FIXED
            /entry/SAMPLE_DESCRIPTION/vy: maxshape=(3,) chunks=None -> FIXED
            /entry/SAMPLE_DESCRIPTION/vz: maxshape=(3,) chunks=None -> FIXED

    CLAIM   claim 4: _Diffractogram's datasets
    RESULT  /entry/FIT/DIFFRACTOGRAM/XAXIS: maxshape=(3, 20) -> FIXED
            /entry/FIT/DIFFRACTOGRAM/diffractogram: maxshape=(3, 20) -> FIXED
            /entry/FIT/DIFFRACTOGRAM/diffractogram_errors: maxshape=(3, 20) -> FIXED
            /entry/FIT/DIFFRACTOGRAM/scan_point: maxshape=(3,) -> FIXED
            /entry/FIT/DIFFRACTOGRAM/fit, fit_errors: maxshape=(None, None) -> extendable

    CLAIM   claim 3: _sample.py's retained per-scan-point logs
    RESULT  4 log field(s); all FIXED
  ```
- What this falsifies: the Architecture section's "reduces to code that already
  exists … No new insertion-position machinery is needed", the Scope bullet
  claiming a tail-append path for `_input_data.py` / `_sample.py` /
  `_fit.py::_Diffractogram`, and the NXstress Changes bullets for
  `_Diffractogram.init_group` and `_sample.py`'s `init_group`. All of them read
  as though those groups need only a new entry point. They needed a writer
  change first.
- Correction, and **why it is not read-merge-rewrite**: a new helper
  [`growable(rank)`](../../pyrs/utilities/NXstress/_definitions.py#L70) returns
  the `maxshape`/`chunks` kwargs, and is applied at every per-scan-point
  `NXfield(...)` — `NXstress.py:801-802`, `_instrument.py:226`,
  `_input_data.py:74`, `_sample.py:131`/`:145`/`:167`/`:186`,
  `_fit.py:485`/`:490`/`:494`/`:498`. A matching
  [`tail_append(field, values)`](../../pyrs/utilities/NXstress/_definitions.py#L109)
  carries the growth rule, and
  [`appendable(field)`](../../pyrs/utilities/NXstress/_definitions.py#L90) the
  pre-flight predicate. The alternative — read the fixed-size array back,
  concatenate, delete, rewrite — was rejected: it round-trips existing data
  through memory, which is exactly what the Architecture section's decision (2)
  excluded, and it interleaves deletes with writes, which would cost the
  byte-neutrality the Conflict-policy section depends on.
- **Consequence, recorded because it is a compatibility break:** a `.nxs` file
  written by a PyRS predating this change has contiguous per-scan-point datasets
  and **cannot be appended to**. `tail_append` refuses it by name rather than
  failing part-way. Nothing depends on this in practice — no viewer writes
  NXstress through an append path, and the GUI hookup is phases 4-6 — but a file
  already on disk is affected. Decisions Log row 32.
- Note the rank: `stress_field` is `(n_scan, 3)`, not 1-D, so `_sample.py` takes
  the rank from the data rather than assuming it. The existing
  `test_Sample_stress_field_present` caught the assumption immediately.

**F2.2** (A4) — **A fixed-width `|S` string column silently truncates on
append.** Found while checking F2.1's fix was safe for the string fields, which
`a4_string_log_dtypes.py` had already shown to be the delicate ones.
`_Sample._writable` converted NumPy `<U` to the variable-length UTF-8 dtype and
**passed `|S` bytes arrays through untouched** — correct, since they are
writable as they stand. But a fixed-width HDF5 string column is sized by the
longest value present *when it is created*, and an append is by definition later
than that.
- Referent: [`probes/a4_growable_string_fields.py`](probes/a4_growable_string_fields.py),
  claim 5.
- Verdict: **the value is truncated and nothing raises.**

  ```console
    CLAIM   claim 5 -- appending a LONGER value to a fixed-width |S column
    RESULT  column dtype is |S8 (sized by the longest value at WRITE time)
            appended b'a_considerably_longer_filename.h5' (33 bytes)
            read back: [b'short.h5', b'a_consid']
            round-tripped intact: False  <-- SILENTLY TRUNCATED, no exception raised
  ```

  `Filename`, `start_time` and `end_time` are all bytes logs, so this was reachable
  by appending a workspace whose project file has a longer name than the first's.
- Action taken: `_writable` now coerces `|S` as well as `<U` to the
  variable-length dtype ([`_sample.py:312`](../../pyrs/utilities/NXstress/_sample.py#L312)).
  The read-back property is unchanged — both dtypes return `bytes` — so no reader
  is affected. The same probe confirms all three forms the writer produces
  (`list[str]`, `|S`, vlen UTF-8) write, reopen and tail-append correctly with
  `maxshape`/`chunks`; bare `<U` still fails at write, which is what `_writable`
  exists to prevent.

**F2.3** (A1) — **The scan-point family has two members this spec's table omits**,
and they are the two that do not live in a subgroup: `entry/start_time` and
`entry/end_time`, written per scan point by `NXstress._init`. The "Scope: all
position-aligned groups" table lists only the five subgroups. An append that
grew those five would have left both arrays short, with no error.
- Action: `_init`'s time computation is extracted to `_entryTimes`, shared with
  [`_appendEntryTimes`](../../pyrs/utilities/NXstress/NXstress.py#L483), so the
  two paths cannot diverge. Pinned by
  `test_append.py::TestRoundTrip::test_every_position_aligned_group_grows_by_the_same_count`,
  which asserts a single length across all fourteen.

**F2.4** (A1) — **`write()` cannot mean both "add an entry" and "grow an entry",
and this spec asks it to mean both.** The Overview states, correctly and with
probe evidence, that `write` already accumulates entries and that mode `"a"`
adds a new one. The NXstress Changes section then says to "dispatch `write()` to
the tail-append path when opened with mode `"a"`" — which would leave "add
another `NXentry` to an existing file", documented in `NXstress.py`'s usage
comment (at lines 152-156 before this pass), with no spelling at all.
- Resolution (stakeholder decision, 2026-10-01): **dispatch on whether the
  resolved entry exists, not on the mode.** `entry_number` omitted, or naming an
  existing entry, appends; naming no existing entry writes a fresh one. Mode
  governs file access, `entry_number` governs targeting. Decisions Log row 33;
  implemented in
  [`_resolveTarget`](../../pyrs/utilities/NXstress/NXstress.py#L237).
- **Overwriting** an existing entry's contents is a third operation, neither
  append nor create, and stays unimplemented. Note what that means under this
  dispatch: no input selects it, so the former collision guard is **unreachable
  by construction** rather than, as this finding first said, "the backstop". It
  is kept at `NXstress.py:232` regardless — the cost of that reasoning being
  wrong is an entry silently replaced instead of grown. Caught by
  `check_citations.py` on the re-run, which flagged the stale pointer that led
  back to it.
- A gap is **rejected**: `entry_number` beyond `max + 1` raises `ValueError`
  naming the next free number. A number past the end is far likelier a typo than
  an intent, and its silent outcome — a stray entry instead of the append that
  was meant — is not one a caller would notice.
- **`entry_number` had to become a `write()` argument as well as a constructor
  one**, which neither the spec nor the decision anticipated. Under the rule
  above a bare second `write()` in one session appends to the entry the first
  one created, so a constructor-only kwarg would have made "write two entries in
  one session" unexpressible — a capability `test_NXentry_multiple` already
  covered and the old usage comment advertised. That test now passes
  `entry_number=2` explicitly.

**F2.5** (A1/A5) — **The Conflict-policy section enumerates three outcomes and
needs seven.** Case A / Case B / duplicate classify the *peak index*. They say
nothing about the other ways an incoming workspace can disagree with the entry
it is joining, each of which produces a readable and wrong file rather than an
error. Added to the pre-flight pass, each raising `RuntimeError`:
  1. **Scan points disjoint from the whole entry.** A genuinely new compound key
     (Case A) may still reuse a scan-point *value*, and the reader attributes
     rows by value — `_workspaceSelections` raises on read. Caught at write now.
  2. **Reduced-diffraction mask set matches.** A mask the entry has no
     `DIFFRACTOGRAM` for would need a new group with no rows for the scan points
     already on disk.
  3. **Retained sample-log set matches** (`_Sample.validateAppend`,
     [`_sample.py:210`](../../pyrs/utilities/NXstress/_sample.py#L210)), compared
     by encoded column name rather than raw PV key, since that is what the file
     indexes by.
  4. **Optional sample fields match** — `temperature`, `stress_field`: an entry
     has one for all its scan points or for none.
  5. **Raw counts loaded on both sides or neither** (`_InputData.validateAppend`,
     [`_input_data.py:83`](../../pyrs/utilities/NXstress/_input_data.py#L83)).
  6. **Instrument geometry, detector shift and calibration agree**
     (`_Instrument.validateAppend`,
     [`_instrument.py:377`](../../pyrs/utilities/NXstress/_instrument.py#L377)) —
     one `NXentry` describes one instrument configuration.
  7. **Peak profile and background function match** the entry's `title` scalars.
     `_append_peak` already raises on a mismatch, but only after earlier groups
     have grown.
- **Two of these were initially written at their point of use and were wrong
  there**, which is the finding worth keeping. Both raised the right exception
  and both left a changed file, because `_appendEntryTimes` had already run. The
  spec says the check must run "before any resize/append call is made"; that
  sentence is load-bearing exactly as Follow-up 1 F1.2 warned, and only a
  byte-level comparison detects its violation. They are now in
  [`_classifyAppend`](../../pyrs/utilities/NXstress/NXstress.py#L325), with the
  point-of-use raise retained as a backstop.

**F2.6** (A5) — all of the above is now probeable, and probed.
[`probes/a5_append_preconditions.py`](probes/a5_append_preconditions.py) builds a
real entry through `NXstress.write` and drives every rejection path, comparing
the file's sha256 before and after each — the measurement
`a4_h5py_nexusformat_append.py` explicitly declined to make ("It does **not**
establish atomicity across a *partial* append"). All confirmed:

```console
  CLAIM   claim 2: Case B -- more scan points under a key the entry already holds
  RESULT  NotImplementedError: ... which this entry already holds, is not supported.
          file byte-for-byte unchanged: True

  CLAIM   claim 3: exact duplicate -- same key, overlapping scan point
  RESULT  RuntimeError: ... scan point(s) [2, 3] are already present in this entry ...
          file byte-for-byte unchanged: True

  CLAIM   claim 4a: Case A precondition 1 -- the new workspace contributes no PeakCollection
  RESULT  RuntimeError: ... input workspace(s) [0] contribute no `PeakCollection`.
          file byte-for-byte unchanged: True

  CLAIM   claim 4b: Case A precondition 2 -- the target entry has no discriminator column
  RESULT  RuntimeError: ... the target entry carries no discriminator columns ...
          file byte-for-byte unchanged: True

  CLAIM   claims 2-3: Case B leaves the instance usable; a duplicate does not
  RESULT  after NotImplementedError: the later Case-A append SUCCEEDED -- instance stayed usable
          after RuntimeError:       the later append raised RuntimeError: ... no longer usable.
```

This closes the A5 gap Follow-up 1 recorded ("This spec's conflict
classification, Case-A/Case-B dispatch and `entry_number` targeting **cannot be
probed** — none of it exists yet"). The coverage matrix moves 04c's A5 from `~`
to `✓✓`.

**F2.7** (A3) — **`if dgram_name in fit.NXdata` can never be true**, so the
pre-existing guard against a duplicate `DIFFRACTOGRAM` group in `_Fit.init_group`
is dead code. `NXgroup.NXdata` returns a **list of `NXdata` objects**, not a
mapping of names, so a `str` is never a member of it:

```console
  children:   ['DESCRIPTION', 'DIFFRACTOGRAM', 'background_parameters', ...]
  NXdata attr: [NXdata('DIFFRACTOGRAM')]
```

Harmless as it stood — `mask_keys` is a `set`, so the duplicate it guards against
cannot arise on a fresh write — but the append path's equivalent check needed to
work, and inherited the bug before a smoke test caught it. Both now use
`in fit`. Found by implementation, claimed by no document.

**F2.8** (A1/A2) — **`_instrument.py` and `_definitions.py` are not in this
spec's ownership row.** `README.md` §5 lists 04c as touching
`pyrs/utilities/NXstress/{NXstress,_input_data,_sample,_fit,_peaks}.py`, and the
"Scope: all position-aligned groups" table places `_instrument.py` under
"Name-keyed, no insertion needed" on the strength of `_Masks`. That is right
about `_Masks` and wrong about the module: `monochromator/wavelength` is written
per scan point and is sliced by `rows` on read, so it is a scan-point-family
member and must grow. `_definitions.py` gains the three helpers. Both added to
§5; `check_ownership.py` would otherwise report them.

**F2.9** (A1) — Follow-up 1 F1.3's reword, which Decisions Log row 22 adopted,
**had not been applied**: the Conflict-policy section still read "isn't possible
without adding a new on-disk column, which this spec's tail-append design does
not do". F1.3 assigned the reword to the implementing PR, and it is applied now.
Noting the tension this sits in: the convention is that a subspec body is left as
the record of what was believed and Follow-ups carry the corrections, but F1.3's
`Action` is explicit and specific. The body is edited, the Follow-up records that
it was, and the original wording is quoted in F1.3 where it remains readable.

**F2.10** (A1) — **The test tier is unit, not integration.** This spec's Tests
section, `README.md` §5's inventory and `probes/README.md`'s Disposition column
all specify `tests/integration/test_nxstress_append.py`. All three predate 04b,
whose structurally identical round trip landed as
`tests/unit/pyrs/utilities/NXstress/test_multi_workspace.py` — unmarked, built on
`minimal_HidraWorkspace`, writing to `tmp_path`, touching no real data. `CLAUDE.md`
agrees: "a synthetic in-memory round trip through `tmp_path` that stays inside one
component's own public API … is unit". Three documents against one precedent and
the tier rule; the precedent and the rule win, and the three documents are
corrected. Shipped as
[`tests/unit/pyrs/utilities/NXstress/test_append.py`](../../tests/unit/pyrs/utilities/NXstress/test_append.py).
Decisions Log row 34.

### Invariants written by this PR

`review/findings.md` §5 item 2 — "tail-append grows each dataset by exactly N,
leaves existing rows unchanged, and a pre-resize abort is byte-neutral" — is
written, at unit rather than the integration tier recorded there (F2.10):
`test_append.py::TestTailAppendHelper` for the growth rule and the
fixed-size refusal, and the `digest(...)` assertion on every rejection test for
byte-neutrality. `probes/README.md` assigns the same promotion to
`a4_h5py_nexusformat_append.py`; it is satisfied by the same tests.

**One invariant not on anyone's list, and the most valuable one here.**
`test_append.py::TestWriterEmitsResizableDatasets` writes an entry, reopens it,
and **sweeps** every dataset whose first axis is the scan-point axis, asserting
each is extendable. It iterates rather than naming fields — the
[`test_definitions.py`](../../tests/unit/pyrs/utilities/NXstress/test_definitions.py)
idiom — so a per-scan-point field added later without `growable` fails this test
rather than failing a user's append months afterwards. F2.1 is precisely the
defect it would have caught, and nothing in the series was looking for it. Its
companion `test_the_sweep_notices_a_field_that_loses_growable` adds a fixed-size
field *locally*, not through the writer, so the detector is checked against
something other than the code under test.

### Verification, as run

- `pixi run test-unit` — **412 passed**, 150 deselected (was 360 after 04b). *(403 when Follow-up 2 was written; the nine added in the Follow-up 3 round.)*
- `pixi run test-integration` — **104 passed**, 28 skipped, 2 xfailed.
- `pixi run test-gui` — **16 passed**.
- "Confirm by inspection that no GUI file calls `NXstress(..., "a")`" —
  confirmed: every call in `pyrs/interface/` is `"w"` or `"r"`
  (`combine_runs_model.py:37`, `peak_fitting_model.py:97`/`:234`,
  `texture_fitting_model.py:52`/`:197`).
- "Manual check … confirm each group is locally sorted, globally segmented" —
  run as the last claim of `a5_append_preconditions.py` and pinned by
  `test_append.py::TestRoundTrip::test_file_is_locally_sorted_globally_segmented`,
  which appends a discriminator value sorting *before* the one on disk, so a
  re-sorting append would be detected rather than merely assumed absent.

**F2.11** (A3) — **The `# TODO` three of this spec's claims point at no longer
exists**, because this PR is what resolved it. `_Peaks.init_group` carried
"these code sections are implemented in a form that allows new scan-point data
to be appended / However, at present, appending data is not yet supported",
and the Architecture, Scope and NXstress Changes sections each cite it as
evidence that the mechanism is already half-built. It was, and the comment is
now replaced by the `data=None` branch it predicted. The three body citations
are repointed at `init_group` itself (`_peaks.py:289-312`) and reworded to the
past tense, since a pointer to a deleted comment resolves to whatever happens to
occupy those lines. Mentioned because this is the ordinary end-state of a `TODO`
cited as evidence: the citation outlives its referent by exactly one PR.

Other pointers corrected in place this pass, all pure drift with the claims
around them unchanged: `_peaks.py:246-338` → `:425-535` (`peakCollectionRanges`),
`_peaks.py:190-244` → `:315-390` (`_append_peak`), `_input_data.py:44-46,63-72`
→ `:60-79`, and `NXstress.py:151-152` → `:232` (the overwrite guard, which this
PR moved rather than removed — see F2.4). Follow-up 1's "Checked and accurate"
list still quotes the superseded values and is left as written; it records what
was true when it was written, which is the point of an append-only section.

---

## Follow-up 3 — 2026-10-01 (sub-agent review round)

Follow-up 2 was written against code that passed 403 tests, three clean tiers
and the whole toolkit. Two review sub-agents — one on design, one on tests —
then independently found the **same defect**, and one of them demonstrated it
corrupting a file through the public API. That is the finding worth keeping:
the property Follow-up 2 reported as closed was closed for every path the
tests covered and open on the one they did not.

**F3.1** (A5) — **"A rejected append leaves the entry byte-for-byte unchanged"
was false.** F2.5 moved six checks into the pre-flight pass and recorded that
two of them had initially sat at their point of use. It missed that
`tail_append` itself makes two refusals — a non-resizable dataset, and a
trailing-axis disagreement — and that **neither was pre-flighted**. They
therefore fired during mutation, after earlier groups had grown.
- The giveaway, in hindsight: `_definitions.appendable` was written precisely
  so the pre-flight could ask "can this grow?", and **it had no production
  caller at all**. A predicate nothing asks is a design that did not land.
- Reproduced through `NXstress.write`, with the entry written at 20 two-theta
  bins and the appended batch reduced onto 25 — not a contrived input but the
  ordinary difference between two reduction passes:

  ```console
    before: start_time (3,)  SAMPLE/scan_point [1, 2, 3]  XAXIS (3, 20)
    RAISED: RuntimeError NXstress: cannot append to '/entry/FIT/DIFFRACTOGRAM/XAXIS':
            the incoming rows have trailing shape (25,), the existing data (20,)
    file unchanged? False
    after:  start_time (6,)  SAMPLE/scan_point [1, 2, 3, 4, 5, 6]  XAXIS (3, 20)
    read back OK: [[1, 2, 3, 4, 5, 6]]
  ```

  27 datasets at six rows, three at three, **and it reads back without error**
  as one workspace of six scan points, three of which have no diffraction data
  and no peaks. Silent corruption, which is worse than the crash it replaced.
- Why the tests did not catch it, which is the structural lesson: the refusal
  *was* tested, twice — at the `tail_append` level and at the
  `_Diffractogram.init_group` level. Neither went through `NXstress.write`, so
  neither could observe the 27 datasets that had already grown. **Every refusal
  reachable during an append needs one end-to-end test with a `digest()`
  assertion**, not a unit test of the function that raises. `pytest.raises`
  passed throughout; only the digest fails.
- Corrections, all in the pre-flight:
  - [`_validateAppendableShapes`](../../pyrs/utilities/NXstress/NXstress.py#L644)
    sweeps every per-scan-point dataset in the target entry and refuses the
    append as a whole if any cannot grow — the production counterpart of
    `TestWriterEmitsResizableDatasets`, reimplemented rather than shared with it
    so the test can fail independently of the code it guards.
  - [`_Fit.validateAppend`](../../pyrs/utilities/NXstress/_fit.py#L706) and
    [`_Diffractogram.validateAppend`](../../pyrs/utilities/NXstress/_fit.py#L519)
    check the two-theta bin count per mask.
  - [`_InputData.validateAppend`](../../pyrs/utilities/NXstress/_input_data.py#L83)
    gains the detector pixel count; it checked only *whether* counts existed.
  - The mutation phase is wrapped so that **any** escape sets `self._invalid`
    ([`NXstress.py:395`](../../pyrs/utilities/NXstress/NXstress.py#L395)). The
    policy was exactly inverted before: a pre-flight rejection, where the file
    is untouched, invalidated the instance; a mutation failure, the only case
    where the file is damaged, left the caller free to append onto the wreckage.
- Re-measured after the fix, through the same input:

  ```console
    RAISED: RuntimeError NXstress._fit: cannot append -- the incoming reduced
            diffraction for mask '_DEFAULT_' has 25 two-theta bin(s), the target entry 20.
    file unchanged? True
    after:  start_time (3,)  SAMPLE/scan_point [1, 2, 3]  XAXIS (3, 20)
  ```

  `probes/a5_append_preconditions.py` gains both cases (claim 6), and
  `test_append.py::TestPreconditions` gains seven end-to-end refusal tests, each
  with its `digest` assertion.

**F3.2** (A1) — **`_Sample._append_group` validated after mutating**, and its own
comment said so: "a mismatch found mid-append would already have grown
something" sat *below* a `tail_append` of `scan_point` and the three coordinate
axes. Same class as F2.5's two, missed in the same pass. The call is now the
first statement ([`_sample.py:287`](../../pyrs/utilities/NXstress/_sample.py#L287)),
and the coordinate arrays are built and shape-checked before anything is
resized rather than appended as they are computed.

**F3.3** (A3) — **An appended workspace's detector masks were silently
discarded.** `_Instrument.init_group`'s append branch grows `wavelength` and
returns; the mask arrays are entry-wide and were written fixed-size, so they
*cannot* grow. `_classifyAppend`'s mask check compares `ws._diff_data_set`
keys, which is a different set from `_Masks.mask_keys(ws)` — a workspace could
pass it carrying masks the entry has no record of, and `masksFromNexus` would
hand it the first write's masks on read. Now refused in
[`_Instrument.validateAppend`](../../pyrs/utilities/NXstress/_instrument.py#L377),
reusing the existing `_validate_masks_agree`.

**F3.4** (A4) — **`data: NXdata = None` is a trap under `@validate_call_`.**
Pydantic does not validate defaults, so omitting the argument works, but
passing it explicitly does not: `_InputData.init_group(wss)` succeeds where
`_InputData.init_group(wss, data=None)` raises `ValidationError: Input should be
an instance of NXdata`. The first caller to write `data=maybe_group` would hit
it. All seven `data` parameters are now `X | None = None`, and
`_Fit.init_group`'s had no annotation at all. **mypy cannot catch this**:
`nexusformat` is untyped and `ignore_missing_imports` makes `NXdata` resolve to
`Any`.

**F3.5** (A1) — smaller corrections from the same round:
- `if dgram_name in fit.NXdata` (F2.7) had a sibling: `_resolveTarget` re-derived
  entry-name parsing with `rsplit` instead of using `suffix_from_group_name`,
  the declared inverse of `group_naming_scheme`, and its `range(1, len(...)+1)`
  term reduced to `[1]` after its own existence filter — a comment reading
  "derived from the names present rather than from a count", immediately above
  code using a count.
- Appending to an entry written with `write([ws], [[]])` was refused for
  "disagreeing with the target entry's `_undefined_`" — the writer's own
  sentinel. Now refused for the real reason: such an entry records no fit model
  and no discriminator values, so nothing appended to it could be told apart.
- `_classifyAppend` reached 158 lines doing seven jobs, which is the wrong shape
  for the one method a reader must follow in full to believe the no-op property.
  Split into six named checks called in sequence.
- `_Sample.OPTIONAL_SCAN_POINT_FIELDS` is a parallel definition: the fresh-write
  path still spells each field out, because each carries its own attribute rule.
  Cross-referenced both ways rather than unified, with the failure mode named —
  a field added to one and not the other is written and silently never grown.
- `TestWriterEmitsResizableDatasets` kept a 17-name `ENTRY_WIDE` denylist of
  which **two names did not exist in any entry this writer produces** and 14
  were already excluded by the scalar check. Removed: the scalar filter does the
  work. Its `n_scan` moved from 3 to 7, because the sweep matches by length and
  the writer emits fixed-size arrays of length 1, 2 and 16 — a collision would
  have been a false failure, and nothing recorded the constraint.
- The lockstep test enumerated 15 dataset paths by hand, in the class whose
  docstring argues against exactly that. It now *discovers* the family from the
  pre-append file, so a field added later is covered without editing it.
- `createPeakCollection` gained a `mask` parameter, replacing a `collection._mask`
  poke in the new mask test.

### Invariants added in this round

Seven end-to-end refusal tests in `TestPreconditions`, each asserting the file's
sha256 is unchanged: two-theta width, detector pixel count, detector shift,
background function, detector mask set, a legacy fixed-size entry, and a
mutation-phase failure invalidating the instance. The last is reached by
monkeypatching `_sample.tail_append`, since every *known* cause is now
pre-flighted — the guarantee under test is the invalidation, not the trigger.

Plus `test_the_sweep_reaches_input_data` (the raw-counts datasets were outside
the resizability guarantee, because the shared fixture carries no counts and a
length-matched sweep drops zero-length arrays), and
`test_a_workspace_lacking_a_mask_is_nan_filled_on_append`.

### What this round says about the process

`process.md` §5.6 budgets a document-correction pass per PR. This was a
*code*-correction pass, found after the PR had passed its own `## Verification`,
all three tiers and the full toolkit — none of which could see it, because the
defect was in a path no test took and no probe built. The audit's own
anti-pattern list already names the mechanism twice: "a probe that reimplements
its counterparty is testing the reimplementation" (F2.1, the `maxshape` fixtures)
and "reading source tells you what is written, not what it means". **F3.1 is the
third instance and the first that reached shipped code.** The practice that
caught it was neither auditing nor testing but an adversarial read by someone
who had not written it, and the cheap generalisation is the rule in F3.1: a
refusal is only verified where it is reachable from the public API, with the
file compared byte-for-byte.
