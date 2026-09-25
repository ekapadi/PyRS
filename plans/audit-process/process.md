# What a complete audit consists of

**Status:** proposal, written 2026-09-12 during subspec `01`'s implementation.
**Scope:** the `math-verification` plan series, but nothing here is
math-specific — the intent is that the definition in §4 migrates to
`CLAUDE.md` once it has been exercised on the rest of this series.

---

## 1. Why this document exists

The current planning process is four steps:

> **I.** Generate an overview implementation plan (no codebase awareness).
> **II.** Match the plan to the codebase; extend where necessary.
> **III.** Break the plan into PR-sized subspecs against a shared `README.md`.
> **IV.** Audit the plan repeatedly, against the codebase, until consistent.

Step IV has been run **five times** over this series. It still shipped
subspecs whose implementation then cost weeks of bug-fixing (`00a`–`00g`), and
subspec `01` — the smallest, lowest-risk document in the set, explicitly rated
*"low risk: types only, no behaviour"* — was found on first implementation to
contain six blocking defects.

The problem is not diligence. It is that **every artifact the process produces
is prose, and every check it runs is a human reading prose.** A reader cannot
detect that `sympy.Eq(x, 1)` is not an `Expr`, and re-reading a true-when-written
sentence produces agreement, not detection.

This document sorts the observed failures into classes, defines what an audit
would have to cover to catch each class, and proposes mechanisms.

---

## 2. The evidence

Concrete defects from this series, with what it would actually have taken to
find each one.

### 2.1 The one with no excuse

`01` §5 asserted: *"The original draft's `[PLAN-AGENT]` asked whether an
existing `Result`-like envelope already exists in the tool layer to extend
rather than nest inside. **None does.**"*

By the time `01` was implemented this was false. `00b` had established a
codebase-wide tool-return contract: a shared status vocabulary
(`RAISING_STATUSES`), a shared policy function (`raise_if_error_status`), and
generic enforcement in `@sandboxed_tool`'s wrapper, which inspects **any**
returned envelope for a `status` key and warns when one is missing.

The git history:

| when | what |
|---|---|
| 2026-09-05 | `18bbc5f` — "subspec 00b" lands `src/tools/errors.py` |
| 2026-09-05 | `c9d4b71` — **"PR comment: update docs for `timeout_as_error` implementation"** edits `01-core-types.md` |

That edit was made *specifically to reflect 00b*, and it updated §5's **Rules**
subsection — which now cites `00b` five times — while leaving the
extend-vs-nest paragraph **twenty lines above it, in the same section**,
asserting the opposite. Four subsequent audit passes read past the
contradiction.

**This was not hard to find.** It required only reading one section against
itself. That is the axis nobody was asked to check (§3, Class C).

### 2.2 The ones that reading could never have found

- `parse_expr` with a curated `global_dict` still evaluates
  `S('(1).__class__')` to a live Python class, because an applied function
  sympifies its string argument.
- If `global_dict` has no `"__builtins__"` key, `eval` **injects the real
  builtins into it**.
- `Eq(x, 1)` and `x < 1` are `Basic` but **not** `Expr`; a mutable `Matrix` is
  neither. `01` §4 specified `-> sympy.Expr`, which would have rejected three
  shapes its own §11 required.
- `x and y` parses to `y`; `x if 1 else 2` parses to `x`. Silent, and exactly
  the failure mode README P6 exists to prevent.
- `Symbol('q', foo=True)` constructs happily and compares **unequal** to
  `Symbol('q')` — sympy silently accepts a typo'd assumption.
- `Result` had no `message` field, so a failing `Result` reached the calling
  LLM as `[error] verify_equivalence failed`, with the reason discarded — the
  shared wrapper reads `parsed.get("message")` first.

Every one required **executing** something. None is visible in any document.

### 2.3 Still live, and doc-vs-doc

`03` gives two different paths for the same file: §4.2 says
`src/tools/math_verification/backend.py`, §8's table says
`src/math_kernel/backend.py`. The first-pass audit's note for `03` reads
*"guard-rail logic and config shape are new and self-consistent; **no existing
file to conflict with**, confirmed"* — i.e. "self-consistent" was assessed as
*against the codebase*, not against the document.

---

## 3. The three failure classes

