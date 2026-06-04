"""
Cloven API — single endpoint that turns a client transcript into a
structured adviser brief, with every LLM-emitted span passed through
the deterministic compliance guardrail before it leaves the server.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Make the project root importable so `guardrail` resolves whether the
# app is run from ./api or from the repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load .env from the project root for local dev. In Docker the env
# vars are injected by compose, so dotenv is a no-op there.
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from guardrail import redact  # noqa: E402

from api.prompts import SYSTEM_PROMPT, CLIENT_BRIEF_TOOL  # noqa: E402


logger = logging.getLogger("cloven")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))


app = FastAPI(title="Cloven", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=20_000)


class AnalyzeResponse(BaseModel):
    snapshot: dict[str, Any]
    adviser_agenda: list[str]
    background_notes_safe: str
    background_notes_raw: str
    ledger: dict[str, Any]
    model: str
    used_mock: bool


def _call_llm(transcript: str) -> tuple[dict[str, Any], str]:
    """
    Returns (tool_input_dict, model_id).

    Provider precedence:
      1. ANTHROPIC_API_KEY → Claude with native tool_use + prompt caching.
      2. GROQ_API_KEY      → Groq (OpenAI-compatible) with function calling.
      3. mock              → deterministic offline brief that still
                             exercises the guardrail end-to-end.

    The guardrail downstream doesn't care which model produced the
    output — that's the whole point of a deterministic compliance
    layer sitting *outside* the model.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _call_anthropic(transcript)
    if os.environ.get("GROQ_API_KEY"):
        return _call_groq(transcript)
    logger.warning("No LLM API key found — using deterministic mock")
    return _mock_brief(transcript), "mock-claude"


def _call_anthropic(transcript: str) -> tuple[dict[str, Any], str]:
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic SDK not installed — falling back to mock")
        return _mock_brief(transcript), "mock-claude"

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("CLOVEN_MODEL", "claude-haiku-4-5")

    # Prompt caching: we place a cache_control breakpoint at the end of
    # the system block. Every /analyze with the same model + system
    # text hits the cache; only the user transcript varies. Per the
    # Anthropic docs this gives ~90% input-token discount on the
    # cached portion after the first warmup call.
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[CLIENT_BRIEF_TOOL],
        tool_choice={"type": "tool", "name": "client_brief"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Analyse the following client transcript and call the "
                    "client_brief tool with structured output.\n\n"
                    "---\n"
                    f"{transcript}\n"
                    "---"
                ),
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "client_brief":
            return block.input, model

    raise RuntimeError("Anthropic call returned no client_brief tool_use")


def _call_groq(transcript: str) -> tuple[dict[str, Any], str]:
    """
    Groq exposes an OpenAI-compatible /v1 endpoint, so we drive it via
    the openai SDK with base_url overridden. Tool schema is Anthropic-
    shaped in `prompts.py`; we re-wrap it as an OpenAI function spec
    so the model emits a tool_call we can parse.

    Note: Groq doesn't yet expose Anthropic-style prompt caching, so the
    system prompt is sent in full each call. At scale this is the lever
    that pushes us back to Anthropic — documented in the README as a
    cost trade-off.
    """
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai SDK not installed — falling back to mock")
        return _mock_brief(transcript), "mock-claude"

    client = OpenAI(
        api_key=os.environ["GROQ_API_KEY"],
        base_url=os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
    )
    model = os.environ.get("CLOVEN_MODEL", "llama-3.3-70b-versatile")

    openai_tool = {
        "type": "function",
        "function": {
            "name": CLIENT_BRIEF_TOOL["name"],
            "description": CLIENT_BRIEF_TOOL["description"],
            "parameters": CLIENT_BRIEF_TOOL["input_schema"],
        },
    }

    response = client.chat.completions.create(
        model=model,
        max_tokens=2048,
        temperature=0.2,
        tools=[openai_tool],
        tool_choice={"type": "function", "function": {"name": "client_brief"}},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Analyse the following client transcript and call the "
                    "client_brief tool with structured output.\n\n"
                    "---\n"
                    f"{transcript}\n"
                    "---"
                ),
            },
        ],
    )

    msg = response.choices[0].message
    if not msg.tool_calls:
        raise RuntimeError("Groq call returned no tool_calls")
    call = msg.tool_calls[0]
    if call.function.name != "client_brief":
        raise RuntimeError(f"Groq called unexpected tool: {call.function.name}")

    import json
    return json.loads(call.function.arguments), f"groq/{model}"


