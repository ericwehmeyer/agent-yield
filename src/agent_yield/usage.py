"""The usage fields, kept apart -- including the two prices of a cache write.

Collapsing these is how a careful metrics file came to be wrong by ~80x:
`subagent_tokens` counts output and uncached input, and cache reads are 97.4%
of what is actually consumed. Every total in this tool is built from a `Usage`
so that the numbers stay visible all the way to the report.

`cache_creation_tokens` is one number with TWO prices behind it. The transcript
splits it into `ephemeral_1h_input_tokens` and `ephemeral_5m_input_tokens`, and
the hour costs 2.00x base input where the five minutes cost 1.25x. That is not a
rounding difference between arms: SUBAGENTS WRITE 5m AND THE PARENT WRITES 1h,
so the measured 5m share of cache writes runs 0.0% on a reading parent and
65-96% on a dispatching one. Dispatching changes the PRICE of a cache write and
not only the count, and a `Usage` that collapses the split cannot see it.

The split fields are additions, kept AFTER `cache_read_tokens` so that the four
original fields keep their positions -- but `__add__` constructs by KEYWORD, and
must keep doing so. Appending a field to a positional constructor still compiles
and still passes every test while silently zeroing the new field on every
addition, which here would read as "all writes are 1h" -- the reading parent's
profile -- and so would overprice exactly the dispatching arms this tool exists
to judge.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_5m: int = 0
    cache_creation_1h: int = 0

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

        # The TTL split lives one level down, in `cache_creation`. It is absent
        # from older transcripts and from the flat shape this tool used to
        # persist, so both halves default to 0 and the shortfall shows up as
        # `cache_creation_unattributed` rather than as a wrong price.
        split = payload.get("cache_creation")
        if not isinstance(split, dict):
            split = {}

        def sub(name: str) -> int:
            value = split.get(name, 0)
            return value if isinstance(value, int) else 0

        return cls(
            input_tokens=field("input_tokens"),
            output_tokens=field("output_tokens"),
            cache_creation_tokens=field("cache_creation_input_tokens"),
            cache_read_tokens=field("cache_read_input_tokens"),
            cache_creation_5m=sub("ephemeral_5m_input_tokens"),
            cache_creation_1h=sub("ephemeral_1h_input_tokens"),
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
    def cache_creation_unattributed(self) -> int:
        """Cache-write tokens with no TTL, and so no known price.

        Never negative: a transcript that reports a split larger than the total
        is malformed, and clamping keeps a bad line from making a report read as
        though the tool had found free tokens.
        """
        return max(0, self.cache_creation_tokens
                   - self.cache_creation_5m - self.cache_creation_1h)

    @property
    def cache_read_share(self) -> float:
        return self.cache_read_tokens / self.total if self.total else 0.0

    def __add__(self, other: "Usage") -> "Usage":
        # By keyword, deliberately. See the module docstring: a positional call
        # here survives a new field being appended and drops it in silence.
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_tokens=(self.cache_creation_tokens
                                   + other.cache_creation_tokens),
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_creation_5m=self.cache_creation_5m + other.cache_creation_5m,
            cache_creation_1h=self.cache_creation_1h + other.cache_creation_1h,
        )
