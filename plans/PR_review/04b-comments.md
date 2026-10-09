# PR review — subspec 04b (multi-workspace NXstress I/O)

Review of `eb5457b1..cda22352`, per
[`plans/PR-review-process/review-process.md`](../PR-review-process/review-process.md).

Each entry: the comment, the agreed resolution, and the change actually made.
My summaries of the diff are not recorded (§6e); defects I flagged are, whether or
not they were acted on.

---

## Batch 2 — `pyrs/utilities/NXstress/_discriminator.py`

### D4 — a read-only property breaks the discriminator round trip, silently

**Flagged by me.** `resolve` uses a `HidraWorkspace` property whenever one exists;
`apply` used it only when `fset is not None`, otherwise writing a sample log. All
six `HidraWorkspace` properties are read-only, so a field naming one was read from
the property and written back to a log: the value reached the file correctly and
came back as the constructor's default, with nothing raising.

**Reviewer:** *"Since `HidraWorkspace` may need to have readonly properties for
'user facing' reasons, I think the correct solution is probably to add an
internal-use (i.e. non private) accessor method to `HidraWorkspace` for use by
`NXstress`. We cannot simply omit the property, or raise if it is readonly, and the
round-trip verification is definitely a requirement."* Then, after reviewing the
options: *"What I want to work out, is a well-designed method to allow properties
which are used as discriminators to be settable, but without making them read/write
properties."*

**Why it could not wait.** `strainstressviewer/model.py` constructs
`HidraWorkspace(direction)` — the viewer already carries direction in a read-only
property, and spec 05 is the viewer. A `set_<name>()` method was rejected on the
reviewer's criterion: it makes the value writable in all but spelling.

**Resolution: a `restorable_property` descriptor**, declared on the property
itself, in its own module.

**Changes:**
- **New** [`pyrs/utilities/restorable_property.py`](../../pyrs/utilities/restorable_property.py)
  — `restorable_property` (a `property` subclass naming a backing attribute),
  the `restorable()` decorator, and `is_restorable()` / `restore()`. Assignment
  still raises `AttributeError`; `isinstance(…, property)` still holds, so
  `resolve`'s read path is untouched. A `setter()` call raises rather than
  silently producing a writable property.
- `pyrs/core/workspaces.py` — new `_direction` field; `direction` as a
  `restorable_property`; `hidra_project_file` marked restorable (it was settable
  only as a side effect of `load_hidra_project`, so a workspace rebuilt from any
  other source could not record its origin).
- `pyrs/interface/strainstressviewer/model.py` — one line in
  `load_hidra_project_file`, the single funnel all three directions and both entry
  points pass through.
- `_discriminator.apply` — a branch for `is_restorable`, between the settable
  property and the sample-log fallback.
- `_discriminator.field_names` — rejects, **at configuration time**, a field
  naming a read-only property that is neither settable nor restorable. This is
  what makes the asymmetry unreachable rather than merely fixed.

