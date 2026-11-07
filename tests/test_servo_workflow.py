"""Unit tests for Micro Servo placement, semantic terminal resolution,
three-wire wiring verification, CodeMirror persistence, and the high-level
add_servo_with_distance_control composite workflow.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.catalog.components_catalog import (
    COMPONENTS_CATALOG,
    find_component_by_query,
    find_component_candidates,
)
from src.browser.browser_manager import BrowserManager
from src.services.circuits_service import CircuitsService
from src.services.components_service import ComponentsService
from src.services.wiring_service import WiringService
from src.services.code_service import CodeService
from src.services.composite_service import CompositeService


class TestMicroServoPlacementAndChevronRejection(unittest.IsolatedAsyncioTestCase):
    """Requirement 1: Exact Micro Servo placement & hidden chevron rejection."""

    def test_servo_catalog_definition(self):
        comp = find_component_by_query("servo")
        self.assertIsNotNone(comp)
        self.assertEqual(comp.id, "servo")
        self.assertEqual(comp.name, "Micro Servo")
        pin_names = [p.name for p in comp.pins]
        self.assertIn("signal", pin_names)
        self.assertIn("power", pin_names)
        self.assertIn("ground", pin_names)

    async def test_add_component_clicks_exact_card_and_skips_chevrons(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_components_drawer_open = AsyncMock(return_value=True)
        mock_bm.is_pointer_intercepted = AsyncMock(return_value=(False, None))

        service = ComponentsService(mock_bm)
        service._get_canvas_bounds = AsyncMock(return_value={"x": 100, "y": 100, "width": 800, "height": 600})

        # JS card_match_info returns exact Micro Servo card with click coordinates
        # and excludes chevrons
        mock_page.evaluate = AsyncMock(side_effect=[
            True,  # _ensure_all_components_category
            [],  # before_instances
            {  # card_match_info
                "selected": {
                    "index": 14,
                    "did": "146740",
                    "title": "Micro Servo",
                    "clickX": 950,
                    "clickY": 450,
                },
                "matches": [{"title": "Micro Servo"}],
            },
            {  # placed_verification
                "verified": True,
                "instance_id": "_servo_1",
                "name": "1",
                "type": "Micro Servo",
                "did": "146740",
                "pins": ["signal", "power", "ground"],
            },
        ])
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.mouse.click = AsyncMock()
        mock_page.mouse.move = AsyncMock()

        res = await service.add_component("Micro Servo", x=700, y=500)
        self.assertTrue(res["success"])
        self.assertEqual(res["component"], "Micro Servo")
        self.assertEqual(res["instance_id"], "_servo_1")
        self.assertEqual(res["position"], {"x": 700, "y": 500})
        # Verify it clicked the exact card position (950, 450) and never dragged
        mock_page.mouse.click.assert_any_call(950, 450)

    async def test_wrong_component_placement_fails(self):
        """If a wrong component was placed (e.g. nMOS transistor instead of Micro Servo), fail explicitly."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_components_drawer_open = AsyncMock(return_value=True)
        mock_bm.is_pointer_intercepted = AsyncMock(return_value=(False, None))

        service = ComponentsService(mock_bm)
        service._get_canvas_bounds = AsyncMock(return_value={"x": 100, "y": 100, "width": 800, "height": 600})

        mock_page.evaluate = AsyncMock(side_effect=[
            True,  # _ensure_all_components_category
            [],
            {
                "selected": {"index": 0, "title": "Micro Servo", "clickX": 950, "clickY": 450},
                "matches": [{"title": "Micro Servo"}],
            },
            {
                "verified": True,
                "instance_id": "_transistor_1",
                "name": "1",
                "type": "Small Signal nMOS Transistor",  # Wrong component!
                "pins": ["drain", "gate", "source"],
            },
        ])
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.mouse.click = AsyncMock()
        mock_page.mouse.move = AsyncMock()

        res = await service.add_component("Micro Servo", x=700, y=500)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "wrong_component_placed")
        self.assertIn("Small Signal nMOS Transistor", res["placed"])


