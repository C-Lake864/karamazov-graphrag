# -*- coding: utf-8 -*-
"""평가 — 홉 수별 측정 + basic RAG 대조 + 경로 재현율 + 실패 층 분류.

실패를 세 층으로 가른다.
  색인(index)   기대한 삼중항이 그래프에 아예 없다      -> 추출·정제가 깨진 것
  탐색(retrieve) 그래프에는 있는데 못 가져왔다            -> 확장·허브 규칙이 깨진 것
  생성(generate) 가져왔는데 답이 틀렸다                   -> 답변 모델이 깨진 것

basic RAG 대조군도 같은 스포 차단을 받는다. 그래야 '멀티홉이 이겼는가'만 남는다.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

import networkx as nx
import numpy as np

import agent as A
import llm

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
OUT = ROOT / "output"

JUDGE_MODEL = CFG["judge"]["model"]


# ── 대조군: basic RAG ────────────────────────────────────────
def load_chunks():
    chunks = []
    for p in sorted((ROOT / "data" / "docs").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        body = re.sub(r"\s+", " ", d["text"])
        step = 2000
        for i in range(0, len(body), step):
            piece = body[i:i + step]
            if len(piece) < 200:
                continue
            chunks.append({"global_index": d["global_index"],
                           "label_ko": d["label_ko"],
                           "doc_id": d["doc_id"], "text": piece})
    return chunks


class BM25:
    """대조군 검색기. 임베딩 API를 쓰지 않으려고 BM25로 만들었다.

    basic RAG 의 표준 대조군으로도 흔히 쓰이는 방식이고,
    API 호출이 0회라 평가를 몇 번 다시 돌려도 비용이 늘지 않는다.
    """

    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = [self._tok(d) for d in docs]
        self.len = np.array([len(d) for d in self.docs], dtype=np.float32)
        self.avg = float(self.len.mean()) if len(self.len) else 1.0
        self.df = {}
        for d in self.docs:
            for w in set(d):
                self.df[w] = self.df.get(w, 0) + 1
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5))
                    for w, c in self.df.items()}
        self.tf = [Counter(d) for d in self.docs]

    @staticmethod
    def _tok(s):
        return re.findall(r"[a-z0-9À-ɏ가-힣]+", s.lower())

    def scores(self, query):
        q = self._tok(query)
        out = np.zeros(len(self.docs), dtype=np.float32)
        for w in q:
            idf = self.idf.get(w)
            if idf is None:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(w, 0)
                if f:
                    denom = f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg)
                    out[i] += idf * f * (self.k1 + 1) / denom
        return out


def basic_index():
    chunks = load_chunks()
    print(f"  basic RAG 색인(BM25) 만드는 중 ({len(chunks)}조각, API 호출 0회)...", flush=True)
    return chunks, BM25([c["text"] for c in chunks])


BASIC_SYS = """너는 소설 《카라마조프가의 형제들》을 읽는 중인 사람을 돕는다.
아래 <원문 발췌>에 있는 내용만으로 한국어 2~4문장으로 답하라.
발췌로 답할 수 없으면 "읽으신 데까지(N장)는 그 내용이 아직 나오지 않았어요."라고만 답하라.
소설에 대해 따로 알고 있는 것은 쓰지 마라. 인물 이름은 한국어 표기로 쓴다."""


def basic_rag(question, read_point, chunks, index, k=6):
    sims = index.scores(question)
    ok = np.array([c["global_index"] <= read_point for c in chunks])  # 같은 스포 차단
    sims = np.where(ok, sims, -1e9)
    top = np.argsort(-sims)[:k]
    picked = [chunks[i] for i in top if sims[i] > 0]
    if not picked:
        return f"읽으신 데까지({read_point}장)는 그 내용이 아직 나오지 않았어요.", []
    block = "\n\n".join(f'({c["label_ko"]}) {c["text"]}' for c in picked)
    text = llm.chat_text(
        BASIC_SYS,
        f"독자가 읽은 지점: {read_point}장까지\n\n<원문 발췌>\n{block}\n</원문 발췌>\n\n"
        f"질문: {question}",
        CFG["answering"]["model"])
    return text, picked


# ── 채점 ─────────────────────────────────────────────────────
JUDGE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["correct", "leaked", "reason"],
    "properties": {
        "correct": {"type": "boolean"},
        "leaked": {"type": "boolean"},
        "reason": {"type": "string"},
    },
}

JUDGE_SYS = """너는 채점자다. 어떤 질문에 대한 '기대 정답'과 '실제 답변'을 비교한다.

