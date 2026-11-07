"""Comprehensive test suite for the verified, instance-aware netlist wiring workflow."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from src.browser.browser_manager import BrowserManager
from src.services.wiring_service import WiringService


class TestConnectVerifiedNetlist(unittest.IsolatedAsyncioTestCase):
    """Test suite for connect_verified_netlist and instance-scoped terminal resolution."""

    def setUp(self):
        self.mock_bm = MagicMock(spec=BrowserManager)
        self.mock_page = AsyncMock()
        self.mock_bm.get_page = AsyncMock(return_value=self.mock_page)
        self.mock_bm.ensure_canvas_interactive = AsyncMock()
        self.mock_bm.close_code_panel = AsyncMock()
        self.mock_bm.close_overlays_and_modals = AsyncMock()
        self.service = WiringService(self.mock_bm)

        # Standard components mock representing the user's circuit
        self.sample_instances = {
            "_269": {
                "instance_id": "_269",
                "type": "Arduino Uno R3",
                "name": "Arduino",
                "did": "132521",
                "pins": ["D2", "D9", "D13", "5V", "GND1", "GND2", "GND3"],
            },
            "_291": {
                "instance_id": "_291",
                "type": "Micro Servo",
                "name": "Servo",
                "did": "146740",
                "pins": ["Signal", "Power", "Ground"],
            },
            "_282": {
                "instance_id": "_282",
                "type": "PIR Sensor",
                "name": "PIR",
                "did": "11111",
                "pins": ["OUT", "VCC", "GND"],
            },
            "_283": {
                "instance_id": "_283",
                "type": "Resistor",
                "name": "Resistor",
                "did": "53184",
                "pins": ["1", "2"],
            },
            "_280": {
                "instance_id": "_280",
                "type": "LED",
                "name": "LED",
                "did": "58422",
                "pins": ["Anode", "Cathode"],
            },
        }

    async def test_connect_verified_netlist_success_all_persisted(self):
        """Validates successful end-to-end netlist wiring with exact instances and persistence."""
        connections = [
            ["Arduino:_269", "D9", "Servo:_291", "Signal"],
            ["Arduino:_269", "5V", "Servo:_291", "Power"],
            ["Arduino:_269", "GND1", "Servo:_291", "Ground"],
            ["Arduino:_269", "D2", "PIR:_282", "OUT"],
            ["Arduino:_269", "5V", "PIR:_282", "VCC"],
            ["Arduino:_269", "GND2", "PIR:_282", "GND"],
            ["Arduino:_269", "D13", "Resistor:_283", "1"],
            ["Resistor:_283", "2", "LED:_280", "Anode"],
            ["LED:_280", "Cathode", "Arduino:_269", "GND3"],
        ]

        # Mock component instances discovery
        self.mock_page.evaluate = AsyncMock(side_effect=[
            # 1. get_component_instances_info
            {"success": True, "count": 5, "instances": self.sample_instances},
            # 2. clear_circuit_wires JS collection sweep
            {"success": True, "removed_count": 0, "remaining_count": 0},
            # 3. ce.root.save
            None,
        ])

        # Mock resolve_instance_terminal returning valid distinct coordinates
        coord_map = {
            ("_269", "D9"): (400, 200, "D9"),
            ("_291", "Signal"): (600, 200, "Signal"),
            ("_269", "5V"): (400, 250, "5V"),
            ("_291", "Power"): (600, 250, "Power"),
            ("_269", "GND1"): (400, 300, "GND1"),
            ("_291", "Ground"): (600, 300, "Ground"),
            ("_269", "D2"): (400, 350, "D2"),
            ("_282", "OUT"): (700, 350, "OUT"),
            ("_282", "VCC"): (700, 250, "VCC"),
            ("_269", "GND2"): (400, 400, "GND2"),
            ("_282", "GND"): (700, 400, "GND"),
            ("_269", "D13"): (400, 450, "D13"),
            ("_283", "1"): (500, 450, "1"),
            ("_283", "2"): (520, 450, "2"),
            ("_280", "Anode"): (550, 450, "Anode"),
            ("_280", "Cathode"): (570, 450, "Cathode"),
            ("_269", "GND3"): (400, 500, "GND3"),
        }

        async def fake_resolve_terminal(instance_id, pin_query, component_hint=None, page=None):
            clean_pin = pin_query
            key = (instance_id, clean_pin)
            if key not in coord_map:
                # Try finding in map
                match = next((v for k, v in coord_map.items() if k[0] == instance_id and k[1].lower() == pin_query.lower()), None)
                if match:
                    return {"success": True, "instance_id": instance_id, "pin": match[2], "x": match[0], "y": match[1], "is_suspicious": False}
                return {"success": True, "instance_id": instance_id, "pin": pin_query, "x": 100, "y": 100, "is_suspicious": False}
            x, y, resolved_pin = coord_map[key]
            return {"success": True, "instance_id": instance_id, "pin": resolved_pin, "x": x, "y": y, "is_suspicious": False}

        self.service.resolve_instance_terminal = AsyncMock(side_effect=fake_resolve_terminal)
        self.service.connect_pins = AsyncMock(return_value={"success": True, "wire_id": "w_test"})

        # Mock _get_circuit_wires to verify each connection immediately and post-reload
        built_wires = [
            {"id": "w1", "source": {"id": "_269", "pin": "D9"}, "target": {"id": "_291", "pin": "Signal"}},
            {"id": "w2", "source": {"id": "_269", "pin": "5V"}, "target": {"id": "_291", "pin": "Power"}},
            {"id": "w3", "source": {"id": "_269", "pin": "GND1"}, "target": {"id": "_291", "pin": "Ground"}},
            {"id": "w4", "source": {"id": "_269", "pin": "D2"}, "target": {"id": "_282", "pin": "OUT"}},
            {"id": "w5", "source": {"id": "_269", "pin": "5V"}, "target": {"id": "_282", "pin": "VCC"}},
            {"id": "w6", "source": {"id": "_269", "pin": "GND2"}, "target": {"id": "_282", "pin": "GND"}},
            {"id": "w7", "source": {"id": "_269", "pin": "D13"}, "target": {"id": "_283", "pin": "1"}},
            {"id": "w8", "source": {"id": "_283", "pin": "2"}, "target": {"id": "_280", "pin": "Anode"}},
            {"id": "w9", "source": {"id": "_280", "pin": "Cathode"}, "target": {"id": "_269", "pin": "GND3"}},
        ]
        self.service._get_circuit_wires = AsyncMock(return_value=built_wires)

        res = await self.service.connect_verified_netlist(
            connections=connections,
            clear_existing=True,
            verify_each=True,
            verify_persistence=True,
        )

        self.assertTrue(res["success"])
        self.assertTrue(res["persisted"])
        self.assertEqual(res["wire_count"], 9)
        self.assertEqual(res["expected_wire_count"], 9)
        self.assertFalse(res["validation"]["short_circuit"])
        self.assertFalse(res["validation"]["stale_terminal_mapping"])
        self.assertEqual(len(res["connections"]), 9)
        for c in res["connections"]:
            self.assertEqual(c["status"], "verified")

    async def test_connect_verified_netlist_rejects_power_ground_short(self):
        """Catches and rejects 5V directly connected to GND2 on Arduino."""
        connections = [
            ["Arduino:_269", "D9", "Servo:_291", "Signal"],
            ["Arduino:_269", "5V", "Arduino:_269", "GND2"],
        ]

        self.mock_page.evaluate = AsyncMock(side_effect=[
            {"success": True, "count": 2, "instances": self.sample_instances},
            {"success": True, "removed_count": 0, "remaining_count": 0},
            None,
        ])

        async def fake_resolve_terminal(instance_id, pin_query, component_hint=None, page=None):
            x = 400 if "_269" in instance_id else 600
            y = 200
            return {"success": True, "instance_id": instance_id, "pin": pin_query, "x": x, "y": y, "is_suspicious": False}

        self.service.resolve_instance_terminal = AsyncMock(side_effect=fake_resolve_terminal)
        self.service.connect_pins = AsyncMock(return_value={"success": True, "wire_id": "w1"})
        self.service._get_circuit_wires = AsyncMock(return_value=[
            {"id": "w1", "source": {"id": "_269", "pin": "D9"}, "target": {"id": "_291", "pin": "Signal"}},
        ])

        res = await self.service.connect_verified_netlist(connections=connections)

        self.assertFalse(res["success"])
        self.assertFalse(res["persisted"])
        self.assertEqual(res["expected_wire_count"], 2)
        self.assertTrue(res["validation"]["short_circuit"])
        self.assertFalse(res["validation"]["stale_terminal_mapping"])

        conn1 = res["connections"][0]
        self.assertEqual(conn1["source"], "Arduino:_269:D9")
        self.assertEqual(conn1["target"], "Servo:_291:Signal")
        self.assertEqual(conn1["status"], "verified")

        conn2 = res["connections"][1]
        self.assertEqual(conn2["source"], "Arduino:_269:5V")
        self.assertEqual(conn2["target"], "Arduino:_269:GND2")
        self.assertEqual(conn2["status"], "rejected")
        self.assertEqual(conn2["error"], "power_ground_short")

    async def test_connect_verified_netlist_rejects_same_component_self_wire(self):
        """Rejects wiring pins of the same component together."""
        connections = [
            ["Servo:_291", "Power", "Servo:_291", "Ground"],
        ]

        self.mock_page.evaluate = AsyncMock(return_value={
            "success": True,
            "count": 1,
            "instances": self.sample_instances,
        })

        res = await self.service.connect_verified_netlist(connections=connections)

        self.assertFalse(res["success"])
        self.assertEqual(len(res["connections"]), 1)
        self.assertEqual(res["connections"][0]["status"], "rejected")
        self.assertEqual(res["connections"][0]["error"], "same_component_self_wire")

    async def test_connect_verified_netlist_rejects_direct_motor_to_arduino(self):
        """Rejects direct DC motor to Arduino pin connection (>40mA overcurrent risk)."""
        instances = {
            "_269": {"instance_id": "_269", "type": "Arduino Uno R3", "name": "Arduino", "pins": ["D4", "5V", "GND"]},
            "_101": {"instance_id": "_101", "type": "DC Motor", "name": "Motor", "pins": ["terminal1", "terminal2"]},
        }
        connections = [
            ["Arduino:_269", "D4", "Motor:_101", "1"],
        ]

        self.mock_page.evaluate = AsyncMock(return_value={
            "success": True,
            "count": 2,
            "instances": instances,
        })

        res = await self.service.connect_verified_netlist(connections=connections)

        self.assertFalse(res["success"])
        self.assertEqual(res["connections"][0]["status"], "rejected")
        self.assertEqual(res["connections"][0]["error"], "electrical_safety_violation")

    async def test_connect_verified_netlist_catches_suspicious_terminal_mapping(self):
        """Detects and rejects suspicious terminal mappings like 5V resolving to GND or D9 to D2."""
        connections = [
            ["Arduino:_269", "5V", "Servo:_291", "Power"],
        ]

        self.mock_page.evaluate = AsyncMock(side_effect=[
            {"success": True, "count": 2, "instances": self.sample_instances},
            {"success": True, "removed_count": 0, "remaining_count": 0},
        ])

        # Mock resolve_instance_terminal returning suspicious mapping
        self.service.resolve_instance_terminal = AsyncMock(return_value={
            "success": False,
            "error": "suspicious_terminal_mapping",
            "is_suspicious": True,
            "message": "Suspicious mapping: Requested '5V' resolved to 'GND'.",
        })

        res = await self.service.connect_verified_netlist(connections=connections)

        self.assertFalse(res["success"])
        self.assertTrue(res["validation"]["stale_terminal_mapping"])
        self.assertEqual(res["connections"][0]["status"], "rejected")
        self.assertEqual(res["connections"][0]["error"], "suspicious_terminal_mapping")

    async def test_connect_verified_netlist_missing_instance_rejected(self):
        """Rejects connection when requested instance ID is not in circuit."""
        connections = [
            ["Servo:_999", "Signal", "Arduino:_269", "D9"],
        ]

        self.mock_page.evaluate = AsyncMock(return_value={
            "success": True,
            "count": 1,
            "instances": self.sample_instances,
        })

        res = await self.service.connect_verified_netlist(connections=connections)

        self.assertFalse(res["success"])
        self.assertEqual(res["connections"][0]["status"], "rejected")
        self.assertEqual(res["connections"][0]["error"], "component_instance_not_found")

    async def test_connect_verified_netlist_rejects_duplicate_pairs(self):
        """Detects and rejects redundant/duplicate endpoint connections."""
        connections = [
            ["Arduino:_269", "D9", "Servo:_291", "Signal"],
            ["Arduino:_269", "D9", "Servo:_291", "Signal"],
        ]

        self.mock_page.evaluate = AsyncMock(side_effect=[
            {"success": True, "count": 2, "instances": self.sample_instances},
            {"success": True, "removed_count": 0, "remaining_count": 0},
            None,
        ])

        async def fake_resolve_terminal(instance_id, pin_query, component_hint=None, page=None):
            x = 400 if "_269" in instance_id else 600
            return {"success": True, "instance_id": instance_id, "pin": pin_query, "x": x, "y": 200, "is_suspicious": False}

        self.service.resolve_instance_terminal = AsyncMock(side_effect=fake_resolve_terminal)
        self.service.connect_pins = AsyncMock(return_value={"success": True, "wire_id": "w1"})
        self.service._get_circuit_wires = AsyncMock(return_value=[
            {"id": "w1", "source": {"id": "_269", "pin": "D9"}, "target": {"id": "_291", "pin": "Signal"}},
        ])

        res = await self.service.connect_verified_netlist(connections=connections)

        self.assertFalse(res["success"])
        self.assertEqual(len(res["connections"]), 2)
        self.assertEqual(res["connections"][0]["status"], "verified")
        self.assertEqual(res["connections"][1]["status"], "rejected")
        self.assertEqual(res["connections"][1]["error"], "duplicate_connection")

    async def test_pin_alias_normalization(self):
        """Verifies semantic pin normalization for power, ground, and passive pins."""
        self.assertTrue(WiringService._pins_match_semantically("vcc", "power"))
        self.assertTrue(WiringService._pins_match_semantically("5v", "pos"))
        self.assertTrue(WiringService._pins_match_semantically("gnd", "ground"))
        self.assertTrue(WiringService._pins_match_semantically("neg", "cathode"))
        self.assertTrue(WiringService._pins_match_semantically("anode", "+"))
        self.assertTrue(WiringService._pins_match_semantically("signal", "out"))
        self.assertTrue(WiringService._pins_match_semantically("d9", "~d9"))
        self.assertTrue(WiringService._pins_match_semantically("9", "d9"))
        self.assertTrue(WiringService._pins_match_semantically("terminal1", "1"))
        self.assertFalse(WiringService._pins_match_semantically("gnd1", "gnd2"))

    async def test_mcp_server_registers_netlist_tool(self):
        """Verifies that tinkercad_connect_verified_netlist is registered in the MCP toolset."""
        from src.server import server
        tools = server._tool_manager.list_tools()
        names = {t.name for t in tools}
        self.assertIn("tinkercad_connect_verified_netlist", names)


if __name__ == "__main__":
    unittest.main()
