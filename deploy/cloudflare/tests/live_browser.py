"""Synthetic Chromium workflow for the authorized workers.dev preview."""
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = "https://cogniflow-v01.mphamnhat2006.workers.dev"
ROOT = Path(__file__).resolve().parents[1]

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, executable_path=os.environ["CHROMIUM_PATH"], args=["--no-sandbox"])
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(BASE + "/focus")
    page.locator("#api-key").fill((ROOT / ".owner-credential-ts-final").read_text().strip())
    page.locator("#credential-form button").click()
    page.locator("#app-view").wait_for(state="visible")
    cookie = next(c for c in context.cookies() if c["name"] == "__Host-cogniflow")
    assert cookie["secure"] and cookie["httpOnly"] and cookie["sameSite"] == "Strict"
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
    page.locator("#synthetic-estimate").click()
    expect(page.locator("#synthetic-result")).to_contain_text("demo_rule")
    page.reload()
    page.locator("#app-view").wait_for(state="visible")
    page.locator("#disconnect").click() if page.locator("#disconnect").count() else page.get_by_text("Sign out", exact=True).click()
    page.locator("#credential-view").wait_for(state="visible")
    assert not errors, errors
    browser.close()
print("PASS: live Chromium login, secure cookie, lifecycle, estimate, reload, logout; no JS errors")
