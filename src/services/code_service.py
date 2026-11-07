"""Code editor service: toggling code panel, switching to text mode, reading and injecting Arduino sketch code."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from ..browser.browser_manager import BrowserManager
from ..browser.selectors import CODE_SELECTORS, EDITOR_SELECTORS
from ..config import logger


class CodeService:
    """Manages reading and writing Arduino microcontroller code in Tinkercad Circuits."""

    def __init__(self, browser: Optional[BrowserManager] = None) -> None:
        self.browser = browser or BrowserManager.get_instance()

    async def get_code(self) -> Dict[str, Any]:
        """Read the currently loaded sketch/code from the code editor."""
        page = await self.browser.get_page()
        await self._ensure_code_panel_open(page)

        # Attempt reading via CodeMirror (preferred), dev.properties, Ace, or visible textarea
        code_text = await page.evaluate("""
            () => {
                try {
                    // 1. CodeMirror JS API (primary for Tinkercad text editor)
                    const cmEl = document.querySelector('.CodeMirror');
                    if (cmEl && cmEl.CodeMirror) {
                        const val = cmEl.CodeMirror.getValue();
                        if (val !== undefined && val !== null && val.trim() !== '') {
                            return val;
                        }
                    }

                    // 2. Query microcontroller device model code in circuit_editor properties
                    const ce = window.circuit_editor;
                    if (ce?.data?.devices?._content) {
                        for (const k in ce.data.devices._content) {
                            const dev = ce.data.devices._content[k]?.val || ce.data.devices._content[k];
                            if (dev?.properties?._content) {
                                for (const pid in dev.properties._content) {
                                    const prop = dev.properties._content[pid]?.val || dev.properties._content[pid];
                                    if (prop && (prop.name === 'Code' || prop.unit === 'code') && prop.value) {
                                        return prop.value;
                                    }
                                }
                            }
                            if (dev?.codemirrorDoc && typeof dev.codemirrorDoc.getValue === 'function') {
                                const c = dev.codemirrorDoc.getValue();
                                if (c && c.trim() !== '') return c;
                            }
                        }
                    }

                    // 3. Ace editor JS API fallback
                    const aceEl = document.querySelector('.ace_editor');
                    if (aceEl && window.ace) {
                        const editor = window.ace.edit(aceEl);
                        return editor.getValue();
                    }

                    // 4. Visible code textarea fallback
                    const visibleTa = Array.from(document.querySelectorAll(
                        'textarea.js-code_editor__textarea, textarea.code_editor__textarea, .js-code_editor__textarea, textarea.code-editor, textarea.ace_text-input'
                    )).find(el => el.offsetParent !== null || (window.getComputedStyle(el).display !== 'none' && window.getComputedStyle(el).visibility !== 'hidden'));
                    if (visibleTa && visibleTa.value !== undefined && visibleTa.value.trim() !== '') {
                        return visibleTa.value;
                    }

                    // 5. Any textarea fallback
                    const ta = document.querySelector(
                        'textarea.js-code_editor__textarea, textarea.code_editor__textarea, .js-code_editor__textarea'
                    );
                    if (ta && ta.value !== undefined && ta.value.trim() !== '') {
                        return ta.value;
                    }
                } catch(e) {}
                return null;
            }
        """)

        if code_text is None:
            # Fallback: scrape visible code lines from DOM
            lines = await page.locator(".CodeMirror-line, .cm-line, .ace_line").all_text_contents()
            if lines:
                code_text = "\n".join(lines)

        mode = await self._get_current_mode(page)

        return {
            "success": True,
            "mode": mode,
            "line_count": len(code_text.splitlines()) if code_text else 0,
            "code": code_text or "",
            "message": f"Successfully retrieved code ({len(code_text.splitlines()) if code_text else 0} lines).",
        }

    async def set_code(
        self,
        code: str,
        ensure_text_mode: bool = True,
        verify_persistence: bool = True,
    ) -> Dict[str, Any]:
        """Inject or write Arduino C++ sketch code into the editor.

        Args:
            code: The Arduino C++ source code to write into the sketch editor
            ensure_text_mode: If True, automatically switches editor from Blocks to Text mode
            verify_persistence: If True, verifies code was accepted and persists after reload
        """
        page = await self.browser.get_page()
        await self._ensure_code_panel_open(page)

        if ensure_text_mode:
            await self._switch_to_text_mode(page)

        line_count = len(code.splitlines())
        updated = False

        # 1. Primary: Type via Playwright keyboard input into CodeMirror.
        # This emits genuine user input events (origin: '+input') that Tinkercad's ShareJS
        # operational transformation engine requires to generate deltas and save to cloud servers.
        editor_el = await self.browser.find_first_matching(
            [".CodeMirror-lines", ".CodeMirror-scroll", ".CodeMirror"] + CODE_SELECTORS.get("codemirror_input", []) + CODE_SELECTORS["code_textarea"],
            timeout=2000,
            page=page,
        )
        if editor_el:
            try:
                await editor_el.click()
                await page.wait_for_timeout(300)
                if hasattr(page, "keyboard"):
                    await page.keyboard.press("Control+a")
                    await page.wait_for_timeout(200)
                    await page.keyboard.insert_text(code)
                    await page.wait_for_timeout(1000)
                    updated = True
            except Exception as e:
                logger.debug(f"Keyboard insertion had error: {e}")

        # 2. Fallback: Only if keyboard typing was not possible, update CodeMirror/textarea via DOM
        dom_success = False
        if not updated:
            dom_success = await page.evaluate("""
                (newCode) => {
                    let success = false;
                    try {
                        const cmEl = document.querySelector('.CodeMirror');
                        if (cmEl && cmEl.CodeMirror) {
                            const cm = cmEl.CodeMirror;
                            cm.setValue(newCode);
                            if (typeof cm.save === 'function') cm.save();
                            if (typeof cm.refresh === 'function') cm.refresh();
                            cmEl.dispatchEvent(new Event('input', { bubbles: true }));
                            cmEl.dispatchEvent(new Event('change', { bubbles: true }));
                            success = true;
                        }

                        const ta = document.querySelector('textarea.js-code_editor__textarea, textarea.code_editor__textarea');
                        if (ta) {
                            ta.value = newCode;
                            ta.dispatchEvent(new Event('input', { bubbles: true }));
                            ta.dispatchEvent(new Event('change', { bubbles: true }));
                            success = true;
                        }
                    } catch(e) {}
                    return success;
                }
            """, code)

        if not updated and not dom_success:
            return {
                "success": False,
                "verified": False,
                "error": "editor_write_failed",
                "message": "Failed to set code: neither CodeMirror nor textarea could be updated.",
            }

        logger.info(f"Updated code editor with {line_count} lines of code.")

        # Commit changes and trigger save to Tinkercad cloud servers
        await page.evaluate("""
            () => {
                // Blur active element to commit any pending controller operations
                if (document.activeElement && typeof document.activeElement.blur === 'function') {
                    document.activeElement.blur();
                }

                // Trigger root circuit save
                const ce = window.circuit_editor;
                if (ce) {
                    if (ce.root && typeof ce.root.save === 'function') {
                        try { ce.root.save(); } catch(e) {}
                    }
                    if (ce.data && typeof ce.data.save === 'function') {
                        try { ce.data.save(); } catch(e) {}
                    }
                    if (typeof ce.save === 'function') {
                        try { ce.save(); } catch(e) {}
                    }
                }
                window.dispatchEvent(new CustomEvent('save'));
            }
        """)

        # Immediate readback verification to ensure editor accepted the value
        immediate_read = await self.get_code()
        immediate_code = immediate_read.get("code", "")
        if code.strip() != immediate_code.strip():
            logger.warning("Code verification failed: editor did not accept the new code.")
            return {
                "success": False,
                "verified": False,
                "error": "code_not_accepted",
                "message": "Editor did not accept the new code. Live value did not match.",
                "expected_lines": line_count,
                "actual_lines": len(immediate_code.splitlines()),
            }

        # Cloud persistence verification across reload if requested
        if verify_persistence:
            # Allow 5.0s for ShareJS operational transformation and autosave network XHR to complete
            await page.wait_for_timeout(5000)

            # If on a live circuit project page, reload and verify cloud persistence
            current_url = getattr(page, "url", "")
            if current_url and "/things/" in current_url and hasattr(page, "reload"):
                logger.info("Verifying code persistence across circuit page reload...")
                try:
                    await page.reload(wait_until="domcontentloaded")
                    await page.wait_for_timeout(5000)
                    await self._ensure_code_panel_open(page)
                    persisted_read = await self.get_code()
                    persisted_code = persisted_read.get("code", "")
                    if code.strip() != persisted_code.strip():
                        logger.error("Code persistence failed: code reverted after page reload!")
                        return {
                            "success": False,
                            "verified": False,
                            "error": "code_persistence_failed",
                            "message": "Code change reverted upon project reload. Autosave did not persist the code.",
                            "code": persisted_code,
                        }
                    logger.info("Code persistence successfully verified after page reload.")
                except Exception as e:
                    logger.warning(f"Reload persistence check encountered non-fatal error: {e}")

        return {
            "success": True,
            "verified": verify_persistence,
            "line_count": line_count,
            "message": f"Successfully set and verified {line_count} lines of Arduino sketch code.",
        }

    async def _ensure_code_panel_open(self, page) -> None:
        """Ensure the code panel drawer is visible and fully interactive."""
        is_open = await page.evaluate("""
            () => {
                const btn = document.querySelector('a#CODE_EDITOR_ID, .js-toggle_code_panel, a.circ_btn[data-event="code-editor"], [data-testid="code-button"]');
                const btnActive = btn && (btn.classList.contains('active') || btn.getAttribute('aria-pressed') === 'true');
                const panel = document.querySelector('.js-tpl-target__code_panel, .code_panel, #scratchDiv, #code-editor-drawer, .code-editor');
                if (panel) {
                    const style = window.getComputedStyle(panel);
                    const rect = panel.getBoundingClientRect();
                    if (style.display !== 'none' && style.visibility !== 'hidden' && rect.height > 80 && rect.width > 80) {
                        return true;
                    }
                }
                return !!btnActive;
            }
        """)

        if not is_open:
            code_btn = await self.browser.find_first_matching(EDITOR_SELECTORS["code_toggle_btn"], timeout=2000, page=page)
            if code_btn:
                await code_btn.click()
            else:
                await page.evaluate("""
                    () => {
                        const btn = document.querySelector('a#CODE_EDITOR_ID, .js-toggle_code_panel, a[data-event="code-editor"], [data-testid="code-button"]');
                        if (btn) btn.click();
                    }
                """)
            await page.wait_for_timeout(1000)

        # Unblock pointer events on panel elements in case close_code_panel set pointer-events: none
        await page.evaluate("""
            () => {
                document.querySelectorAll(
                    '.js-tpl-target__code_panel, .code_panel, #scratchDiv, .blocklyDiv, .blocklySvg, .injectionDiv, .CodeMirror, textarea, .cm-editor, .cm-content'
                ).forEach(el => {
                    el.style.pointerEvents = 'auto';
                });
            }
        """)

    async def _switch_to_text_mode(self, page) -> None:
        """Switch code editor mode to Text (Arduino C++), handling confirmation modal."""
        current_mode = await self._get_current_mode(page)
        if current_mode.lower() == "text":
            return

        logger.info(f"Current mode is '{current_mode}'. Switching to 'Text' mode...")

        # 1. Click the mode dropdown button
        await page.evaluate("""
            () => {
                const modeContainer = document.querySelector('.code_panel__toolbar__mode, .js-code_panel__toolbar__mode');
                const btn = modeContainer ? modeContainer.querySelector('.editor__dropdown__button') : null;
                if (btn) {
                    btn.click();
                    return;
                }
                const btns = Array.from(document.querySelectorAll('.editor__dropdown__button, [class*="mode"]'));
                for (const b of btns) {
                    const txt = b.textContent?.trim();
                    if (txt === 'Blocks' || txt === 'Blocks + Text' || txt === 'Text') {
                        b.click();
                        return;
                    }
                }
            }
        """)
        await page.wait_for_timeout(400)

        # 2. Click the "Text" option
        await page.evaluate("""
            () => {
                const options = Array.from(document.querySelectorAll(
                    '.editor__dropdown__list__option__value, .editor__dropdown__list__option, .goog-menuitem, li'
                ));
                for (const opt of options) {
                    const txt = opt.textContent?.trim();
                    if (txt === 'Text' || opt.getAttribute('data-item') === 'text') {
                        opt.click();
                        return;
                    }
                }
            }
        """)
        await page.wait_for_timeout(600)

        # 3. Confirm modal dialog ("Are you sure you want to close the blocks editor?")
        confirm_btn = await self.browser.find_first_matching(CODE_SELECTORS["confirm_modal_continue"], timeout=2000, page=page)
        if confirm_btn:
            await confirm_btn.click()
        else:
            await page.evaluate("""
                () => {
                    const btns = Array.from(document.querySelectorAll('.modal button, .confirm-dialog button, button'));
                    for (const b of btns) {
                        const txt = (b.textContent || '').trim().toLowerCase();
                        if (txt === 'continue' || txt === 'ok') {
                            b.click();
                            return;
                        }
                    }
                }
            """)
        await page.wait_for_timeout(1000)

    async def _get_current_mode(self, page) -> str:
        """Get current editor mode string (Blocks, Blocks + Text, or Text)."""
        try:
            mode = await page.evaluate("""
                () => {
                    const modeContainer = document.querySelector('.code_panel__toolbar__mode, .js-code_panel__toolbar__mode');
                    const btn = modeContainer ? modeContainer.querySelector('.editor__dropdown__button') : null;
                    if (btn && btn.textContent?.trim() === 'Text') {
                        return 'Text';
                    }
                    const cm = document.querySelector('.CodeMirror, .cm-editor, .ace_editor');
                    if (cm) {
                        const rect = cm.getBoundingClientRect();
                        if (rect.height > 50 && window.getComputedStyle(cm).display !== 'none') {
                            return 'Text';
                        }
                    }
                    return 'Blocks';
                }
            """)
            if mode:
                return mode
        except Exception:
            pass
        return "Blocks"
