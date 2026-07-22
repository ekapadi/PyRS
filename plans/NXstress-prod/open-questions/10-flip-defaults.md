# Open Questions — 10 Flip Defaults: NXstress Becomes Primary

**Spec:** [10-flip-defaults.md](../10-flip-defaults.md)
**Blocking:** Partially — Q1 gates *entering* this spec at all; Q2 is a
decision needed during implementation.

---

## Q1 — Are the trigger criteria for entering this spec actually met, and who signs off?

The spec lists three trigger criteria itself but flags them as provisional:
> **Trigger criteria** for entering this spec (to be confirmed at the end of
> spec 02 / start of spec 03):
> - All NXstress round-trip tests pass.
> - At least one real-data smoke test has been run by a scientist and signed off.
> - No open correctness bugs against the NXstress writer or reader.

None of the three currently has a concrete owner, a defined "scientist"
signing off, or a tracked bug list to check against "no open correctness
bugs." This mirrors the plan-level README's own note that Phase 6
acceptance criteria are "to be defined at the end of Phase 1"
(README.md:224, :419) — as of this writing that definition still hasn't
happened.

**Why it matters:** without a concrete checklist and named sign-off owner,
"entering Phase 6" is a judgment call that could happen prematurely (before
NXstress is genuinely trustworthy as the *only* save format offered) or be
indefinitely delayed (no one is unambiguously responsible for declaring the
criteria met).

**Next step:** convert the three bullet points into a literal checklist with
an owner and a link to wherever "open correctness bugs" would be tracked
(e.g., a GitHub issue label); do this at the latest by the end of Phase 1,
per the plan's own stated schedule.

**Chris:** Instrument scientist will confirm that the new format provides the same functionality as the previous data. One route is to save data both data in parallel, HIDRA Project files and NXStress files.


---

## Q2 — Reject, or silently route, a manually-typed `.h5` save path?

The spec's own Verification section poses this as an open either/or rather
than a decided behavior:
> Smoke test: attempt to save as `.h5` (by typing the extension manually in
> the save dialog); confirm the viewer either rejects it with a clear
> message or routes it through the NXstress writer regardless.

**Why it matters:** these produce very different user experiences — silently
routing a `foo.h5` filename through the NXstress writer would produce a file
with a `.h5` extension but NXstress-format contents (misleading and
potentially breaking any external tooling that dispatches on extension);
rejecting outright is safer but needs an explicit error message and matching
GUI validation logic that isn't described anywhere else in the plan.

**Next step:** decide explicitly (rejecting with a clear message is the
safer default, consistent with the plan's extension-is-authoritative
policy in README.md:216-218) and update the spec's Scope/NXstress Changes
section to describe the validation logic needed, rather than leaving it as
an either/or in the verification step alone.

**Chris:** NXstress should automatically apply the correct extenssion and silently reoute to the format if needed.