**Class A — staleness.** A document asserts a codebase fact. A later PR *in
the same series* falsifies it. Nothing links the two.
> Repeated auditing makes this **worse, not better**: each pass re-reads the
> same sentence, finds it plausible, and re-confirms it. Confidence rises while
> correctness falls. §2.1 is Class A compounded by Class C.

**Class B — unexecutable claims.** Assertions about third-party library
behaviour, or about how another module treats our output at runtime.
> Unfixable by review, at any level of care. §2.2 is entirely this class, and
> it is the likeliest explanation for the `00a`–`00g` weeks: these defects
> surface at first execution because that is the only place they *can*.

**Class C — intra-document contradiction.** A document disagreeing with
itself.
> Cheap to catch, and consistently missed, because every audit instruction so
> far has pointed *outward* — at the codebase, or at the initial specification.

---

## 4. Definition of a complete audit

An audit is complete when **all seven axes** below have been covered, with the
stated evidence. Anything less is a partial audit and should be recorded as
such rather than reported as "consistent".

| # | Axis | Question | Evidence required |
|---|---|---|---|
| **A1** | Doc ↔ self | Does every prose claim agree with every code block, table and cross-reference *in the same document*? | Section-by-section pass; each `§N` cross-reference resolved |
| **A2** | Doc ↔ siblings | Do shared types, file paths, vocabularies and dependency ordering agree across subspecs? | Each shared name traced to exactly one owning document |
| **A3** | Doc ↔ codebase | Does every cited file, symbol and line range exist and say what is claimed? | The citation opened and read, not recalled |
| **A4** | Doc ↔ library | Is every claim about third-party behaviour true *of the installed version*? | A committed probe; its real output pasted into the doc |
| **A5** | Doc ↔ runtime contract | Will another module actually treat our output the way we assume? | A probe that feeds a representative payload through that module's real code path |
| **A6** | Doc ↔ earlier draft | Where the grounded plan diverges from the initial specification, is the divergence acknowledged and justified? | Divergence listed with rationale |
| **A7** | Freshness | Are the claims true *now*, given everything that has landed since they were written? | Re-verification dated later than the most recent landed PR the doc depends on |

The process so far has covered **A2, A3 and A6**. Every defect in §2 falls in
A1, A4, A5 or A7.

### 4.1 Anti-patterns — things that look like auditing and are not

- **Re-reading a claim and finding it plausible.** Plausibility is what a
  stale claim has in abundance. A claim is verified when it has been *checked
  against its referent*, not when it has been re-read.
- **Checking a grounded doc against the initial specification.** This
  confirms faithful transcription. `01` §4's codec contract was carried
  verbatim from `initial-specification/01-core-types.md:112-122`, so checking
  it against the initial spec *confirmed the contradiction*.
- **Treating `*Spec-ahead*` as exempt.** The label means "unverified", which
  readers convert to "not worth checking yet". Both of `01` §12's defects lived
  entirely inside its spec-ahead block. A spec-ahead section is exempt from
  **A4/A5** (nothing is built yet); it is **not** exempt from **A1**.
- **Assessing "self-consistent" as "does not conflict with the codebase."**
  The `03` note in §2.3 is the worked example.
- **Counting audit passes.** Five passes over three axes is three axes covered,
  not fifteen.

---

## 5. Mechanisms

Ordered by leverage per unit of effort. Each attacks a named class.

### 5.1 Convert audit findings into executable checks — not paragraphs
*(Class A, permanently)*

**This repo has already invented the mechanism three times, ad hoc:**

| existing test | what it pins |
|---|---|
| `tests/sandbox/test_injected_state_api.py` | a third-party API surface (`InjectedState.field`), with the version pinned in both manifests and the test named in the pin comment |
| `tests/api/test_at_escape_logging.py::test_every_written_role_has_an_inspector_badge` | a documented convention, by scanning source for `log_event(role=...)` literals |
| `tests/api/test_static_assets_clean.py` | a file-content invariant (no NUL bytes) |

Make it the default rather than the exception: **an audit finding that can be
expressed as a test must be, and the prose becomes a comment on the test.**

The version already written for `01`:

```python
def test_result_status_covers_the_shared_raise_policy() -> None:
    # Imported from src/tools/errors.py, never copied as a literal, so the
    # two cannot drift.
    assert (RAISING_STATUSES | {"timeout"}) <= set(get_args(ResultStatus))
```

