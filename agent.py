# -*- coding: utf-8 -*-
"""③④⑤ 시작 개체 찾기 -> n홉 확장 -> 근거만으로 답변 (경로 기록)

LangGraph 상태 흐름:

    find_start ──> expand ──> judge ──┬─(근거 모자람 & 더 넓힐 수 있음)─> expand
                                      └─(충분하거나 한계)─> answer

스포 차단은 expand 안에서 일어난다. '읽은 지점보다 뒤에 드러난' 노드와 엣지를
그래프에서 아예 빼고 탐색하므로, 답변 모델은 그 내용을 볼 수가 없다.
"""
from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path
from typing import Annotated, TypedDict

import networkx as nx
from langgraph.graph import END, StateGraph

import llm

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
RET = CFG["retrieval"]
OUT = ROOT / "output"

ANSWER_MODEL = CFG["answering"]["model"]
LINK_MODEL = CFG["extraction"]["model"]

# 한국어 질문에 나오는 이름 -> 그래프의 대표 이름.
# 자주 나오는 인물은 사전으로 바로 붙이고, 못 붙인 것만 LLM에 맡긴다.
KO_SEED = {
    "알료샤": "Alexey Fyodorovitch Karamazov", "알렉세이": "Alexey Fyodorovitch Karamazov",
    "드미트리": "Dmitri Fyodorovitch Karamazov", "미챠": "Dmitri Fyodorovitch Karamazov",
    "미탸": "Dmitri Fyodorovitch Karamazov", "미첸카": "Dmitri Fyodorovitch Karamazov",
    "이반": "Ivan Fyodorovitch Karamazov",
    "표도르": "Fyodor Pavlovitch Karamazov", "표도르 파블로비치": "Fyodor Pavlovitch Karamazov",
    "스메르쟈코프": "Smerdyakov", "스메르댜코프": "Smerdyakov",
    "그루셴카": "Grushenka", "그루샤": "Grushenka", "아그라페나": "Grushenka",
    "카체리나": "Katerina Ivanovna", "카테리나": "Katerina Ivanovna", "카챠": "Katerina Ivanovna",
    "조시마": "Father Zossima", "조시마 장로": "Father Zossima",
    "그리고리": "Grigory", "마르파": "Marfa Ignatyevna",
    "라키친": "Rakitin", "라키틴": "Rakitin",
    "일류샤": "Ilusha", "일루샤": "Ilusha",
    "스네기료프": "Captain Snegiryov", "대위": "Captain Snegiryov",
    "콜랴": "Kolya Krassotkin", "크라소트킨": "Kolya Krassotkin",
    "리자": "Lise", "리제": "Lise",
    "미우소프": "Pyotr Alexandrovitch Miüsov",
    "페라폰트": "Father Ferapont",
    "페츄코비치": "Fetyukovitch",
    "페르호친": "Pyotr Ilyitch Perhotin",
    "수도원": "the Monastery", "암자": "the Hermitage",
    "모크로예": "Mokroe",
}


# ── 그래프 ───────────────────────────────────────────────────
def load_graph() -> nx.MultiDiGraph:
    return nx.read_graphml(OUT / "graph.graphml")


def load_aliases() -> dict:
    return json.loads((OUT / "graph.json").read_text(encoding="utf-8")).get("aliases", {})


def visible(G: nx.MultiDiGraph, read_point: int) -> nx.MultiDiGraph:
    """읽은 지점까지 드러난 것만 남긴 그래프. ← 스포 차단의 전부."""
    H = nx.MultiDiGraph()
    for n, d in G.nodes(data=True):
        if int(d.get("first_revealed_index", 1)) <= read_point:
            H.add_node(n, **d)
    for s, o, k, d in G.edges(keys=True, data=True):
        if s in H and o in H and int(d.get("first_revealed_index", 1)) <= read_point:
            H.add_edge(s, o, key=k, **d)
    return H


# ── 상태 ─────────────────────────────────────────────────────
class State(TypedDict, total=False):
    _G: object          # 읽은 지점까지만 남긴 그래프 (LangGraph가 버리지 않게 선언해 둔다)
    question: str
    read_point: int
    starts: list
    hops: int
    allow_hub: bool
    triples: list
    paths: list
    answer: str
    trace: list


# ── ③ 시작 개체 찾기 ─────────────────────────────────────────
def find_start(state: State) -> State:
    q = state["question"]
    G = state["_G"]
    names = list(G.nodes)

    found = []
    for ko, canon in KO_SEED.items():
        if ko in q and canon in G and canon not in found:
            found.append(canon)

    # 사전으로 못 붙였으면 LLM에게 후보 목록을 주고 고르게 한다
    if not found and names:
        listing = "\n".join(f"- {n}" for n in names[:400])
        try:
            res = llm.chat_json(
                "아래 목록은 어떤 지식 그래프에 있는 개체 이름이다. "
                "한국어 질문이 가리키는 개체를 목록에서 골라 답하라. "
                "목록에 없으면 빈 배열로 답하라. 지어내지 마라.\n\n" + listing,
                q,
                {"type": "object", "required": ["names"],
                 "properties": {"names": {"type": "array", "items": {"type": "string"}}}},
                LINK_MODEL,
            )
            for n in res.get("names", []):
                if n in G and n not in found:
                    found.append(n)
        except Exception as e:
            state.setdefault("trace", []).append(f"개체 연결 실패: {e}")

    tr = state.get("trace", [])
    tr.append(f"시작 개체: {found or '못 찾음'}")
    return {**state, "starts": found, "trace": tr,
            "hops": RET["max_hops"], "allow_hub": False}


