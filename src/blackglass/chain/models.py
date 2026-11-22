"""Recon records. An approval or a discovered address is an observation."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AddressKind(str, Enum):
    eoa = "eoa"
    contract = "contract"
    proxy = "proxy"


class SpenderKind(str, Enum):
    eoa = "eoa"
    verified = "verified"
    unverified = "unverified"
    unknown = "unknown"


class Identity(BaseModel):
    chain_id: int
    address: str
    block: int
    kind: AddressKind
    implementation: str | None = None
    admin: str | None = None
    verified: bool
    deployer: str | None = None


class TokenBalance(BaseModel):
    token: str
    symbol: str
    amount: str


class Transfer(BaseModel):
    block: int
    tx: str
    token: str | None = None
    direction: str
    counterparty: str
    amount: str


class Approval(BaseModel):
    standard: str
    token: str
    spender: str
    amount: str
    unlimited: bool
    spender_kind: SpenderKind


class Neighbor(BaseModel):
    address: str
    relation: str
    source: str
    granted: bool = False


class ReconMap(BaseModel):
    identity: Identity
    native_balance_wei: str
    native_as_of: str = "block"
    tokens: list[TokenBalance] = Field(default_factory=list)
    tokens_as_of: str = "indexer-current"
    transfers: list[Transfer] = Field(default_factory=list)
    transfers_truncated: bool = False
    approvals: list[Approval] = Field(default_factory=list)
    neighbors: list[Neighbor] = Field(default_factory=list)
    window_start: int
    block: int