A paragraph describing that relationship is re-read by a human on each audit
pass. A test is re-checked on every commit.

### 5.2 A machine-checkable claims block per subspec
*(Class A + C)*

Every assertion a subspec makes *about the codebase* gets an executable form:

```yaml
# docs/plans/math-verification/claims/01.yml
- id: no-shared-result-model
  claim: "no base pydantic result envelope exists in src/tools/ to subclass"
  check: "! grep -rq 'class .*Result(BaseModel)' src/tools/"
  asserted: 2026-09-04
  section: "01 §5"
```

One `scripts/verify_plan_claims.py` runs every claim in the tree. The §2.1
defect would have gone **red on 2026-09-05**, the day `00b` landed, instead of
surviving four audits and being found by a reviewer a week later.

Claims that cannot be reduced to a command are exactly the Class B claims, and
are routed to §5.3.

### 5.3 Probe-before-audit for every Class B claim
*(Class B, moved from "weeks of implementation" to "minutes of probing")*

**Rule:** a subspec may not be marked audited if it asserts (a) third-party
library behaviour, or (b) how another module treats its output, without a
committed probe under `docs/plans/<series>/probes/` whose **real output is
pasted into the document**.

**A probe is not a "User verification" section, and this is not an extension of
that convention** — an earlier draft of this document said it was, which was
wrong. The two share exactly one thing: an evidentiary standard (run it, paste
the *real* output, never the predicted output). Otherwise:

| | User verification | Probe |
|---|---|---|
| Audience | the PR reviewer | the spec author / auditor |
| When | after implementation | before it, during the audit |
| Purpose | demonstrate the shipped thing works end to end | test whether a design assumption is true |
| Lives in | the subspec's own section | a probe file; output pasted at the claim |
| If it fails | the PR is not finished | the **spec** is wrong and the design must change |

That last row is the separation that matters. A failing user verification means
there is more work to do against an agreed design; a failing probe means the
document is describing something that does not exist, and the design changes.
Conflating them would put design-validation evidence in a section the reviewer
reads as a feature demo, and would delay it to after implementation — which is
precisely the cost this mechanism exists to avoid.

Cost is small and the payoff is immediate. The `Result`/`message` defect:

```python
# probes/result_vs_tool_wrapper.py -- ~10 lines
parsed = json.loads(Result(status="error").model_dump_json())
msg = (parsed.get("message")
       or (parsed.get("warnings") or [""])[0]
       or f"{tool_name} failed")
raise_if_error_status(parsed["status"], msg)
# -> ToolExecutionError: [error] verify_equivalence failed   <-- the defect
```

Ten minutes, a month earlier.

### 5.4 Cross-PR dependencies are imports, never sentences
*(Class A, for the cases that matter most)*

Where subspec *N* depends on module *M*'s behaviour, express the dependency as
a **test that imports *M***, not a paragraph describing *M*. Then a change to
*M* breaks *N*'s test rather than silently invalidating *N*'s prose.

Corollary for probes: reproduce the other module's logic **locally** in the
test (as `test_result_interoperates_with_the_shared_tool_return_contract`
does), so the test fails when that module's shape changes rather than silently
tracking it.

### 5.5 A landing trigger
*(Class A + A7)*

When any PR in a series lands:

```bash
git diff --name-only <merge-base>..HEAD          # files this PR touched
# ∩ files cited by each subspec  ->  subspecs needing re-audit
```

Mechanical, seconds to run, and precisely targets the claims that just went
stale. This is the missing link in §2.1: nothing connected "00b changed
`src/tools/errors.py`" to "`01` §5 makes a claim about `src/tools/`".

### 5.6 Stop treating "audited" as a terminal state
*(expectation-setting, not a mechanism)*

Audit can eliminate Class A and Class C. It **cannot** eliminate Class B. A
plan series should therefore budget a **doc-correction pass per PR** as normal
cost, not as an audit failure.

The `## Follow-up N` convention already does this; what is missing is the
expectation. The frustration of finding defects during implementation is
partly a mis-set expectation that step IV could have found them. For Class B,
it could not — but §5.3 moves most of that cost from *implementation* to
*probing*, which is an order of magnitude cheaper.

---

## 6. Recommended sequence for the remainder of this series

