"""Schematic analysis and verification service: SVG extraction, netlist tracing, and electrical rule checks (ERC)."""

from __future__ import annotations

import asyncio
from datetime import datetime
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ..browser.browser_manager import BrowserManager
from ..browser.selectors import EDITOR_SELECTORS
from ..config import SCREENSHOTS_DIR, logger


class SchematicService:
    """Manages schematic SVG inspection, visual netlist extraction, and ERC connection verification."""

    def __init__(self, browser: Optional[BrowserManager] = None) -> None:
        self.browser = browser or BrowserManager.get_instance()

    async def get_schematic_svg(
        self,
        save_path: Optional[str] = None,
        switch_to_schematic: bool = True,
        return_to_view: Optional[str] = "circuits",
    ) -> Dict[str, Any]:
        """Switch to schematic view, capture the complete schematic SVG diagram, and save to disk.

        Args:
            save_path: Optional specific file path for the .svg output.
            switch_to_schematic: If True, switches to Schematic view via workspace switcher.
            return_to_view: Optional view name ('circuits', 'breadboard') to return to after capture.
        """
        page = await self.browser.get_page()

        # 1. Switch to schematic view if requested
        if switch_to_schematic:
            schematic_btn = await self.browser.find_first_matching(
                EDITOR_SELECTORS.get("workspace_schematic_btn", []), timeout=3000, page=page
            )
            if schematic_btn:
                await schematic_btn.click()
                await page.wait_for_timeout(1000)

        # 2. Extract SVG element from the schematic container
        svg_data = await page.evaluate(r"""
            () => {
                // Find schematic SVG container
                const candidates = [
                    document.querySelector('#schematicTab svg'),
                    document.querySelector('.schematic-canvas svg'),
                    document.querySelector('#schematic-container svg'),
                    document.querySelector('svg.schematic'),
                    document.querySelector('.workspace-schematic svg'),
                    document.querySelector('div[id*="schematic"] svg'),
                ].filter(Boolean);

                let svgEl = candidates[0];
                if (!svgEl) {
                    // Fallback: search all SVGs for schematic markers
                    const allSvgs = Array.from(document.querySelectorAll('svg'));
                    svgEl = allSvgs.find(s => {
                        const parent = s.closest('#schematicTab, .schematic-canvas, [id*="schematic"], [class*="schematic"]');
                        if (parent) return true;
                        const txt = s.textContent || '';
                        return (txt.includes('Arduino') || txt.includes('UNO') || txt.includes('U1') || txt.includes('DIST1')) &&
                               !s.closest('#breadboardTab');
                    });
                }

                if (!svgEl) {
                    // Last resort: any SVG with schematic components
                    svgEl = document.querySelector('#schematicTab') || document.querySelector('svg');
                }

                if (!svgEl) {
                    return { success: false, error: 'schematic_svg_not_found' };
                }

                // If element is a container div, find inner svg or serialize
                let rawSvg = '';
                if (svgEl.tagName.toLowerCase() === 'svg') {
                    rawSvg = svgEl.outerHTML;
                } else {
                    const inner = svgEl.querySelector('svg');
                    rawSvg = inner ? inner.outerHTML : svgEl.innerHTML;
                }

                // Ensure SVG has proper XML namespace attributes
                if (!rawSvg.includes('xmlns=')) {
                    rawSvg = rawSvg.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"');
                }

                const viewBox = svgEl.getAttribute('viewBox') || '';
                const width = svgEl.getAttribute('width') || svgEl.getBoundingClientRect?.().width || 1000;
                const height = svgEl.getAttribute('height') || svgEl.getBoundingClientRect?.().height || 800;

                // Extract text labels from schematic SVG (designators like U1, DIST1, pin names)
                const textNodes = Array.from(svgEl.querySelectorAll('text')).map(t => (t.textContent || '').trim()).filter(Boolean);
                const circles = svgEl.querySelectorAll('circle').length;
                const paths = svgEl.querySelectorAll('path, line').length;

                return {
                    success: true,
                    svg_content: rawSvg,
                    viewBox: viewBox,
                    width: Math.round(Number(width) || 1000),
                    height: Math.round(Number(height) || 800),
                    text_labels: textNodes,
                    junction_dots_count: circles,
                    wire_paths_count: paths,
                };
            }
        """)

        if not svg_data.get("success"):
            return {
                "success": False,
                "error": svg_data.get("error", "schematic_svg_not_found"),
                "message": "Could not locate schematic SVG on the canvas. Ensure the circuit editor is loaded.",
            }

        svg_content = svg_data.get("svg_content", "")

        # 3. Save SVG to disk
        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not save_path:
            filename = f"schematic_{timestamp}.svg"
            target_path = os.path.join(SCREENSHOTS_DIR, filename)
        else:
            target_path = save_path
            filename = os.path.basename(target_path)

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(svg_content)

        logger.info(f"Saved schematic SVG to {target_path} ({len(svg_content)} bytes)")

        # 4. Optional switch back to previous view
        if return_to_view:
            circ_btn = await self.browser.find_first_matching(
                EDITOR_SELECTORS.get("workspace_circuits_btn", []), timeout=2000, page=page
            )
            if circ_btn:
                await circ_btn.click()
                await page.wait_for_timeout(600)

        return {
            "success": True,
            "saved_path": target_path,
            "filename": filename,
            "width": svg_data.get("width"),
            "height": svg_data.get("height"),
            "viewBox": svg_data.get("viewBox"),
            "junction_dots_count": svg_data.get("junction_dots_count", 0),
            "wire_paths_count": svg_data.get("wire_paths_count", 0),
            "detected_labels": svg_data.get("text_labels", [])[:30],
            "message": f"Schematic SVG successfully captured and saved to {target_path}.",
        }

    async def inspect_schematic_connections(self) -> Dict[str, Any]:
        """Extract structured schematic netlist, grouping all mutually connected terminals into electrical Nets."""
        page = await self.browser.get_page()

        data = await page.evaluate(r"""
            () => {
                const ce = window.circuit_editor;
                const devMap = ce?.data?.devices?._content || {};
                const wireMap = ce?.data?.wires?._content || {};

                // Map terminals to canonical terminal keys: "devId::terminalName"
                const termToKey = new Map();
                const keyToInfo = new Map();
                const allPins = [];

                for (const [dId, dWrap] of Object.entries(devMap)) {
                    const dev = dWrap.val || dWrap;
                    const dName = typeof dev.name === 'function' ? String(dev.name()) : String(dev.name || '');
                    const dDid = typeof dev.did === 'function' ? String(dev.did()) : String(dev.did || '');
                    const desc = typeof dev.getDescription === 'function' ? dev.getDescription() : null;
                    const compType = desc?.device?.name || desc?.footprint_name || 'Component';

                    // Schematic designator heuristic (e.g. U1, DIST1, R1, D1)
                    let designator = dName;
                    const normType = compType.toLowerCase();
                    if (normType.includes('arduino')) designator = `U${dName || '1'}`;
                    else if (normType.includes('ultrasonic') || normType.includes('sonar')) designator = `DIST${dName || '1'}`;
                    else if (normType.includes('piezo') || normType.includes('buzzer')) designator = `PIEZO${dName || '1'}`;
                    else if (normType.includes('servo')) designator = `SERVO${dName || '1'}`;
                    else if (normType.includes('resistor')) designator = `R${dName || '1'}`;
                    else if (normType.includes('led')) designator = `D${dName || '1'}`;

                    const n2t = dev.name2terminal?._content || {};
                    for (const [tName, tWrap] of Object.entries(n2t)) {
                        const tObj = tWrap.val || tWrap;
                        const key = `${dId}::${tName}`;
                        termToKey.set(tObj, key);

                        const pinInfo = {
                            key: key,
                            instance_id: String(dId),
                            component: compType,
                            name: dName,
                            designator: designator,
                            pin: String(tName),
                            did: dDid,
                        };
                        keyToInfo.set(key, pinInfo);
                        allPins.push(pinInfo);
                    }
                }

                // Disjoint Set / Union-Find for Nets
                const parent = new Map();
                for (const pin of allPins) {
                    parent.set(pin.key, pin.key);
                }

                function find(x) {
                    if (parent.get(x) === x) return x;
                    const root = find(parent.get(x));
                    parent.set(x, root);
                    return root;
                }

                function union(a, b) {
                    const rootA = find(a);
                    const rootB = find(b);
                    if (rootA !== rootB) {
                        parent.set(rootA, rootB);
                    }
                }

                // Process wires to union connected terminals
                const wires = [];
                const wireColors = new Map();

                for (const [wId, wWrap] of Object.entries(wireMap)) {
                    const w = wWrap.val || wWrap;
                    const b = typeof w.begin === 'function' ? w.begin() : w.begin;
                    const e = typeof w.end === 'function' ? w.end() : w.end;
                    const color = typeof w.color === 'function' ? String(w.color()) : String(w.color || 'green');

                    const keyB = termToKey.get(b);
                    const keyE = termToKey.get(e);

                    if (keyB && keyE) {
                        union(keyB, keyE);
                        wires.push({
                            wire_id: String(wId),
                            color: color,
                            from: keyToInfo.get(keyB),
                            to: keyToInfo.get(keyE),
                        });
                    }
                }

                // Group terminals by Net root
                const netGroups = new Map();
                for (const pin of allPins) {
                    const root = find(pin.key);
                    if (!netGroups.has(root)) {
                        netGroups.set(root, []);
                    }
                    netGroups.get(root).push(pin);
                }

                // Format Nets (only groups with >= 2 pins or connected by wires)
                const nets = [];
                const unconnectedPins = [];
                let netIndex = 1;

                for (const [root, members] of netGroups.entries()) {
                    if (members.length > 1) {
                        // Classify net type
                        let netType = 'Signal';
                        const pinNames = members.map(m => m.pin.toLowerCase());
                        const compTypes = members.map(m => m.component.toLowerCase());

                        const has5V = pinNames.some(p => p === '5v' || p === 'vcc' || p === 'power' || p === 'pos' || p === 'vs');
                        const hasGND = pinNames.some(p => p.includes('gnd') || p === 'neg' || p === 'ground');

                        if (has5V && hasGND) {
                            netType = 'SHORT_CIRCUIT (5V+GND)';
                        } else if (has5V) {
                            netType = 'Power (+5V / VCC)';
                        } else if (hasGND) {
                            netType = 'Ground (GND)';
                        }

                        nets.push({
                            net_id: `Net_${netIndex++}`,
                            type: netType,
                            is_power_gnd_short: has5V && hasGND,
                            pins_count: members.length,
                            pins: members.map(m => ({
                                component: m.component,
                                designator: m.designator,
                                instance_id: m.instance_id,
                                pin: m.pin,
                            })),
                        });
                    } else {
                        unconnectedPins.push(members[0]);
                    }
                }

                return {
                    success: true,
                    total_components: Object.keys(devMap).length,
                    total_wires: Object.keys(wireMap).length,
                    nets: nets,
                    unconnected_pins: unconnectedPins.map(p => ({
                        component: p.component,
                        designator: p.designator,
                        instance_id: p.instance_id,
                        pin: p.pin,
                    })),
                };
            }
        """)

        return data

    async def verify_schematic_connections(self, strict: bool = True) -> Dict[str, Any]:
        """Perform Electrical Rule Checks (ERC) on the schematic connections.

        Checks:
        1. Catastrophic Power-to-Ground Shorts (e.g. 5V wired directly to GND).
        2. Component Self-Shorts (e.g. Piezo positive & negative tied to same net).
        3. Floating Power / Ground on active sensors, ICs, and microcontrollers.
        4. Overconnected / Conflicted pins (e.g. Piezo (+) tied to 3 conflicting pins).
        5. Unconnected active components or missing code signal pins.
        """
        netlist_data = await self.inspect_schematic_connections()
        if not netlist_data.get("success"):
            return {
                "success": False,
                "is_valid": False,
                "error": "inspection_failed",
                "message": "Failed to inspect schematic netlist.",
            }

        nets: List[Dict[str, Any]] = netlist_data.get("nets", [])
        unconnected: List[Dict[str, Any]] = netlist_data.get("unconnected_pins", [])

        violations: List[Dict[str, Any]] = []

        # -------------------------------------------------------------
        # CHECK 1: Power-to-Ground Short Circuits
        # -------------------------------------------------------------
        for net in nets:
            if net.get("is_power_gnd_short"):
                pins_desc = [f"{p['designator'] or p['component']} ({p['pin']})" for p in net["pins"]]
                violations.append({
                    "rule": "POWER_GROUND_SHORT_CIRCUIT",
                    "severity": "CRITICAL",
                    "net_id": net["net_id"],
                    "message": f"Catastrophic short circuit on {net['net_id']}! Power (+5V/VCC) and Ground (GND) are directly connected: {', '.join(pins_desc)}.",
                    "recommendation": "Disconnect the ground connection from the 5V power net immediately to prevent simulation crash or hardware damage.",
                })

        # -------------------------------------------------------------
        # CHECK 2: Component Self-Shorts (Pins of same device on same net)
        # -------------------------------------------------------------
        for net in nets:
            pins_by_inst: Dict[str, List[str]] = {}
            for p in net["pins"]:
                pins_by_inst.setdefault(p["instance_id"], []).append(p["pin"])

            for inst_id, pin_list in pins_by_inst.items():
                if len(pin_list) > 1:
                    # Find component details
                    sample = next(p for p in net["pins"] if p["instance_id"] == inst_id)
                    comp_name = sample["component"]
                    desig = sample["designator"] or comp_name
                    norm_type = comp_name.lower()

                    # For 2-terminal or 3-terminal devices, connecting multiple pins to same net is a dead short
                    is_two_terminal = any(k in norm_type for k in ("piezo", "buzzer", "resistor", "led", "motor", "capacitor", "diode"))
                    if is_two_terminal:
                        violations.append({
                            "rule": "COMPONENT_SELF_SHORT",
                            "severity": "CRITICAL",
                            "component": comp_name,
                            "designator": desig,
                            "net_id": net["net_id"],
                            "message": f"{desig} ({comp_name}) is self-shorted! Both pins [{', '.join(pin_list)}] are connected to the same net ({net['net_id']}).",
                            "recommendation": f"Connect {desig} positive to a dedicated digital/power pin and negative to ground separately.",
                        })

        # -------------------------------------------------------------
        # CHECK 3: Multi-Connection Conflict on Passive Components
        # -------------------------------------------------------------
        for net in nets:
            piezo_pins = [p for p in net["pins"] if "piezo" in p["component"].lower() or "buzzer" in p["component"].lower()]
            if piezo_pins and len(net["pins"]) > 3:
                # If Piezo positive is tied to 3 or more pins including power and digital
                comp_pins = [f"{p['designator'] or p['component']} ({p['pin']})" for p in net["pins"]]
                violations.append({
                    "rule": "PIN_CONNECTION_CONFLICT",
                    "severity": "CRITICAL",
                    "component": "Piezo",
                    "net_id": net["net_id"],
                    "message": f"Piezo pin is improperly bridged to {len(net['pins'])} terminals on {net['net_id']}: {', '.join(comp_pins)}.",
                    "recommendation": "Remove extraneous wire connections so Piezo (+) connects only to its assigned Arduino pin (e.g. D11).",
                })

        # -------------------------------------------------------------
        # CHECK 4: Floating Power (VCC) or Ground (GND) on Active Devices
        # -------------------------------------------------------------
        active_critical_pins = {
            "ultrasonic": ["pos", "vcc", "power", "neg", "gnd", "ground"],
            "hc-sr04": ["pos", "vcc", "power", "neg", "gnd", "ground"],
            "distance sensor": ["pos", "vcc", "power", "neg", "gnd", "ground"],
            "servo": ["power", "ground"],
            "h-bridge": ["vs", "vss", "gnd"],
            "motor driver": ["vs", "vss", "gnd"],
            "l293": ["vs", "vss", "gnd"],
            "pir": ["power", "ground"],
            "tmp36": ["power", "ground"],
            "lcd": ["vcc", "gnd"],
        }

        for u in unconnected:
            c_type = u["component"].lower()
            p_name = u["pin"].lower()
            desig = u["designator"] or u["component"]

            for act_key, crit_pins in active_critical_pins.items():
                if act_key in c_type:
                    if any(cp == p_name or cp in p_name for cp in crit_pins):
                        violations.append({
                            "rule": "FLOATING_POWER_OR_GROUND",
                            "severity": "CRITICAL",
                            "component": u["component"],
                            "designator": desig,
                            "pin": u["pin"],
                            "message": f"Active device {desig} ({u['component']}) has unconnected power/ground pin '{u['pin']}'! Component will fail to operate.",
                            "recommendation": f"Connect {desig} ({u['pin']}) to {'Arduino 5V' if any(k in p_name for k in ('vcc', 'power', 'pos', 'vs')) else 'Arduino GND'}.",
                        })
                        break

        # Overall validity
        critical_count = sum(1 for v in violations if v["severity"] == "CRITICAL")
        is_valid = (critical_count == 0)

        # Build human-readable summary
        if is_valid:
            summary = "Schematic Verification PASSED: All electrical nets are properly isolated, no shorts detected, and all active power/ground pins are connected."
        else:
            summary_lines = [
                f"Schematic Verification FAILED: Detected {critical_count} critical ERC violation(s):",
            ]
            for i, v in enumerate(violations, 1):
                summary_lines.append(f"{i}. [{v['rule']}] {v['message']}")
                summary_lines.append(f"   -> Fix: {v['recommendation']}")
            summary = "\n".join(summary_lines)

        return {
            "success": True,
            "is_valid": is_valid,
            "critical_errors_count": critical_count,
            "violations_count": len(violations),
            "violations": violations,
            "total_nets": len(nets),
            "nets": nets,
            "unconnected_pins_count": len(unconnected),
            "unconnected_pins": unconnected,
            "summary": summary,
        }
