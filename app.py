# -*- coding: utf-8 -*-
"""데모 화면 — 읽은 지점을 정하고 물어본다.

화면에서 신경 쓴 것
  · 읽은 지점은 한 번 정하면 질문을 몇 번 하든 유지된다 (session_state)
  · 아직 안 읽은 장은 제목을 감춘다. 장 제목 자체가 스포일러다
  · 답변 밑에 탄 경로 · 근거 삼중항 · 출처 장을 항상 같이 보여준다
"""
import json
from pathlib import Path

import streamlit as st

import agent as A
import ko_labels as KO

ROOT = Path(__file__).resolve().parent

st.set_page_config(page_title="카라마조프 관계도 도우미", page_icon="📖", layout="wide")


@st.cache_data
def load_index():
    return json.loads((ROOT / "data" / "chapter_index.json").read_text(encoding="utf-8"))


@st.cache_data
def load_aliases():
    return json.loads((ROOT / "output" / "graph.json").read_text(encoding="utf-8"))["aliases"]


@st.cache_resource
def load_graph():
    return A.load_graph()


IDX = load_index()
BY_GI = {c["global_index"]: c for c in IDX}
BOOKS = sorted({c["book_no"] for c in IDX})
BOOK_NAME = {13: "에필로그"}


def label(gi: int, read_point: int) -> str:
    """읽은 지점 뒤의 장은 제목을 감춘다."""
    c = BY_GI[gi]
    head = "에필로그" if c["book_no"] == 13 else f"{c['book_no']}편"
    base = f"{head} {c['chapter_no']}장"
    return f"{base} — {c['chapter_title']}" if gi <= read_point else base


if "read_point" not in st.session_state:
    st.session_state.read_point = 13
if "history" not in st.session_state:
    st.session_state.history = []

# ── 왼쪽: 읽은 지점 ──────────────────────────────────────────
with st.sidebar:
    st.header("📖 어디까지 읽으셨나요")

    rp = st.slider("장 번호 (전체 96장)", 1, 96, st.session_state.read_point,
                   help="읽으면서 한 칸씩 밀면 됩니다. 이 지점보다 뒤의 내용은 답변에 절대 안 나옵니다.")
    if rp != st.session_state.read_point:
        st.session_state.read_point = rp

    st.caption("편·장으로 고르기")
    c1, c2 = st.columns(2)
    cur = BY_GI[st.session_state.read_point]
    with c1:
        bk = st.selectbox("편", BOOKS, index=BOOKS.index(cur["book_no"]),
                          format_func=lambda b: BOOK_NAME.get(b, f"{b}편"),
                          label_visibility="collapsed")
    chs = [c for c in IDX if c["book_no"] == bk]
    with c2:
        ch = st.selectbox("장", [c["chapter_no"] for c in chs],
                          index=min(cur["chapter_no"], len(chs)) - 1 if bk == cur["book_no"] else 0,
                          format_func=lambda n: f"{n}장",
                          label_visibility="collapsed")
    pick = next(c["global_index"] for c in chs if c["chapter_no"] == ch)
    if st.button("이 장까지 읽음으로 설정", width="stretch"):
        st.session_state.read_point = pick
        st.rerun()

    st.divider()
    rp = st.session_state.read_point
    st.success(f"**지금: {label(rp, rp)}**\n\n(전체 96장 중 {rp}장)")
    st.caption("아직 안 읽은 장은 제목을 감춥니다 — 장 제목 자체가 스포일러라서요.")

    st.divider()
    st.subheader("🏷️ 지금까지 나온 별명")
    st.caption("읽은 데까지 등장한 호칭만 보여줍니다.")
    aliases = load_aliases()

    def entries():
        for canon, al in aliases.items():
            vis = [a["alias"] for a in al if a["display"] and a["first_index"] <= rp]
            if len(vis) < 2:
                continue
            # "Adelaïda Ivanovna Miüsov · Adelaïda Ivanovna" 처럼 긴 이름/짧은 이름
            # 쌍만 있는 것은 별명이 아니다. 정말 다른 호칭이 하나라도 있어야 보여준다.
            base = canon.lower()
            if not any(a not in base and base not in a for a in vis):
                continue
            # 짧은 호칭이 실제로 헷갈리는 것들이다(미챠·알료샤).
            # 길어질수록 "Ex-Lieutenant Karamazov" 같은 군더더기라 6개에서 끊는다.
            yield canon, sorted(set(vis), key=len)[:6]

    rows = list(entries())
    # 한국어 이름이 붙은 주요 인물을 위로. 라틴 문자가 한글보다 먼저 정렬돼서
    # 그냥 두면 정작 헷갈리는 인물들이 목록 아래로 밀린다.
    rows.sort(key=lambda kv: (KO.node(kv[0]) == kv[0], -len(kv[1]), kv[0]))
    for canon, vis in rows:
        st.markdown(f"**{KO.node(canon)}**  \n" + " · ".join(a.title() for a in vis))
    if not rows:
        st.caption("아직 별명이 여러 개 나온 인물이 없습니다.")

