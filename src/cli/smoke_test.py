"""Quick smoke-test script to test Tinkercad MCP services directly from the terminal."""

from __future__ import annotations

import asyncio
import sys
from ..browser.browser_manager import BrowserManager
from ..services.auth_service import AuthService
from ..services.circuits_service import CircuitsService
from ..catalog.components_catalog import list_components_catalog


async def run_smoke_test() -> None:
    print("=" * 65)
    print("   Tinkercad MCP Server - Self-Diagnostic Smoke Test")
    print("=" * 65)

    # 1. Component catalog check
    comps = list_components_catalog()
    print(f"\n[1/3] Components Catalog: {len(comps)} electronic components loaded.")
    arduino = next((c for c in comps if "arduino" in c["name"].lower()), None)
    if arduino:
        print(f"      Verified: {arduino['name']} with {len(arduino['pins'])} pin definitions.")

    # 2. Browser & Auth Check
    print("\n[2/3] Checking Browser Profile and Auth Status...")
    browser = BrowserManager.get_instance()
    auth = AuthService(browser)
    circuits = CircuitsService(browser)

    try:
        status = await auth.get_auth_status()
        is_logged_in = status.get("is_logged_in", False)
        print(f"      Auth Status: {'LOGGED IN' if is_logged_in else 'NOT LOGGED IN'}")
        print(f"      Current URL: {status.get('current_url', 'N/A')}")

        if not is_logged_in:
            print("\n      [!] Note: You are not currently logged in.")
            print("          To log in, run: .\\.venv\\Scripts\\python -m src.cli.login_cli")
        else:
            # 3. Circuits listing check
            print("\n[3/3] Fetching circuits from dashboard...")
            circuits_list = await circuits.list_circuits()
            count = circuits_list.get("count", 0)
            print(f"      Found {count} circuit design(s) in your account:")
            for c in circuits_list.get("circuits", [])[:5]:
                print(f"        - {c.get('title', 'Untitled')} ({c.get('url', '')})")

        print("\n" + "=" * 65)
        print("   Smoke Test Completed Successfully!")
        print("=" * 65)

    finally:
        await browser.close()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    try:
        asyncio.run(run_smoke_test())
    except KeyboardInterrupt:
        print("\nTest cancelled by user.")
    except Exception as e:
        print(f"\nTest encountered error: {e}")


if __name__ == "__main__":
    main()

