import csv, io

from app.pipeline import run
from app.exporter import evidence_csv
from app.modules.m3_issues.rules import expand
from app.modules.m5_gaps.rules import (
    declarations,
    merge_ranges,
    missing,
)


HEADER = "record_id,title,issn,year,volume,issue,copy,binding,status,note"


def build(rows):
    lines = [HEADER]
    for row in rows:
        lines.append(",".join(row))
    return "\n".join(lines) + "\n"


def row(rid, issue, status, binding="", copy="01", note="备注", issn="2000-0001", title="合刊测试刊", year="2026"):
    return [rid, title, issn, year, "001", issue, copy, binding, status, note]


def annual(result, issn="2000-0001"):
    return next(g for g in result["gaps"] if g["issn"] == issn)


def test_declared_range_does_not_exempt_held_issue():
    rows = [row(f"A{i:03d}", str(i), "held", f"B{i}") for i in range(1, 12)]
    rows.append(row("A012", "12", "held", "B12"))
    rows.append(row("S1", "10-12", "suspended"))
    data = run(build(rows))
    g = annual(data)
    # The whole declaration is preserved for review...
    assert g["declared_suspended"] == ["10", "11", "12"]
    # ...but physically arrived issues are not exempt from the shelf or the gaps.
    assert g["suspended"] == []
    assert g["missing"] == []
    assert g["physical_in_suspension"] == 3
    assert data["books"] == 12
    assert data["suspension_books"] == 3
    assert data["final"] == []


def test_suspension_scope_still_exempts_absent_issues():
    rows = [row(f"A{i:03d}", str(i), "held", f"B{i}") for i in range(1, 11)]
    rows.append(row("S1", "11-12", "suspended"))
    data = run(build(rows))
    g = annual(data)
    assert g["suspended"] == ["11", "12"]
    assert g["missing"] == []
    assert g["status"] == "COMPLETE"
    assert data["final"] == []
    assert g["declared_ranges"] == "11—12"


def test_combined_volume_inside_suspension_counts_once():
    rows = [row(f"A{i:03d}", str(i), "held", f"B{i}") for i in range(1, 10)]
    rows.append(row("A910", "9-10", "held", "B910"))
    rows.append(row("S1", "10-12", "suspended"))
    data = run(build(rows))
    g = annual(data)
    assert g["covered"] == ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
    assert g["physical_in_suspension"] == 1
    assert data["books"] == 10
    assert data["final"] == []


def test_multiple_declarations_with_different_bounds_are_all_kept():
    rows = [row(f"A{i:03d}", str(i), "held", f"B{i}") for i in range(1, 9)]
    rows.append(row("S1", "9-12", "suspended"))
    rows.append(row("S2", "11-12", "suspended"))
    data = run(build(rows))
    g = annual(data)
    assert g["multiple_declarations"] is True
    assert g["declaration_conflict"] is True
    assert [d["record_id"] for d in g["declarations"]] == ["S1", "S2"]
    assert [d["start"] for d in g["declarations"]] == ["9", "11"]
    assert g["declared_ranges"] == "9—12"
    assert g["overlap_issues"] == ["11", "12"]
    # Both declarations remain attached as evidence for the overlapping issues.
    for issue in ("11", "12"):
        decision = next(d for d in g["issue_decisions"] if d["issue"] == issue)
        assert decision["decision"] == "suspended"
        assert set(decision["suspension_records"]) == {"S1", "S2"}
        assert "S1" in decision["basis_text"] and "S2" in decision["basis_text"]
    assert data["final"] == []


def test_physical_beats_declaration_but_declaration_stays_evident():
    rows = [row(f"A{i:03d}", str(i), "held", f"B{i}") for i in range(1, 11)]
    rows.append(row("A1112", "11-12", "held", "B1112"))
    rows.append(row("S1", "12", "suspended"))
    data = run(build(rows))
    decision = next(d for d in annual(data)["issue_decisions"] if d["issue"] == "12")
    assert decision["decision"] == "held"
    assert decision["declared_suspended"] is True
    assert decision["held_records"] == ["A1112"]
    assert decision["suspension_records"] == ["S1"]
    assert "实物" in decision["basis_text"] and "停刊声明" in decision["basis_text"]