# ── 본문 ─────────────────────────────────────────────────────
st.title("카라마조프가의 형제들 — 관계도 도우미")
st.caption("읽으신 데까지의 내용만으로 답합니다. 뒷이야기는 근거 단계에서 아예 걸러내므로 답변 모델이 볼 수 없습니다.")

G = load_graph()
H = A.visible(G, st.session_state.read_point)
m1, m2, m3 = st.columns(3)
m1.metric("읽은 지점", f"{st.session_state.read_point} / 96장")
m2.metric("지금 보이는 인물·장소", f"{H.number_of_nodes()}개", f"전체 {G.number_of_nodes()}개")
m3.metric("지금 보이는 관계", f"{H.number_of_edges()}개", f"전체 {G.number_of_edges()}개")

st.divider()

for turn in st.session_state.history:
    with st.chat_message("user"):
        st.write(turn["q"])
        st.caption(f"{turn['rp']}장까지 읽은 시점")
    with st.chat_message("assistant"):
        st.write(turn["answer"])

        if turn["paths"]:
            # 답변에 실제로 쓰인 근거와 이어지는 경로를 먼저 보여준다.
            # 그냥 두면 Varvara·Nina 처럼 답과 무관한 곳으로 간 경로가 앞에 나온다.
            order = []
            for t in turn["triples"]:
                for n in (t["subject"], t["object"]):
                    if n not in order:
                        order.append(n)
            rank = {n: i for i, n in enumerate(order)}
            seen_to = set()
            shown = []
            for p in sorted(turn["paths"],
                            key=lambda p: (rank.get(p["to"], 999), -p["hops"])):
                if p["to"] in seen_to or p["hops"] < 1:
                    continue
                seen_to.add(p["to"])
                shown.append(p)
                if len(shown) == 4:
                    break
            with st.expander(f"🧭 탄 경로 ({len(turn['paths'])}개 중 {len(shown)}개)",
                             expanded=True):
                for p in shown:
                    lines = [f"시작: {KO.node(p['from'])}"]
                    for i, s in enumerate(p["steps"], 1):
                        a, rest = s.split(" -[", 1)
                        r, b = rest.split("]-> ", 1)
                        lines.append(f"  {i}홉  {KO.node(a)} ─[{KO.rel(r)}]→ {KO.node(b)}")
                    lines.append(f"도착: {KO.node(p['to'])}")
                    st.code("\n".join(lines), language=None)

        if turn["triples"]:
            with st.expander(f"🔗 근거 삼중항 ({len(turn['triples'])}개)"):
                for t in turn["triples"]:
                    ev = t["evidence"][0] if t["evidence"] else {}
                    if t.get("disputed"):
                        mark = "  ⚠️ 소문·부인"
                    elif t.get("unjudged") and t.get("n_hits", 1) <= 1:
                        mark = "  · 근거 약함"
                    else:
                        mark = ""
                    st.markdown(
                        f"`{t['hop']}홉` {KO.triple(t)}  ·  {ev.get('label_ko','?')}{mark}")
                    if ev.get("quote"):
                        st.caption(f"> {ev['quote']}")

        srcs = sorted({e["label_ko"] for t in turn["triples"] for e in t["evidence"]},
                      key=lambda s: (int(s.split("편")[0]) if "편" in s else 99))
        if srcs:
            st.caption("📄 출처 문서: " + " · ".join(srcs))
        with st.expander("⚙️ 어떻게 찾았나"):
            for line in turn["trace"]:
                st.text("· " + line)

q = st.chat_input("궁금한 걸 물어보세요 — 예: 알료샤의 스승은 누구야?")
if q:
    rp = st.session_state.read_point
    with st.spinner("근거를 모으는 중..."):
        res = A.ask(q, rp)
    st.session_state.history.append({
        "q": q, "rp": rp, "answer": res["answer"],
        "triples": res["triples"], "paths": res["paths"], "trace": res["trace"]})
    st.rerun()
