"""Print corpus outcomes. A broken patched twin fails the command."""

from __future__ import annotations

import json
from pathlib import Path

from blackglass.campaign.corpus import load_cases
from blackglass.campaign.models import CampaignResult, FindingStatus


def collect_rows(corpus_dir: Path, campaigns_dir: Path) -> tuple[list[tuple[str, str, str]], int]:
    rows: list[tuple[str, str, str]] = []
    exit_code = 0
    for case in load_cases(corpus_dir):
        rows.append((case.id, case.outcome, "-"))
    if campaigns_dir.is_dir():
        for path in sorted(campaigns_dir.glob("*/result.json")):
            result = CampaignResult.model_validate(json.loads(path.read_text(encoding="utf-8")))
            patched = "held" if result.outcome.patched_held is True else "broken" if result.outcome.patched_held is False else "-"
            rows.append((result.id, result.status.value, patched))
            if result.outcome.patched_held is False:
                exit_code = 1
            if result.status is FindingStatus.reproduced and not result.minimized_test:
                exit_code = 1
    return rows, exit_code


def render_score(rows: list[tuple[str, str, str]]) -> str:
    lines = [f"{'id':<28} {'outcome':<16} patched", "-" * 56]
    for case_id, outcome, patched in rows:
        lines.append(f"{case_id:<28} {outcome:<16} {patched}")
    return "\n".join(lines)
