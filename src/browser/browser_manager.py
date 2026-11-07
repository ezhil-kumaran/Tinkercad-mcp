"""Async Playwright browser management for Tinkercad with persistent session caching."""

from __future__ import annotations

import asyncio
import base64
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    Locator,
    async_playwright,
)

from ..config import (
    DEFAULT_HEADLESS,
    DEFAULT_TIMEOUT_MS,
    NO_SANDBOX,
    PROFILE_DIR,
    SCREENSHOTS_DIR,
    logger,
)
from .selectors import CODE_SELECTORS, COMPONENTS_SELECTORS, EDITOR_SELECTORS


class BrowserManager:
    """Manages persistent Playwright browser context and active pages."""

    _instance: Optional[BrowserManager] = None

    def __init__(self) -> None:
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.current_headless: bool = DEFAULT_HEADLESS
        self._lock: Optional[asyncio.Lock] = None
        self._op_lock: Optional[asyncio.Lock] = None

    @property
    def lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @property
    def operation_lock(self) -> asyncio.Lock:
        if self._op_lock is None:
            self._op_lock = asyncio.Lock()
        return self._op_lock

    @classmethod
    def get_instance(cls) -> BrowserManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _is_context_alive(self) -> bool:
        """Check whether current browser context is active, connected, and not closed."""
        if self.context is None:
            return False
        try:
            if hasattr(self.context, "is_closed") and self.context.is_closed():
                return False
            # Verify context can still list pages without throwing TargetClosedError
            _ = self.context.pages
            return True
        except Exception:
            return False

    async def ensure_context(self, headless: Optional[bool] = None) -> BrowserContext:
        """Ensure persistent browser context is launched, healthy, and ready."""
        target_headless = headless if headless is not None else DEFAULT_HEADLESS

        async with self.lock:
            # Check if existing context is alive, healthy, and matches desired headless mode
            if self._is_context_alive() and self.current_headless == target_headless:
                assert self.context is not None
                return self.context

            # If mode changed or existing context is dead/closed, close and clean up
            if self.context is not None or self.playwright is not None:
                logger.info(
                    f"Resetting browser context (alive={self._is_context_alive()}, "
                    f"mode={self.current_headless} -> {target_headless})"
                )
                await self.close_locked()

            if self.playwright is None:
                self.playwright = await async_playwright().start()

            logger.info(f"Launching persistent browser context (headless={target_headless}, profile='{PROFILE_DIR}')")
            self.current_headless = target_headless

            # Launch persistent Chromium context with secure arguments for WebGL canvas rendering
            args = [
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--enable-webgl",
            ]
            if NO_SANDBOX:
                logger.warning("Chromium sandbox disabled via TINKERCAD_NO_SANDBOX=true.")
                args.extend(["--no-sandbox", "--disable-setuid-sandbox"])

            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=target_headless,
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                args=args,
                accept_downloads=True,
            )

            self.context.set_default_timeout(DEFAULT_TIMEOUT_MS)

            # Block heavy tracking, analytics, and telemetry to speed up Tinkercad WebGL initialization
            await self._setup_route_blocking(self.context)

            # Register close listener so BrowserManager automatically knows when window/context dies
            def _on_context_close():
                logger.info("Playwright BrowserContext closed event received. Resetting active context.")
                self.context = None
                self.page = None

            self.context.on("close", _on_context_close)

            # Get or create initial page
            try:
                pages = [p for p in self.context.pages if not p.is_closed()]
                if pages:
                    self.page = pages[0]
                else:
                    self.page = await self.context.new_page()
            except Exception as e:
                logger.warning(f"Error getting page from new context: {e}")
                self.page = await self.context.new_page()

            return self.context

    @staticmethod
    async def _setup_route_blocking(context: BrowserContext) -> None:
        """Block heavy tracking, analytics, and telemetry scripts to speed up Tinkercad WebGL initialization."""
        tracking_regex = re.compile(
            r"https?://.*(google-analytics|googletagmanager|segment\.io|segment\.com|"
            r"hotjar|optimizely|heap\.io|fullstory|datadoghq|"
            r"browser-intake-datadoghq|clarity\.ms|doubleclick).*",
            re.IGNORECASE,
        )

        async def _block_trackers(route):
            try:
                await route.abort()
            except Exception:
                pass

        try:
            if hasattr(context, "route"):
                await context.route(tracking_regex, _block_trackers)
                logger.info("Configured route interception to block heavy telemetry and analytics trackers.")
        except Exception as e:
            logger.debug(f"Could not configure tracker route blocking: {e}")

    async def get_page(self, headless: Optional[bool] = None) -> Page:
        """Get the current active page, launching browser or recovering automatically if closed."""
        for attempt in range(2):
            try:
                await self.ensure_context(headless=headless)
                assert self.context is not None

                if self.page is None or self.page.is_closed():
                    pages = [p for p in self.context.pages if not p.is_closed()]
                    if pages:
                        self.page = pages[0]
                    else:
                        self.page = await self.context.new_page()

                if self.page.is_closed():
                    raise RuntimeError("Active page is closed")

                return self.page
            except Exception as e:
                err_str = str(e).lower()
                is_closed_err = (
                    "closed" in err_str or
                    "target" in err_str or
                    "destroyed" in err_str
                )
                if attempt == 0 and is_closed_err:
                    logger.warning(
                        f"BrowserContext or Page was closed unexpectedly ({e}). "
                        f"Auto-recovering and relaunching persistent session..."
                    )
                    async with self.lock:
                        await self.close_locked()
                    continue
                raise

    async def restart(self, headless: Optional[bool] = None) -> Dict[str, Any]:
        """Explicitly restart the persistent browser context and return session status."""
        target_headless = headless if headless is not None else self.current_headless
        async with self.lock:
            await self.close_locked()
        page = await self.get_page(headless=target_headless)
        return {
            "success": True,
            "message": f"Successfully restarted persistent browser context (headless={target_headless}).",
            "url": page.url,
            "headless": target_headless,
        }

    async def navigate(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout: Optional[int] = None,
        headless: Optional[bool] = None,
    ) -> Page:
        """Navigate to a URL and wait for page to reach target state."""
        page = await self.get_page(headless=headless)
        t = timeout or DEFAULT_TIMEOUT_MS
        logger.info(f"Navigating to {url} (wait_until={wait_until}, timeout={t}ms)")
        await page.goto(url, wait_until=wait_until, timeout=t)  # type: ignore[arg-type]
        await page.wait_for_timeout(1000)
        return page

    async def find_first_matching(
        self, selectors: List[str], timeout: int = 5000, page: Optional[Page] = None
    ) -> Optional[Locator]:
        """Try a list of selector alternatives and return the first one found."""
        p = page or await self.get_page()
        for sel in selectors:
            try:
                locator = p.locator(sel).first
                if await locator.is_visible(timeout=timeout):
                    return locator
            except Exception:
                continue
        return None

    async def click_first_matching(
        self, selectors: List[str], timeout: int = 5000, page: Optional[Page] = None
    ) -> bool:
        """Click the first matching selector from a fallback list."""
        locator = await self.find_first_matching(selectors, timeout=timeout, page=page)
        if locator:
            try:
                await locator.click()
                return True
            except Exception as e:
                logger.warning(f"Failed clicking matched element: {e}")
        return False

    async def ensure_circuits_view_active(self, page: Optional[Page] = None) -> bool:
        """Ensure the workspace is switched to the primary Circuits/Breadboard view."""
        p = page or await self.get_page()
        try:
            is_active = await p.evaluate("""
                () => {
                    const btn = document.querySelector(
                        'button.workspace-switcher__button.workspace-switcher__button--active, ' +
                        'button.workspace-switcher__button[aria-pressed="true"]'
                    );
                    if (btn && btn.textContent.toLowerCase().includes('circuits')) return true;
                    const schematic = document.querySelector('#schematicTab, .workspace-schematic');
                    if (schematic && window.getComputedStyle(schematic).display !== 'none') return false;
                    const compList = document.querySelector('#bomTab, .workspace-bom, #componentListTab');
                    if (compList && window.getComputedStyle(compList).display !== 'none') return false;
                    return true;
                }
            """)
            if not is_active:
                from ..services.circuits_service import CircuitsService
                cs = CircuitsService(self)
                res = await cs.switch_workspace_view("circuits")
                return res.get("success", False)
            return True
        except Exception:
            return False

    async def close_code_panel(self, page: Optional[Page] = None) -> bool:
        """Close the code editor drawer if it is currently open or blocking."""
        p = page or await self.get_page()
        try:
            # Check if code toggle button is active or code panel is visible
            is_active = await p.evaluate("""
                () => {
                    const panel = document.querySelector('.js-tpl-target__code_panel, .code_panel, #scratchDiv, .blocklyDiv, .blocklySvg, .injectionDiv, .CodeMirror');
                    if (panel) {
                        const rect = panel.getBoundingClientRect();
                        if (rect.height > 50 && rect.width > 50 && window.getComputedStyle(panel).display !== 'none') {
                            return true;
                        }
                    }
                    // Also check for the empty code panel message
                    const bodyText = document.body ? document.body.innerText : '';
                    if (bodyText.includes('No programmable components in this circuit')) {
                        return true;
                    }
                    const btn = Array.from(document.querySelectorAll(
                        'a#CODE_EDITOR_ID, .js-toggle_code_panel, a.circ_btn, [data-testid="code-button"], button, a'
                    )).find(el => {
                        const t = (el.textContent || '').trim();
                        const isCode = t === 'Code' || el.id === 'CODE_EDITOR_ID' || el.getAttribute('data-event') === 'code-editor';
                        const isActive = el.classList.contains('active') || el.getAttribute('aria-pressed') === 'true' || el.classList.contains('selected');
                        return isCode && isActive;
                    });
                    return !!btn;
                }
            """)
            if is_active:
                logger.info("Code panel is active/open. Closing to prevent click interception...")
                code_btn = await self.find_first_matching(EDITOR_SELECTORS["code_toggle_btn"], timeout=2000, page=p)
                if code_btn:
                    await code_btn.click()
                    await p.wait_for_timeout(800)
                    try:
                        await p.evaluate("""() => {
                            document.querySelectorAll('.js-tpl-target__code_panel, .code_panel, #scratchDiv, .blocklyDiv, .blocklySvg, .injectionDiv').forEach(el => {
                                el.style.pointerEvents = 'none';
                            });
                        }""")
                    except Exception:
                        pass
                    return True

                clicked = await p.evaluate("""
                    () => {
                        const candidates = Array.from(document.querySelectorAll('a#CODE_EDITOR_ID, .js-toggle_code_panel, a[data-event="code-editor"], button, a')).filter(el => {
                            const t = (el.textContent || '').trim();
                            return (t === 'Code' || el.id === 'CODE_EDITOR_ID' || el.getAttribute('data-event') === 'code-editor') && el.offsetParent !== null;
                        });
                        if (candidates.length > 0) {
                            candidates[0].click();
                            return true;
                        }
                        return false;
                    }
                """)
                if clicked:
                    await p.wait_for_timeout(800)
                    try:
                        await p.evaluate("""() => {
                            document.querySelectorAll('.js-tpl-target__code_panel, .code_panel, #scratchDiv, .blocklyDiv, .blocklySvg, .injectionDiv').forEach(el => {
                                el.style.pointerEvents = 'none';
                            });
                        }""")
                    except Exception:
                        pass
                    return True
        except Exception as e:
            logger.warning(f"Error checking/closing code panel: {e}")
        return False

    async def close_overlays_and_modals(self, page: Optional[Page] = None) -> bool:
        """Close any open modals, dialogs, or popovers that intercept pointer events."""
        p = page or await self.get_page()
        closed_any = False
        try:
            close_btn = await self.find_first_matching(COMPONENTS_SELECTORS.get("modal_close", []), timeout=500, page=p)
            if close_btn:
                await close_btn.click()
                await p.wait_for_timeout(400)
                closed_any = True

            has_dialog = await p.evaluate("""
                () => {
                    const d = document.querySelector('.modal:not(.hide), .ui-dialog:not(.hidden), .confirm-dialog');
                    return !!d && window.getComputedStyle(d).display !== 'none';
                }
            """)
            if has_dialog:
                await p.keyboard.press("Escape")
                await p.wait_for_timeout(300)
                closed_any = True
        except Exception as e:
            logger.debug(f"Error closing overlays: {e}")
        return closed_any

    async def ensure_canvas_interactive(self, page: Optional[Page] = None) -> bool:
        """Ensure the canvas is visible, interactive, and no overlays intercept pointer events."""
        p = page or await self.get_page()
        await self.close_code_panel(page=p)
        await self.close_overlays_and_modals(page=p)
        canvas = await self.find_first_matching(EDITOR_SELECTORS["editor_canvas"], timeout=5000, page=p)
        return canvas is not None

    async def ensure_components_drawer_open(self, page: Optional[Page] = None) -> bool:
        """Ensure the component drawer is open and unobstructed."""
        p = page or await self.get_page()
        await self.close_code_panel(page=p)
        await self.close_overlays_and_modals(page=p)

        drawer = await self.find_first_matching(COMPONENTS_SELECTORS["drawer"], timeout=1000, page=p)
        if not drawer:
            await self.click_first_matching(EDITOR_SELECTORS["components_toggle_btn"], timeout=2000, page=p)
            await p.wait_for_timeout(800)
            drawer = await self.find_first_matching(COMPONENTS_SELECTORS["drawer"], timeout=3000, page=p)
        return drawer is not None

    async def is_pointer_intercepted(
        self, x: int, y: int, target_selector: Optional[str] = None, page: Optional[Page] = None
    ) -> tuple[bool, Optional[str]]:
        """Check if pointer click at (x, y) would be intercepted by an unexpected overlay element."""
        p = page or await self.get_page()
        try:
            interceptor = await p.evaluate("""
                ({x, y, sel}) => {
                    const el = document.elementFromPoint(x, y);
                    if (!el) return null;
                    if (sel) {
                        const target = document.querySelector(sel);
                        if (target && (el === target || target.contains(el))) {
                            return null;
                        }
                    }
                    if (el.closest('.js-tpl-target__code_panel, .code_panel, #scratchDiv, .blocklyDiv, .blocklySvg, .injectionDiv, .modal, .ui-dialog, .overlay')) {
                        const blocker = el.closest('.js-tpl-target__code_panel, .code_panel, #scratchDiv, .blocklyDiv, .blocklySvg, .injectionDiv, .modal, .ui-dialog, .overlay');
                        return blocker.className || blocker.tagName;
                    }
                    return null;
                }
            """, {"x": x, "y": y, "sel": target_selector})
            if interceptor:
                return True, interceptor
        except Exception:
            pass
        return False, None

    @staticmethod
    def _sanitize_screenshot_filename(filename: Optional[str]) -> str:
        """Sanitize filename to prevent path traversal and ensure safe PNG naming."""
        if not filename or not filename.strip():
            import time
            return f"tinkercad_{int(time.time())}.png"

        # Extract only the base filename to strip any directory traversal attempts
        name = Path(filename).name.strip()
        # Sanitize against any characters other than alphanumerics, underscores, hyphens, and dots
        clean_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)
        # Strip leading dots or empty result
        clean_name = clean_name.lstrip(".")
        if not clean_name:
            import time
            clean_name = f"tinkercad_{int(time.time())}.png"
        elif not clean_name.lower().endswith(".png"):
            clean_name = f"{clean_name}.png"

        return clean_name

    async def take_screenshot(
        self,
        filename: Optional[str] = None,
        full_page: bool = False,
        page: Optional[Page] = None,
    ) -> Dict[str, Any]:
        """Capture screenshot safely and return saved file path and base64 string."""
        p = page or await self.get_page()
        safe_filename = self._sanitize_screenshot_filename(filename)
        save_path = (SCREENSHOTS_DIR / safe_filename).resolve()

        # Security check: verify the resolved path is strictly within SCREENSHOTS_DIR
        screenshots_dir_resolved = SCREENSHOTS_DIR.resolve()
        try:
            save_path.relative_to(screenshots_dir_resolved)
        except ValueError:
            raise ValueError(f"Path traversal detected: {filename} cannot be saved outside {SCREENSHOTS_DIR}")

        bytes_data = await p.screenshot(path=str(save_path), full_page=full_page)
        b64_str = base64.b64encode(bytes_data).decode("utf-8")
        logger.info(f"Screenshot safely saved to {save_path}")

        return {
            "path": str(save_path),
            "filename": safe_filename,
            "base64": b64_str,
            "width": p.viewport_size["width"] if p.viewport_size else 1440,
            "height": p.viewport_size["height"] if p.viewport_size else 900,
        }

    async def close_locked(self) -> None:
        """Internal close helper (assumes lock is acquired)."""
        try:
            if self.context:
                await self.context.close()
        except Exception as e:
            msg = str(e).lower()
            if "'nonetype' object has no attribute 'send'" in msg or "event loop is closed" in msg or "closed" in msg or "target" in msg:
                logger.debug(f"Harmless transport cleanup during context close: {e}")
            else:
                logger.warning(f"Error closing browser context: {e}")
        finally:
            self.context = None
            self.page = None

        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            msg = str(e).lower()
            if "'nonetype' object has no attribute 'send'" in msg or "event loop is closed" in msg or "closed" in msg or "target" in msg:
                logger.debug(f"Harmless transport cleanup during playwright stop: {e}")
            else:
                logger.warning(f"Error stopping playwright: {e}")
        finally:
            self.playwright = None

    async def close(self) -> None:
        """Public method to close context and browser."""
        async with self.lock:
            await self.close_locked()

