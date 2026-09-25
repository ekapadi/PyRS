# Agent prompt — audit pass over subspecs `02`–`12b`

*Copy the block below into a fresh session. It assumes no prior context.*

---

We are adding a math-verification feature to our research-agent / coding-agent
application. The implementation specifications are in
`docs/plans/math-verification`. That directory holds a `README.md` overview
plus numbered subspecs, each corresponding to one planned PR, to be
implemented in numbered order. Subspecs `00a`–`00g` address defects and
oversights in the existing implementation and were prerequisites for `01`.

Implementation and testing through subspec `01` is complete. **Right now: all
unit and integration tests are passing; the application itself functions
correctly in normal usage.**

**Our current task is an audit pass over subspecs `02` through `12b`. Do not
implement any of them.** The deliverable is corrected specification documents
plus the evidence behind the corrections.

Read `CLAUDE.md`'s section **"What a complete audit of a plan/subspec consists
of"** first — it defines the seven axes an audit must cover and the
anti-patterns to avoid. Then read `docs/plans/math-verification/review/process.md`,
which records why that definition exists, the failure taxonomy behind it, and
the probe candidates already identified per subspec.

Context you need for calibration: this series has already been audited
repeatedly — its review log (`review/first-pass/findings.md`) records fifteen
rounds of follow-up findings. Despite that, subspec `01` — the smallest
document in the set, rated *"low risk: types only, no behaviour"* — was found
on first implementation to contain six blocking defects. Those earlier passes
covered three of the seven axes. **Assume the same is true of `02`–`12b`, and
that re-reading them the way they have already been re-read will find nothing.**

Work in this order, which is deliberately not the order the documents are in:

1. **A4/A5 probes first.** These are the defects that cost weeks, and reading
   cannot find them. Write and run a probe for every claim about third-party
   library behaviour or about how another module will treat our output. Paste
   the real observed output next to the claim. `process.md` §6 lists starting
   candidates per subspec — treat that list as incomplete, not exhaustive.
   Note that at least one is already known to be false: `10a` depends on
   `parse_latex`, and `antlr4-python3-runtime` is **absent** from this
   environment today.
2. **A7 freshness.** `00a`–`00g` and `01` have landed since these documents
   were written. For each subspec, check every claim it makes about files
   those PRs touched. Subspec `01` in particular moved five shared types into
   `src/tools/math_verification/types.py`; `03`, `05a`, `05b` and `06` were
   updated to import them, and anything else asserting where those types live
   is stale.
3. **A1 doc-against-self.** Every prose claim against every code block, table
   and cross-reference in the *same* document. This axis has never been run on
   this series. One finding is already known and unresolved: `03` gives two
   different paths for the same file — §4.2 says
   `src/tools/math_verification/backend.py`, §8's table says
   `src/math_kernel/backend.py`.
4. **A2 doc-against-siblings**, then **A3** and **A6** for anything the first
   three passes disturbed.

Deliverables:

- **Corrections applied to the subspecs themselves**, appended as
  `## Follow-up N` sections rather than rewritten in place, so the record of
  what was believed when survives.
- **Probes committed** under `docs/plans/math-verification/probes/`, with
  their real output pasted into the subspec at the claim each supports.
- **A findings document** at `review/second-pass/findings.md`, mirroring
  `review/first-pass/findings.md`. For each subspec, state explicitly which of
  the seven axes were covered and what each turned up — a partial audit must
  be reported as partial, not as "consistent".
- **Any invariant that can be a test should become one** rather than a
  paragraph, per `CLAUDE.md`. Flag these; do not add them to the test suite in
  this pass, since the code they would guard mostly does not exist yet.

Please start by reading `CLAUDE.md`'s audit section and `review/process.md`,
then propose a plan for the pass before beginning it.
