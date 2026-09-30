#!/usr/bin/env python3
"""Split an extracted thesis text file into front matter, abstracts, Ch1-5, and
references. Standard library only.

Usage:
    python segment.py <full_text.txt> <output_dir>

Writes one <label>.txt per detected section into <output_dir>, plus a
segmentation.json map. Heading detection is bilingual (Thai + English) and tries
to ignore table-of-contents lines via two layers: (1) a TOC-region guard that
skips everything between a "สารบัญ"/"Table of Contents" marker and the first
short bare chapter heading, and (2) per-line dot-leader / trailing-page-number
filters for TOC entries that live outside that region.

The JSON map also records, for each chapter, the internal `X.1`-`X.5`
sub-section markers found inside it (e.g. `2.1 บทนำ`, `3.4 ผลการศึกษา`).
This lets callers (the skill's Stage 2b format detector) tell a complete
3-paper-collection essay from one truncated mid-way.
"""
import json
import re
import sys
from pathlib import Path

THAI_DIGITS = {"๐": "0", "๑": "1", "๒": "2", "๓": "3", "๔": "4", "๕": "5",
               "๖": "6", "๗": "7", "๘": "8", "๙": "9"}
ENG_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

# Internal sub-section markers used by Thai-DBA essays:
#   X.1 Introduction, X.2 Literature Review, X.3 Methodology,
#   X.4 Results, X.5 Discussion & Conclusions.  Informational only (non-splitting).
SUBSECTION_RE = re.compile(r"^([1-9])\.([1-9])\s+\S")
TOC_START_RE = re.compile(
    r"^\s*(?:สารบัญ|สารบัญหัวข้อ|สารบัญตาราง|สารบัญภาพ|"
    r"table\s+of\s+contents|contents|list\s+of\s+(?:tables|figures))\b\s*:?\s*$",
    re.IGNORECASE,
)

# The 7 canonical parts of a Format-B essay, and the keywords that signal each
# part inside an "X.N <keyword>" heading (bilingual). Used to report per-part
# completeness in segmentation.json so the skill can review each part.
ESSAY_PARTS = {
    "introduction":   ["บทนำ", "introduction"],
    "literature":     ["ทบทวนวรรณกรรม", "literature review", "review of literature"],
    "methodology":    ["ระเบียบวิธี", "วิธีดำเนินการวิจัย", "วิธีการวิจัย", "methodology", "research method"],
    "results":        ["ผลการศึกษา", "ผลการวิเคราะห์", "ผลการวิจัย", "results", "findings", "result"],
    "discussion":     ["วิเคราะห์", "สรุป", "อภิปราย", "discussion", "conclusion", "concluding remarks"],
    "bibliography":   ["บรรณานุกรม", "เอกสารอ้างอิง", "bibliography", "references", "reference list"],
    "appendix":       ["ภาคผนวก", "appendix", " annex", "questionnaire", "แบบสอบถาม"],
}


def classify_essay_part(line: str, ch_num: int):
    """Given a heading line like '2.4 ผลการศึกษา', return the canonical part name
    (one of ESSAY_PARTS keys) or None. Falls back to the numeric position for
    parts 1-5 when no keyword matches."""
    s = line.strip()
    m = SUBSECTION_RE.match(s)
    if not m:
        # Non-numbered lines: only bibliography/appendix travel without a number.
        low = s.lower()
        if any(k in low for k in ESSAY_PARTS["bibliography"]):
            return "bibliography"
        if any(k in low for k in ESSAY_PARTS["appendix"]):
            return "appendix"
        return None
    if int(m.group(1)) != ch_num:
        return None
    sub, rest = int(m.group(2)), s[m.end() - len(s) + len(m.group(0)):].strip()  # text after number
    rest_low = rest.lower()
    for part, kws in ESSAY_PARTS.items():
        if part in ("bibliography", "appendix"):
            continue
        if any(k in rest_low for k in kws):
            return part
    # Keyword fallback: by position (X.1=intro ... X.5=discussion).
    pos_map = {1: "introduction", 2: "literature", 3: "methodology",
               4: "results", 5: "discussion"}
    return pos_map.get(sub)


def to_arabic(token: str):
    """Convert a chapter-number token (Arabic, Thai numeral, or English word) to int."""
    token = token.strip().lower()
    if token in ENG_WORD_NUM:
        return ENG_WORD_NUM[token]
    digits = "".join(THAI_DIGITS.get(ch, ch) for ch in token)
    m = re.search(r"\d+", digits)
    return int(m.group()) if m else None


