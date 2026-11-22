"""Campaign records. A reproduced finding requires both twin results."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class FindingStatus(str, Enum):
    hypothesis = "hypothesis"
    reproduced = "reproduced"
    rejected = "rejected"


class Impact(str, Enum):
    funds = "funds"
    bad_debt = "bad_debt"
    privilege = "privilege"
    liveness = "liveness"


class Property(BaseModel):
    id: str
    statement: str
    impact: Impact


class TwinOutcome(BaseModel):
    vulnerable_broken: bool | None = None
    patched_held: bool | None = None


class CallStep(BaseModel):
    name: str
    arg: int | None = None


class CampaignResult(BaseModel):
    id: str
    property: Property
    status: FindingStatus
    outcome: TwinOutcome
    minimized_test: str | None = None
    sequence: list[CallStep] = Field(default_factory=list)
    seed: str | None = None
    tool_versions: dict[str, str] = Field(default_factory=dict)
    medusa: str | None = None
    fork_block: int | None = None


class CorpusCase(BaseModel):
    id: str
    title: str
    domain: str
    chain_id: int
    fork_block: int | None = None
    vulnerable_ref: str | None = None
    patched_ref: str | None = None
    property: str
    impact: Impact
    source_url: str
    outcome: str

    @model_validator(mode="after")
    def metadata_cannot_claim_a_reproduction(self) -> CorpusCase:
        if self.outcome == FindingStatus.reproduced.value:
            raise ValueError("a corpus file cannot mark itself reproduced")
        if self.domain != "lending":
            raise ValueError("phase 1 corpus cases are lending cases")
        return self


def judge(outcome: TwinOutcome) -> FindingStatus:
    """Reproduced only when the vulnerable pin breaks and the patched pin holds."""
    if outcome.vulnerable_broken is True and outcome.patched_held is True:
        return FindingStatus.reproduced
    if outcome.vulnerable_broken is False and outcome.patched_held is not False:
        return FindingStatus.rejected
    return FindingStatus.hypothesis
