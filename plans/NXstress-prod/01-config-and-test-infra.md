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
- `config/pyrs.default.yml` — default config file, checked into the repo
- `argparse` wiring on `pyrsplot`, `pyrs-calibration`, and `create-mask`
- Pydantic `Config` model with v1 NXstress fields
- Shared pytest fixtures in `tests/unit/pyrs/utilities/NXstress/conftest.py`
  and/or a new `tests/conftest.py` contribution
- Test-data management conventions (temp-file helpers, fixture cleanup)

**Out of scope:**
- Any NXstress writer/reader changes
- Any GUI viewer changes
- The production-names flip (that happens in spec 04 once the upstream
  `nexusformat` validator bug is resolved)

---

## PyRS Changes

_None_ — the config infrastructure is new code; it does not modify any
existing PyRS module.

New files:
- `pyrs/utilities/config.py` — `load_config(path: Path | None) -> Config`
  function plus a pydantic `Config` model.
- `config/pyrs.default.yml` — default YAML with at minimum:
  ```yaml
  nxstress:
    use_production_names: false   # true once nexusformat validator bug resolved
    default_extension: ".nxs"
  ```

Modified files:
- `scripts/pyrsplot.py` — add `argparse` with `--config <path>` (default:
  `config/pyrs.default.yml` relative to the package root).
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

The following items clean up or extend the existing NXstress test suite so
that specs 02–10 can write tests without boilerplate.

### Shared fixtures (extend `tests/unit/pyrs/utilities/NXstress/conftest.py`)

- `minimal_workspace` — returns a small but valid `HidraWorkspace` with:
  - a minimal `SampleLogs` (at least `sx`, `sy`, `sz`, `start_time`,
    `end_time` with ISO-8601 values, `mrot`)
  - one sub-run
  - a `DENEXDetectorGeometry` instance
  - a wavelength value
- `minimal_peak_collection` — returns a `PeakCollection` consistent with
  `minimal_workspace` (matching sub-run count, a parseable peak tag such as
  `Fe 110`).
- `nxstress_tmp_path` (or use pytest's built-in `tmp_path`) — ensure all
  written `.nxs` files land in a temp directory and are cleaned up; document
  the convention.
- `default_config` — returns a `Config` object loaded from
  `config/pyrs.default.yml`; usable in any test that exercises config-aware
  paths.

### Test-data hygiene

- Replace any hardcoded absolute paths in the existing NXstress test files
  with `tmp_path`-relative paths.
- Confirm all existing NXstress tests pass after these changes.

### Convention note

Add a brief `tests/unit/pyrs/utilities/NXstress/README.md` (or a docstring
in `conftest.py`) documenting the fixture conventions for future contributors.

---

## Delivered Feature

> **For end users and contributors:**
> `pyrsplot` (and the other installed scripts) now accept a `--config` flag:
>
> ```bash
> pyrsplot --config /path/to/my/pyrs.yml
> ```
>
> A default configuration file (`config/pyrs.default.yml`) ships with the
> package and documents all available options. NXstress field naming can be
> switched between the current validator-safe form and the production lowercase
> form by setting `nxstress.use_production_names: true` in the config.
>
> Internally, the test suite for NXstress gains shared fixtures that make it
> easier to write and maintain NXstress-related tests.

---

## Verification

- `pyrsplot --help` shows the `--config` option.
- `pyrsplot --config config/pyrs.default.yml` starts the GUI without error.
- `from pyrs.utilities.config import load_config; cfg = load_config(None)`
  returns a valid `Config` object with defaults.
- `pytest tests/unit/pyrs/utilities/NXstress/` — all existing tests pass;
  new fixture-based tests pass.
- `pytest tests/unit/pyrs/utilities/ -k config` — config-loader unit tests
  pass (round-trip YAML parse, missing-key defaults, user override merging).
