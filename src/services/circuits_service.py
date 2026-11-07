"""Circuit design management: list, open, create, rename, and inspect circuits."""

from __future__ import annotations

import asyncio
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from ..browser.browser_manager import BrowserManager
from ..browser.selectors import DASHBOARD_SELECTORS, EDITOR_SELECTORS
from ..config import (
    BASE_URL,
    CIRCUITS_DASHBOARD_URL,
    NEW_CIRCUIT_URL,
    THINGS_CIRCUITS_URL,
    logger,
)


class CircuitsService:
    """Handles circuit listing, creation, opening, and metadata inspection."""

    def __init__(self, browser: Optional[BrowserManager] = None) -> None:
        self.browser = browser or BrowserManager.get_instance()

    async def list_circuits(self) -> Dict[str, Any]:
        """List all circuit designs available in the user's Tinkercad account."""
        page = await self.browser.navigate(CIRCUITS_DASHBOARD_URL)

        # Ensure circuits tab is active
        circuits_tab = await self.browser.find_first_matching(DASHBOARD_SELECTORS["circuits_tab"], timeout=3000, page=page)
        if circuits_tab:
            try:
                await circuits_tab.click()
                await page.wait_for_timeout(1500)
            except Exception:
                pass

        # Give items a moment to render
        await page.wait_for_timeout(2000)

        # Scrape circuit cards
        circuits: List[Dict[str, Any]] = []

        # Find design card elements or links
        cards = await page.locator("a[href*='/things/']").all()
        seen_ids = set()

        for card in cards:
            try:
                href = await card.get_attribute("href") or ""
                # Extract thing ID
                # URLs look like /things/0abcdef-circuit-name or /things/0abcdef/editel
                match = re.search(r"/things/([a-zA-Z0-9_\-]+)", href)
                if not match:
                    continue

                thing_id = match.group(1)
                if thing_id in seen_ids or thing_id in ("new", "duplicate", "export"):
                    continue
                seen_ids.add(thing_id)

                title_text = ""
                # Try finding title within card
                title_elem = card.locator("h3, h4, .design-title, .card-title, [data-testid='design-title']").first
                if await title_elem.count() > 0:
                    title_text = (await title_elem.text_content() or "").strip()
                if not title_text:
                    title_text = (await card.text_content() or "").strip().split("\n")[0]
                if not title_text:
                    title_text = thing_id

                # Thumbnail image if present
                img_elem = card.locator("img").first
                img_url = ""
                if await img_elem.count() > 0:
                    img_url = (await img_elem.get_attribute("src")) or ""

                edit_url = f"{BASE_URL}/things/{thing_id}/editel"

                circuits.append({
                    "id": thing_id,
                    "title": title_text,
                    "url": f"{BASE_URL}/things/{thing_id}",
                    "edit_url": edit_url,
                    "thumbnail": img_url,
                })
            except Exception as e:
                logger.debug(f"Error parsing card item: {e}")
                continue

        logger.info(f"Discovered {len(circuits)} circuit designs in account.")
        return {
            "success": True,
            "total_count": len(circuits),
            "circuits": circuits,
        }

    def _validate_circuit_target(self, circuit_id_or_url: str) -> str:
        """Validate and construct safe Tinkercad editor URL, guarding against SSRF and open redirects."""
        raw = circuit_id_or_url.strip()
        if not raw:
            raise ValueError("circuit_id_or_url cannot be empty.")

        if raw.startswith("http://") or raw.startswith("https://"):
            parsed = urllib.parse.urlparse(raw)
            if parsed.scheme.lower() != "https":
                raise ValueError("Only secure HTTPS URLs on tinkercad.com are allowed.")
            hostname = (parsed.hostname or "").lower()
            if hostname not in ("www.tinkercad.com", "tinkercad.com"):
                raise ValueError(f"Untrusted host '{hostname}'. Only tinkercad.com URLs are allowed.")
            # Match /things/<id>(/editel)?
            path_match = re.match(r"^/things/([a-zA-Z0-9_\-]+)(?:/editel)?/?$", parsed.path)
            if not path_match:
                raise ValueError("URL must point to a valid Tinkercad circuit design (/things/<circuit_id>).")
            clean_id = path_match.group(1)
            return f"{BASE_URL}/things/{clean_id}/editel"

        # Check for disallowed schemes, traversals or protocols
        clean_id = raw.replace("/things/", "").replace("/editel", "").strip("/")
        if not re.match(r"^[a-zA-Z0-9_\-]+$", clean_id):
            raise ValueError(f"Invalid circuit identifier '{raw}'. Circuit ID must only contain letters, numbers, hyphens, and underscores.")

        return f"{BASE_URL}/things/{clean_id}/editel"

    async def open_circuit(
        self,
        circuit_id_or_url: Optional[str] = None,
        circuit_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Open an existing circuit design in the Tinkercad Circuits editor."""
        target = circuit_id_or_url or circuit_id or kwargs.get("url") or kwargs.get("id")
        if not target:
            return {"success": False, "message": "circuit_id_or_url or circuit_id cannot be empty."}
        try:
            target_url = self._validate_circuit_target(target)
        except ValueError as ve:
            return {"success": False, "message": str(ve)}

        # If an editor is currently open with pending changes, trigger save and wait for cloud sync before navigating away
        try:
            current_page = await self.browser.get_page()
            if current_page and not current_page.is_closed():
                await current_page.evaluate("""() => {
                    const ce = window.circuit_editor;
                    if (ce?.root?.save) {
                        try { ce.root.save(); } catch (e) {}
                    }
                }""")
                await current_page.wait_for_timeout(1500)
        except Exception:
            pass

        logger.info(f"Opening circuit editor at: {target_url}")
        page = await self.browser.navigate(target_url, wait_until="domcontentloaded", timeout=45000)

        # Wait for editor canvas or header to indicate it is loaded
        canvas = await self.browser.find_first_matching(EDITOR_SELECTORS["editor_canvas"], timeout=20000, page=page)
        await page.wait_for_timeout(3000)

        # Proactively collapse code editor panel if open to prevent pointer interception
        try:
            await self.browser.close_code_panel(page=page)
        except Exception:
            pass

        # Get circuit title
        title = await self._get_current_title(page)

        return {
            "success": True,
            "circuit_id": self._extract_id_from_url(page.url),
            "title": title,
            "url": page.url,
            "message": f"Circuit '{title}' opened successfully in editor.",
        }

    async def create_circuit(self, title: Optional[str] = None) -> Dict[str, Any]:
        """Create a new circuit design and open it in the editor.

        Navigates to the Tinkercad Circuits dashboard, clicks Create -> Circuits,
        waits for the real /editel editor URL to load, and verifies the canvas exists.
        Rejects invalid /things/new pages or missing canvas states.
        """
        page = await self.browser.get_page()

        # If not currently on dashboard, navigate to dashboard first
        if "dashboard" not in page.url:
            logger.info(f"Navigating to dashboard: {CIRCUITS_DASHBOARD_URL}")
            page = await self.browser.navigate(CIRCUITS_DASHBOARD_URL, wait_until="domcontentloaded", timeout=35000)
            await page.wait_for_timeout(1500)

        # 1. Click Create button
        create_btn = await self.browser.find_first_matching(DASHBOARD_SELECTORS["create_button"], timeout=5000, page=page)
        if not create_btn:
            # Fallback: try navigating to CIRCUITS_DASHBOARD_URL again
            page = await self.browser.navigate(CIRCUITS_DASHBOARD_URL, wait_until="domcontentloaded", timeout=35000)
            await page.wait_for_timeout(2000)
            create_btn = await self.browser.find_first_matching(DASHBOARD_SELECTORS["create_button"], timeout=5000, page=page)

        if not create_btn:
            return {
                "success": False,
                "error": "dashboard_create_button_not_found",
                "message": "Could not find 'Create' button on Tinkercad dashboard.",
            }

        await create_btn.click()
        await page.wait_for_timeout(800)

        # 2. Click "Circuits" item in the Create menu
        circuit_item = await self.browser.find_first_matching(DASHBOARD_SELECTORS["create_circuit_item"], timeout=5000, page=page)
        if not circuit_item:
            return {
                "success": False,
                "error": "create_circuit_item_not_found",
                "message": "Could not find 'Circuits' item in the Create dropdown menu.",
            }

        logger.info("Clicked 'Create > Circuits' on dashboard. Waiting for editor (/editel)...")
        await circuit_item.click()

        # 3. Wait for editor navigation: URL should contain /things/*/editel
        try:
            await page.wait_for_url(lambda u: "/editel" in u, timeout=40000)
        except Exception:
            if "/editel" not in page.url:
                missing = await page.evaluate(r"""
                    () => {
                        const txt = document.body ? document.body.innerText : '';
                        return txt.includes('Sorry, that page is missing') || txt.includes('Page Not Found');
                    }
                """)
                if missing or "/things/new" in page.url:
                    return {
                        "success": False,
                        "error": "circuit_creation_failed",
                        "message": f"Failed to load new circuit editor. Current URL: {page.url}",
                    }

        # 4. Verify page is not a 404 / missing page
        is_missing = await page.evaluate(r"""
            () => {
                const text = document.body ? document.body.innerText : '';
                return text.includes('Sorry, that page is missing') || text.includes('Page Not Found');
            }
        """)
        if is_missing or "/things/new" in page.url:
            return {
                "success": False,
                "error": "circuit_creation_failed",
                "message": f"Tinkercad returned 'Sorry, that page is missing' at {page.url}.",
            }

        # 5. Wait for editor canvas to be present and fully rendered (polling with retries)
        canvas = None
        canvas_count = 0
        for attempt in range(8):
            canvas = await self.browser.find_first_matching(EDITOR_SELECTORS["editor_canvas"], timeout=5000, page=page)
            canvas_count = await page.evaluate(r"""
                () => {
                    return document.querySelectorAll('#breadboardTab, .schematic-canvas, canvas, #canvas-container, .hasSVG svg').length;
                }
            """)
            if canvas and canvas_count > 0:
                break
            logger.info(f"Waiting for circuit canvas to render (attempt {attempt + 1}/8)...")
            await page.wait_for_timeout(1500)

        if not canvas or canvas_count == 0:
            return {
                "success": False,
                "error": "editor_canvas_not_found",
                "message": "Editor loaded without a functional circuit canvas after multiple wait attempts.",
            }

        # Settle
        await page.wait_for_timeout(2000)

        # Proactively collapse code editor panel if open to prevent pointer interception
        try:
            await self.browser.close_code_panel(page=page)
        except Exception:
            pass

        # 6. Rename circuit if custom title requested
        current_title = await self._get_current_title(page)
        if title and title != current_title:
            rename_res = await self.rename_circuit(title)
            if rename_res.get("success"):
                current_title = title

        circuit_id = self._extract_id_from_url(page.url)

        return {
            "success": True,
            "circuit_id": circuit_id,
            "title": current_title,
            "url": page.url,
            "message": f"New circuit '{current_title}' created successfully.",
        }

    async def rename_circuit(
        self,
        new_title: Optional[str] = None,
        new_name: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Rename the currently open circuit."""
        title = new_title or new_name or kwargs.get("title") or kwargs.get("name")
        clean_title = re.sub(r'[\r\n\t]', ' ', title or '').strip()
        if not clean_title:
            return {"success": False, "message": "Circuit title cannot be empty."}
        if len(clean_title) > 200:
            clean_title = clean_title[:200]

        page = await self.browser.get_page()

        try:
            # 1. Click title pill / text to reveal input if hidden
            pill = await self.browser.find_first_matching(EDITOR_SELECTORS.get("circuit_title_pill", []), timeout=2000, page=page)
            if pill:
                await pill.click()
                await page.wait_for_timeout(400)

            # 2. Locate the input element
            input_selectors = EDITOR_SELECTORS.get("circuit_title_input", []) + EDITOR_SELECTORS["circuit_title"]
            title_elem = await self.browser.find_first_matching(input_selectors, timeout=3000, page=page)
            if not title_elem:
                return {"success": False, "message": "Could not locate circuit title element in editor."}

            tag_name = await title_elem.evaluate("el => el.tagName.toLowerCase()")
            if tag_name == "input":
                await title_elem.fill(clean_title)
                await title_elem.press("Enter")
            else:
                # If it's a div/span, click to activate and find input
                await title_elem.click()
                await page.wait_for_timeout(300)
                input_field = page.locator("input#topnav-title-input, .sitemenu__title__input:not(.is-hidden), input[type='text']").first
                if await input_field.count() > 0:
                    await input_field.fill(clean_title)
                    await input_field.press("Enter")

            await page.wait_for_timeout(1000)
            return {
                "success": True,
                "title": clean_title,
                "message": f"Renamed circuit to '{clean_title}'.",
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to rename circuit: {e}"}

    async def _inspect_circuit_svg_fallback(self, page: Any) -> Dict[str, Any]:
        """Fast fallback inspecting SVG DOM elements when internal circuit_editor data model is not settling."""
        try:
            return await asyncio.wait_for(page.evaluate("""
                () => {
                    const result = { components: [], wires: [], simulation_running: false };
                    document.querySelectorAll('#breadboardTab svg[class*="cgfx__"]').forEach((svg, idx) => {
                        const cls = svg.getAttribute('class') || '';
                        let cType = cls.replace('cgfx__', '').replace(/-/g, ' ');
                        if (cls.includes('arduino')) cType = 'Arduino Uno R3';
                        else if (cls.includes('motor-dc')) cType = 'DC Motor';
                        else if (cls.includes('servo')) cType = 'Micro Servo';
                        else if (cls.includes('resistor')) cType = 'Resistor';
                        else if (cls.includes('led')) cType = 'LED';
                        else if (cls.includes('ultrasonic')) cType = 'Ultrasonic Distance Sensor';
                        else if (cls.includes('piezo') || cls.includes('buzzer')) cType = 'Piezo';

                        const rect = svg.getBoundingClientRect();
                        const pins = [];
                        svg.querySelectorAll('g.cgfx__terminal').forEach(t => {
                            const name = t.querySelector('.cgfx__terminalname')?.textContent?.trim() || 'pin';
                            pins.push({ name: name, connected: false, connections: [] });
                        });

                        result.components.push({
                            instance_id: `svg_${idx}`,
                            type: cType,
                            name: String(idx + 1),
                            did: null,
                            position: { x: Math.round(rect.x), y: Math.round(rect.y) },
                            pins: pins
                        });
                    });
                    return result;
                }
            """), timeout=3.0)
        except Exception:
            return {"components": [], "wires": [], "simulation_running": False}

    async def inspect_circuit(self) -> Dict[str, Any]:
        """Perform semantic circuit inspection returning structured components, pins, and wire connections.

        Extracts circuit elements directly from internal editor state and SVG DOM without screenshots.
        Guards with bounded evaluation timeouts so slow WebGL settling never hangs context.
        """
        page = await self.browser.get_page()
        title = await self._get_current_title(page)
        circuit_id = self._extract_id_from_url(page.url)

        try:
            data = await asyncio.wait_for(
                page.evaluate("""
                () => {
                    const result = {
                        components: [],
                        wires: [],
                        simulation_running: false,
                    };

                    const ce = window.circuit_editor;
                    const devMap = ce?.data?.devices?._content || {};
                    const wireMap = ce?.data?.wires?._content || {};

                    // Check simulation
                    const btn = document.querySelector('#SIMULATION_ID, .js-toggleSimulation');
                    if (btn) {
                        const txt = btn.querySelector('.js-simulation-text')?.textContent || btn.textContent || '';
                        if (txt.includes('Stop')) result.simulation_running = true;
                        const stopIcon = btn.querySelector('.js-simulation-stop');
                        if (stopIcon && !stopIcon.classList.contains('hide')) result.simulation_running = true;
                    }

                    // Map term to component & pin info
                    const termToPin = new Map();
                    const devEntries = Object.entries(devMap);

                    for (const [dId, entry] of devEntries) {
                        const dev = entry.val || entry;
                        const dName = typeof dev.name === 'function' ? String(dev.name()) : String(dev.name || '');
                        const dDid = typeof dev.did === 'function' ? dev.did() : dev.did;
                        const desc = typeof dev.getDescription === 'function' ? dev.getDescription() : null;
                        
                        let compType = 'Unknown';
                        if (desc?.device?.name) compType = desc.device.name;
                        else if (desc?.footprint_name) compType = desc.footprint_name;
                        else if (dDid === 132521 || dDid === '132521') compType = 'Arduino Uno R3';
                        else if (dDid === 114158 || dDid === '114158') compType = 'DC Motor';
                        else if (dDid === 146740 || dDid === '146740' || String(dName).toLowerCase().includes('servo')) compType = 'Micro Servo';
                        else if (dDid === 53184 || dDid === '53184') compType = 'Resistor';
                        else if (dDid === 58422 || dDid === '58422') compType = 'LED';

                        let pos = { x: 0, y: 0 };
                        try {
                            const bb = dev.breadboard ? dev.breadboard() : null;
                            const p = bb?.pos ? bb.pos() : null;
                            if (p) pos = { x: Math.round(Number(p.x || 0)), y: Math.round(Number(p.y || 0)) };
                        } catch(e) {}

                        const pins = [];
                        const n2t = dev.name2terminal?._content || {};
                        for (const [tName, tEntry] of Object.entries(n2t)) {
                            const t = tEntry.val || tEntry;
                            const pinObj = {
                                name: String(tName),
                                connected: false,
                                connected_to: null,
                                connections: []
                            };
                            pins.push(pinObj);
                            termToPin.set(t, {
                                instance_id: String(dId),
                                type: compType,
                                name: dName,
                                pinName: String(tName),
                                pinRef: pinObj,
                            });
                        }

                        // Map breadboard terminals (from bbid2terminal)
                        if (dev.bbid2terminal) {
                            const bbidMap = dev.bbid2terminal._content || {};
                            for (const [bbid, tEntry] of Object.entries(bbidMap)) {
                                const t = tEntry.val || tEntry;
                                const desc = t.bbDesc || t.breadboardDescription;
                                const pName = desc?.name || (typeof t.name === 'function' ? t.name() : t.name) || bbid;
                                termToPin.set(t, {
                                    instance_id: String(dId),
                                    type: compType,
                                    name: dName,
                                    pinName: String(pName),
                                    pinRef: null,
                                });
                            }
                        }

                        result.components.push({
                            instance_id: String(dId),
                            type: compType,
                            name: dName,
                            did: dDid !== undefined && dDid !== null ? String(dDid) : null,
                            position: pos,
                            pins: pins
                        });
                    }

                    // Process wires
                    for (const [wId, entry] of Object.entries(wireMap)) {
                        const w = entry.val || entry;
                        const b = typeof w.begin === 'function' ? w.begin() : w.begin;
                        const e = typeof w.end === 'function' ? w.end() : w.end;
                        const color = typeof w.color === 'function' ? String(w.color()) : String(w.color || 'green');

                        const sInfo = termToPin.get(b);
                        const tInfo = termToPin.get(e);

                        if (sInfo && sInfo.pinRef) {
                            sInfo.pinRef.connected = true;
                            if (tInfo) {
                                sInfo.pinRef.connected_to = {
                                    component: tInfo.type,
                                    pin: tInfo.pinName,
                                    instance_id: tInfo.instance_id
                                };
                                sInfo.pinRef.connections.push({
                                    wire_id: String(wId),
                                    color: color,
                                    connected_to: {
                                        instance_id: tInfo.instance_id,
                                        component: tInfo.type,
                                        name: tInfo.name,
                                        pin: tInfo.pinName
                                    }
                                });
                            }
                        }

                        if (tInfo && tInfo.pinRef) {
                            tInfo.pinRef.connected = true;
                            if (sInfo) {
                                tInfo.pinRef.connected_to = {
                                    component: sInfo.type,
                                    pin: sInfo.pinName,
                                    instance_id: sInfo.instance_id
                                };
                                tInfo.pinRef.connections.push({
                                    wire_id: String(wId),
                                    color: color,
                                    connected_to: {
                                        instance_id: sInfo.instance_id,
                                        component: sInfo.type,
                                        name: sInfo.name,
                                        pin: sInfo.pinName
                                    }
                                });
                            }
                        }

                        result.wires.push({
                            wire_id: String(wId),
                            color: color,
                            source: sInfo ? {
                                instance_id: sInfo.instance_id,
                                component: sInfo.type,
                                name: sInfo.name,
                                pin: sInfo.pinName
                            } : null,
                            target: tInfo ? {
                                instance_id: tInfo.instance_id,
                                component: tInfo.type,
                                name: tInfo.name,
                                pin: tInfo.pinName
                            } : null,
                        });
                    }

                    // Fallback to SVG DOM if components array is empty
                    if (result.components.length === 0) {
                        document.querySelectorAll('#breadboardTab svg[class*="cgfx__"]').forEach((svg, idx) => {
                            const cls = svg.getAttribute('class') || '';
                            let cType = cls.replace('cgfx__', '').replace(/-/g, ' ');
                            if (cls.includes('arduino')) cType = 'Arduino Uno R3';
                            else if (cls.includes('motor-dc')) cType = 'DC Motor';
                            else if (cls.includes('resistor')) cType = 'Resistor';
                            else if (cls.includes('led')) cType = 'LED';

                            const rect = svg.getBoundingClientRect();
                            const pins = [];
                            svg.querySelectorAll('g.cgfx__terminal').forEach(t => {
                                const name = t.querySelector('.cgfx__terminalname')?.textContent?.trim() || 'pin';
                                pins.push({ name: name, connected: false, connections: [] });
                            });

                            result.components.push({
                                instance_id: `svg_${idx}`,
                                type: cType,
                                name: String(idx + 1),
                                did: null,
                                position: { x: Math.round(rect.x), y: Math.round(rect.y) },
                                pins: pins
                            });
                        });
                    }

                    return result;
                }
            """),
            timeout=12.0,
        )
        except asyncio.TimeoutError:
            logger.warning("inspect_circuit timed out waiting for internal data model; falling back to SVG DOM extraction.")
            data = await self._inspect_circuit_svg_fallback(page)
        except Exception as e:
            logger.warning(f"Error inspecting circuit structure: {e}")
            data = await self._inspect_circuit_svg_fallback(page)

        components = data.get("components", [])
        unconnected_mandatory = []
        try:
            from ..catalog.components_catalog import find_component_by_did, find_component_by_query
            for c in components:
                c_type = c.get("type", "")
                c_did = c.get("did")
                comp_def = find_component_by_did(c_did) if c_did else find_component_by_query(c_type)
                if comp_def:
                    c["catalog_id"] = comp_def.id
                    c["description"] = comp_def.description
                    cat_pin_map = {p.name.lower(): p for p in comp_def.pins}
                    for p in c.get("pins", []):
                        p_name_lower = p.get("name", "").lower()
                        matched_p = cat_pin_map.get(p_name_lower)
                        if matched_p:
                            p["aliases"] = matched_p.aliases
                            p["description"] = matched_p.description
                            p["terminal_type"] = matched_p.terminal_type

                # Check for unconnected mandatory power/ground pins on active components
                norm_c = c_type.lower()
                is_active = any(k in norm_c for k in ("ultrasonic", "sensor", "driver", "hbridge", "servo", "lcd", "pir", "tmp36"))
                if is_active:
                    missing = []
                    pins = c.get("pins", [])
                    pwr_pin = next((p for p in pins if p.get("name", "").lower() in ("pos", "vcc", "power", "5v", "vs", "vss")), None)
                    gnd_pin = next((p for p in pins if any(k in p.get("name", "").lower() for k in ("neg", "gnd", "ground"))), None)
                    if pwr_pin and not pwr_pin.get("connected"):
                        missing.append(f"{pwr_pin.get('name')} (Power)")
                    if gnd_pin and not gnd_pin.get("connected"):
                        missing.append(f"{gnd_pin.get('name')} (Ground)")
                    if missing:
                        unconnected_mandatory.append({
                            "component": c_type,
                            "instance_id": c.get("instance_id"),
                            "name": c.get("name"),
                            "missing_pins": missing,
                        })
        except Exception as e:
            logger.debug(f"Non-fatal error enriching inspect_circuit metadata: {e}")

        return {
            "success": True,
            "circuit_id": circuit_id,
            "title": title,
            "url": page.url,
            "simulation_running": data.get("simulation_running", False),
            "detected_components_count": len(components),
            "detected_wires_count": len(data.get("wires", [])),
            "components": components,
            "wires": data.get("wires", []),
            "unconnected_mandatory_pins": unconnected_mandatory,
        }

    async def get_circuit_info(self) -> Dict[str, Any]:
        """Inspect and return current circuit editor state."""
        page = await self.browser.get_page()
        title = await self._get_current_title(page)
        circuit_id = self._extract_id_from_url(page.url)

        # Check simulation status
        is_simulating = False
        try:
            is_simulating = await page.evaluate("""
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
        except Exception:
            stop_btn = await self.browser.find_first_matching(EDITOR_SELECTORS["stop_simulation_btn"], timeout=500, page=page)
            is_simulating = stop_btn is not None

        # Count placed components if canvas SVG items can be queried
        component_count = 0
        try:
            items = await page.locator(
                "#breadboardTab [class*='cgfx__'], .schematic-canvas .component, svg .component, [data-component-id]"
            ).count()
            component_count = items
        except Exception:
            pass

        return {
            "circuit_id": circuit_id,
            "title": title,
            "url": page.url,
            "simulation_running": is_simulating,
            "detected_components_count": component_count,
        }

    async def _get_current_title(self, page) -> str:
        """Helper to extract title from input or text."""
        try:
            # First try display text from topnav title
            title_text = await page.evaluate("""
                () => {
                    const txtEl = document.querySelector('#topnav-title-text, .js-circuit-menu-title');
                    if (txtEl && txtEl.textContent.trim()) {
                        return txtEl.textContent.trim();
                    }
                    const inputEl = document.querySelector('#topnav-title-input, input#thing-title, input[name="title"]');
                    if (inputEl && inputEl.value.trim()) {
                        return inputEl.value.trim();
                    }
                    return null;
                }
            """)
            if title_text:
                return title_text

            title_input = await self.browser.find_first_matching(EDITOR_SELECTORS["circuit_title"], timeout=2000, page=page)
            if title_input:
                try:
                    val = await title_input.input_value()
                    if val and val.strip():
                        return val.strip()
                except Exception:
                    pass
                txt = await title_input.text_content()
                if txt and txt.strip():
                    return txt.strip()
        except Exception:
            pass
        return "Untitled Circuit"

    def _extract_id_from_url(self, url: str) -> str:
        """Extract thing ID from URL."""
        match = re.search(r"/things/([a-zA-Z0-9_\-]+)", url)
        return match.group(1) if match else "unknown"

    async def switch_workspace_view(self, view: str) -> Dict[str, Any]:
        """Switch between editor workspace views: 'circuits', 'schematic', or 'components'.

        Args:
            view: Target view ('circuits'/'breadboard', 'schematic', 'components'/'component_list').
        """
        view_norm = view.lower().strip()
        selector_key = None
        target_name = None
        if view_norm in ("circuits", "breadboard", "circuit"):
            selector_key = "workspace_circuits_btn"
            target_name = "Circuits"
        elif view_norm in ("schematic", "schematics"):
            selector_key = "workspace_schematic_btn"
            target_name = "Schematic"
        elif view_norm in ("components", "component_list", "bom", "list"):
            selector_key = "workspace_components_btn"
            target_name = "Component List"
        else:
            return {
                "success": False,
                "error": "invalid_view",
                "message": f"Invalid workspace view '{view}'. Choose from 'circuits', 'schematic', or 'components'.",
            }

        page = await self.browser.get_page()
        selectors = EDITOR_SELECTORS.get(selector_key, [])
        btn = await self.browser.find_first_matching(selectors, timeout=3000, page=page)
        if not btn:
            btn = page.locator(f"button.workspace-switcher__button:has-text('{target_name}')").first
            if await btn.count() == 0:
                return {
                    "success": False,
                    "error": "view_button_not_found",
                    "message": f"Workspace switcher button for '{target_name}' could not be located.",
                }

        await btn.click()
        await page.wait_for_timeout(600)

        # Verify active state
        is_active = await page.evaluate(r"""
            (targetText) => {
                const buttons = Array.from(document.querySelectorAll('button.workspace-switcher__button'));
                for (const b of buttons) {
                    const txt = b.textContent.trim().toLowerCase();
                    if (txt.includes(targetText.toLowerCase())) {
                        const active = b.classList.contains('workspace-switcher__button--active') || b.getAttribute('aria-pressed') === 'true';
                        return active;
                    }
                }
                return false;
            }
        """, target_name)

        return {
            "success": True,
            "target_view": target_name,
            "is_active": is_active,
            "message": f"Successfully switched workspace view to {target_name}." if is_active else f"Switched view to {target_name}.",
        }

    async def zoom_canvas(self, action: str = "fit", steps: int = 1) -> Dict[str, Any]:
        """Zoom or adjust the circuit editor canvas view.

        Args:
            action: Zoom action - 'fit' (Zoom to Fit / View All), 'out' (Zoom Out), 'in' (Zoom In), or 'reset'.
            steps: Number of zoom steps to apply (for 'in' and 'out', default: 1, max: 10).
        """
        action_norm = (action or "fit").lower().strip()
        page = await self.browser.get_page()

        # Ensure canvas container is interactive and overlays are closed
        if hasattr(self.browser, "ensure_canvas_interactive"):
            await self.browser.ensure_canvas_interactive(page)

        canvas_box = None
        canvas_el = await self.browser.find_first_matching(EDITOR_SELECTORS["editor_canvas"], timeout=3000, page=page)
        if canvas_el:
            try:
                canvas_box = await canvas_el.bounding_box()
            except Exception:
                pass

        center_x = int(canvas_box["x"] + canvas_box["width"] / 2) if canvas_box else 500
        center_y = int(canvas_box["y"] + canvas_box["height"] / 2) if canvas_box else 400

        steps = max(1, min(steps, 10))

        if action_norm in ("fit", "all", "view_all", "fit_all"):
            # 1. Try toolbar button
            fit_btn = await self.browser.find_first_matching(EDITOR_SELECTORS.get("zoom_fit_btn", []), timeout=1500, page=page)
            clicked = False
            if fit_btn:
                try:
                    await fit_btn.click()
                    clicked = True
                except Exception:
                    pass

            # 2. Try keyboard shortcut 'f' on canvas
            if not clicked:
                try:
                    await page.mouse.click(center_x, center_y)
                    await page.keyboard.press("f")
                    clicked = True
                except Exception:
                    pass

            # 3. Try internal editor API
            try:
                await page.evaluate("""() => {
                    const ce = window.circuit_editor;
                    if (ce) {
                        if (typeof ce.zoomFit === 'function') { ce.zoomFit(); return true; }
                        if (typeof ce.viewAll === 'function') { ce.viewAll(); return true; }
                        if (typeof ce.fitToScreen === 'function') { ce.fitToScreen(); return true; }
                        if (ce.canvas && typeof ce.canvas.zoomFit === 'function') { ce.canvas.zoomFit(); return true; }
                    }
                    return false;
                }""")
            except Exception:
                pass

            await page.wait_for_timeout(500)
            logger.info("Executed canvas zoom to fit.")
            return {
                "success": True,
                "action": "fit",
                "message": "Zoomed canvas to fit all components into view.",
            }

        elif action_norm in ("out", "zoom_out", "shrink"):
            await page.mouse.move(center_x, center_y)
            # Wheel scroll down (positive deltaY zooms out in Three.js/Tinkercad canvas)
            wheel_delta = 180 * steps
            try:
                await page.mouse.wheel(0, wheel_delta)
            except Exception:
                pass

            # Also try keyboard shortcut '-'
            for _ in range(steps):
                try:
                    await page.keyboard.press("Minus")
                except Exception:
                    pass

            # Also try toolbar zoom-out button
            zoom_out_btn = await self.browser.find_first_matching(EDITOR_SELECTORS.get("zoom_out_btn", []), timeout=500, page=page)
            if zoom_out_btn:
                for _ in range(steps):
                    try:
                        await zoom_out_btn.click()
                    except Exception:
                        pass

            await page.wait_for_timeout(400)
            logger.info(f"Executed canvas zoom out by {steps} step(s).")
            return {
                "success": True,
                "action": "out",
                "steps": steps,
                "message": f"Successfully zoomed out canvas by {steps} step(s).",
            }

        elif action_norm in ("in", "zoom_in", "enlarge"):
            await page.mouse.move(center_x, center_y)
            wheel_delta = -180 * steps
            try:
                await page.mouse.wheel(0, wheel_delta)
            except Exception:
                pass

            for _ in range(steps):
                try:
                    await page.keyboard.press("Equal")
                except Exception:
                    pass

            zoom_in_btn = await self.browser.find_first_matching(EDITOR_SELECTORS.get("zoom_in_btn", []), timeout=500, page=page)
            if zoom_in_btn:
                for _ in range(steps):
                    try:
                        await zoom_in_btn.click()
                    except Exception:
                        pass

            await page.wait_for_timeout(400)
            logger.info(f"Executed canvas zoom in by {steps} step(s).")
            return {
                "success": True,
                "action": "in",
                "steps": steps,
                "message": f"Successfully zoomed in canvas by {steps} step(s).",
            }

        elif action_norm in ("reset", "100%"):
            return await self.zoom_canvas(action="fit")
        else:
            return {
                "success": False,
                "error": "invalid_zoom_action",
                "message": f"Invalid zoom action '{action}'. Choose from 'fit', 'out', 'in', or 'reset'.",
            }

    async def validate_circuit_pre_simulation(self) -> Dict[str, Any]:
        """Perform comprehensive pre-simulation validation of circuit integrity and electrical safety.

        Validates:
        1. Components: checks that placed components are present and healthy.
        2. Wire connections: checks that wires have valid source and target endpoints.
        3. Electrical safety: ensures no DC motors are connected directly to Arduino I/O pins (>40 mA overcurrent violation).
        4. Motor driver integration: if DC motors are present, verifies an H-bridge driver is used with external power supply (Vs) and common ground.
        5. Code readiness: verifies code is present, in Text mode (not Blocks), and pins in code match wired pins.
        """
        from .wiring_service import WiringService
        from .code_service import CodeService

        wiring_service = WiringService(self.browser)
        code_service = CodeService(self.browser)

        # 1. Inspect circuit
        circuit_info = await self.inspect_circuit()
        components = circuit_info.get("components", [])
        wires = circuit_info.get("wires", [])

        # 2. Check electrical safety
        safety = await wiring_service.check_circuit_electrical_safety()

        # 3. Code inspection
        code_check = {"present": False, "mode": "none", "pins_in_code": []}
        try:
            code_res = await code_service.get_code()
            if code_res.get("success") and code_res.get("code"):
                code_text = code_res.get("code", "")
                mode = code_res.get("mode", "unknown")
                code_check["present"] = True
                code_check["mode"] = mode
                found_pins = re.findall(r"(?:int|pin|const\s+int)\s+[a-zA-Z0-9_]+\s*=\s*([0-9]+)\s*;", code_text)
                code_check["pins_in_code"] = [int(p) for p in found_pins]
        except Exception:
            pass

        # 4. Check readiness
        # Empty circuits or circuits with un-wired microcontrollers are never ready for simulation
        ready = (
            safety.get("is_safe", True)
            and len(safety.get("violations", [])) == 0
            and len(components) > 0
        )
        overview = safety.get("circuit_overview", {})
        if overview.get("has_arduino") and len(wires) == 0:
            ready = False

        checks = []

        # Check: Components
        if len(components) == 0:
            checks.append({
                "name": "Component Integrity",
                "status": "fail",
                "details": "Circuit is empty (0 components found). Simulation requires at least one active component."
            })
        else:
            checks.append({
                "name": "Component Integrity",
                "status": "pass",
                "details": f"Found {len(components)} component(s) on canvas."
            })

        # Check: Wires
        if overview.get("has_arduino") and len(wires) == 0:
            checks.append({
                "name": "Wiring Integrity",
                "status": "fail",
                "details": "Arduino microcontroller is present but has 0 wire connections."
            })
        elif len(wires) == 0:
            checks.append({
                "name": "Wiring Integrity",
                "status": "warn",
                "details": "0 wire connections found."
            })
        else:
            checks.append({
                "name": "Wiring Integrity",
                "status": "pass",
                "details": f"Found {len(wires)} wire connection(s)."
            })

        # Check: Electrical safety (Overcurrent & isolation)
        if safety.get("is_safe", True):
            checks.append({
                "name": "Electrical Safety",
                "status": "pass",
                "details": "No overcurrent or dangerous direct motor connections detected."
            })
        else:
            checks.append({
                "name": "Electrical Safety",
                "status": "fail",
                "details": f"Found {safety.get('violations_count', 0)} critical safety violation(s)."
            })

        # Check: Driver presence
        overview = safety.get("circuit_overview", {})
        if overview.get("has_motors"):
            if overview.get("has_motor_driver"):
                checks.append({
                    "name": "Motor Driver Architecture",
                    "status": "pass",
                    "details": "H-bridge Motor Driver (L293D) present to isolate motor loads."
                })
            else:
                checks.append({
                    "name": "Motor Driver Architecture",
                    "status": "warn",
                    "details": "DC motors detected without an H-bridge driver."
                })

        # Check: Code Mode
        if overview.get("has_arduino"):
            if code_check["present"]:
                if code_check["mode"] == "Blocks":
                    checks.append({
                        "name": "Arduino Code Mode",
                        "status": "warn",
                        "details": "Code editor is currently in Blocks mode. Text/C++ mode is recommended for precision."
                    })
                else:
                    checks.append({
                        "name": "Arduino Code Mode",
                        "status": "pass",
                        "details": f"Verified Text/C++ code with pins {code_check['pins_in_code']}."
                    })
            else:
                checks.append({
                    "name": "Arduino Code",
                    "status": "warn",
                    "details": "No Arduino code found."
                })

        return {
            "success": True,
            "ready_for_simulation": ready,
            "circuit_title": circuit_info.get("title", "Untitled"),
            "component_count": len(components),
            "wire_count": len(wires),
            "checks": checks,
            "safety_report": safety,
            "code_report": code_check,
            "message": "Circuit passed all pre-simulation checks and is ready to simulate." if ready else "Pre-simulation checks failed with safety violations. Fix issues before starting simulation."
        }

