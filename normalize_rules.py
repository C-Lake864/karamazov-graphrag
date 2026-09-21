# -*- coding: utf-8 -*-
"""정제 규칙 — 표기 통일 · 별칭 병합 · 일반명사 제외.

러시아 소설이라 한 인물이 이름/애칭/부칭/성으로 제각기 불린다.
이걸 안 합치면 같은 사람이 대여섯 노드로 흩어져서 멀티홉이 아예 끊긴다.
"""

# ── 1. 별칭 병합 ──────────────────────────────────────────────
# 왼쪽이 대표 이름(canonical), 오른쪽이 본문에 나오는 다른 표기들.
# 대표 이름은 모두 본문에서 실제로 확인한 형태만 쓴다.
ALIAS_GROUPS = {
    "Fyodor Pavlovitch Karamazov": [
        "Fyodor Pavlovitch", "old Karamazov", "old Fyodor Pavlovitch",
        "Fyodor Pavlovitch Karamazov", "the old man Karamazov",
    ],
    "Dmitri Fyodorovitch Karamazov": [
        "Dmitri", "Dmitri Fyodorovitch", "Mitya", "Mitka", "Mitenka", "Mitri",
        "Dmitri Karamazov", "Mitya Karamazov",
    ],
    "Ivan Fyodorovitch Karamazov": [
        "Ivan", "Ivan Fyodorovitch", "Vanya", "Vanka", "Ivan Karamazov",
    ],
    "Alexey Fyodorovitch Karamazov": [
        "Alexey", "Alexey Fyodorovitch", "Alyosha", "Alyoshka", "Alyoshenka",
        "Alexey Karamazov", "Alyosha Karamazov",
    ],
    "Smerdyakov": [
        "Pavel Fyodorovitch Smerdyakov", "Pavel Fyodorovitch", "Pavel Smerdyakov",
    ],
    "Grushenka": [
        "Agrafena Alexandrovna", "Agrafena Alexandrovna Svyetlov",
        "Agrafena", "Grusha", "Grushenka Svyetlov",
    ],
    "Katerina Ivanovna": [
        "Katya", "Katka", "Katerina Ivanovna Verhovtsev", "Katenka",
    ],
    "Father Zossima": ["Zossima", "the elder Zossima", "Father Zossima", "elder Zossima"],
    "Grigory": ["Grigory Vassilyevitch", "Grigory Vassilyevitch Kutuzov", "old Grigory"],
    "Marfa Ignatyevna": ["Marfa"],
    # "Misha" 는 2편 7장에서 알료샤가 라키친을 부르는 호칭 — 원문에서 확인함.
    "Rakitin": ["Mihail Osipovitch Rakitin", "Misha Rakitin", "Misha", "Rakitka"],
    "Captain Snegiryov": [
        "Snegiryov", "Nikolay Ilyitch Snegiryov", "captain Snegiryov",
        "Nikolay Ilyitch",
    ],
    "Ilusha": ["Ilusha Snegiryov", "Ilyusha", "Ilushechka"],
    "Kolya Krassotkin": ["Krassotkin", "Kolya", "Nikolay Ivanovitch Krassotkin"],
    "Pyotr Alexandrovitch Miüsov": ["Miüsov", "Pyotr Alexandrovitch"],
    "Pyotr Ilyitch Perhotin": ["Perhotin", "Pyotr Ilyitch"],
    "Lizaveta Smerdyastchaya": ["Stinking Lizaveta", "Lizaveta"],
    "Father Ferapont": ["Ferapont"],
    "Fetyukovitch": ["the counsel for the defense"],
    "Ippolit Kirillovitch": ["the prosecutor", "the public prosecutor"],
}

# 성(姓)만 같고 다른 사람인 경우 — 절대 자동 병합하면 안 된다.
# Karamazov 는 4명, Hohlakov 는 모녀 2명, Snegiryov 는 부자 2명이다.
NEVER_MERGE_BY_SURNAME = {"karamazov", "hohlakov", "snegiryov", "krassotkin"}

# 성 하나만 나와도 그 사람으로 확정할 수 있는 이름들 (동명이인이 없음)
DISTINCTIVE_SURNAMES = {
    "smerdyakov": "Smerdyakov",
    "grushenka": "Grushenka",
    "rakitin": "Rakitin",
    "zossima": "Father Zossima",
    "perhotin": "Pyotr Ilyitch Perhotin",
    "fetyukovitch": "Fetyukovitch",
    "miüsov": "Pyotr Alexandrovitch Miüsov",
    "miusov": "Pyotr Alexandrovitch Miüsov",
    "ferapont": "Father Ferapont",
}

# ── 2. 일반명사 제외 ──────────────────────────────────────────
# 고유명사가 아니라서 노드가 되면 안 되는 것들. 이게 섞이면
# "the old man" 같은 노드에 수십 개 관계가 붙어 허브가 되고 경로가 망가진다.
GENERIC_STOP = {
    "the old man", "old man", "the boy", "boy", "the child", "child",
    "the woman", "woman", "the girl", "girl", "the man", "man",
    "the father", "father", "the mother", "mother", "the son", "son",
    "the brother", "brother", "the elder", "elder", "the monk", "monk",
    "the servant", "servant", "the peasant", "peasant", "the doctor", "doctor",
    "the prisoner", "prisoner", "the president", "the court", "the jury",
    "the reader", "reader", "the narrator", "narrator", "the author",
    "god", "the lord", "christ", "the devil", "satan",
    "the people", "people", "the crowd", "crowd", "everyone", "the public",
    "the family", "family", "the house", "house", "the town", "town",
    "the monastery",  # 장소는 따로 대표 이름을 둔다 (아래 PLACE_CANON)
    "money", "the money", "the letter", "letter", "the door", "door",
    "the captain",    # 스네기료프인지 다른 사람인지 문맥 없이는 못 정한다
    "he", "she", "they", "it", "i", "you", "we",
}

# 장소 표기 통일
PLACE_CANON = {
    "the monastery": "the Monastery",
    "monastery": "the Monastery",
    "the hermitage": "the Hermitage",
    "hermitage": "the Hermitage",
    "mokroe": "Mokroe",
    "mokroye": "Mokroe",
    "petersburg": "Petersburg",
    "st. petersburg": "Petersburg",
    "moscow": "Moscow",
}
