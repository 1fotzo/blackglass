"""Keccak-256 as Ethereum uses it. This is not NIST SHA-3."""

from __future__ import annotations

_MASK = (1 << 64) - 1
_RATE = 136
_RC = (
    0x0000000000000001,
    0x0000000000008082,
    0x800000000000808A,
    0x8000000080008000,
    0x000000000000808B,
    0x0000000080000001,
    0x8000000080008081,
    0x8000000000008009,
    0x000000000000008A,
    0x0000000000000088,
    0x0000000080008009,
    0x000000008000000A,
    0x000000008000808B,
    0x800000000000008B,
    0x8000000000008089,
    0x8000000000008003,
    0x8000000000008002,
    0x8000000000000080,
    0x000000000000800A,
    0x800000008000000A,
    0x8000000080008081,
    0x8000000000008080,
    0x0000000080000001,
    0x8000000080008008,
)
# Rotation offsets indexed by x + 5*y.
_ROT = (
    0, 1, 62, 28, 27,
    36, 44, 6, 55, 20,
    3, 10, 43, 25, 39,
    41, 45, 15, 21, 8,
    18, 2, 61, 56, 14,
)


def keccak256(data: bytes) -> bytes:
    state = [0] * 25
    padded = _pad(data)
    for offset in range(0, len(padded), _RATE):
        block = padded[offset : offset + _RATE]
        for index in range(_RATE // 8):
            state[index] ^= int.from_bytes(block[index * 8 : (index + 1) * 8], "little")
        _permute(state)
    out = bytearray()
    for index in range(4):
        out += state[index].to_bytes(8, "little")
    return bytes(out)


def selector(signature: str) -> str:
    return "0x" + keccak256(signature.encode()).hex()[:8]


def topic(signature: str) -> str:
    return "0x" + keccak256(signature.encode()).hex()


def _pad(data: bytes) -> bytes:
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % _RATE != 0:
        padded.append(0)
    padded[-1] |= 0x80
    return bytes(padded)


def _rotl(value: int, shift: int) -> int:
    shift %= 64
    if shift == 0:
        return value & _MASK
    return ((value << shift) | (value >> (64 - shift))) & _MASK


def _permute(state: list[int]) -> None:
    for round_constant in _RC:
        columns = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20] for x in range(5)]
        mixed = [columns[(x - 1) % 5] ^ _rotl(columns[(x + 1) % 5], 1) for x in range(5)]
        for index in range(25):
            state[index] ^= mixed[index % 5]
        rotated = [0] * 25
        for x in range(5):
            for y in range(5):
                rotated[y + 5 * ((2 * x + 3 * y) % 5)] = _rotl(state[x + 5 * y], _ROT[x + 5 * y])
        for x in range(5):
            for y in range(5):
                left = rotated[((x + 1) % 5) + 5 * y]
                right = rotated[((x + 2) % 5) + 5 * y]
                state[x + 5 * y] = rotated[x + 5 * y] ^ ((~left) & right) & _MASK
        state[0] ^= round_constant
