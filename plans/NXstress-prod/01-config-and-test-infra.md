# 01 — Config Infrastructure & Test Framework

**Plan:** [NXstress GUI Hookup](README.md)
**Phase:** 1
**Depends on:** —

---

## Overview

This is the first and foundational sub-spec. It introduces two pieces of
infrastructure that every subsequent spec relies on:

1. **YAML Config** — a runtime configuration file with `--config` CLI support,
   so NXstress behaviour (field naming, default file extension, etc.) can be
   controlled without code changes.
2. **Test-framework fixups** — shared pytest fixtures and conventions for the
   NXstress test suite, so every subsequent spec can write clean, consistent
   tests without repeating boilerplate.

Neither of these items add user-visible NXstress I/O to the GUI yet (that
starts in specs 02–03), but both are prerequisites for all later work.

---

## Scope

**In scope:**
- `pyrs/utilities/config.py` — new config loader module
- `pyrs/config/pyrs.default.yml` — default config file, checked into the
  repo, inside the package tree (see packaging note below)
- `argparse` wiring on `pyrsplot`, `pyrs-calibration`, and `create-mask`
- Pydantic `Config` model with the two-section `nxstress`/`legacy_io` schema
  (see below), including the "at least one format enabled" validation rule
- Add `pyyaml` as an explicit dependency
- Shared pytest fixtures in `tests/unit/pyrs/utilities/NXstress/conftest.py`
  and/or a new `tests/conftest.py` contribution
- Test-data management conventions (temp-file helpers, fixture cleanup)

**Out of scope:**
- Any NXstress writer/reader changes
- Any GUI viewer changes
- The production-names flip (that happens in spec 10, not spec 04 —
  corrected cross-reference; spec 04 explicitly lists this flip as out of
  its own scope)

---

## PyRS Changes

_None_ — the config infrastructure is new code; it does not modify any
existing PyRS module.

New files:
- `pyrs/utilities/config.py` — `load_config(path: Path | None) -> Config`
  function plus a pydantic `Config` model.
- `pyrs/config/pyrs.default.yml` — default YAML with at minimum:
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
  shared or ambiguous between them. `load_config()` raises if
  `not (nxstress.enable or legacy_io.enable)` — at least one format must be
  writable; unlike an enum, two independent booleans don't make that state
  unrepresentable by construction, so this is an explicit validation rule.
  Note the location: `pyrs/config/pyrs.default.yml`, **inside** the `pyrs`
  package, not at the repo root — `pyproject.toml`'s
  `[tool.hatch.build.targets.wheel] packages = ["pyrs", "scripts"]` plus its
  `pyrs/**/*.yml` artifact globs only cover paths inside the `pyrs`
  package, so a repo-root `config/pyrs.default.yml` would not ship in the
  installed wheel.
- Add `pyyaml` as an explicit dependency in `pyproject.toml`
  (`[tool.pixi.dependencies]` and run-dependencies) — it's currently only
  present transitively via `mantid`.

Modified files:
- `scripts/pyrsplot.py` — add `argparse` with `--config <path>` (default:
  `pyrs/config/pyrs.default.yml` relative to the package root).
- `scripts/pyrs_calibration.py` — same.
- `scripts/create_mask.py` — same.

The `Config` object should be importable from `pyrs.utilities.config` and
injected at NXstress callsites that read the flags (spec 02 onwards).

---

## NXstress / GUI Changes

_None_ — no changes to `pyrs/utilities/NXstress/` or `pyrs/interface/` in
this spec.

---

## Test-framework Fixups

The following items clean up and extend the NXstress test suite so that
specs 02–10 can write tests without boilerplate. Delivered ahead of the
config-loader half of this spec (see "PyRS Changes" above, still
outstanding).

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
- `default_config` is **not delivered** — it depends on the config-loader
  half of this spec (`pyrs/utilities/config.py`,
  `pyrs/config/pyrs.default.yml`), which remains out of scope for this pass.

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
> `pyrsplot` (and the other installed scripts) now accept a `--config` flag:
>
> ```bash
> pyrsplot --config /path/to/my/pyrs.yml
> ```
>
> A default configuration file (`pyrs/config/pyrs.default.yml`) ships with
> the package and documents all available options. NXstress output and
> legacy `.h5` output are each independently controlled — `nxstress.enable`
> and `legacy_io.enable` — and each format's file extension
> (`nxstress.extension`, `legacy_io.extension`) is fixed by config, never
> chosen by the user in the GUI. NXstress field naming can be switched
> between the current validator-safe form and the production lowercase
> form by setting `nxstress.use_production_names: true` in the config.
>
> Internally, the test suite for NXstress gains shared fixtures that make it
> easier to write and maintain NXstress-related tests.

---

## Verification

- `pyrsplot --help` shows the `--config` option.
- `pyrsplot --config pyrs/config/pyrs.default.yml` starts the GUI without
  error.
- `from pyrs.utilities.config import load_config; cfg = load_config(None)`
  returns a valid `Config` object with defaults.
- `python -c "import pyrs; from importlib.resources import files;
  print(files('pyrs') / 'config' / 'pyrs.default.yml')"` (or equivalent)
  confirms the default config file is present in an *installed* (not just
  editable/source-tree) package — the packaging concern this spec fixes.
- A config with both `nxstress.enable: false` and `legacy_io.enable: false`
  raises at `load_config()` time, not later.
- `pytest tests/unit/pyrs/utilities/NXstress/` — all existing tests pass;
  new fixture-based tests pass.
- `pytest tests/unit/pyrs/utilities/ -k config` — config-loader unit tests
  pass (round-trip YAML parse, missing-key defaults, user override merging,
  the both-disabled validation error).
