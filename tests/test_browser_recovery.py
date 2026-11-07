"""Tests for BrowserManager auto-recovery, resilient session lifecycle, and browser restart."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.browser.browser_manager import BrowserManager
from src.server import server


class TestBrowserRecovery(unittest.IsolatedAsyncioTestCase):
    """Test suite for persistent browser session resilience and auto-recovery."""

    async def asyncSetUp(self):
        self.bm = BrowserManager()
        # Reset internal references
        self.bm.context = None
        self.bm.page = None
        self.bm.playwright = None

    async def asyncTearDown(self):
        await self.bm.close()

    def test_is_context_alive_handles_none_and_closed(self):
        """Returns False when context is None, closed, or raises an error."""
        self.assertFalse(self.bm._is_context_alive())

        mock_ctx = MagicMock()
        mock_ctx.is_closed = MagicMock(return_value=True)
        self.bm.context = mock_ctx
        self.assertFalse(self.bm._is_context_alive())

        mock_ctx.is_closed = MagicMock(return_value=False)
        mock_ctx.pages = []
        self.assertTrue(self.bm._is_context_alive())

        # If accessing pages raises TargetClosedError
        type(mock_ctx).pages = property(MagicMock(side_effect=Exception("Target page, context or browser has been closed")))
        self.assertFalse(self.bm._is_context_alive())

    async def test_ensure_context_recycles_dead_context(self):
        """ensure_context automatically closes a dead context and launches a new one."""
        dead_ctx = MagicMock()
        dead_ctx.is_closed = MagicMock(return_value=True)
        dead_ctx.close = AsyncMock()

        healthy_page = MagicMock()
        healthy_page.is_closed = MagicMock(return_value=False)

        new_ctx = MagicMock()
        new_ctx.is_closed = MagicMock(return_value=False)
        new_ctx.pages = [healthy_page]
        new_ctx.new_page = AsyncMock(return_value=healthy_page)
        new_ctx.close = AsyncMock()
        new_ctx.on = MagicMock()
        new_ctx.set_default_timeout = MagicMock()

        mock_pw = MagicMock()
        mock_pw.stop = AsyncMock()
        mock_pw.chromium.launch_persistent_context = AsyncMock(return_value=new_ctx)

        self.bm.context = dead_ctx
        self.bm.playwright = mock_pw

        with patch("src.browser.browser_manager.async_playwright") as mock_ap:
            mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
            ctx = await self.bm.ensure_context()
            self.assertEqual(ctx, new_ctx)
            dead_ctx.close.assert_awaited()

    async def test_get_page_recovers_from_target_closed_error(self):
        """get_page auto-recovers and relaunches context when new_page raises TargetClosedError."""
        dead_ctx = MagicMock()
        dead_ctx.is_closed = MagicMock(return_value=False)
        dead_ctx.pages = []
        # Simulate target closed during new_page
        dead_ctx.new_page = AsyncMock(side_effect=Exception("BrowserContext.new_page: Target page, context or browser has been closed"))
        dead_ctx.close = AsyncMock()

        healthy_page = AsyncMock()
        healthy_page.is_closed = MagicMock(return_value=False)

        recovered_ctx = MagicMock()
        recovered_ctx.is_closed = MagicMock(return_value=False)
        recovered_ctx.pages = [healthy_page]
        recovered_ctx.close = AsyncMock()
        recovered_ctx.on = MagicMock()
        recovered_ctx.set_default_timeout = MagicMock()

        mock_pw = MagicMock()
        mock_pw.stop = AsyncMock()
        mock_pw.chromium.launch_persistent_context = AsyncMock(side_effect=[dead_ctx, recovered_ctx])

        with patch("src.browser.browser_manager.async_playwright") as mock_ap:
            mock_ap.return_value.start = AsyncMock(return_value=mock_pw)

            page = await self.bm.get_page()
            self.assertEqual(page, healthy_page)
            self.assertFalse(page.is_closed())

    async def test_restart_method_forces_clean_context_relaunch(self):
        """restart() explicitly closes active context and returns status."""
        old_ctx = MagicMock()
        old_ctx.close = AsyncMock()
        self.bm.context = old_ctx

        new_page = AsyncMock()
        new_page.url = "https://www.tinkercad.com/dashboard"
        new_page.is_closed = MagicMock(return_value=False)

        new_ctx = MagicMock()
        new_ctx.is_closed = MagicMock(return_value=False)
        new_ctx.pages = [new_page]
        new_ctx.close = AsyncMock()
        new_ctx.on = MagicMock()
        new_ctx.set_default_timeout = MagicMock()

        mock_pw = MagicMock()
        mock_pw.stop = AsyncMock()
        mock_pw.chromium.launch_persistent_context = AsyncMock(return_value=new_ctx)

        with patch("src.browser.browser_manager.async_playwright") as mock_ap:
            mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
            res = await self.bm.restart(headless=True)

            self.assertTrue(res["success"])
            self.assertIn("Successfully restarted", res["message"])
            self.assertEqual(res["url"], "https://www.tinkercad.com/dashboard")
            old_ctx.close.assert_awaited()

    async def test_context_on_close_event_clears_references(self):
        """When Playwright emits 'close' on the context, internal references are cleared."""
        ctx_on_handlers = {}

        healthy_page = MagicMock()
        healthy_page.is_closed = MagicMock(return_value=False)

        mock_ctx = MagicMock()
        mock_ctx.is_closed = MagicMock(return_value=False)
        mock_ctx.pages = [healthy_page]
        mock_ctx.new_page = AsyncMock(return_value=healthy_page)
        mock_ctx.close = AsyncMock()
        mock_ctx.set_default_timeout = MagicMock()

        def fake_on(event, handler):
            ctx_on_handlers[event] = handler

        mock_ctx.on = MagicMock(side_effect=fake_on)

        mock_pw = MagicMock()
        mock_pw.stop = AsyncMock()
        mock_pw.chromium.launch_persistent_context = AsyncMock(return_value=mock_ctx)

        with patch("src.browser.browser_manager.async_playwright") as mock_ap:
            mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
            await self.bm.ensure_context()
            self.assertIsNotNone(self.bm.context)
            self.assertIn("close", ctx_on_handlers)

            # Trigger close event
            ctx_on_handlers["close"]()
            self.assertIsNone(self.bm.context)
            self.assertIsNone(self.bm.page)


if __name__ == "__main__":
    unittest.main()
