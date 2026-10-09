# PR review — subspec 04 (NXstress internal cleanup)

Review of `eb5457b1..cda22352`, per
[`plans/PR-review-process/review-process.md`](../PR-review-process/review-process.md).

Each entry: the comment, the agreed resolution, and the change actually made.
My summaries of the diff are not recorded (§6e); defects I flagged are, whether or
not they were acted on.

---

## Batch 1 — `pyrs/utilities/NXstress/_definitions.py`

`_definitions.py` carries work from both `04` (the identifier policy and the mask-key
correspondence) and `04c` (the growth helpers). Per the process document §4, the batch
is split across documents by which subspec's change is under discussion: the
`allowed_identifier` exchange is here, and `D1`–`D3` on `growable`/`tail_append` are in
[`04c-comments.md`](04c-comments.md).

### Reviewer question — how is a literal `__` encoded?

Answered in full in [`04c-comments.md`](04c-comments.md) (kept together with the rest
of that exchange rather than duplicated). Summary: `__` encodes to `__5F_` and
round-trips exactly; the durable point is that *n* consecutive underscores expand
~2.5×, which interacts with the 63-character `MAX_IDENTIFIER_LENGTH` cap. No real log
name triggers it, and the failure is loud. **No change.**

### No defects flagged against `04`'s part of this file

The identifier encoding was checked rather than read: all three docstring examples
produce exactly what they claim, and the encoding is **injective and round-trips over
7380 adversarial inputs** drawn from `_ . : a A 0 u $` and space at lengths 1–4, with
every output matching `VALID_ITEM_NAME` and fitting the 63-character cap.

Worth recording one non-obvious property the correctness rests on, because it reads
like an optimisation and is not: a literal `_` is emitted only when the next character
is neither `_` nor illegal, so **two literal underscores are never adjacent in the
output** and a literal `_` never precedes an escape. Without that one-character
lookahead, `_` followed by `:` would encode to `___3A` and the decoder would attempt
`int("_3", 16)`.

---

## Batch 5 — `pyrs/utilities/NXstress/_instrument.py` (brought forward during batch 4)

Opened early at the reviewer's direction, because batch 4's D8 discussion ran into
the mask handling and the context was loaded. Four defects, **one root cause**.

### The root cause: two namespaces conflated into one

| | what it is | always has | lives in |
|---|---|---|---|
| **detector mask** | `_DEFAULT_` + named masks from `_mask_dict` | an array | `masks/detector/` |
| **diffractogram key** | a `_diff_data_set` key — *references* a detector mask, optionally ∩ an eta ROI | no array of its own | the `FIT` group's names |

`reduction_manager` builds the key as `"{mask_id}_eta_{eta_cent}"`, dropping either
part that is absent, so the four shapes are `None`, `"mask_a"`, `"eta_-5.0"` and
`"mask_a_eta_-5.0"`. `_Masks.mask_keys` unioned those keys into the *mask*
namespace, and everything below follows from that.

**Reviewer, correcting me twice on the way:** *"'eta ROI intersected with mask_vec'
actually does imply that the default-mask is being used, when no other detector
mask has been specified"*, and *"the default detector mask is always being used.
There is no reduction that 'has no mask'."* Both corrections mattered: the first
removed my objection that a link to the default would be *false*, the second showed
that `None` means "the default mask alone", not "no mask" — which is what makes the
diffractogram keyspace and the mask namespace genuinely different sets rather than
the same set with a quirk.

### D11 — `masks/names` listed masks that had no array

Measured before the fix, on a texture-shaped workspace:

```console
  names          : ['_DEFAULT_', 'eta_0.0', 'eta_-5.0', 'eta_5.0']
  detector/      : ['_DEFAULT_']
  solid_angle/   : []
      eta_0.0    -> NOWHERE  <-- name with no array
```

The `NXlink` meant to patch this was never serialised. **And making it work would
have been worse**: `masksFromNexus` would then return the default array under each
composite key, and `set_masks_from_dict` would add entries to `_mask_dict` that the
original workspace never had — the D8 defect in a different property.

