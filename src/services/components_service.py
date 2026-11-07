"""Component management: catalog browsing, placing parts on canvas, removing, and setting properties."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Optional

from ..browser.browser_manager import BrowserManager
from ..browser.selectors import COMPONENTS_SELECTORS, EDITOR_SELECTORS
from ..catalog.components_catalog import (
    COMPONENTS_CATALOG,
    find_component_by_did,
    find_component_by_query,
    find_component_candidates,
    list_components_catalog,
)
from ..config import logger


class ComponentsService:
    """Handles component catalog inspection, placement, removal, and property configuration."""

    def __init__(self, browser: Optional[BrowserManager] = None) -> None:
        self.browser = browser or BrowserManager.get_instance()
        self._placed_count = 0
        self._placed_origins: List[Dict[str, Any]] = []

    @staticmethod
    def get_component_exclusion_radius(comp_name: str) -> int:
        """Return the safe exclusion radius (in canvas pixels) for a component to prevent hitbox overlap."""
        name = (comp_name or "").lower().strip()
        if "breadboard" in name:
            if "mini" in name:
                return 110
            if "small" in name or "half" in name:
                return 140
            return 190
        if any(k in name for k in ("arduino", "uno", "micro:bit", "controller", "atmega", "esp32", "esp8266")):
            return 150
        if any(k in name for k in ("lcd", "display", "screen", "oled", "7 segment", "7-segment")):
            return 160
        if any(k in name for k in ("keypad",)):
            return 130
        if any(k in name for k in ("ultrasonic", "distance", "sonar", "hcsr04", "hc-sr04")):
            return 110
        if any(k in name for k in ("servo", "motor", "stepper", "driver", "l293d", "h-bridge", "gear")):
            return 110
        if any(k in name for k in ("battery", "power supply", "9v", "coin cell")):
            return 110
        if any(k in name for k in ("pir", "tmp36", "temperature", "photo", "ldr", "tilt", "gas", "piezo", "buzzer", "relay")):
            return 85
        if any(k in name for k in ("led", "resistor", "capacitor", "diode", "pushbutton", "button", "potentiometer", "switch", "slide switch")):
            return 60
        return 100

    def get_placed_origins(self) -> List[Dict[str, Any]]:
        """Return copy of tracked component origins and exclusion radii."""
        return [dict(o) for o in self._placed_origins]

    def clear_placed_origins(self) -> None:
        """Reset the stored origin coordinates of placed components."""
        self._placed_origins.clear()
        self._placed_count = 0

    def record_placed_origin(
        self,
        instance_id: str,
        name: str,
        x: int,
        y: int,
        radius: Optional[int] = None,
    ) -> None:
        """Store or update the origin coordinate and exclusion radius of a placed component."""
        rad = radius if radius is not None else self.get_component_exclusion_radius(name)
        for o in self._placed_origins:
            if o.get("instance_id") == instance_id:
                o["name"] = name
                o["x"] = int(x)
                o["y"] = int(y)
                o["radius"] = rad
                return
        self._placed_origins.append({
            "instance_id": str(instance_id),
            "name": str(name),
            "x": int(x),
            "y": int(y),
            "radius": int(rad),
        })

    async def zoom_to_fit(self, page: Optional[Any] = None) -> Dict[str, Any]:
        """Zoom canvas to fit all placed components into view."""
        from .circuits_service import CircuitsService
        cs = CircuitsService(self.browser)
        return await cs.zoom_canvas(action="fit")

    async def zoom_out(self, steps: int = 1, page: Optional[Any] = None) -> Dict[str, Any]:
        """Zoom out canvas to give more workspace."""
        from .circuits_service import CircuitsService
        cs = CircuitsService(self.browser)
        return await cs.zoom_canvas(action="out", steps=steps)

    async def list_available_components(
        self, category: Optional[str] = None, search: Optional[str] = None
    ) -> Dict[str, Any]:
        """List electronic components available for use in Tinkercad Circuits."""
        items = list_components_catalog(category=category)
        if search:
            s = search.lower().strip()
            items = [
                i for i in items
                if s in i["name"].lower() or s in i["description"].lower() or s in i["id"].lower()
            ]

        return {
            "success": True,
            "total_count": len(items),
            "components": items,
        }

    @staticmethod
    def validate_coordinates(x: Optional[int], y: Optional[int]) -> tuple[bool, Optional[str]]:
        """Validate canvas coordinates are within realistic bounds (-1000 to 10000)."""
        if x is not None and not (-1000 <= x <= 10000):
            return False, f"X coordinate {x} out of bounds (-1000 to 10000)."
        if y is not None and not (-1000 <= y <= 10000):
            return False, f"Y coordinate {y} out of bounds (-1000 to 10000)."
        return True, None

    async def _ensure_all_components_category(self, page) -> bool:
        """Switch component picker category dropdown to 'All' so non-basic components are visible and initialized."""
        try:
            return await page.evaluate(r"""
                () => {
                    const catBtn = document.querySelector(
                        '#COMPONENT_CATEGORY_SELECT, a[data-event="component-group-select"], a.editor__component_picker__category_dropdown'
                    );
                    if (catBtn) {
                        const txt = (catBtn.textContent || '').trim().toLowerCase();
                        if (txt.includes('all')) return true;
                        catBtn.click();
                        const opts = Array.from(document.querySelectorAll(
                            '.editor__dropdown__list__option, .editor__dropdown__list__option__value, .dropdown-menu a, [data-item], li'
                        ));
                        for (const opt of opts) {
                            const val = (opt.getAttribute('data-item') || opt.getAttribute('data-value') || '').toLowerCase();
                            const optTxt = (opt.textContent || '').trim().toLowerCase();
                            if (val === 'all' || optTxt === 'all' || optTxt.includes('all components')) {
                                opt.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }
            """)
        except Exception:
            return False

    async def add_component(
        self,
        component_name: Optional[str] = None,
        component_id: Optional[str] = None,
        x: Optional[int] = None,
        y: Optional[int] = None,
        required_pins: Optional[List[str]] = None,
        min_pins: Optional[int] = None,
        verify_persistence: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Add a component onto the circuit canvas by name/type at specified or default coordinates.

        Args:
            component_name: Name or keyword of component (e.g. 'Arduino Uno R3', 'LED', 'H-bridge Motor Driver')
            component_id: Alias for component_name (accepts catalog ID or component name)
            x: Optional canvas X coordinate
            y: Optional canvas Y coordinate
            required_pins: Optional list of pin names that must exist on the placed component (e.g. ['trig', 'echo'])
            min_pins: Optional minimum number of pins required on the component (e.g. 4 for HC-SR04)
            verify_persistence: Optional flag to verify component survives page reload
        """
        raw_name = component_name or component_id or kwargs.get("name") or kwargs.get("id")
        if not raw_name:
            return {"success": False, "message": "Either component_name or component_id must be provided."}
        component_name = str(raw_name).strip()

        valid, err_msg = self.validate_coordinates(x, y)
        if not valid:
            return {"success": False, "message": err_msg or "Invalid coordinates."}

        # Check for ultrasonic sensor disambiguation
        name_lower = component_name.lower().strip()
        needs_4pin_ultrasonic = (
            ("ultrasonic" in name_lower or "hc-sr04" in name_lower or "sonar" in name_lower or "distance sensor" in name_lower)
            and not ("3-pin" in name_lower or "3 pin" in name_lower or "3pin" in name_lower)
        )
        if required_pins and any(p.lower() in ("trig", "echo", "trigger") for p in required_pins):
            needs_4pin_ultrasonic = True

        if needs_4pin_ultrasonic:
            comp_def = find_component_by_query("ultrasonic_sensor_4pin", required_pins=required_pins)
            min_pins = min_pins or 4
            required_pins = required_pins or ["trig", "echo"]
        else:
            candidates = find_component_candidates(component_name)
            comp_def = find_component_by_query(component_name, required_pins=required_pins)
            if len(candidates) > 1 and comp_def is None:
                return {
                    "success": False,
                    "error": "ambiguous_component_match",
                    "matches": [c.name for c in candidates],
                    "message": f"Query '{component_name}' is ambiguous. Please specify exact component name or ID.",
                }

        search_query = comp_def.name if comp_def else component_name.strip()
        if search_query:
            import re
            search_query = re.sub(r'\[.*?\]', '', search_query).strip()
        target_did = comp_def.did if comp_def else None

        page = await self.browser.get_page()

        # Proactively ensure Circuits (breadboard) view is active
        if hasattr(self.browser, "ensure_circuits_view_active"):
            await self.browser.ensure_circuits_view_active(page)

        # Proactively ensure the code drawer is collapsed to prevent pointer interception
        try:
            await self.browser.close_code_panel(page)
        except Exception:
            pass

        # Ensure code panels, popovers, and blocking overlays are closed and drawer is open
        await self.browser.ensure_components_drawer_open(page)

        # Switch component category to 'All' to ensure non-basic components (e.g. 4-pin ultrasonic, ICs) are loaded
        await self._ensure_all_components_category(page)

        # Record components before placement for verification
        before_instances = await page.evaluate("""
            () => {
                const ce = window.circuit_editor;
                const devMap = ce?.data?.devices?._content || {};
                const ids = Object.keys(devMap);
                if (ids.length > 0) return ids;
                // Also try TC app state
                try {
                    const app = window.TC?.app || window.tcApp;
                    if (app) {
                        const devs = app.circuit?.devices || app.editor?.circuit?.devices;
                        if (devs) return Object.keys(devs);
                    }
                } catch(e) {}
                // Fallback: SVG ids/classes
                return Array.from(document.querySelectorAll('#breadboardTab svg[class*="cgfx__"]')).map((el, i) => el.id || `svg_${i}`);
            }
        """)

        # Search for component in the drawer
        search_box = await self.browser.find_first_matching(COMPONENTS_SELECTORS["search_input"], timeout=3000, page=page)
        if search_box:
            await search_box.click()
            await search_box.fill("")
            await search_box.fill(search_query)
            await search_box.press("Enter")
            search_btn = await self.browser.find_first_matching(COMPONENTS_SELECTORS.get("search_btn", []), timeout=500, page=page)
            if search_btn:
                try:
                    await search_btn.click()
                except Exception:
                    pass
            await page.wait_for_timeout(800)

        # Select matching card using stable identity and strict matching
        # Inspect visible and catalog cards in the drawer
        card_match_info = await page.evaluate(r"""
            ({searchQuery, targetDid}) => {
                const query = searchQuery.toLowerCase().replace(/\[.*?\]/g, '').trim();
                const targetDidStr = targetDid ? String(targetDid).toLowerCase() : null;

                // Explicitly target actual component card containers only, excluding chevrons and scrollbars
                const cards = Array.from(document.querySelectorAll(
                    '.editor__component_picker__groups__item, div[data-did], .catalog-item'
                ));

                // 1. Exact DID match: check all cards and unhide if marked hidden
                if (targetDidStr) {
                    for (let i = 0; i < cards.length; i++) {
                        const card = cards[i];
                        if (
                            card.classList.contains('editor__component_picker__groups__item__list__chevron') ||
                            card.classList.contains('chevron') ||
                            card.closest('.editor__component_picker__groups__item__list__chevron')
                        ) {
                            continue;
                        }

                        const did = card.getAttribute('data-did')?.toLowerCase() || null;
                        if (did === targetDidStr) {
                            card.classList.remove('hidden');
                            card.style.display = 'block';
                            card.style.visibility = 'visible';
                            if (typeof card.scrollIntoView === 'function') {
                                card.scrollIntoView({ block: 'center', inline: 'center' });
                            }
                            const rect = card.getBoundingClientRect();
                            const titleEl = card.querySelector(
                                '.editor__component_picker__groups__item__grid__title, .editor__component_picker__groups__item__list__title, .component-title, .title, [data-component-name]'
                            );
                            const title = (titleEl?.textContent || card.getAttribute('data-component-name') || card.getAttribute('title') || searchQuery).trim();
                            const clickX = Math.round(rect.x + (rect.width > 0 ? rect.width / 2 : 50));
                            const clickY = Math.round(rect.y + (rect.height > 0 ? rect.height / 2 : 50));
                            return {
                                selected: { index: i, did, title, clickX, clickY },
                                matches: [{ index: i, did, title }]
                            };
                        }
                    }
                }

                const items = [];
                for (let i = 0; i < cards.length; i++) {
                    const card = cards[i];

                    // Skip chevrons, list toggles, and search container wrappers
                    if (
                        card.classList.contains('editor__component_picker__groups__item__list__chevron') ||
                        card.classList.contains('chevron') ||
                        card.closest('.editor__component_picker__groups__item__list__chevron')
                    ) {
                        continue;
                    }

                    // Skip invisible or zero-sized cards
                    const rect = card.getBoundingClientRect();
                    if (
                        rect.width <= 15 || rect.height <= 15 ||
                        card.offsetParent === null ||
                        window.getComputedStyle(card).display === 'none' ||
                        window.getComputedStyle(card).visibility === 'hidden'
                    ) {
                        continue;
                    }

                    const did = card.getAttribute('data-did')?.toLowerCase() || null;
                    const titleEl = card.querySelector(
                        '.editor__component_picker__groups__item__grid__title, .editor__component_picker__groups__item__list__title, .component-title, .title, [data-component-name]'
                    );
                    const title = (titleEl?.textContent || card.getAttribute('data-component-name') || card.getAttribute('title') || '').trim();
                    if (!title && !did) continue;

                    const clickX = Math.round(rect.x + rect.width / 2);
                    const clickY = Math.round(rect.y + rect.height / 2);

                    items.push({
                        index: i,
                        did: did,
                        title: title,
                        clickX: clickX,
                        clickY: clickY,
                    });
                }

                // 2. Exact Title match
                const exactTitle = items.filter(it => it.title.toLowerCase() === query);
                if (exactTitle.length === 1) return { selected: exactTitle[0], matches: exactTitle };
                if (exactTitle.length > 1) {
                    return { selected: exactTitle[0], matches: exactTitle };
                }

                // 3. Title starts with or contains query as whole word
                const prefixTitle = items.filter(it => {
                    const t = it.title.toLowerCase();
                    return t === query || t.startsWith(query + ' ') || t.split(/\s+/).some(w => w === query);
                });
                if (prefixTitle.length === 1) return { selected: prefixTitle[0], matches: prefixTitle };
                if (prefixTitle.length > 1) {
                    return { selected: null, ambiguous: true, matches: prefixTitle };
                }

                // 4. Broad contains match
                const containMatches = items.filter(it => {
                    const t = it.title.toLowerCase().replace(/\[.*?\]/g, '').trim();
                    return t.includes(query) || query.includes(t);
                });
                if (containMatches.length === 1) return { selected: containMatches[0], matches: containMatches };
                if (containMatches.length > 1) {
                    return { selected: null, ambiguous: true, matches: containMatches };
                }

                return { selected: null, matches: [] };
            }
        """, {"searchQuery": search_query, "targetDid": target_did})

        if card_match_info.get("ambiguous"):
            match_titles = [m.get("title") for m in card_match_info.get("matches", []) if m.get("title")]
            return {
                "success": False,
                "error": "ambiguous_component_match",
                "matches": list(dict.fromkeys(match_titles)),
                "message": f"Ambiguous component matches in drawer for '{search_query}'. Matches: {match_titles}",
            }

        selected_card = card_match_info.get("selected")
        if not selected_card:
            return {
                "success": False,
                "error": "component_not_found",
                "message": f"Could not find component '{search_query}' in the Tinkercad component drawer.",
            }

        card_title = selected_card.get('title') or search_query

        # Calculate target placement coordinates using collision-avoidance auto-layout engine
        target_x, target_y = await self._find_non_overlapping_coordinates(
            page, requested_x=x, requested_y=y, comp_name=card_title
        )
        logger.info(f"Placing component '{card_title}' at canvas ({target_x}, {target_y})")

        # In Tinkercad Circuits, clicking the component card attaches it to the cursor, then clicking canvas places it
        click_x = selected_card.get("clickX")
        click_y = selected_card.get("clickY")

        # Verify and ensure the card is physically visible in the viewport using Playwright locator
        if hasattr(page, "locator") and not asyncio.iscoroutinefunction(page.locator):
            try:
                card_loc = None
                if target_did:
                    raw_loc = page.locator(f"div[data-did='{target_did}']")
                    if not asyncio.iscoroutine(raw_loc):
                        first_loc = raw_loc.first
                        if await first_loc.count() > 0:
                            card_loc = first_loc
                if not card_loc:
                    cand = page.locator(".editor__component_picker__groups__item, div[data-did], .catalog-item")
                    if not asyncio.iscoroutine(cand) and hasattr(cand, "filter"):
                        filt = cand.filter(has_text=card_title)
                        first_filt = filt.first
                        if await first_filt.count() > 0:
                            card_loc = first_filt
                if card_loc:
                    await card_loc.scroll_into_view_if_needed(timeout=2000)
                    box = await card_loc.bounding_box()
                    if box and 0 <= box["y"] <= 850 and 0 <= box["x"] <= 1400:
                        click_x = round(box["x"] + box["width"] / 2)
                        click_y = round(box["y"] + box["height"] / 2)
            except Exception:
                pass

        if click_x is None or click_y is None:
            return {
                "success": False,
                "error": "component_card_not_clickable",
                "message": f"Component card '{card_title}' was matched but could not be located on screen.",
            }

        try:
            # Detect and clear any pointer interception on component card before clicking
            intercepted, blocker = await self.browser.is_pointer_intercepted(click_x, click_y, page=page)
            if intercepted:
                logger.warning(f"Card click intercepted by '{blocker}'. Closing overlays...")
                await self.browser.close_code_panel(page)
                await self.browser.close_overlays_and_modals(page)

            # Detect and clear any pointer interception on canvas drop coordinates (e.g. Code drawer overlay)
            intercepted_drop, blocker_drop = await self.browser.is_pointer_intercepted(target_x, target_y, page=page)
            if intercepted_drop:
                logger.warning(f"Canvas drop point ({target_x}, {target_y}) intercepted by '{blocker_drop}'. Closing drawer/overlays...")
                await self.browser.close_code_panel(page)
                await self.browser.close_overlays_and_modals(page)
                try:
                    await page.evaluate("""() => {
                        document.querySelectorAll('.js-tpl-target__code_panel, .code_panel, #scratchDiv, .blocklyDiv, .blocklySvg, .injectionDiv').forEach(el => {
                            el.style.pointerEvents = 'none';
                        });
                    }""")
                except Exception:
                    pass

            await page.mouse.click(click_x, click_y)
            await page.wait_for_timeout(500)
            await page.mouse.move(target_x, target_y)
            await page.wait_for_timeout(300)
            await page.mouse.click(target_x, target_y)
            await page.wait_for_timeout(800)

            # Proactively dismiss any opened property inspector popover or code drawer
            try:
                await page.keyboard.press("Escape")
                await self.browser.close_code_panel(page)
                await self.browser.close_overlays_and_modals(page)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Error during click-place: {e}")
            return {"success": False, "error": "placement_error", "message": f"Failed to place component: {e}"}

        # Clear search input and reset drawer filter so next search succeeds immediately without reload
        if search_box:
            try:
                await search_box.fill("")
                await search_box.press("Enter")
            except Exception:
                pass

        # Give the editor a little more time to process the drop
        await page.wait_for_timeout(1500)

        # Verify the placed component exists on canvas using structured editor state
        placed_verification = await page.evaluate("""
            ({beforeIds, targetDid, compName}) => {
                const ce = window.circuit_editor;
                const devMap = ce?.data?.devices?._content || {};
                const currentIds = Object.keys(devMap);

                // Find newly added device ID
                const newIds = currentIds.filter(id => !beforeIds.includes(id));
                if (newIds.length > 0) {
                    const newId = newIds[newIds.length - 1];
                    const dev = devMap[newId]?.val || devMap[newId];
                    const desc = dev?.getDescription ? dev.getDescription() : null;
                    const dName = dev?.name ? String(dev.name()) : '';
                    const dDid = dev?.did ? String(dev.did()) : null;
                    const typeName = desc?.device?.name || desc?.footprint_name || compName;
                    
                    const pins = [];
                    const n2t = dev?.name2terminal?._content || {};
                    for (const tName of Object.keys(n2t)) {
                        pins.push(String(tName));
                    }

                    return {
                        verified: true,
                        instance_id: newId,
                        name: dName,
                        did: dDid,
                        type: typeName,
                        pins: pins,
                    };
                }

                // If no new device found in devMap, check total device count or SVG
                if (currentIds.length > beforeIds.length) {
                    return { verified: true, instance_id: currentIds[currentIds.length - 1], type: compName, pins: [] };
                }

                // Fallback: check SVG elements on the breadboard canvas for newly added components
                const svgElements = Array.from(document.querySelectorAll('#breadboardTab svg, #breadboardTab [class*="cgfx"]'));
                const prevCount = beforeIds.length;
                if (svgElements.length > 0 && prevCount === 0) {
                    // Components exist on canvas via SVG even if circuit_editor API is unavailable
                    return { verified: true, instance_id: 'svg_fallback_0', type: compName, pins: [], fallback: true };
                }

                // Check via Tinkercad's internal app state as a last resort
                try {
                    const app = window.TC?.app || window.tcApp;
                    if (app) {
                        const devs = app.circuit?.devices || app.editor?.circuit?.devices;
                        if (devs && Object.keys(devs).length > prevCount) {
                            const ids = Object.keys(devs);
                            return { verified: true, instance_id: ids[ids.length - 1], type: compName, pins: [], fallback: true };
                        }
                    }
                } catch(e) {}

                return { verified: false };
            }
        """, {"beforeIds": before_instances, "targetDid": target_did, "compName": comp_def.name if comp_def else search_query})

        if not placed_verification or not placed_verification.get("verified"):
            return {
                "success": False,
                "error": "placement_verification_failed",
                "message": f"Verification failed: component '{search_query}' was not detected on the canvas after placement.",
            }

        # Trigger immediate root save so Tinkercad registers the new component and begins cloud synchronization
        try:
            await page.evaluate("""() => {
                const ce = window.circuit_editor;
                if (ce?.root?.save) {
                    try { ce.root.save(); } catch (e) {}
                }
            }""")
        except Exception:
            pass

        # Settle autosave pipeline
        await page.wait_for_timeout(1500)

        pins_info = placed_verification.get("pins") or ([p.name for p in comp_def.pins] if comp_def else [])
        component_display_name = placed_verification.get("type") or (comp_def.name if comp_def else component_name)

        # Reject mismatch if a completely different component was placed
        if comp_def:
            import re
            norm_exp = re.sub(r"[^a-z0-9]", "", comp_def.name.lower())
            norm_got = re.sub(r"[^a-z0-9]", "", component_display_name.lower())
            if norm_exp not in norm_got and norm_got not in norm_exp:
                keywords = [re.sub(r"[^a-z0-9]", "", kw.lower()) for kw in getattr(comp_def, "search_keywords", [])]
                if not any(kw and kw in norm_got for kw in keywords):
                    return {
                        "success": False,
                        "error": "wrong_component_placed",
                        "expected": comp_def.name,
                        "placed": component_display_name,
                        "message": f"Verification failed: expected '{comp_def.name}' to be placed, but '{component_display_name}' was detected on canvas.",
                    }

        # Validate minimum pin count if requested
        if min_pins and len(pins_info) < min_pins:
            inst_id = placed_verification.get("instance_id")
            if inst_id:
                try:
                    await page.evaluate("""(id) => {
                        const ce = window.circuit_editor;
                        const dev = ce?.data?.devices?._content[id]?.val || ce?.data?.devices?._content[id];
                        if (dev && dev.remove) dev.remove();
                    }""", inst_id)
                except Exception:
                    pass
            return {
                "success": False,
                "error": "insufficient_pins",
                "placed_pins": pins_info,
                "required_min_pins": min_pins,
                "message": f"Verification failed: placed component '{component_display_name}' has only {len(pins_info)} pins ({pins_info}), but at least {min_pins} pins are required.",
            }

        # Validate required named pins if requested
        if required_pins:
            import re
            norm_pins = [re.sub(r"[^a-z0-9]", "", p.lower()) for p in pins_info]
            missing_pins = [
                rp for rp in required_pins
                if not any(re.sub(r"[^a-z0-9]", "", rp.lower()) in np or np in re.sub(r"[^a-z0-9]", "", rp.lower()) for np in norm_pins)
            ]
            if missing_pins:
                inst_id = placed_verification.get("instance_id")
                if inst_id:
                    try:
                        await page.evaluate("""(id) => {
                            const ce = window.circuit_editor;
                            const dev = ce?.data?.devices?._content[id]?.val || ce?.data?.devices?._content[id];
                            if (dev && dev.remove) dev.remove();
                        }""", inst_id)
                    except Exception:
                        pass
                return {
                    "success": False,
                    "error": "missing_required_pins",
                    "placed_pins": pins_info,
                    "missing_pins": missing_pins,
                    "message": f"Verification failed: placed component '{component_display_name}' does not have required pins {missing_pins}. Placed pins: {pins_info}",
                }

        # Persistence verification across page reload if requested
        if verify_persistence:
            inst_id = placed_verification.get("instance_id")
            if inst_id:
                # Do NOT immediately reload! Wait for Tinkercad cloud autosave debounce & network sync to settle
                logger.info("Waiting for Tinkercad cloud autosave to settle before reload verification (4.5s)...")
                await page.wait_for_timeout(4500)
                if hasattr(page, "reload"):
                    try:
                        logger.info("Reloading page to verify component persistence...")
                        await page.reload(wait_until="domcontentloaded")
                        await page.wait_for_timeout(4000)
                        if hasattr(self.browser, "ensure_canvas_interactive"):
                            await self.browser.ensure_canvas_interactive(page)
                        persisted = await page.evaluate("""(id) => {
                            const ce = window.circuit_editor;
                            const devMap = ce?.data?.devices?._content || {};
                            return devMap[id] ? id : null;
                        }""", inst_id)
                        if not persisted:
                            persisted_alt = await page.evaluate("""({did, name}) => {
                                const ce = window.circuit_editor;
                                const devMap = ce?.data?.devices?._content || {};
                                for (const k of Object.keys(devMap)) {
                                    const dev = devMap[k]?.val || devMap[k];
                                    const dDid = dev?.did ? String(dev.did()) : null;
                                    if (did && dDid === String(did)) return k;
                                }
                                return null;
                            }""", {"did": placed_verification.get("did"), "name": component_display_name})
                            if not persisted_alt:
                                return {
                                    "success": False,
                                    "verified": False,
                                    "error": "component_persistence_failed",
                                    "message": f"Component '{component_display_name}' was placed but did not persist after page reload.",
                                }
                            placed_verification["instance_id"] = persisted_alt
                        elif isinstance(persisted, str):
                            placed_verification["instance_id"] = persisted
                    except Exception as e:
                        logger.warning(f"Reload component persistence check encountered error: {e}")

        canonical_instance_id = placed_verification.get("instance_id")
        # Record placed component origin and exclusion radius in tracking store
        inst_id = str(canonical_instance_id or f"inst_{len(self._placed_origins) + 1}")
        self.record_placed_origin(
            instance_id=inst_id,
            name=component_display_name,
            x=target_x,
            y=target_y,
            radius=self.get_component_exclusion_radius(component_display_name),
        )

        # If multiple components exist on canvas, auto-fit view so workspace remains clear and expansive
        if len(self._placed_origins) >= 3:
            try:
                await self.zoom_to_fit(page)
            except Exception:
                pass

        return {
            "success": True,
            "verified": verify_persistence,
            "component": component_display_name,
            "component_id": comp_def.id if comp_def else str(placed_verification.get("did") or "custom"),
            "instance_id": canonical_instance_id,
            "position": {"x": target_x, "y": target_y},
            "available_pins": pins_info,
            "message": f"Successfully placed '{component_display_name}' at ({target_x}, {target_y}).",
        }

    async def remove_component(
        self,
        component_name: Optional[str] = None,
        x: Optional[int] = None,
        y: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Remove/delete a placed component from the canvas."""
        valid, err_msg = self.validate_coordinates(x, y)
        if not valid:
            return {"success": False, "message": err_msg or "Invalid coordinates."}

        page = await self.browser.get_page()

        # If coordinates provided, click on canvas at that point
        if x is not None and y is not None:
            await page.mouse.click(x, y)
            await page.wait_for_timeout(400)
            # Remove from tracked origins if within radius
            import math
            self._placed_origins = [
                o for o in self._placed_origins
                if math.hypot(o.get("x", 0) - x, o.get("y", 0) - y) > max(40, o.get("radius", 60) * 0.8)
            ]
        elif component_name:
            # Safely click component by text on canvas without selector injection
            elem = page.locator(".schematic-canvas text, svg text").filter(has_text=component_name).first
            if await elem.count() > 0:
                await elem.click()
                await page.wait_for_timeout(400)
            cn_clean = component_name.lower().strip()
            self._placed_origins = [
                o for o in self._placed_origins
                if cn_clean not in o.get("name", "").lower() and cn_clean not in str(o.get("instance_id", "")).lower()
            ]

        # Trigger Delete action via toolbar button or keyboard
        deleted = False
        del_btn = await self.browser.find_first_matching(EDITOR_SELECTORS["delete_btn"], timeout=1500, page=page)
        if del_btn:
            try:
                await del_btn.click()
                deleted = True
            except Exception:
                pass

        if not deleted:
            await page.keyboard.press("Delete")
            await page.wait_for_timeout(300)
            await page.keyboard.press("Backspace")
            deleted = True

        return {
            "success": True,
            "message": f"Removed component {component_name or 'at specified location'}.",
        }

    async def set_component_property(
        self,
        property_name: str,
        value: str,
        unit: Optional[str] = None,
        instance_id: Optional[str] = None,
        component_name: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Update property of component in inspector dialog (e.g. resistance value/unit, LED color).

        If component is not currently selected, automatically selects it programmatically.
        """
        page = await self.browser.get_page()
        prop = re.sub(r'[^a-zA-Z0-9_\-]', '', property_name.lower().strip())
        val_clean = str(value).strip()

        target_inst = instance_id or kwargs.get("id") or kwargs.get("component_id")
        target_comp = component_name or kwargs.get("component") or kwargs.get("name")

        inspector = page.locator(".inspector-panel, .component-inspector, .properties-panel, .ui-dialog, .popover").first
        if not await inspector.count():
            # Programmatically select component so inspector opens
            selected = False
            try:
                selected = await page.evaluate("""
                    ({instId, compName}) => {
                        const ce = window.circuit_editor;
                        const devMap = ce?.data?.devices?._content || {};
                        let dev = null;
                        if (instId && devMap[instId]) {
                            dev = devMap[instId]?.val || devMap[instId];
                        } else if (compName) {
                            const q = compName.toLowerCase().replace(/[^a-z0-9]/g, '');
                            for (const [k, entry] of Object.entries(devMap)) {
                                const d = entry.val || entry;
                                const dName = (typeof d.name === 'function' ? String(d.name()) : String(d.name || '')).toLowerCase().replace(/[^a-z0-9]/g, '');
                                const desc = d.getDescription ? d.getDescription() : null;
                                const tName = (desc?.device?.name || desc?.footprint_name || '').toLowerCase().replace(/[^a-z0-9]/g, '');
                                if (dName.includes(q) || tName.includes(q) || q.includes(tName)) {
                                    dev = d;
                                    break;
                                }
                            }
                        }
                        if (!dev) {
                            const keys = Object.keys(devMap);
                            if (keys.length > 0) dev = devMap[keys[keys.length - 1]]?.val || devMap[keys[keys.length - 1]];
                        }
                        if (dev) {
                            if (typeof dev.select === 'function') {
                                try { dev.select(); } catch(e) {}
                            }
                            const bb = dev.breadboard ? dev.breadboard() : null;
                            const el = bb?.node || bb?.el;
                            if (el) {
                                el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                                el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                                el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                                return true;
                            }
                        }
                        return false;
                    }
                """, {"instId": target_inst, "compName": target_comp})
            except Exception:
                pass

            if selected:
                await page.wait_for_timeout(600)
            else:
                # Fallback: click last placed origin if known
                if self._placed_origins:
                    last_orig = self._placed_origins[-1]
                    try:
                        await page.mouse.click(last_orig["x"], last_orig["y"])
                        await page.wait_for_timeout(600)
                    except Exception:
                        pass

        # Check again if inspector is visible
        inspector = page.locator(".inspector-panel, .component-inspector, .properties-panel, .ui-dialog, .popover").first
        if not await inspector.count():
            return {
                "success": False,
                "message": "Inspector popover is not visible. Please select a component on the canvas first.",
            }

        try:
            if "color" in prop:
                # Color dropdown or buttons
                color_select = inspector.locator("select[name*='color'], select").first
                if await color_select.count() > 0:
                    await color_select.select_option(label=val_clean)
                else:
                    color_btn = inspector.locator("button, div[title]").filter(has_text=val_clean).first
                    if await color_btn.count() > 0:
                        await color_btn.click()
            elif "resist" in prop or "value" in prop:
                # Value input
                val_input = inspector.locator("input[type='text'], input[type='number']").first
                if await val_input.count() > 0:
                    await val_input.fill(val_clean)

                # Unit dropdown if provided
                if unit:
                    unit_select = inspector.locator("select").first
                    if await unit_select.count() > 0:
                        await unit_select.select_option(label=unit)
            else:
                # General text input
                inp = inspector.locator("input").first
                if await inp.count() > 0:
                    await inp.fill(val_clean)

            await page.wait_for_timeout(500)
            return {
                "success": True,
                "property": property_name,
                "value": val_clean,
                "unit": unit,
                "message": f"Successfully updated {property_name} to {val_clean} {unit or ''}.",
            }
        except Exception as e:
            return {"success": False, "message": f"Failed setting component property: {e}"}

    async def get_component_instances_info(self) -> Dict[str, Any]:
        """Extract structured component instance metadata: instance IDs, types, names, and available terminal pins."""
        page = await self.browser.get_page()
        try:
            return await page.evaluate(r"""
                () => {
                    const ce = window.circuit_editor;
                    const devMap = ce?.data?.devices?._content || {};
                    const instances = {};

                    for (const [dId, dWrap] of Object.entries(devMap)) {
                        const dev = dWrap.val || dWrap;
                        const dName = typeof dev.name === 'function' ? String(dev.name()) : String(dev.name || '');
                        const dDid = typeof dev.did === 'function' ? String(dev.did()) : String(dev.did || '');
                        const desc = typeof dev.getDescription === 'function' ? dev.getDescription() : null;
                        const compType = desc?.device?.name || desc?.footprint_name || 'Component';
                        const n2t = dev.name2terminal?._content || {};
                        const pins = Object.keys(n2t);

                        instances[String(dId)] = {
                            instance_id: String(dId),
                            type: compType,
                            name: dName,
                            did: dDid,
                            pins: pins,
                        };
                    }
                    return { success: true, count: Object.keys(instances).length, instances: instances };
                }
            """)
        except Exception as e:
            logger.warning(f"Error fetching component instance metadata: {e}")
            return {"success": False, "error": str(e), "instances": {}}

    async def _ensure_components_drawer_open(self, page) -> None:
        """Helper to ensure components drawer is open and unobstructed."""
        await self.browser.ensure_components_drawer_open(page)

    async def _get_canvas_bounds(self, page) -> Dict[str, float]:
        """Get bounding box of the canvas workspace."""
        canvas = await self.browser.find_first_matching(EDITOR_SELECTORS["editor_canvas"], timeout=3000, page=page)
        if canvas:
            box = await canvas.bounding_box()
            if box:
                return box
        return {"x": 50, "y": 100, "width": 1000, "height": 700}

    async def _find_non_overlapping_coordinates(
        self,
        page: Any,
        requested_x: Optional[int],
        requested_y: Optional[int],
        comp_name: str,
    ) -> tuple[int, int]:
        """Determine collision-free placement coordinates avoiding component stacking and hitbox overlaps."""
        import math

        comp_radius = self.get_component_exclusion_radius(comp_name)

        # 1. Fast-path check when coordinates are explicitly requested:
        # Check against tracked placed origins without needing DOM evaluation
        if requested_x is not None and requested_y is not None:
            is_zero_origin = (abs(requested_x - 161) < 25 and abs(requested_y - (-76)) < 25)
            is_negative_or_too_far = (requested_x < 50 or requested_y < 50 or requested_x > 3500 or requested_y > 2500)

            if not is_zero_origin and not is_negative_or_too_far:
                # Check collision with already placed component origins
                colliding_origin = None
                for o in self._placed_origins:
                    ox = o.get("x", 0)
                    oy = o.get("y", 0)
                    o_rad = o.get("radius", 100)
                    safe_dist = (comp_radius + o_rad) * 0.85
                    if math.hypot(requested_x - ox, requested_y - oy) < safe_dist:
                        colliding_origin = o
                        break

                if colliding_origin is None:
                    # No collision with any stored component origin! Safe to place at requested coordinate.
                    return requested_x, requested_y

                logger.warning(
                    f"Requested placement ({requested_x}, {requested_y}) for '{comp_name}' collides with existing component "
                    f"'{colliding_origin.get('name')}' within exclusion radius ({comp_radius}px). Displacing to safe coordinates."
                )
                # Displace: search in expanding spiral rings around requested_x, requested_y
                for step_dist in range(comp_radius + 40, 600, 50):
                    for angle_deg in (0, 90, 180, 270, 45, 135, 225, 315):
                        rad = math.radians(angle_deg)
                        cand_x = int(requested_x + step_dist * math.cos(rad))
                        cand_y = int(requested_y + step_dist * math.sin(rad))
                        if cand_x >= 120 and cand_y >= 120:
                            cand_collides = any(
                                math.hypot(cand_x - o.get("x", 0), cand_y - o.get("y", 0)) < (comp_radius + o.get("radius", 100)) * 0.85
                                for o in self._placed_origins
                            )
                            if not cand_collides:
                                logger.info(f"Relocated '{comp_name}' from colliding ({requested_x}, {requested_y}) to safe ({cand_x}, {cand_y})")
                                return cand_x, cand_y
            else:
                logger.info(
                    f"Requested coordinates ({requested_x}, {requested_y}) for '{comp_name}' are out of bounds or default zero-origin. Auto-routing."
                )

        # 2. Canvas bounds and DOM obstacle inspection for auto-layout
        canvas_box = await self._get_canvas_bounds(page)
        base_x = int(canvas_box.get("x", 50))
        base_y = int(canvas_box.get("y", 100))
        c_width = int(canvas_box.get("width", 1000))
        c_height = int(canvas_box.get("height", 700))

        # Safe boundaries avoiding top header, left toolbar, and right component catalog drawer
        min_x = base_x + 60
        min_y = base_y + 60
        max_grid_x = min(base_x + c_width - 380, base_x + 850)
        max_grid_y = min(base_y + c_height - 80, base_y + 650)

        # Query existing component bounding boxes on screen
        existing_boxes: List[Dict[str, Any]] = []
        try:
            raw_boxes = await page.evaluate("""
                () => {
                    const boxes = [];
                    const svgs = document.querySelectorAll('#breadboardTab svg[class*="cgfx__"]');
                    for (const s of svgs) {
                        const r = s.getBoundingClientRect();
                        if (r.width > 10 && r.height > 10) {
                            boxes.push({
                                x: Math.round(r.left + r.width / 2),
                                y: Math.round(r.top + r.height / 2),
                                left: Math.round(r.left),
                                top: Math.round(r.top),
                                right: Math.round(r.right),
                                bottom: Math.round(r.bottom),
                                width: Math.round(r.width),
                                height: Math.round(r.height)
                            });
                        }
                    }
                    return boxes;
                }
            """)
            if isinstance(raw_boxes, list):
                for item in raw_boxes:
                    if isinstance(item, dict):
                        existing_boxes.append(item)
        except (Exception, BaseException):
            existing_boxes = []

        # Merge live DOM boxes with tracked component origins
        obstacles: List[Dict[str, Any]] = list(existing_boxes)
        for o in self._placed_origins:
            ox = o.get("x", 0)
            oy = o.get("y", 0)
            rad = o.get("radius", 100)
            already_captured = any(math.hypot(b.get("x", 0) - ox, b.get("y", 0) - oy) < 30 for b in existing_boxes)
            if not already_captured:
                obstacles.append({
                    "x": ox,
                    "y": oy,
                    "radius": rad,
                    "left": ox - rad,
                    "right": ox + rad,
                    "top": oy - rad,
                    "bottom": oy + rad,
                    "width": rad * 2,
                    "height": rad * 2,
                    "name": o.get("name", ""),
                })

        def collides(tx: int, ty: int, radius: int) -> bool:
            for b in obstacles:
                if not isinstance(b, dict):
                    continue
                bx = b.get("x", 0)
                by = b.get("y", 0)
                b_rad = b.get("radius") or max(b.get("width", 0), b.get("height", 0)) / 2 or 80
                safe_dist = (radius + b_rad) * 0.85
                if math.hypot(tx - bx, ty - by) < safe_dist:
                    return True
                # Bounding box test with radius margin
                half_r = radius * 0.6
                if (b.get("left", 0) - half_r <= tx <= b.get("right", 0) + half_r and
                        b.get("top", 0) - half_r <= ty <= b.get("bottom", 0) + half_r):
                    return True
            return False

        # Auto-layout slot generation based on component type
        norm_c = comp_name.lower().strip()
        is_mcu = any(k in norm_c for k in ("arduino", "micro:bit", "controller", "uno"))
        is_bb = "breadboard" in norm_c
        is_sensor = any(k in norm_c for k in ("ultrasonic", "distance", "pir", "tmp36", "sensor", "sonar", "hcsr04", "photo"))
        is_actuator = any(k in norm_c for k in ("servo", "motor", "piezo", "buzzer", "speaker", "led", "display", "lcd"))

        candidate_slots: List[tuple[int, int]] = []
        if is_mcu:
            candidate_slots.extend([
                (base_x + 240, base_y + 260),
                (base_x + 240, base_y + 440),
                (base_x + 440, base_y + 260),
            ])
        elif is_bb:
            candidate_slots.extend([
                (base_x + 240, base_y + 530),
                (base_x + 480, base_y + 530),
                (base_x + 240, base_y + 360),
            ])
        elif is_sensor:
            candidate_slots.extend([
                (base_x + 580, base_y + 180),
                (base_x + 760, base_y + 180),
                (base_x + 580, base_y + 320),
                (base_x + 760, base_y + 320),
            ])
        elif is_actuator:
            candidate_slots.extend([
                (base_x + 580, base_y + 420),
                (base_x + 760, base_y + 420),
                (base_x + 580, base_y + 560),
                (base_x + 760, base_y + 560),
                (base_x + 440, base_y + 420),
            ])

        # Fill with general grid slots (avoiding right drawer: max X ~ base_x + c_width - 380)
        for col_x in range(base_x + 200, max_grid_x, 180):
            for row_y in range(base_y + 160, max_grid_y, 140):
                candidate_slots.append((col_x, row_y))

        for cand_x, cand_y in candidate_slots:
            if not collides(cand_x, cand_y, radius=comp_radius):
                return cand_x, cand_y

        for cand_x, cand_y in candidate_slots:
            if not collides(cand_x, cand_y, radius=int(comp_radius * 0.7)):
                return cand_x, cand_y

        # Fallback with placed_count offset if canvas is dense
        self._placed_count += 1
        fb_x = base_x + 220 + ((self._placed_count * 160) % max(300, max_grid_x - base_x - 100))
        fb_y = base_y + 180 + (((self._placed_count * 130) // 400) % max(200, max_grid_y - base_y - 80))
        return int(fb_x), int(fb_y)

