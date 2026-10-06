# PR review — subspec 04 (NXstress internal cleanup)

Review of `eb5457b1..cda22352`, per
[`plans/PR-review-process/review-process.md`](../PR-review-process/review-process.md).

Each entry: the comment, the agreed resolution, and the change actually made.
My summaries of the diff are not recorded (§6e); defects I flagged are, whether or
not they were acted on.

---

## Batch 1 — `pyrs/utilities/NXstress/_definitions.py`

`_definitions.py` carries work from both `04` (the identifier policy and the mask-key
correspondence) and `04c` (the growth helpers). Per the process document §4, the batch
is split across documents by which subspec's change is under discussion: the
`allowed_identifier` exchange is here, and `D1`–`D3` on `growable`/`tail_append` are in
[`04c-comments.md`](04c-comments.md).

### Reviewer question — how is a literal `__` encoded?

Answered in full in [`04c-comments.md`](04c-comments.md) (kept together with the rest
of that exchange rather than duplicated). Summary: `__` encodes to `__5F_` and
round-trips exactly; the durable point is that *n* consecutive underscores expand
~2.5×, which interacts with the 63-character `MAX_IDENTIFIER_LENGTH` cap. No real log
name triggers it, and the failure is loud. **No change.**

### No defects flagged against `04`'s part of this file

The identifier encoding was checked rather than read: all three docstring examples
produce exactly what they claim, and the encoding is **injective and round-trips over
7380 adversarial inputs** drawn from `_ . : a A 0 u $` and space at lengths 1–4, with
every output matching `VALID_ITEM_NAME` and fitting the 63-character cap.

Worth recording one non-obvious property the correctness rests on, because it reads
like an optimisation and is not: a literal `_` is emitted only when the next character
is neither `_` nor illegal, so **two literal underscores are never adjacent in the
output** and a literal `_` never precedes an escape. Without that one-character
lookahead, `_` followed by `:` would encode to `___3A` and the decoder would attempt
`int("_3", 16)`.