1. **Retroactive probe pass (§5.3) across `02`–`12`.** Front-loads the class
   that has been costing weeks. Parallelisable; the candidates are already
   identifiable from the documents:
   - `02` — `dill` round-trip of a live sympy namespace; kata sidecar envelope
     round-trip; fork-per-call wall-clock kill actually terminating a hung
     `10**10**10`.
   - `03` — `python-flint` availability and the `mpmath.iv` fallback; whether
     `lambdify` caching survives the way §6 assumes.
   - `04` — `pint` availability; unit-string round-trip.
   - `09a`/`09b` — `matplotlib` SVG output; the multimodal `image_url` message
     shape against the installed LangChain.
   - `10a` — `antlr4-python3-runtime` (confirmed **absent** today) and
     `parse_latex`'s real failure modes.
2. **Claims blocks (§5.2) for `02`–`12`**, then run them. The series is
   half-landed, so Class A staleness is now the dominant risk.
3. **A1 pass** over every subspec — each document against itself. Cheap, and
   it is the axis that has never been run. `03`'s two `backend.py` paths is a
   known open item.
4. Only then resume implementation.

---

## 6a. The toolkit, and how to apply it

*Added 2026-09-14, after §6's steps 1–3 were run over `02`–`12b`. §5 proposed
mechanisms; this section records the ones that were **built**, where they live,
and when to run them. It exists because the toolkit is now large enough that
keeping it in any one person's head — or any one session's context — is the
failure mode it was built to prevent.*

### 6a.1 What exists

| artifact | count | answers |
|---|---|---|
| `probes/a4_*.py`, `a4_env_solve.sh` | 10 | **A4** — is this claim about a third-party library true of the installed version? |
| `probes/a5_*.py` | 7 | **A5** — will another module in this repo actually treat our output this way? |
| `probes/README.md` | 1 | the index: one row per probe, naming the claims it tests, the subspecs at risk, and its verdict |
| `review/second-pass/landing_trigger.py` | 1 | **A7** — which cited paths did a landed PR disturb? |
| `review/second-pass/check_line_citations.py` | 1 | **A7** — what is *actually at* each cited line now? |
| `review/second-pass/check_section_refs.py` | 1 | **A1** — does every `§N` cross-reference resolve, in this document or the sibling it names? |
| `review/second-pass/check_ownership.py` | 1 | **A2** — is every file path created by exactly one document, modified only where something creates it, and cited only inside the citing document's dependency closure? |
| `review/second-pass/check_symbols.py` | 1 | **A3** — is every symbol cited beside a repo path actually in that file, and does every path cited as existing exist? |
| `review/second-pass/check_plan_agent_coverage.py` | 1 | **A6** — is every `[PLAN-AGENT]` question from the initial specification accounted for in the document that superseded it? |
| `review/second-pass/findings.md` | 1 | the narrative, with a 7 × 15 axis-coverage matrix |

**`probes/README.md`'s index is the entry point.** Read it before writing a new
probe — several claims are already covered, and a probe that re-tests a covered
claim is worse than none, because it implies the uncovered ones are covered too.

### 6a.2 Two interpreters, and why

- **`a5_*` run under `research-agent`.** They `import` from `src/`, so they must
  see the real, landed code. This is what makes them A5 rather than A4: they
  test the actual counterparty, not a model of it.
- **`a4_*` run under a disposable conda env** built by the recipe in
  `probes/README.md`, because they need the math stack `02` §9 *proposes adding*
  — `dill`, `pint`, `python-flint`, `lark`, `cairosvg` are in no environment
  this repo currently has. **That is the point:** an A4 probe tests what the
  environment *would* be, before the PR that creates it exists, which is the
  only way to find an environment defect before implementation pays for it.

**`env-research-agent.yml` is never modified by a probe.** `F-01` owns it, and
the whole series is sequenced so that file changes last.

### 6a.3 When to run what

