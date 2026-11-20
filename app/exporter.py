import csv, io, json


def evidence_csv(run):
    out = io.StringIO()
    writer = csv.writer(out)
    result = run["result"]
    writer.writerow(["run_id", "sha256", "rule_version", "kind", "line", "reason", "evidence"])
    writer.writerow([
        run["id"], run["digest"], run["rule_version"], "manifest", "", "",
        json.dumps(
            {"balance": result["balance"], "decision": run["decision"], "revision": run["revision"]},
            ensure_ascii=False,
        ),
    ])
    # Annual suspension scope: the merged declared range, the effective (not
    # physically held) range, and every declaration that contributes to it.
    for scope in result.get("suspension_ranges", []):
        writer.writerow([
            run["id"], run["digest"], run["rule_version"], "suspension_scope",
            "", "SUSPENSION_SCOPE", json.dumps(scope, ensure_ascii=False),
        ])
        for declaration in scope.get("declarations", []):
            writer.writerow([
                run["id"], run["digest"], run["rule_version"], "suspension_declaration",
                declaration.get("line", ""), "SUSPENDED",
                json.dumps(
                    dict(declaration, issn=scope["issn"], title=scope["title"], year=scope["year"]),
                    ensure_ascii=False,
                ),
            ])
    # Per-issue reconciliation: which evidence (physical, suspension, missing
    # declaration) decided each issue.
    for annual in result.get("gaps", []):
        for decision in annual.get("issue_decisions", []):
            basis = decision.get("basis") or []
            writer.writerow([
                run["id"], run["digest"], run["rule_version"], "issue_decision",
                basis[0].get("line", "") if basis else "", decision.get("decision", ""),
                json.dumps(
                    dict(decision, issn=annual["issn"], title=annual["title"], year=annual["year"]),
                    ensure_ascii=False,
                ),
            ])
    for row in result.get("final", []):
        writer.writerow([
            run["id"], run["digest"], run["rule_version"], "result", row.get("line", ""),
            row.get("status", ""), json.dumps(row, ensure_ascii=False),
        ])
    for row in result.get("quarantine", []):
        writer.writerow([
            run["id"], run["digest"], run["rule_version"], "quarantine", row.get("line", ""),
            row["reason"], json.dumps(row, ensure_ascii=False),
        ])
    return "﻿" + out.getvalue()
