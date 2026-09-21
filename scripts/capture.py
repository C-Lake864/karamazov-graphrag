# -*- coding: utf-8 -*-
"""데모 화면 캡처.

app.py 를 띄운 뒤 이 스크립트를 돌리면 docs/ 에 PNG 가 저장된다.

    streamlit run app.py --server.port 8511 --server.headless true
    python scripts/capture.py

질문을 넣는 캡처(2·3번)는 LLM 호출이 필요하다. API 가 막혀 있으면
읽은 지점만 바꾸는 1·4번만 찍고 나머지는 건너뛴다.
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs"
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
URL = ARGS[0] if ARGS else "http://localhost:8511"

# 질문을 던지는 캡처를 할지 (LLM 호출이 필요)
WITH_ANSWER = "--with-answer" in sys.argv


def settle(page, ms=2500):
    page.wait_for_timeout(ms)
    try:
        page.wait_for_selector("text=지금 보이는 관계", timeout=15000)
    except Exception:
        pass


IDX = {c["global_index"]: c for c in
       __import__("json").loads((ROOT / "data" / "chapter_index.json")
                                .read_text(encoding="utf-8"))}


def pick_option(page, combo_i: int, label: str):
    page.locator('div[data-testid="stSelectbox"]').nth(combo_i).click()
    page.wait_for_timeout(600)
    page.get_by_role("option", name=label, exact=True).first.click()
    page.wait_for_timeout(1200)


def set_read_point(page, value: int):
    """편·장 선택 + 버튼으로 읽은 지점을 옮긴다.

    슬라이더를 방향키로 옮기려 했더니, Streamlit 이 값이 바뀔 때마다 화면을
    다시 그리면서 포커스가 풀려 한 칸만 움직였다. 선택 + 버튼은 한 번의
    조작으로 끝나 확실하다.
    """
    c = IDX[value]
    book = "에필로그" if c["book_no"] == 13 else f'{c["book_no"]}편'
    pick_option(page, 0, book)
    pick_option(page, 1, f'{c["chapter_no"]}장')
    page.get_by_role("button", name="이 장까지 읽음으로 설정").click()
    page.wait_for_timeout(2500)   # Streamlit 이 다시 그릴 시간


def ask(page, question: str):
    box = page.get_by_placeholder("궁금한 걸 물어보세요", exact=False)
    box.click()
    box.fill(question)
    page.keyboard.press("Enter")
    # 답변 생성에는 시간이 걸린다
    page.wait_for_timeout(2000)
    for _ in range(60):
        if page.locator("text=탄 경로").count() or page.locator("text=근거 삼중항").count():
            break
        page.wait_for_timeout(1000)
    page.wait_for_timeout(1500)


def main():
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000},
                                device_scale_factor=2)
        page.goto(URL, wait_until="networkidle")
        settle(page)

        # ① 스포 차단이 걸린 상태 — 13장
        set_read_point(page, 13)
        page.screenshot(path=str(OUT / "01-읽은지점-13장.png"))
        print("  01-읽은지점-13장.png")

        # ② 읽은 지점을 옮기면 보이는 양이 늘어난다 — 60장
        set_read_point(page, 60)
        page.screenshot(path=str(OUT / "02-읽은지점-60장.png"))
        print("  02-읽은지점-60장.png")

        # ③ 별명 패널 — 사이드바가 길어서 화면을 늘려 찍는다
        set_read_point(page, 45)
        page.set_viewport_size({"width": 1440, "height": 2100})
        page.wait_for_timeout(1500)
        side = page.locator('section[data-testid="stSidebar"]').first
        side.screenshot(path=str(OUT / "03-별명-45장.png"))
        page.set_viewport_size({"width": 1440, "height": 1000})
        print("  03-별명-45장.png")

        if WITH_ANSWER:
            # Streamlit 본문은 안쪽에서 따로 스크롤돼서 full_page 로는 다 안 담긴다.
            # 화면을 길게 잡고 답변 부분으로 올려서 찍는다.
            set_read_point(page, 31)
            ask(page, "일류샤의 아버지를 길에서 수염을 잡고 끌고 다닌 사람은 누구야?")
            page.set_viewport_size({"width": 1440, "height": 1700})
            page.wait_for_timeout(1500)
            page.get_by_text("일류샤의 아버지를 길에서").first.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            page.screenshot(path=str(OUT / "04-답변과경로.png"))
            print("  04-답변과경로.png")

            ask(page, "표도르 파블로비치를 죽인 사람은 누구야?")
            page.wait_for_timeout(1500)
            page.get_by_text("표도르 파블로비치를 죽인").first.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            page.screenshot(path=str(OUT / "05-스포차단.png"))
            page.set_viewport_size({"width": 1440, "height": 1000})
            print("  05-스포차단.png")
        else:
            print("  (질문 캡처는 --with-answer 로 실행. LLM 호출이 필요합니다)")

        browser.close()
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
