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
