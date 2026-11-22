"""Markdown reports with reproduced findings, hypotheses, and recommendations kept apart."""

from __future__ import annotations

import sqlite3

from blackglass.core.store import Store


def render_report(store: Store, project_id: int, project_name: str) -> str:
    reproduced: list[str] = []
    hypotheses: list[str] = []
    recommendations: list[str] = []
    for finding in store.findings(project_id):
        evidence = store.evidence_for(int(finding["id"]))
        block = _finding_block(finding, evidence)
        if finding["status"] == "reproduced" and _has_minimized_evidence(evidence) and finding["patched_held"] == 1:
            reproduced.append(block)
            recommendations.append(
                f"- Retain the minimized test as a regression for: {finding['statement']}"
            )
        else:
            hypotheses.append(block)
            recommendations.append(f"- Do not treat this as confirmed: {finding['statement']}")
    if not recommendations:
        recommendations.append("- No findings are stored.")
    return "\n".join(
        [
            f"# {project_name}",
            "",
            "## Reproduced",
            "",
            "\n\n".join(reproduced) if reproduced else "None.",
            "",
            "## Hypotheses",
            "",
            "\n\n".join(hypotheses) if hypotheses else "None.",
            "",
            "## Recommendations",
            "",
            "\n".join(recommendations),
            "",
        ]
    )


def _finding_block(finding: sqlite3.Row, evidence: list[sqlite3.Row]) -> str:
    lines = [
        f"### {finding['title']}",
        "",
        finding["statement"],
        "",
        f"Status: {finding['status']}",
    ]
    for item in evidence:
        lines.append(f"- {item['source']} sha256 {item['sha256']}")
    return "\n".join(lines)


def _has_minimized_evidence(evidence: list[sqlite3.Row]) -> bool:
    return any(str(item["source"]).endswith(".sol") for item in evidence)
