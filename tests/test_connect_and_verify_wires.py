"""Unit tests for tinkercad_connect_and_verify_wires and multi-connection workflow."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.browser.browser_manager import BrowserManager
from src.services.wiring_service import WiringService


class TestConnectAndVerifyWires(unittest.IsolatedAsyncioTestCase):
    """Test suite for the connect_and_verify_wires orchestrated wiring tool."""

    async def test_connect_and_verify_six_wire_dune_circuit_success(self):
        """Successfully connects, verifies, and validates all 6 wires for the dune circuit."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock()
        mock_bm.close_code_panel = AsyncMock()
        mock_bm.close_overlays_and_modals = AsyncMock()

        service = WiringService(mock_bm)

        # 6 connections:
        # Arduino 5V -> Ultrasonic pos
        # Arduino GND -> Ultrasonic neg
        # Arduino D2 -> Ultrasonic trig
        # Arduino D3 -> Ultrasonic echo
        # Arduino D11 -> Piezo +
        # Arduino GND -> Piezo -
        connections = [
            {"source_component": "Arduino Uno R3", "source_pin": "5V", "target_component": "Ultrasonic Distance Sensor (4-pin)", "target_pin": "pos", "color": "red"},
            {"source_component": "Arduino Uno R3", "source_pin": "GND", "target_component": "Ultrasonic Distance Sensor (4-pin)", "target_pin": "neg", "color": "black"},
            {"source_component": "Arduino Uno R3", "source_pin": "D2", "target_component": "Ultrasonic Distance Sensor (4-pin)", "target_pin": "trig", "color": "blue"},
            {"source_component": "Arduino Uno R3", "source_pin": "D3", "target_component": "Ultrasonic Distance Sensor (4-pin)", "target_pin": "echo", "color": "green"},
            {"source_component": "Arduino Uno R3", "source_pin": "D11", "target_component": "Piezo", "target_pin": "+", "color": "yellow"},
            {"source_component": "Arduino Uno R3", "source_pin": "GND", "target_component": "Piezo", "target_pin": "-", "color": "black"},
        ]

        # Mock connect_component_pins returning success for each call
        service.connect_component_pins = AsyncMock(return_value={"success": True, "wire_id": "_wire_new"})

        # Mock _get_circuit_wires: initially 0, then after reload returns all 6 wires
        reloaded_wires = [
            {"id": "w1", "source": {"type": "Arduino Uno R3", "pin": "5V"}, "target": {"type": "Ultrasonic Distance Sensor (4-pin)", "pin": "pos"}},
            {"id": "w2", "source": {"type": "Arduino Uno R3", "pin": "GND"}, "target": {"type": "Ultrasonic Distance Sensor (4-pin)", "pin": "neg"}},
            {"id": "w3", "source": {"type": "Arduino Uno R3", "pin": "D2"}, "target": {"type": "Ultrasonic Distance Sensor (4-pin)", "pin": "trig"}},
            {"id": "w4", "source": {"type": "Arduino Uno R3", "pin": "D3"}, "target": {"type": "Ultrasonic Distance Sensor (4-pin)", "pin": "echo"}},
            {"id": "w5", "source": {"type": "Arduino Uno R3", "pin": "D11"}, "target": {"type": "Piezo", "pin": "+"}},
            {"id": "w6", "source": {"type": "Arduino Uno R3", "pin": "GND"}, "target": {"type": "Piezo", "pin": "-"}},
        ]
        service._get_circuit_wires = AsyncMock(return_value=reloaded_wires)

        mock_page.wait_for_timeout = AsyncMock()
        mock_page.reload = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=True)

        with patch("src.services.schematic_service.SchematicService.verify_schematic_connections") as mock_erc:
            mock_erc.return_value = {
                "success": True,
                "is_valid": True,
                "critical_errors_count": 0,
                "violations": [],
            }

            res = await service.connect_and_verify_wires(
                connections=connections,
                expected_wire_count=6,
                verify_after_each=True,
                verify_persistence=True,
                run_schematic_erc=True,
            )

            self.assertTrue(res["success"])
            self.assertEqual(res["connections_succeeded"], 6)
            self.assertEqual(res["connections_failed"], 0)
            self.assertEqual(res["wire_count_persisted"], 6)
            self.assertTrue(res["wire_count_matched"])
            mock_page.reload.assert_awaited_once()

    async def test_connect_and_verify_wires_skips_existing_duplicate(self):
        """If a wire already exists in the circuit, it is detected and duplicate placement is skipped."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        service = WiringService(mock_bm)

        existing_wire = {
            "id": "w_exist",
            "source": {"type": "Arduino Uno R3", "pin": "D11"},
            "target": {"type": "Piezo", "pin": "+"},
        }
        service._get_circuit_wires = AsyncMock(return_value=[existing_wire])
        service.connect_component_pins = AsyncMock()

        mock_page.wait_for_timeout = AsyncMock()
        mock_page.reload = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=True)

        connections = [
            {"source_component": "Arduino Uno R3", "source_pin": "D11", "target_component": "Piezo", "target_pin": "+", "color": "yellow"}
        ]

        with patch("src.services.schematic_service.SchematicService.verify_schematic_connections") as mock_erc:
            mock_erc.return_value = {"success": True, "is_valid": True, "critical_errors_count": 0, "violations": []}

            res = await service.connect_and_verify_wires(
                connections=connections,
                expected_wire_count=1,
                verify_persistence=True,
                run_schematic_erc=True,
            )

            self.assertTrue(res["success"])
            self.assertEqual(res["connections_succeeded"], 1)
            # connect_component_pins was NOT called because wire already existed
            service.connect_component_pins.assert_not_called()
            self.assertEqual(res["results"][0]["status"], "already_connected")

    async def test_connect_and_verify_wires_fails_when_wire_count_mismatches(self):
        """Fails when expected_wire_count does not match actual persisted count."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        service = WiringService(mock_bm)
        service.connect_component_pins = AsyncMock(return_value={"success": True, "wire_id": "w1"})
        # Only 1 wire returned, but expected 2
        service._get_circuit_wires = AsyncMock(return_value=[
            {"id": "w1", "source": {"type": "Arduino Uno R3", "pin": "5V"}, "target": {"type": "Ultrasonic Distance Sensor (4-pin)", "pin": "pos"}}
        ])

        mock_page.wait_for_timeout = AsyncMock()
        mock_page.reload = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=True)

        connections = [
            {"source_component": "Arduino Uno R3", "source_pin": "5V", "target_component": "Ultrasonic Distance Sensor (4-pin)", "target_pin": "pos"},
            {"source_component": "Arduino Uno R3", "source_pin": "GND", "target_component": "Ultrasonic Distance Sensor (4-pin)", "target_pin": "neg"},
        ]

        with patch("src.services.schematic_service.SchematicService.verify_schematic_connections") as mock_erc:
            mock_erc.return_value = {"success": True, "is_valid": True, "critical_errors_count": 0, "violations": []}

            res = await service.connect_and_verify_wires(
                connections=connections,
                expected_wire_count=2,  # Expected 2, but only 1 persisted
                verify_persistence=True,
                run_schematic_erc=True,
            )

            self.assertFalse(res["success"])
            self.assertFalse(res["wire_count_matched"])
            self.assertIn("MISMATCH", res["message"])

    async def test_connect_and_verify_wires_fails_when_schematic_erc_detects_short(self):
        """Fails when Schematic ERC detects a critical 5V-to-GND short circuit."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        service = WiringService(mock_bm)
        service.connect_component_pins = AsyncMock(return_value={"success": True, "wire_id": "w1"})
        service._get_circuit_wires = AsyncMock(return_value=[
            {"id": "w1", "source": {"type": "Arduino Uno R3", "pin": "5V"}, "target": {"type": "Arduino Uno R3", "pin": "GND"}}
        ])

        mock_page.wait_for_timeout = AsyncMock()
        mock_page.reload = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=True)

        connections = [
            {"source_component": "Arduino Uno R3", "source_pin": "5V", "target_component": "Arduino Uno R3", "target_pin": "GND"}
        ]

        with patch("src.services.schematic_service.SchematicService.verify_schematic_connections") as mock_erc:
            mock_erc.return_value = {
                "success": True,
                "is_valid": False,
                "critical_errors_count": 1,
                "violations": [{"rule": "POWER_GROUND_SHORT_CIRCUIT", "message": "Catastrophic short circuit"}],
            }

            res = await service.connect_and_verify_wires(
                connections=connections,
                expected_wire_count=1,
                verify_persistence=True,
                run_schematic_erc=True,
            )

            self.assertFalse(res["success"])
            self.assertIn("schematic ERC found 1 critical violation", res["message"])

    async def test_connect_and_verify_wires_list_of_lists_clear_and_code(self):
        """Supports list-of-lists connection syntax, clear_existing_wires=True, and code injection."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock()
        mock_bm.close_code_panel = AsyncMock()
        mock_bm.close_overlays_and_modals = AsyncMock()

        service = WiringService(mock_bm)
        service.clear_circuit_wires = AsyncMock(return_value={"success": True, "removed_count": 3})
        service.connect_component_pins = AsyncMock(return_value={"success": True, "wire_id": "w_new"})
        service._get_circuit_wires = AsyncMock(return_value=[
            {"id": "w1", "source": {"type": "Arduino Uno R3", "pin": "D2"}, "target": {"type": "Ultrasonic Distance Sensor (4-pin)", "pin": "trig"}},
            {"id": "w2", "source": {"type": "Arduino Uno R3", "pin": "D3"}, "target": {"type": "Ultrasonic Distance Sensor (4-pin)", "pin": "echo"}},
        ])

        mock_page.wait_for_timeout = AsyncMock()
        mock_page.reload = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=True)

        connections = [
            ["Arduino Uno R3", "D2", "Ultrasonic Distance Sensor (4-pin)", "trig", "blue"],
            ["Arduino Uno R3", "D3", "Ultrasonic Distance Sensor (4-pin)", "echo", "green"],
        ]

        dummy_code = "void setup() { pinMode(2, OUTPUT); } void loop() {}"

        with patch("src.services.schematic_service.SchematicService.verify_schematic_connections") as mock_erc, \
             patch("src.services.code_service.CodeService.set_code") as mock_code:
            mock_erc.return_value = {
                "success": True,
                "is_valid": True,
                "critical_errors_count": 0,
                "violations": [],
            }
            mock_code.return_value = {"success": True, "persisted": True}

            res = await service.connect_and_verify_wires(
                connections=connections,
                clear_existing_wires=True,
                code=dummy_code,
                expected_wire_count=2,
                verify_persistence=True,
                run_schematic_erc=True,
            )

            self.assertTrue(res["success"])
            service.clear_circuit_wires.assert_awaited_once_with(verify_persistence=False)
            mock_code.assert_awaited_once_with(code=dummy_code, ensure_text_mode=True, verify_persistence=False)
            self.assertEqual(res["connections_succeeded"], 2)
            self.assertIn("validation", res)
            self.assertEqual(res["validation"]["electrical_safety"], "pass")
            self.assertTrue(res["validation"]["simulation_ready"])


if __name__ == "__main__":
    unittest.main()
