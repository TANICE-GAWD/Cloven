"""
Rule-based FCA-style classifier for LLM-generated financial claims.

Distinction (FCA PERG 8, Article 53 RAO):

    information : factual, generic, not addressed to an individual
                  ("ISAs have an annual allowance of £20,000")

    guidance    : narrows options without recommending a specific
                  regulated product to a specific person
                  ("if you're saving for a deposit in <5 years,
                   instant-access savings tend to suit that horizon")

    advice      : personal recommendation about a specific regulated
                  product or transaction — requires FCA-authorised
                  human adviser; MUST NOT be served by the LLM
                  ("you should put your savings into the Vanguard
                   LifeStrategy 80 fund")

Classification is the intersection of three signals:
    P = personal addressing  (you should, in your case, for you)
    S = specific product     (named fund, named provider, named scheme)
    A = action verb          (buy, invest, switch, transfer, move)

    A ∧ P ∧ S     → advice
    A ∧ ¬(P ∧ S)  → guidance        (action recommended without
                                     the specific-person + specific-
                                     product combination)
    ¬A            → information     (no action recommended at all)

Plus a hard prohibited-phrase set (guarantees, risk-free claims,
performance promises) that triggers immediate `blocked` regardless
of class — these are unsafe in any regulated context.
"""

import re
from dataclasses import dataclass
from typing import Literal

from .ledger import ClaimClass


# Hard-prohibited phrases — always blocked regardless of context.
# These map to FCA conduct-of-business rules (COBS 4: communications
# must be fair, clear, not misleading; no guaranteed-return language).
PROHIBITED_PATTERNS: list[tuple[str, str, str]] = [
    (r"\bguaranteed?\s+returns?\b", "PROHIBITED_GUARANTEE",
     "Implies guaranteed return — prohibited under COBS 4.2"),
    (r"\bguaranteed?\s+to\s+(?:grow|increase|outperform|beat|rise|improve|help|make)\b",
     "PROHIBITED_GUARANTEE",
     "Implies guaranteed outcome — prohibited under COBS 4.2"),
    (r"\bit['’]?s?\s+guaranteed\b", "PROHIBITED_GUARANTEE",
     "Implies guaranteed outcome — prohibited under COBS 4.2"),
    (r"\brisk[- ]free\b", "PROHIBITED_RISK_FREE",
     "Describes investment as risk-free — prohibited under COBS 4.2"),
    (r"\b(?:can't|cannot|won't|will not)\s+lose\b", "PROHIBITED_NO_LOSS",
     "Implies loss is impossible — prohibited under COBS 4.2"),
    (r"\b(?:will|going to|gonna)\s+(?:definitely|certainly|surely)\s+"
     r"(?:go up|increase|grow|outperform|rise|improve|help)\b",
     "PROHIBITED_PERFORMANCE_PROMISE",
     "Promises future performance — prohibited under COBS 4.5"),
    (r"\b(?:definitely|certainly|surely)\s+(?:will|going to|gonna)\s+"
     r"(?:go up|increase|grow|outperform|rise|improve|help)\b",
     "PROHIBITED_PERFORMANCE_PROMISE",
     "Promises future performance — prohibited under COBS 4.5"),
    (r"\bbeat the market\b", "PROHIBITED_PERFORMANCE_PROMISE",
     "Promises market-beating return — prohibited under COBS 4.5"),
    (r"\bdouble your money\b", "PROHIBITED_PERFORMANCE_PROMISE",
     "Specific return promise — prohibited under COBS 4.5"),
]
# Note: we deliberately do NOT block bare "tax-free growth/gains" — the
# phrase is factually correct in the context of ISAs/pensions/SIPPs.
# Blocking it produces false positives on legitimate information about
# UK tax wrappers, which is the bulk of legitimate adviser briefs.


# Personal-addressing signals — the claim is directed at this person.
# "people in your situation" is *deliberately not* a personal signal:
# pluralised hedges ("people often", "many do") are generic guidance
# language, not a recommendation to this individual.
PERSONAL_PATTERNS = [
    r"\byou should\b",
    r"\byou (?:need|ought) to\b",
    r"\b(?<!people )(?<!many )(?<!some )you (?:might|could|may) (?:want to|consider)\b",
    r"\bI(?:\s+would|['’]d)?\s+recommend\b",
    r"\bmy advice (?:to you )?is\b",
    r"\bfor you,?\b",
    r"\byour best (?:bet|option|choice)\b",
    r"\bin your (?:case|situation|position)\b",
    r"\bgiven your\b",
]


