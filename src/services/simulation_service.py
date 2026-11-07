"""Circuit simulation control: starting, stopping, and monitoring simulation execution."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from ..browser.browser_manager import BrowserManager
from ..browser.selectors import EDITOR_SELECTORS
from ..config import logger


class SimulationService:
    """Controls the in-browser AVR/circuit simulator in Tinkercad Circuits."""

    def __init__(self, browser: Optional[BrowserManager] = None) -> None:
        self.browser = browser or BrowserManager.get_instance()

    async def start_simulation(self, wait_seconds: int = 2) -> Dict[str, Any]:
        """Start the circuit simulation and wait for it to become active."""
        try:
            wait_seconds = max(0, min(int(wait_seconds), 60))
        except (ValueError, TypeError):
            wait_seconds = 2

        page = await self.browser.get_page()

        # Check if already running
        if await self._is_simulation_active(page):
            time_str = await self._get_simulation_time(page)
            return {
                "success": True,
                "running": True,
                "simulation_time": time_str,
                "message": "Simulation is already running.",
            }

        start_btn = await self.browser.find_first_matching(EDITOR_SELECTORS["start_simulation_btn"], timeout=5000, page=page)
        if not start_btn:
            return {
                "success": False,
                "running": False,
                "message": "Could not find 'Start Simulation' button. Make sure a circuit is opened in the editor.",
            }

        try:
            await self.browser.close_code_panel(page)
        except Exception:
            pass

        logger.info("Clicking 'Start Simulation' button...")
        await start_btn.click()

        # Wait for simulation to transition to active running state
        await page.wait_for_timeout(wait_seconds * 1000)

        # Check if compilation error modal or toast appeared
        error_msg = await self._check_simulation_errors(page)
        if error_msg:
            return {
                "success": False,
                "running": False,
                "error": error_msg,
                "message": f"Simulation failed with error: {error_msg}",
            }

        # Verify simulation is active
        is_running = await self._is_simulation_active(page)
        time_str = await self._get_simulation_time(page)

        return {
            "success": is_running,
            "running": is_running,
            "simulation_time": time_str,
            "message": "Simulation started successfully." if is_running else "Simulation trigger sent.",
        }

    async def stop_simulation(self) -> Dict[str, Any]:
        """Stop the running circuit simulation."""
        page = await self.browser.get_page()

        if not await self._is_simulation_active(page):
            return {
                "success": True,
                "running": False,
                "message": "Simulation is not currently running.",
            }

        stop_btn = await self.browser.find_first_matching(EDITOR_SELECTORS["stop_simulation_btn"], timeout=3000, page=page)
        if not stop_btn:
            # Fallback to general simulation button
            stop_btn = await self.browser.find_first_matching(["a#SIMULATION_ID", "a.js-toggleSimulation"], timeout=1000, page=page)

        if stop_btn:
            logger.info("Clicking 'Stop Simulation' button...")
            await stop_btn.click()
            await page.wait_for_timeout(1000)

        is_running = await self._is_simulation_active(page)

        return {
            "success": not is_running,
            "running": is_running,
            "message": "Simulation stopped." if not is_running else "Stop command sent.",
        }

    async def get_simulation_status(self) -> Dict[str, Any]:
        """Check the status and elapsed time of the simulation."""
        page = await self.browser.get_page()

        is_running = await self._is_simulation_active(page)
        time_str = await self._get_simulation_time(page)
        error_msg = await self._check_simulation_errors(page)

        return {
            "running": is_running,
            "simulation_time": time_str,
            "error": error_msg,
            "message": f"Simulation is {'RUNNING (' + time_str + ')' if is_running else 'STOPPED'}.",
        }

    async def _is_simulation_active(self, page) -> bool:
        """Helper to determine whether the simulation is actively running."""
        try:
            status = await page.evaluate("""
                () => {
                    const btn = document.querySelector('#SIMULATION_ID, .js-toggleSimulation');
                    if (btn) {
                        const txt = btn.querySelector('.js-simulation-text')?.textContent || btn.textContent || '';
                        if (txt.includes('Stop')) return true;
                        const stopIcon = btn.querySelector('.js-simulation-stop');
                        if (stopIcon && !stopIcon.classList.contains('hide')) return true;
                    }
                    return false;
                }
            """)
            if status:
                return True
        except Exception:
            pass
        return await self.browser.find_first_matching(EDITOR_SELECTORS["stop_simulation_btn"], timeout=500, page=page) is not None

    async def _get_simulation_time(self, page) -> str:
        """Helper to get current simulator time string."""
        time_elem = await self.browser.find_first_matching(EDITOR_SELECTORS["simulation_timer"], timeout=1000, page=page)
        if time_elem:
            try:
                return (await time_elem.text_content() or "").strip()
            except Exception:
                pass
        return "00:00:00"

    async def _check_simulation_errors(self, page) -> Optional[str]:
        """Check if an error dialog or toast is visible."""
        try:
            dialog = page.locator(".error-dialog, .notification-error, .alert-danger, .error-message").first
            if await dialog.is_visible(timeout=500):
                return (await dialog.text_content() or "").strip()
        except Exception:
            pass
        return None

