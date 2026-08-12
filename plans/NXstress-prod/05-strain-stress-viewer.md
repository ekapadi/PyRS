# 05 — StrainStressViewer NXstress Hookup

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** 3
**Depends on:**
- [01 — Config infrastructure & test framework](01-config-and-test-infra.md)
- [04 — NXstress internal cleanup](04-nxstress-internal-cleanup.md)
- [04b — Multi-workspace NXstress I/O](04b-multi-workspace-nxstress.md)

---

## Overview

Wire NXstress into the StrainStressViewer so that multi-direction stress
measurements (directions 11, 22, 33) can be saved and loaded as a single
`.nxs` file.

The current viewer loads N separate `HidraProjectFile`s per direction into
three parallel slots (`filenames_11/22/33`). This is exactly the N-workspace
case spec 04b builds general support for: one `HidraWorkspace` per direction
in, one `.nxs` `NXentry` out. This spec's contribution is narrower than
originally scoped — it declares `direction` as one of 04b's discriminator
fields, rather than inventing its own index-extension machinery. The
schema question of whether `NXreflections` can carry additional index
columns at all is answered once, generally, at 04b kickoff (see
`open-questions/04b-multi-workspace-nxstress.md` Q1); this spec only needs
to confirm that `direction` is the right name and semantics for one such
column.

### `direction` needs a home on `HidraWorkspace`, not just a config entry

04b resolves discriminator values *from* the workspace object (a matching
`@property`, else a `SampleLogs` fallback) — it does not accept them as a
separate argument to `write()`. But today, the viewer tracks direction
purely at the *model* level (`filenames_11/22/33` slots); `HidraWorkspace`
has no notion of direction at all. Per Chris's answer to
`open-questions/05-strain-stress-viewer.md` Q1 — direction is something "a
User defines... in the GUI or API," not something derived from existing log
data — **decided:** this spec adds a real, settable `direction` property to
`HidraWorkspace`, per 04b's own forward-looking convention note (any later
spec wanting a first-class accessor should add a `@property`, matching
`HidraWorkspace`'s existing style). The viewer sets `ws.direction` on each
per-direction workspace before calling `write()`; 04b's read-path resolver
(now bidirectional — see the "Discriminator value resolution" update in
[04b](04b-multi-workspace-nxstress.md)) sets it back onto each reconstructed
workspace on `read()`, so the viewer can select `ws.direction == "11"` etc.
with no extra plumbing.

### Direction blocks are contiguous on disk, not interleaved

04b's ordering rule makes discriminator values the most slowly varying
`sort_key` coordinate — i.e., each configured discriminator's rows form one
contiguous block, rather than being interleaved with other discriminator
values by scan point or by phase/hkl (see
`open-questions/04b-multi-workspace-nxstress.md` Q6). Since `direction` is
this spec's sole discriminator, that means a saved `.nxs` file's peak-index
contains exactly three contiguous blocks — `"11"`'s rows, then `"22"`'s,
then `"33"`'s, in string-sorted order — never interleaved. This isn't new
mechanism this spec builds; it falls straight out of 04b's general rule,
applied to the one discriminator field this spec configures. It's worth
stating explicitly here because a reader of this spec would otherwise have
no way to know how the three directions' data actually sit relative to one
another on disk, and it's a cheap, concrete thing to assert in this spec's
own round-trip test (see Tests below), rather than only in 04b's more
generic contiguity tests.

### Compliance with 04b's "≥1 PeakCollection per workspace" invariant

04b's Q7 documents (and enforces at write time) that every input workspace
must contribute at least one `PeakCollection` whenever N>1 — without one,
that workspace's discriminator value can't be recovered on read, so the
scan-point family (sample logs, diffraction data) can't be split back out
for it. This spec already satisfies that invariant by construction: all
three direction workspaces always carry real peak fits (that's the whole
point of a StrainStress calculation) — there's no code path in this spec
that would call `save_as_nxstress` with a direction contributing zero
peaks. Noted here only for completeness; no additional check is needed in
this spec beyond 04b's own write-time validation.

### Config precondition

