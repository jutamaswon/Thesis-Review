#!/usr/bin/env python3
"""Apply corrections to a Word .docx as REAL Word track changes (revision
marks), so the author can Accept/Reject each one in Word. Standard library
only (zipfile + xml.etree). Only word/document.xml is modified.

Usage:
    python revise_docx.py input.docx edits.json output.docx [--author NAME]

edits.json format (the AI builds this during the review from the Corrections
Log; every "find" must be quoted EXACTLY as the text appears in the document):

{
  "author": "AI Reviewer",          # optional; --author overrides
  "edits": [
    {"action": "replace", "find": "หลักฐาน", "replace": "หลักการ"},
    {"action": "replace", "find": "teh ", "replace": "the ", "count": "all"},
    {"action": "delete", "find": " ในทางปฏิบัติ"},
    {"action": "insert_after", "find": "ผลการศึกษา", "text": " ดังนี้"}
  ]
}

Actions:
- replace       — delete the found text and insert "replace" (both tracked)
- delete        — delete the found text (tracked)
- insert_after  — keep the found text, insert "text" right after it (tracked)

"count": 1 (default, first occurrence only) | "all" | integer N.

Matching is exact-substring over each paragraph's visible text (runs joined
across formatting boundaries; runs inside existing tracked deletions are
ignored). Edits whose "find" is not found, or whose covered runs contain
complex content (tabs, breaks, fields, images), are skipped and reported in
the JSON summary so the caller can retry with corrected quotes or drop them.

Stdout summary (JSON):
{"applied": [...], "skipped": [{"action", "find", "reason"}]}
"""
import copy
import datetime
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XMLSPACE = "{http://www.w3.org/XML/1998/namespace}space"


def w(tag):
    return "{%s}%s" % (W, tag)


_next_id = [1000]


def new_id():
    _next_id[0] += 1
    return str(_next_id[0])


def register_all_namespaces(xml_text):
    """Register every xmlns prefix declared in the file so ElementTree keeps
    the original prefixes when re-serializing (unknown prefixes would be
    renamed to ns0/ns1/..., which Word rejects)."""
    for prefix, uri in re.findall(r'xmlns:([A-Za-z0-9_]+)="([^"]+)"', xml_text):
        ET.register_namespace(prefix, uri)


def parent_map(root):
    return {child: parent for parent in root.iter() for child in parent}


def run_text(run):
    return "".join(t.text or "" for t in run.findall(w("t")))


def is_simple_run(run):
    """True if the run contains only rPr + w:t children (safe to split and
    rebuild). Runs holding tabs, breaks, fields, drawings are never edited."""
    return all(child.tag in (w("rPr"), w("t")) for child in run)


def visible_runs(para, parents):
    """Paragraph runs in document order, excluding runs inside existing
    tracked deletions (deleted text is not part of the visible document)."""
    runs = []
    for run in para.iter(w("r")):
        node, deleted = run, False
        while node is not None:
            if node.tag == w("del"):
                deleted = True
                break
            node = parents.get(node)
        if not deleted:
            runs.append(run)
    return runs


def under_deletion(node, parents):
    while node is not None:
        if node.tag == w("del"):
            return True
        node = parents.get(node)
    return False


def make_text(tag, text):
    el = ET.Element(tag)
    el.text = text
    el.set(XMLSPACE, "preserve")
    return el


def clone_run(run, text, del_text=False):
    """A new run copying `run`'s formatting (rPr) and carrying `text` in a
    w:t (or w:delText for tracked deletions)."""
    new = ET.Element(w("r"))
    rpr = run.find(w("rPr"))
    if rpr is not None:
        new.append(copy.deepcopy(rpr))
    if text:
        new.append(make_text(w("delText") if del_text else w("t"), text))
    return new


def wrap_at(parent, index, tag, author, date, children):
    """Insert <w:ins|w:del w:id w:author w:date> at parent[index]."""
    mark = ET.Element(tag)
    mark.set(w("id"), new_id())
    mark.set(w("author"), author)
    mark.set(w("date"), date)
    for child in children:
        mark.append(child)
    parent.insert(index, mark)


