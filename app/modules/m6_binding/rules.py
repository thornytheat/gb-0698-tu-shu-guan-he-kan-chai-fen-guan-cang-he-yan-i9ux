from app.report import report


def book_key(row):
    """Identity of one physical volume: journal + year + copy + binding."""
    return (
        row["journal_key"],
        row["year"],
        row["copy"],
        row["binding"] or row.get("record_id", ""),
    )


def is_in_suspension(row, declared_suspended):
    return any(str(issue) in declared_suspended for issue in row["issues"])


def book_count(rows):
    return len({book_key(r) for r in rows if r["status"] == "held"})


def suspension_book_count(rows, declared_by_scope):
    """Physical volumes that arrive inside a declared suspension scope.

    Such a volume is still a real binding and counts once, exactly like any
    other physical volume; it is reported separately only for review.
    """
    return len(
        {
            book_key(r)
            for r in rows
            if r["status"] == "held"
            and is_in_suspension(r, declared_by_scope.get((r["journal_key"], r["year"]), set()))
        }
    )


def apply(ctx):
    # Union every annual scope sharing an ISSN+year: an identity conflict must
    # never make one declaration disappear from the physical-volume review.
    declared_by_scope = {}
    for item in ctx.get("gaps", []):
        declared_by_scope.setdefault((item["issn"], item["year"]), set()).update(
            item["declared_suspended"]
        )
    ctx["books"] = book_count(ctx["held"])
    ctx["suspension_books"] = suspension_book_count(ctx["held"], declared_by_scope)
    ctx["balance"] = {
        "input": ctx["input_count"],
        "accepted": ctx["input_count"] - len(ctx["quarantine"]) - ctx["blank_rows"],
        "quarantined": len(ctx["quarantine"]),
        "blank": ctx["blank_rows"],
    }
    rows = [
        {"kind": "实体册", "count": ctx["books"]},
        {"kind": "停刊期实物", "count": ctx["suspension_books"]},
        {"kind": "覆盖期次", "count": sum(len(r["issues"]) for r in ctx["held"])},
        {"kind": "合刊记录", "count": sum(len(r["issues"]) > 1 for r in ctx["held"])},
        {"kind": "冲突", "count": len(ctx["binding_conflicts"])},
    ]
    return report(
        rows,
        实体册=ctx["books"],
        停刊期实物=ctx["suspension_books"],
        装订冲突=len(ctx["binding_conflicts"]),
    )
