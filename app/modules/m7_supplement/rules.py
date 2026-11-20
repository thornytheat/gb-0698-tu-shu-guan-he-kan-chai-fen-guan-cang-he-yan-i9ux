from app.report import report


def _issue_key(value):
    text = str(value)
    return (0, int(text)) if text.isdigit() else (1, text)


def request_list(gaps):
    """One supplement task per (ISSN, year, issue).

    Suspension never appears here: the gap list has already removed physically
    held issues and effective suspension issues.  Deduplication keeps repeated
    runs (or overlapping declarations) from creating extra tasks.
    """
    tasks = {}
    for gap in gaps:
        for issue in gap["missing"]:
            key = (gap["issn"], str(gap["year"]), str(issue))
            tasks.setdefault(
                key,
                {
                    "issn": gap["issn"],
                    "title": gap["title"],
                    "year": str(gap["year"]),
                    "issue": str(issue),
                    "status": "待补录",
                },
            )
    return [
        tasks[key]
        for key in sorted(tasks, key=lambda k: (_issue_key(k[1]), k[0], _issue_key(k[2])))
    ]


def apply(ctx):
    ctx["final"] = request_list(ctx["gaps"])
    ctx["blocked"] = bool(ctx["binding_conflicts"] or ctx["identity_conflicts"])
    return report(
        ctx["final"],
        补录任务=len(ctx["final"]),
        冲突=len(ctx["binding_conflicts"]) + len(ctx["identity_conflicts"]),
    )
