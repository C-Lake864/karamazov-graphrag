# 카라마조프가의 형제들 — 스포 방지 관계도 도우미

《카라마조프가의 형제들》을 읽다가 "얘가 아까 그 사람 맞나?", "이 둘이 무슨 사이였지?" 싶을 때
물어보는 한국어 챗봇입니다. **읽은 지점까지의 내용만으로** 답합니다.

읽은 지점(1~96장)을 정해두면, 그보다 뒤에서 드러난 인물·관계는 **검색 단계에서 그래프에서 아예 제거**한 뒤
남은 것만 답변 모델에 넘깁니다. "말하지 마"라고 부탁하는 게 아니라 **볼 수 없게** 만드는 방식입니다.

---

## 빠르게 실행하기

### 1. 준비물

- Python 3.11 이상
- **OpenAI API 키** (기본 설정)
  — Gemini 로 바꾸려면 `config.json`의 `"provider"`를 `"google"`로 바꾸고
  `.env`에 `GOOGLE_API_KEY`를 넣으면 됩니다. 모델 이름은 `llm.py`가 알아서 고릅니다.

```bash
pip install google-genai openai networkx langgraph streamlit numpy python-dotenv
```

`.env.example`을 `.env`로 복사해 키를 채우세요. (파일은 **UTF-8**로 저장)

```bash
cp .env.example .env    # 그리고 OPENAI_API_KEY 를 채웁니다
```

> `.env`는 `.gitignore`에 있어 저장소에 올라가지 않습니다.

### 2. 데모 실행

저장소에 그래프(`output/graph.graphml`)가 이미 들어 있어서, **바로 띄울 수 있습니다.**