# ── ④ n홉 확장 ───────────────────────────────────────────────
def expand(state: State) -> State:
    G: nx.MultiDiGraph = state["_G"]
    read_point = state["read_point"]
    starts = state["starts"]
    max_hops = state["hops"]
    allow_hub = state["allow_hub"]

    triples, paths = [], []
    seen_edge = set()

    for s0 in starts:
        if s0 not in G:
            continue
        parent = {s0: None}
        dq = deque([(s0, 0)])
        while dq:
            u, d = dq.popleft()
            if d >= max_hops:
                continue
            # 허브는 '경유'하지 않는다. 시작점이면 통과시킨다.
            if not allow_hub and d > 0 and int(G.nodes[u].get("is_hub", 0)):
                continue
            for a, b, k, ed in list(G.in_edges(u, keys=True, data=True)) + \
                               list(G.out_edges(u, keys=True, data=True)):
                v = b if a == u else a
                sig = (a, k, b)
                if sig not in seen_edge:
                    seen_edge.add(sig)
                    # 근거도 읽은 지점까지만 남긴다. 엣지가 보인다고 해서 그 엣지에 달린
                    # 뒷장 인용문까지 보여주면 거기서 샌다.
                    ev = [x for x in json.loads(ed.get("evidence", "[]"))
                          if x.get("global_index", 1) <= read_point]
                    if not ev:
                        continue
                    triples.append({
                        "subject": a, "relation": k, "object": b,
                        "hop": d + 1,
                        "first_revealed_index": int(ed.get("first_revealed_index", 1)),
                        # 읽은 데까지의 근거가 전부 '소문·부인'이면 확정된 사실이 아니다.
                        "disputed": all(x.get("disputed") is True for x in ev),
                        # 추출을 3회 돌리는 동안 이 삼중항이 몇 번 뽑혔는가.
                        # 추출은 분산이 커서, 한 번만 뽑힌 관계는 우연일 수 있다.
                        "n_hits": max((x.get("n_passes", 1) for x in ev), default=1),
                        # 소문인지 확정인지 아무 회차도 판정하지 않았는가
                        "unjudged": all(x.get("disputed") is None for x in ev),
                        "evidence": ev,
                    })
                if v not in parent:
                    parent[v] = (u, a, k, b)
                    dq.append((v, d + 1))
        # 실제로 탄 경로 복원
        for node, par in parent.items():
            if par is None:
                continue
            chain, cur = [], node
            while parent.get(cur):
                u, a, k, b = parent[cur]
                chain.append(f"{a} -[{k}]-> {b}")
                cur = u
            paths.append({"from": s0, "to": node, "hops": len(chain),
                          "steps": list(reversed(chain))})

    # 홉이 가까운 것, 여러 회차에서 겹쳐 나온 것, 근거 장이 많은 것 순으로
    triples.sort(key=lambda t: (t["hop"], -t["n_hits"], -len(t["evidence"])))
    triples = triples[: RET["max_triples"]]

    tr = state.get("trace", [])
    tr.append(f"{max_hops}홉 확장 (허브 경유 {'허용' if allow_hub else '금지'}) "
              f"-> 삼중항 {len(triples)}개")
    return {**state, "triples": triples, "paths": paths, "trace": tr}


# ── 근거가 충분한가 ──────────────────────────────────────────
def judge(state: State) -> State:
    return state


def route(state: State) -> str:
    n = len(state.get("triples", []))
    if n >= 3:
        return "answer"
    if not state.get("allow_hub") or state["hops"] < RET["fallback_hops"]:
        return "widen"
    return "answer"


def widen(state: State) -> State:
    tr = state.get("trace", [])
    if not state["allow_hub"]:
        tr.append("근거 3개 미만 -> 허브 경유를 열어준다")
        return {**state, "allow_hub": True, "trace": tr}
    tr.append(f"근거 여전히 모자람 -> {RET['fallback_hops']}홉까지 넓힌다")
    return {**state, "hops": RET["fallback_hops"], "trace": tr}


