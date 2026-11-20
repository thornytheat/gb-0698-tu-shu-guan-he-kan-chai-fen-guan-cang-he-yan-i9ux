from collections import Counter
from app.report import report

EXPECTED = 12

KIND_LABELS = {"held": "实物", "suspended": "停刊声明", "missing": "缺期声明"}


def _issue_key(value):
    text = str(value)
    return (0, int(text)) if text.isdigit() else (1, text)


def expected_issues(expected=EXPECTED):
    return [str(i) for i in range(1, expected + 1)]


def missing(covered, suspended, expected=EXPECTED):
    """Annual gaps: expected issues minus physical issues minus effective suspension."""
    covered = {str(i) for i in covered}
    suspended = {str(i) for i in suspended}
    return sorted(set(expected_issues(expected)) - covered - suspended, key=_issue_key)


def merge_ranges(issues):
    """Merge numeric issue numbers into inclusive [start, end] ranges.

    Non-numeric issues (for example supplements) are not part of the regular
    annual sequence and are deliberately left out of the ranges.
    """
    numbers = sorted({int(str(i)) for i in issues if str(i).isdigit()})
    ranges = []
    for number in numbers:
        if ranges and number == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], number)
        else:
            ranges.append((number, number))
    return [
        {
            "start": str(first),
            "end": str(last),
            "issues": [str(n) for n in range(first, last + 1)],
        }
        for first, last in ranges
    ]


def _evidence(row, kind, issue):
    # Deliberately compact: the raw row (including note) already lives in the
    # held/expanded result, so the per-issue basis only carries the reference
    # needed to cross-check a decision without duplicating the whole input.
    return {
        "kind": kind,
        "kind_label": KIND_LABELS[kind],
        "record_id": row.get("record_id", ""),
        "line": row.get("line", 0),
        "issue": issue,
        "expression": row.get("issue", ""),
        "copy": row.get("copy", ""),
        "binding": row.get("binding", ""),
    }


def declarations(rows):
    """Normalise every suspension declaration, preserving all source evidence."""
    out = []
    for row in rows:
        if row["status"] != "suspended":
            continue
        issues = sorted({str(i) for i in row["issues"]}, key=_issue_key)
        out.append(
            {
                "record_id": row.get("record_id", ""),
                "line": row.get("line", 0),
                "expression": row.get("issue", ""),
                "start": issues[0] if issues else "",
                "end": issues[-1] if issues else "",
                "issues": issues,
                "ranges": merge_ranges(issues),
                "copy": row.get("copy", ""),
                "status": row.get("status", ""),
                "note": row.get("note", ""),
            }
        )
    out.sort(key=lambda item: (item["line"], item["record_id"], item["expression"]))
    return out


def _basis_text(evidence, fallback=""):
    if not evidence:
        return fallback
    return "；".join(
        f"{b['kind_label']} {b['record_id']}（行{b['line']}）{b['expression']}"
        for b in evidence
    )


def _decision(issue, held_rows, suspended_rows, missing_rows):
    held_evidence = [_evidence(r, "held", issue) for r, issues in held_rows if issue in issues]
    suspension_evidence = [
        _evidence(r, "suspended", issue) for r, issues in suspended_rows if issue in issues
    ]
    missing_evidence = [
        _evidence(r, "missing", issue) for r, issues in missing_rows if issue in issues
    ]
    basis = held_evidence + suspension_evidence + missing_evidence

    if held_evidence:
        # A physical copy always wins over a suspension declaration for the same
        # issue.  The declaration evidence stays attached so the overlap is
        # reviewable rather than silently discarded.
        decision, label = "held", "实物"
    elif suspension_evidence:
        # Every declaration that covers this issue is retained as evidence; the
        # reconciliation never silently picks one of several declarations.
        decision, label = "suspended", "停刊"
    else:
        decision, label = "missing", "缺期"

    return {
        "issue": issue,
        "decision": decision,
        "label": label,
        "declared_suspended": bool(suspension_evidence),
        "basis": basis,
        "basis_text": _basis_text(basis, "无到馆记录，年度应到未到"),
        "held_records": [b["record_id"] for b in held_evidence],
        "suspension_records": [b["record_id"] for b in suspension_evidence],
        "missing_records": [b["record_id"] for b in missing_evidence],
    }


def _scope_text(issues):
    """Range text for numeric issues plus any explicitly listed special issues."""
    merged = _range_text(merge_ranges(issues))
    specials = [str(i) for i in sorted({str(i) for i in issues}, key=_issue_key) if not str(i).isdigit()]
    if not specials:
        return merged
    if merged == "无":
        return "、".join(specials)
    return f"{merged}（含 {'、'.join(specials)}）"


def _display(item):
    """Compact, page-friendly projection of an annual reconciliation."""
    return {
        "issn": item["issn"],
        "title": item["title"],
        "year": item["year"],
        "status": item["status"],
        "declared_ranges": item["declared_ranges"],
        "effective_ranges": item["effective_ranges"],
        "declared_suspended": _issue_text(item["declared_suspended"]),
        "suspended": _issue_text(item["suspended"]),
        "covered": _issue_text(item["covered"]),
        "missing": _issue_text(item["missing"]),
        "declarations": len(item["declarations"]),
        "declaration_conflict": item["declaration_conflict"],
        "physical_in_suspension": item["physical_in_suspension"],
    }


def _range_text(ranges):
    return "、".join(
        r["start"] if r["start"] == r["end"] else f'{r["start"]}—{r["end"]}' for r in ranges
    ) or "无"


def _issue_text(issues):
    return "、".join(issues) or "无"