```bash
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 이 열립니다.

### 3. 그래프를 처음부터 다시 만들기 (선택)

```bash
python scripts/split_corpus.py     # 원문을 96개 장으로 분할
python extract.py                  # LLM 추출 1차  (약 6분)
PASS=2 python extract.py           # 2차
PASS=3 python extract.py           # 3차 — 추출은 분산이 커서 합집합을 씁니다
python build_graph.py              # 정제·병합 -> graph.graphml  (API 안 씀)
```

> 추출이 이 프로젝트에서 API를 가장 많이 쓰는 단계입니다(96장 × 3회 ≈ 600회 호출).
> 결과가 `output/extract_cache*/`에 캐시돼 있으니, 저장소를 받아서 쓰는 경우
> **이 단계를 건너뛰어도 됩니다.**

원문은 `data/raw_gutenberg_28054.txt`에 포함돼 있습니다
(Project Gutenberg #28054, Constance Garnett 번역, **퍼블릭 도메인**).
없다면 `scripts/split_corpus.py`가 참조하는 URL에서 내려받으면 됩니다.

### 4. 평가

```bash
python evaluate.py                 # 골든셋 13문항 + basic RAG(BM25) 대조
```

대조군은 BM25라 **API를 쓰지 않습니다.** 평가 전체가 약 55회 호출이면 끝납니다.

결과는 `output/eval.json`에, 질문별 실행 기록은 `output/runs.jsonl`에 쌓입니다.

### 5. 한 문항만 빠르게 확인

```bash
python agent.py "조시마 장로의 제자는 누구야?" 13
```

두 번째 인자가 읽은 지점(장 번호)입니다.

---

## 화면

| | |
|---|---|
| **읽은 지점** | 슬라이더(1~96) 또는 편·장 2단 선택. 한 번 정하면 질문을 몇 번 하든 유지됩니다 |
| **답변** | 한국어. 근거가 없으면 "아직 나오지 않았어요"라고 답합니다 |
| **탄 경로** | 몇 홉으로 어떤 관계를 타고 갔는지 |
| **근거 삼중항** | 관계 + 출처 장 + 영어 원문 인용 |
| **별명 사전** | 읽은 데까지 등장한 호칭만. 예) 드미트리 · 미챠 |

아직 안 읽은 장은 **제목을 감추고 번호만** 보여줍니다 — 도스토옙스키의 장 제목은
그 자체로 스포일러인 것이 많습니다.

### 화면 캡처

**읽은 지점 13장 — 전체의 15%만 보입니다**

![13장](docs/01-읽은지점-13장.png)

**같은 화면, 읽은 지점 60장 — 보이는 양이 늘어납니다**

인물·장소 43개 → 185개, 관계 86개 → 378개. 스포 차단이 실제로 걸리고 있다는 증거입니다.

![60장](docs/02-읽은지점-60장.png)

**별명 사전 (45장 시점)**

읽은 데까지 등장한 호칭만 보여줍니다. 드미트리 = Mitya = Mitri,
스메르쟈코프 = Pavel Fyodorovitch 처럼요.

<img src="docs/03-별명-45장.png" width="300">

**질문과 답변 (31장까지 읽은 시점)**

답변 밑에 탄 경로 · 근거 삼중항 · 출처 장이 함께 나옵니다.

![답변](docs/04-답변과경로.png)

**같은 지점에서 뒷이야기를 물으면**

![스포차단](docs/05-스포차단.png)

캡처는 `scripts/capture.py` 가 Playwright 로 자동으로 찍습니다
(`pip install playwright && playwright install chromium` 필요).

```bash
python scripts/capture.py --with-answer
```

---

## 파일 구조

```
.
├── data/
│   ├── raw_gutenberg_28054.txt   원문 (퍼블릭 도메인)
│   ├── docs/                     장 단위 문서 96건
│   ├── chapter_index.json        편·장·통짜번호 목차
│   └── goldenset.json            평가셋 13문항
├── config.json                   스키마·반경·허브 기준 (도메인에 묶인 값)
├── normalize_rules.py            별칭 병합표 · 일반명사 제외 목록
├── ko_labels.py                  화면용 한국어 표기
├── llm.py                        LLM 호출 (google / openai 전환)
├── scripts/
│   ├── split_corpus.py           원문 -> 장 단위 분할
│   ├── build_goldenset.py        평가셋 생성 (인용문을 원문에서 직접 추출)
│   └── capture.py                데모 화면 자동 캡처
├── extract.py                    ① 추출
├── build_graph.py                ② 정제·병합
├── agent.py                      ③④⑤ 시작 개체 -> n홉 -> 답변 (LangGraph)
├── evaluate.py                   평가 + basic RAG 대조
├── app.py                        데모 화면 (Streamlit)
├── docs/                         화면 캡처
├── output/
│   ├── graph.graphml             지식 그래프
│   ├── graph.json                작업용 형식 (별칭 사전 포함)
│   ├── extract_cache*/           추출 결과 (회차별)
│   ├── runs.jsonl                질문별 실행 기록
│   └── eval.json                 평가 결과
├── PRD.md                        기획
└── REPORT.md                     주제·측정 결과·회고
```

---

## 측정 결과 요약

| 구분 | 문항 | GraphRAG | basic RAG |
|---|---|---|---|
| 1홉 | 3 | 100% | 67% |
| 2홉 | 3 | 67% | 33% |
| 3홉 | 2 | 50% | 50% |
| 대조군(한 장에서 풀림) | 1 | 100% | 100% |
| 스포 차단 | 4 | 100% | 75% |
| **전체** | 13 | **85%** | **62%** |

경로 재현율 87%, 스포 누수 양쪽 0건. 자세한 내용과 실패 분석은 [REPORT.md](REPORT.md).

---

## 알아두실 것

- **답변은 한국어, 근거 인용문은 영어입니다.** 한국어 번역본은 번역가 저작권이 살아 있어
  저장소에 올릴 수 없어서, 저작권이 만료된 영어 번역본(1880년 원작)을 썼습니다.
- **스포 차단은 그래프에 담긴 것에만 걸립니다.** 답변 모델 자체가 소설을 알고 있으므로,
  프롬프트로 "근거에만 근거하라"를 강하게 걸어 막고 있습니다. 측정 결과는 `REPORT.md`에 있습니다.
- 인터넷 배포는 하지 않았습니다. 로컬 실행 전용입니다.
