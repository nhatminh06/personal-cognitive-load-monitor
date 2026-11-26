"""Local Chromium check; requires Playwright and an existing Chromium executable."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:18787"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=os.environ["CHROMIUM_PATH"], args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE + "/focus")
        page.locator(".skip-link").focus()
        page.keyboard.press("Enter")
        assert page.locator("#workspace").evaluate("e => e === document.activeElement")
        page.locator("#api-key").fill((ROOT / ".local-credential").read_text())
        page.locator("#credential-form button").click()
        page.locator("#app-view").wait_for(state="visible")
        cookie = next(c for c in context.cookies() if c["name"] == "__Host-cogniflow")
        assert cookie["secure"] and cookie["httpOnly"] and cookie["sameSite"] == "Strict"
        assert "__Host-cogniflow" not in page.evaluate("document.cookie")
        page.locator('#setup-form button[type="submit"]').click()
        page.locator("#session-view").wait_for(state="visible")
        page.get_by_role("button", name="Pause", exact=True).click()
        page.locator("#dialog-confirm").click()
        expect(page.locator("#state-badge")).to_have_text("paused")
        page.get_by_role("button", name="Resume", exact=True).click()
        expect(page.locator("#state-badge")).to_have_text("resumed")
        page.get_by_role("button", name="Complete", exact=True).click()
        page.locator("#dialog-confirm").click()
        expect(page.locator("#state-badge")).to_have_text("completed")
        # Restore synthetic completed windows prepared by local_smoke.py to exercise rating UI.
        sid = (ROOT / ".wrangler/restart-session").read_text()
        page.evaluate("sid => localStorage.setItem('cogniflow.focus.session-id', sid)", sid)
        page.reload()
        page.locator("#effort-form").wait_for(state="visible")
        page.locator('input[name="effort"][value="5"]').check()
        page.locator("#save-rating").click()
        expect(page.locator("#status-message")).to_contain_text("saved")
        page.locator("#synthetic-estimate").click()
        expect(page.locator("#synthetic-result")).to_contain_text("demo_rule")
        assert page.locator("#timeline li").count() >= 8
        for width in (390, 1280):
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#disconnect").click()
        page.locator("#credential-view").wait_for(state="visible")
        page.wait_for_timeout(200)
        assert page.request.get(BASE + "/sessions/auth-check").status == 401
        assert not errors, errors
        browser.close()
        print("PASS: Chromium login/cookie privacy, keyboard skip link, lifecycle controls, rating, timeline, demo_rule, mobile overflow, logout; no JS errors")


if __name__ == "__main__":
    main()