**Two decisions inside the resolution.** `direction` is backed by `_direction`,
**not** aliased to `_name` — aliasing would make `ws.direction` answer
`"Combined Project Files"` for `CombineRunsModel`'s workspace. And its getter
falls back to the `direction` sample log when `_direction` is unset, a deliberate
compatibility shim that kept every existing test working unchanged; spec 05
retires it (05's Follow-up 2).

### D6 — `_discriminator` was the only module bypassing the documented `Config` access

**Flagged by me, and I got the diagnosis backwards first.** `_discriminator` did
`from pyrs.utilities import config as _config` and reached `_config.Config[...]`,
with a comment explaining that a bound name goes stale when the `default_config`
fixture reloads. I verified the comment's claim was *true* and concluded the
deviation was therefore correct.

**Reviewer:** *"this override capability is a test-only capability, so what
`_discriminator.py` is doing should definitely not be viewed as correct access!"*
— which is the deciding point: production shape must not be bent around a test
capability. `config.py`'s docstring says *"Import `Config` from this module"*, and
every other consumer does.

**What the investigation then found**, in order:
- There is **no config-based property decorator** in the installed
  `neutrons_standard` — the capability the fix might have leaned on does not exist.
  The absence is the finding.
- `Config.__getitem__` → `_find` reads `_config` **live on every access**, with no
  cache, so a test can override in place with no rescan. Three caveats: a helper
  must deep-merge (a shallow assignment drops siblings — verified by `KeyError`);
  `_fix_directory_properties` only matters for `instrument.home`/`samples.home`;
  and nothing re-validates, since `_Config.validate()` is `pass`.
- **`default_config` leaked.** Its teardown reloaded to yet another new singleton,
  so any test using it orphaned every consumer module for the **rest of the
  session**. That is why the first version of the override fixture worked in
  isolation and failed in a full run.

**Changes:**
- `_discriminator.py` → `from pyrs.utilities.config import Config`.
- `tests/unit/pyrs/utilities/conftest.py` — new `config_override` fixture that
  deep-merges into the live singleton's `_config` and restores a deep copy, never
  swapping the instance; **and** `default_config` now restores the pre-test
  singleton instead of reloading to a third one.
- The three NXstress test files switched from `default_config` + `loadEnv` to
  `config_override`.

**Side effect worth naming:** `_instrument.py` was unoverridable in tests —
`_instrument_names()` returned the shipped default whatever a test configured, so
any test asserting a configured instrument name was passing vacuously. It works now.

### D5 (nit) — a field name with surrounding whitespace is accepted

**Flagged by me.** `field_names` checks `name.strip()` is non-blank, then uses
`name` unstripped, so `' direction '` becomes the column `__20direction__20`.

**Not resolved.** `OPEN DEFECT` — see below.

---

## `OPEN DEFECT`

**D5 — whitespace in a configured discriminator field name.** A config typo
produces a valid but surprising column that will not match on read once corrected.
Would be resolved by either rejecting a name that differs from its own `.strip()`,
or normalising it. Not raised with the reviewer; recorded here per §6c and to be
raised again at the end of 04b's walk.

---

## `RE-REVIEW RECOMMENDED`

**Files:** `pyrs/utilities/restorable_property.py` (new),
`pyrs/core/workspaces.py`, `pyrs/interface/strainstressviewer/model.py`,
`tests/unit/pyrs/utilities/conftest.py`, `pyrs/utilities/NXstress/_discriminator.py`.

**Why:** §5's *"a fix agreed during review outgrew its estimate"*. Batch 2 began as
a read of one 322-line file and produced a new module, a change to a core data
class, a change to a viewer, and a rework of shared config test infrastructure —
four of those outside the PR's original 66-file diff. Per §5 this is also the
weakest configuration the process has: I implemented it and then verified it with
tests I wrote in the same pass.

**Scope for a second pass:** the `restorable_property` semantics (does read-only
really hold everywhere it is used?), and the `config_override` / `default_config`
interaction, which is subtle enough that it failed in a full run after passing in
isolation.

---

## Batch 3 — `pyrs/utilities/NXstress/_peaks.py`

### D7 — a string discriminator column was created as `float64` when the entry has no peak collections

**Flagged by me.** `discriminator_dtypes` infers each column's dtype from the
values present. With no collections there are none, and `np.asarray([]).dtype` is
`float64`, whose kind is not in `("U","S","O")`, so the string branch was skipped.
Reachable in production: `CombineRunsModel` exports via `write([ws], [[]])`
(Decisions row 28), and spec 05 configures `discriminator_fields: ["direction"]`.

Measured before the fix — the file round-tripped through PyRS, so the harm was a
wrong on-disk type for any other reader:

```console
  peaks/direction   dtype=float64  shape=(0,)     <-- should hold strings
  peaks/phase_name  dtype=object                  (for comparison)
  read back: 1 workspace(s), [0] collection(s)
```

**Reviewer:** *"Emit no discriminator columns when there are no collections."*

**Change:** `discriminator_dtypes` returns `{}` for an empty `indexed`, so `_init`
emits no column. Verified: the entry now carries only the 15 reserved columns and
still reads back as one workspace with zero collections. The docstring records why
the empty case is not a detail.

### Reviewer question — is such a file then non-appendable?

*"I think then that such a NXstress file is non-appendable, except via the
multiple NXentry route."* **Correct, and already enforced.** Measured:

```console
  append to a column-less entry -> RuntimeError:
    "the target entry carries no discriminator columns, so an appended
     workspace could not be told apart from the one(s) already there."
  new NXentry route still available? yes
```

**No change** — 04c's Case-A precondition 2 already covers it.

### Raise earlier than "interleaved blocks detected"

**Reviewer:** *"When `discriminator_names` is `()` (AND should this be `None`
instead of `()`?) — there is no possible merge allowed? Is this correct? My point
is we can raise a RuntimeError earlier than 'interleaved blocks detected ...'."*

**The case for raising is stronger than it looked.** Omitting the names does not
produce a confusing error — it produces a **silent wrong answer**:

