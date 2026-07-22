# Open Questions — 09 Fit Spectrum & Calibration Fidelity (NXstress)

**Spec:** [09-fit-spectrum-nxstress.md](../09-fit-spectrum-nxstress.md)
**Blocking:** No — both items are inherited unknowns from spec 08 that
resolve automatically once that spec's investigations conclude.

---

## Q1 — Does the NXbeam profile get populated, or closed as "not applicable"?

This spec's NXstress Changes section states the branch explicitly:
*"Per the spec-08 finding: either populate the NXbeam field from the
workspace attribute identified in spec 08, or add a one-line comment closing
the TODO as 'not applicable' ..."* — i.e., this spec cannot be finished as
written until [spec 08 Q1](08-fit-spectrum-prereqs.md#q1-does-a-beam-intensity-profile-data-path-exist-anywhere-in-pyrs)
is answered.

**Why it matters:** this is a direct pass-through dependency — there is no
way to know which of the two `_instrument.py:127` code paths to write until
spec 08's trace is complete.

**Next step:** none beyond tracking spec 08 Q1; once that resolves, this
item is mechanical.

**Chris:** We handle within `peak_collections.py` using the `self._exclude_list`

---

## Q2 — Where and how should the "sub-run did not converge" `NaN` fallback be logged?

Spec text: *"If the method is unavailable for a given scan point (e.g., fit
did not converge), fall back to `NaN` for that point only with a logged
warning."* The spec doesn't specify the logging channel, level, or whether
the warning should be surfaced to the GUI (e.g., a status-bar note similar
to the Phase-6 deprecation hint) or remain a backend-only log line.

**Why it matters:** a silent per-scan-point `NaN` in an otherwise
"fully populated" file (per this spec's own Delivered Feature claim: *"no
NaN placeholders remain for data that PyRS actually computes"*) could
confuse a downstream NXstress-aware consumer who has no visibility into
*why* one scan point differs from its neighbors, unless the warning is
discoverable somewhere.

**Next step:** decide whether this warrants a GUI-visible warning (consistent
with how spec 04 handles missing sx/sy/sz — "fall back to NaN gracefully ...
with a logged warning rather than a hard failure") or a log-only note is
sufficient, and use the same convention across both specs for consistency.

**Chris:** We handle within `peak_collections.py` using the `self._exclude_list` this list is also exported to the csv files for record keeping
