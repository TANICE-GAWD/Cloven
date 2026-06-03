"""
End-to-end redactor tests. The redactor composes the classifier with
the policy layer (what action to take per class), so the assertions
here are about *behaviour visible to a downstream consumer*, not
classifier internals.
"""

from guardrail.redactor import redact, HANDOFF_NOTE


def test_information_passes_through_untouched():
    raw = "ISAs have an annual allowance of £20,000 for the 2025/26 tax year."
    result = redact(raw)
    assert result.safe_text.strip() == raw
    assert not result.ledger.has_blocked()
    counts = result.ledger.to_dict()["counts"]
    assert counts["information"] == 1
    assert counts["advice"] == 0


def test_advice_is_redacted_with_handoff():
    raw = "You should put your £8,000 into the Vanguard LifeStrategy 80 fund."
    result = redact(raw)
    assert HANDOFF_NOTE in result.safe_text
    assert "Vanguard" not in result.safe_text
    counts = result.ledger.to_dict()["counts"]
    assert counts["advice"] == 1


def test_blocked_phrase_redacted_with_reason_code():
    raw = "This fund offers a guaranteed return of 7% per year."
    result = redact(raw)
    assert HANDOFF_NOTE in result.safe_text
    counts = result.ledger.to_dict()["counts"]
    assert counts["blocked"] == 1
    assert any(
        e.reason_code == "PROHIBITED_GUARANTEE"
        for e in result.ledger.entries
    )


def test_guidance_keeps_text_with_disclaimer():
    raw = ("If you're saving for a deposit in under five years, you might "
           "want to put your money into instant-access savings.")
    result = redact(raw)
    assert "instant-access savings" in result.safe_text
    assert "generic guidance" in result.safe_text.lower()


def test_mixed_paragraph():
    # Info + advice + guidance in one blob — common LLM output shape.
    raw = (
        "ISAs have an annual allowance of £20,000. "
        "You should put your £8,000 into the Vanguard LifeStrategy 80 fund. "
        "If you're saving for a deposit in under five years, you might "
        "want to put your money into instant-access savings."
    )
    result = redact(raw)
    counts = result.ledger.to_dict()["counts"]
    assert counts["information"] == 1
    assert counts["advice"] == 1
    assert counts["guidance"] == 1
    assert "Vanguard" not in result.safe_text
    assert "£20,000" in result.safe_text


def test_raw_text_preserved():
    raw = "You should buy Vanguard LifeStrategy 80."
    result = redact(raw)
    assert result.raw_text == raw  # the toggle-the-truth UX hinges on this


def test_empty_input():
    result = redact("")
    assert result.safe_text == ""
    assert result.ledger.entries == []