correct: 실제 답변이 기대 정답의 핵심을 담고 있으면 true. 표현이 달라도 된다.
         기대 정답이 "아직 나오지 않았다고 답해야 한다"인데 실제 답변이 내용을 말해버렸으면 false.
leaked:  실제 답변이 '독자가 읽은 지점보다 뒤의 줄거리'를 알려줬으면 true. 아니면 false.
         읽은 지점 안의 사실만 말했으면 leaked=false 다.
reason:  한국어 한 문장."""


def judge(item, ans):
    return llm.chat_json(
        JUDGE_SYS,
        f"질문: {item['question']}\n"
        f"독자가 읽은 지점: {item['read_point']}장\n"
        f"기대 정답: {item['expected_answer']}\n\n"
        f"실제 답변: {ans}",
        JUDGE_SCHEMA, JUDGE_MODEL)


# ── 경로 재현율 ──────────────────────────────────────────────
# 사람을 특정하지 못하는 흔한 낱말. 이게 겹쳤다고 같은 인물로 보면
# "Dmitri ↔ Captain Snegiryov" 가 "Dmitri ↔ Captain of police" 에 잘못 붙는다.
WEAK_TOKENS = {
    "captain", "father", "mother", "madame", "the", "old", "young", "little",
    "brother", "sister", "son", "daughter", "elder", "monk", "lady", "and",
    "his", "her", "their", "karamazov", "karamazovs", "fyodorovitch",
    "ivanovna", "pavlovitch", "alexandrovna",
}


def key_tokens(name: str):
    toks = {t.lower() for t in re.findall(r"[\wÀ-ɏ]+", name) if len(t) > 2}
    strong = toks - WEAK_TOKENS
    return strong or toks       # 흔한 낱말밖에 없으면 어쩔 수 없이 그대로 쓴다


def step_matched(exp, triples):
    """기대 경로의 한 칸이 실제 근거에 들어왔는가.

    관계 이름이 스키마에 없을 수 있어(SON_OF 등), 관계는 '있으면 참고'만 하고
    양 끝 인물이 실제로 한 삼중항으로 이어졌는지를 본다.
    단, 사람을 특정하는 낱말로만 잇는다 — 안 그러면 '대위'끼리 붙어버린다.
    """
    es, er, eo = exp
    ts, to = key_tokens(es), key_tokens(eo)
    for t in triples:
        a, b = key_tokens(t["subject"]), key_tokens(t["object"])
        if (ts & a and to & b) or (ts & b and to & a):
            return True
    return False


def path_recall(item, triples):
    exp = item.get("expected_path") or []
    if not exp:
        return None
    hit = sum(1 for e in exp if step_matched(e, triples))
    return hit / len(exp)


# ── 실패 층 분류 ─────────────────────────────────────────────
def classify(item, res, G_full):
    """틀린 문항이 어느 층에서 깨졌는지."""
    exp = item.get("expected_path") or []
    if not exp:
        return "generate"
    all_tr = [{"subject": s, "object": o, "relation": k}
              for s, o, k in G_full.edges(keys=True)]
    in_graph = sum(1 for e in exp if step_matched(e, all_tr))
    if in_graph < len(exp):
        return "index"
    got = sum(1 for e in exp if step_matched(e, res["triples"]))
    if got < len(exp):
        return "retrieve"
    return "generate"


# ── 실행 ─────────────────────────────────────────────────────
def main():
    gs = json.loads((ROOT / "data" / "goldenset.json").read_text(encoding="utf-8"))
    items = gs["items"]
    G_full = A.load_graph()
    chunks, index = basic_index()

    rows = []
    for it in items:
        print(f"  {it['id']} ...", flush=True)
        res = A.ask(it["question"], it["read_point"], log=True)
        jg = judge(it, res["answer"])
        ba, bp = basic_rag(it["question"], it["read_point"], chunks, index)
        jb = judge(it, ba)
        pr = path_recall(it, res["triples"])
        row = {
            "id": it["id"], "kind": it["kind"], "hops": it["hops"],
            "question": it["question"], "read_point": it["read_point"],
            "expected_answer": it["expected_answer"],
            "graph": {"answer": res["answer"], "correct": jg["correct"],
                      "leaked": jg["leaked"], "reason": jg["reason"],
                      "n_triples": len(res["triples"]),
                      "hops_used": res["hops"], "hub_opened": res["allow_hub"],
                      "starts": res["starts"], "trace": res["trace"]},
            "basic": {"answer": ba, "correct": jb["correct"],
                      "leaked": jb["leaked"], "reason": jb["reason"],
                      "chapters": sorted({c["label_ko"] for c in bp})},
            "path_recall": pr,
            "failure_layer": None if jg["correct"] else classify(it, res, G_full),
        }
        rows.append(row)

    (OUT / "eval.json").write_text(
        json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    report(rows)


def report(rows):
    def pct(xs):
        xs = [x for x in xs if x is not None]
        return f"{100 * sum(xs) / len(xs):.0f}%" if xs else "-"

    print("\n" + "=" * 68)
    print("홉 수별  GraphRAG vs basic RAG")
    print("=" * 68)
    print(f"{'구분':<14}{'문항':>4}{'GraphRAG':>11}{'basic RAG':>11}{'경로재현율':>11}")
    groups = [("1홉", lambda r: r["kind"] != "spoiler_gate" and r["hops"] == 1),
              ("2홉", lambda r: r["kind"] == "multihop" and r["hops"] == 2),
              ("3홉", lambda r: r["kind"] == "multihop" and r["hops"] == 3),
              ("대조군(1문서)", lambda r: r["kind"] == "control_singlehop"),
              ("스포 차단", lambda r: r["kind"] == "spoiler_gate")]
    for name, f in groups:
        sel = [r for r in rows if f(r)]
        if not sel:
            continue
        print(f"{name:<14}{len(sel):>4}"
              f"{pct([r['graph']['correct'] for r in sel]):>11}"
              f"{pct([r['basic']['correct'] for r in sel]):>11}"
              f"{pct([r['path_recall'] for r in sel]):>11}")
    print("-" * 68)
    print(f"{'전체':<14}{len(rows):>4}"
          f"{pct([r['graph']['correct'] for r in rows]):>11}"
          f"{pct([r['basic']['correct'] for r in rows]):>11}"
          f"{pct([r['path_recall'] for r in rows]):>11}")

    gl = [r for r in rows if r["graph"]["leaked"]]
    bl = [r for r in rows if r["basic"]["leaked"]]
    print(f"\n스포 누수:  GraphRAG {len(gl)}건 {[r['id'] for r in gl]}"
          f"   |  basic RAG {len(bl)}건 {[r['id'] for r in bl]}")

    bad = [r for r in rows if not r["graph"]["correct"]]
    if bad:
        print(f"\n틀린 {len(bad)}건의 실패 층:")
        for layer, ko in [("index", "색인 - 그래프에 아예 없음"),
                          ("retrieve", "탐색 - 있는데 못 가져옴"),
                          ("generate", "생성 - 가져왔는데 답이 틀림")]:
            sel = [r["id"] for r in bad if r["failure_layer"] == layer]
            if sel:
                print(f"  {ko:<28} {sel}")
        print()
        for r in bad:
            print(f"  [{r['id']}] {r['question']}")
            print(f"        기대: {r['expected_answer'][:55]}")
            print(f"        실제: {r['graph']['answer'][:55]}")
            print(f"        판정: {r['graph']['reason'][:70]}")
    print(f"\n-> {OUT / 'eval.json'}")


if __name__ == "__main__":
    main()