| trigger | run | why |
|---|---|---|
| **A PR in this series lands** | `landing_trigger.py` **scoped to that PR** (its default), then `check_line_citations.py` | §5.5. Seconds, and it precisely targets the claims that just went stale. Scope matters: audit-wide it reports 92 flags across 285 files; scoped to one PR, a handful. Mechanical drift is fixed in the landing PR, a substantive claim gets a one-line re-check note appended to the affected subspec — see `prompts/implementation-prompt.md`. **Do not re-run the full audit between subspecs:** A1/A2/A6 are doc-internal and cannot go stale from a landing, and A4 moves only if dependencies do. |
| **About to assert third-party behaviour** | write an `a4_` probe | §5.3. Do not write the sentence first and probe later; the probe decides what the sentence says. |
| **About to assert how another module treats our output** | write an `a5_` probe | §5.3. |
| **A design decision is taken during an audit** | probe it *before* writing it into the subspec | `03` F1.9 and `10a` F1.5 were both probed before being written; `10a`'s first three candidate answers were all wrong and only executing showed it. |
| **Resuming this work in a new session** | `probes/README.md` index, then `findings.md` §0's matrix | the two together say what is covered, what is partial, and what has never been run. |

### 6a.4 Conventions for adding a probe

1. **Name it `a4_<cluster>.py` or `a5_<cluster>.py`** — the prefix is the
   interpreter *and* the axis.
2. **State the claims in the module docstring, verbatim, with their `§`
   references.** A probe whose purpose must be reconstructed from its output is
   a script, not evidence.
3. **Print the claim next to the real result.** Every probe here prints
   `doc says` / `file has`, or the claim text above the measurement, so the
   output can be pasted into a subspec and still make sense.
4. **Paste the real output into the subspec at the claim it supports** — never
   the predicted output, and never a summary of it.
5. **Add a row to `probes/README.md`'s index**, including the verdict.
6. **Supersede, don't delete.** When a probe's conclusion is overturned, keep
   it and say so in both files: `a4_parse_latex.py` is retained and marked
   superseded by `a4_latex_backends.py`, because `10a`'s Follow-up quotes its
   output and the record of what was believed must survive.
7. **Record a probe that produced a false finding, and how it was caught.**
   `a4_latex_backends.py` §7 does this at length. A toolkit that only records
   its successes teaches nothing about its failure modes.
8. **Assign its disposition in the same commit.** Per `CLAUDE.md`'s *"What
   happens to a probe when its PR lands"*: `promote` (→ unit or integration),
   `retire to record` (superseded but still quoted), or `stays a probe`
   (genuinely not a test — a solver check that takes minutes and hits the
   network). Name **both** the PR that makes promotion possible (usually the one
   declaring a dependency) and the PR that owns the invariant; they are often
   different. The table lives at the foot of `probes/README.md`.

   The corollary that matters: **do not write the promoted test during the
   audit.** An audit flags; the implementing PR writes. Six of the seventeen
   probes here are promotable today and are deliberately left alone, because
   none guards code that exists-and-is-violated — the one exception `CLAUDE.md`
   carves out. Writing them now produces tests with no subject.

### 6a.4a Reusing this toolkit for a different plan series

Every tool carries a block marked
`# --- series-specific: change all of these for a different plan series ---`.
Copy the directory, change what is under the marker, and the toolkit works on
any numbered plan series in `docs/plans/`. What is under it:

| constant | in | what it is |
|---|---|---|
| `PLANS` | all six | the series directory |
| `SUBSPECS` / `SLUGS` / `AUDITED` | all six | which documents are in scope |
| `INIT`, `SPLITS` | `check_plan_agent_coverage.py` | the pre-codebase draft, and which grounded doc superseded which part of it |
| `SERIES_BASE` | `landing_trigger.py` | the commit the series branched from |

**`SERIES_BASE` is the dangerous one, and it is the reason this section
exists.** Every other constant fails *loudly* on a new series — a wrong `PLANS`
finds no documents, a wrong `SLUGS` raises `StopIteration`. A stale
`SERIES_BASE` fails **silently**: `git diff` against an unrelated commit
succeeds, and the tool reports a plausible flag count computed over the wrong
range. It is therefore (a) documented at its definition with the commit's date
and subject, not just its hash, (b) used *only* by `--audit-wide` — every other
mode derives its range from the git history and needs no constant at all, and
(c) overridable as `--audit-wide=<sha>` so no one has to edit a file to check
a different range.

For the record, this series' base is **`9e2db92`** — the `math-tools` branch
point, *"Document ingestion: PR review pass"*, 2026-09-03.

### 6a.5 What these tools cannot do — stated so the gaps are not mistaken for coverage

- **`landing_trigger.py` flags citations, not claims.** It says a file moved
  under a citation; whether the surrounding prose is still true is A3.
