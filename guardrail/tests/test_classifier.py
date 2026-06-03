"""
Table-driven classifier tests. Each row is (label, text, expected_class).

The point of these tests is twofold:
  1. Regression coverage — the classifier is the trust boundary, so it
     gets the deepest test surface in the project.
  2. Documentation by example — a hiring manager reading this file
     learns the FCA distinction without reading FCA handbooks.
"""

import pytest

from guardrail.classifier import classify_claim


INFORMATION_CASES = [
    ("isa_allowance_factual",
     "ISAs have an annual allowance of £20,000 for the 2025/26 tax year."),
    ("pension_factual",
     "Workplace pensions in the UK operate under auto-enrolment rules."),
    ("generic_market",
     "Markets can rise and fall over short time horizons."),
    ("definition",
     "A Lifetime ISA is a savings account designed for first-time buyers and retirement."),
]


GUIDANCE_CASES = [
    # Personal + action, NO specific product → guidance
    ("short_horizon_savings",
     "If your goal is a deposit in under five years, you might "
     "want to put your money into instant-access savings rather than equities."),
    # Specific product + action, NO personal addressing → guidance
    ("balance_transfer_generic",
     "Many people consolidate higher-interest debt with a balance-transfer credit card."),
    # Action only — no personal, no specific → guidance
    ("emergency_fund",
     "A common rule is to set aside three to six months of expenses before investing in equities."),
]


ADVICE_CASES = [
    ("specific_fund_advice",
     "Given your situation, I'd recommend you put your £8,000 into the "
     "Vanguard LifeStrategy 80 fund."),
    ("specific_isa_advice",
     "You should open a Cash ISA with Hargreaves Lansdown and transfer "
     "your savings into it this week."),
    ("pension_switch_advice",
     "In your case, you should switch your workplace pension into a SIPP "
     "and invest in the FTSE 100."),
]


BLOCKED_CASES = [
    ("guaranteed_return",
     "This fund offers a guaranteed return of 7% per year."),
    ("risk_free",
     "It's a risk-free way to grow your money."),
    ("no_loss",
     "You can't lose money with this strategy."),
    ("performance_promise",
     "The S&P 500 will definitely go up over the next year."),
    ("beat_market",
     "Active funds reliably beat the market over the long term."),
    ("double_money",
     "You'll double your money in three years."),
]


@pytest.mark.parametrize("label,text", INFORMATION_CASES, ids=[c[0] for c in INFORMATION_CASES])
def test_information(label, text):
    v = classify_claim(text)
    assert v.classification == "information", (
        f"[{label}] expected 'information', got '{v.classification}' "
        f"(reason={v.reason_code}); P={v.personal} S={v.specific_product} A={v.action}"
    )


@pytest.mark.parametrize("label,text", GUIDANCE_CASES, ids=[c[0] for c in GUIDANCE_CASES])
def test_guidance(label, text):
    v = classify_claim(text)
    assert v.classification == "guidance", (
        f"[{label}] expected 'guidance', got '{v.classification}' "
        f"(reason={v.reason_code}); P={v.personal} S={v.specific_product} A={v.action}"
    )


@pytest.mark.parametrize("label,text", ADVICE_CASES, ids=[c[0] for c in ADVICE_CASES])
def test_advice(label, text):
    v = classify_claim(text)
    assert v.classification == "advice", (
        f"[{label}] expected 'advice', got '{v.classification}' "
        f"(reason={v.reason_code}); P={v.personal} S={v.specific_product} A={v.action}"
    )


@pytest.mark.parametrize("label,text", BLOCKED_CASES, ids=[c[0] for c in BLOCKED_CASES])
def test_blocked(label, text):
    v = classify_claim(text)
    assert v.classification == "blocked", (
        f"[{label}] expected 'blocked', got '{v.classification}' "
        f"(reason={v.reason_code})"
    )
    assert v.prohibited_match is not None


def test_prohibited_trumps_advice():
    # A claim that is both advice AND prohibited must be blocked, not
    # downgraded to advice — block is the safer label for the ledger.
    text = ("You should buy the Vanguard LifeStrategy 80 fund — "
            "it's risk-free and guaranteed to outperform.")
    v = classify_claim(text)
    assert v.classification == "blocked"


def test_empty_text():
    v = classify_claim("")
    assert v.classification == "information"


def test_signals_exposed():
    # The verdict carries P/S/A flags so downstream code (UI, eval
    # harness) can render *why* something tripped.
    v = classify_claim("You should buy the Vanguard LifeStrategy 80 fund.")
    assert v.personal and v.specific_product and v.action
