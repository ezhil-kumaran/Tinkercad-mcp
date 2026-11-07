"""Tests for SchematicService: SVG extraction, netlist tracing, and ERC connection verification."""

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.browser.browser_manager import BrowserManager
from src.services.schematic_service import SchematicService
from src.server import server


class TestSchematicService(unittest.IsolatedAsyncioTestCase):
    """Test suite for schematic SVG extraction and connection verification."""

    async def test_get_schematic_svg_captures_and_saves_file(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        mock_btn = AsyncMock()
        mock_btn.click = AsyncMock()
        mock_bm.find_first_matching = AsyncMock(return_value=mock_btn)

        mock_page.evaluate = AsyncMock(return_value={
            "success": True,
            "svg_content": '<svg viewBox="0 0 1000 800"><text>U1</text><text>DIST1</text><circle cx="50" cy="50" r="3"/><path d="M 0 0 L 100 100"/></svg>',
            "viewBox": "0 0 1000 800",
            "width": 1000,
            "height": 800,
            "text_labels": ["U1", "DIST1", "Arduino UNO", "TRIG", "ECHO"],
            "junction_dots_count": 1,
            "wire_paths_count": 1,
        })
        mock_page.wait_for_timeout = AsyncMock()

        service = SchematicService(mock_bm)
        res = await service.get_schematic_svg()

        self.assertTrue(res["success"])
        self.assertIn("saved_path", res)
        self.assertTrue(os.path.exists(res["saved_path"]))
        self.assertEqual(res["junction_dots_count"], 1)
        self.assertEqual(res["wire_paths_count"], 1)
        self.assertIn("U1", res["detected_labels"])

        # Clean up test output
        try:
            os.remove(res["saved_path"])
        except Exception:
            pass

    async def test_inspect_schematic_connections_extracts_clean_nets(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        # Mock clean netlist evaluation
        mock_page.evaluate = AsyncMock(return_value={
            "success": True,
            "total_components": 3,
            "total_wires": 6,
            "nets": [
                {
                    "net_id": "Net_1",
                    "type": "Signal",
                    "is_power_gnd_short": False,
                    "pins_count": 2,
                    "pins": [
                        {"component": "Arduino Uno R3", "designator": "U1", "instance_id": "_ard", "pin": "D2"},
                        {"component": "Ultrasonic Distance Sensor", "designator": "DIST1", "instance_id": "_dist", "pin": "trig"},
                    ],
                },
                {
                    "net_id": "Net_2",
                    "type": "Power (+5V / VCC)",
                    "is_power_gnd_short": False,
                    "pins_count": 2,
                    "pins": [
                        {"component": "Arduino Uno R3", "designator": "U1", "instance_id": "_ard", "pin": "5V"},
                        {"component": "Ultrasonic Distance Sensor", "designator": "DIST1", "instance_id": "_dist", "pin": "pos"},
                    ],
                },
            ],
            "unconnected_pins": [],
        })

        service = SchematicService(mock_bm)
        res = await service.inspect_schematic_connections()

        self.assertTrue(res["success"])
        self.assertEqual(len(res["nets"]), 2)
        self.assertEqual(res["nets"][0]["pins"][1]["pin"], "trig")

    async def test_verify_schematic_catches_power_ground_short(self):
        """Catches 5V and GND directly wired on the same net."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        service = SchematicService(mock_bm)
        service.inspect_schematic_connections = AsyncMock(return_value={
            "success": True,
            "nets": [
                {
                    "net_id": "Net_1",
                    "type": "SHORT_CIRCUIT (5V+GND)",
                    "is_power_gnd_short": True,
                    "pins_count": 4,
                    "pins": [
                        {"component": "Arduino Uno R3", "designator": "U1", "instance_id": "_ard", "pin": "5V"},
                        {"component": "Arduino Uno R3", "designator": "U1", "instance_id": "_ard", "pin": "GND"},
                        {"component": "Piezo", "designator": "PIEZO1", "instance_id": "_piezo", "pin": "1"},
                        {"component": "Piezo", "designator": "PIEZO1", "instance_id": "_piezo", "pin": "2"},
                    ],
                }
            ],
            "unconnected_pins": [],
        })

        res = await service.verify_schematic_connections()
        self.assertTrue(res["success"])
        self.assertFalse(res["is_valid"])
        self.assertGreaterEqual(res["critical_errors_count"], 1)

        rules = [v["rule"] for v in res["violations"]]
        self.assertIn("POWER_GROUND_SHORT_CIRCUIT", rules)
        self.assertIn("COMPONENT_SELF_SHORT", rules)

    async def test_verify_schematic_catches_floating_ultrasonic_vcc_and_gnd(self):
        """Catches when Ultrasonic TRIG/ECHO are wired but VCC and GND are left unconnected (user's exact issue)."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        service = SchematicService(mock_bm)
        service.inspect_schematic_connections = AsyncMock(return_value={
            "success": True,
            "nets": [
                {
                    "net_id": "Net_1",
                    "type": "Signal",
                    "is_power_gnd_short": False,
                    "pins_count": 2,
                    "pins": [
                        {"component": "Arduino Uno R3", "designator": "U1", "instance_id": "_ard", "pin": "D8"},
                        {"component": "Ultrasonic Distance Sensor", "designator": "DIST1", "instance_id": "_dist", "pin": "trig"},
                    ],
                },
                {
                    "net_id": "Net_2",
                    "type": "Signal",
                    "is_power_gnd_short": False,
                    "pins_count": 2,
                    "pins": [
                        {"component": "Arduino Uno R3", "designator": "U1", "instance_id": "_ard", "pin": "D6"},
                        {"component": "Ultrasonic Distance Sensor", "designator": "DIST1", "instance_id": "_dist", "pin": "echo"},
                    ],
                },
            ],
            # VCC and GND are floating!
            "unconnected_pins": [
                {"component": "Ultrasonic Distance Sensor", "designator": "DIST1", "instance_id": "_dist", "pin": "pos"},
                {"component": "Ultrasonic Distance Sensor", "designator": "DIST1", "instance_id": "_dist", "pin": "neg"},
            ],
        })

        res = await service.verify_schematic_connections()
        self.assertTrue(res["success"])
        self.assertFalse(res["is_valid"])

        floating_violations = [v for v in res["violations"] if v["rule"] == "FLOATING_POWER_OR_GROUND"]
        self.assertEqual(len(floating_violations), 2)
        pins_flagged = [v["pin"] for v in floating_violations]
        self.assertIn("pos", pins_flagged)
        self.assertIn("neg", pins_flagged)
        self.assertIn("DIST1", floating_violations[0]["message"])

    async def test_mcp_server_registers_schematic_tools(self):
        tools = await server.list_tools()
        tool_names = [t.name for t in tools]
        self.assertIn("tinkercad_get_schematic_svg", tool_names)
        self.assertIn("tinkercad_inspect_schematic_connections", tool_names)
        self.assertIn("tinkercad_verify_schematic_connections", tool_names)


if __name__ == "__main__":
    unittest.main()