```console
  peakCollectionRanges(peaks) with the argument FORGOTTEN:
    no error; returned 1 range -- WRONG, should be 2 workspaces
```

Both workspaces shared `('Fe',1,1,0,'_DEFAULT_')`, so their adjacent blocks merged
into one range, and the monotonicity check passed because the concatenated scan
points were still increasing. "Interleaved blocks detected" is only the failure
mode when the data happens to be shaped differently — the failure varies with the
data.

**On `None` vs `()`: kept `()`.** Once the group is authoritative via the check
below, `None` and `()` behave identically, so the extra state buys nothing. The
alternative use for `None` — "derive the names yourself" — would make
`peakCollectionRanges` read configuration, turning a pure function over a group
into one with a hidden config dependency, and would mask the caller's mistake
rather than surface it.

**Change:** new `_Peaks._validateDiscriminatorNames`, called first in
`peakCollectionRanges`, comparing the caller's names against the columns actually
present and naming both sets. Distinct from `_discriminator.names_for_read`, which
compares *configuration* against the file.

### `merge_workspaces` does not make NXstress merge anything

**Reviewer:** *"the NXstress implementation does not merge workspaces -- that's
something that is external (in PyRS itself)."* **Correct**, and my phrasing had
attributed a merge to NXstress. `merge_workspaces` is a config key only — it
appears in no method signature — and its whole effect is permissive: it lifts
`_validateMultiWorkspace`'s refusal so rows may be concatenated with no boundary
recorded. Merging that produces a genuinely merged `HidraWorkspace` happens in
PyRS first (`HidraWorkspace.append_hidra_project` via
`CombineRunsModel.combine_project_files`, which then passes a length-1 list).

**Change:** phrasing corrected in all three places I had introduced or inherited it
— `_discriminator.names_for_read`, `_peaks._validateDiscriminatorNames`, and the
new test's comments. `()` now reads as "the entry records no workspace boundary"
rather than "the entry is merged".

Four other sites use "merged write/entry" as shorthand without attributing an
operation (`_peaks.py:79`, `:458`, `_discriminator.py:175`, `:300`); left as
shorthand now that `names_for_read` carries the authoritative note.

### Reviewer question — does `merge_workspaces: false` with N>1 and no discriminators raise?

**Yes.** Measured across all three configurations:

```console
  fields=[]            merge=False -> ValueError: given 2 workspaces, but
                                      'nxstress.discriminator_fields' names no field
  fields=[]            merge=True  -> ValueError: Duplicate PeakCollection detected
                                      at ('Fe', 1, 1, 0, '_DEFAULT_')
  fields=['direction'] merge=False -> ValueError: sample log 'direction' not found
```

The middle row is worth recording: **even with `merge_workspaces: true`, two
workspaces sharing a compound key are still refused**, by `validateNoDuplicatePeaks`
— with no discriminators their sort keys are identical. So the escape hatch only
works when the inputs' compound keys already differ, and the ordinary
multi-direction case (two workspaces measuring the same peak) cannot use it at all.
**No change**; recorded because it narrows what the setting is for.

---

## Batch 4 — `pyrs/utilities/NXstress/_fit.py`

### D8 — a round trip added an all-NaN mask to a workspace that never reduced it

**Flagged by me.** One `DIFFRACTOGRAM` group spans the whole entry, so when one
input reduced a mask and another did not, `_concatenated_diffraction` NaN-fills
the second's rows to keep the scan-point axis aligned — deliberately, and
documented. But the read side handed every group in the entry to every workspace,
so the second got the mask back:

```console
  before write:      ws0 [None, 'mask_a']    ws1 [None]
  after round trip:  ws0 [None, 'mask_a']    ws1 [None, 'mask_a']   <-- all-NaN
```

`reduction_masks` is *counted* by `texture_fitting_crtl.py:142`
(`if len(...) == 2:`) and `mantid_peakfit_calibration.py:240`, and drives
`setup_out_of_plane_angle` / `enable_polar_plot` in the texture viewer. Latent
today — it needs a multi-workspace file with uneven reduced masks opened in that
viewer — and live once spec 05's multi-direction files exist.

**Reviewer:** *"Drop the all-NaN mask on read. HOWEVER, I'm wondering if we should
just warn and drop the mask with no reductions associated with it on write... a
user setting up a set of masks, and just not bothering to perform a specific
reduction; that might not necessarily be an error."*

**On the write-side proposal: that case is already handled, and is a different
case.** Measured, for a single workspace defining `mask_a` but never reducing it:

