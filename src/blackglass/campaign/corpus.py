"""Load lending corpus files. They hold public metadata, not exploit code."""

from __future__ import annotations

import json
from pathlib import Path

from blackglass.campaign.models import CorpusCase


def load_cases(directory: Path) -> list[CorpusCase]:
    cases = [CorpusCase.model_validate(json.loads(path.read_text(encoding="utf-8"))) for path in sorted(directory.glob("*.json"))]
    if len(cases) < 10:
        raise ValueError(f"expected at least 10 lending cases, found {len(cases)}")
    return cases