def test_partial_arrival_keeps_rest_of_declaration_exempt():
    # Only issue 11 physically arrived inside the declared 10-12 range.  The
    # declaration is not voided as a whole: 10 and 12 remain exempt, while 11
    # is a real volume.
    rows = [row(f"A{i:03d}", str(i), "held", f"B{i}") for i in range(1, 10)]
    rows.append(row("A011", "11", "held", "B11"))
    rows.append(row("S1", "10-12", "suspended"))
    data = run(build(rows))
    g = annual(data)
    assert g["covered"] == ["1", "2", "3", "4", "5", "6", "7", "8", "9", "11"]
    assert g["suspended"] == ["10", "12"]
    assert g["effective_ranges"] == "10、12"
    assert g["missing"] == []
    assert g["physical_in_suspension"] == 1
    assert data["books"] == 10
    assert data["suspension_books"] == 1
    assert data["final"] == []


def test_supplement_task_deduplicated_by_scope():
    from app.modules.m7_supplement.rules import request_list

    gaps = [
        {"issn": "i", "title": "a", "year": "2026", "missing": ["3", "2", "3"]},
        {"issn": "i", "title": "a", "year": "2026", "missing": ["2"]},
    ]
    tasks = request_list(gaps)
    assert [(t["issn"], t["year"], t["issue"]) for t in tasks] == [
        ("i", "2026", "2"),
        ("i", "2026", "3"),
    ]


def test_rerun_same_batch_is_idempotent():
    rows = [row(f"A{i:03d}", str(i), "held", f"B{i}") for i in range(1, 10)]
    rows.append(row("S1", "10-12", "suspended"))
    text = build(rows)
    first, second = run(text), run(text)
    assert first["final"] == second["final"]
    assert first["books"] == second["books"]
    assert first["gaps"] == second["gaps"]


def test_missing_helper_unchanged_contract():
    assert missing(["1", "2"], ["3"], 4) == ["4"]
    assert missing(["S1"], [], 2) == ["1", "2"]


def test_merge_ranges():
    assert merge_ranges(["1", "2", "3", "5"]) == [
        {"start": "1", "end": "3", "issues": ["1", "2", "3"]},
        {"start": "5", "end": "5", "issues": ["5"]},
    ]
    assert merge_ranges(["S1"]) == []


def test_declarations_keep_line_and_expression():
    expanded = [
        {"record_id": "S1", "line": 4, "issue": "9-12", "issues": expand("9-12"),
         "copy": "01", "status": "suspended", "note": "停刊"},
        {"record_id": "H1", "line": 5, "issue": "1", "issues": ["1"],
         "copy": "01", "status": "held", "note": "期刊"},
    ]
    found = declarations(expanded)
    assert len(found) == 1 and found[0]["line"] == 4 and found[0]["start"] == "9"


def test_evidence_csv_exposes_suspension_and_decision_rows():
    rows = [row(f"A{i:03d}", str(i), "held", f"B{i}") for i in range(1, 11)]
    rows.append(row("S1", "11-12", "suspended"))
    result = run(build(rows))
    run_obj = {
        "id": "abcdef0123456789", "digest": "digest", "rule_version": "v",
        "result": result, "decision": "待复核", "revision": 0,
    }
    parsed = list(csv.reader(io.StringIO(evidence_csv(run_obj).lstrip("﻿"))))
    kinds = {line[3] for line in parsed[1:]}
    assert {"suspension_scope", "suspension_declaration", "issue_decision"} <= kinds
    assert all(len(line) == 7 for line in parsed)
