# NXstress GUI Hookup — Design Overview

## Context

An NXstress-compliant (NeXus schema) I/O implementation was recently completed
under [`pyrs/utilities/NXstress/`](../../pyrs/utilities/NXstress/). The next
step is to attach it to the existing PyRS GUI I/O endpoints so that project
data can be persisted in NXstress-native form (either alongside, or eventually
in place of, the current `HidraProjectFile` HDF5 layout).

This document maps the current I/O terrain and flags gaps that must be
resolved (or explicitly scheduled) before and during wiring NXstress into the
GUI. The phased schedule in Section 3 is the primary deliverable.

This document is the primary reference for the NXstress production hookup work. Sub-specifications for each PR-sized chunk of work are listed below.

## Sub-specifications

| Spec | Title | Phase | Depends on |
|---|---|---|---|
| [01](01-config-and-test-infra.md) | Config infrastructure & test framework | 1 | — |
| [02](02-peak-and-texture-nxstress.md) | NXstress I/O for PeakFitting & Texture viewers | 1 | 01 |
| [03](03-combine-runs-nxstress.md) | NXstress I/O for CombineRuns viewer | 1 | 01 |
| [04](04-nxstress-internal-cleanup.md) | NXstress internal cleanup (Phase 2 TODOs) | 2 | 02, 03 |
| [04b](04b-multi-workspace-nxstress.md) | Multi-workspace NXstress I/O | 2/3 | 01, 04 |
| [04c](04c-nxstress-append.md) | NXstress append mode (library only) | 3 | 04b |
| [05](05-strain-stress-viewer.md) | StrainStressViewer NXstress hookup | 3 | 01, 04, 04b |
| [06](06-manual-reduction-prereqs.md) | Manual reduction PyRS prerequisites (not required for NXstress) | — (independent PyRS cleanup) | — |
| [07](07-manual-reduction-nxstress.md) | ManualReductionViewer NXstress hookup | 4 | — |
| [08](08-fit-spectrum-prereqs.md) | Reconstructed fit spectrum & calibration fidelity (PyRS) | 5 | — |
| [09](09-fit-spectrum-nxstress.md) | Fit spectrum & calibration fidelity (NXstress) | 5 | 07, 08 |
| [10](10-flip-defaults.md) | Flip defaults — NXstress becomes primary | 6 | 09 |

---

## 1. Current I/O Architecture

### 1.1 Core layers

| Layer | Module | Role |
|---|---|---|
| Low-level HDF5 | `pyrs/projectfile/file_object.py` — `HidraProjectFile` | Read/write every field in a `.h5` project file (raw counts, reduced diffraction, sample logs, peak parameters, masks, instrument geometry, wavelengths). |
| Workspace | `pyrs/core/workspaces.py` — `HidraWorkspace` | High-level in-memory model; wraps `HidraProjectFile` load/save. Methods: `load_hidra_project` (L463), `append_hidra_project` (L497), `save_experimental_data` (L1025), `save_reduced_diffraction_data` (L1096). |
| Peaks | `pyrs/peaks/peak_collection.py` — `PeakCollection` / `PeakCollectionLite` | The unit persisted by `HidraProjectFile.write_peak_parameters` (L778) / `read_peak_parameters` (L712). |
| Fields | `pyrs/dataobjects/fields.py` — `StrainField`, `StressField`, `ScalarFieldSample` | Built _from_ `HidraProjectFile` reads; persisted via CSV (`ScalarFieldSample.to_csv`, L610) and the CSV summary generators. Not directly serialized to HDF5 today. |
| Summary writers | `pyrs/core/summary_generator.py`, `summary_generator_stress.py` | CSV exports for peaks + logs and for stress fields. |
| Calibration | `pyrs/utilities/calibration_file_io.py` | JSON/ASCII calibration recipes (independent of project-file layout). |

### 1.2 GUI endpoints that touch I/O

All GUI dialogs live under `pyrs/interface/` and are launched via
`pyrs/interface/pyrs_main.py::PyRSLauncher` (L36). The six top-level windows
and their I/O touch points are:

| Viewer | Load path (I/O method) | Save path (I/O method) | File filter |
|---|---|---|---|
| **PeakFittingViewer** (`peak_fitting/`) | `PeakFittingModel.load_hidra_project` → `HidraProjectFile(...)` (`peak_fitting_model.py:100`) | `save_fit_result` → copyfile + `HidraProjectFile(..., READWRITE)` + `write_peak_parameters` per `PeakCollection` + `save(False)` (`peak_fitting_model.py:189-199`) | `HDF (*.hdf);H5 (*.h5)` load; `H5 (*.h5);;HDF (*.hdf5)` save |
| **TextureFittingViewer** (`texture_fitting/`) | `TextureFittingModel.load_hidra_project_file` → `HidraProjectFile(READONLY)` (`model.py:37`) | `save_fit_result` → `HidraProjectFile(READWRITE)` + `write_peak_parameters` per masked `PeakCollection` (`model.py:141-165`) | `HidraProjectFile (*.h5)` |
| **StrainStressViewer** (`strainstressviewer/`) | `Model.load_hidra_project_file` per direction → `HidraProjectFile(READONLY)` + `read_peak_tags` + `read_peak_parameters` (`model.py:280-293`) | CSV via `SummaryGeneratorStress` (`model.py:258-264`); state via JSON (`to_json`/`from_json`, `model.py:316/344`); d0 grid via `np.savetxt`/`np.loadtxt` | `HidraProjectFile (*.h5)` load; `CSV (*.csv)` / `JSON (*.json)` save |
| **CombineRunsViewer** (`combine_runs/`) | `Model.combine_project_files` → multiple `HidraProjectFile(...)` reads (`combine_runs_model.py:16-21`) | `Model.export_project_files` → new `HidraProjectFile("w")` + `save_experimental_data` + `save_reduced_diffraction_data` + `save` (`combine_runs_model.py:25-31`) | `HidraProjectFile (*.h5)` |
| **ManualReductionViewer** (`manual_reduction/`) | Browse-only line edits for NeXus/mask/vanadium inputs | `reduce_hidra_workflow` (module-level function, `pyrs_api.py:251`) automatically calls `ReductionApp.save_diffraction_data` (`pyrs_api.py:348`) as part of every reduction — this is the actual, currently-functional save path. `ReductionController.save_project` (`pyrs_api.py:190`, not `HB2BReductionManager` — that name belongs to an unrelated class in `pyrs/core/reduction_manager.py`) is a separate, `NotImplementedError` stub with **zero callers anywhere in the codebase** | `NeXus(*.nxs.h5)`, `Mantid Mask(*.xml)`, `HiDRA project(*.h5)` |
| **DetectorCalibrationViewer** (`detector_calibration/`) | `Nexus (*.nxs.h5)` load, `json (*.json)` recipe load | `write_calibration` via calibration object; `json.dumps` recipe (`detector_calibration_viewer.py:558`) | `Nexus (*.nxs.h5)`, `JSON (*.json)` |

