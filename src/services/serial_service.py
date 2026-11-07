"""Serial monitor service: opening serial monitor drawer, reading serial output, and sending commands."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from ..browser.browser_manager import BrowserManager
from ..browser.selectors import CODE_SELECTORS, EDITOR_SELECTORS, SERIAL_SELECTORS
from ..config import logger


class SerialService:
    """Controls the Arduino Serial Monitor in Tinkercad Circuits."""

    def __init__(self, browser: Optional[BrowserManager] = None) -> None:
        self.browser = browser or BrowserManager.get_instance()

    async def open_serial_monitor(self) -> Dict[str, Any]:
        """Open or toggle the Serial Monitor drawer."""
        page = await self.browser.get_page()
        await self._ensure_code_panel_open(page)

        toggle_btn = await self.browser.find_first_matching(SERIAL_SELECTORS["toggle_btn"], timeout=3000, page=page)
        if toggle_btn:
            await toggle_btn.click()
            await page.wait_for_timeout(800)
            return {"success": True, "message": "Toggled Serial Monitor panel."}

        return {"success": False, "message": "Could not find Serial Monitor toggle button."}

    async def read_serial_monitor(self, last_n_lines: int = 50) -> Dict[str, Any]:
        """Read the logged output from the Arduino Serial Monitor."""
        try:
            last_n_lines = max(1, min(int(last_n_lines), 1000))
        except (ValueError, TypeError):
            last_n_lines = 50

        page = await self.browser.get_page()
        await self._ensure_serial_monitor_open(page)

        # Scrape text from serial output log
        output_text = await page.evaluate("""
            () => {
                const selectors = [
                    '.js-code_editor__serial-monitor__content',
                    '.js-code_panel__serial__text',
                    '.code_panel__serial__content__text',
                    '.serial-output',
                    'textarea.serial-log',
                    '[data-testid="serial-output"]',
                    '.serial-messages',
                    '.monitor-content',
                    '.serial-monitor-log'
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        return el.value || el.innerText || el.textContent;
                    }
                }
                return "";
            }
        """)

        lines = [line for line in (output_text or "").splitlines() if line.strip()]
        selected_lines = lines[-last_n_lines:] if last_n_lines and len(lines) > last_n_lines else lines

        return {
            "success": True,
            "total_lines": len(lines),
            "lines": selected_lines,
            "raw_output": "\n".join(selected_lines),
            "message": f"Retrieved {len(selected_lines)} lines from Serial Monitor.",
        }

    async def send_serial_monitor(self, text: str, append_newline: bool = True) -> Dict[str, Any]:
        """Send a string/command to the Arduino via the Serial Monitor."""
        page = await self.browser.get_page()
        await self._ensure_serial_monitor_open(page)

        input_field = await self.browser.find_first_matching(SERIAL_SELECTORS["input_field"], timeout=3000, page=page)
        if not input_field:
            return {"success": False, "message": "Could not find Serial Monitor input box."}

        # Type message
        await input_field.click()
        await input_field.fill(text)
        await page.wait_for_timeout(200)

        # Send via button or Enter
        send_btn = await self.browser.find_first_matching(SERIAL_SELECTORS["send_btn"], timeout=1000, page=page)
        if send_btn:
            await send_btn.click()
        else:
            await input_field.press("Enter")

        await page.wait_for_timeout(500)
        logger.info(f"Sent serial input: '{text}'")

        return {
            "success": True,
            "sent_text": text,
            "message": f"Successfully sent '{text}' to Serial Monitor.",
        }

    async def clear_serial_monitor(self) -> Dict[str, Any]:
        """Clear the Serial Monitor output display."""
        page = await self.browser.get_page()
        await self._ensure_serial_monitor_open(page)

        clear_btn = await self.browser.find_first_matching(SERIAL_SELECTORS["clear_btn"], timeout=2000, page=page)
        if clear_btn:
            await clear_btn.click()
            await page.wait_for_timeout(300)
            return {"success": True, "message": "Serial Monitor cleared."}

        # Fallback evaluate to clear value
        await page.evaluate("""
            () => {
                const el = document.querySelector(
                    '.js-code_editor__serial-monitor__content, .js-code_panel__serial__text, .code_panel__serial__content__text, .serial-output, textarea.serial-log, [data-testid="serial-output"]'
                );
                if (el) {
                    if (el.value !== undefined) el.value = '';
                    if (el.innerText !== undefined) el.innerText = '';
                    if (el.textContent !== undefined) el.textContent = '';
                }
            }
        """)
        return {"success": True, "message": "Serial Monitor cleared via DOM."}

    async def _ensure_code_panel_open(self, page) -> None:
        """Helper to ensure the code panel is open."""
        is_active = await page.locator(
            "a#CODE_EDITOR_ID.active, .js-toggle_code_panel.active, a.circ_btn.active[data-event='code-editor']"
        ).count() > 0
        if is_active:
            return

        panel = await self.browser.find_first_matching(CODE_SELECTORS["panel"], timeout=1000, page=page)
        if not panel:
            code_btn = await self.browser.find_first_matching(EDITOR_SELECTORS["code_toggle_btn"], timeout=2000, page=page)
            if code_btn:
                await code_btn.click()
                await page.wait_for_timeout(1000)

    async def _ensure_serial_monitor_open(self, page) -> None:
        """Helper to ensure the serial monitor drawer is open."""
        await self._ensure_code_panel_open(page)

        # Check if already open (height > 0 or content text container is visible)
        is_open = await page.evaluate("""
            () => {
                const textEl = document.querySelector(
                    '.js-code_editor__serial-monitor__content, .code_panel__serial__content__text, .code_panel__serial__content'
                );
                if (textEl && textEl.offsetHeight > 0) return true;
                const arrow = document.querySelector('.js-code_panel__serial__arrow');
                if (arrow && arrow.classList.contains('code_panel__serial__arrow__up')) return true;
                return false;
            }
        """)
        if not is_open:
            toggle_btn = await self.browser.find_first_matching(SERIAL_SELECTORS["toggle_btn"], timeout=2000, page=page)
            if toggle_btn:
                await toggle_btn.click()
                await page.wait_for_timeout(800)