def apply_once(para, parents, find, mode, ins_text, author, date):
    """Apply one edit to `para` at its first occurrence of `find`.

    mode: "replace"      -> tracked del(find) + tracked ins(ins_text) (""=delete)
          "insert_after" -> keep find, tracked ins(ins_text) after it
    Returns True if applied; False if not found or too complex."""
    if not find:
        return False
    runs = visible_runs(para, parents)
    texts = [run_text(r) for r in runs]
    full = "".join(texts)
    idx = full.find(find)
    if idx < 0:
        return False
    end = idx + len(find)

    # Map the match [idx, end) onto (run, start_in_run, end_in_run) segments.
    segs = []
    pos = 0
    for run, text in zip(runs, texts):
        rs, re_ = pos, pos + len(text)
        if re_ > idx and rs < end:
            segs.append((run, max(idx, rs) - rs, min(end, re_) - rs))
        pos = re_
    if not segs or any(not is_simple_run(run) for run, _, _ in segs):
        return False

    ins_parent = None  # (parent, index) where the tracked insertion goes
    for i, (run, s, e) in enumerate(segs):
        parent = parents.get(run)
        index = list(parent).index(run)
        text = run_text(run)
        before, covered, after = text[:s], text[s:e], text[e:]

        # Rebuild this run in place as: [before][covered][after], where
        # "covered" is a tracked deletion (replace/delete) or a plain clone
        # (insert_after). Record where the insertion anchor sits (right
        # after the covered piece of the LAST segment).
        elements = []  # (element | ("del", element), is_covered)
        if before:
            elements.append((clone_run(run, before), False))
        if covered:
            if mode == "insert_after":
                elements.append((clone_run(run, covered), True))
            else:
                elements.append((("del", clone_run(run, covered, del_text=True)), True))
        if after:
            elements.append((clone_run(run, after), False))

        parent.remove(run)
        at = index
        for item, is_covered in elements:
            if isinstance(item, tuple):
                wrap_at(parent, at, w("del"), author, date, [item[1]])
            else:
                parent.insert(at, item)
            at += 1
            if is_covered and i == len(segs) - 1:
                ins_parent = (parent, at)
    # else: empty covered text cannot happen for a non-empty `find` match

    if ins_text and ins_parent is not None:
        parent, at = ins_parent
        wrap_at(parent, at, w("ins"), author, date,
                [clone_run(segs[-1][0], ins_text)])
    return True


def apply_edit(root, parents, find, mode, ins_text, count, author, date):
    """Apply an edit across the whole document up to `count` times
    (int, or "all"). Returns the number of applications."""
    limit = None if count == "all" else max(1, int(count))
    applied = 0
    for para in list(root.iter(w("p"))):
        if under_deletion(para, parents):
            continue
        while apply_once(para, parents, find, mode, ins_text, author, date):
            applied += 1
            parents = parent_map(root)  # tree changed under us
            if limit is not None and applied >= limit:
                return applied, parents
        parents = parent_map(root)
    return applied, parents


def main():
    args = sys.argv[1:]
    author_arg = None
    if "--author" in args:
        i = args.index("--author")
        author_arg = args[i + 1]
        del args[i:i + 2]
    if len(args) != 3:
        print(__doc__)
        sys.exit(1)
    src, edits_path, out = args

    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        data = {n: zin.read(n) for n in names}

    doc_xml = data["word/document.xml"].decode("utf-8")
    register_all_namespaces(doc_xml)
    root = ET.fromstring(doc_xml)

    with open(edits_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    author = author_arg or spec.get("author") or "AI Reviewer"
    date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    applied, skipped = [], []
    parents = parent_map(root)
    for edit in spec.get("edits", []):
        action = edit.get("action", "replace")
        find = edit.get("find") or ""
        if action == "replace":
            mode, ins_text = "replace", edit.get("replace", "")
        elif action == "delete":
            mode, ins_text = "replace", ""
        elif action == "insert_after":
            mode, ins_text = "insert_after", edit.get("text", "")
        else:
            skipped.append({"action": action, "find": find,
                            "reason": "unknown action"})
            continue
        count = edit.get("count", 1)
        n, parents = apply_edit(root, parents, find, mode, ins_text,
                                count, author, date)
        if n == 0:
            skipped.append({"action": action, "find": find,
                            "reason": ("empty find" if not find else
                                       "text not found (or spans complex "
                                       "run content such as tabs/fields)")})
        else:
            applied.append({"action": action, "find": find,
                            "applied_times": n})

    new_xml = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
    # sanity: must still be well-formed before we ship it
    ET.fromstring(new_xml)
    data["word/document.xml"] = new_xml

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in names:  # preserve the original entry order
            zout.writestr(n, data[n])

    print(json.dumps({"applied": applied, "skipped": skipped},
                     ensure_ascii=False, indent=2))
    print(f"Wrote {out}: {len(applied)} edit(s) applied, "
          f"{len(skipped)} skipped.", file=sys.stderr)


if __name__ == "__main__":
    main()