**Change:** `_Masks.mask_keys` returns the mask namespace only. The `NXlink` branch
and its warning are gone. `masks/names` now carries `['_DEFAULT_']` for that
workspace, and every name resolves.

### D13 — a texture workspace could not be written at all

Two independent rejections, both from the same conflation:

```console
  eta-only reductions      -> ValueError: Reduced data required for mask '_DEFAULT_'
  eta-keyed PeakCollection -> ValueError: Mask 'eta_0.0' required by `PeakCollection`
```

The first because `nxstress_mask_names` injected `DEFAULT_TAG` into the
*diffractogram* keyspace, demanding a bare `DIFFRACTOGRAM` for data never reduced.
The second because `validateWorkspaceAndPeaksData` checked `PeakCollection.mask` —
a **diffractogram key** — against the *mask* namespace, where `eta_0.0` is correctly
absent.

**Change:** a new `nxstress_diffractogram_keys` that does **not** inject the
default, used by `_Fit.init_group` and `_Fit.validateAppend`; and the peak check
now validates against `_diff_data_set`, which its *second* check was already doing
correctly — so fixing it meant deleting the first, not adding a third.

### D10 — the solid-angle heuristic guessed, and guessed wrong

```console
  detector mask, float, 16 px -> solid_angle=True    MISCLASSIFIED
  solid-angle, 3 floats (odd) -> solid_angle=False   MISCLASSIFIED
```

Nothing in PyRS loads a solid-angle mask into a `HidraWorkspace` —
`read_mask_solid_angle` exists on `HidraProjectFile` but is called only in one test,
and `_load_masks` reads detector masks only. So the branch has never run.

**Change, per the reviewer:** *raise `NotImplementedError`* rather than classify,
and fold in `_generate_default_mask`'s dead `detector_mask=False` branch (which
returned a plausible-looking `[-180.0, 180.0]`). The `solid_angle` group stays as the
placeholder, and `masksFromNexus` still reads it, so a future writer needs no reader
change.

### D12 — a workspace with no mask wrote a file PyRS could not read

```console
  masks SET (default exists):        on disk (16,)  -> read back OK
  masks ABSENT (default generated):  on disk (4, 4) -> READ FAILED
                                     RuntimeError: Mask array with shape (4, 4) is not acceptable
```

`_generate_default_mask` returned `np.ones(detector_size)` — 2-D — while
`set_detector_mask` refuses any 2-D array whose second axis is not 1. **All 42
round-trip tests use `with_masks=True`**, so the generated-default path had never
been round-tripped.

**Change:** return 1-D `np.ones(nrows * ncols)`, plus the missing
`with_masks=False` round-trip test.

### Also repaired

**A retained probe had stopped running.** `a5_transformations_chain` calls
`_Instrument.init_group(ws)`, which 04b generalised to `list[HidraWorkspace]`; it
has been broken since 04b landed, undetected because nothing runs the probes.
`probes/README.md` lists it as *retained* for the numeric composition — unlike
`a5_nxstress_roundtrip`, whose failure is documented and deliberate. Repointed; it
confirms Decisions row 26 still holds (8 of 8 transformations reachable).

**A test was asserting an impossible workspace.** `test_Fit_multiple_masks` built
`_diff_data_set` keys `mask1`/`mask2` without ever registering those masks, which the
new reference check correctly rejects. A real reduction using `mask1` had `mask1`
loaded; the test now does too.

### `OPEN DEFECT` — the mask-append path is unreachable and would break

`_Masks.init_group(ws, masks=...)` reads `names = masks["names"].nxvalue`, which
returns a bare `str` rather than a 1-element list when exactly one mask exists —
so `names.append(...)` would raise `AttributeError`. Unreachable today
(`_Instrument.init_group` never passes `masks=`), and left standing rather than
fixed blind, since the append semantics for masks are not otherwise specified.
