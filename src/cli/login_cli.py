"""Standalone CLI tool to log in to Tinkercad interactively and save session profile."""

from __future__ import annotations

import asyncio
import sys
from ..browser.browser_manager import BrowserManager
from ..services.auth_service import AuthService
from ..config import LOGIN_URL, PROFILE_DIR, logger


async def interactive_login() -> None:
    print("=" * 60)
    print("  Tinkercad Circuits MCP - One-Time Browser Authentication")
    print("=" * 60)
    print(f"Browser profile directory: {PROFILE_DIR}")
    print("Launching visible Chrome window...")

    browser = BrowserManager.get_instance()
    # Force headed browser
    page = await browser.navigate(LOGIN_URL, headless=False)
    auth = AuthService(browser)

    print("\nPlease log into your Autodesk / Tinkercad account in the browser window.")
    print("You can use Autodesk ID, Google Sign-in, or Classrooms / Nicknames.")
    print("\nWaiting for you to reach the dashboard...")

    try:
        # Poll for login status
        login_result = await auth.login(interactive=True, timeout_seconds=300)

        if login_result.get("success"):
            print("\nSUCCESS!")
            print(f"Logged in successfully. Current URL: {login_result.get('url')}")
            print("Your session tokens and cookies have been safely saved.")
            print("You can now close this window and use the Tinkercad MCP Server seamlessly!")
        else:
            print("\nLogin was not detected within timeout. You can run this command again anytime.")
    finally:
        print("\nClosing browser...")
        await browser.close()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    try:
        asyncio.run(interactive_login())
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting...")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