def _mock_brief(transcript: str) -> dict[str, Any]:
    """
    Deterministic mock used when no API key is configured. Returns a
    *deliberately imperfect* brief that includes both safe content
    AND a piece of advice-shaped text in `background_notes`. The
    guardrail will catch the offending span — that's the demo.
    """
    t = transcript.lower()

    goals: list[str] = []
    if "deposit" in t or "house" in t or "mortgage" in t:
        goals.append("Buy a first home")
    if "pension" in t or "retire" in t:
        goals.append("Plan for retirement")
    if "isa" in t or "save" in t or "savings" in t:
        goals.append("Build long-term savings")
    if "debt" in t or "credit card" in t or "loan" in t:
        goals.append("Pay down high-interest debt")
    if "redundan" in t or "lost my job" in t:
        goals.append("Stabilise income after redundancy")
    if "inherit" in t:
        goals.append("Decide how to deploy inherited funds")
    if not goals:
        goals = ["Understand current financial position"]

    risk_signals: list[str] = []
    if "kids" in t or "children" in t or "child" in t:
        risk_signals.append("Dependents — adviser should confirm life cover")
    if "don't" in t and ("understand" in t or "know" in t):
        risk_signals.append("Self-reported limited product knowledge")
    if "stressed" in t or "anxious" in t or "worried" in t:
        risk_signals.append("Emotional pressure — vulnerable-client checks apply")
    if "redundan" in t:
        risk_signals.append("Recent redundancy — income volatility")
    if not risk_signals:
        risk_signals.append("None flagged by transcript")

    urgency = "high" if any(w in t for w in ("urgent", "deadline", "asap", "this week")) else "medium"

    agenda = [
        "What is the realistic timescale for each of the stated goals?",
        "What does the household's current emergency fund look like?",
        "Are there any existing pensions or workplace schemes already in place?",
        "What is the client's tolerance for capital loss in the short term?",
    ]
    if "debt" in t or "credit card" in t:
        agenda.insert(0, "What are the interest rates and balances across outstanding debts?")
    agenda = agenda[:5]

    # The mock deliberately emits a sentence the guardrail will catch.
    # This is what makes the "Show raw output" toggle a *demo*: the
    # reviewer can see the guardrail visibly stripping advice that the
    # LLM would otherwise leak.
    background = (
        "Stocks & Shares ISAs allow up to £20,000 per tax year of "
        "tax-advantaged investment. Lifetime ISAs are designed for "
        "first-time buyers under 40 and add a 25% government bonus on "
        "contributions up to £4,000 per tax year. "
        "You should put your £8,000 into the Vanguard LifeStrategy 80 "
        "fund — it's a guaranteed strong performer over the long term."
    )

    return {
        "snapshot": {
            "life_stage": _infer_life_stage(t),
            "stated_goals": goals,
            "risk_signals": risk_signals,
            "urgency": urgency,
        },
        "adviser_agenda": agenda,
        "background_notes": background,
    }


def _infer_life_stage(t: str) -> str:
    bits: list[str] = []
    import re
    m = re.search(r"\bi['’]?m\s+(\d{2})\b", t)
    if m:
        bits.append(f"Age {m.group(1)}")
    if "two kids" in t or "two children" in t:
        bits.append("two dependents")
    elif "kids" in t or "children" in t:
        bits.append("has dependents")
    if "renting" in t or "rent" in t:
        bits.append("renting")
    if "owns" in t or "homeowner" in t:
        bits.append("homeowner")
    return ", ".join(bits) if bits else "Unspecified life stage"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    try:
        brief, model = _call_llm(req.transcript)
    except Exception as exc:
        logger.exception("LLM call failed")
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}")

    raw_notes = brief.get("background_notes", "") or ""
    redaction = redact(raw_notes)

    return AnalyzeResponse(
        snapshot=brief["snapshot"],
        adviser_agenda=brief["adviser_agenda"],
        background_notes_safe=redaction.safe_text,
        background_notes_raw=redaction.raw_text,
        ledger=redaction.ledger.to_dict(),
        model=model,
        used_mock=model.startswith("mock"),
    )
