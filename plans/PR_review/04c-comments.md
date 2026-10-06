# PR review — subspec 04c (NXstress append mode)

Review of `eb5457b1..cda22352`, per
[`plans/PR-review-process/review-process.md`](../PR-review-process/review-process.md).
This document also carries the work belonging to **no** subspec — commit `61389b28`,
the integration-test fixups — per §4 of that process.

Each entry: the comment, the agreed resolution, and the change actually made.
My summaries of the diff are not recorded (§6e); defects I flagged are, whether or
not they were acted on.

---

## Batch 1 — `pyrs/utilities/NXstress/_definitions.py`

### D1 — `tail_append`'s error named the dataset `'unknown'`

**Flagged by me.** The whole value of that message is naming which dataset cannot
grow, and `NXfield.nxpath` returns the literal string `'unknown'` for a field not
attached to a tree, so the message read *"dataset 'unknown' was written at a fixed
size"*. `.nxname` is `'unknown'` too — there is genuinely no name to report.
Unreachable from the append path, which is always file-backed; reachable from a unit
test or a future in-memory caller.

**Resolution:** fix.

**Change:** new `_definitions._field_label(field)`, used by all three `tail_append`
messages. Returns `dataset '<nxpath>'` when there is a path, and
``an unattached (3,) `NXfield` `` when there is not, so the message never presents
`unknown` as a name.

### D2 — `tail_append(field, <scalar>)` raised `IndexError: tuple index out of range`

**Flagged by me.** `np.asarray(5).shape` is `()`, which passes the trailing-axis
check vacuously (a 0-d array has no trailing axes to disagree about); `values.shape[0]`
then raises an `IndexError` naming neither the field nor the problem. No current
caller passes a scalar — an unguarded contract rather than a live bug.

**Resolution:** fix.

**Change:** a `values.ndim == 0` guard before the trailing-axis check, raising
`RuntimeError` that names the field and says to pass a 1-element array. The comment
at the guard records why it must precede the trailing-axis check rather than follow it.

### D3 — `growable` advertises flexibility the writer refuses

**Flagged by me.** `growable(rank)` makes *every* axis unlimited, so `diffractogram`
goes to disk as `maxshape=(None, None)` — telling any NeXus reader the two-theta axis
can grow, when `tail_append` and `_Fit.validateAppend` both refuse exactly that.

**Reviewer:** *"I think we need to give a meaningful error message when a 'trailing
axis' append is rejected? (Assuming we don't have one already.) Also, it wasn't obvious
if we could just have the non-appendable items (e.g. 'diffractogram') NOT use the
'maxshape=(None, None)' form — what would be the implication of this?"*

**On the error message:** one already existed, in `tail_append`, and
`_Fit.validateAppend` has a domain-specific one that fires first in the append path
(*"the incoming reduced diffraction for mask `_DEFAULT_` has 25 two-theta bin(s), the
target entry 20"*). `tail_append`'s was extended to say *why*, not only *what*: "Only
the first axis grows on an append; the trailing axes are fixed when the entry is
written."

**On pinning the trailing axes — probed, not reasoned about.** Pinning works and HDF5
enforces it: `maxshape=(None, 20)` writes, an axis-0 grow succeeds, and an axis-1 grow
is refused by the library (`NeXusError: Shape incompatible with current NXfield`).
**But `(None, None)` turns out to be load-bearing for `CHUNK_SHAPE` as written** —
h5py accepts a chunk wider than the data only when that axis is unlimited:

```console
  maxshape=(None, None)  chunks=(1, 100)  data (3, 20):  OK
  maxshape=(None, 20)    chunks=(1, 100)  data (3, 20):  ValueError:
        Chunk shape must not be greater than data shape in any dimension
  maxshape=(None, 20)    chunks=(1, 20)   data (3, 20):  OK
```

So pinning drags in a shape-aware `CHUNK_SHAPE`, and two datasets must stay unlimited
regardless: `DIFFRACTOGRAM/fit` and `fit_errors` are `(0, 0)` placeholders that **spec
09** resizes on *both* axes when it fills them in.

**Resolution: keep `(None, None)`, document why.** No second change to on-disk layout
in one PR, no scope growth inside a review.

**Change:** the `growable` docstring now records the asymmetry, the h5py constraint
that causes it, the three measured cases above, and the spec-09 placeholder reason —
stating plainly that the trailing axes are *"a chunking artifact, not a contract"* and
naming the three places that enforce the real rule.

### Noted, not a defect — `__` in a log name expands ~2.5×

**Reviewer:** *"a minor question about what actually happens if an incoming identifier
includes `__` — how would this actually be encoded?"*

Each `__` becomes `__5F_`: the first underscore is escaped because its successor is an
underscore, the second passes through. Round-trips exactly —

| input | encoded | decoded |
|---|---|---|
| `a__b` | `a__5F_b` | `a__b` |
| `__foo` | `__5F_foo` | `__foo` |
| `__` | `__5F_` | `__` |
| `HB2B__CS__X` | `HB2B__5F_CS__5F_X` | `HB2B__CS__X` |
| `a____b` | `a__5F__5F__5F_b` | `a____b` |

**The durable point is the expansion against the 63-character cap.** *n* consecutive
underscores become ~2.5× their length, so a name that is comfortably short can still
fail to encode. Not live — zero of the 185 real log names in `tests/data` need an
escaped underscore at all — and it fails *loudly*, with `allowed_identifier` raising a
`ValueError` that quotes both the original and the encoded form. Recorded because the
condition is not obvious from reading the encoder. **No change.**
