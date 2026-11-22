"""Markdown reports with reproduced findings, hypotheses, and recommendations kept apart."""

from __future__ import annotations

import json
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
    parts = [
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
    observations = _observations(store, project_id)
    if observations:
        parts.extend(["## Observations", "", observations, ""])
    return "\n".join(parts)


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


def _observations(store: Store, project_id: int) -> str:
    blocks: list[str] = []
    for row in store.recon_rows(project_id):
        try:
            body = json.loads(str(row["body"]))
        except json.JSONDecodeError:
            continue
        identity = body.get("identity") or {}
        approvals = body.get("approvals") or []
        neighbors = body.get("neighbors") or []
        unlimited = sum(1 for item in approvals if isinstance(item, dict) and item.get("unlimited"))
        discovered = [
            str(item.get("address"))
            for item in neighbors
            if isinstance(item, dict) and not item.get("granted") and item.get("address")
        ]
        blocks.append(
            "\n".join(
                [
                    f"### {identity.get('address', row['address'])}",
                    "",
                    (
                        f"chain {identity.get('chain_id', row['chain_id'])}  "
                        f"block {identity.get('block', row['block'])}  "
                        f"kind {identity.get('kind', '')}  "
                        f"verified {str(identity.get('verified', False)).lower()}"
                    ),
                    f"unlimited approvals: {unlimited}",
                    "discovered, not granted: " + (", ".join(discovered) if discovered else "none"),
                    "Token balances and verified source are indexer-current. Code, slots, native balance, transfers, and approval logs use the pinned block.",
                    "These reads are observations. They are not reproduced findings.",
                ]
            )
        )
    return "\n\n".join(blocks)


def _has_minimized_evidence(evidence: list[sqlite3.Row]) -> bool:
    return any(str(item["source"]).endswith(".sol") for item in evidence)
