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

### Update, 2026-10-16 — partially mitigated in tests; the gap itself is unchanged

Re-verified before acting, rather than recalled. The reproduction still holds
exactly as recorded above:

```console
before override: False
after loadEnv  : 'yes'   (type str, truthy=True)
validate_config(): RuntimeError -- so it WOULD catch it, if called
```

`_Config.validate` is still `pass`, `refresh` still mentions no validation, and
nothing re-validates after `loadEnv`. **The deferral stands.**

**Done — the narrow fix this entry proposed.** `config_override`
(`tests/unit/pyrs/utilities/conftest.py`) now calls `validate_config()` after
each merge, so a test cannot install a configuration production would have
rejected. 104 call sites; a malformed override is refused by default and
accepted only under the opt-out below.

> **Correction, same day.** This paragraph originally claimed the guarantee
> "was checked by measurement rather than assumed". That was true of a
> standalone script and **false of the suite**: an independent test review
> deleted the hook and all 675 tests stayed green, so the guarantee was real
> but unconstrained. The hook had also made `test_config.py:354`'s own
> `validate_config()` unreachable, leaving the 8 tests in
> `TestValidateConfigRejectsMalformedValues` asserting against the *fixture's*
> exception rather than the subject's — passing, and no longer testing what
> their names said. Both closed:
> `test_config.py::TestConfigOverrideRefusesMalformedConfig` now pins the hook
> and the dead line is gone; deleting the hook fails 11 tests. Recorded in full
> in `04b-comments.md`'s `RE-REVIEW RECOMMENDED` section as D10. **Measuring a
> guarantee once is not the same as constraining it**, and only the second
> survives the next refactor.

**Still to do — the actual fix.** Ask `neutrons_standard` for a validation hook
that `refresh`/`loadEnv` invoke, so a runtime override is checked by the package
that performs it. PyRS cannot add this from outside, and the three PyRS-side
workarounds rejected above are still worse than the gap. Recorded here so the
request is not re-derived; **not yet raised with the package's owners.**

### What the fix uncovered: three consumer checks that production cannot reach

Adding validation broke 3 of the 104 uses, and the reason is worth more than the
fix was.

All three install a malformed configuration in order to test that a *consumer*
rejects it — `_discriminator.field_names()` on a blank and on a repeated
discriminator name, `_Instrument._instrument_names()` on a blank instrument
name. Measured against `ConfigSchema` directly:

```console
blank discriminator   : rejected by schema -> consumer check NOT reachable in production
repeated discriminator: rejected by schema -> consumer check NOT reachable in production
blank instrument_name : rejected by schema -> consumer check NOT reachable in production
```

`NonBlankText` and `_distinct` already refuse all three at import, and the `env`
OS-variable override is merged *before* `validate_config()` runs — so no
production path can deliver such a configuration to a consumer. **The three
tests passed only because nothing validated the override**, which is the very
gap this entry is about.

This is the review's recurring finding inverted: not an assertion that cannot
fail, but a test that can only pass by installing a state production forbids.
One of the three already said so in its own docstring — *"reachable only by
bypassing `validate_config`"* — so it was known at one site and not generalised.

**Resolved by opt-out, not by deletion.** `override(..., validate=False)`, used
at exactly those three sites, each carrying a comment saying why. Whether that
defence-in-depth should remain is a layering question — the schema validates
once at a boundary, the consumers re-check at point of use — and settling it
means touching `_discriminator.py` and `_instrument.py`, which is not something
to decide inside a PR about append. Recorded here as the open half.
