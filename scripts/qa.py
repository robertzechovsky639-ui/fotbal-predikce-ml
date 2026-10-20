"""Mobilní průchod: dny, filtry, detail, oblíbené, vlastní predikce, týmy, chat, model."""
import pathlib
import sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1]
OUT = pathlib.Path(__file__).resolve().parents[1] / "screenshots"
OUT.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
issues = []


def chk(cond, msg):
    if not cond:
        issues.append(msg)
        print("CHYBA:", msg)


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/usr/local/bin/google-chrome", args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, user_agent=UA)
    errs = []
    page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errs.append("JS: " + str(e)))
    page.goto(URL)
    page.wait_for_selector(".m[data-id]", timeout=60000)
    page.wait_for_timeout(2500)
    page.screenshot(path=str(OUT / "01_zapasy.png"))
    n_all = page.locator(".m[data-id]").count()
    chk(n_all > 0, "dnes bez zápasů")
    for value in ["all", "europe_top", "czech", "asia", "south_america", "europe_cups"]:
        page.select_option("#reg", value)
        page.wait_for_timeout(250)
        n = page.locator(".m[data-id]").count()
        print("region", value, n)
        chk(n > 0 or page.locator(".empty").count() == 1, f"region {value} bez karty i prázdného stavu")
    page.select_option("#reg", "focus")
    for value in ["live", "up", "fin", "all"]:
        page.select_option("#filt", value)
        page.wait_for_timeout(200)
        print("filtr", value, page.locator(".m[data-id]").count())
        chk(page.locator(".m[data-id]").count() > 0 or page.locator(".empty").count() == 1, f"filtr {value}")
    page.select_option("#filt", "all")
    for day in ["-1", "1", "2", "-2", "0"]:
        page.click(f'.days button[data-day="{day}"]')
        page.wait_for_timeout(300)
        print("den", day, page.locator(".m[data-id]").count())
    page.locator(".m[data-id]").first.click()
    page.wait_for_selector(".tabs")
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "05_detail.png"))
    for tab in ["predikce", "kurzy", "h2h", "stat"]:
        page.click(f'.tabs button[data-t="{tab}"]')
        page.wait_for_timeout(300)
        text = page.inner_text("#detail")
        chk("undefined" not in text and "NaN" not in text, f"detail/{tab}")
    page.click("#fv")
    page.click("#bk")
    page.click('nav.bottom button[data-v="oblibene"]')
    page.wait_for_timeout(300)
    chk(page.locator(".m[data-id]").count() >= 1, "oblíbené prázdné")
    page.click('nav.bottom button[data-v="predikce"]')
    page.fill("#pa", "Arsenal")
    page.fill("#pb", "Chelsea")
    page.press("#pb", "Enter")
    page.wait_for_timeout(400)
    chk("%" in page.inner_text("#pres"), "vlastní predikce")
    page.screenshot(path=str(OUT / "08_predikce.png"))
    page.click('nav.bottom button[data-v="tymy"]')
    page.fill("#ps", "Arsenal")
    page.wait_for_timeout(500)
    chk(page.locator("#plist .fac").count() > 0, "týmy")
    page.click('nav.bottom button[data-v="chat"]')
    page.fill("#cq", "Arsenal vs Chelsea")
    page.click("#cs")
    page.wait_for_timeout(400)
    chk("%" in page.inner_text("#msgs"), "chat")
    page.click('nav.bottom button[data-v="model"]')
    page.wait_for_timeout(400)
    body = page.inner_text("body")
    chk("LOG LOSS" in body and "RPS" in body, "model bez metrik")
    chk("undefined" not in body and "NaN" not in body, "NaN v modelu")
    page.screenshot(path=str(OUT / "11_model.png"))
    # predikce na všech vykreslených kartách
    page.click('nav.bottom button[data-v="zapasy"]')
    page.select_option("#reg", "all")
    page.select_option("#filt", "all")
    page.wait_for_timeout(400)
    cards = page.locator(".m[data-id]")
    count = cards.count()
    bare = 0
    for i in range(min(count, 40)):
        if "%" not in cards.nth(i).inner_text():
            bare += 1
    chk(bare == 0, f"karty bez procent: {bare}")
    print("karet dnes", n_all, "console", errs[:6], "PROBLÉMY", issues or "žádné")
    browser.close()
sys.exit(1 if issues else 0)