def has_dot_leader(line: str) -> bool:
    """True if the line contains a dot-leader run (3+ dots, ASCII or fullwidth,
    possibly space-separated) typical of a table-of-contents row."""
    if re.search(r"\.{3,}", line):
        return True
    if re.search(r"(?:\.\s){3,}", line):          # ". . ." style leaders
        return True
    if re.search(r"[．。]{3,}", line):             # fullwidth / CJK full stops
        return True
    if re.search(r"(?:[•·]\s?){4,}", line):        # bullet leaders
        return True
    return False


def has_trailing_page_number(line: str) -> bool:
    """True if the line ends with a big-then-page-number pattern typical of TOC."""
    if re.search(r"\s{2,}\d{1,4}\s*$", line):
        return True
    if re.search(r"[.．。\s]\d{1,4}\s*$", line) and has_dot_leader(line):
        return True
    return False


def is_toc_line(line: str) -> bool:
    """Heuristic: a table-of-contents row has dot leaders and/or a trailing
    page number."""
    return has_dot_leader(line) or has_trailing_page_number(line)


# (kind, key) detectors. kind in {abstract_th, abstract_en, chapter, references}
CHAPTER_RE = re.compile(
    r"^\s*(?:บทที่\s*([๐-๙\d]+)"
    r"|chapter\s+(\d+|one|two|three|four|five))\b",
    re.IGNORECASE,
)

# Thai-DBA convention: chapters often start with a bare "X.1 บทนำ" intro
# subsection (no separate "บทที่ N" heading), and Chapter 1 may be a bare
# "บทนำ" line. These are the most reliable markers when the document lacks
# explicit chapter-title pages.
CHAPTER_INTRO_RE = re.compile(r"^([1-5])\.1\s+บทนำ\b")
INTRO_ONLY_RE = re.compile(r"^บทนำ\s*[:.]?\s*$")  # bare "บทนำ" = Chapter 1


def is_bare_chapter_heading(s: str) -> bool:
    """True if the stripped line is a real chapter start (not a TOC row) in any
    of the supported styles: 'บทที่ N <short>', 'Chapter N <short>',
    'X.1 บทนำ', or bare 'บทนำ'."""
    if not s or is_toc_line(s):
        return False
    if CHAPTER_RE.match(s) and len(s) <= 25:
        return True
    if CHAPTER_INTRO_RE.match(s) and len(s) <= 20:
        return True
    if INTRO_ONLY_RE.match(s):
        return True
    return False


def classify(line: str):
    """Return (kind, key) or None. A chapter is accepted only if the line is
    short (heading dominates), has no dot leader, and no trailing page number —
    this rejects wrapped table-of-contents title fragments that happen to start
    with 'บทที่ N ...' but carry a long title with no dots."""
    s = line.strip()
    if not s or len(s) > 90:
        return None
    if has_dot_leader(s) or has_trailing_page_number(s):
        return None
    low = s.lower()

    if "บทคัดย่อ" in s:
        return ("abstract_th", None)
    if re.match(r"^abstract\b", low) and len(s) <= 30:
        return ("abstract_en", None)
    if re.match(r"^(references|bibliography)\b", low) and len(s) <= 30:
        return ("references", None)
    if s.startswith("เอกสารอ้างอิง") or s.startswith("บรรณานุกรม"):
        return ("references", None)

    m = CHAPTER_RE.match(s)
    if m:
        num = to_arabic(m.group(1) or m.group(2) or "")
        if num and 1 <= num <= 5:
            # Reject TOC-style chapter rows: the line after the chapter marker
            # must not be very long (real chapter starts are short headings;
            # TOC rows carry a title + leader + page number).
            return ("chapter", num)

    # Thai-DBA bare-intro styles: "X.1 บทนำ" or a bare "บทนำ" (Chapter 1).
    m2 = CHAPTER_INTRO_RE.match(s)
    if m2:
        return ("chapter", int(m2.group(1)))
    if INTRO_ONLY_RE.match(s):
        return ("chapter", 1)
    return None


