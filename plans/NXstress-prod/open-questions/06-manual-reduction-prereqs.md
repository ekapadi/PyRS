# Open Questions — 06 Manual Reduction PyRS Prerequisites

**Spec:** [06-manual-reduction-prereqs.md](../06-manual-reduction-prereqs.md)
**Blocking:** No — both questions are scoped as things to check during this
spec's own implementation, not external blockers.

---

## Q1 — Should `save_project` delegate to, wrap, or replace `ReductionApp.save_diffraction_data`?

Spec text is explicit that this isn't decided yet: *"Specifically check how
`ReductionApp.save_diffraction_data` (L348) is currently called and whether
`save_project` should delegate to it, wrap it, or replace it."*

**Why it matters:** these three options have different blast radii —
delegating keeps `save_diffraction_data` as the single source of truth and
risks double-invocation bugs if both are called from different code paths;
wrapping adds a thin new code path that must stay in sync; replacing risks
breaking whatever currently calls `save_diffraction_data` directly if other
callers exist beyond the manual-reduction flow.

**Next step:** grep all callers of `ReductionApp.save_diffraction_data`
before deciding; if `HB2BReductionManager.save_project` is the only
consumer, replacing/delegating is safe — if other paths call it directly,
wrapping without touching the existing signature is safer.

**Chris:** There was a dead code instance of `save_diffraction_data` that has been deleted in a recent PR. 

---

## Q2 — Are `nexus_conversion.py:118` and `:374` reachable from the manual-reduction save path, from some other path, or dead code?

The spec frames this as a three-way branch to resolve during the audit,
without pre-judging the answer: implement if reachable from save, file a
separate issue if reachable elsewhere, remove if dead.

**Why it matters:** this determines whether this spec's scope grows (if
either branch is reachable from save and must be implemented here), spins
off a separate tracked issue (if reachable elsewhere), or shrinks (if dead
code can simply be deleted). Spec 07 blocks on this spec being "done," so
an ambiguous or deferred answer here would silently push scope into spec 07.

**Next step:** trace call graphs from `HB2BReductionManager.save_project`
and from `ManualReductionViewer`'s other entry points into
`nexus_conversion.py` to determine reachability for both line numbers
before deciding which of the three branches applies.

**Chris:** `ManualReductionViewer` is a realatively old codebase. The `ManualReductionViewer` should use `HB2BReductionManager.save_project`.