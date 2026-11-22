"""Import a campaign result into the open project."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from blackglass.campaign.models import CampaignResult, FindingStatus, judge
from blackglass.core.scope import ScopeError, require_path
from blackglass.core.store import Store, utc_now


class ImportError(Exception):
    """The campaign result cannot be stored."""


def import_campaign(store: Store, root: Path, result_path: Path, scope_path: str) -> CampaignResult:
    project = store.current()
    if project is None:
        raise ImportError("no project is open")
    project_id = int(project["id"])
    try:
        granted = require_path(store, project_id, root, scope_path)
    except ScopeError:
        store.log(project_id, f"import refused path={scope_path}")
        raise

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    result = CampaignResult.model_validate(payload)
    status = judge(result.outcome)
    minimized = _minimized_file(result_path, result.minimized_test)
    if status is FindingStatus.reproduced and minimized is None:
        status = FindingStatus.hypothesis
    result.status = status

    try:
        finding_id = store.add_finding(
            project_id,
            campaign_key=result.id,
            title=result.property.id,
            status=status.value,
            statement=result.property.statement,
            impact=result.property.impact.value,
            vulnerable_broken=result.outcome.vulnerable_broken,
            patched_held=result.outcome.patched_held,
        )
    except sqlite3.IntegrityError as exc:
        raise ImportError(f"{result.id} is already imported") from exc

    collected = utc_now()
    store.add_evidence(
        finding_id,
        source=result_path.name,
        sha256=_hash(result_path),
        collected_at=collected,
    )
    if minimized is not None:
        store.add_evidence(
            finding_id,
            source=minimized.name,
            sha256=_hash(minimized),
            collected_at=collected,
        )
    store.add_campaign(project_id, campaign_key=result.id, result_path=granted)
    store.log(project_id, f"import {result.id} path={granted} status={status.value}")
    return result


def _minimized_file(result_path: Path, recorded: str | None) -> Path | None:
    if recorded:
        candidate = Path(recorded)
        if candidate.is_file():
            return candidate
    sibling = result_path.parent / "Minimized.t.sol"
    if sibling.is_file():
        return sibling
    return None


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
