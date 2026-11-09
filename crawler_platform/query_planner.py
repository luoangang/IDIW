"""Validated, opt-in DeepSeek terminology planning for keyword monitors."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from urllib.request import Request, urlopen


API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
KINDS = ("translations", "synonyms", "related")
LANGUAGES = ("zh", "en")
LIMITS = {"translations": 3, "synonyms": 5, "related": 3}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def validate_terms(value, original):
    if not isinstance(value, dict) or set(value) != set(KINDS):
        raise ValueError("term plan must contain translations, synonyms and related")
    if not isinstance(original, str) or not original.strip():
        raise ValueError("original keyword is required")
    output = {}
    seen = {unicodedata.normalize("NFKC", original).casefold().strip()}
    for kind in KINDS:
        languages = value[kind]
        if not isinstance(languages, dict) or set(languages) != set(LANGUAGES):
            raise ValueError(f"{kind} must contain zh and en lists")
        output[kind] = {}
        for language in LANGUAGES:
            terms = languages[language]
            if not isinstance(terms, list) or len(terms) > LIMITS[kind]:
                raise ValueError(f"{kind}.{language} exceeds its term limit")
            retained = []
            for term in terms:
                if not isinstance(term, str) or not 2 <= len(term.strip()) <= 100:
                    raise ValueError("invalid query term length")
                if term != term.strip() or re.search(r"[\x00-\x1f<>\[\]{};]", term):
                    raise ValueError("query terms must be plain phrases")
                key = unicodedata.normalize("NFKC", term).casefold().strip()
                if key not in seen:
                    seen.add(key)
                    retained.append(term)
            output[kind][language] = retained
    return output


def enabled_aliases(plan, original, manual_aliases=(), approved_terms=()):
    """Generated candidates are inactive until explicitly approved."""
    value = validate_terms(plan, original)
    aliases = list(manual_aliases)
    seen = {unicodedata.normalize("NFKC", term).casefold().strip()
            for term in (original, *aliases)}
    approved = {unicodedata.normalize("NFKC", term).casefold().strip()
                for term in approved_terms}
    for kind in ("translations", "synonyms"):
        for language in LANGUAGES:
            for term in value[kind][language]:
                key = unicodedata.normalize("NFKC", term).casefold().strip()
                if key in approved and key not in seen:
                    seen.add(key)
                    aliases.append(term)
    return aliases


def generate_terms(original, *, api_key=None, opener=urlopen, timeout=45):
    key = api_key or os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("DEEPSEEK_API_KEY is not configured")
    example = {kind: {lang: [] for lang in LANGUAGES} for kind in KINDS}
    prompt = (
        "Return JSON only, exactly matching this shape: " + json.dumps(example) + ". "
        "Plan Chinese and English search expressions for a research topic. "
        "translations must be equivalent translations; synonyms must be close alternative "
        "phrases; related means broader concepts and is not automatically enabled. "
        "For 智能体, mean autonomous or agentic AI systems, never human agents, spies, "
        "chemical or biological agents. For 具身智能, mean AI grounded in physical "
        "perception and action, not embodied cognition philosophy. Avoid ambiguous "
        "short phrases such as military agent or combat agent. Never split a multiword "
        "concept into generic single words (for example AI, military, robot). "
        "No Boolean operators, website syntax, code, or explanations. "
        "At most 3 translations, 5 synonyms, and 3 related phrases per language. "
        "Return empty arrays if there is no accurate equivalent."
    )
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Topic: " + original},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "max_tokens": 600,
        "temperature": 0,
        "stream": False,
    }
    request = Request(API_URL, data=json.dumps(payload).encode("utf-8"), headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    with opener(request, timeout=timeout) as response:
        body = json.load(response)
    content = body["choices"][0]["message"]["content"]
    if not content:
        raise ValueError("DeepSeek returned empty content")
    terms = validate_terms(json.loads(content, object_pairs_hook=_unique_object), original)
    return {"model": body.get("model", MODEL), "terms": terms,
            "usage": body.get("usage", {})}