Common file filters in use today: `*.h5` (dominant), `*.hdf5`/`*.hdf`
(peak-fit compatibility), `*.nxs.h5` (NeXus event files), `*.csv`, `*.json`,
`*.xml` (masks). No bare `*.nxs` is currently registered anywhere in the GUI.

### 1.3 Non-GUI entry points

`pyproject.toml` registers CLI scripts under `scripts/`:

- `pyrsplot` — GUI launcher, no direct I/O.
- `pyrs-calibration` (`scripts/pyrs_calibration.py:144`) — CLI-only, writes
  calibration JSON via `write_calibration` (L212–229). Not a project-file path.
- `pyrs-calibration-correlation`, `create-mask` — supporting scripts.

Per-viewer standalone `start.py` scripts route all I/O through the GUI model.
None of the installed scripts currently accept `--config` or any equivalent
flag (see Section 2.3).

### 1.4 What NXstress currently expects

The public surface is one class,
[`pyrs.utilities.NXstress.NXstress`](../../pyrs/utilities/NXstress/NXstress.py):

```python
with NXstress(path, "w") as nxS:
    nxS.write(ws: HidraWorkspace, peakss: list[PeakCollection])

with NXstress(path, "r") as nxS:
    ws, peakss = nxS.read(entry_number=1)
```

Its input/output types are **exactly** the pair
`(HidraWorkspace, list[PeakCollection])` that PeakFittingViewer and
TextureFittingViewer already produce and consume, making those two viewers
the natural first integration point.

Multiple `NXentry` groups per file are supported (`NXstress.py:149`). These
are reserved for "distinct data-reduction or sample conditions" — not for
multi-direction stress data, which is handled via the compound `PeakIndex`
(see Section 2.4).

---

## 2. Issues to Resolve Before / During Hookup

### 2.1 NXstress-side gaps (already noted in the code)

These are things the NXstress implementation itself cannot yet do. Some are
self-contained fixes; others require upstream PyRS changes (scheduled in the
phases below).

- **Appending to an existing entry / workspace** — `_input_data.py:44,63` and
  `NXstress.py:151-152` raise on any operation that would extend an existing
  `NXentry`. Each write must currently be a fresh entry (save-as). Scheduled:
  Phase 3 (spec 04c) — as a library capability only; no GUI wiring is
  scheduled for append in this pass, since spec 07's reduction pathway is
  decided to always write a fresh file.
- **NXbeam intensity profile empty** — `_instrument.py:127`. Fine for Phase 1;
  readers must tolerate absence. Scheduled: Phase 5 (depends on reduction
  pipeline producing a profile).
- **Detector L2 not extractable from `DENEXDetectorGeometry`** —
  `_instrument.py:138-140`. Round-tripping a calibrated geometry may lose the
  arm-shift information. Requires a new accessor on `DENEXDetectorGeometry`.
  Scheduled: Phase 5.
- **Detector rotation-order TODO** — `_instrument.py:165`. A wrong order
  silently mis-orients the instrument in the file. Must be cross-checked
  against the reduction code's convention. Scheduled: Phase 2.
- **Instrument name hardcoded to `"HB2B"`** — `_instrument.py:70`. Fine for
  single-beamline use; parameterize before any HB2A/other-instrument use.
  Scheduled: Phase 2.
- **Scan-point positions `sx`/`sy`/`sz` hardcoded to NaN** —
  `_peaks.py:235-239`. The commented-out `logs['sx'/'sy'/'sz']` block was
  disabled pending log-key naming confirmation. Needs to be restored and the
  key names reconciled against what the reduction pipeline emits. Scheduled:
  Phase 2.
- **Fit diffractogram `fit`/`fit_errors` initialized to NaN** —
  `_fit.py:425-429` (placeholder comment), `:430-438` (zero-sized resizable
  field creation). PyRS does not currently reconstruct the fitted
  model spectrum after peak-fitting. Blocked on a PyRS fit-engine change.
  Scheduled: Phase 5.
- **Mask naming/storage inconsistency** — `_fit.py:546-549`. Default vs. named
  masks are addressed differently in the current writer; needs a single
  convention before external readers can rely on the layout. Scheduled:
  Phase 2.
