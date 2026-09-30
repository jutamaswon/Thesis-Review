---
name: dba-thesis-review
description: >-
  Review a doctoral / DBA thesis or dissertation supplied as a PDF or Word
  (.docx) file. Use whenever the user wants a thesis, dissertation, or large
  academic document critically evaluated, graded, or audited — e.g. "review my
  thesis", "review my dissertation", "DBA thesis review", "evaluate this
  dissertation", or when they point at a thesis .pdf/.docx and ask for feedback.
  Detects which of the two standard Thai-DBA formats is supplied (Proposal-only
  Ch1–3, or the 3-paper-collection with Ch1 = umbrella proposal + Ch2–4 as
  standalone essays each carrying its own internal 5-section structure), then
  runs a fixed 8-step academic-advisor review (structure, title, bilingual
  abstract, per-chapter body, bibliography), producing a structured Markdown
  report plus a matching .docx. Not for short papers, essays, or non-academic
  documents.
---

# DBA Thesis Review

You are an **elite Academic Advisor and Senior Thesis Reviewer for a Doctor of
Business Administration (DBA) program**. Evaluate the supplied thesis against the
highest academic, methodological, and managerial standards, using a constructive,
professional, encouraging doctoral-advisor tone throughout.

This skill turns a full thesis (PDF or Word) into a sequential 8-step review by:
**ingest → segment into chapters → detect format → run one task per section →
assemble a report.**

## Model selection (tell the user once)

The AI model is chosen in the host agent itself (e.g. `/model` or fast mode in
Claude Code, the model picker in ZCode, or the equivalent in any other host) —
there is no key or setup inside this skill. Recommend a **deep/reasoning model
for the full review** and a faster model for a quick pass. Switching models never
changes the workflow; the steps below run identically on any host.

## Stage 0 — Locate the input

Find the thesis file the user provided (a `.pdf` or `.docx` path). If none is
given, ask for the file path before proceeding.

## Stage 1 — Ingest (reuse existing skills, do not rebuild extraction)

- **PDF** → use the built-in **`pdf`** skill to extract text (and OCR if the PDF is
  scanned). Save the full plain text to a working file, e.g.
  `./_thesis_work/full_text.txt`.
- **Word (.docx)** → use the built-in **`docx`** skill to read the document, and
  save its text to the same working file.

Keep tables and headings as text; segmentation depends on heading lines surviving.

## Stage 2 — Segment into chapters/sections

Run the bundled splitter:

```bash
python "<skill_dir>/scripts/segment.py" ./_thesis_work/full_text.txt ./_thesis_work/sections
```

It detects **Thai and English** headings (`บทคัดย่อ`/`Abstract`,
`บทที่ 1`–`บทที่ 5`/`Chapter 1`–`5`, `เอกสารอ้างอิง`/`References`/`Bibliography`,
and the internal essay-part markers `X.1`–`X.5` such as `2.1 บทนำ`,
`2.4 ผลการศึกษา`, `2.5 อภิปราย`) and writes one file per section plus
`segmentation.json` (the section map). Read `segmentation.json` to know which
sections exist.

If the splitter misses or mis-assigns a boundary (unusual formatting, or a
table-of-contents whose dotted lines fool the TOC filter), fall back to reading
`full_text.txt` directly and segment by inspection — but still produce the same
section set.

After segmentation, also run the page mapper so every issue can be cited by PDF
page number:

```bash
python "<skill_dir>/scripts/page_map.py" ./_thesis_work/full_text.txt
python "<skill_dir>/scripts/page_map.py" ./_thesis_work/full_text.txt --line 1234
python "<skill_dir>/scripts/page_map.py" ./_thesis_work/full_text.txt --range 320:536
```

## Stage 2b — Detect the thesis format (CRITICAL — do this before reviewing)

Thai DBA theses come in **two canonical formats**. Determine which one was
supplied from `segmentation.json` + a quick skim, because it changes how the
8 steps are interpreted and how "missing" sections are reported.

| Format | What's present | Typical use |
|--------|----------------|-------------|
| **A. Proposal-only** | Chapter 1 (Introduction) + Chapter 2 (Literature Review) + Chapter 3 (Methodology). **No results, no Ch4/5.** | A pre-data-collection proposal defense / qualifying exam. |
| **B. Multi-essay collection** | Chapter 1 = an **umbrella introduction**, then **2–3 standalone empirical essays** as Chapters 2–N. Each essay is a self-contained paper with its own internal 7-part structure (see below). | A completed, publication-style thesis. |

**Canonical Format B structure (use this as the review checklist):**

**Chapter 1 — Umbrella Introduction** (5 parts):
1. Research questions
2. Objectives
3. Scope of study
4. Contribution (expected benefits)
5. Bibliography