- **It flags boilerplate.** The three header citations every subspec carries
  (`docker-compose-sandbox-v1.yml`, `env-research-agent.yml`, `pyproject.toml`)
  appear in all sixteen documents and assert nothing specific. 91 flags, far
  fewer real findings.
- **`check_line_citations.py` cannot see a *missing* citation** — a claim about
  code that cites nothing is invisible to it.
- **Nor can it see a citation that was "corrected" only in the log.** It checks
  that a `path:LINE` resolves, not that anyone acted on the finding. Found
  during `02`'s implementation (its Follow-up 5 F5.19): **six** A7 findings
  across the series say *"Corrected to `:N`"* while the body still cites the old
  number, `02` §3.2's own among them. The tool reports those as resolved,
  because they are — to the wrong code.

  **A `path:LINE` citation is the one thing an A7 Follow-up should fix in
  place.** The running-log convention exists so a Follow-up does not destroy the
  record of what was *believed*, which is right for a claim. A line number is not
  a belief, it is a pointer: leaving it stale sends the next implementer to the
  wrong code while reading as perfectly fine — the failure mode §5.5 exists to
  catch. Log the finding, and apply the number.
- **A symbol-existence check was tried and abandoned.** It returned 8 hits, 7 of
  which were the auditor's own list-curation error (symbols the subspecs
  *create*, and one that lives in sympy). It is not in the toolkit; the attempt
  is recorded in `findings.md` §2.4 so nobody rebuilds it expecting better.
- **`check_section_refs.py` covers only half of A1.** It resolves references;
  it cannot tell whether a section that *exists* says what the citing sentence
  claims. That stays a reading task, and `findings.md` §0's matrix marks A1 `~`
  on the eight documents where only the mechanical half was done.
- **It took three rounds of false positives to become trustworthy** — path-
  qualified references, prefix inheritance across commas/slashes/line breaks,
  and list items being referable (`README §P3`, `07 §9.1`). An earlier run
  flagged ~30 valid references as broken. A tool whose first output is wrong in
  a plausible-looking way is worse than no tool; budget for tuning it against
  known-good input before trusting a finding.
- **`check_ownership.py` covers paths, not names.** A path is the one shared
  name a tool can identify without parsing the documents' prose conventions;
  types, config keys and vocabularies are traced by reading, and `findings.md`
  §0's matrix marks A2 `~` where only the mechanical half was done.
- **It needed the same two fixes as its siblings** before it could be trusted:
  `Depends on:` **wraps across lines** in half these documents (a first-line
  regex produced a false ordering violation), and path citations carry `:LINE`
  suffixes that must be stripped before comparison (three false orphans). Every
  tool in this toolkit has required a tuning round against known-good input;
  budget for it.
- **`check_symbols.py` confirms containment, not correctness.** It answers "is
  this symbol in that file"; whether the surrounding sentence describes it
  correctly is a reading task. It is also blind to any symbol cited without a
  path beside it, which is many of them.
- **A3 and A7 are complements, not duplicates.** A7's landing trigger finds a
  stale citation *because a PR touched the file*; A3 finds it by asking whether
  the symbol is there at all. A rename by a PR that never touched the citing
  file is invisible to the first and caught by the second —
  `10c`'s `_build_initial_task_state` is the worked example, reached
  independently by both.
- **`check_plan_agent_coverage.py` is a shortlist generator, not an oracle.**
  A "match" means a distinctive token appeared somewhere in the superseding
  document — not that the question was answered well. Its value is the
  *unmatched* list, which is short enough to read.
- **All seven axes now have at least partial coverage.** What remains unrun is
  reading-depth, not axis coverage: `findings.md` §0's matrix records per
  document which half of each axis was mechanical and which was read.

### 6a.6 The self-check property, and a caution

`check_line_citations.py` resolves citations in the `Follow-up` sections too, so
the audit's own line numbers are checked by the same tool on the next run — the
count went from 33 to 54 once Pass 1 and Pass 2's findings were appended. This
is deliberate and worth preserving: an audit that cites line numbers is
generating exactly the artifact it exists to catch.

The caution: **a drifted line number does not imply a stale claim.** `11` §7
cited `nodes.py:126` for a `TODO(PR-05)` comment that is at `:128` — the number
is wrong and the claim is exactly right. Treating the two as equivalent will
either bury real defects in noise or manufacture false ones. Every drift in
`findings.md` §2.1 is recorded with *both* — where it moved to, and whether the
claim survived.

