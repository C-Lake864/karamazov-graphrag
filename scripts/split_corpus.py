"""구텐베르크 원문(#28054)을 장(chapter) 단위 문서로 쪼갠다.

스포 차단의 기준값이 되는 '통짜 번호(global_index, 1~96)'를 여기서 붙인다.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw_gutenberg_28054.txt"
OUT_DIR = ROOT / "data" / "docs"

BODY_START = "PART I"
BODY_END = "*** END OF THE PROJECT GUTENBERG EBOOK"

RE_PART = re.compile(r"^PART ([IVXL]+)\s*$")
RE_BOOK = re.compile(r"^Book ([IVXL]+)\.\s*(.*)$")
RE_EPILOGUE = re.compile(r"^EPILOGUE\s*$")
RE_CHAPTER = re.compile(r"^Chapter ([IVXL]+)\.\s*$")

ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman_to_int(s: str) -> int:
    total, prev = 0, 0
    for ch in reversed(s):
        val = ROMAN[ch]
        total = total - val if val < prev else total + val
        prev = max(prev, val)
    return total


def main() -> None:
    lines = RAW.read_text(encoding="utf-8").splitlines()

    start = next(i for i, l in enumerate(lines) if l.rstrip() == BODY_START)
    end = next(i for i, l in enumerate(lines) if l.startswith(BODY_END))
    body = lines[start:end]

    docs = []
    part = book_no = book_title = None
    cur = None  # 현재 모으는 중인 장

    def flush():
        if cur is None:
            return
        text = "\n".join(cur["buf"]).strip("\n")
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        cur["text"] = text
        del cur["buf"]
        docs.append(cur)

    i = 0
    while i < len(body):
        line = body[i]

        if m := RE_PART.match(line):
            part = roman_to_int(m.group(1))
            i += 1
            continue

        if m := RE_BOOK.match(line):
            flush()
            cur = None
            book_no = roman_to_int(m.group(1))
            book_title = m.group(2).strip()
            i += 1
            continue

        if RE_EPILOGUE.match(line):
            flush()
            cur = None
            book_no, book_title = 13, "Epilogue"
            i += 1
            continue

        if m := RE_CHAPTER.match(line):
            flush()
            chapter_no = roman_to_int(m.group(1))
            # 제목: 바로 뒤 빈 줄들을 건너뛰고, 빈 줄을 만날 때까지의 줄들
            j = i + 1
            while j < len(body) and not body[j].strip():
                j += 1
            title_lines = []
            while j < len(body) and body[j].strip():
                title_lines.append(body[j].strip())
                j += 1
            cur = {
                "global_index": len(docs) + 1,
                "part": part,
                "book_no": book_no,
                "book_title": book_title,
                "chapter_no": chapter_no,
                "chapter_title": " ".join(title_lines),
                "buf": [],
            }
            i = j
            continue

        if cur is not None:
            cur["buf"].append(line)
        i += 1

    flush()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.json"):
        old.unlink()

    for d in docs:
        d["doc_id"] = f"ch{d['global_index']:03d}"
        d["label_ko"] = f"{d['book_no']}편 {d['chapter_no']}장"
        d["source"] = "Project Gutenberg #28054 (Constance Garnett 역, 퍼블릭 도메인)"
        d["n_chars"] = len(d["text"])
        (OUT_DIR / f"{d['doc_id']}.json").write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 확인용 목차
    index = [
        {k: d[k] for k in ("doc_id", "global_index", "part", "book_no",
                           "book_title", "chapter_no", "chapter_title", "n_chars")}
        for d in docs
    ]
    (ROOT / "data" / "chapter_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 검증
    print(f"문서 수: {len(docs)}")
    assert len(docs) == 96, f"96장이어야 하는데 {len(docs)}장"
    books = {}
    for d in docs:
        books.setdefault(d["book_no"], []).append(d["chapter_no"])
    for b in sorted(books):
        ch = books[b]
        assert ch == list(range(1, len(ch) + 1)), f"{b}편 장 번호가 끊김: {ch}"
        print(f"  {b:>2}편 {len(ch):>2}장  {docs[0]['book_title'] if False else ''}")
    empty = [d["doc_id"] for d in docs if d["n_chars"] < 500]
    print(f"짧은 장(<500자): {empty or '없음'}")
    print(f"총 글자 수: {sum(d['n_chars'] for d in docs):,}")


if __name__ == "__main__":
    main()