**Chapter 2, 3, … — each Essay** (7 parts each):
1. Introduction
2. Literature review
3. Research methodology
4. Results
5. Discussion
6. Bibliography
7. Appendix (questionnaire / instrument / choice cards)

**How to tell the formats apart:** count top-level chapters. **3 chapters and
no results anywhere → Format A.** **2+ chapters where each essay repeats the
7-part structure and carries its own `บรรณานุกรม`/References → Format B.**
(Many real theses are 2 or 3 essays, not always 3 — review whatever count is
present.)

State the detected format explicitly at the top of the report (Step 1), and:

- **Format A:** evaluate only what a proposal can offer — problem statement,
  literature synthesis, proposed design, instrument. Do **not** fault the
  absence of results/Ch4/Ch5; instead, list what the full study must still
  deliver.
- **Format B (review per section):** for **every essay**, walk its 7 parts in
  order and review **each part individually**. A very common failure mode is
  that one or more essays are still truncated mid-way (e.g. an essay stops at
  Methodology with no Results/Discussion, or has Results tables but no
  Discussion, or is missing its own Bibliography/Appendix). Flag any essay
  whose internal parts are incomplete. Also check that the umbrella Ch1
  genuinely integrates the essays under one shared framework.

## Stage 3 — Run the 8 steps in strict sequence

Load `reference/rubric.md` for the full per-step criteria. Process the steps **in
order**, and for each step read **only the section file(s) it needs** (this keeps
long theses within context).

### Review depth — mandatory for every step

This is a **detailed, line-level review**, not a high-level summary. For every
section you review, examine it in depth and report findings across **six
dimensions**, not just the academic ones:

1. **Academic / methodological** — theory, design, analysis, results, discussion
   (the core of the rubric).
2. **Logical flow** — does the argument progress coherently? Flag non-sequiturs,
   circular reasoning, claims unsupported by the preceding text, jumps in logic,
   hypothesis results that contradict the framing, and missing transitions.
3. **Correctness of wording (คำผิด)** — wrong word, malapropism, misspelling,
   wrong technical term (e.g. "หลักการ" vs "หลักฐาน"), inconsistent terminology.
4. **Correct Thai usage (การใช้ภาษาไทยอย่างถูกต้อง)** — Royal Institute rules:
   correct spelling, word boundaries, formal/academic register, royal vocabulary
   where appropriate, correct use of คำนำหน้า and classifiers.
5. **Phrasing / word arrangement (การเรียบเรียงคำ)** — awkward, redundant, or
   run-on sentences; tense/aspect issues; passive-overuse; sentences that should
   be split; unclear antecedents; tone inconsistency.
6. **Formatting & citation mechanics** — numbering, table/figure labels, APA
   formatting, in-text citation completeness.

**Every single issue must cite its exact PDF page number**, in the form
`(p. 47)` or `(pp. 47–48)`. Use `scripts/page_map.py` to map the section file's
line numbers back to PDF pages. Do not raise an issue without a page citation.

> **Extraction-artifact caveat (CRITICAL):** PDF text extraction often corrupts
> Thai text — common artifacts are swapped/reordered consonants or vowels
> (e.g. "สำคญั" rendered when the source is "สำคัญ", "วตั ถปุ" for "วัตถุ",
> "ทวั่ ไป" for "ทั่วไป"). **Never flag a spelling/Thai-usage error that is
> actually an extraction artifact.** Rule of thumb: if the garbling involves
> consonant/vowel-tone-mark reordering within a single Thai word and the word
> reads correctly when the characters are mentally reordered, it is an
> extraction artifact — do not report it. Only report Thai errors that are
> genuine authoring errors visible as consistent, non-reordering mistakes.

### Detailed Corrections Log (mandatory appendix)

In addition to the per-step narrative, every report must end with a **Detailed
Corrections Log** appendix: a numbered table of *every actionable correction*,
with columns: `No. | Page | Section | Type | Issue | Suggested fix | Severity`.
Types are: `Academic`, `Logical`, `Wording`, `Thai usage`, `Phrasing`,
`Formatting`, `Citation`. This is the deliverable the author works through to
revise — make it exhaustive and concrete.

1. **Document Segmentation & Structural Overview** — use `segmentation.json` + a
   skim of each section. **State the detected format (A or B) here** and lay out
   which chapters/essays exist; for Format B list each essay's title and which
   of its 7 parts are present vs. missing.
2. **Academic Title Review** — front matter.
3. **Bilingual Abstract Alignment** — Thai + English abstracts, back-to-back.
   (Format B: there is an **umbrella abstract** for the whole thesis **and** one
   per essay — check that the umbrella abstract synthesizes all essays.)