def apply(ctx):
    groups = {}
    for row in ctx["expanded"]:
        key = (row["journal_key"], row["year"], row["canonical"])
        groups.setdefault(key, []).append(row)

    out = []
    scopes = []
    for key in sorted(groups, key=lambda k: (_issue_key(k[1]), k[0], k[2])):
        issn, year, title = key
        rows = groups[key]
        held_rows = [r for r in rows if r["status"] == "held"]
        suspended_rows = [r for r in rows if r["status"] == "suspended"]
        missing_rows = [r for r in rows if r["status"] == "missing"]
        # Pre-index each row's issue set once instead of rebuilding it for every
        # one of the twelve annual issues.
        indexed_held = [(r, {str(i) for i in r["issues"]}) for r in held_rows]
        indexed_suspended = [(r, {str(i) for i in r["issues"]}) for r in suspended_rows]
        indexed_missing = [(r, {str(i) for i in r["issues"]}) for r in missing_rows]

        covered = {str(i) for r in held_rows for i in r["issues"]}
        declared_suspended = {str(i) for r in suspended_rows for i in r["issues"]}
        # A physically held issue is not exempt: it is a real volume and it also
        # must not be reported as missing.  Suspension only exempts the issues
        # that did not arrive, so every issue is resolved on its own evidence.
        suspended = declared_suspended - covered
        absent = missing(covered, suspended)

        declaration_list = declarations(rows)
        overlap_issues = sorted(
            (
                issue
                for issue, count in Counter(
                    i for d in declaration_list for i in d["issues"]
                ).items()
                if count > 1
            ),
            key=_issue_key,
        )
        # Conflict = the same issue is covered by declarations with different
        # start/end bounds.  Declarations that merely sit side by side (for
        # example 3-4 and 7) are not a conflict, but every declaration is still
        # kept as evidence and merged into the annual scope.
        bound_conflict_issues = sorted(
            {
                issue
                for issue in overlap_issues
                if len({(d["start"], d["end"]) for d in declaration_list if issue in d["issues"]}) > 1
            },
            key=_issue_key,
        )
        declaration_conflict = bool(bound_conflict_issues)

        issue_decisions = [
            _decision(issue, indexed_held, indexed_suspended, indexed_missing)
            for issue in expected_issues()
        ]
        physical_overlap_issues = sorted(
            {str(i) for r in held_rows for i in r["issues"]} & declared_suspended,
            key=_issue_key,
        )
        # Count distinct physical volumes that touch a declared suspension range.
        # A combined volume counts once, exactly like it does in the shelf count.
        physical_in_suspension = len(
            {
                (r.get("copy", ""), r.get("binding", "") or r.get("record_id", ""))
                for r in held_rows
                if any(str(i) in declared_suspended for i in r["issues"])
            }
        )
        physical_books = len(
            {
                (r.get("copy", ""), r.get("binding", "") or r.get("record_id", ""))
                for r in held_rows
            }
        )

        item = {
            "issn": issn,
            "title": title,
            "year": year,
            "missing": absent,
            "covered": sorted(covered, key=_issue_key),
            "suspended": sorted(suspended, key=_issue_key),
            "declared_suspended": sorted(declared_suspended, key=_issue_key),
            "status": "GAP" if absent else "COMPLETE",
            "declared_ranges": _scope_text(sorted(declared_suspended, key=_issue_key)),
            "effective_ranges": _scope_text(sorted(suspended, key=_issue_key)),
            "declarations": declaration_list,
            "declaration_conflict": declaration_conflict,
            "multiple_declarations": len(declaration_list) > 1,
            "overlap_issues": overlap_issues,
            "issue_decisions": issue_decisions,
            "physical_books": physical_books,
            "physical_in_suspension": physical_in_suspension,
            "physical_overlap_issues": physical_overlap_issues,
        }
        out.append(item)

        if declaration_list:
            scopes.append(
                {
                    "issn": issn,
                    "title": title,
                    "year": year,
                    "declared_ranges": item["declared_ranges"],
                    "effective_ranges": item["effective_ranges"],
                    "declared_suspended": item["declared_suspended"],
                    "suspended": item["suspended"],
                    "physical_overlap_issues": physical_overlap_issues,
                    "physical_in_suspension": physical_in_suspension,
                    "declarations": declaration_list,
                    "overlap_issues": overlap_issues,
                    "declaration_conflict": declaration_conflict,
                    "multiple_declarations": len(declaration_list) > 1,
                }
            )

    ctx["gaps"] = out
    # Declarations live on the annual records; this flat index only points at
    # them for the evidence export, so it does not duplicate the payload.
    ctx["suspension_ranges"] = scopes
    ctx["suspended_issue_count"] = sum(len(item["suspended"]) for item in out)
    ctx["declared_suspended_issue_count"] = sum(
        len(item["declared_suspended"]) for item in out
    )
    # Each held volume belongs to exactly one annual record (journal+year+title),
    # so summing per-record distinct volumes cannot double count.  M6 remains the
    # owner of the total physical-book count.
    ctx["suspension_physical_books"] = sum(
        item["physical_in_suspension"] for item in out
    )
    ctx["suspension_conflicts"] = [
        {
            "issn": scope["issn"],
            "title": scope["title"],
            "year": scope["year"],
            "overlap_issues": scope["overlap_issues"],
            "declarations": scope["declarations"],
        }
        for scope in scopes
        if scope["declaration_conflict"]
    ]
    return report(
        [_display(item) for item in out],
        缺期=sum(len(item["missing"]) for item in out),
        年度=len(out),
        停刊声明=sum(len(scope["declarations"]) for scope in scopes),
        停刊期=ctx["suspended_issue_count"],
        停刊期实物=ctx["suspension_physical_books"],
        停刊声明冲突=len(ctx["suspension_conflicts"]),
    )