# ── ⑤ 근거만으로 답변 ────────────────────────────────────────
ANSWER_SYS = """너는 소설 《카라마조프가의 형제들》을 읽는 중인 사람을 돕는다.

절대 규칙
1. 아래 <근거>에 있는 내용만으로 답한다. 소설에 대해 네가 따로 알고 있는 것은 전부 잊어라.
2. <근거>로 답할 수 없으면 반드시 이렇게 답한다:
   "읽으신 데까지(N장)는 그 내용이 아직 나오지 않았어요."
   비슷한 걸로 둘러대거나, 뒷부분을 암시하거나, 추측하지 마라.
3. 근거마다 <확정> / <소문·부인 (확정 아님)> / <확정 아님 (근거 약함)> 표시가 붙어 있다.
   <확정>이 아닌 것은 절대 사실처럼 쓰지 마라. "~라는 말이 오갔다",
   "아직 확실하지 않다" 처럼 확정되지 않았음이 드러나게 쓴다.
   <소문·부인>인 것은 절대로 사실처럼 쓰지 마라. 반드시 "~라는 말이 오갔다",
   "~라는 소리를 듣고 부인했다" 처럼 확정되지 않았다는 것이 드러나게 쓴다.
   질문이 "A가 맞아?"인데 근거가 <소문·부인>뿐이면, "아직 확정되지 않았고
   이런 말이 오갔다"까지만 답한다.
4. 한국어로, 2~4문장으로 답한다. 인물 이름은 한국어 표기로 쓴다
   (Alexey Fyodorovitch Karamazov -> 알료샤, Grushenka -> 그루셴카 처럼).
5. 근거에 없는 장 번호나 사건을 지어내지 마라.
"""


def answer(state: State) -> State:
    rp = state["read_point"]
    ts = state.get("triples", [])
    if not ts:
        tr = state.get("trace", [])
        tr.append("근거 0개 -> 모른다고 답함")
        return {**state,
                "answer": f"읽으신 데까지({rp}장)는 그 내용이 아직 나오지 않았어요.",
                "trace": tr}

    lines = []
    for i, t in enumerate(ts, 1):
        ev = t["evidence"][0] if t["evidence"] else {}
        if t.get("disputed"):
            mark = "소문·부인 (확정 아님)"
        elif t.get("unjudged") and t.get("n_hits", 1) <= 1:
            # 확정인지 소문인지 판정된 적도 없고, 딱 한 번만 뽑힌 관계.
            # 이런 것을 사실로 단정하면 스포일러가 된다.
            mark = "확정 아님 (근거 약함)"
        else:
            mark = "확정"
        lines.append(
            f'[{i}] {t["subject"]} -[{t["relation"]}]-> {t["object"]}  <{mark}>\n'
            f'    출처: {ev.get("label_ko", "?")}\n'
            f'    원문: "{ev.get("quote", "")}"')
    block = "\n".join(lines)

    text = llm.chat_text(
        ANSWER_SYS,
        f"독자가 읽은 지점: {rp}장까지\n\n<근거>\n{block}\n</근거>\n\n"
        f"질문: {state['question']}",
        ANSWER_MODEL,
    )
    tr = state.get("trace", [])
    tr.append(f"근거 {len(ts)}개로 답변 생성")
    return {**state, "answer": text, "trace": tr}


# ── 그래프 조립 ──────────────────────────────────────────────
def build_app():
    g = StateGraph(State)
    g.add_node("find_start", find_start)
    g.add_node("expand", expand)
    g.add_node("judge", judge)
    g.add_node("widen", widen)
    g.add_node("answer", answer)
    g.set_entry_point("find_start")
    g.add_edge("find_start", "expand")
    g.add_edge("expand", "judge")
    g.add_conditional_edges("judge", route, {"widen": "widen", "answer": "answer"})
    g.add_edge("widen", "expand")
    g.add_edge("answer", END)
    return g.compile()


_APP = None
_GRAPH = None


def ask(question: str, read_point: int, log: bool = True) -> dict:
    global _APP, _GRAPH
    if _APP is None:
        _APP = build_app()
    if _GRAPH is None:
        _GRAPH = load_graph()

    H = visible(_GRAPH, read_point)
    state = {"question": question, "read_point": read_point,
             "trace": [f"읽은 지점 {read_point}장 -> 보이는 노드 {H.number_of_nodes()}개 / "
                       f"엣지 {H.number_of_edges()}개 (전체 {_GRAPH.number_of_nodes()}/"
                       f"{_GRAPH.number_of_edges()})"],
             "_G": H}
    out = _APP.invoke(state, {"recursion_limit": 25})
    res = {k: out.get(k) for k in
           ("question", "read_point", "starts", "hops", "allow_hub",
            "triples", "paths", "answer", "trace")}
    if log:
        OUT.mkdir(exist_ok=True)
        with (OUT / "runs.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
    return res


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "알료샤의 아버지는 누구야?"
    rp = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    r = ask(q, rp)
    print("\n".join("  · " + t for t in r["trace"]))
    print("\n답변:", r["answer"])
    print("\n근거:")
    for t in r["triples"][:6]:
        ev = t["evidence"][0] if t["evidence"] else {}
        print(f'  {t["hop"]}홉  {t["subject"]} -[{t["relation"]}]-> {t["object"]}'
              f'   ({ev.get("label_ko","?")})')
