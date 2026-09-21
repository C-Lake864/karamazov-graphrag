# -*- coding: utf-8 -*-
"""화면에 보여줄 한국어 표기.

그래프는 영어 원문에서 만들어져서 노드 이름이 영어다. 하지만 읽는 사람은
한국어 번역본으로 읽고 있으니, 화면에서는 익숙한 한국어 이름으로 보여준다.
(근거 인용문만 영어 원문 그대로 둔다 — 원문을 보여주는 게 목적이므로.)
"""

NODE_KO = {
    "Alexey Fyodorovitch Karamazov": "알료샤",
    "Dmitri Fyodorovitch Karamazov": "드미트리(미챠)",
    "Ivan Fyodorovitch Karamazov": "이반",
    "Fyodor Pavlovitch Karamazov": "표도르 파블로비치",
    "Smerdyakov": "스메르쟈코프",
    "Grushenka": "그루셴카",
    "Katerina Ivanovna": "카체리나 이바노브나",
    "Father Zossima": "조시마 장로",
    "Grigory": "그리고리",
    "Marfa Ignatyevna": "마르파",
    "Rakitin": "라키친",
    "Captain Snegiryov": "스네기료프 대위",
    "Ilusha": "일류샤",
    "Kolya Krassotkin": "콜랴 크라소트킨",
    "Pyotr Alexandrovitch Miüsov": "미우소프",
    "Pyotr Ilyitch Perhotin": "페르호친",
    "Lizaveta Smerdyastchaya": "리자베타",
    "Father Ferapont": "페라폰트 신부",
    "Fetyukovitch": "페츄코비치",
    "Ippolit Kirillovitch": "이폴리트 키릴로비치",
    "Madame Hohlakov": "호흘라코바 부인",
    "Lise": "리자",
    "Maximov": "막시모프",
    "the Monastery": "수도원",
    "the Hermitage": "암자",
    "Mokroe": "모크로예",
    "Petersburg": "페테르부르크",
    "Moscow": "모스크바",
}

REL_KO = {
    "FATHER_OF": "아버지",
    "BROTHER_OF": "형제",
    "SERVANT_OF": "하인",
    "MENTOR_OF": "스승",
    "RAISED": "키움",
    "RELATED_TO": "친척",
    "LOVES": "사랑",
    "ENGAGED_TO": "약혼",
    "RIVAL_OF": "연적",
    "QUARRELS_WITH": "다툼",
    "OWES_MONEY_TO": "빚",
    "MEMBER_OF": "소속",
    "LIVES_AT": "머묾",
    "PRESENT_AT": "참여",
    "ACCUSED_OF": "혐의",
    "POSSESSES": "가짐",
    "OCCURRED_AT": "장소",
}


def node(name: str) -> str:
    """사전에 없으면 영어 이름을 그대로 쓴다 — 지어내지 않는다."""
    return NODE_KO.get(name, name)


def rel(name: str) -> str:
    return REL_KO.get(name, name)


def triple(t: dict) -> str:
    return f"{node(t['subject'])} ─[{rel(t['relation'])}]→ {node(t['object'])}"
