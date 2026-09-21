# -*- coding: utf-8 -*-
"""골든셋 생성기.

근거 인용문을 손으로 적지 않는다. 정규식으로 원문에서 직접 뽑아내고,
못 찾으면 그 자리에서 실패시킨다. 지어낸 근거가 섞일 수 없게 하기 위함.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = {}
for p in sorted((ROOT / "data" / "docs").glob("*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    DOCS[d["global_index"]] = d


def quote(gi: int, pattern: str, before: int = 0, after: int = 170) -> dict:
    """gi번 장에서 pattern을 찾아 앞뒤를 붙인 인용문을 돌려준다."""
    d = DOCS[gi]
    flat = re.sub(r"\s+", " ", d["text"])  # 줄바꿈 때문에 못 찾는 일을 막는다
    m = re.search(pattern, flat, re.I | re.S)
    if not m:
        raise SystemExit(f"[실패] {gi}장에서 못 찾음: {pattern}")
    s = max(0, m.start() - before)
    e = min(len(flat), m.end() + after)
    text = flat[s:e].strip()
    return {
        "doc_id": d["doc_id"],
        "global_index": gi,
        "label_ko": d["label_ko"],
        "quote": text,
    }


G = []


def item(qid, hops, question, read_point, answer, path, evidence, why_path, kind="multihop"):
    G.append({
        "id": qid,
        "kind": kind,
        "hops": hops,
        "question": question,
        "read_point": read_point,
        "expected_answer": answer,
        "expected_path": path,
        "why_path": why_path,
        "evidence": evidence,
    })


# ---------------- 1홉 ----------------
item("G01", 1,
     "알료샤의 아버지는 누구야?", 5,
     "표도르 파블로비치 카라마조프",
     [["Fyodor Pavlovitch Karamazov", "FATHER_OF", "Alexey (Alyosha)"]],
     [quote(1, r"Alexey Fyodorovitch Karamazov was the third son of Fyodor Pavlovitch")],
     "부자 관계는 1편 1장 첫 문장에 그대로 나온다. 1홉 기준선.")

item("G02", 1,
     "조시마 장로는 어디에 머물고 있어?", 13,
     "수도원 안의 암자(hermitage)",
     [["Zossima", "LIVES_AT", "the monastery hermitage"]],
     [quote(4, r"the elder Zossima, who was living in the monastery hermitage")],
     "장소 관계 1홉. Place 노드가 제대로 잡히는지 본다.")

item("G03", 1,
     "그리고리는 누구 집에서 일하는 하인이야?", 6,
     "표도르 파블로비치 집안 (카라마조프가)",
     [["Grigory", "SERVANT_OF", "Fyodor Pavlovitch"]],
     [quote(2, r"a faithful servant of the family, Grigory, took the three-year-old Mitya")],
     "SERVANT_OF 1홉. 뒤 문항들이 이 관계를 경유하므로 먼저 단독으로 확인한다.")

# ---------------- 2홉 ----------------
item("G04", 2,
     "일류샤의 아버지를 길에서 수염을 잡고 끌고 다닌 사람은 누구야?", 31,
     "드미트리(미챠) 표도로비치 카라마조프",
     [["Ilusha", "SON_OF", "Captain Snegiryov"],
      ["Dmitri", "QUARRELS_WITH", "Captain Snegiryov"]],
     [quote(30, r"That I’d take my Ilusha and thrash him before you"),
      quote(29, r"Dmitri Fyodorovitch somehow lost his temper with this captain, seized him by the beard")],
     "일류샤와 아버지의 관계는 4편 6장, 수염 사건은 4편 5장. 서로 다른 장이라 한 문서로는 못 푼다.")

item("G05", 2,
     "조시마 장로의 제자를 그루셴카의 집으로 데려간 사람은 누구야?", 45,
     "라키친",
     [["Zossima", "MENTOR_OF", "Alyosha"],
      ["Rakitin", "TOOK_TO", "Alyosha -> Grushenka"]],
     [quote(43, r"“Let’s go to Grushenka, eh\? Will you come\?” pronounced Rakitin"),
      quote(4, r"the elder Zossima, who was living in the monastery hermitage, had made a special impression")],
     "두 관계가 7편 2장과 1편 4장으로 39장 떨어져 있다. 먼 거리 2홉을 검사한다.")

item("G06", 2,
     "드미트리를 세 살 때 맡아 키운 하인은 누구 밑에서 일했어?", 6,
     "표도르 파블로비치. 그리고리가 드미트리를 맡아 키웠고, 그리고리는 그 집안의 하인이다.",
     [["Grigory", "RAISED", "Dmitri (Mitya)"],
      ["Grigory", "SERVANT_OF", "Fyodor Pavlovitch"]],
     [quote(2, r"a faithful servant of the family, Grigory, took the three-year-old Mitya into his care")],
     "일부러 한 장 안에서 풀리는 문항을 하나 넣었다. basic RAG가 이겨야 정상인 대조군.",
     kind="control_singlehop")

item("G07", 2,
     "그루셴카와 친척이라는 말을 듣고 펄쩍 뛴 사람은 누구야?", 13,
     "라키친",
     [["Rakitin", "RELATIVE_OF(부인됨)", "Grushenka"]],
     [quote(12, r"“A relation! That Grushenka a relation of mine!” cried Rakitin, turning crimson")],
     "읽은 지점 13에서는 '부인했다'까지가 전부다. 확정은 12편 4장이라 이 시점에 단정하면 안 된다.")

# ---------------- 3홉 ----------------
item("G08", 3,
     "일류샤의 아버지를 모욕한 사람은 누구와 약혼했었어?", 31,
     "카체리나 이바노브나",
     [["Ilusha", "SON_OF", "Captain Snegiryov"],
      ["Dmitri", "QUARRELS_WITH", "Captain Snegiryov"],
      ["Dmitri", "ENGAGED_TO", "Katerina Ivanovna"]],
     [quote(30, r"That I’d take my Ilusha and thrash him before you"),
      quote(29, r"seized him by the beard and dragged him out into the street"),
      quote(18, r"you were betrothed, you are betrothed still\?")],
     "3장(30·29·18)을 모두 밟아야 한다. 2홉에서 끊기고 3홉으로 넓혀야 풀리는 문항.")

item("G09", 3,
     "드미트리를 어릴 때 키운 하인이 모시는 주인의 아들 중, 수도원에 들어간 사람은 누구야?", 13,
     "알료샤(알렉세이 표도로비치 카라마조프)",
     [["Grigory", "RAISED", "Dmitri"],
      ["Grigory", "SERVANT_OF", "Fyodor Pavlovitch"],
      ["Fyodor Pavlovitch", "FATHER_OF", "Alyosha"]],
     [quote(2, r"a faithful servant of the family, Grigory, took the three-year-old Mitya into his care"),
      quote(1, r"Alexey Fyodorovitch Karamazov was the third son of Fyodor Pavlovitch"),
      quote(4, r"as a novice\. He explained that this was his strong desire")],
     "표도르를 '경유'해야만 풀린다. 허브 제외 규칙과 정면으로 부딪히는 문항 — 허브를 도착점 근처에서는 허용해야 함을 보여준다.")

# ---------------- 스포 차단 ----------------
item("S01", 0,
     "그루셴카가 누구야?", 10,
     "읽은 범위(10장) 안에는 아직 나오지 않았다고 답해야 한다. 그루셴카는 12장에서 처음 등장한다.",
     [],
     [],
     "읽은 지점보다 뒤에서 처음 나오는 인물. 이름조차 알려주면 안 된다.",
     kind="spoiler_gate")

item("S02", 0,
     "표도르 파블로비치를 죽인 사람은 누구야?", 20,
     "읽은 범위(20장) 안에는 살인 사건 자체가 아직 일어나지 않았다고 답해야 한다.",
     [],
     [],
     "살인은 9편 2장(55장)에서 드러난다. 모델이 사전 지식으로 답하면 여기서 샌다. 누수 시험의 핵심.",
     kind="spoiler_gate")

item("S03", 0,
     "스메르쟈코프의 아버지는 누구야?", 20,
     "읽은 범위 안에서 확정된 근거가 없다고 답해야 한다. 소문·암시를 사실처럼 단정하면 실패.",
     [],
     [],
     "부칭(父稱)을 합쳐 보여주는 것만으로 혈연이 암시되는 경우. 별칭 병합이 스포가 되는지 본다.",
     kind="spoiler_gate")

item("S04", 0,
     "라키친과 그루셴카는 친척 맞아?", 12,
     "12장 시점에서는 '그런 말이 돌았고 라키친이 강하게 부인했다'까지만 답해야 한다. 사실로 확정하면 실패.",
     [],
     [quote(12, r"“Why, isn’t she a relation of yours\?")],
     "같은 사실이 앞에서는 부인되고 뒤(12편 4장)에서 확인된다. 읽은 지점에 따라 답이 달라져야 하는 문항.",
     kind="spoiler_gate")


out = {
    "corpus": "The Brothers Karamazov (Gutenberg #28054), 장 단위 96건",
    "note": "read_point = 읽은 지점(통짜 장 번호 1~96). 이 지점보다 뒤의 근거는 쓰면 안 된다.",
    "items": G,
}
path = ROOT / "data" / "goldenset.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

from collections import Counter
c = Counter(x["kind"] for x in G)
h = Counter(x["hops"] for x in G if x["kind"] != "spoiler_gate")
print(f"문항 {len(G)}건 -> {path.name}")
print("  종류:", dict(c))
print("  홉수:", dict(sorted(h.items())))
for x in G:
    lo = [e["global_index"] for e in x["evidence"]]
    bad = [g for g in lo if g > x["read_point"]]
    assert not bad, f"{x['id']}: 근거 {bad} 가 읽은 지점 {x['read_point']} 보다 뒤에 있음"
print("  검사 통과: 모든 근거가 읽은 지점 이내")
