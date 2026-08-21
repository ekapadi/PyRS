# 01 — Config Infrastructure & Test Framework

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** 1
**Depends on:** —

---

## Overview

This is the first and foundational sub-spec. It introduces two pieces of
infrastructure that every subsequent spec relies on:

1. **Config** — a runtime configuration file, loaded via the shared
   `neutrons_standard.Config` singleton (not a from-scratch loader), so
   NXstress behaviour (field naming, default file extension, etc.) can be
   controlled without code changes.
2. **Test-framework fixups** — shared pytest fixtures and conventions for the
   NXstress test suite, so every subsequent spec can write clean, consistent
   tests without repeating boilerplate.

Neither of these items add user-visible NXstress I/O to the GUI yet (that
starts in specs 02–03), but both are prerequisites for all later work.

---

## Scope

**In scope:**
- Add the `neutrons` pixi channel and the `neutrons_standard` dependency
  (`[tool.pixi.dependencies]` and run-dependencies)
- `pyrs/utilities/config.py` — thin wrapper that registers PyRS with
  `neutrons_standard` and re-exports its `Config` singleton, plus PyRS's own
  "at least one format enabled" validation rule
- `pyrs/resources/application.yml` (+ `pyrs/resources/__init__.py`) —
  default config file, at the exact location/name `neutrons_standard`
  requires
- The two-section `nxstress`/`legacy_io` config schema (see below)
- Shared pytest fixtures in `tests/unit/pyrs/utilities/NXstress/conftest.py`
  and `tests/unit/pyrs/utilities/conftest.py`
- Test-data management conventions (temp-file helpers, fixture cleanup)

**Out of scope:**
- Any NXstress writer/reader changes
- Any GUI viewer changes
- `argparse`/`--config` CLI wiring on `pyrsplot`, `pyrs-calibration`, or
  `create-mask` — dropped; `neutrons_standard.Config` is `env`-var driven,
  not CLI-driven, and a plan reviewer confirmed that's sufficient
- A from-scratch pydantic `Config` model, or `pyyaml` as an explicit
  dependency — superseded by `neutrons_standard.Config`, which handles its
  own YAML I/O internally
- The production-names flip (that happens in spec 10, not spec 04 —
  corrected cross-reference; spec 04 explicitly lists this flip as out of
  its own scope)

---

## PyRS Changes

_None to existing modules_ — the config infrastructure is new code. A plan
reviewer asked that it build on the shared `neutrons_standard.Config`
singleton (`github.com/neutrons/PythonCommons`, `neutrons` pixi channel)
rather than a from-scratch pydantic loader; this changed the design from
what this section originally specified (see git history for the earlier
CLI-flag/pydantic version).

Pixi wiring (`pyproject.toml`):
- `"neutrons"` added to `[tool.pixi.workspace] channels`.
- `neutrons_standard = "*"` added to `[tool.pixi.dependencies]` and
  `[tool.pixi.package.run-dependencies]`. Verified empirically that this is
  sufficient for every pixi environment (`default`, `dev`, `qa`, `prod`) to
  resolve and import `neutrons_standard` — pixi's environments compose base
  deps with feature deps additively, so no per-environment duplicate entry
  is needed.

New files:
- `pyrs/utilities/config.py` — registers PyRS with `neutrons_standard`
  (`neutrons_standard.init("pyrs")`) and re-exports its `Config` singleton;
  `Config` must always be imported from *this* module, never
  `from neutrons_standard...import Config` directly elsewhere, because
  `init()` must run before `neutrons_standard.config` is first imported (a
  stray direct import elsewhere would race `init()` and silently pin
  `neutrons_standard`'s internal `package_name` to `None` for the rest of
  the process). Also owns PyRS's own "at least one format enabled"
  validation rule — `neutrons_standard.Config` provides no schema
  validation of its own — raised eagerly at import time via
  `validate_config()`, rather than at the first NXstress-I/O callsite that
  needs a valid config.