LABELS = {
    "abstract_th": "Abstract (Thai)",
    "abstract_en": "Abstract (English)",
    "references": "References",
}


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    lines = src.read_text(encoding="utf-8", errors="replace").splitlines()

    # --- Pass 1: find chapter markers, skipping the TOC region entirely. ---
    # A TOC region opens at a "สารบัญ"/"Table of Contents" line and closes at
    # the first *bare* chapter heading (a chapter line whose text is essentially
    # just "บทที่ N" or "Chapter N", <= 25 chars). Everything inside the TOC
    # region is ignored when locating real section boundaries.
    in_toc = False
    markers = []           # list of (line_index, label, title)
    seen = set()
    for i, line in enumerate(lines):
        s = line.strip()

        # TOC region tracking
        if TOC_START_RE.match(s):
            in_toc = True
            continue
        if in_toc:
            # Any real chapter-start heading (in any supported style) closes
            # the TOC region. Use the unified detector so layouts that start
            # chapters with "X.1 บทนำ" or a bare "บทนำ" are handled too.
            if is_bare_chapter_heading(s):
                in_toc = False
                # fall through and classify this line normally below
            else:
                # still inside TOC: ignore even if it looks like a heading
                continue

        hit = classify(line)
        if not hit:
            continue
        kind, key = hit
        if kind == "chapter":
            label = f"chapter_{key}"
            title = f"Chapter {key}"
        else:
            label = kind
            title = LABELS[kind]
        if label in seen:
            continue
        seen.add(label)
        markers.append((i, label, title))

    markers.sort(key=lambda m: m[0])

    # --- Pass 2: assign boundaries; everything before the first marker is front matter.
    boundaries = []
    if not markers or markers[0][0] > 0:
        boundaries.append((0, "front_matter", "Front Matter"))
    boundaries.extend(markers)

    # --- Pass 3: write sections + scan each chapter for X.1-X.5 sub-markers. ---
    sections = []
    for idx, (start, label, title) in enumerate(boundaries):
        end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(lines)
        text = "\n".join(lines[start:end]).strip()
        fname = f"{label}.txt"
        (out / fname).write_text(text, encoding="utf-8")

        entry = {
            "label": label,
            "title": title,
            "start_line": start,
            "end_line": end,
            "chars": len(text),
            "file": fname,
        }
        # For chapters >= 2, record which of the 7 canonical essay parts are
        # present so the skill can review each part and flag missing ones.
        # Chapter 1 (umbrella) is skipped — its parts differ.
        if label.startswith("chapter_"):
            try:
                ch_num = int(label.split("_")[1])
            except (IndexError, ValueError):
                ch_num = 0
            found_parts = {}
            if ch_num >= 2:
                for ln in lines[start:end]:
                    part = classify_essay_part(ln, ch_num)
                    if part and part not in found_parts:
                        # record the heading text as evidence
                        head = ln.strip()[:60]
                        found_parts[part] = head
                # build present/missing against the canonical 7
                entry["essay_parts"] = {
                    "present": list(found_parts.keys()),
                    "missing": [p for p in ESSAY_PARTS if p not in found_parts],
                    "headings": found_parts,
                }
            # keep the old numeric subsection map for backward compat
            found_subs = {}
            for ln in lines[start:end]:
                m = SUBSECTION_RE.match(ln.strip())
                if m and int(m.group(1)) == ch_num:
                    found_subs.setdefault(m.group(2), []).append(m.group(0).strip())
            entry["subsections"] = {k: v for k, v in sorted(found_subs.items())}
        sections.append(entry)

    found = {s["label"] for s in sections}
    expected = ["abstract_th", "abstract_en",
                "chapter_1", "chapter_2", "chapter_3", "chapter_4", "chapter_5",
                "references"]
    missing = [e for e in expected if e not in found]

    report = {
        "source": str(src),
        "sections": sections,
        "missing": missing,
        "note": ("Boundaries located with a TOC-region guard; subsection markers "
                 "are informational and help detect the thesis format."),
    }
    (out / "segmentation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {len(sections)} sections to {out}")
    for s in sections:
        extra = ""
        if "essay_parts" in s:
            ep = s["essay_parts"]
            present = ",".join(ep["present"]) or "(none)"
            missing_parts = ",".join(ep["missing"])
            extra = f"  parts:[{present}]  MISSING:[{missing_parts}]"
        elif "subsections" in s:
            extra = "  subs: " + ",".join(s["subsections"].keys())
        print(f"  {s['label']:<14} lines {s['start_line']}-{s['end_line']}  "
              f"({s['chars']} chars){extra}")
    if missing:
        print("Missing (not detected):", ", ".join(missing))


if __name__ == "__main__":
    main()
