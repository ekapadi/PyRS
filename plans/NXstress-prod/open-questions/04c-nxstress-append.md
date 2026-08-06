# Open Questions — 04c NXstress Append Mode (library only)

**Spec:** [04c-nxstress-append.md](../04c-nxstress-append.md)
**Blocking:** No — all previously-open design questions are now resolved
(see below). What remains is implementation detail, not user-facing
behavior.

---

## Q1 — RESOLVED: write mode, entry targeting, and conflict policy

Originally three separate open items (carried over from the pre-split spec
07's Q1/Q2, plus a new entry-targeting question that surfaced once the
architecture was worked out). All three are now decided together, since they
shape one coherent API:

- **Architecture:** append resizes and inserts directly into the on-disk
  arrays of the target entry; it does **not** reconstruct the existing
  entry as `HidraWorkspace`/`PeakCollection` and rewrite via 04b's merge
  path. Driving concern: a reduction/append cycle shouldn't have to
  round-trip potentially large existing raw-count data through PyRS's outer
  types just to grow it.
- **Write mode:** always explicit — `NXstress(path, "a")` — no auto-detection
  based on whether the file/entry already exists. This was already the
  spec's leaning before this round; it's now fully consistent with entry
  targeting also being explicit.
- **Entry targeting:** `NXstress(path, "a")` with no further argument
  targets the **last** existing `NXentry`; `entry_number` is an optional
  override for targeting an earlier entry.
- **Conflict policy:** reject. Any overlapping scan point or peak-index row
  raises `RuntimeError` (not `ValueError` — deliberately distinct from
  `validateNoDuplicatePeaks`'s fresh-write duplicate case, since this
  represents a violated invariant on already-committed data, not an
  expected bad-input case). The check runs against all affected groups
  before any mutation, so a rejected append is a true no-op. After raising,
  the `NXstress` instance is invalidated for further writes in that
  session — the caller must re-open rather than continue.

See the spec's Overview for the full reasoning; nothing here blocks
implementation.

---

## Q2 — RESOLVED: append scope covers all position-aligned groups, not just input_data and peaks

The spec as originally drafted (inherited from the pre-split spec 07) only
listed `_input_data.py` and `_peaks.py` as needing append logic. That
undercounts what a consistent append actually requires:
`_fit.py::_PeakParameters`/`_BackgroundParameters` build their rows via the
exact same sort order as the peaks index (`_fit.py:87`), so they're
positionally aligned with it, not independently keyed — and
`_sample.py`/`_fit.py::_Diffractogram` are both indexed by `scan_point`,
same as `_input_data.py`'s `detector_counts`. A partial append that only
grew some of these would desynchronize the entry with no error to signal it.

**Decided:** full scope — both position-aligned families (peak-index family:
peaks + peak_parameters + background_parameters; scan-point family:
detector_counts + sample logs + diffractogram), inserted in coordinated
lockstep within each family. `_instrument.py::_Masks` needs no new work — it's
name-keyed, not position-sensitive, and already accepts an existing group to
extend.

---

## Q3 — Shared insertion-position helper: one utility, or one per group?

The spec describes computing insertion positions once per family and
applying them across every group in that family (e.g., `_peaks.py` computes
positions for the peak-index family; `_input_data.py`/`_sample.py`/
`_Diffractogram` need a shared computation for the scan-point family). It
doesn't specify whether this is a single shared utility function (e.g. in
`_definitions.py` or a small new module) called from each group's
`init_group`, or independently duplicated logic per group that happens to
produce the same result given the same inputs.

**Why it matters:** duplicated logic risks the two families' insertion
positions silently diverging if one copy is later modified and the other
isn't — exactly the kind of desync this spec exists to prevent elsewhere.

**Next step:** implement as a single shared helper (e.g.
`_definitions.py::insertion_positions(existing_keys, new_keys) -> np.ndarray`
using `np.searchsorted` or equivalent), called identically by every group in
a family. Cosmetic/structural, not a behavior decision — default to sharing
unless implementation reveals a reason not to.

---

## Q4 — Does the conflict check need to handle a family-cross-check (e.g. a scan point present in `_input_data` but not yet in `_sample`)?

The conflict policy (Q1) assumes each family's groups are always mutually
consistent going into an append — i.e., that no prior write ever left, say,
`detector_counts` and `SAMPLE_DESCRIPTION` with different scan-point sets
for the same entry. That should hold given 04b's write path always writes
all groups in a family together, but append's conflict check doesn't
currently specify whether it should also *verify* that invariant on the
existing entry (defensively) before proceeding, or simply trust it.

**Why it matters:** if the invariant were ever violated (e.g. by a bug in
an earlier write, or a hand-edited file), an append that trusts it could
silently produce a still-inconsistent result rather than surfacing the
pre-existing problem.

**Next step:** decide at implementation time whether the conflict check
includes a defensive cross-group consistency check on the *existing* entry
before applying the new data, or documents that it assumes (without
verifying) the existing entry is internally consistent. Low priority —
does not block starting implementation.
