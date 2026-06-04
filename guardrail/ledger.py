"""
Compliance ledger — the audit trail attached to every LLM response.

Every claim the model surfaced is recorded with its classification, the
text span that triggered it, and the reason code. This is what makes
the guardrail defensible to a compliance officer: every output decision
is inspectable after the fact.
"""

from dataclasses import dataclass, field, asdict
from typing import Literal


ClaimClass = Literal["information", "guidance", "advice", "blocked"]


@dataclass(frozen=True)
class LedgerEntry:
    span: str
    classification: ClaimClass
    reason_code: str
    detail: str
    action: Literal["allowed", "annotated", "redacted", "blocked"]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Ledger:
    entries: list[LedgerEntry] = field(default_factory=list)

    def add(self, entry: LedgerEntry) -> None:
        self.entries.append(entry)

    def by_class(self, cls: ClaimClass) -> list[LedgerEntry]:
        return [e for e in self.entries if e.classification == cls]

    def has_blocked(self) -> bool:
        return any(e.action == "blocked" for e in self.entries)

    def to_dict(self) -> dict:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "counts": {
                "information": len(self.by_class("information")),
                "guidance": len(self.by_class("guidance")),
                "advice": len(self.by_class("advice")),
                "blocked": len(self.by_class("blocked")),
            },
        }