class TestSemanticTerminalResolution(unittest.IsolatedAsyncioTestCase):
    """Requirement 2 & 3: Semantic terminal lookup and three-wire resolution."""

    async def test_resolve_servo_terminals(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock(return_value=True)

        service = WiringService(mock_bm)

        # Mock resolve_terminal for signal, power, ground
        mock_page.evaluate = AsyncMock(side_effect=[
            {"success": True, "component": "Micro Servo", "instance_id": "_s1", "name": "1", "pin": "Signal", "x": 800, "y": 450},
            {"success": True, "component": "Micro Servo", "instance_id": "_s1", "name": "1", "pin": "Power", "x": 800, "y": 460},
            {"success": True, "component": "Micro Servo", "instance_id": "_s1", "name": "1", "pin": "Ground", "x": 800, "y": 470},
        ])

        r_sig = await service.resolve_terminal("Micro Servo", "signal")
        self.assertTrue(r_sig["success"])
        self.assertEqual(r_sig["pin"], "Signal")

        r_pwr = await service.resolve_terminal("Micro Servo", "power")
        self.assertTrue(r_pwr["success"])
        self.assertEqual(r_pwr["pin"], "Power")

        r_gnd = await service.resolve_terminal("Micro Servo", "ground")
        self.assertTrue(r_gnd["success"])
        self.assertEqual(r_gnd["pin"], "Ground")

    async def test_resolve_arduino_terminals(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock(return_value=True)

        service = WiringService(mock_bm)

        mock_page.evaluate = AsyncMock(side_effect=[
            {"success": True, "component": "Arduino Uno R3", "instance_id": "_a1", "name": "1", "pin": "~9", "x": 420, "y": 300},
            {"success": True, "component": "Arduino Uno R3", "instance_id": "_a1", "name": "1", "pin": "5V", "x": 420, "y": 550},
            {"success": True, "component": "Arduino Uno R3", "instance_id": "_a1", "name": "1", "pin": "GND", "x": 420, "y": 560},
        ])

        r_d9 = await service.resolve_terminal("Arduino Uno R3", "D9")
        self.assertTrue(r_d9["success"])
        self.assertEqual(r_d9["pin"], "~9")

        r_5v = await service.resolve_terminal("Arduino Uno R3", "5V")
        self.assertTrue(r_5v["success"])
        self.assertEqual(r_5v["pin"], "5V")

        r_gnd = await service.resolve_terminal("Arduino Uno R3", "GND")
        self.assertTrue(r_gnd["success"])
        self.assertEqual(r_gnd["pin"], "GND")


class TestCompositeAddServoWithDistanceControl(unittest.IsolatedAsyncioTestCase):
    """Requirement 6: High-level composite operation tinkercad_add_servo_with_distance_control."""

    async def test_add_servo_workflow_success(self):
        mock_circuits = MagicMock(spec=CircuitsService)
        mock_components = MagicMock(spec=ComponentsService)
        mock_wiring = MagicMock(spec=WiringService)
        mock_code = MagicMock(spec=CodeService)

        # 1. Existing circuit has ultrasonic (D2, D3) and buzzer (D11)
        mock_circuits.inspect_circuit = AsyncMock(return_value={
            "success": True,
            "components": [
                {
                    "type": "Arduino Uno R3",
                    "pins": [
                        {"name": "D2", "connected": True},
                        {"name": "D3", "connected": True},
                        {"name": "D11", "connected": True},
                        {"name": "D9", "connected": False},
                    ],
                }
            ],
            "wires": [],
        })

        # 2. Add component succeeds
        mock_components.add_component = AsyncMock(return_value={
            "success": True,
            "component": "Micro Servo",
            "instance_id": "_servo_1",
            "position": {"x": 700, "y": 500},
        })

        # 3. Wiring all 3 connections succeeds
        mock_wiring.connect_component_pins = AsyncMock(side_effect=[
            {"success": True, "wire_id": "_wire_sig", "source": {"pin": "signal"}, "target": {"pin": "D9"}},
            {"success": True, "wire_id": "_wire_pwr", "source": {"pin": "power"}, "target": {"pin": "5V"}},
            {"success": True, "wire_id": "_wire_gnd", "source": {"pin": "ground"}, "target": {"pin": "GND"}},
        ])

        # 4. Code service
        original_code = (
            "int trigger_pin = 2;\n"
            "int echo_pin = 3;\n"
            "int buzzer_pin = 11;\n"
            "void setup() {}\n"
            "void loop() {\n"
            "  int distance = 20;\n"
            "}\n"
        )
        mock_code.get_code = AsyncMock(return_value={"success": True, "code": original_code})
        mock_code.set_code = AsyncMock(return_value={"success": True, "verified": True})

        composite = CompositeService(
            circuits=mock_circuits,
            components=mock_components,
            wiring=mock_wiring,
            code=mock_code,
        )

        res = await composite.add_servo_with_distance_control(
            distance_threshold=30,
            angle_when_near=150,
            angle_when_far=0,
            signal_pin=None,  # Should auto-select unused PWM pin D9!
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["servo"]["signal_pin"], "D9")
        self.assertEqual(len(res["wires"]), 3)
        self.assertTrue(res["code"]["verified"])

        # Verify CodeMirror set_code was called with Servo code
        code_args = mock_code.set_code.call_args[0][0]
        self.assertIn("#include <Servo.h>", code_args)
        self.assertIn("distance_servo.attach", code_args)
        self.assertIn("distance_servo.write(150)", code_args)

    async def test_add_servo_fails_if_any_wire_fails(self):
        """If power or ground wire fails, composite tool must fail explicitly without false success."""
        mock_circuits = MagicMock(spec=CircuitsService)
        mock_components = MagicMock(spec=ComponentsService)
        mock_wiring = MagicMock(spec=WiringService)
        mock_code = MagicMock(spec=CodeService)

        mock_circuits.inspect_circuit = AsyncMock(return_value={"components": []})
        mock_components.add_component = AsyncMock(return_value={"success": True})

        # Signal succeeds, power fails
        mock_wiring.connect_component_pins = AsyncMock(side_effect=[
            {"success": True, "wire_id": "_w1"},
            {"success": False, "message": "Terminal 5V could not be located"},
        ])

        composite = CompositeService(
            circuits=mock_circuits,
            components=mock_components,
            wiring=mock_wiring,
            code=mock_code,
        )

        res = await composite.add_servo_with_distance_control()
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "wiring_failed")
        self.assertEqual(res["failed_wire"], "power")
        mock_code.set_code.assert_not_called()


class TestStructuredInspectionOutput(unittest.IsolatedAsyncioTestCase):
    """Requirement 4: inspect_circuit returns components, pins with connected_to, and wires without screenshots."""

    async def test_inspect_circuit_structure(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_page.url = "https://www.tinkercad.com/things/test-circuit-demo/editel"
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.take_screenshot = AsyncMock()

        service = CircuitsService(mock_bm)
        service._get_current_title = AsyncMock(return_value="Super Krunk")

        # Mock page.evaluate returning structured circuit inspection
        mock_page.evaluate = AsyncMock(return_value={
            "components": [
                {
                    "instance_id": "_servo_1",
                    "type": "Micro Servo",
                    "name": "1",
                    "did": "146740",
                    "position": {"x": 700, "y": 500},
                    "pins": [
                        {
                            "name": "signal",
                            "connected": True,
                            "connected_to": {
                                "instance_id": "_arduino_1",
                                "component": "Arduino Uno R3",
                                "pin": "D9",
                            },
                        },
                        {
                            "name": "power",
                            "connected": True,
                            "connected_to": {
                                "instance_id": "_arduino_1",
                                "component": "Arduino Uno R3",
                                "pin": "5V",
                            },
                        },
                        {
                            "name": "ground",
                            "connected": True,
                            "connected_to": {
                                "instance_id": "_arduino_1",
                                "component": "Arduino Uno R3",
                                "pin": "GND",
                            },
                        },
                    ],
                }
            ],
            "wires": [
                {
                    "wire_id": "_w1",
                    "color": "orange",
                    "source": {"component": "Micro Servo", "pin": "signal"},
                    "target": {"component": "Arduino Uno R3", "pin": "D9"},
                }
            ],
            "simulation_running": False,
        })

        res = await service.inspect_circuit()
        self.assertTrue(res["success"])
        self.assertEqual(len(res["components"]), 1)
        servo = res["components"][0]
        self.assertEqual(servo["type"], "Micro Servo")
        self.assertTrue(servo["pins"][0]["connected"])
        self.assertEqual(servo["pins"][0]["connected_to"]["pin"], "D9")

        # Zero screenshot calls
        mock_bm.take_screenshot.assert_not_called()


class TestArduinoGndResolutionAndBreadboardFallback(unittest.IsolatedAsyncioTestCase):
    """Test distinct GND pin resolution and automated Breadboard ground routing when pins are occupied."""

    async def test_distinct_gnd1_gnd2_gnd3_coordinates(self):
        """Arduino GND1 (5V), GND2 (VIN), and GND3 (digital header) must resolve to distinct coordinates."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock(return_value=True)

        service = WiringService(mock_bm)

        # Mock page.evaluate returning distinct coordinates for GND1, GND2, GND3
        mock_page.evaluate = AsyncMock(side_effect=[
            {"success": True, "component": "Arduino Uno R3", "pin": "GND1", "x": 413, "y": 491},
            {"success": True, "component": "Arduino Uno R3", "pin": "GND2", "x": 404, "y": 491},
            {"success": True, "component": "Arduino Uno R3", "pin": "GND3", "x": 352, "y": 314},
        ])

        r1 = await service.resolve_terminal("Arduino Uno R3", "GND1")
        r2 = await service.resolve_terminal("Arduino Uno R3", "GND2")
        r3 = await service.resolve_terminal("Arduino Uno R3", "GND3")

        self.assertTrue(r1["success"])
        self.assertTrue(r2["success"])
        self.assertTrue(r3["success"])

        # Coordinates must be distinct
        pos1 = (r1["x"], r1["y"])
        pos2 = (r2["x"], r2["y"])
        pos3 = (r3["x"], r3["y"])
        self.assertNotEqual(pos1, pos2)
        self.assertNotEqual(pos1, pos3)
        self.assertNotEqual(pos2, pos3)

    async def test_generic_gnd_skips_occupied_buzzer_pin_and_selects_free_pin(self):
        """When GND1 is wired to the buzzer, resolving 'GND' must select a free GND pin (e.g. GND2 or GND3)."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock(return_value=True)

        service = WiringService(mock_bm)

        # Mock page.evaluate returning GND2 as the selected free pin
        mock_page.evaluate = AsyncMock(return_value={
            "success": True,
            "component": "Arduino Uno R3",
            "instance_id": "_arduino_1",
            "name": "1",
            "pin": "GND2",
            "x": 404,
            "y": 491,
            "all_gnd_occupied": False,
        })

        res = await service.resolve_terminal("Arduino Uno R3", "GND")
        self.assertTrue(res["success"])
        # Selected unused pin instead of occupied GND1
        self.assertEqual(res["pin"], "GND2")
        self.assertFalse(res.get("all_gnd_occupied", False))

    async def test_all_gnd_occupied_triggers_breadboard_routing(self):
        """When all Arduino GND pins are occupied, connect_component_pins routes via Breadboard."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock(return_value=True)

        service = WiringService(mock_bm)

        # Servo ground succeeds
        servo_term = {"success": True, "component": "Micro Servo", "instance_id": "_s1", "name": "1", "pin": "Ground", "x": 800, "y": 470}
        # Arduino GND query returns all_gnd_occupied
        arduino_term = {
            "success": False,
            "all_gnd_occupied": True,
            "error": "all_arduino_gnd_occupied",
            "message": "All 3 Arduino GND pins (GND1, GND2, GND3) are already connected.",
        }

        service.resolve_terminal = AsyncMock(side_effect=[servo_term, arduino_term])
        service.route_pin_via_breadboard = AsyncMock(return_value={
            "success": True,
            "routed_via_breadboard": True,
            "wire_id": "_w_bb_gnd",
            "component": "Micro Servo",
            "pin": "ground",
            "breadboard_pin": "-",
            "rail": "ground",
            "color": "black",
        })

        res = await service.connect_component_pins(
            source_component="Micro Servo",
            source_pin="ground",
            target_component="Arduino Uno R3",
            target_pin="GND",
            color="black",
        )

        self.assertTrue(res["success"])
        self.assertTrue(res.get("routed_via_breadboard"))
        service.route_pin_via_breadboard.assert_called_once_with(
            component="Micro Servo",
            pin="ground",
            rail="ground",
            color="black",
            microcontroller_name="Arduino Uno R3",
        )

    async def test_route_pin_via_breadboard_workflow(self):
        """route_pin_via_breadboard places breadboard if missing, links rail, and connects component."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock(return_value=True)

        service = WiringService(mock_bm)
        mock_page.evaluate = AsyncMock(return_value="_bb_1")  # Breadboard already present
        mock_page.wait_for_timeout = AsyncMock()

        # Existing wires: Breadboard rail already connected to Arduino GND
        service._get_circuit_wires = AsyncMock(return_value=[
            {
                "id": "_link_wire",
                "source": {"type": "Arduino Uno R3", "name": "1", "pin": "GND1"},
                "target": {"type": "Breadboard Small", "name": "1", "pin": "-"},
            }
        ])

        # Connect servo ground to Breadboard (-)
        service.connect_component_pins = AsyncMock(return_value={
            "success": True,
            "wire_id": "_w_servo_bb",
        })

        res = await service.route_pin_via_breadboard(
            component="Micro Servo",
            pin="ground",
            rail="ground",
            color="black",
        )

        self.assertTrue(res["success"])
        self.assertTrue(res["routed_via_breadboard"])
        self.assertEqual(res["wire_id"], "_w_servo_bb")
        self.assertEqual(res["breadboard_pin"], "-")
        service.connect_component_pins.assert_called_once_with(
            source_component="Micro Servo",
            source_pin="ground",
            target_component="Breadboard Small",
            target_pin="-",
            color="black",
        )


if __name__ == "__main__":
    unittest.main()