04b's discriminator mechanism only works if the deployment's
`nxstress.discriminator_fields` actually includes `"direction"` — if some
other field is configured instead (or none), all three per-direction
workspaces would resolve to the same discriminator tuple, most likely
surfacing as an opaque duplicate-index error several layers removed from
the real cause. **Decided:** `save_as_nxstress` checks
`"direction" in load_config().nxstress.discriminator_fields` before calling
`write()` and raises a clear, StrainStress-specific error if not; and the
shipped default in `pyrs/config/pyrs.default.yml` (delivered by spec 01) is
updated to `nxstress.discriminator_fields: ["direction"]` (was `[]`), so
this works out of the box rather than requiring every deployment to opt in
manually.

---

## Scope

**In scope:**
- Add a settable `direction` `@property` to `HidraWorkspace`
  (`pyrs/core/workspaces.py`) — see "`direction` needs a home..." above.
- Declare `direction: str` as one of 04b's discriminator fields on
  `_peaks.py::PeakIndex` (values `"11"`, `"22"`, `"33"`), using the
  mechanism 04b already implements — no new index-extension machinery is
  built here.
- Confirm `direction` composes correctly with 04b's `sort_key`,
  `validateNoDuplicatePeaks`, `_init`, `init_group`, and
  `peakCollectionsFromNexus`; add StrainStress-specific tests, not new
  mechanism.
- `save_as_nxstress`'s config precondition check (see "Config precondition"
  above), and the corresponding default-config update in
  `pyrs/config/pyrs.default.yml`.
- Wire NXstress read path into `strainstressviewer/model.py` —
  `load_hidra_project_file` / `load_hidra_project_files` — so a single
  `.nxs` file replaces the N-files-per-direction pattern
- Add **Save as NXstress…** action on the StrainStressViewer that writes
  all three directions into one `.nxs` file
- Round-trip integration test

**Out of scope:**
- Resolving `NotImplementedError` methods in `fields.py` beyond those
  actually hit on the read path (fix only what the test exercises)
- Append support (spec 04c) — this spec always writes a fresh file
- Any change to the existing JSON state-save or CSV export paths

---

## PyRS Changes

- `pyrs/core/workspaces.py` — add a settable `direction` `@property` to
  `HidraWorkspace` (get/set, backed by a plain instance attribute; no
  persistence requirement beyond what NXstress round-trips via the
  bidirectional resolver in 04b). Matches the existing `@property`
  convention already used for `name`, `hidra_project_file`,
  `reduction_masks`, `calibration_file`, `sample_log_names`
  (`pyrs/core/workspaces.py:55-1155`).
- `pyrs/dataobjects/fields.py` — resolve any `NotImplementedError` in
  `StrainField` / `StressField` that is exercised by the read-back path
  (i.e., when reconstructing a `StressField` from the direction-indexed
  peak collections returned by `NXstress.read()`). Fix only the methods
  the round-trip test actually calls.

_The direction-aware `HidraWorkspace` container question (previously listed
here) is retired: 04b's `list[HidraWorkspace]` signature means the viewer
passes one workspace per direction directly, with no merged container
needed._

---

## NXstress Changes

