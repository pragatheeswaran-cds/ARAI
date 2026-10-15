"""Investigation memos with a deterministic gate (frontend data plan WP7, decision D7).

After a run has succeeded and its results are published, one memo is drafted per selected customer from the case
as the API serves it: the signals with their denominators, the basket expectation, the score breakdown, the
community, the timeline facts, the wardrobing indicator. No free text, no private truth, no identifier other than
the customer's own reaches the model. The draft passes a deterministic gate before anyone sees it: every number it
cites must be a value or denominator present in the case, every panel it anchors to must exist, the action must be
one of the gate outcomes, no other customer may be named, and the sections must be short. Two failed attempts give
status `unavailable` with the reason; the UI never shows a memo that did not pass. A memo is a draft for a
reviewer, never a decision, and nothing here changes a score, a rank or a selection.

Memos run after `finish_run`, so the queue and every case are served while they arrive. Without an API key every
memo is `unavailable` by design (reason `no_api_key`) and no network call is made.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

log = logging.getLogger("arai.memo")

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"    # a declined request is retried server-side on the recommended fallback model
ATTEMPTS = 2
POOL = 4                                             # concurrent calls; the worker thread itself is single
MAX_TOKENS = 2000
PANELS = ("expected", "returns", "linked", "wardrobing")
ACTIONS = ("ESCALATE", "HOLD", "WARNING", "LOW")
LIMITS = {"summary": 600, "statement": 300, "explanation": 300, "key_evidence": 6, "alternative_explanations": 4}
CUSTOMER_ID = re.compile(r"\bW\d+-C\d+\b")
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "key_evidence", "alternative_explanations", "recommended_action"],
    "properties": {
        "summary": {"type": "string"},
        "key_evidence": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["statement", "panel", "value", "denominator"],
            "properties": {"statement": {"type": "string"}, "panel": {"type": "string", "enum": list(PANELS)},
                           "value": {"type": "number"}, "denominator": {"type": ["number", "null"]}}}},
        "alternative_explanations": {"type": "array", "items": {"type": "string"}},
        "recommended_action": {"type": "string", "enum": list(ACTIONS)},
    },
}
SYSTEM = """You draft a short investigation memo for a returns analyst about one customer account of an apparel retailer.
You are given the case exactly as the analyst's workbench shows it: measured signals with their denominators, the
basket expectation, the score breakdown by feature family, the linked-accounts group, the return timeline, the
wardrobing indicator, and the gate outcome the workbench shows. Rules:
- Use only numbers that appear in the case, exactly as given; every key_evidence value and denominator must be one of them.
- Anchor each key_evidence item to the panel it comes from: expected (basket expectation and return rates), returns
  (timeline, reason codes, claims, timing), linked (the group of linked accounts and coordinated claims), wardrobing.
- The risk score is a training reference percentile, not a probability; a link is evidence about a relationship, not guilt;
  the gate outcome is a presentation rule, not a model output. Say "suspected" or "indicator", never "fraud" as a fact.
- recommended_action is one of ESCALATE, HOLD, WARNING, LOW and should normally equal the gate outcome shown; if you
  recommend another, say why in the summary.
- Offer alternative explanations an honest customer could have.
- Never mention any customer identifier other than the case's own, and never invent a name.
- Keep it short: a summary under 600 characters, at most six evidence items, at most four alternatives."""


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat().replace("+00:00", "Z")


# ------------------------------------------------------------------ input
def _strip_ids(value, own: str, replace: dict):
    """Replace every customer identifier but the case's own with a stable 'linked account n' label, recursively."""
    if isinstance(value, dict):
        return {k: _strip_ids(v, own, replace) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_ids(v, own, replace) for v in value]
    if isinstance(value, str) and value != own and CUSTOMER_ID.fullmatch(value):
        return replace.setdefault(value, f"linked account {len(replace) + 1}")
    return value


def case_input(case: dict) -> dict:
    """The case as the model sees it: the served Case without reviews, the memo itself, and free text, with every other
    customer's identifier replaced by a neutral label. Timeline rows keep their facts and drop the sentence."""
    customer = case["customer"]
    own = customer["customer_id"]
    body = {
        "customer": {k: v for k, v in customer.items() if k not in ("workflow",)},
        "signals": case["signals"],
        "score_breakdown": case.get("score_breakdown"),
        "rules_fired": case.get("rules_fired"),
        "community": case.get("community"),
        "neighbors": case.get("neighbors"),
        "wardrobing": case.get("wardrobing"),
        "styles": [{k: v for k, v in style.items() if k != "name"} for style in case.get("styles", [])],
        "timeline": [{k: v for k, v in event.items() if k != "description"} for event in case.get("timeline", [])],
    }
    return _strip_ids(body, own, {})


def _numbers(value, out: set) -> set:
    if isinstance(value, bool):
        return out
    if isinstance(value, (int, float)):
        out.add(round(float(value), 6))
    elif isinstance(value, dict):
        for v in value.values():
            _numbers(v, out)
    elif isinstance(value, list):
        for v in value:
            _numbers(v, out)
    return out