- `pyrs/resources/__init__.py` + `pyrs/resources/application.yml` — the
  exact filename and location `neutrons_standard` requires (a genuine
  `pyrs.resources` subpackage, found via `importlib.resources`), not a
  PyRS-chosen path. Content:
  ```yaml
  nxstress:
    enable: true
    extension: ".nxs"
    use_production_names: false   # true once nexusformat validator bug resolved
  legacy_io:
    enable: true
    extension: ".h5"
  ```
  Two fully parallel, self-contained top-level sections — one per format.
  Each owns its own `enable` flag and its own `extension`; nothing is
  shared or ambiguous between them. `validate_config()` raises if
  `not (nxstress.enable or legacy_io.enable)`.
  Packaging note: no change needed — `pyproject.toml`'s existing
  `[tool.hatch.build.targets.wheel] artifacts` glob `"pyrs/**/*.yml"`
  already covers this new location.

No CLI wiring: `neutrons_standard.Config` is driven entirely by the `env`
OS environment variable (e.g. `env=/path/to/override.yml`, deep-merged on
top of the shipped default), not by an argparse flag — `pyrsplot`,
`pyrs_calibration`, and `create_mask` are unchanged.

`Config` (from `pyrs.utilities.config`) is importable and usable via
dot-string keys (e.g. `Config["nxstress.enable"]`) at NXstress callsites
that read the flags (spec 02 onwards).

---

## NXstress / GUI Changes

_None_ — no changes to `pyrs/utilities/NXstress/` or `pyrs/interface/` in
this spec.

---

## Test-framework Fixups

The following items clean up and extend the NXstress test suite so that
specs 02–10 can write tests without boilerplate.

### Shared fixtures (`tests/unit/pyrs/utilities/NXstress/conftest.py`)

- `minimal_HidraWorkspace` — a factory fixture (not the single fixed shape
  originally proposed as `minimal_workspace`), since real NXstress tests
  need several structural combinations. Returns a small, entirely
  synthetic `HidraWorkspace` — no project file is read from disk — built
  from minimal `SampleLogs` (`vx`/`vy`/`vz`, `start_time`/`end_time` as
  ISO-8601 bytes matching real HDF5 string datasets, `mrot`, `Filename`),
  one or more sub-runs, and a wavelength, with instrument geometry, masks,
  raw counts, and reduced-diffraction data each toggled on via keyword
  flags (`with_instrument`, `with_masks`, `with_raw_counts`,
  `with_reduced_diffraction`).
  Naming note: never abbreviate `HidraWorkspace` to "workspace" — Mantid's
  own `Workspace` is a different concept; this matches the pre-existing
  `load_HidraWorkspace` naming.
- `minimal_PeakCollection` — a thin, defaults-filling wrapper around the
  pre-existing `createPeakCollection` fixture
  (`tests/util/peak_collection_helpers.py`), fulfilling the plan's
  `minimal_peak_collection` ask under the same renaming rationale.
- `load_HidraWorkspace` (the original real-file loader) is kept as an
  explicit *legacy* fixture, documented as such, for a test that
  genuinely needs real project-file content.
- `tmp_path`-relative `.nxs` files needed no new fixture: every NXstress
  test already used pytest's built-in `tmp_path`, confirmed as the
  convention (the plan allowed this alternative).
- `default_config` (`tests/unit/pyrs/utilities/conftest.py` — one directory
  up from `NXstress/`, since `pyrs/utilities/config.py` isn't itself
  NXstress-specific, and a fixture there is visible down into `NXstress/`
  too) — a test-isolated `neutrons_standard.Config` singleton. Every test
  that requests it gets a genuinely fresh instance: `HOME` monkeypatched to
  `tmp_path`, `env` cleared, `reset_Singletons()` called, then
  `pyrs.utilities.config` (and `neutrons_standard.config`) reloaded so the
  already-bound `Config` name actually picks up the reset. Without this, a
  test that merely imports `pyrs.utilities.config` unconditionally writes a
  backup file to the real user's `~/.pyrs/` — the same class of
  shared-process-global-state hazard as the pre-fix RNG issue below, fixed
  the same way (full per-test re-initialization).

### Test-data hygiene

- Went beyond "replace hardcoded absolute paths": 74 of the 76 NXstress
  tests that depended on loading a real HB2B project file (via
  `load_HidraWorkspace`) were migrated onto the synthetic fixtures above,
  eliminating real-file I/O from them entirely rather than just
  relocating paths. The only "absolute path"-shaped strings left anywhere
  in the suite are inert `projectfilename=` metadata on synthetic
  `PeakCollection`s, never opened — confirmed, not changed.
