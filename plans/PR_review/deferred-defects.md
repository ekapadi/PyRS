# Deferred defects — PyRS PR review

Defects found during the PR review of NXstress subspecs 04, 04b and 04c that are
**real and reproduced**, but deliberately not fixed in that PR — because the fix
belongs to code the PR does not own, or to a change that deserves its own review.

This file is not a backlog of ideas and not a place for open questions. Every
entry is a defect that was measured, with the measurement attached, so that
picking one up later does not mean re-deriving it.

**Each entry records where it was found** (`subspec <list>: part <batch>`,
matching the review's commit headers) and why it was deferred. Entries are
append-only; when one is fixed, say so in place rather than deleting it.

---

## DD-1 — `validate_config` cannot be enforced after a runtime override

**Found during:** subspec 04b, 04c: part 7
**Owner:** `neutrons_standard.Config`, not PyRS
**Status:** open, not patched here

### What happens

`pyrs/utilities/config.py` calls `validate_config()` once, at import, so a
malformed configuration fails at the first import rather than at the first I/O
call site. That is the right posture and it works — for the configuration that
exists at import.

It cannot cover an override applied afterwards. `Config.loadEnv(<path>)` installs
a new configuration at any later point, and nothing re-validates:

```console
>>> Config.loadEnv("bad.yml")            # nxstress: {use_production_names: "yes"}
>>> Config["nxstress.use_production_names"]
'yes'                                     # a truthy string, never checked
```

`validate_config()` is a public function and can be called again by hand, but
nothing in `Config` invites it: there is no validation hook, no post-refresh
callback, and `_Config.validate` is a documented no-op. So the guarantee the
module advertises — that a malformed config is rejected before it can be acted
on — holds only for the import-time path.

### Why it is deferred

The gap is in the external package. Closing it properly means
`neutrons_standard.Config` growing a validation hook that `refresh`/`loadEnv`
invoke, which PyRS cannot add from the outside, and which is the kind of change
that wants its own review with the package's owners.

The PyRS-side workarounds are all worse than the gap:

- calling `validate_config()` from every consumer — the scattering this module
  exists to prevent;
- wrapping `Config` in a PyRS proxy that re-validates on access — a second
  `Config`, and the module docstring is explicit that there must be exactly one
  way to reach it;
- re-validating inside `_discriminator.field_names()` and friends — validates
  some keys, at some call sites, which reads as coverage and is not.

### Why it is tolerable for now

The runtime-override path is **test-only** by decision (subspec 04b, part 2: the
`env` OS variable is the documented production mechanism, and it is read at
import). Production never calls `loadEnv`. What is missing is that nothing says
so, and nothing stops a future caller.

### If picked up

Ask `neutrons_standard` for a validation hook on `refresh`. Failing that, the
narrow PyRS fix is for the `config_override` test fixture to call
`validate_config()` after merging, so at least every overridden configuration a
test installs is one production would have accepted — which is where a malformed
override would otherwise first mislead someone.