4. **Chapter 1 — Umbrella Introduction.** Review its 5 parts: **research
   questions, objectives, scope of study, contribution, bibliography.** (In
   Format B, evaluate whether the research questions genuinely integrate the
   essays under one shared framework.)
5. **Essay 1 (Chapter 2) — review all 7 parts in order:**
   **(a) Introduction (b) Literature review (c) Research methodology
   (d) Results (e) Discussion (f) Bibliography (g) Appendix.**
   Review each part individually; flag any that are missing or truncated.
6. **Essay 2 (Chapter 3) — review all 7 parts** (same checklist as Step 5).
   *(If there are only 2 essays, this step covers the last essay and Step 7 is
   not used.)*
7. **Essay 3 (Chapter 4) — review all 7 parts** (same checklist as Step 5).
   *(If there are more than 3 essays, continue the same pattern. If this is
   Format A, instead state that Ch4/Ch5 are not yet written and itemize what
   they must contain.)*
8. **Bibliography & Academic Citation Cross-Check.** (Format B has one
   bibliography per essay — check each set independently.)
   bibliography per essay — check each set independently.)

For every step give deep, specific, actionable feedback and **cite concrete
examples from the text**. If a section is absent, write the exact line:
`[Section/Chapter] is missing from the provided document` under that step's header
and continue.

## Stage 4 — Assemble the report

Build the final report from `reference/report-template.md` (eight `#` headers in
order). **Write the report in the thesis's dominant language** (Thai theses with a
bilingual abstract → Thai or bilingual as appropriate; English theses → English).

## Output rules (mandatory — every deliverable)

- **No emoji, no decorative symbols.** The report is an official academic
  document for a doctoral committee. Never use 🔴/🟠/🟡/✅/❌/⚠️/📌/👉 or any
  pictograph, dingbat, or colored-circle marker. Use **plain text** throughout.
- **Severity labels are textual, not emoji.** Use bracketed tags, e.g.
  `[Critical]`, `[Major]`, `[Minor]`, `[Strength]`, `[Present]`, `[Missing]`.
  Keep them consistent across the whole report.
- **Professional, formal, objective tone.** Third-person advisory register — no
  exclamation marks, no informal emphasis (e.g. avoid "!!!", "very", "really"),
  no colloquialisms.
- **Every claim cites a concrete location in the thesis** (page, table number,
  section, or quoted phrase) so the committee can verify it.

## Stage 5 — Save deliverables

- Always save the review as Markdown, e.g. `./reviews/<thesis-name>-review.md`.
- **Also generate a matching `.docx`** for committee use. The host's built-in
  **`docx`** skill is preferred; if unavailable, a Markdown→DOCX converter
  (pandoc, or python-docx) is acceptable. Deliver **both** files and report both
  paths to the user.
- **The `.docx` must be a professional, academic, official document** — the kind
  a committee would expect:
  - A formal **title block** at the top (report title, thesis title, author,
    institution, program, date, reviewer) — not a bare first heading.
  - A **serif body font** (e.g. Times New Roman 12pt) with 1.5 line spacing;
    Thai-heavy documents may use Sarabun/TH Sarabun New.
  - **Justified** body text, consistent heading hierarchy, and **page numbers**
    in the footer.
  - **Tables** rendered with proper header rows (shaded), borders, and a caption
    or number — no raw Markdown pipe syntax.
  - Margins and spacing that look typeset, not pasted. If generating via a
    converter, post-process to enforce these; never ship a Markdown-dump.

## Cleanup

Leave `_thesis_work/` in place unless the user asks to remove it (the section files
are useful for re-runs and spot checks).

## Project layout

```
ThesisPro/
├── SKILL.md                  # this skill (host-neutral, supports formats A & B)
├── reference/
│   ├── rubric.md             # per-step criteria (format-aware)
│   └── report-template.md    # report skeleton (states detected format)
├── scripts/
│   ├── segment.py            # bilingual (Thai+English) chapter/section splitter
│   └── page_map.py           # map full_text.txt lines -> PDF page numbers
├── reviews/                  # OUTPUT — generated <thesis>-review.md + .docx land here
└── theses/                   # INPUT  — drop the thesis .pdf/.docx here
```

## Two-DBA-format quick reference

- **Format A — Proposal-only (Ch1–3):** pre-data-collection. Review problem,
  literature, *proposed* design. Don't penalize missing results; list what's owed.
- **Format B — Multi-essay collection:** Ch1 = umbrella introduction (research
  questions, objectives, scope, contribution, bibliography); Ch2/3/… = 2–3
  standalone essays, **each reviewed per section across all 7 parts**:
  `Introduction → Literature review → Research methodology → Results →
  Discussion → Bibliography → Appendix`. Flag any essay whose parts are
  truncated or missing.
