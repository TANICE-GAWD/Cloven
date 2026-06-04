"""
Span-level redaction and disclaimer injection.

The redactor takes raw LLM output, runs it through the classifier, and
produces:

    * `safe_text`     — what's allowed to leave the server
    * `ledger`        — the audit trail of every decision
    * `raw_text`      — the unmodified original (for the "show raw" toggle)

Policy:
    advice    → redact the span entirely, replace with handoff prompt
    blocked   → redact + reason code surfaced in ledger
    guidance  → keep, but annotate with disclaimer on first occurrence
    info      → keep verbatim
"""

from dataclasses import dataclass

from .classifier import Verdict, classify_text
from .ledger import Ledger, LedgerEntry


HANDOFF_NOTE = (
    "[REDACTED — specific recommendation withheld. Cloven flags this "
    "as regulated advice; defer to your FCA-authorised adviser.]"
)

GUIDANCE_DISCLAIMER = (
    "\n\n_This is generic guidance, not a personal recommendation. "
    "Speak to your adviser before acting._"
)


@dataclass
class RedactionResult:
    safe_text: str
    raw_text: str
    ledger: Ledger

    def to_dict(self) -> dict:
        return {
            "safe_text": self.safe_text,
            "raw_text": self.raw_text,
            "ledger": self.ledger.to_dict(),
        }


def redact(raw_text: str) -> RedactionResult:
    """
    Run raw LLM output through the guardrail. Pure function — no I/O,
    no LLM calls, no global state. Deterministic given the same input.
    """
    ledger = Ledger()
    if not raw_text or not raw_text.strip():
        return RedactionResult(safe_text="", raw_text=raw_text, ledger=ledger)

    classified = classify_text(raw_text)
    safe_parts: list[str] = []
    guidance_disclaimer_added = False

    for span, verdict in classified:
        action = _action_for(verdict)
        entry = LedgerEntry(
            span=span,
            classification=verdict.classification,
            reason_code=verdict.reason_code,
            detail=verdict.detail,
            action=action,
        )
        ledger.add(entry)

        if action in ("redacted", "blocked"):
            safe_parts.append(HANDOFF_NOTE)
        elif action == "annotated":
            safe_parts.append(span)
            if not guidance_disclaimer_added:
                safe_parts.append(GUIDANCE_DISCLAIMER.strip())
                guidance_disclaimer_added = True
        else:
            safe_parts.append(span)

    return RedactionResult(
        safe_text=" ".join(safe_parts),
        raw_text=raw_text,
        ledger=ledger,
    )


def _action_for(verdict: Verdict) -> str:
    if verdict.classification == "blocked":
        return "blocked"
    if verdict.classification == "advice":
        return "redacted"
    if verdict.classification == "guidance":
        return "annotated"
    return "allowed"
