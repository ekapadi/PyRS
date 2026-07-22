# Open Questions — 05 StrainStressViewer NXstress Hookup

**Spec:** [05-strain-stress-viewer.md](../05-strain-stress-viewer.md)
**Blocking:** **Yes** — Q1 is a hard implementation gate stated in the spec
itself; nothing in "Schema-driven PeakIndex extension" should be built until
it's answered.

---

## Q1 — Is a `direction` axis on `NXreflections` schema-conformant? {#q1}

The spec's own warning banner (05:20-26):
> **⚠ Schema check required before implementation begins.** Before modifying
> `_peaks.py::PeakIndex`, verify against the canonical NXstress.xml schema
> whether adding a `direction` axis to `NXreflections` is conformant, or
> whether a different mechanism (multi-NXentry, dedicated stress-field
> subgroup, etc.) is the schema-intended approach.

The plan's Decisions Log (README.md:448) records this as **provisional**,
explicitly pending re-evaluation at Phase 3 kickoff.

**Why it matters:** this decides the entire shape of the spec's NXstress
Changes section — whether `PeakIndex` gains a `direction` field (current
assumption), or whether the three directions instead live in three separate
`NXentry` groups, or in some other subgroup structure the schema author
intended. Getting this wrong means redoing `_peaks.py::sort_key`,
`validateNoDuplicatePeaks`, `_init`, `init_group`, and
`peakCollectionsFromNexus` a second time.

**Next step:** locate or obtain the canonical NXstress.xml schema
definition and check `NXreflections`' allowed fields/axes; update the
Decisions Log entry (README.md §4, Q3) with the outcome before writing any
`_peaks.py` code for this spec.

**Response from Chris:** The `direction` can be defined based on the description logs. But the stress-strain viewer does not automatically search for this type of log. Instead, a User defines the `direction` in the GUI or API. We can auto populate anything that is then udpated when the stress-strain calculation is completed.

---

## Q2 — Can `HidraWorkspace` represent direction-merged sample-log content, or does it need a new container?

Spec text (PyRS Changes): *"confirm `HidraWorkspace` can represent (or
cleanly hold) sample-log content from a direction-merged measurement. If a
direction-aware container is needed, design it here."* This is phrased as
an open design question, not a confirmed approach.

**Why it matters:** if `HidraWorkspace` can't cleanly hold three directions'
worth of sample logs, a new container type is a nontrivial PyRS-side design
task that isn't scoped or estimated anywhere in the plan — it would expand
this spec's PyRS-side footprint substantially beyond "confirm and resolve
`NotImplementedError`s."

**Next step:** attempt to construct a direction-merged `HidraWorkspace` in a
throwaway script/test early in this spec's implementation, before committing
to the NXstress-side `PeakIndex` changes — if it doesn't fit cleanly, the
container design becomes a prerequisite sub-task.

**Response from Chris:** The current approach is that a user would provide 1 `HidraWorkspace` per direction. A final NXstress output should contain the 2/3 directions with provenance about the calculation. 

Could we define the nexusformat to have the following approach? A user provides 3 nexus formated files with a single direction and with a header note that states `NXstrain`. The stress calulator would offer the option to output a NXstress file with 2 or 3 directions with provenance about the calculation.

---

## Q3 — Which specific `NotImplementedError` methods in `fields.py` will the round-trip test actually exercise?

The spec deliberately scopes this down: *"resolve any `NotImplementedError`
in `StrainField` / `StressField` that is exercised by the read-back path ...
Fix only the methods the round-trip test actually calls"* — but the actual
set of methods among the 11 flagged in the README (`fields.py` L239, 611,
816, 927, 956, 960, 964, 983, 986, 994, 1184) isn't known until the test is
written.

**Why it matters:** the spec's own scope and effort estimate depend on this
— if the read-back path for a direction-indexed `StressField` happens to
exercise most of those 11 methods, this becomes a much larger PyRS change
than "fix only what's hit" implies at a glance.

**Next step:** write the round-trip test's assertions first (against a stub
`StressField` reconstruction), run it, and let the resulting
`NotImplementedError` tracebacks enumerate the actual method list.

**Chris:** Do existing tests define the `NotImplementedError`? 