# Specific-product signals — a named regulated product, provider, or scheme.
# Word boundaries chosen so "ISA" matches but "Lisa" does not.
SPECIFIC_PRODUCT_PATTERNS = [
    # UK regulated wrappers and named schemes
    r"\b(?:Cash|Stocks?\s*&?\s*and?\s*Shares|Lifetime|Junior|Innovative\s+Finance)\s+ISA\b",
    r"\bLISA\b",
    r"\bHelp[- ]to[- ]Buy\s+ISA\b",
    r"\bSIPP\b",
    r"\b(?:workplace|personal|stakeholder)\s+pension\b",
    r"\bauto[- ]enrol(?:ment|ed)\b",
    # Named UK fund providers / platforms / lenders
    r"\b(?:Vanguard|BlackRock|iShares|Fidelity|HSBC|Legal\s*&\s*General|L&G|"
    r"Aviva|Standard\s+Life|Aegon|Scottish\s+Widows|"
    r"Hargreaves\s+Lansdown|AJ\s+Bell|interactive\s+investor|II|"
    r"Nutmeg|Moneybox|Wealthify|InvestEngine|Trading\s*212|Freetrade|"
    r"Nationwide|NatWest|Lloyds|Halifax|Santander|Barclays|Barclaycard|"
    r"Monzo|Starling|First\s+Direct|Chase|Revolut|Co[- ]?op(?:erative)?\s+Bank)\b",
    # Named fund/strategy patterns
    r"\bLifeStrategy\s*\d{1,3}\b",
    r"\bFTSE\s*(?:100|250|All[- ]Share|Global\s+All\s+Cap)\b",
    r"\bS&P\s*500\b",
    # Specific debt / mortgage products
    r"\b(?:fixed[- ]rate|tracker|offset|interest[- ]only|repayment)\s+mortgage\b",
    r"\b(?:balance[- ]transfer|0%)\s+(?:credit\s+)?card\b",
]


# Transaction-action verbs — recommending a specific action.
ACTION_PATTERNS = [
    r"\bbuy\b",
    # "invest in X" — requires a target so we don't trip on descriptive
    # uses ("investing carries risk").
    r"\binvest(?:s|ed|ing)? in\b",
    # "put X into Y" — non-greedy match within a single sentence
    r"\bput\b[^.!?]{0,40}?\binto\b",
    r"\bopen(?:s|ed|ing)? (?:an?|the)\b",
    r"\bswitch(?:es|ed|ing)?\b[^.!?]{0,40}?\b(?:to|into|over)\b",
    # "transfer ... to/into/from" — must have a target, so passive
    # descriptions ("transferred balances") don't count as actions.
    r"\btransfer(?:s|red|ring)?\b[^.!?]{0,40}?\b(?:to|into|over|from)\b",
    r"\bmove\b[^.!?]{0,30}?\b(?:money|funds|savings|cash|pension|to|into)\b",
    r"\bcontribut(?:e|es|ed|ing)\b[^.!?]{0,30}?\b(?:to|into)\b",
    r"\bremortgage\b",
    r"\bconsolidat(?:e|es|ed|ing)\b",
    r"\bwithdraw(?:s|n|al)?\b",
    r"\bsell(?:s|ing)?\b",
    # Hedged action language — guidance-flavoured but still an action recommendation.
    r"\bset aside\b",
    r"\bhold(?:ing)?\b[^.!?]{0,30}?\b(?:in|expenses|months)\b",
    r"\bbuild(?:s|ing)? (?:up |an? )?(?:emergency fund|deposit|nest egg)\b",
]


@dataclass(frozen=True)
class Verdict:
    classification: ClaimClass
    reason_code: str
    detail: str
    personal: bool
    specific_product: bool
    action: bool
    prohibited_match: str | None


def _any_match(text: str, patterns: list[str]) -> str | None:
    """Return the first matching span, or None."""
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return m.group(0)
    return None


def _prohibited_match(text: str) -> tuple[str, str, str] | None:
    """Return (span, reason_code, detail) of first prohibited hit, or None."""
    for pat, code, detail in PROHIBITED_PATTERNS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return (m.group(0), code, detail)
    return None


def classify_claim(text: str) -> Verdict:
    """
    Classify a single claim / sentence as information / guidance /
    advice / blocked.

    The function is pure and deterministic — same input always
    produces the same verdict. This is what makes the guardrail
    auditable.
    """
    prohibited = _prohibited_match(text)
    if prohibited:
        span, code, detail = prohibited
        return Verdict(
            classification="blocked",
            reason_code=code,
            detail=detail,
            personal=False,
            specific_product=False,
            action=False,
            prohibited_match=span,
        )

    personal = _any_match(text, PERSONAL_PATTERNS) is not None
    specific = _any_match(text, SPECIFIC_PRODUCT_PATTERNS) is not None
    action = _any_match(text, ACTION_PATTERNS) is not None

    if not action:
        return Verdict(
            classification="information",
            reason_code="INFORMATION_FACTUAL",
            detail="No action verb — purely informational claim.",
            personal=personal,
            specific_product=specific,
            action=False,
            prohibited_match=None,
        )

    if personal and specific:
        return Verdict(
            classification="advice",
            reason_code="ADVICE_PERSONAL_SPECIFIC_ACTION",
            detail=(
                "Personal recommendation of a specific regulated product "
                "with an action verb — regulated advice under FCA "
                "PERG 8 / Article 53. Must be delivered by an authorised "
                "human adviser."
            ),
            personal=True,
            specific_product=True,
            action=True,
            prohibited_match=None,
        )

    return Verdict(
        classification="guidance",
        reason_code="GUIDANCE_PARTIAL_SIGNAL",
        detail=(
            "Action verb present, but the (personal + specific-product) "
            "combination is incomplete. Falls under generic guidance — "
            "allowed with disclaimer."
        ),
        personal=personal,
        specific_product=specific,
        action=True,
        prohibited_match=None,
    )


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")


def classify_text(text: str) -> list[tuple[str, Verdict]]:
    """
    Split free-form LLM output into sentence-like claims and classify
    each. Returns a list of (span, verdict) preserving order.
    """
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text.strip()) if p.strip()]
    return [(p, classify_claim(p)) for p in parts]