_None beyond 04b/04c's own scope._ The general index-extension mechanism
(schema check, `PeakIndex` shape, `sort_key`/`validateNoDuplicatePeaks`/
`_init`/`init_group`/`peakCollectionsFromNexus` changes, and the
bidirectional discriminator resolver) is built once in
[04b](04b-multi-workspace-nxstress.md), not here. This spec's work against
NXstress is limited to:
- Confirm `direction: str` (values `"11"`, `"22"`, `"33"`) is a valid
  discriminator value for 04b's mechanism, and that the new `direction`
  property (this spec's PyRS Changes) round-trips correctly through 04b's
  get/set resolver.
- Confirm the on-disk consequence of 04b's most-slowly-varying ordering
  rule for this specific discriminator: the three directions' peak-index
  rows land as three contiguous blocks, string-sorted by `direction`
  (see "Direction blocks are contiguous on disk" above) — not a new
  behavior to implement, just a property of 04b's mechanism to verify
  holds for this concrete discriminator value set.
- Add StrainStress-specific tests exercising `direction` through 04b's
  general read/write/split path.

### `pyrs/config/pyrs.default.yml`

- Update the default `nxstress.discriminator_fields` from `[]` to
  `["direction"]`, so multi-direction save/load works without per-deployment
  config changes.

### `pyrs/interface/strainstressviewer/model.py`

- `save_as_nxstress(filename)`: check
  `"direction" in load_config().nxstress.discriminator_fields`; raise a
  clear error if not present. Set `ws.direction = "11"` / `"22"` / `"33"`
  on each of the (up to three) direction workspaces. Call
  `NXstress(filename, "w").write([ws_11, ws_22, ws_33], peakss)` per 04b's
  signature.
- `load_hidra_project_file(filename, direction)`: if `*.nxs`, call
  `NXstress(filename, "r").read()` (returning `list[HidraWorkspace]` per
  04b, each with `.direction` already set by 04b's read-side resolver) and
  select `next(ws for ws in wss if ws.direction == direction)`.
- `load_hidra_project_files(filenames, direction)`: if a single `.nxs`
  file is supplied (rather than N `.h5` files), read all directions in
  one call and populate the three direction slots.

### `pyrs/interface/strainstressviewer/strain_stress_view.py`

- Add **File → Save as NXstress…** action with filter `"NXstress (*.nxs)"`.
- Extend the load file dialog to include `"NXstress (*.nxs)"`.
- **Config-driven enablement (both actions, always visible, never hidden):**
  the new **Save as NXstress…** action gets
  `.setEnabled(load_config().nxstress.enable)`; this viewer has no existing
  `.h5`-format "Save" action to gate (its current save paths are CSV/JSON,
  unaffected by this spec), so there is no `legacy_io.enable` check here.
- **Extension is imposed, not user-chosen:** `save_as_nxstress` enforces
  `nxstress.extension` on the `QFileDialog`'s returned filename, regardless
  of what a user types.

---

## Tests

`tests/unit/pyrs/core/test_workspaces.py` (extend):
- `direction` property: default value (unset), get/set round-trip, and that
  setting it on one `HidraWorkspace` instance doesn't affect another.

`tests/integration/test_nxstress_viewer_roundtrip.py` (extend):

- Construct minimal workspaces and peak-collection lists for all three
  directions using spec-01 fixtures; set `.direction` on each before saving.
- Call `model.save_as_nxstress(path)`.
- Load back with `model.load_hidra_project_files([path], direction)` for
  each direction; assert each returned workspace's `.direction` matches
  what was requested.
- Assert that the reconstructed `StressField` matches the CSV-summary
  output produced from the original inputs.
- Config-precondition error: call `save_as_nxstress` with
  `nxstress.discriminator_fields` configured to something other than
  `["direction"]` (e.g. `[]`); assert the clear StrainStress-specific error
  is raised, not an opaque duplicate-index error from 04b.
- Enablement wiring: with `nxstress.enable: false`, assert
  **Save as NXstress…** is disabled but still visible.
- Direction-block contiguity: after `save_as_nxstress` writes all three
  directions, read the raw on-disk `PEAKS`/`NXreflections` arrays directly
  (via `.nxdata`, not through `NXstress.read()`) and assert each
  direction's rows occupy one contiguous run — `"11"`'s block, then
  `"22"`'s, then `"33"`'s — with no direction's rows split across, or
  interleaved with, another's.

---

## Delivered Feature

> **For end users:**
> Multi-direction stress measurements can now be saved and loaded as a single
> NXstress (`.nxs`) file from the Strain/Stress viewer:
>
> - *Strain/Stress → File → Save as NXstress…*
>
> Instead of managing three separate `.h5` files (one per direction), the
> entire stress dataset — all three measurement directions — is stored in one
> NXstress-compliant file. This file can be shared with other NXstress-aware
> analysis tools.
>
> Existing `.h5` project files and the JSON state-save continue to work
> as before.

---

## Verification

- GUI smoke test: load three `.h5` files (one per direction) in
  StrainStressViewer, compute stress, **File → Save as NXstress…**, confirm
  a single `.nxs` file is written; then load the `.nxs` back and confirm
  the stress field is reproduced.
- `pytest tests/unit/pyrs/core/test_workspaces.py` — all pass including the
  new `direction` property tests.
- `pytest tests/integration/test_nxstress_viewer_roundtrip.py` — all pass.
- `pytest tests/unit/pyrs/utilities/NXstress/` — all pass including updated
  `test_peaks.py` / `test_peaks_read.py` for the direction axis, and 04b's
  resolver-symmetry tests exercising a real get/set property (this spec's
  `direction`) rather than only the log-fallback case.
- Confirm the shipped `pyrs/config/pyrs.default.yml` includes
  `nxstress.discriminator_fields: ["direction"]`.