```console
  _mask_dict keys       : ['mask_a']            <- defined
  _diff_data_set keys   : ['None']              <- never reduced
  DIFFRACTOGRAM groups  : ['DIFFRACTOGRAM']     <- no DIFFRACTOGRAM_mask_a written
  instrument/masks/names: ['_DEFAULT_', 'mask_a']  <- the mask array IS preserved
  round-tripped reduction_masks: [None]         <- unchanged
```

`_Fit.init_group` builds `mask_keys` from `_diff_data_set`, not `_mask_dict`, so
an unreduced mask already produces no diffractogram, while the mask array itself
still reaches `instrument/masks` and round-trips into `_mask_dict`. Nothing to
change, and no warning is warranted: it is not an anomaly, just a mask that was
defined and not used.

**And a write-side drop would be actively wrong for D8.** There, `mask_a` *does*
have reductions — the first input's. Dropping it at write would discard real data
to tidy up the second input's absence. Whether a workspace has a mask is a
per-workspace fact, so it can only be resolved per workspace, which is the read
side.

**Change:** `NXstress._workspaceFromNexus` omits a mask whose data is entirely NaN
across *this workspace's* rows, logging at INFO. The two-theta matrix is taken
before the check, so dropping the first group does not lose the axis. The comment
records the accepted cost: a reduction that genuinely produced only NaN is
indistinguishable from one that never ran and is dropped too — preferred over
silently changing a workspace's mask set across a round trip.

### Observations, no change

### D9 — `_2theta_matrix`'s row count was never validated against the sub-run count

**Flagged by me as an observation; escalated by the reviewer.** NXstress writes
`scan_point` from the sub-runs and the diffractogram rows from `_2theta_matrix`.
A workspace whose two disagree produced a file whose rows did not correspond to
its scan points, with nothing saying so. Pre-existing, but N workspaces amplify
it: one short input shifts every later input onto the wrong rows.

**Reviewer:** *"The following must be guarded; we should not allow a silent error
like this!"* and *"I would probably guard it in both places; or at least add an
additional test ensuring that the guard does not regress (and pointing to all of
its consumers in a comment at the test)."*

**Change — guarded in both places, because one is not enough.**
`HidraWorkspace.set_reduced_diffraction_data_set` now rejects a `two_theta_matrix`
that is not 2-D, a mask array whose shape disagrees with it, and a row count that
contradicts the sub-runs when those are known. But that setter is only **one of
five** paths that write `_2theta_matrix`; the other four bypass it entirely:

| path | reaches `_2theta_matrix` |
|---|---|
| `_load_reduced_diffraction_data` | reading a `HidraProjectFile` |
| `_append_reduced_diffraction_data` | `append_hidra_project` |
| `set_reduced_diffraction_data` | row-wise; `reduction_manager`, `mantid_peakfit_calibration` |
| direct assignment | anywhere |

So `_Diffractogram._concatenated_diffraction` carries the second guard, at the
write boundary every one of those funnels through, naming **which input** is
short — which matters precisely because the damage is not local.

Four tests in `test_fit.py::TestReducedDataRowCountIsGuarded`, whose class
docstring carries that table so a future reader knows what each guard covers and
why removing either leaves a silent route to a misaligned file. Two exercise the
setter; two force the mismatch *past* it, as the other four paths can.
- **`_concatenated_diffraction` runs twice per append** — once in `validateAppend`,
  once in `init_group`. The cost of pre-flighting rather than discovering
  mid-mutation, and the largest array work on that path.

### Cross-reference — `_fit.py` also changed in batch 5

Batch 5 (`_instrument.py`, written up in
[04-comments.md](04-comments.md#batch-5--pyrsutilitiesnxstress_instrumentpy-brought-forward-during-batch-4),
04's Follow-up 8) separated the detector-mask namespace from the diffractogram
keyspace, and three of its edits land in this file:

- `_Fit.init_group` and `_Fit.validateAppend` now key on
  `nxstress_diffractogram_keys` instead of `nxstress_mask_names`, so the default
  tag is no longer forced into the keyspace.
- `_Fit.init_group` validates that each diffractogram key references a detector
  mask that is actually registered, via the new
  `diffractogram_detector_mask(key, known_masks)`.
- `validateWorkspaceAndPeaksData` lost its mask-namespace check on
  `PeakCollection.mask`; its `_diff_data_set` check was the correct one all along.

Noted here rather than re-argued: the defect is 04's, the file is 04b's.
