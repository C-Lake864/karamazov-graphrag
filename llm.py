# -*- coding: utf-8 -*-
"""LLM 호출을 한 곳으로 모은다.

config.json 의 "provider" 로 google / openai 를 갈아끼운다.
나머지 코드(extract.py, agent.py, evaluate.py)는 여기만 호출한다.
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
PROVIDER = CFG.get("provider", "google")

def model_for(section: str) -> str:
    """제공자에 맞는 모델 이름을 고른다.

    config.json 에 "model"(기본 제공자용)과 "model_openai" 를 같이 적어두고,
    provider 에 따라 알아서 고른다. 제공자를 바꿀 때 모델 이름을 손으로
    바꿔 적다가 틀리는 일을 막으려는 것.
    """
    sec = CFG[section]
    if PROVIDER == "openai" and sec.get("model_openai"):
        return sec["model_openai"]
    return sec["model"]


_google = _openai = None
# 추출은 스레드 8개로 돌린다. 잠금 없이 만들면 클라이언트가 두 번 만들어지고
# 먼저 것이 닫히면서 "client has been closed" 가 난다.
_lock = threading.Lock()


def _g():
    global _google
    if _google is None:
        with _lock:
            if _google is None:
                from google import genai
                key = (os.environ.get("GOOGLE_API_KEY")
                       or os.environ.get("GEMINI_API_KEY"))
                if not key:
                    raise SystemExit(
                        "GOOGLE_API_KEY 가 없습니다. https://aistudio.google.com/apikey "
                        "에서 키를 받아 .env 에 GOOGLE_API_KEY=... 로 넣어주세요.")
                _google = genai.Client(api_key=key)
    return _google


def _o():
    global _openai
    if _openai is None:
        from openai import OpenAI
        _openai = OpenAI()
    return _openai


# ── JSON 스키마 변환 ─────────────────────────────────────────
def _to_gemini_schema(s):
    """OpenAI 형식 JSON 스키마를 Gemini 가 받는 형태로 바꾼다.

    Gemini 는 OpenAPI 3.0 부분집합만 받는다 — additionalProperties, strict 등은 빼야 한다.
    """
    if not isinstance(s, dict):
        return s
    out = {}
    for k, v in s.items():
        if k in ("additionalProperties", "strict", "$schema", "title"):
            continue
        if k == "properties":
            out[k] = {pk: _to_gemini_schema(pv) for pk, pv in v.items()}
        elif k == "items":
            out[k] = _to_gemini_schema(v)
        else:
            out[k] = v
    # Gemini 는 properties 순서를 지키면 결과가 안정적이다
    if "properties" in out and "propertyOrdering" not in out:
        out["propertyOrdering"] = list(out["properties"].keys())
    return out


def _retry(fn, tries: int = 5):
    """요청 제한(429)·일시 오류에 대비한 재시도. 96장 × 3회를 돌리려면 필요하다."""
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            transient = any(s in msg for s in
                            ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE",
                             "500", "INTERNAL", "deadline", "timeout"))
            if not transient or i == tries - 1:
                raise
            time.sleep(min(60, 2 ** i * 3) + random.uniform(0, 2))


# ── 호출 ─────────────────────────────────────────────────────
def chat_json(system: str, user: str, schema: dict, model: str) -> dict:
    """JSON 스키마를 강제해서 구조화된 결과를 받는다."""
    if PROVIDER == "google":
        from google.genai import types
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=_to_gemini_schema(schema),
            temperature=0.2,
        )
        r = _retry(lambda: _g().models.generate_content(
            model=model, contents=user, config=cfg))
        return json.loads(r.text)

    r = _o().chat.completions.create(
        model=model, reasoning_effort="low",
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        response_format={"type": "json_schema",
                         "json_schema": {"name": "out", "strict": True, "schema": schema}},
    )
    return json.loads(r.choices[0].message.content)


def chat_text(system: str, user: str, model: str) -> str:
    if PROVIDER == "google":
        from google.genai import types
        cfg = types.GenerateContentConfig(system_instruction=system, temperature=0.3)
        r = _retry(lambda: _g().models.generate_content(
            model=model, contents=user, config=cfg))
        return (r.text or "").strip()

    r = _o().chat.completions.create(
        model=model, reasoning_effort="low",
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
    )
    return r.choices[0].message.content.strip()


def embed(texts: list[str], model: str | None = None) -> list[list[float]]:
    model = model or CFG["embedding"]["model"]
    if PROVIDER == "google":
        from google.genai import types
        cfg = types.EmbedContentConfig(
            task_type="SEMANTIC_SIMILARITY",
            output_dimensionality=CFG["embedding"].get("dim", 768))
        out = []
        for i in range(0, len(texts), 100):          # Gemini 는 한 번에 100개까지
            batch = texts[i:i + 100]
            r = _retry(lambda: _g().models.embed_content(
                model=model, contents=batch, config=cfg))
            out.extend(e.values for e in r.embeddings)
        return out

    out = []
    for i in range(0, len(texts), 256):
        r = _o().embeddings.create(model=model, input=texts[i:i + 256])
        out.extend(d.embedding for d in r.data)
    return out
