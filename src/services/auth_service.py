"""Authentication and session management for Tinkercad."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

from ..browser.browser_manager import BrowserManager
from ..browser.selectors import AUTH_SELECTORS, DASHBOARD_SELECTORS
from ..config import (
    BASE_URL,
    DASHBOARD_URL,
    LOGIN_URL,
    JOIN_URL,
    logger,
)


class AuthService:
    """Handles Tinkercad authentication, status checks, login, and logout."""

    def __init__(self, browser: Optional[BrowserManager] = None) -> None:
        self.browser = browser or BrowserManager.get_instance()

    async def get_auth_status(self) -> Dict[str, Any]:
        """Check whether the persistent browser session is authenticated."""
        page = await self.browser.get_page()

        # If on blank or about:blank, navigate to dashboard to test auth
        if page.url in ("about:blank", "", "chrome://newtab/"):
            await self.browser.navigate(DASHBOARD_URL)

        current_url = page.url

        # Check for avatar or profile menu
        avatar = await self.browser.find_first_matching(AUTH_SELECTORS["user_avatar"], timeout=3000, page=page)
        if avatar:
            user_text = ""
            try:
                user_text = (await avatar.get_attribute("title")) or (await avatar.text_content()) or "User"
            except Exception:
                user_text = "Authenticated User"
            return {
                "authenticated": True,
                "user": user_text.strip(),
                "current_url": current_url,
                "message": f"Successfully authenticated as {user_text.strip()}.",
            }

        # Check if login or join buttons are present (indicates logged out)
        login_btn = await self.browser.find_first_matching(AUTH_SELECTORS["login_button"], timeout=2000, page=page)
        if login_btn or "login" in current_url or "join" in current_url:
            return {
                "authenticated": False,
                "user": None,
                "current_url": current_url,
                "message": "Not authenticated. Please call 'tinkercad_login' to sign in.",
            }

        # Check cookies for actual authentication token
        try:
            cookies = await page.context.cookies()
            has_auth_cookie = any(
                c.get("name", "").lower() in ("tinkerauth", "oxygen_session", "autodesk_session")
                or ("auth" in c.get("name", "").lower() and c.get("name", "").lower() != "tinkercad-ldid")
                for c in cookies
            )
            if has_auth_cookie:
                return {
                    "authenticated": True,
                    "user": "Tinkercad User",
                    "current_url": current_url,
                    "message": "Session is active with valid authentication token.",
                }
        except Exception:
            pass

        # Otherwise attempt dashboard check
        try:
            await self.browser.navigate(DASHBOARD_URL, timeout=15000)
            page = await self.browser.get_page()
            avatar = await self.browser.find_first_matching(AUTH_SELECTORS["user_avatar"], timeout=4000, page=page)
            if avatar:
                return {
                    "authenticated": True,
                    "user": "Tinkercad User",
                    "current_url": page.url,
                    "message": "Session is authenticated.",
                }
        except Exception as e:
            logger.warning(f"Error checking dashboard auth: {e}")

        return {
            "authenticated": False,
            "user": None,
            "current_url": page.url,
            "message": "Not logged in. Use 'tinkercad_login' to sign into your account.",
        }

    @staticmethod
    def validate_login_params(
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout_seconds: int = 180,
    ) -> tuple[bool, Optional[str], int]:
        """Validate login parameters, check for partial credentials, and bound timeout."""
        try:
            bounded_timeout = max(10, min(int(timeout_seconds), 600))
        except (ValueError, TypeError):
            bounded_timeout = 180

        if (username and not password) or (password and not username):
            return False, "Both username and password are required when providing credentials.", bounded_timeout

        return True, None, bounded_timeout

    async def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        interactive: bool = True,
        timeout_seconds: int = 180,
    ) -> Dict[str, Any]:
        """Sign in to Tinkercad either via interactive headed window or automated credentials."""
        valid, err_msg, timeout_seconds = self.validate_login_params(username, password, timeout_seconds)
        if not valid:
            return {
                "success": False,
                "message": err_msg or "Invalid login parameters.",
                "url": LOGIN_URL,
            }

        # For interactive or SSO (Autodesk ID / Google / Classrooms), launch headed browser
        headless = False if interactive else None
        page = await self.browser.navigate(LOGIN_URL, headless=headless)

        if username and password:
            # Automated credential input
            logger.info("Attempting automated credential input on login form...")
            try:
                email_field = await self.browser.find_first_matching(AUTH_SELECTORS["email_input"], timeout=8000, page=page)
                if email_field:
                    await email_field.fill(username)
                    next_btn = await self.browser.find_first_matching(AUTH_SELECTORS["next_button"], timeout=3000, page=page)
                    if next_btn:
                        await next_btn.click()
                        await page.wait_for_timeout(2000)

                    pass_field = await self.browser.find_first_matching(AUTH_SELECTORS["password_input"], timeout=8000, page=page)
                    if pass_field:
                        await pass_field.fill(password)
                        submit_btn = await self.browser.find_first_matching(AUTH_SELECTORS["signin_submit_button"], timeout=3000, page=page)
                        if submit_btn:
                            await submit_btn.click()
                            await page.wait_for_timeout(3000)
            except Exception as e:
                logger.warning(f"Error during credential input: {e}")

        # Wait for user to complete sign-in (or automated redirect to dashboard)
        start_time = time.time()
        logger.info(f"Waiting for successful sign in (up to {timeout_seconds}s)...")
        while time.time() - start_time < timeout_seconds:
            curr_url = page.url
            if "dashboard" in curr_url or "things" in curr_url:
                logger.info("Detected dashboard URL! Login successful.")
                return {
                    "success": True,
                    "message": "Login successful! Session has been saved to your persistent browser profile.",
                    "url": curr_url,
                }

            avatar = await self.browser.find_first_matching(AUTH_SELECTORS["user_avatar"], timeout=1000, page=page)
            if avatar:
                logger.info("Detected user avatar! Login successful.")
                return {
                    "success": True,
                    "message": "Login successful! Session has been saved to your persistent browser profile.",
                    "url": page.url,
                }

            # Check for error alerts (invalid password, unknown account, lockout, etc.)
            error_elem = await self.browser.find_first_matching(AUTH_SELECTORS["error_alert"], timeout=500, page=page)
            if error_elem:
                try:
                    err_txt = (await error_elem.text_content() or "").strip()
                    if err_txt:
                        logger.warning(f"Detected login error on page: {err_txt}")
                        return {
                            "success": False,
                            "message": f"Authentication failed: {err_txt}",
                            "url": page.url,
                        }
                except Exception:
                    pass

            await asyncio.sleep(2)

        return {
            "success": False,
            "message": f"Login timed out after {timeout_seconds} seconds. Please complete sign in and try again.",
            "url": page.url,
        }

    async def open_signup(self, interactive: bool = True) -> Dict[str, Any]:
        """Navigate to Tinkercad account creation / join page."""
        headless = False if interactive else None
        page = await self.browser.navigate(JOIN_URL, headless=headless)
        return {
            "success": True,
            "url": page.url,
            "message": (
                "Opened Tinkercad signup page (https://www.tinkercad.com/join). "
                "Select 'Personal Account' or 'Students' to create your Autodesk Tinkercad account. "
                "Once completed, your session will persist."
            ),
        }

    async def logout(self) -> Dict[str, Any]:
        """Sign out and clear stored session cookies."""
        page = await self.browser.get_page()
        try:
            # Click logout button if visible
            clicked = await self.browser.click_first_matching(AUTH_SELECTORS["logout_button"], timeout=3000, page=page)
            if not clicked:
                # Direct navigate to logout endpoint
                await page.goto(f"{BASE_URL}/logout", timeout=10000)

            # Clear context cookies to ensure clean logout
            if self.browser.context:
                await self.browser.context.clear_cookies()

            return {
                "success": True,
                "message": "Successfully logged out of Tinkercad and cleared session cookies.",
            }
        except Exception as e:
            logger.warning(f"Error during logout: {e}")
            if self.browser.context:
                await self.browser.context.clear_cookies()
            return {
                "success": True,
                "message": f"Session cookies cleared: {e}",
            }

