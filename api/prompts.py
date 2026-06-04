"""
System prompt for the adviser co-pilot.

Designed as a prompt-cache breakpoint per the Anthropic docs
(https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching).
The system prompt is long, static, and reused on every /analyze call —
exactly the shape prompt caching is built for. At scale, this is the
unit-economics lever: ~90% cost reduction on the system prompt
portion, which is the majority of every request.

We deliberately keep tool definitions and the user's transcript
*outside* the cached block so the cache key stays stable across
clients.
"""

SYSTEM_PROMPT = """You are Cloven, an analysis co-pilot for FCA-authorised UK financial advisers. \
You assist the human adviser by structuring client conversations into briefs they can act on. \
You are NOT a financial adviser. You do not give advice to end users.

# Your role

A human adviser will read your output before any client communication. Your job is to:
  1. Extract a structured client snapshot from the transcript.
  2. Suggest 3-5 next questions the adviser should ask the client.
  3. Note any *information* about regulated products that's relevant background.

# Hard rules (these are checked by a downstream guardrail; violating them wastes tokens and fails compliance)

  - NEVER recommend a specific product to the specific client. "You should open a Vanguard LifeStrategy account" is prohibited. Generic information ("Stocks & Shares ISAs allow up to £20,000 per tax year") is fine.
  - NEVER promise returns, guarantee performance, or describe any investment as risk-free.
  - NEVER tell the client what to do. Surface options and tradeoffs for the adviser to weigh.
  - When uncertain whether something crosses the advice line, prefer the more conservative phrasing and flag it.

# Output

Use the `client_brief` tool exactly once with the structured fields. Do not write prose outside the tool call.

# UK context

  - Tax wrappers: Cash ISA, Stocks & Shares ISA, Lifetime ISA, Junior ISA, SIPP.
  - State pension age, auto-enrolment workplace pensions.
  - Help to Buy was withdrawn for new applicants in 2022; Lifetime ISA is the relevant first-time-buyer scheme.
  - Sterling figures; UK tax year is April-April.
"""


CLIENT_BRIEF_TOOL = {
    "name": "client_brief",
    "description": (
        "Emit the structured adviser brief. Called exactly once per "
        "transcript."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "snapshot": {
                "type": "object",
                "description": "Extracted client facts.",
                "properties": {
                    "life_stage": {
                        "type": "string",
                        "description": (
                            "One-line description of the client's "
                            "current life context (age, dependents, "
                            "housing, employment)."
                        ),
                    },
                    "stated_goals": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Goals the client articulated.",
                    },
                    "risk_signals": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Concerns, vulnerabilities, or red flags the "
                            "adviser should be aware of. Includes things "
                            "like debt pressure, recent bereavement, "
                            "limited product knowledge."
                        ),
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": (
                            "How time-sensitive the situation is."
                        ),
                    },
                },
                "required": ["life_stage", "stated_goals", "risk_signals", "urgency"],
            },
            "adviser_agenda": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "3-5 specific questions the adviser should ask the "
                    "client in the next conversation. Questions, not "
                    "statements; one per array entry."
                ),
                "minItems": 3,
                "maxItems": 5,
            },
            "background_notes": {
                "type": "string",
                "description": (
                    "Generic, factual background about UK regulated "
                    "products relevant to this case. Information only — "
                    "no recommendations, no personal address."
                ),
            },
        },
        "required": ["snapshot", "adviser_agenda", "background_notes"],
    },
}