---

## 7. What should migrate to `CLAUDE.md`

Once §4 has been exercised on `02`–`04`:

- **§4's seven-axis table and §4.1's anti-patterns** — the definition of a
  complete audit. This is the core deliverable.
- **§5.3's probe rule**, stated as its own artifact with the
  probe-vs-User-verification table — *not* as an extension of the existing
  *User verification* convention, which has a different audience, timing and
  failure meaning.
- **§5.1's "findings become tests"** rule, citing the three existing
  precedents so it reads as codifying practice rather than inventing it.

Deliberately **not** for `CLAUDE.md` until proven: the claims-file format
(§5.2) and the landing trigger (§5.5). Both need one series' worth of use
before their real cost is known.

---

## 7a. Migration status, 2026-09-14

*§7 was written as a forecast. This records what actually happened, per the
running-log convention — §7 is left as written.*

### 7a.1 All three "should migrate" items have migrated

| §7 item | now lives at |
|---|---|
| §4's seven-axis table | `CLAUDE.md` — *"What a complete audit of a plan/subspec consists of"* |
| §4.1's anti-patterns | `CLAUDE.md` — *"Anti-patterns — things that look like auditing and are not"* |
| §5.3's probe rule + the probe-vs-User-verification table | `CLAUDE.md` — *"Probe before asserting (A4/A5)"* |
| §5.1's findings-become-tests | `CLAUDE.md` — *"Invariants belong in tests, not prose"* |

§5.6 also migrated, as *"'Audited' is not a terminal state"*.

§7 set the bar at "once §4 has been exercised on `02`–`04`". It has now been
exercised on **all of `02`–`12b`** for axes A4, A5 and A7, which is a stronger
warrant than the one asked for.

### 7a.2 §5.5's landing trigger: **proven — recommend migrating**

Built as `review/second-pass/landing_trigger.py` +
`check_line_citations.py`, run over the whole series, and it earned its place:
**15 of 33 line citations had drifted**, across 8 of 16 documents, none of which
five prior audit passes had noticed.

The case for migrating is one finding: `07` §2 cited `decorator.py:93-123` as
the `@sandboxed_tool` wrapper it hooks into. `git show 18bbc5f~1` confirms the
citation was **correct when written**; `00b` inserted a function above it and
moved `wrapper` to `:219`. The sentence is still true, the number is not, and
`:93-123` now lands on plausible, unrelated code. No re-read finds that. A
thirty-line script finds all fifteen.

Two qualifications to carry across with it, both learned by running it:

- It reports **locations, not claims**. `11` §7's `nodes.py:126` drifted to
  `:128` while its claim held exactly. Conflating the two buries real defects in
  noise.
- It flags **boilerplate**. 91 flags, of which the three per-document header
  citations are ~48 and assert nothing.

### 7a.3 §5.2's claims blocks: **not built, and deliberately so**

§5.2 proposed a hand-written `claims/<subspec>.yml` per document, each entry
pairing a prose claim with a `check:` shell command. It was not built, and the
recommendation is now **against** it rather than "not yet".

Building the alternative showed why: a claims file is a **second copy of the
document's assertions**, hand-maintained, and it drifts from the document
exactly the way the document drifts from the code — with nothing to catch it,
since nothing checks the claims file against the prose it paraphrases. That is
the original problem with one more place to keep in sync.

The tools in §6a avoid it by **deriving** what to check from the document's own
citations, so there is no second copy and nothing to maintain. What `claims/`
would have covered and the derived tools do not is the class of assertion that
cites nothing — and the answer to those is §5.1 (make it a test) or §5.3 (make
it a probe), both of which are now `CLAUDE.md` conventions.

### 7a.4 Cost, since §7 asked

- **17 probes + 2 tools**, one working session, all committed and re-runnable.
- The disposable conda env rebuilds in ~2 minutes from the recipe in
  `probes/README.md`; nothing in the toolkit depends on it persisting.
- Across A4, A5 and A7 the pass produced **five design-changing findings**
  (`03`'s `exact` backend, `10a`'s LaTeX backend, `07`'s question payload,
  `12b`'s evidence write path, `10c`'s vanished builder), roughly forty
  corrections, and twelve flagged invariants — against a series that had already
  been audited five times.

