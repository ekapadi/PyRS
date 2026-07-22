# Open Questions — 08 Reconstructed Fit Spectrum & Calibration Fidelity (PyRS)

**Spec:** [08-fit-spectrum-prereqs.md](../08-fit-spectrum-prereqs.md)
**Blocking:** No — each item is itself an investigation task within this
spec; the "open question" is the investigation's undetermined outcome.

---

## Q1 — Does a beam-intensity profile data path exist anywhere in PyRS?

The spec frames this as a live unknown to be traced, not an assumed
capability: *"Trace the reduction pipeline to determine if a beam-intensity
profile ... is ever stored in `HidraWorkspace` or `SampleLogs`. If it is:
document the attribute name ... If it is not: mark `NXbeam` intensity
profile as permanently optional and close ... as 'not applicable'."*

**Why it matters:** this is a binary outcome with very different downstream
work — either spec 09 gets a concrete attribute to read, or the NXbeam TODO
in `_instrument.py:127` closes permanently with no further work ever
required. Right now neither branch has been confirmed.

**Next step:** grep `HidraWorkspace` and `SampleLogs` usage across the
reduction pipeline (`nexus_conversion.py` and related reduction modules) for
any monitor-count or beam-profile concept before concluding either way.

**Chris:** We make an assumption that the beam-intensity profile is uniform

---

## Q2 — What does `model_variance` being "NaN if not computable" mean in practice — how often, and is that acceptable long-term?

The spec's own method signature description hedges: *"`model_variance` —
same shape (propagated from fit parameter uncertainties, **or `NaN` if not
computable**)"* — without defining when uncertainty propagation is
expected to fail, or whether that's a rare edge case or a common one
depending on which fit-engine backend is in use.

**Why it matters:** spec 09 depends on this method to populate
`diffractogram/fit_errors` for "real" data. If `NaN` fallback turns out to
be the common case rather than a rare edge case (e.g., for one of PyRS's
several supported peak-shape functions), the Phase 5 "no NaN placeholders
remain" goal (per spec 09's Delivered Feature) would be undermined for a
predictable, recurring subset of data rather than just non-converged
outliers.

**Next step:** during implementation, test the new method against each
supported peak-shape/background function used by PyRS's fit engine and
note which ones (if any) can't propagate uncertainty — document this
explicitly in the method's docstring rather than leaving it implicit.

**Chris:** We can extend `peak_collection.py:__set_fit_status` L399-L419 to automatically mask entereies when a `diffractogram/fit_errors` is `NaN`.

---

## Q3 — What is the actual (confirmed) `STRESS_FIELD` shape?

`_sample.py:107`'s comment says *"No example data existed when the writer
was drafted."* The spec requires loading a real HB2B dataset and checking,
but the answer isn't known until that's done.

**Why it matters:** spec 09 directly depends on this spec's answer to fix
`_sample.py:107`'s dimensions — an incorrect guess here propagates forward
as a second wrong guess in spec 09 rather than a fix.

**Next step:** obtain a real HB2B dataset with a populated `STRESS_FIELD`
sample-log entry (check with instrument scientists/facility data if none is
readily available in test fixtures) and inspect its shape/dtype directly.

**Chris:** The examples folder has three files, `HB2B_2246.h5, HB2B_2247.h5, and HB2B_2251.h5`, that represent the 3 strain directions .
