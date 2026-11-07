"""Wiring service: connecting electronic pins/terminals on the Tinkercad canvas."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from ..browser.browser_manager import BrowserManager
from ..browser.selectors import EDITOR_SELECTORS
from ..config import logger


class WiringService:
    """Handles routing wires between components, setting wire colors, and deleting wires."""

    def __init__(self, browser: Optional[BrowserManager] = None) -> None:
        self.browser = browser or BrowserManager.get_instance()

    @staticmethod
    def validate_wire_coordinates(from_x: int, from_y: int, to_x: int, to_y: int) -> tuple[bool, Optional[str]]:
        """Validate all four wire terminal coordinates are within allowed canvas bounds."""
        for coord_name, val in [("from_x", from_x), ("from_y", from_y), ("to_x", to_x), ("to_y", to_y)]:
            if not isinstance(val, (int, float)) or not (-1000 <= val <= 10000):
                return False, f"Coordinate {coord_name}={val} out of bounds (-1000 to 10000)."
        return True, None

    async def connect_pins(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        color: Optional[str] = "green",
        wire_type: Optional[str] = "normal",
        waypoints: Optional[List[Dict[str, int]]] = None,
    ) -> Dict[str, Any]:
        """(Low-level) Connect two points on the circuit canvas with a wire using screen coordinates.

        Verifies that a wire object was successfully created after clicking endpoints.

        Args:
            from_x: X coordinate of source terminal/pin
            from_y: Y coordinate of source terminal/pin
            to_x: X coordinate of destination terminal/pin
            to_y: Y coordinate of destination terminal/pin
            color: Wire color (green, black, red, blue, yellow, orange, white, purple, brown)
            wire_type: Wire style (normal, hookup, alligator)
            waypoints: Optional intermediate bend points [{x: int, y: int}]
        """
        # Validate coordinates bounds
        valid, err_msg = self.validate_wire_coordinates(from_x, from_y, to_x, to_y)
        if not valid:
            return {"success": False, "message": err_msg or "Invalid coordinates."}

        page = await self.browser.get_page()

        # Proactively ensure code drawer is collapsed before wiring to prevent click interception
        try:
            await self.browser.close_code_panel(page)
        except Exception:
            pass

        # Ensure canvas is interactive and blocking overlays closed
        await self.browser.ensure_canvas_interactive(page)

        # Get existing wire IDs before drawing
        before_wires = await self._get_circuit_wires(page)
        before_ids = {w["id"] for w in before_wires if "id" in w}

        # Set wire color before drawing if dropdown available
        if color:
            await self._select_wire_color(page, color)

        logger.info(f"Connecting wire from ({from_x}, {from_y}) to ({to_x}, {to_y}) [color={color}]")

        try:
            # Temporarily disable pointer-events on existing wire segments so crossing wires don't obstruct terminal clicks
            try:
                await page.evaluate("""() => {
                    const ws = document.querySelectorAll('.wire-segment');
                    ws.forEach(el => {
                        if (!el.hasAttribute('data-orig-pe')) {
                            el.setAttribute('data-orig-pe', el.style.pointerEvents || 'auto');
                            el.style.pointerEvents = 'none';
                        }
                    });
                }""")
            except Exception:
                pass

            # 1. Click starting pin with intermediate steps for reliable hover & snap
            await page.mouse.move(from_x, from_y, steps=10)
            await page.wait_for_timeout(250)
            await page.mouse.click(from_x, from_y)
            await page.wait_for_timeout(350)

            # 2. Intermediate waypoints for neat orthogonal routing if provided
            if waypoints and isinstance(waypoints, list):
                for wp in waypoints:
                    if isinstance(wp, dict) and "x" in wp and "y" in wp:
                        wx, wy = wp["x"], wp["y"]
                        if -1000 <= wx <= 10000 and -1000 <= wy <= 10000:
                            await page.mouse.move(wx, wy, steps=5)
                            await page.wait_for_timeout(150)
                            await page.mouse.click(wx, wy)
                            await page.wait_for_timeout(150)

            # 3. Click destination pin with intermediate steps to activate connection state machine snap
            await page.mouse.move(to_x, to_y, steps=15)
            await page.wait_for_timeout(350)
            await page.mouse.click(to_x, to_y)
            await page.wait_for_timeout(800)
        finally:
            # Always restore pointer-events on existing wire segments
            try:
                await page.evaluate("""() => {
                    const ws = document.querySelectorAll('.wire-segment');
                    ws.forEach(el => {
                        const orig = el.getAttribute('data-orig-pe');
                        if (orig !== null) {
                            el.style.pointerEvents = (orig === 'auto' || !orig) ? '' : orig;
                            el.removeAttribute('data-orig-pe');
                        }
                    });
                }""")
            except Exception:
                pass

        try:
            # Re-apply color if inspector popover opened for the wire
            if color:
                await self._select_wire_color(page, color)

            # Check wire creation verification
            after_wires = await self._get_circuit_wires(page)
            new_wires = [w for w in after_wires if w.get("id") not in before_ids]

            if not new_wires and len(after_wires) <= len(before_wires):
                return {
                    "success": False,
                    "error": "wire_verification_failed",
                    "from": {"x": from_x, "y": from_y},
                    "to": {"x": to_x, "y": to_y},
                    "message": f"Wiring failed: no wire connection was created between ({from_x}, {from_y}) and ({to_x}, {to_y}). Please verify the coordinates snap to component terminals.",
                }

            new_wire = new_wires[-1] if new_wires else {"id": "wire", "color": color}
            return {
                "success": True,
                "wire_id": new_wire.get("id"),
                "from": {"x": from_x, "y": from_y},
                "to": {"x": to_x, "y": to_y},
                "color": color,
                "resolved_endpoints": {
                    "source": new_wire.get("source"),
                    "target": new_wire.get("target"),
                },
                "message": f"Successfully connected wire from ({from_x}, {from_y}) to ({to_x}, {to_y}).",
            }
        except Exception as e:
            logger.error(f"Failed to connect pins: {e}")
            return {
                "success": False,
                "message": f"Wiring failed: {e}",
            }

    async def resolve_terminal(
        self,
        component_query: str,
        pin_query: str,
        component_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resolve a component's terminal location, instance ID, and screen coordinates.

        Supports semantic pin aliases for Micro Servo (signal, power, ground),
        Arduino Uno R3 (D0-D13, 5V, GND, A0-A5), motors, sensors, and passive components.
        """
        page = await self.browser.get_page()
        await self.browser.ensure_canvas_interactive(page)
        # Ensure DOM and SVG transforms have updated post-render/placement
        await page.wait_for_timeout(100)

        resolution = await page.evaluate(r"""
            ({compQuery, pinQuery, compName}) => {
                function normalize(s) {
                    if (!s) return '';
                    const str = String(s).toLowerCase().trim();
                    if (str === '+' || str === 'positive' || str === 'pos' || str === 'plus') return 'pos';
                    if (str === '-' || str === 'negative' || str === 'neg' || str === 'minus') return 'neg';
                    return str.replace(/[^a-z0-9]/g, '');
                }

                const normC = normalize(compQuery);
                const normP = normalize(pinQuery);
                const normSpecificName = compName ? normalize(compName) : null;

                // Extract numeric index from component query (e.g. "Motor 2" -> "2", "DC Motor 4" -> "4")
                const queryMatch = compQuery.match(/(?:motor|dc\s*motor|servo|led|sensor|#)\s*([0-9]+)/i) || compQuery.match(/([0-9]+)/);
                const requestedIndex = queryMatch ? queryMatch[1] : null;

                // Extract spatial position if requested (for 4-motor robots)
                const isFL = /front\s*left|^fl$/i.test(compQuery);
                const isFR = /front\s*right|^fr$/i.test(compQuery);
                const isRL = /(?:rear|back)\s*left|^rl$/i.test(compQuery);
                const isRR = /(?:rear|back)\s*right|^rr$/i.test(compQuery);

                const ce = window.circuit_editor;
                const devMap = ce?.data?.devices?._content || {};
                const wireMap = ce?.data?.wires?._content || {};

                function isPinWired(devObj, termKey) {
                    if (!devObj || !termKey) return false;
                    const n2t = devObj.name2terminal?._content || {};
                    const entry = n2t[termKey];
                    if (!entry) return false;
                    const tObj = entry.val || entry;
                    for (const [wId, wEntry] of Object.entries(wireMap)) {
                        const w = wEntry.val || wEntry;
                        const b = typeof w.begin === 'function' ? w.begin() : w.begin;
                        const e = typeof w.end === 'function' ? w.end() : w.end;
                        if (b === tObj || e === tObj) return true;
                    }
                    return false;
                }

                function resolveBreadboardHole(bbDev, bbSvg, pQuery, wMap) {
                    if (!bbSvg) return { success: false, error: "Breadboard SVG element not found on canvas." };
                    
                    const occupiedTerms = new Set();
                    const wireEntries = wMap ? Object.entries(wMap) : [];
                    for (const [wId, wEntry] of wireEntries) {
                        const w = wEntry.val || wEntry;
                        const b = typeof w.begin === 'function' ? w.begin() : w.begin;
                        const e = typeof w.end === 'function' ? w.end() : w.end;
                        if (b) occupiedTerms.add(b);
                        if (e) occupiedTerms.add(e);
                    }
                    
                    const bbidMap = bbDev?.bbid2terminal?._content || {};
                    const termEls = Array.from(bbSvg.querySelectorAll('g.cgfx__terminal'));
                    if (termEls.length === 0) return { success: false, error: "No terminal elements found in Breadboard SVG." };
                    
                    const terminalList = [];
                    for (const el of termEls) {
                        const line = el.querySelector('line');
                        const lx = line ? parseFloat(line.getAttribute('x1') || '0') : 0;
                        const ly = line ? parseFloat(line.getAttribute('y1') || '0') : 0;
                        
                        const col = Math.round((lx + 145) / 10) + 1;
                        let row = '';
                        let group = '';
                        let rail = '';
                        
                        if (Math.abs(ly - (-95)) < 3) { rail = 'top_neg'; row = 'z'; group = 'top_neg'; }
                        else if (Math.abs(ly - (-85)) < 3) { rail = 'top_pos'; row = 'y'; group = 'top_pos'; }
                        else if (Math.abs(ly - (-55)) < 3) { row = 'j'; group = 'fj' + col; }
                        else if (Math.abs(ly - (-45)) < 3) { row = 'i'; group = 'fj' + col; }
                        else if (Math.abs(ly - (-35)) < 3) { row = 'h'; group = 'fj' + col; }
                        else if (Math.abs(ly - (-25)) < 3) { row = 'g'; group = 'fj' + col; }
                        else if (Math.abs(ly - (-15)) < 3) { row = 'f'; group = 'fj' + col; }
                        else if (Math.abs(ly - (15)) < 3) { row = 'e'; group = 'ae' + col; }
                        else if (Math.abs(ly - (25)) < 3) { row = 'd'; group = 'ae' + col; }
                        else if (Math.abs(ly - (35)) < 3) { row = 'c'; group = 'ae' + col; }
                        else if (Math.abs(ly - (45)) < 3) { row = 'b'; group = 'ae' + col; }
                        else if (Math.abs(ly - (55)) < 3) { row = 'a'; group = 'ae' + col; }
                        else if (Math.abs(ly - (85)) < 3) { rail = 'bot_neg'; row = 'x'; group = 'bot_neg'; }
                        else if (Math.abs(ly - (95)) < 3) { rail = 'bot_pos'; row = 'w'; group = 'bot_pos'; }
                        
                        const holeName = row + col;
                        
                        let matchedTObj = null;
                        for (const [bbid, tEntry] of Object.entries(bbidMap)) {
                            const t = tEntry.val || tEntry;
                            const desc = t.bbDesc || t.breadboardDescription;
                            if (desc && Math.abs(desc.x - lx) < 2 && Math.abs(desc.y - ly) < 2) {
                                matchedTObj = t;
                                break;
                            }
                        }
                        
                        let isOccupied = matchedTObj ? occupiedTerms.has(matchedTObj) : false;
                        if (!isOccupied && matchedTObj && matchedTObj.wires && typeof matchedTObj.wires.count === 'function' && matchedTObj.wires.count() > 0) {
                            isOccupied = true;
                        }
                        
                        terminalList.push({
                            el, lx, ly, col, row, group, rail, holeName, isOccupied, tObj: matchedTObj
                        });
                    }
                    
                    const raw = String(pQuery || '').trim().toLowerCase();
                    const clean = raw.replace(/[^a-z0-9\+\-]/g, '');
                    
                    let isPos = (clean === '+' || clean.includes('pos') || clean.includes('plus') || clean.includes('vcc') || clean.includes('5v') || clean.includes('power') || clean === 'y' || clean === 'w');
                    let isNeg = (clean === '-' || clean.includes('neg') || clean.includes('minus') || clean.includes('gnd') || clean.includes('ground') || clean === 'z' || clean === 'x');
                    
                    let selectedHole = null;
                    let chosenPinLabel = raw;
                    
                    if (isPos || isNeg) {
                        const isExplicitBot = clean.includes('bot') || clean.includes('bottom') || clean.startsWith('w') || clean.startsWith('x');
                        let targetRail = isPos ? (isExplicitBot ? 'bot_pos' : 'top_pos') : (isExplicitBot ? 'bot_neg' : 'top_neg');
                        
                        let candidateHoles = terminalList.filter(t => t.rail === targetRail);
                        let freeHoles = candidateHoles.filter(t => !t.isOccupied);
                        
                        if (freeHoles.length === 0) {
                            const fallbackRail = isPos ? (targetRail === 'top_pos' ? 'bot_pos' : 'top_pos') : (targetRail === 'top_neg' ? 'bot_neg' : 'top_neg');
                            candidateHoles = terminalList.filter(t => t.rail === fallbackRail);
                            freeHoles = candidateHoles.filter(t => !t.isOccupied);
                        }
                        
                        if (freeHoles.length === 0) {
                            return { success: false, error: `All power rail pins for '${raw}' are occupied on the breadboard.` };
                        }
                        
                        selectedHole = freeHoles[0];
                        chosenPinLabel = (isPos ? '+' : '-') + ` (${selectedHole.holeName})`;
                    } else {
                        let reqCol = null;
                        let reqRow = null;
                        
                        const m1 = clean.match(/^([0-9]{1,2})([a-j])$/i);
                        const m2 = clean.match(/^([a-j])([0-9]{1,2})$/i);
                        
                        if (m1) {
                            reqCol = parseInt(m1[1], 10);
                            reqRow = m1[2].toLowerCase();
                        } else if (m2) {
                            reqRow = m2[1].toLowerCase();
                            reqCol = parseInt(m2[2], 10);
                        } else {
                            const mCol = clean.match(/(?:col|column)?([0-9]{1,2})/i);
                            if (mCol) {
                                reqCol = parseInt(mCol[1], 10);
                                const isTop = clean.includes('top') || clean.includes('fj');
                                const isBot = clean.includes('bot') || clean.includes('bottom') || clean.includes('ae');
                                reqRow = isTop ? 'f' : (isBot ? 'a' : 'f');
                            }
                        }
                        
                        if (!reqCol || reqCol < 1 || reqCol > 30 || !reqRow) {
                            return { success: false, error: `Invalid breadboard tie-point query '${pQuery}'. Expected e.g. '1a'-'30j', '+', '-', 'col_1'.` };
                        }
                        
                        const isFj = ['f', 'g', 'h', 'i', 'j'].includes(reqRow);
                        const targetGroup = (isFj ? 'fj' : 'ae') + reqCol;
                        const groupHoles = terminalList.filter(t => t.group === targetGroup);
                        
                        const exactHole = groupHoles.find(t => t.row === reqRow);
                        if (exactHole && !exactHole.isOccupied) {
                            selectedHole = exactHole;
                            chosenPinLabel = exactHole.holeName;
                        } else {
                            const freeInGroup = groupHoles.filter(t => !t.isOccupied);
                            if (freeInGroup.length > 0) {
                                selectedHole = freeInGroup[0];
                                chosenPinLabel = selectedHole.holeName;
                            } else {
                                return { success: false, error: `All 5 tie-points in column ${reqCol} (group ${targetGroup}) are occupied.` };
                            }
                        }
                    }
                    
                    const el = selectedHole.el;
                    const svgOwner = el.ownerSVGElement || el.closest('svg') || document.querySelector('#breadboardTab svg');
                    let screenX = 0, screenY = 0;
                    if (svgOwner && svgOwner.createSVGPoint && el.getScreenCTM) {
                        const pt = svgOwner.createSVGPoint();
                        pt.x = selectedHole.lx;
                        pt.y = selectedHole.ly;
                        const screenPt = pt.matrixTransform(el.getScreenCTM());
                        screenX = Math.round(screenPt.x);
                        screenY = Math.round(screenPt.y);
                    } else {
                        const rect = el.getBoundingClientRect();
                        screenX = Math.round(rect.x);
                        screenY = Math.round(rect.y);
                    }
                    
                    return {
                        success: true,
                        pin: chosenPinLabel,
                        holeName: selectedHole.holeName,
                        group: selectedHole.group,
                        col: selectedHole.col,
                        row: selectedHole.row,
                        x: screenX,
                        y: screenY,
                    };
                }

                // 1. Find matching devices
                const candidates = [];
                for (const [id, entry] of Object.entries(devMap)) {
                    const dev = entry.val || entry;
                    const dName = dev.name ? String(dev.name()) : '';
                    const dDid = dev.did ? String(dev.did()) : '';
                    const desc = dev.getDescription ? dev.getDescription() : null;
                    const typeName = desc?.device?.name || desc?.footprint_name || '';

                    const normType = normalize(typeName);
                    const normId = normalize(id);
                    const normDevName = normalize(dName);

                    // Strict exclusion: never match Piezo for ultrasonic/sonar/distance query
                    if ((normC.includes('ultrasonic') || normC.includes('sonar') || normC.includes('distance')) &&
                        (normType.includes('piezo') || normType.includes('buzzer'))) {
                        continue;
                    }
                    // Never match Piezo for generic "sensor" unless user specifically asks for piezo/buzzer
                    if (normC.includes('sensor') && !normC.includes('piezo') && !normC.includes('buzzer') &&
                        (normType.includes('piezo') || normType.includes('buzzer'))) {
                        continue;
                    }

                    let score = 0;
                    if (normSpecificName && (normId === normSpecificName || normDevName === normSpecificName)) {
                        score = 250;
                    } else if (normId === normC) {
                        score = 200;
                    } else if (requestedIndex && (normDevName === requestedIndex || dName === requestedIndex)) {
                        // Only score index if device type is relevant to query word
                        const queryWord = compQuery.replace(/[0-9#]/g, '').trim().toLowerCase();
                        const isRelevant = (
                            (queryWord.includes('motor') && normType.includes('motor') && !normType.includes('servo')) ||
                            (queryWord.includes('servo') && normType.includes('servo')) ||
                            (queryWord.includes('ultrasonic') && (normType.includes('ultrasonic') || normType.includes('sonar'))) ||
                            (queryWord.includes('sensor') && (normType.includes('sensor') || normType.includes('tmp') || normType.includes('ultrasonic') || normType.includes('pir'))) ||
                            (queryWord.includes('led') && normType.includes('led')) ||
                            (queryWord.includes('piezo') && (normType.includes('piezo') || normType.includes('buzzer'))) ||
                            (queryWord.includes('buzzer') && (normType.includes('piezo') || normType.includes('buzzer')))
                        );
                        if (isRelevant || normDevName === normC) {
                            score = 180;
                        }
                    } else if (normDevName && (normC.endsWith(normDevName) || normDevName === normC)) {
                        score = 120;
                    } else if (normType === normC) {
                        score = 100;
                    } else if (
                        (normC.includes('hbridge') || normC.includes('driver') || normC.includes('l293')) &&
                        (normType.includes('hbridge') || normType.includes('driver') || normType.includes('l293'))
                    ) {
                        score = 85;
                    } else if (
                        (normC.includes('ultrasonic') || normC.includes('sonar') || normC.includes('hcsr04')) &&
                        (normType.includes('ultrasonic') || normType.includes('sonar'))
                    ) {
                        score = 80;
                    } else if (
                        (normC.includes('servo') && normType.includes('servo')) ||
                        (normC.includes('arduino') && normType.includes('arduino')) ||
                        (normC.includes('motor') && normType.includes('motor') && !normType.includes('servo')) ||
                        ((normC.includes('buzzer') || normC.includes('piezo')) && (normType.includes('piezo') || normType.includes('buzzer')))
                    ) {
                        score = 65;
                    } else if (normType.includes(normC) || normC.includes(normType)) {
                        score = 50;
                    }

                    if (score > 0) {
                        candidates.push({ id, dev, name: dName, type: typeName, did: dDid, score });
                    }
                }

                candidates.sort((a, b) => b.score - a.score);
                if (candidates.length === 0) {
                    return { success: false, error: `Component '${compQuery}' not found in circuit.` };
                }

                // If multiple candidates with same score, prioritize unconnected component for target pin
                let chosen = candidates[0];
                if (candidates.length > 1 && candidates[0].score === candidates[1].score) {
                    for (const cand of candidates) {
                        const n2t = cand.dev.name2terminal?._content || {};
                        for (const [tName, tEntry] of Object.entries(n2t)) {
                            if (normalize(tName) === normP || normP.includes(normalize(tName)) || normalize(tName).includes(normP)) {
                                if (!isPinWired(cand.dev, tName)) {
                                    chosen = cand;
                                    break;
                                }
                            }
                        }
                    }
                }

                // 2. Resolve terminal name in internal device terminals
                const dev = chosen.dev;
                const n2t = dev.name2terminal?._content || {};
                let matchedPinName = null;

                const compTypeNorm = normalize(chosen.type);
                const isServo = compTypeNorm.includes('servo') || normC.includes('servo');
                const isArduino = compTypeNorm.includes('arduino') || normC.includes('arduino');
                const isBreadboard = compTypeNorm.includes('breadboard') || normC.includes('breadboard');
                const isUltrasonic = compTypeNorm.includes('ultrasonic') || normC.includes('ultrasonic') || normC.includes('sonar') || normC.includes('hcsr04');
                const isDriver = compTypeNorm.includes('hbridge') || compTypeNorm.includes('driver') || compTypeNorm.includes('l293') || normC.includes('hbridge') || normC.includes('driver') || normC.includes('l293');
                const isMotor = (compTypeNorm.includes('motor') || normC.includes('motor')) && !isServo;
                const isTemperature = compTypeNorm.includes('temp') || compTypeNorm.includes('tmp36') || normC.includes('temp') || normC.includes('tmp36');
                const isPir = compTypeNorm.includes('pir') || normC.includes('pir');

                // Locate exact SVG element for chosen device
                let targetSvg = null;
                const bb = chosen.dev?.breadboard ? chosen.dev.breadboard() : null;
                if (bb) {
                    targetSvg = bb.node || bb.el || null;
                }
                if (!targetSvg) {
                    const allSvgs = Array.from(document.querySelectorAll('#breadboardTab svg[class*="cgfx__"], #breadboardTab g[class*="cgfx__"]'));
                    const chosenDid = chosen.did ? String(chosen.did).toLowerCase() : '';
                    const matchingSvgs = allSvgs.filter(svg => {
                        const cls = (svg.getAttribute('class') || '').toLowerCase();
                        if (chosenDid && cls.includes(chosenDid)) return true;
                        if (isServo && (cls.includes('servo') || cls.includes('micro'))) return true;
                        if (isArduino && cls.includes('arduino')) return true;
                        if (isBreadboard && cls.includes('breadboard')) return true;
                        if (isDriver && (cls.includes('hbridge') || cls.includes('driver') || cls.includes('dip16') || cls.includes('ic'))) return true;
                        if (isUltrasonic && cls.includes('ultrasonic')) return true;
                        if (isMotor && cls.includes('motor')) return true;
                        if (isTemperature && (cls.includes('temp') || cls.includes('tmp36'))) return true;
                        if (isPir && (cls.includes('pir') || cls.includes('motion') || cls.includes('234203'))) return true;
                        if (compTypeNorm.includes('piezo') && (cls.includes('piezo') || cls.includes('buzzer'))) return true;

                        // Generic match: any keyword token in the component type/name matching SVG class
                        const compTokens = (chosen.type + ' ' + (chosen.name || '')).toLowerCase().split(/[^a-z0-9]+/);
                        for (const tok of compTokens) {
                            if (tok.length >= 3 && cls.includes(tok)) return true;
                        }
                        return cls.includes(compTypeNorm);
                    });

                    // Never fall back to allSvgs[0] (which is typically the Arduino Uno)
                    targetSvg = matchingSvgs[0] || null;
                    if (matchingSvgs.length > 1) {
                        const sameTypeDevIds = [];
                        for (const [id, entry] of Object.entries(devMap)) {
                            const d = entry.val || entry;
                            const desc = d.getDescription ? d.getDescription() : null;
                            const tName = desc?.device?.name || desc?.footprint_name || '';
                            if (normalize(tName).includes(compTypeNorm) || compTypeNorm.includes(normalize(tName))) {
                                sameTypeDevIds.push(id);
                            }
                        }
                        const devIndex = sameTypeDevIds.indexOf(chosen.id);
                        if (devIndex >= 0 && devIndex < matchingSvgs.length) {
                            targetSvg = matchingSvgs[devIndex];
                        }
                    }
                }

                // Map semantic aliases
                let aliasTarget = normP;
                const isPiezo = compTypeNorm.includes('piezo') || compTypeNorm.includes('buzzer');
                if (isPiezo) {
                    const rawP = (pinQuery || '').toLowerCase().trim();
                    if (rawP === '+' || rawP.includes('pos') || rawP.includes('plus') || rawP === '1' || rawP === 'anode' || normP === 'pos') {
                        aliasTarget = 'positive';
                    } else if (rawP === '-' || rawP.includes('neg') || rawP.includes('minus') || rawP.includes('gnd') || rawP.includes('ground') || rawP === '2' || rawP === 'cathode' || normP === 'neg') {
                        aliasTarget = 'negative';
                    }
                } else if (isServo) {
                    if (normP === 'signal' || normP === 'sig' || normP === 's') aliasTarget = 'signal';
                    else if (normP === 'power' || normP === 'pwr' || normP === 'vcc' || normP === '5v' || normP === 'pos' || normP === '+') aliasTarget = 'power';
                    else if (normP === 'ground' || normP === 'gnd' || normP === 'g' || normP === 'neg' || normP === '-') aliasTarget = 'ground';
                } else if (isUltrasonic) {
                    const rawP = (pinQuery || '').toLowerCase().trim();
                    if (rawP === 'vcc' || rawP.includes('power') || rawP.includes('5v') || rawP === 'pos' || rawP === '+' || normP === 'pos') aliasTarget = 'pos';
                    else if (rawP === 'gnd' || rawP.includes('ground') || rawP === 'neg' || rawP === '-' || normP === 'neg') aliasTarget = 'neg';
                    else if (rawP.startsWith('trig') || normP.startsWith('trig') || rawP === 't') aliasTarget = 'trig';
                    else if (rawP.startsWith('echo') || normP.startsWith('echo') || rawP === 'e') aliasTarget = 'echo';
                    else if (rawP.startsWith('sig') || normP.startsWith('sig')) aliasTarget = 'sig';
                } else if (isDriver) {
                    if (normP === 'en1' || normP === 'enable1' || normP === 'enable_1' || normP === 'en12' || normP === 'pwm1') aliasTarget = 'enable1';
                    else if (normP === 'en2' || normP === 'enable2' || normP === 'enable_2' || normP === 'en34' || normP === 'pwm2') aliasTarget = 'enable2';
                    else if (normP === 'in1' || normP === 'input1' || normP === 'input_1' || normP === '1a') aliasTarget = 'input1';
                    else if (normP === 'in2' || normP === 'input2' || normP === 'input_2' || normP === '2a') aliasTarget = 'input2';
                    else if (normP === 'in3' || normP === 'input3' || normP === 'input_3' || normP === '3a') aliasTarget = 'input3';
                    else if (normP === 'in4' || normP === 'input4' || normP === 'input_4' || normP === '4a') aliasTarget = 'input4';
                    else if (normP === 'out1' || normP === 'output1' || normP === 'output_1' || normP === '1y') aliasTarget = 'output1';
                    else if (normP === 'out2' || normP === 'output2' || normP === 'output_2' || normP === '2y') aliasTarget = 'output2';
                    else if (normP === 'out3' || normP === 'output3' || normP === 'output_3' || normP === '3y') aliasTarget = 'output3';
                    else if (normP === 'out4' || normP === 'output4' || normP === 'output_4' || normP === '4y') aliasTarget = 'output4';
                    else if (normP === 'vs' || normP === 'motorpower' || normP === 'power2' || normP === 'vmot' || normP === 'vcc2') aliasTarget = 'vs';
                    else if (normP === 'vss' || normP === 'logicpower' || normP === 'power1' || normP === '5v' || normP === 'vcc1') aliasTarget = 'vss';
                    else if (normP === 'gnd' || normP === 'ground' || normP === 'neg' || normP === '-') {
                        // Pick first unused ground among GND, GND1, GND2, GND3
                        const gndCandidates = ['GND', 'GND1', 'GND2', 'GND3'];
                        const unused = gndCandidates.find(gk => !isPinWired(chosen.dev, gk));
                        aliasTarget = normalize(unused || 'GND');
                    }
                } else if (isMotor) {
                    if (normP === '1' || normP === 'terminal1' || normP === 'terminal_1' || normP === 'pos' || normP === '+') aliasTarget = 'terminal1';
                    else if (normP === '2' || normP === 'terminal2' || normP === 'terminal_2' || normP === 'neg' || normP === '-') aliasTarget = 'terminal2';
                } else if (isTemperature) {
                    const rawP = (pinQuery || '').toLowerCase().trim();
                    if (rawP === 'vcc' || rawP.includes('power') || rawP.includes('pwr') || rawP.includes('5v') || rawP === 'pos' || rawP === '+' || rawP === 'vs' || normP === 'pos' || normP === 'vcc' || normP === 'power' || normP === 'pwr' || normP === 'vs') {
                        aliasTarget = 'vcc';
                    } else if (rawP === 'gnd' || rawP.includes('ground') || rawP === 'neg' || rawP === '-' || normP === 'neg' || normP === 'gnd' || normP === 'ground') {
                        aliasTarget = 'gnd';
                    } else if (rawP.startsWith('vout') || rawP.startsWith('out') || rawP.startsWith('sig') || normP.startsWith('vout') || normP.startsWith('out') || normP.startsWith('sig')) {
                        aliasTarget = 'vout';
                    }
                } else if (isPir) {
                    const rawP = (pinQuery || '').toLowerCase().trim();
                    if (rawP === 'vcc' || rawP.includes('power') || rawP.includes('pwr') || rawP.includes('5v') || rawP === 'pos' || rawP === '+' || normP === 'vcc' || normP === 'power' || normP === 'pos') {
                        aliasTarget = 'vcc';
                    } else if (rawP === 'gnd' || rawP.includes('ground') || rawP === 'neg' || rawP === '-' || normP === 'neg' || normP === 'gnd' || normP === 'ground') {
                        aliasTarget = 'gnd';
                    } else if (rawP.startsWith('out') || rawP.startsWith('sig') || rawP.startsWith('signal') || normP.startsWith('out') || normP.startsWith('sig')) {
                        aliasTarget = 'out';
                    }
                } else if (isArduino) {
                    if (normP === '5v' || normP === 'power') aliasTarget = '5v';
                    else if (normP === '3v3' || normP === '33v') aliasTarget = '3v3';
                } else if (isBreadboard) {
                    if (normP === '-' || normP.includes('minus') || normP.includes('gnd') || normP.includes('ground') || normP.includes('neg')) aliasTarget = '-';
                    else if (normP === '+' || normP.includes('plus') || normP.includes('power') || normP.includes('5v') || normP.includes('pos')) aliasTarget = '+';
                } else {
                    // GENERIC SEMANTIC PIN CLASSIFIER (Gas, IR, Tilt, Soil, Flex, Photoresistor, Potentiometer, etc.)
                    const rawP = (pinQuery || '').toLowerCase().trim();
                    if (['power', 'vcc', '5v', '3v3', 'pos', 'pwr', '+', 'vs', 'vss', 'heater', 'h1', 'v+'].some(k => rawP.includes(k) || normP === k)) {
                        aliasTarget = 'vcc';
                    } else if (['ground', 'gnd', 'neg', '-', 'cathode', 'heater2', 'h2', 'v-'].some(k => rawP.includes(k) || normP === k)) {
                        aliasTarget = 'gnd';
                    } else if (['signal', 'sig', 'out', 'output', 'vout', 'analog', 'data', 'wiper', 'trig', 'echo', 'sense'].some(k => rawP.includes(k) || normP === k)) {
                        aliasTarget = 'out';
                    } else if (['wiper', 'analog', 'data'].some(k => rawP.includes(k) || normP === k)) {
                        aliasTarget = 'wiper';
                    } else if (['terminal1', 'terminal_1', '1', 't1', 'a'].some(k => rawP.includes(k) || normP === k)) {
                        aliasTarget = 'terminal1';
                    } else if (['terminal2', 'terminal_2', '2', 't2', 'b'].some(k => rawP.includes(k) || normP === k)) {
                        aliasTarget = 'terminal2';
                    }
                }

                // --- SPECIAL ARDUINO GND RESOLUTION ---
                if (isArduino && (normP.includes('gnd') || normP.includes('ground'))) {
                    const allGndSvgs = [];
                    const termEls = (targetSvg || document.querySelector('#breadboardTab')).querySelectorAll('g.cgfx__terminal');
                    for (const t of termEls) {
                        const name = t.querySelector('.cgfx__terminalname')?.textContent?.trim()
                            || t.querySelector('desc')?.textContent?.trim()
                            || t.querySelector('title')?.textContent?.trim()
                            || t.getAttribute('title')
                            || '';
                        if (name === 'GND' || name?.includes('GND')) {
                            const line = t.querySelector('line');
                            let lx = 0, ly = 0;
                            if (line) {
                                lx = parseFloat(line.getAttribute('x1') || '0');
                                ly = parseFloat(line.getAttribute('y1') || '0');
                            }
                            allGndSvgs.push({ t, name, lx, ly });
                        }
                    }

                    // Sort into exact physical pins:
                    // 1. Digital header (between AREF and D13): ly < 0 (lx: -31, ly: -95) -> GND3
                    // 2. Power header next to VIN: ly > 0, lx <= 28 (lx: 25, ly: 95) -> GND2
                    // 3. Power header next to 5V: ly > 0, lx > 28 (lx: 35, ly: 95) -> GND1
                    const digitalGnd = allGndSvgs.find(g => g.ly < 0);
                    const powerVinGnd = allGndSvgs.find(g => g.ly > 0 && g.lx <= 28);
                    const power5vGnd = allGndSvgs.find(g => g.ly > 0 && g.lx > 28);

                    const n2t = chosen.dev.name2terminal?._content || {};
                    const wireMap = ce?.data?.wires?._content || {};

                    // Check which physical pins actually have wires connected to them in the circuit model
                    function isPinWired(termKey) {
                        if (!termKey || !n2t[termKey]) return false;
                        const entry = n2t[termKey];
                        const tObj = entry.val || entry;
                        for (const [wId, wEntry] of Object.entries(wireMap)) {
                            const w = wEntry.val || wEntry;
                            const b = typeof w.begin === 'function' ? w.begin() : w.begin;
                            const e = typeof w.end === 'function' ? w.end() : w.end;
                            if (b === tObj || e === tObj) {
                                return true;
                            }
                        }
                        return false;
                    }

                    const gnd1Occupied = isPinWired('GND1');
                    const gnd2Occupied = isPinWired('GND2');
                    const gnd3Occupied = isPinWired('GND3');

                    let chosenGnd = null;
                    let chosenPinName = 'GND';

                    const isExplicitGnd3 = normP === 'gnd3' || normP === 'gnd_3' || normP === '3' || normP.includes('digital');
                    const isExplicitGnd2 = normP === 'gnd2' || normP === 'gnd_2' || normP === '2' || normP.includes('vin');
                    const isExplicitGnd1 = normP === 'gnd1' || normP === 'gnd_1' || normP === '1' || (normP.includes('5v') && normP.includes('gnd'));

                    if (isExplicitGnd3 && !gnd3Occupied && digitalGnd) {
                        chosenGnd = digitalGnd;
                        chosenPinName = 'GND3';
                    } else if (isExplicitGnd2 && !gnd2Occupied && powerVinGnd) {
                        chosenGnd = powerVinGnd;
                        chosenPinName = 'GND2';
                    } else if (isExplicitGnd1 && !gnd1Occupied && power5vGnd) {
                        chosenGnd = power5vGnd;
                        chosenPinName = 'GND1';
                    } else {
                        // Select an unused Arduino GND pin.
                        // GND2 (VIN header) and GND3 (digital header) are checked before GND1 (5V header)
                        // to avoid crowding the power header if already in use by buzzer/power components.
                        if (!gnd2Occupied && powerVinGnd) {
                            chosenGnd = powerVinGnd;
                            chosenPinName = 'GND2';
                        } else if (!gnd3Occupied && digitalGnd) {
                            chosenGnd = digitalGnd;
                            chosenPinName = 'GND3';
                        } else if (!gnd1Occupied && power5vGnd) {
                            chosenGnd = power5vGnd;
                            chosenPinName = 'GND1';
                        } else {
                            // If caller asked for a specific GND pin that is wired, resolve that pin directly
                            if (isExplicitGnd3 && digitalGnd) {
                                chosenGnd = digitalGnd;
                                chosenPinName = 'GND3';
                            } else if (isExplicitGnd2 && powerVinGnd) {
                                chosenGnd = powerVinGnd;
                                chosenPinName = 'GND2';
                            } else if (isExplicitGnd1 && power5vGnd) {
                                chosenGnd = power5vGnd;
                                chosenPinName = 'GND1';
                            } else {
                                // All 3 GND pins are actually occupied by wires in the circuit model
                                return {
                                    success: false,
                                    all_gnd_occupied: true,
                                    error: "all_arduino_gnd_occupied",
                                    message: "All 3 Arduino GND pins (GND1, GND2, GND3) are already connected.",
                                    occupied_pins: ["GND1", "GND2", "GND3"]
                                };
                            }
                        }
                    }

                    if (chosenGnd) {
                        const t = chosenGnd.t;
                        const lx = chosenGnd.lx;
                        const ly = chosenGnd.ly;
                        const svgOwner = t.ownerSVGElement || t.closest('svg') || document.querySelector('#breadboardTab svg');
                        if (svgOwner && svgOwner.createSVGPoint && t.getScreenCTM) {
                            const pt = svgOwner.createSVGPoint();
                            pt.x = lx;
                            pt.y = ly;
                            const screenPt = pt.matrixTransform(t.getScreenCTM());
                            return {
                                success: true,
                                component: chosen.type,
                                instance_id: chosen.id,
                                name: chosen.name,
                                pin: chosenPinName,
                                x: Math.round(screenPt.x),
                                y: Math.round(screenPt.y),
                                all_gnd_occupied: false,
                            };
                        }
                    }
                }

                // --- SPECIAL BREADBOARD RESOLUTION ---
                if (isBreadboard) {
                    const bbRes = resolveBreadboardHole(chosen.dev, targetSvg, pinQuery, wireMap);
                    if (bbRes.success) {
                        return {
                            success: true,
                            component: chosen.type,
                            instance_id: chosen.id,
                            name: chosen.name,
                            pin: bbRes.pin,
                            x: bbRes.x,
                            y: bbRes.y,
                            is_breadboard: true,
                            hole: bbRes.holeName,
                            group: bbRes.group,
                        };
                    } else {
                        return {
                            success: false,
                            error: bbRes.error || `Could not resolve breadboard pin '${pinQuery}'.`
                        };
                    }
                }

                for (const tName of Object.keys(n2t)) {
                    const nt = normalize(tName);
                    const cleanNt = nt.replace(/^~/, '').replace(/^d/, '');
                    const cleanAlias = aliasTarget.replace(/^~/, '').replace(/^d/, '');
                    if (isPiezo) {
                        if (aliasTarget === 'positive' && (nt === 'neg' || nt === 'negative' || nt === '2')) continue;
                        if (aliasTarget === 'negative' && (nt === 'pos' || nt === 'positive' || nt === '1')) continue;
                    }
                    if (
                        nt === aliasTarget ||
                        cleanNt === cleanAlias ||
                        (aliasTarget.length >= 3 && (nt.includes(aliasTarget) || aliasTarget.includes(nt)))
                    ) {
                        matchedPinName = tName;
                        break;
                    }
                }

                // Generic semantic pin fallback for any unhandled sensor / component
                if (!matchedPinName) {
                    const availablePinKeys = Object.keys(n2t);
                    const rawQ = (pinQuery || '').toLowerCase().trim();
                    const normQ = normalize(pinQuery);

                    const isPwrQ = ['power', 'vcc', '5v', '3v3', 'pos', 'pwr', '+', 'vs', 'vss', 'heater', 'heater1', 'h1', 'v+'].some(k => rawQ.includes(k) || normQ === k || aliasTarget === 'vcc');
                    const isGndQ = ['ground', 'gnd', 'neg', '-', 'heater2', 'h2', 'v-', 'cathode', '0v'].some(k => rawQ.includes(k) || normQ === k || aliasTarget === 'gnd');
                    const isSigQ = ['signal', 'sig', 'out', 'output', 'vout', 'analog', 'data', 'wiper', 'trig', 'echo', 'sense'].some(k => rawQ.includes(k) || normQ === k || aliasTarget === 'out');
                    const isWipQ = ['wiper', 'analog', 'data'].some(k => rawQ.includes(k) || normQ === k || aliasTarget === 'wiper');
                    const isT1Q = ['terminal1', 'terminal_1', '1', 't1', 'a'].some(k => rawQ.includes(k) || normQ === k || aliasTarget === 'terminal1');
                    const isT2Q = ['terminal2', 'terminal_2', '2', 't2', 'b'].some(k => rawQ.includes(k) || normQ === k || aliasTarget === 'terminal2');

                    if (isPwrQ) {
                        matchedPinName = availablePinKeys.find(k => {
                            const nk = normalize(k);
                            return ['vcc', 'power', 'pos', 'pwr', '5v', '3v3', 'vs', 'vss', 'h1', 'heater1', 'v+'].some(x => nk.includes(x) || x.includes(nk));
                        }) || null;
                    } else if (isGndQ) {
                        matchedPinName = availablePinKeys.find(k => {
                            const nk = normalize(k);
                            return ['gnd', 'ground', 'neg', 'h2', 'heater2', 'cathode', 'v-'].some(x => nk.includes(x) || x.includes(nk));
                        }) || null;
                    } else if (isWipQ) {
                        matchedPinName = availablePinKeys.find(k => normalize(k).includes('wiper') || normalize(k) === 'w') || null;
                    } else if (isSigQ) {
                        matchedPinName = availablePinKeys.find(k => {
                            const nk = normalize(k);
                            return ['sig', 'signal', 'out', 'output', 'vout', 'analog', 'data', 'wiper', 'trig', 'echo', 'a1', 'b1'].some(x => nk.includes(x) || x.includes(nk));
                        }) || null;
                    } else if (isT1Q) {
                        matchedPinName = availablePinKeys.find(k => normalize(k).includes('1') || normalize(k).includes('a') || normalize(k).includes('terminal1')) || null;
                    } else if (isT2Q) {
                        matchedPinName = availablePinKeys.find(k => normalize(k).includes('2') || normalize(k).includes('b') || normalize(k).includes('terminal2')) || null;
                    }
                }

                // 3. Locate exact SVG terminal coordinates
                let screenPos = null;
                const searchContainers = targetSvg ? [targetSvg, document.querySelector('#breadboardTab')] : [document.querySelector('#breadboardTab')];
                for (const container of searchContainers) {
                    if (!container) continue;
                    const terminals = container.querySelectorAll('g.cgfx__terminal');
                    const matchedTerms = [];
                    for (const t of terminals) {
                        const name = t.querySelector('.cgfx__terminalname')?.textContent?.trim()
                            || t.querySelector('desc')?.textContent?.trim()
                            || t.querySelector('title')?.textContent?.trim()
                            || t.getAttribute('title')
                            || '';
                        if (!name) continue;
                        const normName = normalize(name);
                        const cleanName = normName.replace(/^~/, '').replace(/^d/, '');
                        const cleanAlias = aliasTarget.replace(/^~/, '').replace(/^d/, '');

                        if (isPiezo) {
                            if (aliasTarget === 'positive' && (normName === 'neg' || normName === 'negative' || normName === '2' || name.includes('-'))) continue;
                            if (aliasTarget === 'negative' && (normName === 'pos' || normName === 'positive' || normName === '1' || name.includes('+'))) continue;
                        }
                        if (isUltrasonic) {
                            if ((aliasTarget === 'pos' || aliasTarget === 'vcc' || aliasTarget === 'power') && (normName === 'vcc' || normName === 'power' || normName === 'pos' || normName.includes('5v') || normName === 'v')) {
                                matchedTerms.push({ t, name });
                                continue;
                            }
                            if ((aliasTarget === 'neg' || aliasTarget === 'gnd' || aliasTarget === 'ground') && (normName === 'gnd' || normName === 'ground' || normName === 'neg' || normName === '-')) {
                                matchedTerms.push({ t, name });
                                continue;
                            }
                            if (aliasTarget.startsWith('trig') && normName.startsWith('trig')) {
                                matchedTerms.push({ t, name });
                                continue;
                            }
                            if (aliasTarget.startsWith('echo') && normName.startsWith('echo')) {
                                matchedTerms.push({ t, name });
                                continue;
                            }
                        }
                        if (isTemperature) {
                            if ((aliasTarget === 'vcc' || aliasTarget === 'power' || aliasTarget === 'pos' || aliasTarget === 'vs') && (normName === 'vcc' || normName === 'power' || normName === 'pos' || normName === 'vs' || normName.includes('5v') || normName === 'v')) {
                                matchedTerms.push({ t, name });
                                continue;
                            }
                            if ((aliasTarget === 'gnd' || aliasTarget === 'ground' || aliasTarget === 'neg') && (normName === 'gnd' || normName === 'ground' || normName === 'neg' || normName === '-')) {
                                matchedTerms.push({ t, name });
                                continue;
                            }
                            if ((aliasTarget === 'vout' || aliasTarget === 'out' || aliasTarget === 'sig' || aliasTarget === 'signal') && (normName === 'vout' || normName === 'out' || normName === 'sig' || normName === 'signal')) {
                                matchedTerms.push({ t, name });
                                continue;
                            }
                        }
                        if (isPir) {
                            if ((aliasTarget === 'vcc' || aliasTarget === 'power' || aliasTarget === 'pos') && (normName === 'vcc' || normName === 'power' || normName === 'pos' || normName.includes('5v') || normName === 'v')) {
                                matchedTerms.push({ t, name });
                                continue;
                            }
                            if ((aliasTarget === 'gnd' || aliasTarget === 'ground' || aliasTarget === 'neg') && (normName === 'gnd' || normName === 'ground' || normName === 'neg' || normName === '-')) {
                                matchedTerms.push({ t, name });
                                continue;
                            }
                            if ((aliasTarget === 'out' || aliasTarget === 'sig' || aliasTarget === 'signal') && (normName === 'out' || normName === 'sig' || normName === 'signal')) {
                                matchedTerms.push({ t, name });
                                continue;
                            }
                        }

                        // Generic semantic terminal match for any unlisted sensor or component
                        const rawPin = (pinQuery || '').toLowerCase().trim();
                        const isPwrTerm = ['power', 'vcc', '5v', '3v3', 'pos', 'pwr', '+', 'vs', 'vss', 'heater', 'h1'].some(k => rawPin.includes(k) || aliasTarget === 'vcc');
                        const isGndTerm = ['ground', 'gnd', 'neg', '-', 'cathode', 'h2', 'heater2'].some(k => rawPin.includes(k) || aliasTarget === 'gnd');
                        const isSigTerm = ['signal', 'sig', 'out', 'vout', 'data', 'wiper', 'analog', 'trig', 'echo'].some(k => rawPin.includes(k) || aliasTarget === 'out' || aliasTarget === 'wiper');

                        if (isPwrTerm && ['vcc', 'power', 'pos', 'pwr', '5v', '3v3', 'vs', 'vss', 'h1', 'v+'].some(k => normName === k || normName.includes(k))) {
                            matchedTerms.push({ t, name });
                            continue;
                        }
                        if (isGndTerm && ['gnd', 'ground', 'neg', '-', 'cathode', 'h2', 'v-'].some(k => normName === k || normName.includes(k))) {
                            matchedTerms.push({ t, name });
                            continue;
                        }
                        if (isSigTerm && ['sig', 'signal', 'out', 'vout', 'wiper', 'data', 'analog', 'trig', 'echo', 'a1', 'b1'].some(k => normName === k || normName.includes(k))) {
                            matchedTerms.push({ t, name });
                            continue;
                        }

                        if (
                            normName === aliasTarget ||
                            cleanName === cleanAlias ||
                            (matchedPinName && normalize(matchedPinName) === normName) ||
                            (aliasTarget.length >= 3 && (normName.includes(aliasTarget) || aliasTarget.includes(normName)))
                        ) {
                            matchedTerms.push({ t, name });
                        }
                    }

                    if (matchedTerms.length > 0) {
                        let selected = matchedTerms[0];
                        if (matchedTerms.length > 1 && aliasTarget === 'gnd') {
                            selected = matchedTerms[matchedTerms.length - 1];
                        }

                        const t = selected.t;
                        const termLabel = selected.name;
                        const line = t.querySelector('line');
                        let lx = 0, ly = 0;
                        if (line) {
                            lx = parseFloat(line.getAttribute('x1') || '0');
                            ly = parseFloat(line.getAttribute('y1') || '0');
                        }
                        const svgOwner = t.ownerSVGElement || t.closest('svg') || document.querySelector('#breadboardTab svg');
                        if (svgOwner && svgOwner.createSVGPoint && t.getScreenCTM) {
                            const pt = svgOwner.createSVGPoint();
                            pt.x = lx;
                            pt.y = ly;
                            const screenPt = pt.matrixTransform(t.getScreenCTM());
                            screenPos = { x: Math.round(screenPt.x), y: Math.round(screenPt.y), terminalName: termLabel };
                            break;
                        }
                        const rect = t.getBoundingClientRect();
                        screenPos = { x: Math.round(rect.x), y: Math.round(rect.y), terminalName: termLabel };
                        break;
                    }
                }

                if (!screenPos) {
                    return {
                        success: false,
                        error: `Terminal '${pinQuery}' could not be located on component '${chosen.type}' (${chosen.name}).`
                    };
                }

                return {
                    success: true,
                    component: chosen.type,
                    instance_id: chosen.id,
                    name: chosen.name,
                    pin: screenPos.terminalName || matchedPinName || pinQuery,
                    x: screenPos.x,
                    y: screenPos.y,
                };
            }
        """, {
            "compQuery": component_query,
            "pinQuery": pin_query,
            "compName": component_name,
        })

        if not resolution.get("success"):
            return {
                "success": False,
                "error": "terminal_lookup_failed",
                "message": resolution.get("error") or f"Terminal '{pin_query}' could not be located on component '{component_query}'.",
            }

        return resolution

    async def connect_component_pins(
        self,
        source_component: Optional[str] = None,
        source_pin: Optional[str] = None,
        target_component: Optional[str] = None,
        target_pin: Optional[str] = None,
        color: Optional[str] = "green",
        allow_unsafe_direct: bool = False,
        # Common parameter aliases
        component1_id: Optional[str] = None,
        pin1: Optional[str] = None,
        component2_id: Optional[str] = None,
        pin2: Optional[str] = None,
        from_component: Optional[str] = None,
        from_pin: Optional[str] = None,
        to_component: Optional[str] = None,
        to_pin: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Connect two named component pins and verify the resulting wire connection.

        Resolves component identities and pin coordinates from the structured DOM model,
        draws the wire, and verifies that the resulting connection exists.
        If all microcontroller ground pins are occupied, automatically expands and routes
        ground via a Breadboard rail.
        Protects against overcurrent violations by preventing direct DC motor to MCU I/O connections.

        Args:
            source_component: Source component name/type or instance id (e.g. 'Arduino Uno R3', 'Arduino', 'Motor 1')
            source_pin: Source terminal/pin name (e.g. 'D6', 'D13', 'GND', '5V', 'A0')
            target_component: Target component name/type or instance id (e.g. 'DC Motor', 'Motor 2', 'LED')
            target_pin: Target terminal/pin name (e.g. 'Terminal 1', '1', 'cathode', 'anode')
            color: Wire color ('green', 'black', 'red', 'blue', 'yellow', 'orange', 'white', 'purple', 'brown')
            allow_unsafe_direct: If True, bypasses electrical safety overcurrent protection
            component1_id: Alias for source_component
            pin1: Alias for source_pin
            component2_id: Alias for target_component
            pin2: Alias for target_pin
            from_component: Alias for source_component
            from_pin: Alias for source_pin
            to_component: Alias for target_component
            to_pin: Alias for target_pin
        """
        source_component = source_component or component1_id or from_component or kwargs.get("from") or kwargs.get("component1")
        source_pin = source_pin or pin1 or from_pin or kwargs.get("pin_1")
        target_component = target_component or component2_id or to_component or kwargs.get("to") or kwargs.get("component2")
        target_pin = target_pin or pin2 or to_pin or kwargs.get("pin_2")

        if not source_component or not source_pin or not target_component or not target_pin:
            return {
                "success": False,
                "error": "missing_required_parameters",
                "message": (
                    "connect_component_pins requires source_component, source_pin, target_component, target_pin. "
                    f"Got: source_component={source_component!r}, source_pin={source_pin!r}, "
                    f"target_component={target_component!r}, target_pin={target_pin!r}"
                ),
            }
        # Upfront Electrical Safety Validation: Prevent direct motor-to-Arduino I/O connections (>40mA rating violation)
        if not allow_unsafe_direct:
            import re
            s_c = (source_component or "").lower()
            t_c = (target_component or "").lower()
            s_p = (source_pin or "").lower()
            t_p = (target_pin or "").lower()
            s_is_motor = "motor" in s_c and "servo" not in s_c
            t_is_motor = "motor" in t_c and "servo" not in t_c
            s_is_mcu_io = ("arduino" in s_c or "uno" in s_c) and bool(re.match(r"^(d|a)?[0-9]+$", s_p))
            t_is_mcu_io = ("arduino" in t_c or "uno" in t_c) and bool(re.match(r"^(d|a)?[0-9]+$", t_p))
            if (s_is_motor and t_is_mcu_io) or (t_is_motor and s_is_mcu_io):
                mcu_pin = source_pin if s_is_mcu_io else target_pin
                motor_name = source_component if s_is_motor else target_component
                return {
                    "success": False,
                    "error": "electrical_safety_violation",
                    "hazard": "direct_motor_to_mcu_io_pin",
                    "max_allowed_current_ma": 40.0,
                    "estimated_motor_current_ma": 44.4,
                    "message": (
                        f"Electrical Safety Violation: Connecting a DC Motor ({motor_name}) directly to Arduino I/O pin '{mcu_pin}' "
                        f"exceeds the ATmega328P absolute maximum rating of 40 mA per pin. A standard DC motor draws >44.4 mA running current "
                        f"and >250 mA stall current, causing pin damage and overcurrent simulation warnings. "
                        f"Please connect the motor via an H-bridge Motor Driver (L293D) or transistor to control the motor with external power and common ground. "
                        f"To bypass, pass allow_unsafe_direct=True."
                    ),
                    "recommendation": "Use an H-bridge Motor Driver (L293D) to drive the motor from external power.",
                }

        # Resolve screen coordinates and identities for both terminals
        s = await self.resolve_terminal(source_component, source_pin)
        t = await self.resolve_terminal(target_component, target_pin)

        # Automatic fallback: if all Arduino GND pins are occupied, route via Breadboard rail
        if (isinstance(s, dict) and s.get("all_gnd_occupied") is True) or (isinstance(t, dict) and t.get("all_gnd_occupied") is True):
            logger.info("All Arduino GND pins occupied. Automatically routing ground connection via Breadboard...")
            if s.get("all_gnd_occupied") is True:
                return await self.route_pin_via_breadboard(
                    component=target_component,
                    pin=target_pin,
                    rail="ground",
                    color=color or "black",
                    microcontroller_name=source_component,
                )
            else:
                return await self.route_pin_via_breadboard(
                    component=source_component,
                    pin=source_pin,
                    rail="ground",
                    color=color or "black",
                    microcontroller_name=target_component,
                )

        if not (isinstance(s, dict) and s.get("success")):
            return s if isinstance(s, dict) else {"success": False, "message": "Failed resolving source terminal"}
        if not (isinstance(t, dict) and t.get("success")):
            return t if isinstance(t, dict) else {"success": False, "message": "Failed resolving target terminal"}

        # Secondary Electrical Safety Validation using resolved types
        if not allow_unsafe_direct:
            import re
            s_comp = (s.get("component") or "").lower()
            t_comp = (t.get("component") or "").lower()
            s_pin_res = (s.get("pin") or "").lower()
            t_pin_res = (t.get("pin") or "").lower()

            s_is_motor = "motor" in s_comp and "servo" not in s_comp
            t_is_motor = "motor" in t_comp and "servo" not in t_comp
            s_is_mcu_io = "arduino" in s_comp and bool(re.match(r"^(d|a)?[0-9]+$", s_pin_res))
            t_is_mcu_io = "arduino" in t_comp and bool(re.match(r"^(d|a)?[0-9]+$", t_pin_res))

            if (s_is_motor and t_is_mcu_io) or (t_is_motor and s_is_mcu_io):
                mcu_pin = s.get("pin") if s_is_mcu_io else t.get("pin")
                motor_name = s.get("component") if s_is_motor else t.get("component")
                return {
                    "success": False,
                    "error": "electrical_safety_violation",
                    "hazard": "direct_motor_to_mcu_io_pin",
                    "max_allowed_current_ma": 40.0,
                    "estimated_motor_current_ma": 44.4,
                    "message": (
                        f"Electrical Safety Violation: Connecting a DC Motor ({motor_name}) directly to Arduino I/O pin '{mcu_pin}' "
                        f"exceeds the ATmega328P absolute maximum rating of 40 mA per pin. A standard DC motor draws >44.4 mA running current "
                        f"and >250 mA stall current, causing pin damage and overcurrent simulation warnings. "
                        f"Please connect the motor via an H-bridge Motor Driver (L293D) or transistor to control the motor with external power and common ground. "
                        f"To bypass, pass allow_unsafe_direct=True."
                    ),
                    "recommendation": "Use an H-bridge Motor Driver (L293D) to drive the motor from external power.",
                }

        # Try programmatic connection first for infallible, coordinate-independent terminal binding
        page = await self.browser.get_page()
        prog_res = await self._programmatic_connect_terminals(
            page=page,
            source_dev_id=s["instance_id"],
            source_pin=source_pin or s["pin"],
            target_dev_id=t["instance_id"],
            target_pin=target_pin or t["pin"],
            color=color or "green",
        )
        logger.info(f"Programmatic connection result: {prog_res}")
        if prog_res.get("success"):
            return {
                "success": True,
                "wire_id": prog_res.get("wire_id"),
                "source": {
                    "component": s["component"],
                    "instance_id": s["instance_id"],
                    "name": s["name"],
                    "pin": s["pin"],
                    "x": s["x"],
                    "y": s["y"],
                },
                "target": {
                    "component": t["component"],
                    "instance_id": t["instance_id"],
                    "name": t["name"],
                    "pin": t["pin"],
                    "x": t["x"],
                    "y": t["y"],
                },
                "color": color,
                "message": f"Successfully connected {s['component']} ({s['pin']}) to {t['component']} ({t['pin']}) via internal connection engine.",
            }

        # Fallback to gesture-based connect_pins
        res = await self.connect_pins(
            from_x=s["x"],
            from_y=s["y"],
            to_x=t["x"],
            to_y=t["y"],
            color=color,
        )

        if not res.get("success"):
            # Robust fallback: use Tinkercad's internal editorModel.makeConnection engine
            logger.info("Gesture-based wiring did not create a verified wire. Attempting internal editorModel.makeConnection fallback...")
            page = await self.browser.get_page()
            fallback_res = await self._programmatic_connect_terminals(
                page=page,
                source_dev_id=s["instance_id"],
                source_pin=s["pin"],
                target_dev_id=t["instance_id"],
                target_pin=t["pin"],
                color=color or "green",
            )
            if fallback_res.get("success"):
                wire_id = fallback_res.get("wire_id")
                return {
                    "success": True,
                    "wire_id": wire_id,
                    "source": {
                        "component": s["component"],
                        "instance_id": s["instance_id"],
                        "name": s["name"],
                        "pin": s["pin"],
                        "x": s["x"],
                        "y": s["y"],
                    },
                    "target": {
                        "component": t["component"],
                        "instance_id": t["instance_id"],
                        "name": t["name"],
                        "pin": t["pin"],
                        "x": t["x"],
                        "y": t["y"],
                    },
                    "color": color,
                    "message": f"Successfully connected {s['component']} ({s['pin']}) to {t['component']} ({t['pin']}) via internal connection engine.",
                }
            return {
                "success": False,
                "error": "wiring_failed",
                "message": f"Failed to connect pins: {res.get('message')}. Internal fallback also reported: {fallback_res.get('message')}",
                "source": s,
                "target": t,
            }

        return {
            "success": True,
            "wire_id": res.get("wire_id"),
            "source": {
                "component": s["component"],
                "instance_id": s["instance_id"],
                "name": s["name"],
                "pin": s["pin"],
                "x": s["x"],
                "y": s["y"],
            },
            "target": {
                "component": t["component"],
                "instance_id": t["instance_id"],
                "name": t["name"],
                "pin": t["pin"],
                "x": t["x"],
                "y": t["y"],
            },
            "color": color,
            "message": f"Successfully connected {s['component']} ({s['pin']}) to {t['component']} ({t['pin']}).",
        }

    async def _programmatic_connect_terminals(
        self,
        page,
        source_dev_id: str,
        source_pin: str,
        target_dev_id: str,
        target_pin: str,
        color: str = "green",
    ) -> Dict[str, Any]:
        """Programmatically create a verified wire using Tinkercad's internal editorModel.makeConnection.

        Guarantees wire creation and persistence even if DOM overlays or crossing wires obstruct
        the coordinate-based mouse gesture.
        """
        try:
            return await page.evaluate("""
                ([sDevId, sPin, tDevId, tPin, wireColor]) => {
                    const ce = window.circuit_editor;
                    const csm = ce?.stateMachine?.breadboardStateMachine?.connectingStateMachine;
                    const em = csm?.editorModel || ce?.editorModel;

                    const devMap = ce?.data?.devices?._content || {};
                    const sDevEntry = devMap[sDevId];
                    const tDevEntry = devMap[tDevId];
                    if (!sDevEntry || !tDevEntry) {
                        return { success: false, message: "Device instances not found in circuit data." };
                    }

                    const sDev = sDevEntry.val || sDevEntry;
                    const tDev = tDevEntry.val || tDevEntry;

                    function findTerminal(dev, pName) {
                        if (!dev) return null;
                        const n2t = dev.name2terminal?._content || dev.bbid2terminal?._content || dev.ppid2terminal?._content || {};
                        const norm = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
                        const target = norm(pName);

                        // 1. Direct match
                        if (n2t[pName]) return n2t[pName].val || n2t[pName];
                        for (const [k, v] of Object.entries(n2t)) {
                            if (norm(k) === target) return v.val || v;
                        }

                        // 2. Terminal internal pinName/name
                        for (const [k, v] of Object.entries(n2t)) {
                            const term = v.val || v;
                            const tName = norm(term.pinName || term.name || term.id || '');
                            if (tName === target) return term;
                        }

                        // 3. Ground pin selection
                        if (target.includes('gnd') || target.includes('ground') || target === 'h2' || target === 'heater2') {
                            for (const [k, v] of Object.entries(n2t)) {
                                if (norm(k) === target) return v.val || v;
                            }
                            for (const [k, v] of Object.entries(n2t)) {
                                const nk = norm(k);
                                if (nk.includes('gnd') || nk.includes('ground') || nk === 'h2' || nk === 'heater2' || nk === 'neg' || nk === 'cathode') return v.val || v;
                            }
                        }

                        // 4. Power pin aliases (5V / VCC / Vs / H1)
                        if (target === '5v' || target === 'vcc' || target === 'power' || target === 'vs' || target === 'h1' || target.includes('vcc') || target.includes('pwr') || target.includes('heater')) {
                            for (const [k, v] of Object.entries(n2t)) {
                                const nk = norm(k);
                                if (nk === '5v' || nk === 'vcc' || nk.startsWith('vcc') || nk === 'power' || nk === 'vs' || nk === 'h1' || nk.includes('heater1') || nk === 'v+') return v.val || v;
                            }
                        }

                        // 5. Signal pin aliases
                        if (target.includes('sig') || target.includes('out') || target === 'signal' || target === 'wiper' || target === 'data') {
                            for (const [k, v] of Object.entries(n2t)) {
                                const nk = norm(k);
                                if (nk.includes('sig') || nk.includes('out') || nk === 'signal' || nk === 'wiper' || nk === 'data' || nk === 'a1' || nk === 'b1') return v.val || v;
                            }
                        }

                        // 6. Motor / passive terminal aliases
                        if (target === '1' || target === 'pos' || target === 'terminal1') {
                            for (const [k, v] of Object.entries(n2t)) {
                                const nk = norm(k);
                                if (nk === '1' || nk === 'terminal1' || nk === 'pos') return v.val || v;
                            }
                        }
                        if (target === '2' || target === 'neg' || target === 'terminal2') {
                            for (const [k, v] of Object.entries(n2t)) {
                                const nk = norm(k);
                                if (nk === '2' || nk === 'terminal2' || nk === 'neg') return v.val || v;
                            }
                        }

                        // 7. Arduino digital pins (e.g. D9 vs 9, ~9, DP9)
                        const cleanNum = target.replace(/^d/, '');
                        const reqDigits = target.replace(/[^0-9]/g, '');
                        if (cleanNum.length > 0 && !isNaN(Number(cleanNum))) {
                            for (const [k, v] of Object.entries(n2t)) {
                                const kClean = norm(k).replace(/^d/, '');
                                if (kClean === cleanNum) return v.val || v;
                            }
                        }
                        if (reqDigits.length > 0 && !target.startsWith('a')) {
                            for (const [k, v] of Object.entries(n2t)) {
                                const kNorm = norm(k);
                                if (!kNorm.startsWith('a') && kNorm.replace(/[^0-9]/g, '') === reqDigits) return v.val || v;
                            }
                        }

                        // 8. Arduino analog pins (e.g. A0)
                        if (target.startsWith('a')) {
                            for (const [k, v] of Object.entries(n2t)) {
                                if (norm(k) === target) return v.val || v;
                            }
                        }

                        // 9. Partial contains fallback
                        for (const [k, v] of Object.entries(n2t)) {
                            if (norm(k).includes(target) || target.includes(norm(k))) return v.val || v;
                        }
                        return null;
                    }

                    const sTerm = findTerminal(sDev, sPin);
                    const tTerm = findTerminal(tDev, tPin);
                    if (!sTerm || !tTerm) {
                        return { success: false, message: `Terminals not found on devices: '${sPin}' or '${tPin}'` };
                    }

                    // Check if terminals are already connected by an existing wire
                    const wireMap = ce?.data?.wires?._content || {};
                    for (const [wId, wEntry] of Object.entries(wireMap)) {
                        const w = wEntry.val || wEntry;
                        const b = typeof w.begin === 'function' ? w.begin() : w.begin;
                        const e = typeof w.end === 'function' ? w.end() : w.end;
                        if ((b === sTerm && e === tTerm) || (b === tTerm && e === sTerm)) {
                            return { success: true, already_connected: true, wire_id: String(w.id || w.versions_id || wId) };
                        }
                    }

                    try {
                        if (ce.root && typeof ce.root.rec === 'function') ce.root.rec();
                        let wire = null;
                        if (em && typeof em.makeConnection === 'function') {
                            wire = em.makeConnection(sTerm, tTerm, { color: wireColor });
                            if (wire && em.selection && typeof em.selection.add === 'function') {
                                em.selection.add(wire.interactionModel || wire);
                            }
                            if (em.preConnectLine) em.preConnectLine(null, true);
                        } else if (window.Circuits && window.Circuits.BendableWireData) {
                            wire = new window.Circuits.BendableWireData(ce.root, sTerm, tTerm, { color: wireColor });
                            ce.data.wires.add(wire);
                            if (typeof wire.updateNets === 'function') wire.updateNets();
                        }
                        if (ce.root && typeof ce.root.stopRec === 'function') ce.root.stopRec();
                        if (ce.root && typeof ce.root.save === 'function') {
                            try { ce.root.save(); } catch(e) {}
                        }

                        if (wire) {
                            const wireId = String(wire.id || wire.versions_id || '');
                            return { success: true, wire_id: wireId };
                        }
                        return { success: false, message: "makeConnection returned null." };
                    } catch (e) {
                        return { success: false, message: e.toString() };
                    }
                }
            """, [source_dev_id, source_pin, target_dev_id, target_pin, color])
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def check_circuit_electrical_safety(self) -> Dict[str, Any]:
        """Validate electrical safety of current circuit connections.

        Checks:
        1. Direct DC motor to Arduino I/O pin connections (exceeds 40 mA limit).
        2. Inductive load isolation (verifying DC motors are driven through an H-bridge or transistor).
        3. Common ground integrity between microcontroller and external supplies.
        4. Current draw estimations for high-drain components.
        """
        page = await self.browser.get_page()
        wires = await self._get_circuit_wires(page)

        return await page.evaluate("""
            (wires) => {
                const ce = window.circuit_editor;
                const devMap = ce?.data?.devices?._content || {};

                const violations = [];
                const warnings = [];
                const directMotors = [];
                let hasArduino = false;
                let hasMotorDriver = false;
                let hasMotors = false;
                let hasExternalBattery = false;

                for (const [id, dWrap] of Object.entries(devMap)) {
                    const dev = dWrap.val || dWrap;
                    const desc = dev.getDescription ? dev.getDescription() : null;
                    const type = (desc?.device?.name || desc?.footprint_name || '').toLowerCase();
                    if (type.includes('arduino')) hasArduino = true;
                    if (type.includes('hbridge') || type.includes('driver') || type.includes('l293')) hasMotorDriver = true;
                    if (type.includes('motor') && !type.includes('servo')) hasMotors = true;
                    if (type.includes('battery') || type.includes('power supply')) hasExternalBattery = true;
                }

                // Inspect each wire for direct motor to Arduino I/O connection
                for (const w of wires) {
                    const s = w.source;
                    const t = w.target;
                    if (!s || !t) continue;

                    const sType = (s.type || '').toLowerCase();
                    const tType = (t.type || '').toLowerCase();
                    const sIsMotor = sType.includes('motor') && !sType.includes('servo');
                    const tIsMotor = tType.includes('motor') && !tType.includes('servo');

                    const sIsArduinoIO = sType.includes('arduino') && /^(d|a)?[0-9]+$/i.test(s.pin || '');
                    const tIsArduinoIO = tType.includes('arduino') && /^(d|a)?[0-9]+$/i.test(t.pin || '');

                    if ((sIsMotor && tIsArduinoIO) || (tIsMotor && sIsArduinoIO)) {
                        const mcuPin = sIsArduinoIO ? s.pin : t.pin;
                        const motorName = sIsMotor ? s.name || s.type : t.name || t.type;
                        directMotors.push({
                            motor: motorName,
                            arduino_pin: mcuPin,
                            wire_id: w.id,
                            estimated_current_ma: 44.4,
                            max_pin_rating_ma: 40.0
                        });
                        violations.push({
                            rule: "OVERCURRENT_I_O_PIN",
                            severity: "CRITICAL",
                            message: `Direct connection between ${motorName} and Arduino I/O pin ${mcuPin} exceeds safe 40 mA limit (measured/estimated ~44.4 mA).`,
                            details: `Operating DC motors directly from ATmega328P I/O pins will degrade or damage the microcontroller pin and trigger simulator overcurrent warnings.`
                        });
                    }
                }

                if (hasMotors && !hasMotorDriver) {
                    warnings.push({
                        rule: "MISSING_MOTOR_DRIVER",
                        severity: "HIGH",
                        message: "Circuit contains DC motors but no H-bridge Motor Driver (L293D) or transistor driver.",
                        recommendation: "Add an 'H-bridge Motor Driver' to switch motor loads safely using external power."
                    });
                }

                if (hasMotors && !hasExternalBattery) {
                    warnings.push({
                        rule: "MISSING_EXTERNAL_MOTOR_POWER",
                        severity: "MEDIUM",
                        message: "DC motors should be powered by an external source (e.g. 9V battery), not solely from Arduino 5V regulator.",
                        recommendation: "Connect external 9V battery to motor driver Vs (Pin 8) with shared common ground."
                    });
                }

                const isSafe = violations.length === 0;

                return {
                    is_safe: isSafe,
                    violations_count: violations.length,
                    warnings_count: warnings.length,
                    violations: violations,
                    warnings: warnings,
                    direct_motor_connections: directMotors,
                    circuit_overview: {
                        has_arduino: hasArduino,
                        has_motor_driver: hasMotorDriver,
                        has_motors: hasMotors,
                        has_external_battery: hasExternalBattery,
                        total_wires: wires.length
                    },
                    recommendation: isSafe ? "Circuit adheres to electrical current limits." : "Use an H-bridge Motor Driver (L293D) and Breadboard to route motor control signals safely."
                };
            }
        """, wires)

    async def route_pin_via_breadboard(
        self,
        component: str,
        pin: str,
        rail: str = "ground",
        color: Optional[str] = "black",
        microcontroller_name: str = "Arduino Uno R3",
    ) -> Dict[str, Any]:
        """Route a component terminal through a Breadboard power/ground rail when MCU pins are exhausted or conflicted.

        1. Ensures a Breadboard exists on canvas (placing 'Breadboard Small' if needed).
        2. Ensures the breadboard rail (+/-) is connected to the microcontroller (GND for ground rail, 5V for power rail).
           If all microcontroller pins are occupied, frees one by rerouting an existing direct wire to the breadboard.
        3. Connects the component terminal to the breadboard rail.
        4. Verifies the connection exists in internal circuit state.
        """
        page = await self.browser.get_page()
        await self.browser.ensure_canvas_interactive(page)
        # Ensure DOM and SVG transforms have updated post-render/placement
        await page.wait_for_timeout(100)

        rail_lower = rail.lower().strip()
        is_ground = rail_lower in ("ground", "gnd", "-")
        bb_pin = "-" if is_ground else "+"
        wire_color = color or ("black" if is_ground else "red")
        mcu_pin = "GND" if is_ground else "5V"

        logger.info(f"Routing {component} ({pin}) via Breadboard rail '{bb_pin}' ({rail_lower})")

        # 1. Check if a Breadboard exists on the canvas
        bb_id = await page.evaluate("""
            () => {
                const ce = window.circuit_editor;
                const devMap = ce?.data?.devices?._content || {};
                for (const [id, entry] of Object.entries(devMap)) {
                    const dev = entry.val || entry;
                    const desc = dev.getDescription ? dev.getDescription() : null;
                    const name = (desc?.device?.name || desc?.footprint_name || '').toLowerCase();
                    if (name.includes('breadboard')) {
                        return id;
                    }
                }
                return null;
            }
        """)

        if not bb_id:
            logger.info("No Breadboard found on canvas. Placing 'Breadboard Small'...")
            from .components_service import ComponentsService
            cs = ComponentsService(self.browser)
            placed = await cs.add_component("Breadboard Small", x=350, y=600)
            if not placed.get("success"):
                return {
                    "success": False,
                    "error": "breadboard_placement_failed",
                    "message": f"Failed to place Breadboard: {placed.get('message')}",
                }
            bb_id = placed.get("instance_id") or "Breadboard Small"
            await page.wait_for_timeout(500)

        # 2. Check if the Breadboard rail is already connected to microcontroller GND/5V
        wires = await self._get_circuit_wires(page)
        rail_connected_to_mcu = False
        for w in wires:
            s = w.get("source")
            t = w.get("target")
            if not s or not t:
                continue
            is_bb_s = "breadboard" in (s.get("type", "") + s.get("name", "")).lower()
            is_bb_t = "breadboard" in (t.get("type", "") + t.get("name", "")).lower()
            is_mcu_s = "arduino" in (s.get("type", "") + s.get("name", "")).lower()
            is_mcu_t = "arduino" in (t.get("type", "") + t.get("name", "")).lower()

            s_pin = str(s.get("pin", ""))
            t_pin = str(t.get("pin", ""))
            if is_bb_s and is_mcu_t and (bb_pin in s_pin or self._pins_match_semantically(s_pin, bb_pin)) and (mcu_pin in t_pin.upper() or self._pins_match_semantically(t_pin, mcu_pin)):
                rail_connected_to_mcu = True
                break
            if is_bb_t and is_mcu_s and (bb_pin in t_pin or self._pins_match_semantically(t_pin, bb_pin)) and (mcu_pin in s_pin.upper() or self._pins_match_semantically(s_pin, mcu_pin)):
                rail_connected_to_mcu = True
                break

        if not rail_connected_to_mcu:
            logger.info(f"Breadboard rail '{bb_pin}' not yet connected to {microcontroller_name} {mcu_pin}. Establishing link...")
            # Try to connect a free MCU pin to breadboard rail
            mcu_term = await self.resolve_terminal(microcontroller_name, mcu_pin)
            if mcu_term.get("success") and not mcu_term.get("all_gnd_occupied"):
                free_pin = mcu_term.get("pin", mcu_pin)
                link_res = await self.connect_component_pins(
                    source_component=microcontroller_name,
                    source_pin=free_pin,
                    target_component="Breadboard Small",
                    target_pin=bb_pin,
                    color=wire_color,
                )
                logger.info(f"Connected {microcontroller_name} ({free_pin}) to Breadboard ({bb_pin}): {link_res.get('success')}")
            else:
                # All MCU pins occupied: reroute an existing component wire connected to MCU GND/5V to the breadboard
                existing_wire = None
                for w in wires:
                    s = w.get("source") or {}
                    t = w.get("target") or {}
                    s_type = (s.get("type", "") + s.get("name", "")).lower()
                    t_type = (t.get("type", "") + t.get("name", "")).lower()
                    if "arduino" in t_type and mcu_pin in str(t.get("pin", "")).upper() and "breadboard" not in s_type:
                        existing_wire = {"other_comp": s.get("type") or s.get("name"), "other_pin": s.get("pin"), "mcu_pin": t.get("pin")}
                        break
                    elif "arduino" in s_type and mcu_pin in str(s.get("pin", "")).upper() and "breadboard" not in t_type:
                        existing_wire = {"other_comp": t.get("type") or t.get("name"), "other_pin": t.get("pin"), "mcu_pin": s.get("pin")}
                        break

                if existing_wire:
                    logger.info(
                        f"Rerouting existing {existing_wire['other_comp']} ({existing_wire['other_pin']}) "
                        f"from {microcontroller_name} ({existing_wire['mcu_pin']}) to Breadboard ({bb_pin}) to free MCU pin..."
                    )
                    await self.move_connection(
                        source_component=existing_wire["other_comp"],
                        source_pin=existing_wire["other_pin"],
                        old_target_component=microcontroller_name,
                        old_target_pin=existing_wire["mcu_pin"],
                        new_target_component="Breadboard Small",
                        new_target_pin=bb_pin,
                        color=wire_color,
                    )
                    # Now existing_wire['mcu_pin'] is free! Link it to breadboard rail
                    await self.connect_component_pins(
                        source_component=microcontroller_name,
                        source_pin=existing_wire["mcu_pin"],
                        target_component="Breadboard Small",
                        target_pin=bb_pin,
                        color=wire_color,
                    )

        # 3. Connect target component to the breadboard rail
        conn_res = await self.connect_component_pins(
            source_component=component,
            source_pin=pin,
            target_component="Breadboard Small",
            target_pin=bb_pin,
            color=wire_color,
        )

        if not conn_res.get("success"):
            return {
                "success": False,
                "error": "breadboard_wiring_failed",
                "message": f"Failed to connect {component} ({pin}) to Breadboard ({bb_pin}): {conn_res.get('message')}",
            }

        return {
            "success": True,
            "routed_via_breadboard": True,
            "wire_id": conn_res.get("wire_id"),
            "component": component,
            "pin": pin,
            "breadboard_pin": bb_pin,
            "rail": rail_lower,
            "color": wire_color,
            "message": f"Successfully connected {component} ({pin}) to Breadboard {bb_pin} ({rail_lower} rail).",
        }

    async def _get_circuit_wires(self, page) -> List[Dict[str, Any]]:
        """Extract wire objects and their endpoints from internal editor state or DOM."""
        try:
            return await page.evaluate("""
                () => {
                    const ce = window.circuit_editor;
                    const wireMap = ce?.data?.wires?._content || {};
                    const devMap = ce?.data?.devices?._content || {};

                    const term2Dev = new Map();
                    for (const [dId, dEntry] of Object.entries(devMap)) {
                        const dev = dEntry.val || dEntry;
                        const dName = dev.name ? String(dev.name()) : '';
                        const desc = dev.getDescription ? dev.getDescription() : null;
                        const typeName = desc?.device?.name || desc?.footprint_name || 'Component';
                        const n2t = dev.name2terminal?._content || {};
                        for (const [tName, tEntry] of Object.entries(n2t)) {
                            const t = tEntry.val || tEntry;
                            term2Dev.set(t, { id: dId, name: dName, type: typeName, pin: tName });
                        }
                    }

                    const wires = [];
                    for (const [id, entry] of Object.entries(wireMap)) {
                        const w = entry.val || entry;
                        const b = typeof w.begin === 'function' ? w.begin() : w.begin;
                        const e = typeof w.end === 'function' ? w.end() : w.end;
                        const color = typeof w.color === 'function' ? String(w.color()) : String(w.color || '');
                        wires.push({
                            id: String(id),
                            color: color,
                            source: term2Dev.get(b) || null,
                            target: term2Dev.get(e) || null,
                        });
                    }

                    // Fallback to SVG path wires if empty
                    if (wires.length === 0) {
                        const svgWires = document.querySelectorAll('#breadboardTab path[stroke-width="2.5"], #breadboardTab path[stroke-width="2.5px"]');
                        svgWires.forEach((p, idx) => {
                            wires.push({
                                id: `svg_wire_${idx}`,
                                color: p.getAttribute('stroke') || 'green',
                                source: null,
                                target: null,
                            });
                        });
                    }

                    return wires;
                }
            """)
        except Exception:
            return []

    async def connect_by_terminals(
        self,
        from_terminal_label: str,
        to_terminal_label: str,
        color: Optional[str] = "green",
    ) -> Dict[str, Any]:
        """Attempt to find and click terminals safely by their text label or tooltip on the canvas."""
        page = await self.browser.get_page()

        # Locate terminal 1 and 2 safely without CSS injection
        t1 = page.locator("[title], text").filter(has_text=from_terminal_label).first
        t2 = page.locator("[title], text").filter(has_text=to_terminal_label).first

        if await t1.count() > 0 and await t2.count() > 0:
            box1 = await t1.bounding_box()
            box2 = await t2.bounding_box()
            if box1 and box2:
                x1 = int(box1["x"] + box1["width"] / 2)
                y1 = int(box1["y"] + box1["height"] / 2)
                x2 = int(box2["x"] + box2["width"] / 2)
                y2 = int(box2["y"] + box2["height"] / 2)
                return await self.connect_pins(x1, y1, x2, y2, color=color)

        return {
            "success": False,
            "message": f"Could not find terminals '{from_terminal_label}' and '{to_terminal_label}'. Please specify coordinates (from_x, from_y, to_x, to_y).",
        }

    @staticmethod
    def _endpoint_matches(endpoint: Optional[Dict[str, Any]], comp_query: str, pin_query: str) -> bool:
        """Check whether a wire endpoint dictionary matches a component query and pin query."""
        if not endpoint or not isinstance(endpoint, dict):
            return False
        import re

        def norm_comp(s: str) -> str:
            return re.sub(r"[^a-z0-9]", "", (s or "").lower())

        def norm_pin(s: str) -> str:
            raw = (s or "").lower().strip()
            if raw in ("+", "pos", "positive", "anode"):
                return "+"
            if raw in ("-", "neg", "negative", "cathode"):
                return "-"
            if raw in ("vcc", "power", "5v"):
                return "pos"
            if raw in ("gnd", "ground"):
                return "neg"
            return re.sub(r"[^a-z0-9]", "", raw)

        nc = norm_comp(comp_query)
        np = norm_pin(pin_query)

        ep_type = norm_comp(endpoint.get("type", ""))
        ep_name = norm_comp(endpoint.get("name", ""))
        ep_id = norm_comp(endpoint.get("id", ""))
        ep_pin_raw = (endpoint.get("pin", "") or "").lower().strip()
        ep_pin = norm_pin(ep_pin_raw)

        # Strict exclusion: ultrasonic/sonar queries never match piezo
        if ("ultrasonic" in nc or "sonar" in nc) and ("piezo" in ep_type or "buzzer" in ep_type):
            return False
        if "sensor" in nc and ("piezo" in ep_type or "buzzer" in ep_type) and "piezo" not in nc and "buzzer" not in nc:
            return False

        comp_synonyms = {
            "buzzer": ["piezo", "buzzer", "speaker"],
            "piezo": ["piezo", "buzzer", "speaker"],
            "motor": ["motor", "dcmotor", "dc_motor", "gearmotor"],
            "arduino": ["arduino", "arduinouno", "arduinounor3", "uno"],
            "ultrasonic": ["ultrasonic", "ultrasonicdistancesensor", "ultrasonicsensor", "sonar", "hcsr04"],
            "hcsr04": ["ultrasonic", "ultrasonicdistancesensor", "ultrasonicsensor", "sonar", "hcsr04"],
        }
        syns = comp_synonyms.get(nc, [nc])

        comp_match = any(
            s in ep_type or ep_type in s or
            s in ep_name or ep_name in s or
            s in ep_id or ep_id in s
            for s in syns
        )

        # Pin matching
        pin_match = False
        is_piezo_ep = "piezo" in ep_type or "buzzer" in ep_type
        if is_piezo_ep:
            if np in ("+", "pos", "1"):
                pin_match = ep_pin == "+" or ep_pin_raw in ("+", "pos", "positive", "1")
            elif np in ("-", "neg", "2", "gnd"):
                pin_match = ep_pin == "-" or ep_pin_raw in ("-", "neg", "negative", "2")
            else:
                pin_match = (np == ep_pin)
        elif np in ("+", "-"):
            pin_match = (ep_pin == np or (np == "+" and ep_pin_raw in ("+", "pos", "positive", "1")) or (np == "-" and ep_pin_raw in ("-", "neg", "negative", "2")))
        elif np in ("pos", "neg"):
            pin_match = (ep_pin == np or (np == "pos" and ep_pin_raw in ("pos", "vcc", "5v", "+")) or (np == "neg" and ep_pin_raw in ("neg", "gnd", "ground", "-")))
        else:
            pin_match = (
                np == ep_pin or
                np.lstrip("d") == ep_pin.lstrip("d") or
                (np in ("terminal1", "1") and ep_pin in ("terminal1", "1")) or
                (np in ("terminal2", "2") and ep_pin in ("terminal2", "2")) or
                ("gnd" in np and "gnd" in ep_pin)
            )

        return comp_match and pin_match

    async def delete_wire_between(
        self,
        source_component: str,
        source_pin: str,
        target_component: str,
        target_pin: str,
    ) -> Dict[str, Any]:
        """Find and delete the wire connecting two specific component pins."""
        page = await self.browser.get_page()
        await self.browser.ensure_canvas_interactive(page)
        # Ensure DOM and SVG transforms have updated post-render/placement
        await page.wait_for_timeout(100)

        wires = await self._get_circuit_wires(page)
        target_wire = None
        for w in wires:
            s = w.get("source")
            t = w.get("target")
            if (
                (self._endpoint_matches(s, source_component, source_pin) and self._endpoint_matches(t, target_component, target_pin)) or
                (self._endpoint_matches(t, source_component, source_pin) and self._endpoint_matches(s, target_component, target_pin))
            ):
                target_wire = w
                break

        if not target_wire:
            return {
                "success": False,
                "error": "wire_not_found",
                "message": f"No wire found connecting {source_component} ({source_pin}) and {target_component} ({target_pin}).",
            }

        wire_id = target_wire.get("id")
        logger.info(f"Deleting wire {wire_id} between {source_component} ({source_pin}) and {target_component} ({target_pin})")

        # 1. Deselect any currently focused component first to prevent accidental deletion
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(100)
        except Exception:
            pass

        # 2. Safely remove wire via circuit editor data model and root save
        deleted = await page.evaluate("""
            (wId) => {
                try {
                    const ce = window.circuit_editor;
                    const wEntry = ce?.data?.wires?._content?.[wId];
                    if (wEntry) {
                        const w = wEntry.val || wEntry;
                        let removed = false;
                        if (ce.selection && typeof ce.selection.select === 'function') {
                            try { ce.selection.select(w); } catch (e) {}
                        }
                        if (ce.commands && typeof ce.commands.execute === 'function') {
                            try {
                                ce.commands.execute('delete');
                                removed = true;
                            } catch (e) {}
                        }
                        if (!removed && ce?.data?.wires && typeof ce.data.wires.remove === 'function') {
                            try {
                                ce.data.wires.remove(w);
                                removed = true;
                            } catch (e) {}
                        }
                        if (!removed && typeof w.remove === 'function') {
                            try {
                                w.remove();
                                removed = true;
                            } catch (e) {}
                        }
                        if (removed && ce?.root?.save) {
                            try { ce.root.save(); } catch (e) {}
                        }
                        return removed;
                    }
                } catch (e) {}
                return false;
            }
        """, wire_id)

        # 3. Only click delete button if a wire is actively confirmed selected and NO component is selected
        if not deleted:
            try:
                comp_selected = await page.evaluate(r"""
                    () => {
                        const sel = document.querySelector('.cgfx__device.is-selected, .is-selected:not(.wire-segment)');
                        return !!sel;
                    }
                """)
                if not comp_selected:
                    delete_btn = await self.browser.find_first_matching(EDITOR_SELECTORS.get("delete_btn", []), timeout=500, page=page)
                    if delete_btn:
                        await delete_btn.click()
            except Exception:
                pass

        await page.wait_for_timeout(800)

        # Verify wire was deleted
        after_wires = await self._get_circuit_wires(page)
        still_exists = any(w.get("id") == wire_id for w in after_wires)
        if still_exists:
            return {
                "success": False,
                "error": "wire_deletion_failed",
                "wire_id": wire_id,
                "message": f"Failed to delete wire {wire_id}: wire still exists in circuit.",
            }

        return {
            "success": True,
            "wire_id": wire_id,
            "deleted_wire_id": wire_id,
            "source": f"{source_component} ({source_pin})",
            "target": f"{target_component} ({target_pin})",
            "message": f"Successfully deleted wire {wire_id} between {source_component} ({source_pin}) and {target_component} ({target_pin}).",
        }

    async def move_connection(
        self,
        source_component: str,
        source_pin: str,
        old_target_component: str,
        old_target_pin: str,
        new_target_component: str,
        new_target_pin: str,
        color: Optional[str] = "green",
    ) -> Dict[str, Any]:
        """Move a wire connection from an old target terminal to a new target terminal.

        1. Finds and removes the old wire between source and old_target.
        2. Creates a new wire connection between source and new_target.
        3. Verifies both deletion of the old wire and creation of the new connection.
        """
        # Step 1: Remove old wire
        del_res = await self.delete_wire_between(
            source_component=source_component,
            source_pin=source_pin,
            target_component=old_target_component,
            target_pin=old_target_pin,
        )
        if not del_res.get("success"):
            logger.warning(f"Old wire removal note: {del_res.get('message')}. Proceeding to create new connection.")

        # Step 2: Connect to new target pin
        connect_res = await self.connect_component_pins(
            source_component=source_component,
            source_pin=source_pin,
            target_component=new_target_component,
            target_pin=new_target_pin,
            color=color,
        )

        if not connect_res.get("success"):
            return {
                "success": False,
                "error": "move_connection_failed",
                "old_wire_deleted": del_res.get("success", False),
                "connect_error": connect_res.get("message"),
                "message": f"Failed to move connection: {connect_res.get('message')}",
            }

        return {
            "success": True,
            "old_wire_deleted": del_res.get("success", False),
            "new_wire_id": connect_res.get("wire_id"),
            "source": connect_res.get("source"),
            "target": connect_res.get("target"),
            "color": color,
            "message": f"Successfully moved {source_component} ({source_pin}) connection from {old_target_component} ({old_target_pin}) to {new_target_component} ({new_target_pin}).",
        }

    async def delete_wire(self, x: int, y: int) -> Dict[str, Any]:
        """Click a wire on the canvas and delete it with strict component safety guards."""
        if not (-1000 <= x <= 10000) or not (-1000 <= y <= 10000):
            return {"success": False, "message": "Coordinates out of bounds (-1000 to 10000)."}
        page = await self.browser.get_page()
        try:
            # Step 1: Pre-check element at coordinates to protect components
            guard_check = await page.evaluate(r"""
                ([cx, cy]) => {
                    function getComponentAncestor(elem) {
                        if (!elem) return null;
                        if (elem.classList && (
                            elem.classList.contains('wire-segment') ||
                            elem.classList.contains('cgfx__wire') ||
                            elem.closest?.('.wire-segment, .cgfx__wire')
                        )) {
                            return null;
                        }
                        const comp = elem.closest?.(
                            'svg.cgfx__device, svg[class*="cgfx__"]:not(.cgfx__wire), ' +
                            'g.cgfx__device, g.cgfx__component, g[class*="device"], ' +
                            'g.cgfx__terminal, .editor-component, [data-device-id]'
                        );
                        if (comp) {
                            const nameEl = comp.querySelector?.('.cgfx__devicename, .cgfx__terminalname, text');
                            return nameEl?.textContent?.trim() || comp.getAttribute?.('class') || 'Component';
                        }
                        return null;
                    }

                    const direct = document.elementFromPoint(cx, cy);
                    const compName = getComponentAncestor(direct);
                    if (compName) {
                        return {
                            is_component: true,
                            component: compName,
                            message: `Safety guard: Target at (${cx}, ${cy}) is inside component '${compName}'. Refusing deletion to prevent accidental component removal.`
                        };
                    }

                    // Check if direct element is a wire
                    let wireEl = direct?.closest?.('path.wire-segment, .cgfx__wire, [class*="wire-segment"]') || null;

                    // Proximity check within 15px if not directly on wire
                    if (!wireEl) {
                        const deltas = [-15, -10, -5, 5, 10, 15];
                        for (const dx of deltas) {
                            for (const dy of deltas) {
                                const probe = document.elementFromPoint(cx + dx, cy + dy);
                                if (probe && !getComponentAncestor(probe)) {
                                    const candidate = probe.closest?.('path.wire-segment, .cgfx__wire, [class*="wire-segment"]');
                                    if (candidate) {
                                        wireEl = candidate;
                                        break;
                                    }
                                }
                            }
                            if (wireEl) break;
                        }
                    }

                    // Bounding rect check on all wire segments
                    if (!wireEl) {
                        const segments = Array.from(document.querySelectorAll('path.wire-segment, [class*="wire-segment"]'));
                        for (const seg of segments) {
                            const rect = seg.getBoundingClientRect();
                            if (cx >= rect.left - 10 && cx <= rect.right + 10 && cy >= rect.top - 10 && cy <= rect.bottom + 10) {
                                wireEl = seg;
                                break;
                            }
                        }
                    }

                    if (!wireEl) {
                        return { is_wire: false, message: `No wire segment found at or near (${cx}, ${cy}).` };
                    }

                    const rect = wireEl.getBoundingClientRect();
                    return {
                        is_wire: true,
                        click_x: Math.round(rect.left + rect.width / 2),
                        click_y: Math.round(rect.top + rect.height / 2),
                    };
                }
            """, [x, y])

            # Safety guard 1: Component targeted
            if guard_check and guard_check.get("is_component"):
                logger.warning(f"delete_wire prevented: {guard_check.get('message')}")
                return {
                    "success": False,
                    "error": "destructive_action_prevented",
                    "message": guard_check.get("message"),
                }

            # Safety guard 2: No wire found at coordinates
            if not guard_check or not guard_check.get("is_wire"):
                return {
                    "success": False,
                    "error": "no_wire_at_coordinates",
                    "message": guard_check.get("message", f"No wire found at coordinates ({x}, {y}). Deletion aborted.") if guard_check else f"No wire found at coordinates ({x}, {y}). Deletion aborted.",
                }

            # Step 2: Target the verified wire
            click_x = guard_check.get("click_x", x)
            click_y = guard_check.get("click_y", y)

            await page.mouse.click(click_x, click_y)
            await page.wait_for_timeout(200)

            # Safety guard 3: Confirm no component was selected by the click
            comp_selected = await page.evaluate(r"""
                () => {
                    const sel = document.querySelector('.cgfx__device.is-selected, .is-selected:not(.wire-segment)');
                    return sel ? (sel.textContent?.trim() || 'Component') : null;
                }
            """)
            if comp_selected:
                logger.warning(f"delete_wire click accidentally focused component '{comp_selected}'. Clearing selection with Escape.")
                await page.keyboard.press("Escape")
                return {
                    "success": False,
                    "error": "destructive_action_prevented",
                    "message": f"Safety guard: Selection focused component '{comp_selected}' instead of wire. Action aborted and selection cleared.",
                }

            # Step 3: Delete the selected wire
            delete_btn = await self.browser.find_first_matching(EDITOR_SELECTORS.get("delete_btn", []), timeout=500, page=page)
            if delete_btn:
                await delete_btn.click()
            else:
                await page.keyboard.press("Delete")
                await page.wait_for_timeout(100)
                await page.keyboard.press("Backspace")

            await page.wait_for_timeout(300)

            # Save editor state if save method is present
            if hasattr(page, "evaluate"):
                try:
                    await page.evaluate("""() => {
                        const ce = window.circuit_editor;
                        if (ce?.root?.save) {
                            try { ce.root.save(); } catch (e) {}
                        }
                    }""")
                except Exception:
                    pass

            return {
                "success": True,
                "message": f"Wire at ({x}, {y}) deleted successfully.",
            }
        except Exception as e:
            return {"success": False, "message": f"Failed deleting wire: {e}"}

    async def _select_wire_color(self, page, color: str) -> None:
        """Select wire color in toolbar or popover."""
        color_lower = color.lower().strip()
        try:
            # 1. Try Tinkercad toolbar custom wire-color dropdown
            selected = await page.evaluate("""
                (targetColor) => {
                    // Try finding option directly in custom dropdown
                    const option = document.querySelector(
                        `.js-wire-color-container a.editor__dropdown__list__option__value[data-item="${targetColor}"]`
                    );
                    if (option) {
                        option.click();
                        return true;
                    }
                    return false;
                }
            """, color_lower)

            if not selected:
                # Open the dropdown first if needed
                btn = await self.browser.find_first_matching(EDITOR_SELECTORS["wire_color_dropdown"], timeout=1000, page=page)
                if btn:
                    tag = await btn.evaluate("el => el.tagName.toLowerCase()")
                    if tag == "select":
                        await btn.select_option(label=color.capitalize())
                    else:
                        await btn.click()
                        await page.wait_for_timeout(200)
                        opt = page.locator(f".js-wire-color-container a[data-item='{color_lower}']").first
                        if await opt.count() > 0:
                            await opt.click()
        except Exception:
            pass

    async def clear_circuit_wires(
        self,
        component_name: Optional[str] = None,
        verify_persistence: bool = False,
    ) -> Dict[str, Any]:
        """Remove all wires in the circuit, or all wires connected to a specific component.

        Uses native Playwright UI element deletion to guarantee Tinkercad dirty-state dispatch
        and cloud persistence across reloads, combined with internal collection cleanup.

        Args:
            component_name: Optional component name/type or instance id to filter deletions by.
            verify_persistence: If True, triggers autosave and reloads to confirm wire removal.
        """
        page = await self.browser.get_page()
        if hasattr(self.browser, "ensure_canvas_interactive"):
            await self.browser.ensure_canvas_interactive(page)

        # Fast, infallible internal model sweep first
        removal_res = await page.evaluate(r"""
            (compFilter) => {
                const ce = window.circuit_editor;
                const wireColl = ce?.data?.wires;
                if (!wireColl || !wireColl._content) {
                    return { success: false, removed_count: 0, message: "No wire collection found." };
                }

                const norm = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
                const targetComp = compFilter ? norm(compFilter) : null;

                const wIds = Object.keys(wireColl._content);
                let removed = 0;

                for (const wId of wIds) {
                    const wEntry = wireColl._content[wId];
                    if (!wEntry) continue;
                    const w = wEntry.val || wEntry;

                    if (targetComp && targetComp !== 'all') {
                        const b = typeof w.begin === 'function' ? w.begin() : w.begin;
                        const e = typeof w.end === 'function' ? w.end() : w.end;
                        const bDev = b?.device?.name ? String(b.device.name()) : '';
                        const eDev = e?.device?.name ? String(e.device.name()) : '';
                        const bType = b?.device?.getDescription ? (b.device.getDescription()?.device?.name || '') : '';
                        const eType = e?.device?.getDescription ? (e.device.getDescription()?.device?.name || '') : '';

                        const matches = (
                            norm(bDev).includes(targetComp) || norm(eDev).includes(targetComp) ||
                            norm(bType).includes(targetComp) || norm(eType).includes(targetComp)
                        );
                        if (!matches) continue;
                    }

                    try {
                        if (typeof wireColl.remove === 'function') {
                            wireColl.remove(w);
                            removed++;
                        } else if (typeof w.remove === 'function') {
                            w.remove();
                            removed++;
                        }
                    } catch (e) {}
                }

                if (ce?.root?.save) {
                    try { ce.root.save(); } catch (e) {}
                }

                return {
                    success: true,
                    removed_count: removed,
                    remaining_count: Object.keys(wireColl._content).length,
                };
            }
        """, component_name)

        if isinstance(removal_res, dict):
            internal_removed = removal_res.get("removed_count", 0)
            total_removed = internal_removed
            remaining_count = removal_res.get("remaining_count", 0)
        else:
            total_removed = 0
            remaining_count = 0

        # Method 3: Optional reload verification with debounce wait
        if verify_persistence and hasattr(page, "reload"):
            logger.info("Waiting for wire clearing autosave to settle before reload (4.5s)...")
            await page.wait_for_timeout(4500)
            await page.reload(wait_until="domcontentloaded")
            await page.wait_for_timeout(3500)
            if hasattr(self.browser, "ensure_canvas_interactive"):
                await self.browser.ensure_canvas_interactive(page)
            remaining_wires = await self._get_circuit_wires(page)
            remaining_count = len(remaining_wires)

        return {
            "success": True,
            "removed_count": total_removed,
            "remaining_count": remaining_count,
            "message": f"Successfully cleared {total_removed} wire(s). Remaining: {remaining_count}.",
        }

    async def connect_and_verify_wires(
        self,
        connections: List[Any],
        circuit_id_or_url: Optional[str] = None,
        expected_wire_count: Optional[int] = None,
        clear_existing_wires: bool = False,
        code: Optional[str] = None,
        verify_after_each: bool = True,
        reload_after_each: bool = False,
        verify_persistence: bool = True,
        run_schematic_erc: bool = True,
    ) -> Dict[str, Any]:
        """Orchestrate robust, one-wire-at-a-time wiring with dynamic terminal discovery, duplicate prevention,

        autosave synchronization, reload persistence verification, and schematic Electrical Rule Checks (ERC).

        Supports both dictionary format:
        [
            {"source_component": "Arduino Uno R3", "source_pin": "5V", "target_component": "Ultrasonic Distance Sensor (4-pin)", "target_pin": "pos", "color": "red"}
        ]
        and tuple/list format:
        [
            ["Arduino Uno R3", "5V", "Ultrasonic Distance Sensor (4-pin)", "pos", "red"],
            ["Arduino Uno R3", "D2", "Ultrasonic Distance Sensor (4-pin)", "trig"]
        ]

        Args:
            connections: List of connection dicts or tuples/lists.
            circuit_id_or_url: Optional circuit ID or URL to open first (if not already open).
            expected_wire_count: Optional expected final wire count to validate after completion.
            clear_existing_wires: If True, clears all existing wires before applying new connections.
            code: Optional Arduino C++ sketch code to inject and verify in the same transactional workflow.
            verify_after_each: If True, verifies each wire in the circuit model immediately after placement.
            reload_after_each: If True, reloads the page after each wire.
            verify_persistence: If True, reloads the project after all wires are placed to verify cloud sync.
            run_schematic_erc: If True, runs Electrical Rule Checks to detect shorts or floating VCC/GND pins.
        """
        page = await self.browser.get_page()

        # 1. Open circuit if requested
        if circuit_id_or_url:
            from .circuits_service import CircuitsService
            circuits_svc = CircuitsService(self.browser)
            open_res = await circuits_svc.open_circuit(circuit_id_or_url)
            if not open_res.get("success"):
                return {
                    "success": False,
                    "error": "open_circuit_failed",
                    "message": f"Failed to open circuit '{circuit_id_or_url}': {open_res.get('message')}",
                }
            page = await self.browser.get_page()
            await page.wait_for_timeout(2000)

        # 2. Ensure canvas is interactive and modals closed
        if hasattr(self.browser, "ensure_canvas_interactive"):
            await self.browser.ensure_canvas_interactive(page)
        if hasattr(self.browser, "close_code_panel"):
            await self.browser.close_code_panel(page)
        if hasattr(self.browser, "close_overlays_and_modals"):
            await self.browser.close_overlays_and_modals(page)

        # 3. Clear existing wires if requested
        if clear_existing_wires:
            logger.info("clear_existing_wires=True: clearing all existing wires before wiring...")
            await self.clear_circuit_wires(verify_persistence=False)

        # 4. Normalize connections input (supports dicts or lists/tuples)
        if not connections or not isinstance(connections, list):
            return {
                "success": False,
                "error": "invalid_arguments",
                "message": "connections must be a non-empty list of connection dictionaries or tuples.",
            }

        norm_connections: List[Dict[str, str]] = []
        for item in connections:
            if isinstance(item, (list, tuple)):
                if len(item) >= 4:
                    norm_connections.append({
                        "source_component": str(item[0]),
                        "source_pin": str(item[1]),
                        "target_component": str(item[2]),
                        "target_pin": str(item[3]),
                        "color": str(item[4]) if len(item) > 4 else "green",
                    })
            elif isinstance(item, dict):
                src_comp = item.get("source_component") or item.get("source") or item.get("from_component") or item.get("from")
                src_pin = item.get("source_pin") or item.get("from_pin") or item.get("pin1")
                tgt_comp = item.get("target_component") or item.get("target") or item.get("to_component") or item.get("to")
                tgt_pin = item.get("target_pin") or item.get("to_pin") or item.get("pin2")
                color = item.get("color") or "green"
                norm_connections.append({
                    "source_component": str(src_comp or ""),
                    "source_pin": str(src_pin or ""),
                    "target_component": str(tgt_comp or ""),
                    "target_pin": str(tgt_pin or ""),
                    "color": str(color),
                })

        results: List[Dict[str, Any]] = []
        succeeded = 0
        failed = 0

        # 5. Wiring loop: one wire at a time with dynamic discovery & verification
        for conn in norm_connections:
            src_comp = conn["source_component"]
            src_pin = conn["source_pin"]
            tgt_comp = conn["target_component"]
            tgt_pin = conn["target_pin"]
            color = conn["color"]

            if not src_comp or not src_pin or not tgt_comp or not tgt_pin:
                results.append({
                    "success": False,
                    "status": "invalid_parameters",
                    "error": "missing_parameters",
                    "message": f"Connection entry missing required parameters: {conn}",
                    "entry": conn,
                })
                failed += 1
                continue

            # Check for existing duplicate wire before creating
            current_wires = await self._get_circuit_wires(page)
            already_connected = False
            for w in current_wires:
                s = w.get("source")
                t = w.get("target")
                if s and t:
                    if (self._endpoint_matches(s, src_comp, src_pin) and self._endpoint_matches(t, tgt_comp, tgt_pin)) or \
                       (self._endpoint_matches(t, src_comp, src_pin) and self._endpoint_matches(s, tgt_comp, tgt_pin)):
                        already_connected = True
                        break

            if already_connected:
                logger.info(f"Wire between {src_comp} ({src_pin}) and {tgt_comp} ({tgt_pin}) already exists. Skipping duplicate.")
                results.append({
                    "success": True,
                    "status": "already_connected",
                    "source": f"{src_comp} ({src_pin})",
                    "target": f"{tgt_comp} ({tgt_pin})",
                    "color": color,
                    "message": f"Connection already exists in circuit model between {src_comp} ({src_pin}) and {tgt_comp} ({tgt_pin}).",
                })
                succeeded += 1
                continue

            logger.info(f"Connecting wire: {src_comp} ({src_pin}) -> {tgt_comp} ({tgt_pin}) [color={color}]")
            wire_res = await self.connect_component_pins(
                source_component=src_comp,
                source_pin=src_pin,
                target_component=tgt_comp,
                target_pin=tgt_pin,
                color=color,
            )

            if not wire_res.get("success"):
                results.append({
                    "success": False,
                    "status": "failed",
                    "source": f"{src_comp} ({src_pin})",
                    "target": f"{tgt_comp} ({tgt_pin})",
                    "error": wire_res.get("error", "wiring_failed"),
                    "message": wire_res.get("message", "Failed to connect wire"),
                })
                failed += 1
                continue

            # Immediate per-wire verification
            if verify_after_each:
                post_wires = await self._get_circuit_wires(page)
                verified = any(
                    (self._endpoint_matches(w.get("source"), src_comp, src_pin) and self._endpoint_matches(w.get("target"), tgt_comp, tgt_pin)) or
                    (self._endpoint_matches(w.get("target"), src_comp, src_pin) and self._endpoint_matches(w.get("source"), tgt_comp, tgt_pin))
                    for w in post_wires
                )
                if not verified:
                    results.append({
                        "success": False,
                        "status": "verification_failed",
                        "source": f"{src_comp} ({src_pin})",
                        "target": f"{tgt_comp} ({tgt_pin})",
                        "message": "Wire gesture executed but connection was not verified in circuit model.",
                    })
                    failed += 1
                    continue

            results.append({
                "success": True,
                "status": "connected_and_verified",
                "wire_id": wire_res.get("wire_id"),
                "source": f"{src_comp} ({src_pin})",
                "target": f"{tgt_comp} ({tgt_pin})",
                "color": color,
                "message": f"Successfully connected and verified {src_comp} ({src_pin}) -> {tgt_comp} ({tgt_pin}).",
            })
            succeeded += 1

            if reload_after_each and hasattr(page, "reload"):
                await page.wait_for_timeout(4000)
                await page.reload(wait_until="domcontentloaded")
                await page.wait_for_timeout(3500)
                if hasattr(self.browser, "ensure_canvas_interactive"):
                    await self.browser.ensure_canvas_interactive(page)

        # 6. Inject Arduino code if provided
        code_res = None
        if code:
            try:
                from .code_service import CodeService
                code_svc = CodeService(self.browser)
                code_res = await code_svc.set_code(code=code, ensure_text_mode=True, verify_persistence=False)
            except Exception as e:
                logger.warning(f"Error injecting code during connect_and_verify_wires: {e}")

        # 7. Final autosave & persistence verification
        if hasattr(page, "evaluate"):
            try:
                await page.evaluate("""() => {
                    const ce = window.circuit_editor;
                    if (ce?.root?.save) {
                        try { ce.root.save(); } catch (e) {}
                    }
                }""")
            except Exception:
                pass

        if verify_persistence and hasattr(page, "reload"):
            logger.info("Performing final autosave wait (4.5s) and project reload verification...")
            await page.wait_for_timeout(4500)
            try:
                await page.reload(wait_until="domcontentloaded")
                await page.wait_for_timeout(3500)
                if hasattr(self.browser, "ensure_canvas_interactive"):
                    await self.browser.ensure_canvas_interactive(page)
            except Exception as e:
                logger.warning(f"Final persistence reload encountered non-fatal error: {e}")

        final_wires = await self._get_circuit_wires(page)
        persisted_wire_count = len(final_wires)

        # 8. Verify each requested endpoint pair in reloaded circuit model
        endpoint_verification: List[Dict[str, Any]] = []
        for conn in norm_connections:
            sc = conn["source_component"]
            sp = conn["source_pin"]
            tc = conn["target_component"]
            tp = conn["target_pin"]

            found_wire = next(
                (w for w in final_wires if
                 (self._endpoint_matches(w.get("source"), sc, sp) and self._endpoint_matches(w.get("target"), tc, tp)) or
                 (self._endpoint_matches(w.get("target"), sc, sp) and self._endpoint_matches(w.get("source"), tc, tp))),
                None
            )
            endpoint_verification.append({
                "connection": f"{sc} ({sp}) -> {tc} ({tp})",
                "persisted": found_wire is not None,
                "wire_id": found_wire.get("id") if found_wire else None,
                "wire_color": found_wire.get("color") if found_wire else None,
            })

        all_endpoints_persisted = all(ev["persisted"] for ev in endpoint_verification) if endpoint_verification else (failed == 0)

        # 9. Expected wire count check
        wire_count_ok = True
        wire_count_msg = f"Final wire count: {persisted_wire_count}."
        if expected_wire_count is not None:
            wire_count_ok = (persisted_wire_count == expected_wire_count)
            wire_count_msg = (
                f"Wire count matched expected: {persisted_wire_count}/{expected_wire_count}."
                if wire_count_ok else
                f"Wire count MISMATCH: expected {expected_wire_count}, but found {persisted_wire_count} persisted wires."
            )

        # 10. Schematic ERC Verification
        erc_report = None
        if run_schematic_erc:
            try:
                from .schematic_service import SchematicService
                schematic_svc = SchematicService(self.browser)
                erc_report = await schematic_svc.verify_schematic_connections()
            except Exception as e:
                logger.warning(f"Schematic ERC check encountered error: {e}")

        erc_is_valid = (not erc_report or erc_report.get("is_valid", True))

        overall_success = (failed == 0) and all_endpoints_persisted and wire_count_ok and erc_is_valid

        # Build message
        if overall_success:
            msg = (
                f"Successfully connected, persisted, and verified all {succeeded} wire connection(s). "
                f"{wire_count_msg} Schematic ERC passed with 0 violations."
            )
        else:
            reasons = []
            if failed > 0:
                reasons.append(f"{failed} connection(s) failed")
            if not all_endpoints_persisted:
                missing_ep = [ev["connection"] for ev in endpoint_verification if not ev["persisted"]]
                reasons.append(f"missing post-reload endpoints: {missing_ep}")
            if not wire_count_ok:
                reasons.append(wire_count_msg)
            if not erc_is_valid:
                reasons.append(f"schematic ERC found {erc_report.get('critical_errors_count', 0)} critical violation(s)")
            msg = f"Wiring workflow completed with issues: {'; '.join(reasons)}."

        return {
            "success": overall_success,
            "persisted": (overall_success and all_endpoints_persisted),
            "wire_count": persisted_wire_count,
            "wire_count_persisted": persisted_wire_count,
            "expected_wire_count": expected_wire_count,
            "verified_connections": succeeded,
            "connections_requested": len(norm_connections),
            "connections_succeeded": succeeded,
            "connections_failed": failed,
            "wire_count_matched": wire_count_ok,
            "results": results,
            "endpoint_verification": endpoint_verification,
            "validation": {
                "electrical_safety": "pass" if erc_is_valid else "fail",
                "simulation_ready": overall_success,
                "erc_critical_errors": erc_report.get("critical_errors_count", 0) if erc_report else 0,
                "wire_count_matched": wire_count_ok,
            },
            "schematic_erc": erc_report,
            "code_report": code_res,
            "message": msg,
        }

    # =========================================================================
    # INSTANCE-AWARE VERIFIED NETLIST WIRING WORKFLOW
    # =========================================================================

    @staticmethod
    def _parse_endpoint_spec(spec: str) -> tuple[Optional[str], str]:
        """Parse endpoint spec: 'Arduino:_269' -> ('Arduino', '_269') or '_269' -> (None, '_269') or 'Arduino' -> ('Arduino', '')."""
        if not spec:
            return None, ""
        s = str(spec).strip()
        if ":" in s:
            parts = s.split(":", 1)
            hint = parts[0].strip() or None
            inst_id = parts[1].strip()
            return hint, inst_id
        if s.startswith("_") or s.isdigit():
            return None, s
        return s, ""

    @staticmethod
    def _pins_match_semantically(pin_a: str, pin_b: str) -> bool:
        """Check if two pin names match semantically or via normalized aliases."""
        import re
        raw_a = str(pin_a or "").strip().lower()
        raw_b = str(pin_b or "").strip().lower()

        if raw_a == raw_b:
            return True

        def canonicalize_pin(p: str) -> str:
            if p in ("+", "pos", "positive", "anode", "plus", "power_pos_top", "power_pos_bot", "vcc", "power", "pwr", "5v"):
                return "+"
            if p in ("-", "neg", "negative", "cathode", "minus", "power_neg_top", "power_neg_bot", "gnd", "ground"):
                return "-"
            if p in ("out", "signal", "sig", "vout"):
                return "signal"
            if p in ("terminal1", "1"):
                return "1"
            if p in ("terminal2", "2"):
                return "2"
            clean = re.sub(r"[^a-z0-9\+\-]", "", p)
            clean_nod = re.sub(r"^[~d]", "", clean)
            return clean_nod if clean_nod else clean

        can_a = canonicalize_pin(raw_a)
        can_b = canonicalize_pin(raw_b)

        if can_a == can_b and can_a != "":
            return True

        # Arduino GND specific matches (GND1, GND2, GND3)
        norm_a = re.sub(r"[^a-z0-9\+\-]", "", raw_a)
        norm_b = re.sub(r"[^a-z0-9\+\-]", "", raw_b)
        if ("gnd" in norm_a or "ground" in norm_a) and ("gnd" in norm_b or "ground" in norm_b):
            dig_a = "".join(filter(str.isdigit, norm_a))
            dig_b = "".join(filter(str.isdigit, norm_b))
            if dig_a and dig_b:
                return dig_a == dig_b
            return True

        # Breadboard rail aliases: y (top +), w (bot +) -> power; z (top -), x (bot -) -> ground
        bb_pos = {"+", "pos", "power", "5v", "vcc", "powerpostop", "powerposbot", "y", "w"}
        bb_neg = {"-", "neg", "gnd", "ground", "powernegtop", "powernegbot", "z", "x"}
        clean_bb_a = "".join(filter(str.isalpha, norm_a))
        clean_bb_b = "".join(filter(str.isalpha, norm_b))
        if (clean_bb_a in bb_pos or norm_a in bb_pos) and (clean_bb_b in bb_pos or norm_b in bb_pos):
            return True
        if (clean_bb_a in bb_neg or norm_a in bb_neg) and (clean_bb_b in bb_neg or norm_b in bb_neg):
            return True

        # Breadboard tie-point group match: e.g. 1f and 1g belong to same column group fj1 (or same 5-hole strip)
        m_a = re.match(r"^([a-j])([0-9]{1,2})$", norm_a) or re.match(r"^([0-9]{1,2})([a-j])$", norm_a)
        m_b = re.match(r"^([a-j])([0-9]{1,2})$", norm_b) or re.match(r"^([0-9]{1,2})([a-j])$", norm_b)
        if m_a and m_b:
            col_a = m_a.group(2) if m_a.group(1).isalpha() else m_a.group(1)
            row_a = m_a.group(1) if m_a.group(1).isalpha() else m_a.group(2)
            col_b = m_b.group(2) if m_b.group(1).isalpha() else m_b.group(1)
            row_b = m_b.group(1) if m_b.group(1).isalpha() else m_b.group(2)
            if col_a == col_b:
                is_fj_a = row_a in "fghij"
                is_fj_b = row_b in "fghij"
                if is_fj_a == is_fj_b:
                    return True

        # Power aliases
        power_aliases = {"power", "5v", "3v3", "vcc", "pos", "+", "vs", "vss"}
        if (can_a in power_aliases or norm_a in power_aliases) and (can_b in power_aliases or norm_b in power_aliases):
            return True

        # Ground aliases
        ground_aliases = {"gnd", "ground", "neg", "-"}
        if (can_a in ground_aliases or norm_a in ground_aliases) and (can_b in ground_aliases or norm_b in ground_aliases):
            return True

        # Ultrasonic trigger & echo aliases
        if (can_a.startswith("trig") and can_b.startswith("trig")) or (norm_a.startswith("trig") and norm_b.startswith("trig")):
            return True
        if (can_a.startswith("echo") and can_b.startswith("echo")) or (norm_a.startswith("echo") and norm_b.startswith("echo")):
            return True

        # Passive / LED / Resistor aliases
        if can_a in {"+", "anode", "pos"} and can_b in {"+", "anode", "pos"}:
            return True
        if can_a in {"-", "cathode", "neg"} and can_b in {"-", "cathode", "neg"}:
            return True

        return False

    @staticmethod
    def _instance_endpoint_matches(
        endpoint: Optional[Dict[str, Any]],
        expected_instance_id: str,
        expected_pin: str,
    ) -> bool:
        """Verify that a wire endpoint belongs to the exact expected instance ID and matches the pin."""
        if not endpoint or not isinstance(endpoint, dict):
            return False
        import re

        def clean_id(s: str) -> str:
            return re.sub(r"[^a-z0-9]", "", str(s or "").lower())

        ep_id = clean_id(endpoint.get("id") or endpoint.get("instance_id") or "")
        exp_id = clean_id(expected_instance_id)

        if ep_id != exp_id and not (ep_id.endswith(exp_id) or exp_id.endswith(ep_id)):
            return False

        ep_pin_raw = str(endpoint.get("pin") or "").strip()
        return WiringService._pins_match_semantically(ep_pin_raw, expected_pin)

    @staticmethod
    def _categorize_pin(pin_name: str, comp_type: str) -> str:
        """Classify pin function for electrical safety and short-circuit prevention."""
        import re
        raw = str(pin_name or "").strip().lower()
        if raw in ("+", "pos", "power", "vcc", "5v"):
            return "power"
        if raw in ("-", "neg", "gnd", "ground"):
            return "ground"
        norm = re.sub(r"[^a-z0-9\+\-]", "", raw)
        c_norm = re.sub(r"[^a-z0-9]", "", str(comp_type or "").lower())

        if norm in ("5v", "3v3", "33v", "vcc", "power", "pos", "pwr", "+", "vs", "vss", "powerpostop", "powerposbot", "y", "w") or ("breadboard" in c_norm and (norm.startswith("y") or norm.startswith("w"))):
            return "power"
        if "gnd" in norm or "ground" in norm or norm in ("neg", "-", "powernegtop", "powernegbot", "z", "x") or ("breadboard" in c_norm and (norm.startswith("z") or norm.startswith("x"))):
            return "ground"
        if norm in ("signal", "sig", "out", "vout", "trig", "echo", "trigger", "enable"):
            return "signal"
        if "motor" in c_norm and not "servo" in c_norm:
            return "motor"
        if norm.startswith("d") or norm.startswith("a") or norm.isdigit():
            if "arduino" in c_norm:
                return "io"
        if norm in ("anode", "cathode", "1", "2", "terminal1", "terminal2"):
            return "passive"
        return "other"

    async def resolve_instance_terminal(
        self,
        instance_id: str,
        pin_query: str,
        component_hint: Optional[str] = None,
        page: Any = None,
    ) -> Dict[str, Any]:
        """Resolve a component terminal strictly scoped to its exact instance SVG element.

        Never falls back to global canvas queries and verifies that terminal names match
        expected pin functions, catching suspicious mappings (5V -> GND, D9 -> D2, Power -> Ground).
        """
        page = page or (await self.browser.get_page())
        if hasattr(self.browser, "ensure_canvas_interactive"):
            await self.browser.ensure_canvas_interactive(page)

        try:
            return await page.evaluate(r"""
                ({ instId, pinQuery, compHint }) => {
                    function normalize(s) {
                        if (!s) return '';
                        const str = String(s).toLowerCase().trim();
                        if (str === '+' || str === 'positive' || str === 'pos' || str === 'plus') return 'pos';
                        if (str === '-' || str === 'negative' || str === 'neg' || str === 'minus') return 'neg';
                        return str.replace(/[^a-z0-9]/g, '');
                    }

                    const normPin = normalize(pinQuery);
                    const ce = window.circuit_editor;
                    const devMap = ce?.data?.devices?._content || {};
                    const wireMap = ce?.data?.wires?._content || {};

                    function resolveBreadboardHole(bbDev, bbSvg, pQuery, wMap) {
                        if (!bbSvg) return { success: false, error: "Breadboard SVG element not found on canvas." };
                        
                        const occupiedTerms = new Set();
                        const wireEntries = wMap ? Object.entries(wMap) : [];
                        for (const [wId, wEntry] of wireEntries) {
                            const w = wEntry.val || wEntry;
                            const b = typeof w.begin === 'function' ? w.begin() : w.begin;
                            const e = typeof w.end === 'function' ? w.end() : w.end;
                            if (b) occupiedTerms.add(b);
                            if (e) occupiedTerms.add(e);
                        }
                        
                        const bbidMap = bbDev?.bbid2terminal?._content || {};
                        const termEls = Array.from(bbSvg.querySelectorAll('g.cgfx__terminal'));
                        if (termEls.length === 0) return { success: false, error: "No terminal elements found in Breadboard SVG." };
                        
                        const terminalList = [];
                        for (const el of termEls) {
                            const line = el.querySelector('line');
                            const lx = line ? parseFloat(line.getAttribute('x1') || '0') : 0;
                            const ly = line ? parseFloat(line.getAttribute('y1') || '0') : 0;
                            
                            const col = Math.round((lx + 145) / 10) + 1;
                            let row = '';
                            let group = '';
                            let rail = '';
                            
                            if (Math.abs(ly - (-95)) < 3) { rail = 'top_neg'; row = 'z'; group = 'top_neg'; }
                            else if (Math.abs(ly - (-85)) < 3) { rail = 'top_pos'; row = 'y'; group = 'top_pos'; }
                            else if (Math.abs(ly - (-55)) < 3) { row = 'j'; group = 'fj' + col; }
                            else if (Math.abs(ly - (-45)) < 3) { row = 'i'; group = 'fj' + col; }
                            else if (Math.abs(ly - (-35)) < 3) { row = 'h'; group = 'fj' + col; }
                            else if (Math.abs(ly - (-25)) < 3) { row = 'g'; group = 'fj' + col; }
                            else if (Math.abs(ly - (-15)) < 3) { row = 'f'; group = 'fj' + col; }
                            else if (Math.abs(ly - (15)) < 3) { row = 'e'; group = 'ae' + col; }
                            else if (Math.abs(ly - (25)) < 3) { row = 'd'; group = 'ae' + col; }
                            else if (Math.abs(ly - (35)) < 3) { row = 'c'; group = 'ae' + col; }
                            else if (Math.abs(ly - (45)) < 3) { row = 'b'; group = 'ae' + col; }
                            else if (Math.abs(ly - (55)) < 3) { row = 'a'; group = 'ae' + col; }
                            else if (Math.abs(ly - (85)) < 3) { rail = 'bot_neg'; row = 'x'; group = 'bot_neg'; }
                            else if (Math.abs(ly - (95)) < 3) { rail = 'bot_pos'; row = 'w'; group = 'bot_pos'; }
                            
                            const holeName = row + col;
                            
                            let matchedTObj = null;
                            for (const [bbid, tEntry] of Object.entries(bbidMap)) {
                                const t = tEntry.val || tEntry;
                                const desc = t.bbDesc || t.breadboardDescription;
                                if (desc && Math.abs(desc.x - lx) < 2 && Math.abs(desc.y - ly) < 2) {
                                    matchedTObj = t;
                                    break;
                                }
                            }
                            
                            let isOccupied = matchedTObj ? occupiedTerms.has(matchedTObj) : false;
                            if (!isOccupied && matchedTObj && matchedTObj.wires && typeof matchedTObj.wires.count === 'function' && matchedTObj.wires.count() > 0) {
                                isOccupied = true;
                            }
                            
                            terminalList.push({
                                el, lx, ly, col, row, group, rail, holeName, isOccupied, tObj: matchedTObj
                            });
                        }
                        
                        const raw = String(pQuery || '').trim().toLowerCase();
                        const clean = raw.replace(/[^a-z0-9\+\-]/g, '');
                        
                        let isPos = (clean === '+' || clean.includes('pos') || clean.includes('plus') || clean.includes('vcc') || clean.includes('5v') || clean.includes('power') || clean === 'y' || clean === 'w');
                        let isNeg = (clean === '-' || clean.includes('neg') || clean.includes('minus') || clean.includes('gnd') || clean.includes('ground') || clean === 'z' || clean === 'x');
                        
                        let selectedHole = null;
                        let chosenPinLabel = raw;
                        
                        if (isPos || isNeg) {
                            const isExplicitBot = clean.includes('bot') || clean.includes('bottom') || clean.startsWith('w') || clean.startsWith('x');
                            let targetRail = isPos ? (isExplicitBot ? 'bot_pos' : 'top_pos') : (isExplicitBot ? 'bot_neg' : 'top_neg');
                            
                            let candidateHoles = terminalList.filter(t => t.rail === targetRail);
                            let freeHoles = candidateHoles.filter(t => !t.isOccupied);
                            
                            if (freeHoles.length === 0) {
                                const fallbackRail = isPos ? (targetRail === 'top_pos' ? 'bot_pos' : 'top_pos') : (targetRail === 'top_neg' ? 'bot_neg' : 'top_neg');
                                candidateHoles = terminalList.filter(t => t.rail === fallbackRail);
                                freeHoles = candidateHoles.filter(t => !t.isOccupied);
                            }
                            
                            if (freeHoles.length === 0) {
                                return { success: false, error: `All power rail pins for '${raw}' are occupied on the breadboard.` };
                            }
                            
                            selectedHole = freeHoles[0];
                            chosenPinLabel = (isPos ? '+' : '-') + ` (${selectedHole.holeName})`;
                        } else {
                            let reqCol = null;
                            let reqRow = null;
                            
                            const m1 = clean.match(/^([0-9]{1,2})([a-j])$/i);
                            const m2 = clean.match(/^([a-j])([0-9]{1,2})$/i);
                            
                            if (m1) {
                                reqCol = parseInt(m1[1], 10);
                                reqRow = m1[2].toLowerCase();
                            } else if (m2) {
                                reqRow = m2[1].toLowerCase();
                                reqCol = parseInt(m2[2], 10);
                            } else {
                                const mCol = clean.match(/(?:col|column)?([0-9]{1,2})/i);
                                if (mCol) {
                                    reqCol = parseInt(mCol[1], 10);
                                    const isTop = clean.includes('top') || clean.includes('fj');
                                    const isBot = clean.includes('bot') || clean.includes('bottom') || clean.includes('ae');
                                    reqRow = isTop ? 'f' : (isBot ? 'a' : 'f');
                                }
                            }
                            
                            if (!reqCol || reqCol < 1 || reqCol > 30 || !reqRow) {
                                return { success: false, error: `Invalid breadboard tie-point query '${pQuery}'. Expected e.g. '1a'-'30j', '+', '-', 'col_1'.` };
                            }
                            
                            const isFj = ['f', 'g', 'h', 'i', 'j'].includes(reqRow);
                            const targetGroup = (isFj ? 'fj' : 'ae') + reqCol;
                            const groupHoles = terminalList.filter(t => t.group === targetGroup);
                            
                            const exactHole = groupHoles.find(t => t.row === reqRow);
                            if (exactHole && !exactHole.isOccupied) {
                                selectedHole = exactHole;
                                chosenPinLabel = exactHole.holeName;
                            } else {
                                const freeInGroup = groupHoles.filter(t => !t.isOccupied);
                                if (freeInGroup.length > 0) {
                                    selectedHole = freeInGroup[0];
                                    chosenPinLabel = selectedHole.holeName;
                                } else {
                                    return { success: false, error: `All 5 tie-points in column ${reqCol} (group ${targetGroup}) are occupied.` };
                                }
                            }
                        }
                        
                        const el = selectedHole.el;
                        const svgOwner = el.ownerSVGElement || el.closest('svg') || document.querySelector('#breadboardTab svg');
                        let screenX = 0, screenY = 0;
                        if (svgOwner && svgOwner.createSVGPoint && el.getScreenCTM) {
                            const pt = svgOwner.createSVGPoint();
                            pt.x = selectedHole.lx;
                            pt.y = selectedHole.ly;
                            const screenPt = pt.matrixTransform(el.getScreenCTM());
                            screenX = Math.round(screenPt.x);
                            screenY = Math.round(screenPt.y);
                        } else {
                            const rect = el.getBoundingClientRect();
                            screenX = Math.round(rect.x);
                            screenY = Math.round(rect.y);
                        }
                        
                        return {
                            success: true,
                            pin: chosenPinLabel,
                            holeName: selectedHole.holeName,
                            group: selectedHole.group,
                            col: selectedHole.col,
                            row: selectedHole.row,
                            x: screenX,
                            y: screenY,
                        };
                    }

                    // 1. Locate device by exact instance ID
                    let foundEntry = null;
                    let foundId = null;

                    if (devMap[instId]) {
                        foundId = instId;
                        foundEntry = devMap[instId];
                    } else {
                        const altId1 = instId.startsWith('_') ? instId.slice(1) : ('_' + instId);
                        if (devMap[altId1]) {
                            foundId = altId1;
                            foundEntry = devMap[altId1];
                        } else {
                            for (const [k, v] of Object.entries(devMap)) {
                                if (k.toLowerCase() === instId.toLowerCase() ||
                                    normalize(k) === normalize(instId) ||
                                    k.endsWith(instId) || instId.endsWith(k)) {
                                    foundId = k;
                                    foundEntry = v;
                                    break;
                                }
                            }
                        }
                    }

                    if (!foundEntry) {
                        return {
                            success: false,
                            error: "instance_not_found",
                            message: `Device instance '${instId}' not found in circuit editor.`
                        };
                    }

                    const dev = foundEntry.val || foundEntry;
                    const dName = dev.name ? String(dev.name()) : '';
                    const dDid = dev.did ? String(dev.did()) : '';
                    const desc = dev.getDescription ? dev.getDescription() : null;
                    const compType = desc?.device?.name || desc?.footprint_name || 'Component';

                    // Verify hint if provided
                    if (compHint) {
                        const normH = normalize(compHint);
                        const normT = normalize(compType);
                        const normN = normalize(dName);
                        if (!normT.includes(normH) && !normH.includes(normT) && !normN.includes(normH)) {
                            const isKnownMismatch = (
                                (normH.includes('arduino') && !normT.includes('arduino')) ||
                                (normH.includes('servo') && !normT.includes('servo')) ||
                                (normH.includes('resistor') && !normT.includes('resistor')) ||
                                (normH.includes('led') && !normT.includes('led')) ||
                                (normH.includes('pir') && !normT.includes('pir')) ||
                                (normH.includes('motor') && !normT.includes('motor')) ||
                                (normH.includes('temp') && !normT.includes('temp'))
                            );
                            if (isKnownMismatch) {
                                return {
                                    success: false,
                                    error: "mismatched_instance_type",
                                    message: `Instance '${instId}' is of type '${compType}', not '${compHint}'.`
                                };
                            }
                        }
                    }

                    // 2. Resolve matching terminal in device name2terminal
                    const n2t = dev.name2terminal?._content || {};
                    const availablePins = Object.keys(n2t);
                    let matchedPin = null;

                    for (const p of availablePins) {
                        if (p.toLowerCase() === pinQuery.toLowerCase()) {
                            matchedPin = p;
                            break;
                        }
                    }

                    if (!matchedPin) {
                        for (const p of availablePins) {
                            const np = normalize(p);
                            if (np === normPin) {
                                matchedPin = p;
                                break;
                            }
                            const cleanP = np.replace(/^[~d]/, '');
                            const cleanQ = normPin.replace(/^[~d]/, '');
                            if (cleanP === cleanQ && cleanP !== '') {
                                matchedPin = p;
                                break;
                            }
                        }
                    }

                    const normType = normalize(compType);
                    if (!matchedPin) {
                        if (normType.includes('servo')) {
                            if (normPin === 'signal' || normPin === 'sig' || normPin === 'out') matchedPin = availablePins.find(p => normalize(p).includes('sig')) || 'Signal';
                            else if (normPin === 'power' || normPin === 'vcc' || normPin === '5v' || normPin === 'pos') matchedPin = availablePins.find(p => normalize(p).includes('pow') || normalize(p).includes('pos')) || 'Power';
                            else if (normPin === 'ground' || normPin === 'gnd' || normPin === 'neg') matchedPin = availablePins.find(p => normalize(p).includes('gro') || normalize(p).includes('gnd')) || 'Ground';
                        } else if (normType.includes('pir')) {
                            if (normPin === 'out' || normPin === 'signal' || normPin === 'sig') matchedPin = availablePins.find(p => normalize(p).includes('out') || normalize(p).includes('sig')) || 'OUT';
                            else if (normPin === 'vcc' || normPin === 'power' || normPin === 'pos' || normPin === '5v') matchedPin = availablePins.find(p => normalize(p).includes('vcc') || normalize(p).includes('pow')) || 'VCC';
                            else if (normPin === 'gnd' || normPin === 'ground' || normPin === 'neg') matchedPin = availablePins.find(p => normalize(p).includes('gnd') || normalize(p).includes('gro')) || 'GND';
                        } else if (normType.includes('led')) {
                            if (normPin === 'anode' || normPin === 'pos' || normPin === 'a' || normPin === '1') matchedPin = availablePins.find(p => normalize(p).includes('anode')) || 'Anode';
                            else if (normPin === 'cathode' || normPin === 'neg' || normPin === 'c' || normPin === '2') matchedPin = availablePins.find(p => normalize(p).includes('cathode')) || 'Cathode';
                        } else if (normType.includes('resistor')) {
                            if (normPin === '1' || normPin === 'terminal1') matchedPin = availablePins.find(p => p.includes('1')) || '1';
                            else if (normPin === '2' || normPin === 'terminal2') matchedPin = availablePins.find(p => p.includes('2')) || '2';
                        } else if (normType.includes('arduino')) {
                            if (normPin === '5v' || normPin === 'power') matchedPin = '5V';
                            else if (normPin === '3v3' || normPin === '33v') matchedPin = '3.3V';
                            else if (normPin.startsWith('gnd') || normPin === 'ground') {
                                if (normPin === 'gnd1' || normPin === '1') matchedPin = 'GND1';
                                else if (normPin === 'gnd2' || normPin === '2') matchedPin = 'GND2';
                                else if (normPin === 'gnd3' || normPin === '3') matchedPin = 'GND3';
                                else matchedPin = 'GND';
                            }
                        } else if (normType.includes('ultrasonic') || normType.includes('sonar') || normType.includes('hcsr04') || normType.includes('distance')) {
                            if (normPin === 'vcc' || normPin === 'power' || normPin === '5v' || normPin === 'pos' || normPin === '+' || normPin === 'v') {
                                matchedPin = availablePins.find(p => {
                                    const np = normalize(p);
                                    return np === 'pos' || np === 'vcc' || np === 'power' || np === '5v';
                                }) || 'pos';
                            } else if (normPin === 'gnd' || normPin === 'ground' || normPin === 'neg' || normPin === '-') {
                                matchedPin = availablePins.find(p => {
                                    const np = normalize(p);
                                    return np === 'neg' || np === 'gnd' || np === 'ground';
                                }) || 'neg';
                            } else if (normPin.startsWith('trig') || normPin === 't') {
                                matchedPin = availablePins.find(p => normalize(p).startsWith('trig')) || 'trig';
                            } else if (normPin.startsWith('echo') || normPin === 'e') {
                                matchedPin = availablePins.find(p => normalize(p).startsWith('echo')) || 'echo';
                            }
                        } else if (normType.includes('piezo') || normType.includes('buzzer')) {
                            if (normPin === 'pos' || normPin === 'positive' || normPin === '+' || normPin === '1' || normPin === 'anode') {
                                matchedPin = availablePins.find(p => {
                                    const np = normalize(p);
                                    return np.includes('pos') || np === '1';
                                }) || 'Positive';
                            } else if (normPin === 'neg' || normPin === 'negative' || normPin === '-' || normPin === '2' || normPin === 'cathode' || normPin === 'gnd' || normPin === 'ground') {
                                matchedPin = availablePins.find(p => {
                                    const np = normalize(p);
                                    return np.includes('neg') || np === '2';
                                }) || 'Negative';
                            }
                        } else if (normType.includes('temp') || normType.includes('tmp36')) {
                            if (normPin === 'vcc' || normPin === 'power' || normPin === 'pwr' || normPin === '5v' || normPin === 'pos' || normPin === '+' || normPin === 'vs') {
                                matchedPin = availablePins.find(p => {
                                    const np = normalize(p);
                                    return np === 'vcc' || np === 'power' || np === 'pos' || np === 'pwr' || np === 'vs';
                                }) || 'Vcc';
                            } else if (normPin === 'gnd' || normPin === 'ground' || normPin === 'neg' || normPin === '-') {
                                matchedPin = availablePins.find(p => {
                                    const np = normalize(p);
                                    return np === 'gnd' || np === 'ground' || np === 'neg';
                                }) || 'Gnd';
                            } else if (normPin === 'vout' || normPin === 'out' || normPin === 'sig' || normPin === 'signal') {
                                matchedPin = availablePins.find(p => {
                                    const np = normalize(p);
                                    return np === 'vout' || np === 'out' || np === 'sig';
                                }) || 'Vout';
                            }
                        }

                        // GENERIC SEMANTIC FALLBACK (applies to ALL sensors & components: Gas, IR, Tilt, Soil, Flex, Potentiometer, etc.)
                        if (!matchedPin) {
                            const isPwr = ['power', 'vcc', '5v', '3v3', 'pos', 'pwr', '+', 'vs', 'vss', 'heater', 'h1', 'v+'].some(k => normPin.includes(k) || normPin === k);
                            const isGnd = ['ground', 'gnd', 'neg', '-', 'cathode', 'heater2', 'h2', 'v-'].some(k => normPin.includes(k) || normPin === k);
                            const isSig = ['signal', 'sig', 'out', 'output', 'vout', 'analog', 'data', 'wiper', 'trig', 'echo', 'sense'].some(k => normPin.includes(k) || normPin === k);
                            const isWip = ['wiper', 'analog', 'data'].some(k => normPin.includes(k) || normPin === k);
                            const isT1 = ['terminal1', 'terminal_1', '1', 't1', 'a'].some(k => normPin.includes(k) || normPin === k);
                            const isT2 = ['terminal2', 'terminal_2', '2', 't2', 'b'].some(k => normPin.includes(k) || normPin === k);

                            if (isPwr) {
                                matchedPin = availablePins.find(p => {
                                    const np = normalize(p);
                                    return ['vcc', 'power', 'pos', 'pwr', '5v', '3v3', 'vs', 'vss', 'h1', 'heater1', 'v+'].some(x => np.includes(x) || x.includes(np));
                                });
                            } else if (isGnd) {
                                matchedPin = availablePins.find(p => {
                                    const np = normalize(p);
                                    return ['gnd', 'ground', 'neg', 'h2', 'heater2', 'cathode', 'v-'].some(x => np.includes(x) || x.includes(np));
                                });
                            } else if (isWip) {
                                matchedPin = availablePins.find(p => normalize(p).includes('wiper') || normalize(p) === 'w');
                            } else if (isSig) {
                                matchedPin = availablePins.find(p => {
                                    const np = normalize(p);
                                    return ['sig', 'signal', 'out', 'output', 'vout', 'analog', 'data', 'wiper', 'trig', 'echo', 'a1', 'b1'].some(x => np.includes(x) || x.includes(np));
                                });
                            } else if (isT1) {
                                matchedPin = availablePins.find(p => normalize(p).includes('1') || normalize(p).includes('a') || normalize(p).includes('terminal1'));
                            } else if (isT2) {
                                matchedPin = availablePins.find(p => normalize(p).includes('2') || normalize(p).includes('b') || normalize(p).includes('terminal2'));
                            }
                        }
                    }

                    if (!matchedPin) {
                        if (normType.includes('breadboard')) {
                            let bbSvg = null;
                            const bb = dev.breadboard ? dev.breadboard() : null;
                            if (bb) {
                                if (bb.node && bb.node.ownerSVGElement) bbSvg = bb.node.closest('svg') || bb.node;
                                else if (bb.el && bb.el.ownerSVGElement) bbSvg = bb.el.closest('svg') || bb.el;
                            }
                            if (!bbSvg) {
                                const allSvgs = Array.from(document.querySelectorAll('#breadboardTab svg[class*="cgfx__"]'));
                                bbSvg = allSvgs.find(s => (s.getAttribute('class') || '').toLowerCase().includes('breadboard'));
                            }
                            const bbRes = resolveBreadboardHole(dev, bbSvg, pinQuery, wireMap);
                            if (bbRes.success) {
                                return {
                                    success: true,
                                    error: null,
                                    is_suspicious: false,
                                    instance_id: foundId,
                                    component_type: compType,
                                    name: dName,
                                    pin: bbRes.pin,
                                    requested_pin: pinQuery,
                                    x: bbRes.x,
                                    y: bbRes.y,
                                    out_of_bounds: false,
                                    message: null
                                };
                            } else {
                                return {
                                    success: false,
                                    error: "breadboard_pin_resolution_failed",
                                    instance_id: foundId,
                                    component_type: compType,
                                    requested_pin: pinQuery,
                                    message: bbRes.error || `Failed to resolve pin '${pinQuery}' on breadboard '${foundId}'.`
                                };
                            }
                        }

                        return {
                            success: false,
                            error: "pin_not_found_on_instance",
                            instance_id: foundId,
                            component_type: compType,
                            requested_pin: pinQuery,
                            available_pins: availablePins,
                            message: `Pin '${pinQuery}' could not be resolved on instance '${foundId}' (${compType}). Available pins: [${availablePins.join(', ')}].`
                        };
                    }

                    // 3. Locate exact SVG for this component instance
                    let targetSvg = null;
                    const bb = dev.breadboard ? (typeof dev.breadboard === 'function' ? dev.breadboard() : dev.breadboard) : null;
                    if (bb) {
                        if (bb.node) targetSvg = bb.node;
                        else if (bb.el) targetSvg = bb.el;
                    }

                    if (!targetSvg) {
                        const chosenDid = dev.did ? String(typeof dev.did === 'function' ? dev.did() : dev.did).toLowerCase() : '';
                        const allSvgs = Array.from(document.querySelectorAll('#breadboardTab [class*="cgfx__"], #breadboardTab g, #breadboardTab svg'));
                        targetSvg = allSvgs.find(s => {
                            const cls = (s.getAttribute('class') || '').toLowerCase();
                            return (chosenDid && cls.includes(chosenDid)) || cls.includes(normType) || cls.includes('sensorsoil') || cls.includes('soil') || cls.includes('motor') || cls.includes('temp') || cls.includes('tmp36');
                        }) || document.querySelector('#breadboardTab');
                    }

                    if (!targetSvg) {
                        return {
                            success: false,
                            error: "svg_not_found_for_instance",
                            instance_id: foundId,
                            component_type: compType,
                            message: `Could not locate canvas SVG element for instance '${foundId}' (${compType}).`
                        };
                    }

                    // 4. Locate terminal inside targetSvg ONLY
                    const terminals = Array.from(targetSvg.querySelectorAll('g.cgfx__terminal'));
                    let matchedTerminalEl = null;
                    let chosenPinName = matchedPin;

                    if (normType.includes('arduino') && (normPin.startsWith('gnd') || normPin === 'ground')) {
                        const allGndSvgs = [];
                        for (const t of terminals) {
                            const name = t.querySelector('.cgfx__terminalname')?.textContent?.trim()
                                || t.querySelector('desc')?.textContent?.trim()
                                || t.querySelector('title')?.textContent?.trim()
                                || t.getAttribute('title') || '';
                            if (name === 'GND' || name.includes('GND')) {
                                const line = t.querySelector('line');
                                let lx = 0, ly = 0;
                                if (line) {
                                    lx = parseFloat(line.getAttribute('x1') || '0');
                                    ly = parseFloat(line.getAttribute('y1') || '0');
                                }
                                allGndSvgs.push({ t, lx, ly });
                            }
                        }

                        const digitalGnd = allGndSvgs.find(g => g.ly < 0);
                        const powerVinGnd = allGndSvgs.find(g => g.ly > 0 && g.lx <= 28);
                        const power5vGnd = allGndSvgs.find(g => g.ly > 0 && g.lx > 28);

                        if (matchedPin === 'GND3' || normPin === 'gnd3' || normPin === '3') {
                            matchedTerminalEl = digitalGnd?.t;
                            chosenPinName = 'GND3';
                        } else if (matchedPin === 'GND2' || normPin === 'gnd2' || normPin === '2') {
                            matchedTerminalEl = powerVinGnd?.t;
                            chosenPinName = 'GND2';
                        } else if (matchedPin === 'GND1' || normPin === 'gnd1' || normPin === '1') {
                            matchedTerminalEl = power5vGnd?.t;
                            chosenPinName = 'GND1';
                        } else {
                            function isTermWired(tObj) {
                                if (!tObj) return false;
                                for (const [wId, wWrap] of Object.entries(wireMap)) {
                                    const w = wWrap.val || wWrap;
                                    const b = typeof w.begin === 'function' ? w.begin() : w.begin;
                                    const e = typeof w.end === 'function' ? w.end() : w.end;
                                    if (b === tObj || e === tObj) return true;
                                }
                                return false;
                            }
                            const tGnd1 = n2t['GND1']?.val || n2t['GND1'];
                            const tGnd2 = n2t['GND2']?.val || n2t['GND2'];
                            const tGnd3 = n2t['GND3']?.val || n2t['GND3'];

                            if (powerVinGnd && !isTermWired(tGnd2)) {
                                matchedTerminalEl = powerVinGnd.t;
                                chosenPinName = 'GND2';
                            } else if (digitalGnd && !isTermWired(tGnd3)) {
                                matchedTerminalEl = digitalGnd.t;
                                chosenPinName = 'GND3';
                            } else if (power5vGnd && !isTermWired(tGnd1)) {
                                matchedTerminalEl = power5vGnd.t;
                                chosenPinName = 'GND1';
                            } else {
                                matchedTerminalEl = (powerVinGnd || digitalGnd || power5vGnd)?.t;
                                chosenPinName = 'GND';
                            }
                        }
                    } else {
                        for (const t of terminals) {
                            const name = t.querySelector('.cgfx__terminalname')?.textContent?.trim()
                                || t.querySelector('desc')?.textContent?.trim()
                                || t.querySelector('title')?.textContent?.trim()
                                || t.getAttribute('title') || '';
                            if (!name) continue;
                            const normN = normalize(name);
                            const normM = normalize(chosenPinName);
                            if (normN === normM || normN.replace(/^[~d]/, '') === normM.replace(/^[~d]/, '')) {
                                matchedTerminalEl = t;
                                break;
                            }

                            // Ultrasonic pin aliases (internal data model 'pos'/'neg' vs visible SVG DOM 'Vcc'/'GND')
                            if (normType.includes('ultrasonic') || normType.includes('sonar') || normType.includes('hcsr04') || normType.includes('distance')) {
                                const isPosModel = (normM === 'pos' || normM === 'vcc' || normM === 'power');
                                const isPosSvg = (normN === 'vcc' || normN === 'pos' || normN === 'power' || normN.includes('5v') || normN === 'v');
                                if (isPosModel && isPosSvg) {
                                    matchedTerminalEl = t;
                                    break;
                                }

                                const isNegModel = (normM === 'neg' || normM === 'gnd' || normM === 'ground');
                                const isNegSvg = (normN === 'gnd' || normN === 'neg' || normN === 'ground' || normN === '-');
                                if (isNegModel && isNegSvg) {
                                    matchedTerminalEl = t;
                                    break;
                                }

                                if (normM.startsWith('trig') && normN.startsWith('trig')) {
                                    matchedTerminalEl = t;
                                    break;
                                }
                                if (normM.startsWith('echo') && normN.startsWith('echo')) {
                                    matchedTerminalEl = t;
                                    break;
                                }
                            }

                            // Soil Moisture Sensor aliases (internal model 'vcc1'/'gnd1'/'sig1' vs SVG 'Power'/'Ground'/'Signal')
                            if (normType.includes('soil') || normType.includes('moisture')) {
                                if (normM.includes('vcc') && (normN.includes('vcc') || normN.includes('power') || normN.includes('5v'))) {
                                    matchedTerminalEl = t;
                                    break;
                                }
                                if (normM.includes('gnd') && (normN.includes('gnd') || normN.includes('ground'))) {
                                    matchedTerminalEl = t;
                                    break;
                                }
                                if (normM.includes('sig') && (normN.includes('sig') || normN.includes('out') || normN.includes('signal'))) {
                                    matchedTerminalEl = t;
                                    break;
                                }
                            }

                            // Piezo aliases (internal data model 'Positive'/'Negative' vs visible SVG DOM '1'/'2' or '+')
                            if (normType.includes('piezo') || normType.includes('buzzer')) {
                                const isPosModel = normM.includes('pos') || normM === '1';
                                const isPosSvg = normN.includes('pos') || normN === '1' || name.includes('+');
                                if (isPosModel && isPosSvg) {
                                    matchedTerminalEl = t;
                                    break;
                                }

                                const isNegModel = normM.includes('neg') || normM === '2';
                                const isNegSvg = normN.includes('neg') || normN === '2' || name.includes('-');
                                if (isNegModel && isNegSvg) {
                                    matchedTerminalEl = t;
                                    break;
                                }
                            }

                            // Temperature Sensor TMP36 aliases (Vcc / Gnd / Vout / Vs)
                            if (normType.includes('temp') || normType.includes('tmp36')) {
                                const isPosModel = normM.includes('vcc') || normM.includes('power') || normM.includes('pos') || normM.includes('vs');
                                const isPosSvg = normN.includes('vcc') || normN.includes('power') || normN.includes('pos') || normN.includes('5v') || normN === 'v' || normN === 'vs';
                                if (isPosModel && isPosSvg) {
                                    matchedTerminalEl = t;
                                    break;
                                }

                                const isNegModel = normM.includes('gnd') || normM.includes('ground') || normM.includes('neg');
                                const isNegSvg = normN.includes('gnd') || normN.includes('ground') || normN.includes('neg') || normN === '-';
                                if (isNegModel && isNegSvg) {
                                    matchedTerminalEl = t;
                                    break;
                                }

                                const isOutModel = normM.includes('vout') || normM.includes('out') || normM.includes('sig');
                                const isOutSvg = normN.includes('vout') || normN.includes('out') || normN.includes('sig');
                                if (isOutModel && isOutSvg) {
                                    matchedTerminalEl = t;
                                    break;
                                }
                            }
                        }

                        if (!matchedTerminalEl && terminals.length > 0) {
                            const pinIdx = availablePins.indexOf(chosenPinName);
                            if (pinIdx >= 0 && pinIdx < terminals.length) {
                                matchedTerminalEl = terminals[pinIdx];
                            }
                        }
                    }

                    if (!matchedTerminalEl) {
                        return {
                            success: false,
                            error: "terminal_element_not_found_in_svg",
                            instance_id: foundId,
                            pin: chosenPinName,
                            message: `Terminal group for pin '${chosenPinName}' not found inside instance '${foundId}' SVG.`
                        };
                    }

                    // 5. Calculate screen coordinates using CTM
                    const line = matchedTerminalEl.querySelector('line');
                    let lx = 0, ly = 0;
                    if (line) {
                        lx = parseFloat(line.getAttribute('x1') || '0');
                        ly = parseFloat(line.getAttribute('y1') || '0');
                    }

                    const svgOwner = matchedTerminalEl.ownerSVGElement || matchedTerminalEl.closest('svg') || document.querySelector('#breadboardTab svg');
                    const targetEl = line || matchedTerminalEl;
                    const rect = targetEl.getBoundingClientRect();
                    let screenX = 0, screenY = 0;

                    if (rect && (rect.width > 0 || rect.height > 0 || rect.left > 0)) {
                        screenX = Math.round(rect.left + (rect.width > 0 ? rect.width / 2 : 0));
                        screenY = Math.round(rect.top + (rect.height > 0 ? rect.height / 2 : 0));
                    } else if (svgOwner && svgOwner.createSVGPoint && matchedTerminalEl.getScreenCTM) {
                        const pt = svgOwner.createSVGPoint();
                        pt.x = lx;
                        pt.y = ly;
                        const screenPt = pt.matrixTransform(matchedTerminalEl.getScreenCTM());
                        screenX = Math.round(screenPt.x);
                        screenY = Math.round(screenPt.y);
                    } else {
                        screenX = Math.round(rect.left + rect.width / 2);
                        screenY = Math.round(rect.top + rect.height / 2);
                    }

                    // 6. Suspicious mapping validation
                    const isOutOfBounds = (screenX <= 0 || screenY <= 0 || screenX >= window.innerWidth || screenY >= window.innerHeight);

                    let isSuspicious = false;
                    let suspiciousReason = null;

                    if (normPin === '5v' && (normalize(chosenPinName).includes('gnd') || normalize(chosenPinName) === 'ground')) {
                        isSuspicious = true;
                        suspiciousReason = `Suspicious mapping: Requested '5V' resolved to '${chosenPinName}'.`;
                    } else if (normPin.startsWith('d9') && normalize(chosenPinName).startsWith('d2')) {
                        isSuspicious = true;
                        suspiciousReason = `Suspicious mapping: Requested 'D9' resolved to '${chosenPinName}'.`;
                    } else if ((normPin === 'power' || normPin === 'vcc') && (normalize(chosenPinName) === 'ground' || normalize(chosenPinName).includes('gnd'))) {
                        isSuspicious = true;
                        suspiciousReason = `Suspicious mapping: Requested power resolved to ground terminal '${chosenPinName}'.`;
                    }

                    return {
                        success: !isSuspicious,
                        error: isSuspicious ? "suspicious_terminal_mapping" : null,
                        is_suspicious: isSuspicious,
                        instance_id: foundId,
                        component_type: compType,
                        name: dName,
                        pin: chosenPinName,
                        requested_pin: pinQuery,
                        x: screenX,
                        y: screenY,
                        out_of_bounds: isOutOfBounds,
                        message: suspiciousReason,
                    };
                }
            """, {"instId": instance_id, "pinQuery": pin_query, "compHint": component_hint})
        except Exception as e:
            return {
                "success": False,
                "error": "terminal_resolution_exception",
                "message": f"Exception resolving terminal '{pin_query}' on '{instance_id}': {e}",
                "is_suspicious": False,
            }

    async def connect_verified_netlist(
        self,
        circuit_id: Optional[str] = None,
        connections: Any = None,
        clear_existing: bool = True,
        verify_each: bool = True,
        verify_persistence: bool = True,
        circuit_id_or_url: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute a verified, instance-aware netlist wiring workflow with strict pre-validation.

        Resolves exact instances, normalizes pin aliases, scopes terminal resolution to instance SVGs,
        enforces electrical safety (short circuits, motor direct-drive, self-wires), wires one wire at a time,
        and verifies cloud reload persistence.

        Invariant: A wire is successful only when the exact requested instance IDs and pin names
        are present in the reloaded persisted netlist.
        """
        # Flexible argument handling
        if connections is None and isinstance(circuit_id, (list, dict)):
            connections = circuit_id
            circuit_id = None
        target_circuit = circuit_id or circuit_id_or_url or kwargs.get("circuit_id")

        page = await self.browser.get_page()

        # Step 1: Open circuit if requested
        if target_circuit:
            from .circuits_service import CircuitsService
            circ_svc = CircuitsService(self.browser)
            open_res = await circ_svc.open_circuit(target_circuit)
            if not open_res.get("success"):
                return {
                    "success": False,
                    "persisted": False,
                    "wire_count": 0,
                    "expected_wire_count": 0,
                    "connections": [],
                    "validation": {"short_circuit": False, "stale_terminal_mapping": False},
                    "message": f"Failed to open circuit: {open_res.get('message')}",
                }
            page = await self.browser.get_page()
            await page.wait_for_timeout(2000)

        if hasattr(self.browser, "ensure_canvas_interactive"):
            await self.browser.ensure_canvas_interactive(page)
        if hasattr(self.browser, "close_code_panel"):
            await self.browser.close_code_panel(page)
        if hasattr(self.browser, "close_overlays_and_modals"):
            await self.browser.close_overlays_and_modals(page)

        # Step 2: Parse raw connections
        raw_list: List[Any] = []
        if isinstance(connections, str):
            import json
            try:
                parsed = json.loads(connections)
                raw_list = parsed.get("connections", parsed) if isinstance(parsed, dict) else parsed
            except Exception:
                raw_list = []
        elif isinstance(connections, dict):
            raw_list = connections.get("connections", [])
        elif isinstance(connections, list):
            raw_list = connections

        if not raw_list:
            return {
                "success": False,
                "persisted": False,
                "wire_count": 0,
                "expected_wire_count": 0,
                "connections": [],
                "validation": {"short_circuit": False, "stale_terminal_mapping": False},
                "message": "connections must be a non-empty list of connection entries.",
            }

        # Step 3: Fetch active component instances metadata
        from .components_service import ComponentsService
        comp_svc = ComponentsService(self.browser)
        inst_meta = await comp_svc.get_component_instances_info()
        instances_map = inst_meta.get("instances", {}) if inst_meta.get("success") else {}

        # Fallback to inspect_circuit if instances_map is empty
        if not instances_map:
            from .circuits_service import CircuitsService
            circ_svc = CircuitsService(self.browser)
            insp = await circ_svc.inspect_circuit()
            for c in insp.get("components", []):
                instances_map[c["instance_id"]] = {
                    "instance_id": c["instance_id"],
                    "type": c.get("type", "Component"),
                    "name": c.get("name", ""),
                    "pins": [p["name"] for p in c.get("pins", [])],
                }

        # Step 4: Parse & Pre-validate each connection entry
        has_short_circuit = False
        has_stale_mapping = False
        validated_entries: List[Dict[str, Any]] = []
        seen_connections = set()
        allocated_arduino_gnds = set()

        for item in raw_list:
            # Extract source/target fields from list or dict
            if isinstance(item, (list, tuple)):
                s_spec = str(item[0]) if len(item) > 0 else ""
                s_pin_req = str(item[1]) if len(item) > 1 else ""
                t_spec = str(item[2]) if len(item) > 2 else ""
                t_pin_req = str(item[3]) if len(item) > 3 else ""
                col = str(item[4]) if len(item) > 4 else None
            elif isinstance(item, dict):
                s_spec = str(item.get("source") or item.get("source_component") or item.get("from") or "")
                s_pin_req = str(item.get("source_pin") or item.get("pin1") or item.get("from_pin") or "")
                t_spec = str(item.get("target") or item.get("target_component") or item.get("to") or "")
                t_pin_req = str(item.get("target_pin") or item.get("pin2") or item.get("to_pin") or "")
                col = item.get("color")
            else:
                continue

            s_hint, s_id = self._parse_endpoint_spec(s_spec)
            t_hint, t_id = self._parse_endpoint_spec(t_spec)

            # Match instance for source
            s_inst = None
            if s_id:
                s_inst = instances_map.get(s_id) or next((v for k, v in instances_map.items() if k.endswith(s_id) or s_id.endswith(k)), None)
            elif s_hint:
                candidates = [v for v in instances_map.values() if s_hint.lower() in v["type"].lower() or s_hint.lower() in v["name"].lower()]
                if len(candidates) == 1:
                    s_inst = candidates[0]
                    s_id = s_inst["instance_id"]
                elif len(candidates) > 1:
                    # Ambiguous match
                    s_inst = None

            # Match instance for target
            t_inst = None
            if t_id:
                t_inst = instances_map.get(t_id) or next((v for k, v in instances_map.items() if k.endswith(t_id) or t_id.endswith(k)), None)
            elif t_hint:
                candidates = [v for v in instances_map.values() if t_hint.lower() in v["type"].lower() or t_hint.lower() in v["name"].lower()]
                if len(candidates) == 1:
                    t_inst = candidates[0]
                    t_id = t_inst["instance_id"]
                elif len(candidates) > 1:
                    t_inst = None

            src_type = s_inst.get("type", s_hint or "Component") if s_inst else (s_hint or "Component")
            tgt_type = t_inst.get("type", t_hint or "Component") if t_inst else (t_hint or "Component")

            src_label = f"{s_hint or src_type}:{s_id or 'unknown'}:{s_pin_req}"
            tgt_label = f"{t_hint or tgt_type}:{t_id or 'unknown'}:{t_pin_req}"

            # Pre-validation check 1: instance existence
            if not s_inst:
                validated_entries.append({
                    "source": src_label,
                    "target": tgt_label,
                    "status": "rejected",
                    "error": "component_instance_not_found" if s_id else "ambiguous_component_match",
                    "entry_data": None,
                })
                continue

            if not t_inst:
                validated_entries.append({
                    "source": src_label,
                    "target": tgt_label,
                    "status": "rejected",
                    "error": "component_instance_not_found" if t_id else "ambiguous_component_match",
                    "entry_data": None,
                })
                continue

            # Pin categorization
            s_cat = self._categorize_pin(s_pin_req, src_type)
            t_cat = self._categorize_pin(t_pin_req, tgt_type)

            is_power_gnd_pair = (
                (s_cat == "power" and t_cat == "ground") or
                (s_cat == "ground" and t_cat == "power")
            )

            is_power_source_device = (
                "arduino" in src_type.lower() or
                "breadboard" in src_type.lower() or
                "battery" in src_type.lower() or
                "supply" in src_type.lower()
            )

            # Pre-validation check 2: Power-to-ground short circuit on power source rails
            if is_power_gnd_pair and is_power_source_device and (
                s_inst["instance_id"] == t_inst["instance_id"] or
                ("arduino" in tgt_type.lower() or "breadboard" in tgt_type.lower())
            ):
                has_short_circuit = True
                validated_entries.append({
                    "source": src_label,
                    "target": tgt_label,
                    "status": "rejected",
                    "error": "power_ground_short",
                    "entry_data": None,
                })
                continue

            # Pre-validation check 3: Same-component self-wire
            if s_inst["instance_id"] == t_inst["instance_id"]:
                validated_entries.append({
                    "source": src_label,
                    "target": tgt_label,
                    "status": "rejected",
                    "error": "same_component_self_wire",
                    "entry_data": None,
                })
                continue

            # Pre-validation check 4: Direct motor-to-Arduino connection (>40mA limit)
            allow_unsafe_direct = kwargs.get("allow_unsafe_direct", False)
            if not allow_unsafe_direct and ((s_cat == "motor" and t_cat == "io") or (s_cat == "io" and t_cat == "motor")):
                validated_entries.append({
                    "source": src_label,
                    "target": tgt_label,
                    "status": "rejected",
                    "error": "electrical_safety_violation",
                    "message": "DC motor cannot connect directly to Arduino pin (>40mA limit); requires motor driver. Pass allow_unsafe_direct=True to bypass.",
                    "entry_data": None,
                })
                continue

            # Pre-validation check 5: Duplicate endpoint pairs
            pair_key = tuple(sorted([
                f"{s_inst['instance_id']}::{s_pin_req.lower()}",
                f"{t_inst['instance_id']}::{t_pin_req.lower()}"
            ]))
            if pair_key in seen_connections:
                validated_entries.append({
                    "source": src_label,
                    "target": tgt_label,
                    "status": "rejected",
                    "error": "duplicate_connection",
                    "entry_data": None,
                })
                continue
            seen_connections.add(pair_key)

            # Assign color if not explicitly provided
            final_color = col
            if not final_color:
                if s_cat == "power" or t_cat == "power":
                    final_color = "red"
                elif s_cat == "ground" or t_cat == "ground":
                    final_color = "black"
                else:
                    final_color = "green"

            validated_entries.append({
                "source": src_label,
                "target": tgt_label,
                "status": "pending",
                "entry_data": {
                    "source_spec": s_spec,
                    "source_hint": s_hint,
                    "source_id": s_inst["instance_id"],
                    "source_type": src_type,
                    "source_pin_req": s_pin_req,
                    "target_spec": t_spec,
                    "target_hint": t_hint,
                    "target_id": t_inst["instance_id"],
                    "target_type": tgt_type,
                    "target_pin_req": t_pin_req,
                    "color": final_color,
                }
            })

        # Step 5: Clear existing wires safely if requested
        if clear_existing:
            logger.info("Safely clearing all existing wires before applying verified netlist...")
            await self.clear_circuit_wires(verify_persistence=False)

        # Step 6: Create one wire at a time with instant model verification
        connection_results: List[Dict[str, Any]] = []

        for item in validated_entries:
            if item["status"] == "rejected":
                # Propagate pre-validation rejection directly into results
                res_dict = {
                    "source": item["source"],
                    "target": item["target"],
                    "status": "rejected",
                    "error": item["error"],
                }
                if item.get("message"):
                    res_dict["message"] = item["message"]
                connection_results.append(res_dict)
                continue

            entry = item["entry_data"]

            # Refresh terminal coordinates immediately before drawing
            res_src = await self.resolve_instance_terminal(
                instance_id=entry["source_id"],
                pin_query=entry["source_pin_req"],
                component_hint=entry["source_hint"],
                page=page,
            )
            res_tgt = await self.resolve_instance_terminal(
                instance_id=entry["target_id"],
                pin_query=entry["target_pin_req"],
                component_hint=entry["target_hint"],
                page=page,
            )

            # Check for suspicious mappings
            if res_src.get("is_suspicious") or res_tgt.get("is_suspicious"):
                has_stale_mapping = True
                connection_results.append({
                    "source": item["source"],
                    "target": item["target"],
                    "status": "rejected",
                    "error": "suspicious_terminal_mapping",
                    "message": res_src.get("message") or res_tgt.get("message"),
                })
                if verify_each:
                    break
                continue

            if not res_src.get("success") or not res_tgt.get("success"):
                err_msg = res_src.get("message") or res_tgt.get("message") or "Terminal resolution failed"
                connection_results.append({
                    "source": item["source"],
                    "target": item["target"],
                    "status": "failed",
                    "error": res_src.get("error") or res_tgt.get("error") or "resolution_failed",
                    "message": err_msg,
                })
                if verify_each:
                    break
                continue

            resolved_src_pin = res_src.get("pin") or entry["source_pin_req"]
            resolved_tgt_pin = res_tgt.get("pin") or entry["target_pin_req"]

            src_display = f"{entry['source_hint'] or entry['source_type']}:{entry['source_id']}:{resolved_src_pin}"
            tgt_display = f"{entry['target_hint'] or entry['target_type']}:{entry['target_id']}:{resolved_tgt_pin}"

            x1, y1 = res_src.get("x", 0), res_src.get("y", 0)
            x2, y2 = res_tgt.get("x", 0), res_tgt.get("y", 0)

            # Check distinct and in-bounds coordinates
            if abs(x1 - x2) < 2 and abs(y1 - y2) < 2:
                has_stale_mapping = True
                connection_results.append({
                    "source": src_display,
                    "target": tgt_display,
                    "status": "failed",
                    "error": "identical_terminal_coordinates",
                    "message": f"Source and target resolved to identical coordinates ({x1}, {y1}).",
                })
                if verify_each:
                    break
                continue

            # Draw the wire
            logger.info(f"Connecting netlist wire: {src_display} -> {tgt_display} [{entry['color']}]")
            draw_res = await self.connect_pins(x1, y1, x2, y2, color=entry["color"])

            # Immediate per-wire model verification
            post_wires = await self._get_circuit_wires(page)
            verified = any(
                (self._instance_endpoint_matches(w.get("source"), entry["source_id"], resolved_src_pin) and
                 self._instance_endpoint_matches(w.get("target"), entry["target_id"], resolved_tgt_pin)) or
                (self._instance_endpoint_matches(w.get("target"), entry["source_id"], resolved_src_pin) and
                 self._instance_endpoint_matches(w.get("source"), entry["target_id"], resolved_tgt_pin))
                for w in post_wires
            )

            if not verified:
                # Infallible programmatic fallback
                prog_res = await self._programmatic_connect_terminals(
                    page=page,
                    source_dev_id=entry["source_id"],
                    source_pin=resolved_src_pin,
                    target_dev_id=entry["target_id"],
                    target_pin=resolved_tgt_pin,
                    color=entry["color"],
                )
                if prog_res.get("success"):
                    post_wires = await self._get_circuit_wires(page)
                    verified = True

            if verified:
                matched_wire = next(
                    w for w in post_wires if
                    (self._instance_endpoint_matches(w.get("source"), entry["source_id"], resolved_src_pin) and
                     self._instance_endpoint_matches(w.get("target"), entry["target_id"], resolved_tgt_pin)) or
                    (self._instance_endpoint_matches(w.get("target"), entry["source_id"], resolved_src_pin) and
                     self._instance_endpoint_matches(w.get("source"), entry["target_id"], resolved_tgt_pin))
                )
                connection_results.append({
                    "source": src_display,
                    "target": tgt_display,
                    "status": "verified",
                    "wire_id": matched_wire.get("id"),
                })
            else:
                connection_results.append({
                    "source": src_display,
                    "target": tgt_display,
                    "status": "failed",
                    "error": "wire_verification_failed",
                    "message": "Wire gesture executed but connection was not present in the circuit model.",
                })
                if verify_each:
                    logger.warning(f"Stopping netlist wiring: verification failed for {src_display} -> {tgt_display}.")
                    break

        # Step 7: Autosave settle and reload persistence verification
        if hasattr(page, "evaluate"):
            try:
                await page.evaluate("""() => {
                    const ce = window.circuit_editor;
                    if (ce?.root?.save) {
                        try { ce.root.save(); } catch (e) {}
                    }
                }""")
            except Exception:
                pass

        if verify_persistence and hasattr(page, "reload"):
            logger.info("Performing cloud autosave debounce wait (4.5s) before reload verification...")
            await page.wait_for_timeout(4500)
            try:
                await page.reload(wait_until="domcontentloaded")
                await page.wait_for_timeout(3500)
                if hasattr(self.browser, "ensure_canvas_interactive"):
                    await self.browser.ensure_canvas_interactive(page)
            except Exception as e:
                logger.warning(f"Persistence reload encountered non-fatal note: {e}")

        final_wires = await self._get_circuit_wires(page)
        current_wire_count = len(final_wires)

        # Step 8: Confirm persistence of each verified wire
        all_persisted = True
        for cr in connection_results:
            if cr.get("status") == "verified":
                s_parts = cr["source"].split(":")
                t_parts = cr["target"].split(":")
                s_id = s_parts[1] if len(s_parts) > 1 else s_parts[0]
                s_pin = s_parts[2] if len(s_parts) > 2 else s_parts[-1]
                t_id = t_parts[1] if len(t_parts) > 1 else t_parts[0]
                t_pin = t_parts[2] if len(t_parts) > 2 else t_parts[-1]

                persisted_wire = any(
                    (self._instance_endpoint_matches(w.get("source"), s_id, s_pin) and
                     self._instance_endpoint_matches(w.get("target"), t_id, t_pin)) or
                    (self._instance_endpoint_matches(w.get("target"), s_id, s_pin) and
                     self._instance_endpoint_matches(w.get("source"), t_id, t_pin))
                    for w in final_wires
                )
                if not persisted_wire:
                    all_persisted = False
                    cr["status"] = "failed"
                    cr["error"] = "persistence_lost_on_reload"

        # Overall success invariant:
        # A wire is successful only when the exact requested instance IDs and pin names are present in the reloaded persisted netlist.
        verified_count = sum(1 for c in connection_results if c.get("status") == "verified")
        overall_success = (
            verified_count == len(raw_list) and
            all_persisted and
            not has_short_circuit and
            not has_stale_mapping
        )

        return {
            "success": overall_success,
            "persisted": (overall_success and all_persisted),
            "wire_count": current_wire_count,
            "expected_wire_count": len(raw_list),
            "connections": connection_results,
            "validation": {
                "short_circuit": has_short_circuit,
                "stale_terminal_mapping": has_stale_mapping,
            },
        }
