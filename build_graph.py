# -*- coding: utf-8 -*-
"""② 정제·병합 — 추출된 삼중항을 하나의 지식 그래프로 만든다.

  표기 통일 -> 별칭 병합 -> 일반명사 제외 -> 스키마 타입 검사 -> 허브 표시

모든 엣지에 '처음 드러난 장(first_revealed_index)'과 근거 인용문이 남는다.
스포 차단은 전부 이 숫자 하나에 기댄다.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx

import normalize_rules as R

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
OUT = ROOT / "output"
# 추출 분산을 줄이려고 여러 번 돌린다. extract_cache, extract_cache_p2 ... 를 모두 읽어
# 합집합을 쓴다 (_archive_ 로 시작하는 옛 결과는 뺀다).
CACHE_DIRS = sorted(d for d in OUT.glob("extract_cache*")
                    if d.is_dir() and not d.name.startswith("_"))

DOCS = {}
for _p in sorted((ROOT / "data" / "docs").glob("*.json")):
    _d = json.loads(_p.read_text(encoding="utf-8"))
    DOCS[_d["global_index"]] = _d


# ── 표기 정리 ────────────────────────────────────────────────
CONTROL = re.compile(r"[\x00-\x1f\x7f]")   # graphml 은 제어문자를 못 담는다
POSSESSIVE = re.compile(r"[’']s\b")
LEADING_ART = re.compile(r"^(the|a|an)\s+", re.I)
PUNCT = re.compile(r"[^\w\sÀ-ɏ-]")


def clean(name: str) -> str:
    return re.sub(r"\s+", " ", CONTROL.sub(" ", name)).strip()


def norm(name: str) -> str:
    s = POSSESSIVE.sub("", clean(name))
    s = LEADING_ART.sub("", s)
    s = PUNCT.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def has_upper(name: str) -> bool:
    return any(c.isupper() for c in name)


# 별칭 -> 대표 이름
ALIAS2CANON = {}
for _canon, _variants in R.ALIAS_GROUPS.items():
    ALIAS2CANON[norm(_canon)] = _canon
    for _v in _variants:
        ALIAS2CANON[norm(_v)] = _canon


def resolve(name: str):
    """이름 하나를 대표 이름으로 바꾼다. 노드가 되면 안 되는 것은 None."""
    if not name or not name.strip():
        return None
    n = norm(name)
    if not n:
        return None
    if n in R.GENERIC_STOP or name.strip().lower() in R.GENERIC_STOP:
        return None
    if n in R.PLACE_CANON:
        return R.PLACE_CANON[n]
    if n in ALIAS2CANON:
        return ALIAS2CANON[n]
    # 성 하나만으로 확정 가능한 인물 (동명이인이 없는 성에 한해)
    toks = set(n.split())
    if not (toks & R.NEVER_MERGE_BY_SURNAME):
        for surname, canon in R.DISTINCTIVE_SURNAMES.items():
            if surname in toks:
                return canon
    if not has_upper(name):          # 대문자가 하나도 없으면 일반명사로 본다
        return None
    return clean(name)


def text_spread(canon: str) -> int:
    """이 인물의 이름이나 별칭이 96장 중 몇 장에 나오는가.

    허브 판정에 쓴다. 엣지 수와 달리 추출을 몇 번 돌리든 변하지 않는 값이다.
    """
    # 별칭을 '통째로' 찾는다. 마지막 낱말만 쓰면 Karamazov(4명)·Fyodorovitch(부칭)
    # 같은 공용 낱말에 걸려 남의 등장까지 세게 된다.
    SHARED = {"karamazov", "karamazovs", "fyodorovitch", "pavlovitch",
              "ivanovna", "alexandrovna", "ilyitch", "vassilyevitch",
              "osipovitch", "ignatyevna", "father", "captain", "madame"}
    forms = {canon} | set(R.ALIAS_GROUPS.get(canon, []))
    pats = []
    for f in forms:
        toks = norm(f).split()
        if not toks or set(toks) <= SHARED:
            continue
        pats.append(re.compile(r"\b" + r"\s+".join(re.escape(t) for t in toks) + r"\b", re.I))
    if not pats:
        return 0
    return sum(1 for d in DOCS.values()
               if any(p.search(re.sub(r"\s+", " ", d["text"])) for p in pats))


def type_ok(want: str, got: str) -> bool:
    """스키마가 요구하는 목적어 타입과 실제 타입이 맞는지.

    POSSESSES 의 대상이 사람으로 잡히는 것 같은 오추출을 여기서 버린다.
    타입을 모르는(투표가 없는) 노드는 통과시킨다 — 과하게 버리지 않으려고.
    """
    if got is None:
        return True
    return want == got


def main():
    files = [f for d in CACHE_DIRS for f in sorted(d.glob("*.json"))]
    if not files:
        raise SystemExit("추출 캐시가 없다. 먼저 extract.py 를 돌려라.")
    runs = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    print(f"추출 결과 {len(CACHE_DIRS)}회분 읽음: "
          + ", ".join(f"{d.name}({len(list(d.glob('*.json')))}장)" for d in CACHE_DIRS))

    # LLM이 보고한 별칭도 병합에 쓴다 (일반명사·소문자는 거른다)
    extra_alias = 0
    stats_alias_rejected = []
    for r in runs:
        for e in r["entities"]:
            canon = resolve(e["name"])
            if canon is None:
                continue
            for a in e.get("aliases", []):
                na = norm(a)
                if not na or na in R.GENERIC_STOP or not has_upper(a):
                    continue
                if na in ALIAS2CANON:
                    continue
                # 성(姓)만 적힌 별칭은 받지 않는다. 카라마조프는 4명, 호흘라코바는
                # 모녀 2명이라 "Karamazov" 하나로는 누구인지 정할 수 없다.
                if set(na.split()) <= R.NEVER_MERGE_BY_SURNAME:
                    stats_alias_rejected.append((a, canon, "성만 적힘"))
                    continue
                # 대표 이름과 겹치는 낱말이 하나도 없으면 받지 않는다.
                # LLM이 "아델라이다 = 미우소프", "막시모프 = 폰 존" 처럼
                # 그냥 같이 언급된 사람을 별명으로 보고하는 일이 실제로 있었다.
                # 애칭(미챠·알료샤 등)은 위 ALIAS_GROUPS 에 손으로 적어뒀으므로
                # 여기서는 안전한 쪽을 택한다 — 잘못 합치면 답이 틀리지만,
                # 못 합치면 답이 조금 덜 나올 뿐이다.
                if not (set(na.split()) & {t for t in norm(canon).split() if len(t) > 2}):
                    stats_alias_rejected.append((a, canon, "대표 이름과 안 겹침"))
                    continue
                ALIAS2CANON[na] = canon
                extra_alias += 1

    # 노드 타입 투표
    votes = defaultdict(Counter)
    for r in runs:
        for e in r["entities"]:
            c = resolve(e["name"])
            if c:
                votes[c][e["type"]] += 1

    def typeof(node):
        return votes[node].most_common(1)[0][0] if votes.get(node) else None

    # ── 엣지 모으기 ──────────────────────────────────────────
    edges = {}
    stats = Counter()
    for r in runs:
        for t in r["triples"]:
            stats["raw"] += 1
            s = resolve(t["subject"])
            o = resolve(t["object"])
            if s is None or o is None:
                stats["dropped_generic"] += 1
                continue
            if s == o:
                stats["dropped_selfloop"] += 1
                continue
            spec = CFG["relation_types"][t["relation"]]
            if not type_ok(spec["to"], typeof(o)):
                stats["dropped_type"] += 1
                continue
            key = (s, t["relation"], o)
            ev = {
                "doc_id": t["doc_id"],
                "global_index": t["first_revealed_index"],
                "label_ko": t["label_ko"],
                "quote": t["quote"],
                # 이 장에서 관계가 '확정'인지 '소문·부인'인지. 스포 차단과 직결된다 —
                # 부인된 소문을 사실처럼 말하면 그 자체가 스포일러가 된다.
                # None = 그 회차 추출에는 이 항목이 아예 없었음(모름). False 와 다르다.
                "disputed": t.get("disputed"),
                # 추출 3회 중 몇 회에서 이 삼중항이 나왔는가. 추출은 분산이 커서
                # 1회만 나온 관계는 우연일 수 있다 — 근거의 세기로 쓴다.
                "n_passes": 1,
            }
            slot = edges.setdefault(key, {"evidence": [], "first": ev["global_index"]})
            same = next((x for x in slot["evidence"]
                         if x["global_index"] == ev["global_index"]), None)
            if same is None:
                slot["evidence"].append(ev)
            else:
                same["n_passes"] += 1
                if ev["disputed"] is not None and same["disputed"] is not True:
                    # '모름'을 실제 판정으로 덮어쓴다. 한 회차라도 '소문'이라 하면 소문.
                    same["disputed"] = ev["disputed"]
            slot["first"] = min(slot["first"], ev["global_index"])
            stats["kept"] += 1

    # ── 그래프 조립 ──────────────────────────────────────────
    G = nx.MultiDiGraph()
    for (s, rel, o), e in edges.items():
        for nd in (s, o):
            if nd not in G:
                G.add_node(nd, type=typeof(nd) or "Character")
        e["evidence"].sort(key=lambda x: x["global_index"])
        G.add_edge(
            s, o, key=rel,
            relation=rel,
            first_revealed_index=e["first"],
            n_support=len(e["evidence"]),
            evidence=json.dumps(e["evidence"], ensure_ascii=False),
        )

    # 노드가 '처음 드러난 장' = 그 노드에 달린 엣지 중 가장 이른 장
    for n in G.nodes:
        idxs = [d["first_revealed_index"] for *_, d in G.in_edges(n, data=True)]
        idxs += [d["first_revealed_index"] for *_, d in G.out_edges(n, data=True)]
        G.nodes[n]["first_revealed_index"] = min(idxs) if idxs else 1
        G.nodes[n]["degree"] = G.degree(n)

    # ── 허브 표시 ────────────────────────────────────────────
    # 허브를 '경유'시키면 아무 두 인물이나 2홉으로 이어져 경로가 무의미해진다.
    # 허브 기준을 두 번 갈아엎었다.
    #   1차 '연결 상위 5%' -> 연결 중앙값이 1인 극단적 분포라 일류샤(연결 14)까지 허브가 됨
    #   2차 '연결 40개 이상' -> 추출을 두 번 돌려 엣지가 2배가 되자 콜랴(7장 등장)까지 허브가 됨
    # 둘 다 '엣지 수'에 기대서 깨졌다. 엣지 수는 추출을 몇 번 돌렸는지에 따라 변한다.
    # 그래서 추출과 무관한 값으로 바꿨다 — 본문 96장 중 몇 장에 이름이 나오는가.
    MIN_TEXT_CHAPTERS = 50   # 96장의 절반 넘게 나오는 인물 = 카라마조프 4부자
    hubs = []
    for n in G.nodes:
        chs = {d["first_revealed_index"] for *_, d in G.in_edges(n, data=True)}
        chs |= {d["first_revealed_index"] for *_, d in G.out_edges(n, data=True)}
        n_text = text_spread(n) if G.nodes[n]["type"] == "Character" else 0
        is_hub = n_text >= MIN_TEXT_CHAPTERS
        G.nodes[n]["is_hub"] = int(is_hub)
        G.nodes[n]["n_chapters"] = len(chs)
        G.nodes[n]["n_text_chapters"] = n_text
        if is_hub:
            hubs.append((n, n_text))

    # ── 별칭 사전 ────────────────────────────────────────────
    # 별칭이 본문에 처음 나오는 장까지 적어둔다. 부칭(父稱)을 합쳐 보여주는 것만으로
    # 혈연이 암시될 수 있어서, 별칭도 읽은 지점 기준으로 걸러야 하기 때문.
    def first_text_index(surface: str):
        pat = re.compile(r"\b" + re.escape(surface) + r"\b", re.I)
        for gi in sorted(DOCS):
            if pat.search(DOCS[gi]["text"]):
                return gi
        return None

    # "his elder brother dmitri" 같은 서술구도 질문을 인물에 붙이는 데는 쓸모가 있지만,
    # 화면에 '별명'이라고 보여주면 안 된다. 보여줄 것만 display 로 표시한다.
    DESCRIPTIVE = re.compile(
        r"\b(his|her|their|my|our|that|this|same|the|young|old|little|"
        r"elder|younger|brother|sister|father|mother|son|daughter|half|"
        r"himself|herself|called|named|man|woman|boy|girl|mamma|papa|"
        r"servant|captain|madame|monk|lady)\b", re.I)

    alias_table = defaultdict(list)
    for alias_n, canon in ALIAS2CANON.items():
        # 별명 패널은 인물만 보여준다. 장소·사건의 표기 변형은 별명이 아니다.
        if canon not in G or G.nodes[canon].get("type") != "Character":
            continue
        gi = first_text_index(alias_n)
        if gi is not None:
            alias_table[canon].append({
                "alias": alias_n,
                "first_index": gi,
                "display": not DESCRIPTIVE.search(alias_n) and len(alias_n.split()) <= 3,
            })
    for c in alias_table:
        alias_table[c].sort(key=lambda x: x["first_index"])

    # ── 저장 ─────────────────────────────────────────────────
    OUT.mkdir(exist_ok=True)
    nx.write_graphml(G, OUT / "graph.graphml")
    (OUT / "graph.json").write_text(json.dumps({
        "nodes": [{"id": n, **G.nodes[n]} for n in G.nodes],
        "edges": [{"source": s, "target": o, **d}
                  for s, o, d in G.edges(data=True)],
        "aliases": dict(alias_table),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 보고 ─────────────────────────────────────────────────
    print(f"장 {len(runs)}개에서 삼중항 원본 {stats['raw']}개")
    print(f"  일반명사라 버림    {stats['dropped_generic']}")
    print(f"  타입 안 맞아 버림  {stats['dropped_type']}")
    print(f"  자기 자신이라 버림 {stats['dropped_selfloop']}")
    print(f"  남김               {stats['kept']}")
    print(f"LLM이 추가로 알려준 별칭 {extra_alias}개 "
          f"(잘못돼서 받지 않은 것 {len(stats_alias_rejected)}개)")
    for a, c, why in stats_alias_rejected[:6]:
        print(f"    거절: '{a}' -> {c}  ({why})")
    print(f"\n노드 {G.number_of_nodes()}개 / 엣지 {G.number_of_edges()}개")
    print(f"타입별: {dict(Counter(G.nodes[n]['type'] for n in G.nodes))}")
    print(f"\n허브 {len(hubs)}개 (본문 {MIN_TEXT_CHAPTERS}장 이상에 등장):")
    for n, d in sorted(hubs, key=lambda x: -x[1])[:12]:
        print(f"   {d:>4}  {n}")


if __name__ == "__main__":
    main()
