# -*- coding: utf-8 -*-
"""① 추출 — 장별로 LLM을 돌려 스키마에 맞는 삼중항을 뽑는다.

지켜야 할 것 두 가지:
  - 인용문(quote)은 본문에서 그대로 베껴야 한다. 대조해서 없으면 버린다.
  - 관계는 config.json 의 목록 안에 있는 것만 받는다.
결과는 output/extract_cache/ 에 장별로 캐시되므로 다시 돌려도 공짜다.
"""
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import llm

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
# 추출은 실행할 때마다 결과가 꽤 다르다(같은 장에서 삼중항 11개 vs 29개).
# 그래서 여러 번 돌려 합집합을 쓴다. PASS=2 로 주면 다른 칸에 저장된다.
PASS = int(os.environ.get("PASS", "1"))
CACHE = ROOT / "output" / ("extract_cache" if PASS == 1 else f"extract_cache_p{PASS}")
CACHE.mkdir(parents=True, exist_ok=True)

MODEL = llm.model_for("extraction")
CHUNK = CFG["extraction"]["chunk_chars"]
OVERLAP = 1000

REL_LIST = "\n".join(
    f"  - {k} ({v['from']} -> {v['to']}): {v['hint_en']}"
    for k, v in CFG["relation_types"].items()
)
NODE_LIST = "\n".join(f"  - {k}: {v}" for k, v in CFG["node_types"].items())

SYSTEM = f"""You extract a knowledge graph from a chapter of Dostoevsky's "The Brothers Karamazov" (Constance Garnett translation).

ALLOWED NODE TYPES:
{NODE_LIST}

ALLOWED RELATION TYPES (use the exact label, nothing else):
{REL_LIST}

RULES
0. DIRECTION MATTERS. `subject` and `object` are not interchangeable. Read each relation's description above and put the right person in the right slot. Writing the child as the subject of FATHER_OF is wrong.
1. Only extract what THIS passage states or plainly shows. Do not use knowledge of the rest of the novel. If the passage only hints or if a character merely suspects something, do not assert it as a fact.
1b. Set `disputed` to true when the passage does NOT settle the relation as fact: it is hearsay or gossip, a character asserts it and another denies it, it is a suspicion, or it is put as a question. Set it to false only when the passage presents the relation as established. When in doubt, use true.
2. Every triple needs `quote`: a VERBATIM span copied from the passage, 20-200 characters, that supports the triple. Copy it exactly, character for character. If you cannot copy a supporting span, drop the triple.
3. Use the fullest name form that appears in the passage as `name` (e.g. "Dmitri Fyodorovitch Karamazov", not "Mitya"), and list the other forms used in this passage under `aliases`.
4. Skip generic references ("the boy", "the old man", "the captain") unless no proper name is ever given for that person in the passage; never create a node whose name is a common noun.
5. Extract EVERY relation the passage supports, including ones stated only once, reported second-hand ("I am told that...", "they say that..."), or spoken by a character about someone else. Reported speech still counts as the passage showing it, as long as you can copy a supporting quote. Do not skip a relation merely because it is mentioned briefly.
"""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entities", "triples"],
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "type", "aliases"],
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": list(CFG["node_types"].keys())},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "triples": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["subject", "relation", "object", "quote", "disputed"],
                "properties": {
                    "subject": {"type": "string"},
                    "relation": {"type": "string", "enum": list(CFG["relation_types"].keys())},
                    "object": {"type": "string"},
                    "quote": {"type": "string"},
                    "disputed": {"type": "boolean"},
                },
            },
        },
    },
}


def chunks(text: str):
    if len(text) <= CHUNK:
        return [text]
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + CHUNK])
        i += CHUNK - OVERLAP
    return out


def call_llm(passage: str) -> dict:
    return llm.chat_json(SYSTEM, f"PASSAGE:\n\n{passage}", SCHEMA, MODEL)


def flat(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def norm_quote(s: str) -> str:
    """인용문 대조용. 따옴표·대시 모양 차이는 무시한다."""
    s = flat(s).lower()
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    s = s.replace("\u2014", "-").replace("\u2013", "-")
    return s


def extract_doc(doc: dict) -> dict:
    gi = doc["global_index"]
    cache_f = CACHE / f"{doc['doc_id']}.json"
    if cache_f.exists():
        return json.loads(cache_f.read_text(encoding="utf-8"))

    body = flat(doc["text"])
    haystack = norm_quote(doc["text"])

    entities, triples = [], []
    dropped = 0
    for piece in chunks(body):
        try:
            res = call_llm(piece)
        except Exception as e:  # 한 조각 실패가 전체를 멈추지 않게
            print(f"  ! {doc['doc_id']} 조각 실패: {type(e).__name__}: {e}", flush=True)
            continue
        entities.extend(res.get("entities", []))
        for t in res.get("triples", []):
            # === 인용문 대조: 본문에 없는 근거는 버린다 ===
            if norm_quote(t["quote"]) not in haystack:
                dropped += 1
                continue
            t["first_revealed_index"] = gi
            t["doc_id"] = doc["doc_id"]
            t["label_ko"] = doc["label_ko"]
            triples.append(t)

    out = {
        "doc_id": doc["doc_id"],
        "global_index": gi,
        "label_ko": doc["label_ko"],
        "entities": entities,
        "triples": triples,
        "dropped_unquoted": dropped,
    }
    cache_f.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main():
    docs = [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((ROOT / "data" / "docs").glob("*.json"))]
    only = sys.argv[1:]
    if only:
        docs = [d for d in docs if d["doc_id"] in only or str(d["global_index"]) in only]

    todo = [d for d in docs if not (CACHE / f"{d['doc_id']}.json").exists()]
    print(f"문서 {len(docs)}건 / 새로 뽑을 것 {len(todo)}건 (모델 {MODEL})", flush=True)

    done = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(extract_doc, d): d for d in docs}
        for f in as_completed(futs):
            r = f.result()
            done += 1
            if done % 10 == 0 or done == len(docs):
                print(f"  {done}/{len(docs)}", flush=True)

    tri = ent = drop = 0
    for d in docs:
        r = json.loads((CACHE / f"{d['doc_id']}.json").read_text(encoding="utf-8"))
        tri += len(r["triples"]); ent += len(r["entities"]); drop += r["dropped_unquoted"]
    print(f"\n삼중항 {tri}개 / 개체 언급 {ent}개")
    print(f"인용문 대조 실패로 버린 삼중항: {drop}개 "
          f"({drop / max(1, tri + drop) * 100:.1f}%)")


if __name__ == "__main__":
    main()