- All existing NXstress tests confirmed passing after the migration
  (`pixi run test-unit` / `test-integration`, full suite, before and
  after).

### Convention note

Delivered as a module docstring in `conftest.py` (the plan's own
allowed alternative to a separate README.md), documenting the fixture
conventions above for future contributors.

### Markers & test tiers (repo-wide)

Broader than NXstress alone, but delivered as part of the same pass:
`integration`/`gui` pytest markers registered in `pyproject.toml` and
applied across the whole test suite, with `test-unit` / `test-integration`
/ `test-gui` pixi tasks. This is the mechanism specs 02–10 should use to
tag their own new tests.

### Test directory cleanup

Several pre-existing test files were moved to the `unit`/`integration`
location matching their actual behavior, now that markers make that
classification possible; two overly-mixed files were split. Full detail:
`plans/test-framework.md`.

### RNG determinism & synthetic-data realism

`createPeakCollection`'s RNG was a shared, session-global instance — a
test's outcome depended on how many random draws every other test that
happened to run earlier in the session had already consumed. It now
re-seeds fresh per test. Its synthetic parameter uncertainties were also
bounded to realistic proportional fractions (0.5%–5% of each parameter's
own value) instead of independent absolute ranges — this fixed an
unbounded catastrophic-cancellation amplification that one PseudoVoigt
round-trip test's tolerance had been silently relying on a single real
HB2B file to avoid.

---

## Delivered Feature

> **For end users and contributors:**
> PyRS's runtime configuration is now backed by the shared
> `neutrons_standard.Config` singleton. A default configuration file
> (`pyrs/resources/application.yml`) ships with the package and documents
> all available options. NXstress output and legacy `.h5` output are each
> independently controlled — `nxstress.enable` and `legacy_io.enable` —
> and each format's file extension (`nxstress.extension`,
> `legacy_io.extension`) is fixed by config, never chosen by the user in
> the GUI. NXstress field naming can be switched between the current
> validator-safe form and the production lowercase form by setting
> `nxstress.use_production_names: true` in the config.
>
> Override any value by setting the `env` OS environment variable to the
> name or path of a `.yml` file, whose contents are deep-merged on top of
> the shipped default — e.g. `env=/path/to/override.yml pyrsplot`. There is
> no `--config` CLI flag; this matches `neutrons_standard`'s own idiom.
>
> Internally, the test suite for NXstress (and for `pyrs/utilities/`
> generally) gains shared fixtures that make it easier to write and
> maintain tests, including a `default_config` fixture that gives each test
> a fully isolated configuration singleton.

---

## Verification

- `pixi install` succeeds with `neutrons_standard` resolved from the
  `neutrons` channel, in every pixi environment (`default`, `dev`, `qa`,
  `prod`).
- `python -c "import pyrs.utilities.config as c; print(c.Config['nxstress.enable'])"`
  → `True`, confirming the resource file resolves and loads correctly from
  an installed (not just source-tree) layout.
- A config with both `nxstress.enable: false` and `legacy_io.enable: false`
  raises at `pyrs.utilities.config` import time (via `validate_config()`),
  not later.
- `env=<path>` pointing at a `.yml` file with an override merges correctly
  on top of the shipped default (spot-checked with a throwaway env file;
  also covered by `test_default_config_env_override_merges_on_top_of_default`
  in `tests/unit/pyrs/utilities/test_config.py`).
- `grep -rn "from neutrons_standard import\|^import neutrons_standard"
  pyrs/ tests/` returns only `pyrs/utilities/config.py` — nothing else in
  the codebase races `init("pyrs")` by importing `neutrons_standard`
  directly.
- `pixi run test-unit` — full suite passes (297 passed, 1 skipped as of
  this writing), and `~/.pyrs/` does not exist afterward in a clean
  environment (`rm -rf ~/.pyrs` before the run, `ls ~/.pyrs` fails after) —
  confirming `default_config` fully isolates every config-touching test
  from the real home directory.
- `pytest tests/unit/pyrs/utilities/test_config.py` — dedicated
  config-loader unit tests pass: shipped defaults load correctly, `env`
  override merges correctly, `validate_config()` passes with defaults, and
  raises when both formats are disabled.
