"""The four usage fields, kept apart.

Collapsing these is how a careful metrics file came to be wrong by ~80x:
`subagent_tokens` counts output and uncached input, and cache reads are 97.4%
of what is actually consumed. Every total in this tool is built from a `Usage`
so that the four numbers stay visible all the way to the report.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @classmethod
    def zero(cls) -> "Usage":
        return cls()

    @classmethod
    def from_payload(cls, payload: dict) -> "Usage":
        # Top-level fields only. `payload["iterations"]` repeats these numbers
        # per inference iteration; adding it would double-count.
        def field(name: str) -> int:
            value = payload.get(name, 0)
            return value if isinstance(value, int) else 0

        return cls(
            input_tokens=field("input_tokens"),
            output_tokens=field("output_tokens"),
            cache_creation_tokens=field("cache_creation_input_tokens"),
            cache_read_tokens=field("cache_read_input_tokens"),
        )

    @property
    def total(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_tokens
            + self.cache_read_tokens
        )

    @property
    def cache_read_share(self) -> float:
        return self.cache_read_tokens / self.total if self.total else 0.0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_creation_tokens + other.cache_creation_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
        )