- **Sample `STRESS_FIELD` shape unverified** — `_sample.py:107` (actual
  comment: *"we don't have an example of these entries, so the dimensions
  may not be correct!"*). Confirmed no real dataset with a genuine
  `STRESS_FIELD` log exists anywhere in the repo — blocked, see
  `open-questions/08-fit-spectrum-prereqs.md` Q3. Scheduled: Phase 5.
- **Group-name validator workarounds** — several `GROUP_NAME` values
  (`_definitions.py:106,109,116,122,127-135`) and
  `DGRAM_TWO_THETA_NAME = "XAXIS"` (`_fit.py:414`) were set to upper-case /
  generic forms to work around a `nexusformat` validator bug. The generic names
  are likely acceptable on-disk schema-wise, but the production intent is
  meaningful lowercase names. **Resolution:** expose as a `Config` toggle
  (Section 2.3) so the writer can emit either form without a code change.
  Whether uppercase names are strictly allowed by NXstress requires a
  schema-spec check. Scheduled: Phase 1 (Config infrastructure) + Phase 2
  (flip default once validator bug is resolved upstream).
- **`allowed_identifier` disallowed-character coverage incomplete** —
  `_definitions.py:229`. Scheduled: Phase 2.

### 2.2 Upstream PyRS data-object gaps

Missing capabilities in PyRS proper that NXstress cannot fill in on its own:

- **No `StrainField` / `StressField` serialization** — NXstress today
  serializes `HidraWorkspace` + `list[PeakCollection]` but does not consume or
  produce the field-level objects (`pyrs/dataobjects/fields.py::StrainField`,
  `StressField`). Wiring StrainStressViewer means building the fields on-the-
  fly at read time from a direction-indexed NXstress file. Scheduled: Phase 3.
- **No reconstructed model spectrum** — PyRS's fit engine returns parameter
  values but no full-length reconstructed profile on the two-theta grid.
  This blocks populating `diffractogram/fit` and `diffractogram/fit_errors`
  with real data. Scheduled: Phase 5.
- **`DENEXDetectorGeometry` accepts but discards its `calibrated` flag,
  and its arm-shift-application code path is dead/broken** — corrected
  location: not `file_object.py:510` (that FIXME doesn't exist; the only
  comment there is an unrelated return-type-annotation TODO). The real gap
  is entirely within `instrument_geometry.py::DENEXDetectorGeometry`
  itself. Scheduled: Phase 5 (spec 08).
- **`HidraProjectFile` legacy log-name patches** (`file_object.py:404`, `:494`
  FIXME) — audit to ensure NXstress does not codify the legacy names into the
  schema-conformant file. Scheduled: Phase 2.
- **`ScalarFieldSample` / `StrainField` `NotImplementedError` methods** in
  `fields.py` (L239, 611, 816, 927, 956, 960, 964, 983, 986, 994, 1184) — not
  directly on the write path, but any read-back that reconstructs these fields
  for the StrainStressViewer will hit them. Scheduled: Phase 3 (as needed).
- **`ReductionController.save_project`** (`manual_reduction/pyrs_api.py:190`
  — not `HB2BReductionManager`, an unrelated class elsewhere) is
  `NotImplementedError`, but has zero callers anywhere in the codebase.
  **Resolved: NXstress does not attach there.** The real, currently-functional
  save path is `reduce_hidra_workflow`'s automatic
  `ReductionApp.save_diffraction_data` call — that's where spec 07 hooks in
  instead. `save_project` remains an independent, optional PyRS cleanup item
  (spec 06), not required for NXstress. Not scheduled in this plan's phases.
- **`nexus_conversion.py:118, 374`** — two unimplemented branches, confirmed
  unrelated to any save/output-format path (an unsupported log-property
  type and a non-`.xml` mask-file restriction, both reachable only from
  NeXus-*conversion*, not from saving). Not on the NXstress critical path;
  tracked as an independent PyRS item (spec 06), not scheduled in this
  plan's phases.

### 2.3 New capability: YAML Config

PyRS has no runtime configuration file. The installed scripts (`pyrsplot`,
`pyrs-calibration`, `create-mask`) use either no CLI flags or positional
arguments only; no `argparse` + `--config` plumbing exists. This work adds:

- A YAML config file parsed with `pyyaml` (add as an explicit dependency —
  currently only present transitively via `mantid`). Two fully parallel,
  self-contained top-level sections, one per output format — each owns its
  own `enable` flag and its own `extension`; nothing is shared or ambiguous
  between them:
  ```yaml
  nxstress:
    enable: true
    extension: ".nxs"
    use_production_names: false
    discriminator_fields: []
    merge_workspaces: false
  legacy_io:
    enable: true
    extension: ".h5"
  ```
  - `nxstress.enable` / `legacy_io.enable: bool` — whether each format is
    writable at all. Every NXstress-wired viewer's save action reads its
    own format's `enable` flag directly to decide whether that action is
    clickable (`QAction.setEnabled`, not `setVisible` — the action stays
    visible, just grayed out, when disabled).
  - `nxstress.extension` / `legacy_io.extension: str` — each format's file
    extension. **Imposed, never user-chosen:** every save action enforces
    its own section's extension on whatever filename a `QFileDialog`
    returns; a user cannot type a different extension and have it honored.
  - `load_config()` raises if `not (nxstress.enable or legacy_io.enable)` —
    at least one format must be writable. Unlike an enum, two independent
    booleans don't make this state unrepresentable by construction, so
    this is an explicit validation rule.
  - `nxstress.use_production_names: bool` — toggle between the current
    validator-safe generic group names and the production lowercase forms.
  - `nxstress.discriminator_fields: list[str]` (default `[]`) — names of the
    fields that discriminate one input `HidraWorkspace` from another when
    `NXstress.write` is given more than one (spec 04b).
  - `nxstress.merge_workspaces: bool` (default `false`) — when `true`,
    permits writing more than one workspace with `discriminator_fields`
    empty by silently merging them into one indistinguishable combined index
    instead of raising (spec 04b).
  - Reserved namespace for future flags (`nxstress.write_raw_counts`,
    `nxstress.strict_schema_validation`, etc.).
- Default config location: `pyrs/config/pyrs.default.yml` — **inside** the
  `pyrs` package, not at the repo root (`pyproject.toml`'s
  `[tool.hatch.build.targets.wheel] packages = ["pyrs", "scripts"]` plus its
  `pyrs/**/*.yml` artifact globs only cover paths inside the `pyrs`
  package; a repo-root `config/pyrs.default.yml` would not ship in the
  installed wheel). The loader also honors `~/.config/pyrs/config.yml` if
  present and merges it over the default.
- A shared loader at `pyrs/utilities/config.py` returning a validated
  (pydantic) `Config` object, injected at NXstress callsites that read the
  flags.
- `argparse` wiring on each installed script — `pyrsplot --config <path>`
  (analogously for `pyrs-calibration`, `create-mask`). When `--config` is
  absent, fall back to the default location.

This is a prerequisite for closing the Section 2.1 group-name validator
workaround cleanly. Scheduled: Phase 1.

### 2.4 Beyond-code decisions

- **File-extension policy** — **decided:** distinct `*.nxs` extension across
  every viewer; coexists with existing `*.h5` `HidraProjectFile` paths. Each
  format's extension (`nxstress.extension`/`legacy_io.extension`) is
  imposed by the action a user clicks — never typed/chosen by the user, and
  never auto-detected from an existing file's suffix.
- **Coexistence vs. replacement** — **decided (phased):** Phase 1 ships
  additive (both paths coexist; NXstress offered as new menu entries and file-
  dialog filters, each independently enabled per `nxstress.enable`/
  `legacy_io.enable`). Phase 6 flips defaults (NXstress becomes primary;
  `HidraProjectFile` becomes legacy-read-only) — **purely by flipping the
  shipped config default** (`legacy_io.enable: true` → `false`); no viewer
  code changes, since every wired viewer's save actions were already built
  in their own spec to read these flags directly. Concrete acceptance
  criteria for the Phase 6 flip to be defined at the end of Phase 1
  (tracked, still open — see `open-questions/10-flip-defaults.md` Q1).
- **Multi-direction semantics** — StrainStressViewer today loads N project
  files per direction into three parallel slots (`filenames_11/22/33`).
  **Decision:** this is a special case of the general multi-workspace
  mechanism built in spec 04b — one `HidraWorkspace` per direction in, one
  `.nxs` file (single NXentry) out, with `direction` as one of 04b's
  explicit discriminator fields on the compound peak index. NOT
  one-NXentry-per-direction. The schema question this previously gated on —
  whether `NXreflections` permits additional index columns at all — is
  downgraded from a blocking gate to a tracked follow-up: `_peaks.py`
  already writes `mask`/`scan_point`/etc. as non-required columns, which is
  the same category of extension; see
  `open-questions/04b-multi-workspace-nxstress.md` Q1 for the precedent and
  the pending cross-check against `NXstress.html` and the `nexusformat`-org
  validator once both are added to the repo — tracked as a concrete reminder
  in [10-flip-defaults.md](10-flip-defaults.md)'s Overview, not just noted
  here.
- **Multi-workspace I/O (new)** — beyond StrainStressViewer's specific case,
  `NXstress.write` / `NXstress.read` are generalized to
  `list[HidraWorkspace]`, round-trip symmetric (spec 04b). Workspace
  boundaries are recovered from discriminator field(s) named by the new
  `nxstress.discriminator_fields` config key (§2.3), resolved per workspace
  by preferring a matching `HidraWorkspace` `@property` and otherwise
  falling back to `SampleLogs`, and carried internally name-keyed rather
  than positionally so config reordering between write and read can't cause
  silent misattribution. The specific field names any deployment configures
  are decided at 04b implementation kickoff, not in this document. The
  existing no-overlap invariant (each input workspace contributes only
  unique scan points and/or other index fields) is assumed, not newly
  validated by this decision — 04b does add an explicit write-time check for
  it, and raises if asked to combine more than one workspace with no
  discriminator fields configured, unless `nxstress.merge_workspaces` opts
  into silently merging instead.
- **Append mode, library-only (new)** — append (spec 04c) ships as a tested
  `NXstress(path, "a")` capability with **no GUI entry point** in this pass.
  The one pathway that might have used it (ManualReductionViewer, spec 07)
  is decided to always write a fresh file instead, so append and the
  ManualReduction hookup are no longer bundled (they were, in an earlier
  draft of spec 07).
- **Multi-NXentry semantics (unchanged)** — multiple NXentry within a single
  `.nxs` file remain reserved for "distinct data-reduction or sample
  conditions" (`NXstress.py:107-125`). The compound peak index is the axis for
  finer variation (masks, phases, directions) within a single condition.
- **Read-back completeness** — `NXstress.read` reconstructs wavelengths, sample
  logs, masks, reduced diffraction data, and peak collections. It does NOT
  reconstruct raw counts unless the optional `input_data` group was written.
  Verify each viewer's load path is satisfied by this subset during Phase 1
  wiring.

---

## 3. Phased Implementation Schedule

The work is deliberately phased so Phase 1 can ship using existing PyRS
capabilities, with `NaN` as a documented placeholder for data PyRS does not
yet produce. Subsequent phases progressively close those placeholders —
first by adding capability on the PyRS side, then by wiring the NXstress
writer/reader to use it.

**Every TODO listed in Sections 2.1 and 2.2 must be scheduled — none are
deferred indefinitely.**

Each phase is broken into two strictly-separate sub-lists:

- **PyRS changes** — modifications to PyRS proper (data objects, reduction,
  fit engine, workspace, etc.), independent of NXstress.
- **NXstress extensions** — modifications inside
  `pyrs/utilities/NXstress/` and the GUI wiring in `pyrs/interface/`.

---

### Phase 1 — Baseline hookup with `NaN` placeholders

**Goal:** Every viewer whose data model already matches
`NXstress.write(ws, peakss)` gains a working NXstress save/load path,
alongside (not replacing) the existing `HidraProjectFile` I/O. Any data
NXstress requires but PyRS does not yet produce is written as `NaN` and
documented as a Phase-1 limitation.

**Required PyRS changes:** _none._ Phase 1 is entirely additive on the
consumer side.

**Required NXstress extensions / GUI wiring:**
- Introduce the `Config` infrastructure (Section 2.3):
  `pyrs/config/pyrs.default.yml`, `pyrs/utilities/config.py`, `--config` on
  all installed scripts. Ship with `nxstress.use_production_names = false`
  (validator-safe generic names), `nxstress.enable = true`,
  `legacy_io.enable = true` as the defaults (both formats available,
  matching today's `.h5`-only behavior plus the new NXstress option).
- Wire `NXstress` into `PeakFittingModel.save_fit_result` and
  `PeakFittingModel.load_hidra_project` as a new save/load path, triggered by
  a new `Save as NXstress…` menu action and an added `NXstress (*.nxs)` filter
  in the load dialog (`peak_fitting_viewer.py`, `peak_fitting_model.py`).
  Both this action and the existing `Save` (`.h5`) action are wired to read
  `nxstress.enable`/`legacy_io.enable` for their own enabled/disabled state.
- Same wiring in `TextureFittingModel` (`save_fit_result` /
  `load_hidra_project_file`, `texture_fitting_viewer.py`, `model.py`).
- Same wiring in `CombineRunsModel.export_project_files` /
  `combine_project_files` — fresh-write only; document that append is not yet
  supported.
- Round-trip tests for each of the three viewers: write via NXstress, read
  back, assert equality of `HidraWorkspace` and `list[PeakCollection]`.
- User-facing docs: note the `NaN` placeholders (sx/sy/sz,
  diffractogram fit/fit_errors) as documented Phase-1 limitations.

**Deferred to later phases (all scheduled):**
StrainStressViewer (Phase 3), ManualReductionViewer (Phase 4), all Section 2.1
and 2.2 TODOs.

---

### Phase 2 — Close the low-cost NXstress-side TODOs

**Goal:** Resolve NXstress-internal issues that don't require any PyRS
data-model change.

**Required PyRS changes:**
- Audit `HidraProjectFile` legacy log-name patches (`file_object.py:404`,
  `:494` FIXME) and confirm the correct canonical names to emit from NXstress.

**Required NXstress extensions:**
- Restore `sx`/`sy`/`sz` reading from `SampleLogs` in `_peaks.py:235-239`
  (the commented-out block); reconcile log-key names against what the
  reduction pipeline emits.
- Reconcile default vs. named mask storage into a single convention
  (`_fit.py:546-549`).
- Complete disallowed-character coverage in
  `_definitions.py::allowed_identifier` (L229).
- Flip `nxstress.use_production_names` default to `true` in
  `pyrs/config/pyrs.default.yml` once the upstream `nexusformat` validator
  bug is resolved.
- Parameterize the hardcoded instrument name in `_instrument.py:70`
  (currently `"HB2B"`) — draw from `Config` or from `HidraWorkspace`.
- Detector rotation-order cross-check + fix in `_instrument.py:165`
  against the reduction code's convention; add a regression test.

---

### Phase 2/3 bridge — Multi-workspace NXstress I/O and append mode

**Goal:** Generalize `NXstress.write` / `NXstress.read` from one
`HidraWorkspace` to `list[HidraWorkspace]` (round-trip symmetric), then add
append mode on top of that mechanism as a separate, library-only capability.
These two specs sit between Phase 2 (internal cleanup, which touches the same
`_peaks.py`/`_fit.py`/`_instrument.py` functions this generalizes) and Phase 3
(StrainStressViewer, which is a direct consumer of the new signature).

> **Schema precedent already exists — a tracked follow-up, not a blocker:**
> `_peaks.py` already writes `mask`, `scan_point`, and other non-required
> columns onto `NXreflections`; a discriminator column is the same category
> of extension. Cross-check against `NXstress.html` and the `nexusformat`-org
> validator once both are added to the repo (tracked as a concrete reminder
> in [10-flip-defaults.md](10-flip-defaults.md)'s Overview), and record the
> outcome — but that verification doesn't gate starting 04b. This supersedes
> the narrower
> `direction`-axis question this document previously scheduled as a hard gate
> for Phase 3 kickoff. See `open-questions/04b-multi-workspace-nxstress.md` Q1.

**[04b — Multi-workspace NXstress I/O](04b-multi-workspace-nxstress.md):**
- **Depends on:** spec 01 (Config infrastructure), in addition to 04 — new
  config keys `nxstress.discriminator_fields` and `nxstress.merge_workspaces`
  (§2.3) land wherever spec 01 delivers its config schema.
- **Required PyRS changes:** none. Discriminator-value resolution (property
  on `HidraWorkspace` if one exists, else `SampleLogs` fallback) lives
  entirely in NXstress's own code — no new `HidraWorkspace` method.
- **Required NXstress extensions:** change `write`/`read` to accept/return
  `list[HidraWorkspace]`; resolve discriminator field names from
  `nxstress.discriminator_fields` via `pyrs.utilities.config.load_config()`;
  add a name-keyed discriminator slot to `_peaks.py::PeakIndex` (not
  positional — robust to config reordering between write and read); update
  `sort_key`, `validateNoDuplicatePeaks`, `_init`, `init_group`,
  `peakCollectionsFromNexus`; merge logic across workspaces in
  `_InputData`/`_Sample`/`_Instrument`/`_Fit` `init_group`; raise if asked to
  combine more than one workspace with no discriminator fields configured,
  unless `nxstress.merge_workspaces` is `true`; update specs 02/03 call
  sites to the new (length-1-list-compatible) signature.
- Retires the direction-aware-container item this document previously
  scheduled under Phase 3 — see the Decisions Log update below.

**[04c — NXstress append mode, library only](04c-nxstress-append.md):**
- **Required PyRS changes:** none. Append resizes/inserts directly against
  on-disk NXstress arrays — it does not reconstruct the existing entry as
  `HidraWorkspace`/`PeakCollection` to avoid round-tripping potentially
  large existing raw-count data through PyRS's outer types.
- **Required NXstress extensions:** implement coordinated append across both
  position-aligned families — peak-index family (`_peaks.py`'s compound
  index at `_peaks.py:180-181`, plus `_fit.py::_PeakParameters`/
  `_BackgroundParameters`, which are positionally aligned with it, not
  independently keyed) and scan-point family (`_input_data.py:44-46,63-72`
  `detector_counts`, `_sample.py`'s per-scan-point logs, and
  `_fit.py::_Diffractogram`). `_instrument.py::_Masks` needs no change — it's
  name-keyed and already append-capable. `NXstress.py`: add entry targeting
  (`entry_number`, defaulting to the last entry) and remove the guard at
  `NXstress.py:151-152` for the append case. Conflict policy: reject with
  `RuntimeError` (checked across all affected groups before any mutation;
  invalidates the instance for further writes on conflict). **No GUI
  wiring** — no viewer in this plan calls append in this pass.
- Round-trip test: write, then append, into the same entry; verify combined
  contents.

---

### Phase 3 — StrainStressViewer

**Goal:** Hook up StrainStressViewer, using 04b's multi-workspace mechanism
with `direction` as the discriminator field — one `HidraWorkspace` per
direction in, one `.nxs` `NXentry` out.

**Required PyRS changes:**
- Add a settable `direction` `@property` to `HidraWorkspace`
  (`pyrs/core/workspaces.py`) — needed because 04b resolves discriminator
  values from the workspace object itself (a matching property, else a
  `SampleLogs` fallback), and `HidraWorkspace` had no notion of direction;
  the viewer previously tracked it only at the model level
  (`filenames_11/22/33`). This also required a correction to 04b's own
  resolver — see the Decisions Log update below.
- Resolve any `NotImplementedError` in `pyrs/dataobjects/fields.py`
  (L239, 611, 816, 927, 956, 960, 964, 983, 986, 994, 1184) that falls on the
  StressField reconstruction read path.

**Required NXstress extensions:**
- Confirm `direction: str` (`"11"`/`"22"`/`"33"`) composes correctly with
  04b's discriminator mechanism; no new `PeakIndex` machinery is built here.
- Update the default `pyrs/config/pyrs.default.yml`'s
  `nxstress.discriminator_fields` from `[]` to `["direction"]`;
  `save_as_nxstress` validates this key is set correctly before calling
  `write()`, raising a clear error otherwise.
- Wire NXstress into `strainstressviewer/model.py::load_hidra_project_file` /
  `load_hidra_project_files` — read a direction-indexed NXstress file and
  reconstruct `StrainField` / `StressField` in the viewer.
- Add a `Save as NXstress…` action on the StrainStressViewer.
- Round-trip test: construct a `StressField` from a single NXstress file,
  confirm it matches the CSV-summary output for the same inputs.

---

### Phase 4 — ManualReductionViewer hookup

**Goal:** Wire NXstress into `reduce_hidra_workflow`'s existing, automatic
save step.

**Required PyRS changes:** _none._ Earlier drafts of this phase listed
implementing `HB2BReductionManager.save_project` as a prerequisite — that
was based on the wrong class name (the real class is `ReductionController`)
and the wrong hookup point: `save_project` has zero callers anywhere in the
codebase, so it was never blocking anything. The real, currently-functional
save path is `reduce_hidra_workflow`'s automatic
`ReductionApp.save_diffraction_data` call, which already works today and
needs no PyRS-side prerequisite. (`save_project`, and the two unrelated
`nexus_conversion.py:118,374` input-parsing `NotImplementedError`s, remain
an independent, optional PyRS cleanup item — spec 06 — not scheduled in
this plan.)

**Required NXstress extensions:**
- Wire NXstress into `reduce_hidra_workflow`
  (`pyrs/interface/manual_reduction/pyrs_api.py`): write once per
  currently-enabled format (`legacy_io.enable` → `.h5` via the existing
  `reducer.save_diffraction_data` call; `nxstress.enable` → `.nxs` via
  `NXstress(path, "w").write(hidra_ws, [])`), same basename for both when
  both are enabled. No new GUI dialog or menu action — this viewer has none
  to extend. An explicit `project_file_name`'s extension, if given, is
  stripped and ignored; only its basename is used.
- Round-trip test: reduce a run with each enablement combination
  (NXstress-only, both, legacy-only) and confirm the expected file(s) are
  written and readable.

---

### Phase 5 — Reconstructed fit spectrum + detector-calibration fidelity

**Goal:** Replace the remaining `NaN` placeholders with real data — except
`STRESS_FIELD`, which stays a documented, investigated-but-blocked gap
(see Decisions Log item 14; no dataset anywhere in the repo contains what's
needed, and this cannot be resolved without new information from the
instrument-science team).

**Required PyRS changes:**
- Fit engine (`pyrs/peaks/peak_collection.py`,
  `pyrs/core/peak_profile_utility.py`): add a method that returns the
  reconstructed model spectrum on the original two-theta grid, indexed by
  `PeakCollection` × mask × scan_point, built on the underlying peak-shape/
  background evaluator functions directly — the one existing wrapper
  (`calculate_profile`) is dead, buggy code, not a usable starting point.
  Propagated variance is a documented approximation (no covariance matrix
  exists anywhere in PyRS). This is the largest single PyRS-side item in
  the plan.
- Extend `PeakCollection.__set_fit_status` so an unrepresentable parameter
  error also sets `_exclude_list`, unifying "no representable variance"
  with the existing exclusion mechanism.
- Fix `DENEXDetectorGeometry` (`pyrs/core/instrument_geometry.py`): store
  the `calibrated` flag it already accepts but discards; add an
  `arm_shift_applied` accessor; fix `apply_shift`'s existing
  class-vs-instance `AttributeError` bug; retain the pre-shift arm-length
  value so it's recoverable after a shift is applied. (Not
  `file_object.py:510` — that FIXME doesn't exist; the gap is entirely
  within this class.)
- Add a `beam_intensity_profile` property (get/set) to `HidraWorkspace`,
  defaulting to a documented uniform/constant value — no real
  beam-intensity data path exists anywhere in PyRS today.
- `STRESS_FIELD` shape verification: **blocked**, not scheduled to
  complete in this phase. Investigated directly; no usable example dataset
  exists in the repo.

**Required NXstress extensions:**
- Populate `_fit.py:425-429,430-438` diffractogram `fit` / `fit_errors` from
  the new fit-engine method — these fields are zero-sized resizable
  datasets, so the writer must resize them to the real shape first, not
  index-assign into a pre-shaped array.
- Change `_Diffractogram.diffractogramFromNexus`'s return from a plain
  4-tuple to a `NamedTuple` (`DiffractogramData`, six fields including
  `fit`/`fit_errors`); update its one caller (`NXstress.py:218`) to match.
- Populate `NXbeam` intensity profile in `_instrument.py:126` (construction;
  TODO at `:127`) by reading `HidraWorkspace.beam_intensity_profile`
  unconditionally — no "if measured" branch; the property always has a
  value.
- Fix the L2 arm-shift round-trip in `_instrument.py:132-150` (the
  calibrated/uncalibrated branch; TODO + `distance = arm_length` at
  `:138-140`) using the new `DENEXDetectorGeometry` accessors — the
  double-counting risk this item previously worried about is already
  resolved at the source (PyRS-side), so this is a plain consumer update.
  Reader side (`instrumentFromNexus`): must read the new
  `arm_shift_applied` flag and use it to decide whether to call
  `apply_shift` or use the raw arm-length value directly, or a round-trip
  will double-shift or under-shift.
- `_sample.py:107` `STRESS_FIELD` dimensions: **not touched** — remains
  blocked, carried forward from the PyRS-side item above.

---

### Phase 6 — Flip defaults (NXstress becomes primary)

**Goal:** Complete the phased-replacement decision. Acceptance criteria for
triggering this phase to be defined at the end of Phase 1.

**Required PyRS changes:** _none._

**Required NXstress extensions:**
- Set `legacy_io.enable = false` and `nxstress.use_production_names = true`
  as the defaults in `pyrs/config/pyrs.default.yml` (`nxstress.enable`
  stays `true`, already the Phase 1 default). **No viewer code changes** —
  every wired viewer's save actions already read these flags directly
  (specs 02, 03, 05, 07), so flipping the shipped default is sufficient to
  demote `HidraProjectFile` save paths to disabled-by-default (loading
  remains unaffected, still works).
- Write deprecation-warning docs and a migration note for existing users
  with `.h5` project files, including how to re-enable `.h5` saving via a
  personal `~/.config/pyrs/config.yml` override if still needed.

---

### Skipped

**DetectorCalibrationViewer** — its outputs (calibration JSON, Mantid NeXus
event files) are independent of the NXstress project-file layout. No NXstress
hookup is planned unless a downstream requirement emerges.

---

## 4. Decisions Log

| # | Question | Decision | Notes |
|---|---|---|---|
| 1 | File-extension policy | **New `*.nxs` filter** across every viewer; NXstress writes to `.nxs`, coexisting with existing `*.h5` `HidraProjectFile` paths. | No auto-detection needed; extension is imposed by the action clicked, never typed by the user. Config keys: `nxstress.extension`, `legacy_io.extension` (superseding the earlier single `nxstress.default_extension` key). |
| 2 | Coexistence vs. replacement | **Additive now, replace later (phased).** Keep existing `HidraProjectFile` save/load unchanged in Phase 1; add NXstress as new menu entries and file-dialog filters, each independently enabled per `nxstress.enable`/`legacy_io.enable`. Phase 6 flips defaults so NXstress is primary and `HidraProjectFile` becomes legacy-read-only — **purely a config-default flip** (`legacy_io.enable: true` → `false`), no viewer code changes, since the enablement wiring was already built once, per-viewer, in Phase 1/3/4. | Phase-6 trigger criteria to be defined at the end of Phase 1 (still open — `open-questions/10-flip-defaults.md` Q1). |
| 3 | StressField / multi-direction persistence | **Decided:** `direction` is one discriminator field of the general multi-workspace mechanism built in spec 04b (item 6 below) — one `HidraWorkspace` per direction in, one `.nxs` `NXentry` out. `StressField` is reconstructed in the viewer from the indexed peaks at read time. | Supersedes the earlier provisional framing (a StrainStress-specific `direction` axis). The schema question this depends on is downgraded from a blocking gate to a tracked follow-up — see `open-questions/04b-multi-workspace-nxstress.md` Q1 for the precedent (`_peaks.py` already writes non-required columns) and the pending validator cross-check. |
| 4 | NaN placeholder tolerance | **`NaN` is acceptable for Phase 1.** No NXstress TODO is a Phase-1 blocker. Every TODO in Sections 2.1 and 2.2 is scheduled across Phases 2–5. | The phased schedule (Section 3) is the deliverable of this decision. |
| 5 | Priority ordering | **Keep drafted order.** Phase 1 hooks up PeakFitting, Texture, and CombineRuns (data model matches `NXstress.write` 1:1, zero upstream changes). StrainStressViewer comes in Phase 3, after Phase 2 stabilizes NXstress internals and after the 04b multi-workspace mechanism lands. | Ship something quickly, learn from real use, then tackle the harder integration. |
| 6 | Multi-workspace I/O & round-trip symmetry | **Decided:** `NXstress.write`/`read` generalize to `list[HidraWorkspace]`, round-trip symmetric — `read` recovers the same N workspaces `write` was given. Workspace boundaries are recovered from discriminator field(s) named by the new `nxstress.discriminator_fields` config key, resolved per workspace via a property-or-`SampleLogs`-fallback resolver and carried name-keyed (not positionally); the specific field names any deployment configures are decided at spec 04b's implementation kickoff, not here. | New capability, not in the original plan. Spec: [04b](04b-multi-workspace-nxstress.md). Assumes the existing no-overlap invariant (each input workspace contributes only unique scan points and/or other index fields); 04b adds an explicit write-time check for it, and raises on N>1 with no discriminator fields configured unless `nxstress.merge_workspaces` opts into merging instead. No new `HidraWorkspace` method — resolution logic is NXstress-internal. |
| 7 | Append mode scope | **Decided:** append ships as a tested library capability (`NXstress(path, "a")`) with **no GUI entry point** in this pass. The ManualReductionViewer hookup (spec 07) always writes a fresh file instead, so it no longer depends on append. | New capability, not in the original plan; also un-bundles what was previously one spec (append + ManualReduction). Spec: [04c](04c-nxstress-append.md). |
| 8 | Append architecture & scope | **Decided:** append resizes/inserts directly against on-disk arrays (no round-trip through `HidraWorkspace`/`PeakCollection` for the existing entry); covers both position-aligned families — peak-index (peaks + peak_parameters + background_parameters) and scan-point (detector_counts + sample logs + diffractogram) — not just the originally-scoped `_input_data.py`/`_peaks.py` pair. `NXstress(path, "a")` targets the last entry by default, with `entry_number` as an explicit override. Overlap conflicts raise `RuntimeError` and invalidate the instance for further writes. | Spec: [04c](04c-nxstress-append.md). Corrects an under-scoped original draft: `_fit.py::_PeakParameters`/`_BackgroundParameters` build rows in the same sort order as the peaks index (`_fit.py:87`), so a partial append would desynchronize the entry. |
| 9 | `direction` storage & config default | **Decided:** `HidraWorkspace` gains a settable `direction` `@property` (get/set) — `HidraWorkspace` previously had no notion of direction at all; the viewer tracked it only at the model level (`filenames_11/22/33`), which doesn't fit 04b's workspace-resolved discriminator mechanism. 04b's discriminator resolver is corrected to be bidirectional: "get" from the workspace at write time (as before), "set" onto each reconstructed workspace at read time (new) — so any property-backed discriminator round-trips with no NXstress-side special-casing. `pyrs/config/pyrs.default.yml`'s `nxstress.discriminator_fields` default changes from `[]` to `["direction"]`; `save_as_nxstress` validates this precondition and raises a clear error if unmet. | Spec: [05](05-strain-stress-viewer.md); the resolver correction lands in [04b](04b-multi-workspace-nxstress.md). |
| 10 | CombineRuns keeps its pre-merge | **Decided:** spec 03's `.nxs` export path does **not** switch to 04b's N-workspace mechanism. `HidraWorkspace.append_hidra_project` (used by `combine_project_files`) already discards per-run boundaries the same way `nxstress.merge_workspaces: true` would — same resulting semantics, already implemented at the PyRS layer. The existing `.h5` export path still needs the single merged workspace regardless, so switching only `.nxs` would mean two data paths through `CombineRunsModel` for an identical output file. The `.nxs` branch passes the already-merged workspace as a length-1 list: `NXstress.write([self._hidra_ws], [])`. No `discriminator_fields`/`merge_workspaces` config is touched by this spec. | Spec: [03](03-combine-runs-nxstress.md). Retires `open-questions/04b-multi-workspace-nxstress.md` Q3, which had floated this as a possible simplification. |
| 11 | Config schema: two independent format sections | **Decided:** replaces the single `nxstress.default_extension` key with two fully parallel, self-contained top-level sections — `nxstress` and `legacy_io` — each owning its own `enable` flag and its own `extension`. Each viewer's save action reads its own format's `enable` to decide whether it's clickable (`setEnabled`, never `setVisible` — the action stays visible, grayed out when disabled), and each action *imposes* its own format's `extension` on whatever a user types, rather than accepting a user-chosen extension. `load_config()` raises if neither format is enabled. No single GUI action ever auto-writes both formats — a user with both enabled invokes the two independent actions manually, one at a time. | Spec: [01](01-config-and-test-infra.md). Two earlier framings were tried and corrected first: an `output_mode` enum where "both" meant one action auto-writing two formats (rejected — bad UI design); a single `mode` enum plus one shared `default_extension` (rejected — doesn't make sense once two independently-enabled formats each need their own extension). |
| 12 | ManualReductionViewer: automatic write, not a GUI action | **Decided:** `reduce_hidra_workflow` has no button click to protect the meaning of (it saves automatically, as an inherent side effect of every reduction) — so the "never auto-write both formats" rule from item 11 does not apply to it. It simply writes once per currently-enabled format: one file if only one is enabled, both files (same basename) if both are. No tie-break, no ambiguity. An explicit caller-supplied `project_file_name`'s extension is stripped and ignored — never validated against, never a reason to raise; only its basename is used, exactly as for the auto-derived case. | Spec: [07](07-manual-reduction-nxstress.md). Considered and explicitly deferred: giving this viewer a real Save/Save-As action, and a shared `Viewer` ABC across all five viewers — legitimate future architecture work, but a workflow change unrelated to NXstress, not entangled with this rollout. |
| 13 | Specs 06/07 decoupled; spec 07 hookup point corrected | **Decided:** spec 07 does not depend on spec 06 at all. Tracing the actual code found two errors in the original drafts: the class is `ReductionController`, not `HB2BReductionManager` (an unrelated class in `pyrs/core/reduction_manager.py`); and `ReductionController.save_project` — spec 06's target — has **zero callers anywhere in the codebase**, so implementing it unblocks nothing. The real, currently-functional save path is `reduce_hidra_workflow`'s automatic `ReductionApp.save_diffraction_data` call, which spec 07 now hooks into directly. Spec 06's other item (`nexus_conversion.py:118,374`) is also confirmed unrelated — both branches are on the NeXus-*conversion* step, not the save path. | Specs: [06](06-manual-reduction-prereqs.md) (re-scoped to an independent, optional PyRS cleanup item, not scheduled in this plan's phases), [07](07-manual-reduction-nxstress.md). |
| 14 | Spec 08 corrected: calibration fix scope, beam-profile mechanism, STRESS_FIELD blocked | **Decided, three parts.** (a) The `file_object.py:510` FIXME cited in the original draft doesn't exist there — the real gap is entirely within `DENEXDetectorGeometry` (discards its `calibrated` arg; `apply_shift` is dead code that would raise `AttributeError` if called; destructively overwrites `arm_length` with no way to recover the pre-shift value). Fix stays scoped to that class + NXstress; **no `.h5` format change** in this pass — explicitly flagged as a strong future need, not dropped. (b) No beam-intensity data path exists anywhere in PyRS (confirmed); rather than NXstress hardcoding a uniform placeholder, `HidraWorkspace` gains a `beam_intensity_profile` property (`direction`-style convention) that NXstress reads unconditionally — forward-compatible with a future real beam-monitor path for free. (c) `STRESS_FIELD` shape verification is **blocked, not resolved** — the three example files a stakeholder named are real but contain no `STRESS_FIELD` log, only an unrelated `StrainDirection` label; strain and stress are physically distinct quantities, so that label is not a valid substitute. Documented as an explicit, tracked blocker rather than guessed at. | Specs: [08](08-fit-spectrum-prereqs.md), [09](09-fit-spectrum-nxstress.md) (carries the `STRESS_FIELD` block forward; the other three items proceed normally). |
| 15 | Spec 09 corrected: line numbers, `NamedTuple` return, concrete reader scope | **Decided, three parts.** (a) Cited line numbers in the original draft were imprecise (off by a few; one citation pointed at an unrelated docstring note) — corrected against the current code. (b) `diffractogramFromNexus`'s return type changes from a plain (and now-growing) positional tuple to a `NamedTuple` (`DiffractogramData`) — self-documenting, avoids positional ambiguity as more fields are added; its one existing caller (`NXstress.py:218`) is updated to match. (c) `instrumentFromNexus`'s reader-side scope, previously vague ("update... correspondingly"), is now concrete: it must read the new `arm_shift_applied` flag and use it to decide whether to call `apply_shift` or use the raw arm-length value, or a round-trip double-shifts. Also confirmed as a simplification: `_Diffractogram.init_group`'s `peakss` parameter already exists, unused — no new parameter needed. | Spec: [09](09-fit-spectrum-nxstress.md). |
| 16 | Spec 10 corrected: status-bar UI gap, validator/schema-doc unavailability | **Decided, two parts.** (a) Only `PeakFittingViewer` has a status bar today — `TextureFittingViewer`, `CombineRunsViewer`, and `StrainStressViewer` have none, only modal dialogs. Spec 10 now explicitly adds a status bar to the three that lack one (cheap — `self.statusBar()` creates it lazily), for consistent non-blocking deprecation-hint UX across all four; this is the one piece of genuinely new UI in an otherwise pure config-flip spec. `StrainStressViewer`'s one-time hint flag must live at the window level, since its three direction slots share one load handler. (b) The `nexusformat`-org NXstress validator and the `NXstress.xml`/`.html` schema doc — referenced in specs 02's, 09's, and 10's Verification sections since spec 04b's open questions — are confirmed **not yet added to the repo**; the installed `nexusformat` 1.0.8 package has no validator capability at all. A reminder is added to spec 10's Overview to add both (the validator as a link to its separate repository; the schema doc under `docs/developer/source/design/nexus/`, linked from that directory's `IO_prototype.rst`) — not fabricated in this planning pass. | Specs: [02](02-peak-and-texture-nxstress.md), [09](09-fit-spectrum-nxstress.md), [10](10-flip-defaults.md). |

---

## 5. Files to be Modified

| Phase | PyRS files | NXstress / GUI files |
|---|---|---|
| 1 | _(none)_ | `pyrs/utilities/config.py` (new), `pyrs/config/pyrs.default.yml` (new), `pyproject.toml` (add `pyyaml`), `scripts/pyrsplot.py`, `scripts/pyrs_calibration.py`, `scripts/create_mask.py`, `pyrs/interface/peak_fitting/{peak_fitting_viewer,peak_fitting_model}.py`, `pyrs/interface/texture_fitting/{texture_fitting_viewer,model}.py`, `pyrs/interface/combine_runs/{combine_runs_viewer,combine_runs_model}.py` |
| 2 | `pyrs/projectfile/file_object.py` (audit legacy log names) | `pyrs/utilities/NXstress/{_peaks,_fit,_definitions,_instrument}.py`, `pyrs/config/pyrs.default.yml` |
| 2/3 (04b) | _(none)_ | `pyrs/utilities/NXstress/{NXstress,_peaks,_input_data,_sample,_instrument,_fit}.py`, `pyrs/config/pyrs.default.yml` (new keys: `discriminator_fields`, `merge_workspaces`); call-site updates in `pyrs/interface/{peak_fitting,texture_fitting,combine_runs}/…` |
| 3 (04c) | _(none)_ | `pyrs/utilities/NXstress/{NXstress,_input_data,_sample,_fit,_peaks}.py` — library only, no GUI files |
| 3 (05) | `pyrs/core/workspaces.py` (new `direction` property), `pyrs/dataobjects/fields.py` | `pyrs/utilities/NXstress/_peaks.py` (StrainStress-specific tests only), `pyrs/config/pyrs.default.yml` (discriminator_fields default), `pyrs/interface/strainstressviewer/{strain_stress_view,model}.py` |
| 4 | _(none — see item 13 in the Decisions Log)_ | `pyrs/interface/manual_reduction/pyrs_api.py` (`reduce_hidra_workflow`) |
| 5 | `pyrs/peaks/peak_collection.py`, `pyrs/core/{peak_profile_utility,instrument_geometry,workspaces}.py` (`STRESS_FIELD`/`file_object.py`: blocked, not touched) | `pyrs/utilities/NXstress/{_fit,_instrument}.py` (`_sample.py`: blocked, not touched) |
| 6 | _(none)_ | `pyrs/config/pyrs.default.yml` only — no viewer files; every wired viewer already reads `nxstress.enable`/`legacy_io.enable` directly |

Tests to extend/add:
- `tests/unit/pyrs/utilities/NXstress/*` (existing suite — extend each phase).
- `tests/ui/test_nxstress_roundtrip.py` (new — GUI-level round-trips).
- `tests/integration/test_nxstress_append.py` (new in spec 04c — library-only
  append round-trip; no GUI involved).
- `tests/integration/test_nxstress_reduction.py` (new in Phase 4 — manual
  reduction, fresh-write only).

---

## 6. Verification

- **Round-trip pytest** — for each viewer connected, load an existing
  `HidraProjectFile`, do the workflow, save as NXstress, reload from NXstress,
  assert equality of `HidraWorkspace` and `list[PeakCollection]`.
- **Schema validation** — run each written file through the NXstress validator
  (via `nexusformat`) with `nxstress.use_production_names = true` once the
  upstream validator bug is resolved (Phase 2).
- **GUI smoke test** — launch each affected viewer via `pyrsplot`, exercise the
  new save/load actions, confirm no regressions in existing `HidraProjectFile`
  workflows.
- **Demo script** — keep `tests/scripts/cis_tests/NXstress_demo_script.py`
  passing and update it to reflect current usage after each phase.