# ------------------------------------------------------------------ gate
def gate(memo: dict, inputs: dict, customer_id: str) -> list:
    """Reasons the draft fails; empty when it passes. Deterministic and independent of the model."""
    reasons = []
    numbers = _numbers(inputs, set())
    if not isinstance(memo.get("summary"), str) or not memo["summary"].strip():
        reasons.append("summary missing")
    elif len(memo["summary"]) > LIMITS["summary"]:
        reasons.append("summary too long")
    evidence = memo.get("key_evidence")
    if not isinstance(evidence, list) or not evidence:
        reasons.append("key_evidence missing")
        evidence = []
    if len(evidence) > LIMITS["key_evidence"]:
        reasons.append("too many key_evidence items")
    for item in evidence:
        if not isinstance(item, dict):
            reasons.append("key_evidence item is not an object")
            continue
        if item.get("panel") not in PANELS:
            reasons.append(f"unknown panel {item.get('panel')!r}")
        if not isinstance(item.get("statement"), str) or len(item["statement"]) > LIMITS["statement"]:
            reasons.append("key_evidence statement missing or too long")
        for field in ("value", "denominator"):
            number = item.get(field)
            if number is None and field == "denominator":
                continue
            if isinstance(number, bool) or not isinstance(number, (int, float)) or round(float(number), 6) not in numbers:
                reasons.append(f"key_evidence {field} {number!r} is not a number of the case")
    alternatives = memo.get("alternative_explanations")
    if not isinstance(alternatives, list):
        reasons.append("alternative_explanations missing")
    else:
        if len(alternatives) > LIMITS["alternative_explanations"]:
            reasons.append("too many alternative explanations")
        if any(not isinstance(a, str) or len(a) > LIMITS["explanation"] for a in alternatives):
            reasons.append("an alternative explanation is not a short text")
    if memo.get("recommended_action") not in ACTIONS:
        reasons.append(f"recommended_action {memo.get('recommended_action')!r} is not a gate outcome")
    text = json.dumps(memo)
    others = {m for m in CUSTOMER_ID.findall(text) if m != customer_id}
    if others:
        reasons.append("names another customer")
    return reasons


# ------------------------------------------------------------------ generation
def make_client(api_key: str | None):
    """The Anthropic client, or None without a key: then every memo is unavailable by design and nothing is called."""
    if not api_key:
        return None
    import anthropic                                                        # imported only when a key exists
    return anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=120.0)


def draft(client, model: str, inputs: dict) -> tuple:
    """(memo dict or None, reason). One call with structured output and the server-side fallback for a declined request."""
    import anthropic
    try:
        response = client.beta.messages.create(
            model=model, max_tokens=MAX_TOKENS, betas=[FALLBACK_BETA], fallbacks="default", system=SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}, "effort": "medium"},
            messages=[{"role": "user", "content": "Draft the memo for this case:\n" + json.dumps(inputs, sort_keys=True)}])
    except anthropic.APIStatusError as error:
        return None, f"api_error_{error.status_code}"
    except anthropic.APIConnectionError:
        return None, "api_unreachable"
    if response.stop_reason == "refusal":
        return None, "declined"
    if response.stop_reason != "end_turn":
        return None, f"stop_{response.stop_reason}"
    text = next((block.text for block in response.content if block.type == "text"), "")
    try:
        return json.loads(text), ""
    except ValueError:
        return None, "not_json"


def memo_for(client, model: str, case: dict, attempts: int = ATTEMPTS) -> dict:
    """Draft, gate, retry once; the row to store. `status` is ok only when a draft passed the gate."""
    inputs = case_input(case)
    customer_id = case["customer"]["customer_id"]
    reason, used = "no_api_key", 0
    if client is not None:
        for used in range(1, attempts + 1):
            memo, reason = draft(client, model, inputs)
            if memo is not None:
                failed = gate(memo, inputs, customer_id)
                if not failed:
                    return {"customer_id": customer_id, "status": "ok", "attempts": used, "reason": None, "model": model,
                            "generated_at": datetime.now(timezone.utc), "memo": memo}
                reason = "gate: " + "; ".join(failed)[:300]
    return {"customer_id": customer_id, "status": "unavailable", "attempts": used, "reason": reason, "model": model,
            "generated_at": datetime.now(timezone.utc), "memo": None}


def write_memos(config, store, run_id: str, case_of, client=None) -> dict:
    """Memos for every selected customer of a succeeded run, a few at a time, each stored as soon as it is decided.

    `case_of(customer_id)` returns the case as the API serves it. Returns {"ok": n, "unavailable": n}. A failure for one
    customer gives that customer an unavailable memo; nothing here can fail the run, which already succeeded.
    """
    model = config.memo_model or DEFAULT_MODEL
    client = client if client is not None else make_client(config.anthropic_api_key)
    customers = store.selected_customer_ids(run_id)
    counts, lock = {"ok": 0, "unavailable": 0}, threading.Lock()

    def one(customer_id: str) -> None:
        try:
            row = memo_for(client, model, case_of(customer_id))
        except Exception:                                                   # noqa: BLE001  one memo, never the batch
            log.exception("run=%s customer=%s memo failed", run_id, customer_id)
            row = {"customer_id": customer_id, "status": "unavailable", "attempts": 0, "reason": "error", "model": model,
                   "generated_at": datetime.now(timezone.utc), "memo": None}
        store.write_memo(run_id, row)
        with lock:
            counts[row["status"]] += 1

    if client is None:                                                      # nothing to call: record the reason, read no case
        for customer_id in customers:
            store.write_memo(run_id, {"customer_id": customer_id, "status": "unavailable", "attempts": 0, "reason": "no_api_key",
                                      "model": model, "generated_at": datetime.now(timezone.utc), "memo": None})
            counts["unavailable"] += 1
    else:
        with ThreadPoolExecutor(max_workers=POOL) as pool:
            list(pool.map(one, customers))
    log.info("run=%s memos ok=%d unavailable=%d", run_id, counts["ok"], counts["unavailable"])
    return counts
