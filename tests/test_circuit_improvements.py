"""Unit tests covering the 10 circuit improvement requirements:
1. Exact DC Motor selection
2. Micro Servo must not be selected for a DC Motor request
3. nMOS Transistor must not be selected for a DC Motor request
4. Ambiguous component matches must fail explicitly
5. Overlay handling
6. Semantic pin lookup
7. Successful wire verification
8. Failed wire verification
9. Structured inspect_circuit response schema
10. No screenshot call is made during normal inspection or wiring
"""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.catalog.components_catalog import (
    COMPONENTS_CATALOG,
    find_component_by_did,
    find_component_by_query,
    find_component_candidates,
)
from src.browser.browser_manager import BrowserManager
from src.services.circuits_service import CircuitsService
from src.services.components_service import ComponentsService
from src.services.wiring_service import WiringService


class TestRequirement1ExactDCMotorSelection(unittest.TestCase):
    """1. Exact DC Motor selection."""

    def test_exact_dc_motor_name_lookup(self):
        comp = find_component_by_query("DC Motor")
        self.assertIsNotNone(comp)
        self.assertEqual(comp.id, "dc_motor")
        self.assertEqual(comp.name, "DC Motor")

    def test_exact_dc_motor_id_lookup(self):
        comp = find_component_by_query("dc_motor")
        self.assertIsNotNone(comp)
        self.assertEqual(comp.id, "dc_motor")
        self.assertEqual(comp.name, "DC Motor")

    def test_exact_dc_motor_did_lookup(self):
        comp = find_component_by_did("114158")
        self.assertIsNotNone(comp)
        self.assertEqual(comp.id, "dc_motor")


class TestRequirement2MicroServoNotSelectedForDCMotor(unittest.TestCase):
    """2. Micro Servo must not be selected for a DC Motor request."""

    def test_servo_not_selected_for_dc_motor_query(self):
        comp = find_component_by_query("DC Motor")
        self.assertNotEqual(comp.id, "servo")
        self.assertEqual(comp.id, "dc_motor")

    def test_servo_not_selected_for_dc_motor_id(self):
        comp = find_component_by_query("dc_motor")
        self.assertNotEqual(comp.id, "servo")

    def test_servo_selected_only_for_servo_query(self):
        servo_comp = find_component_by_query("Micro Servo")
        self.assertIsNotNone(servo_comp)
        self.assertEqual(servo_comp.id, "servo")


class TestRequirement3NMOSTransistorNotSelectedForDCMotor(unittest.TestCase):
    """3. nMOS Transistor must not be selected for a DC Motor request."""

    def test_transistor_not_selected_for_dc_motor(self):
        comp = find_component_by_query("DC Motor")
        self.assertNotIn("transistor", comp.id.lower())
        self.assertNotIn("nmos", comp.id.lower())
        self.assertEqual(comp.id, "dc_motor")

    def test_transistor_did_does_not_match_dc_motor(self):
        # 114158 is DC Motor; Transistor is 58422 or other
        motor_comp = find_component_by_did("114158")
        self.assertEqual(motor_comp.id, "dc_motor")


class TestRequirement4AmbiguousComponentMatchesFailExplicitly(unittest.IsolatedAsyncioTestCase):
    """4. Ambiguous component matches must fail explicitly."""

    def test_catalog_query_ambiguity_returns_multiple_candidates(self):
        # 'motor' matches both 'servo' and 'dc_motor' in keywords
        cands = find_component_candidates("motor")
        self.assertGreater(len(cands), 1)
        # Because it's ambiguous, find_component_by_query returns None
        self.assertIsNone(find_component_by_query("motor"))

    async def test_components_service_ambiguous_match_error_response(self):
        mock_bm = MagicMock(spec=BrowserManager)
        service = ComponentsService(mock_bm)

        # Call with ambiguous query 'motor'
        res = await service.add_component("motor")
        self.assertFalse(res["success"])
        self.assertEqual(res.get("error"), "ambiguous_component_match")
        self.assertIn("matches", res)
        self.assertIn("Micro Servo", res["matches"])
        self.assertIn("DC Motor", res["matches"])


class TestRequirement5OverlayHandling(unittest.IsolatedAsyncioTestCase):
    """5. Overlay handling (closing code panel, modals, detecting pointer interception)."""

    async def test_close_code_panel_when_active(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        # Simulate active code panel
        mock_page.evaluate = AsyncMock(return_value=True)

        mock_locator = AsyncMock()
        mock_locator.is_visible = AsyncMock(return_value=True)
        mock_locator.click = AsyncMock()
        mock_page.locator = MagicMock(return_value=mock_locator)

        bm = BrowserManager()
        bm.find_first_matching = AsyncMock(return_value=mock_locator)

        closed = await bm.close_code_panel(page=mock_page)
        self.assertTrue(closed)
        mock_locator.click.assert_awaited_once()

    async def test_close_overlays_and_modals(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=True)
        mock_page.keyboard = AsyncMock()

        bm = BrowserManager()
        bm.find_first_matching = AsyncMock(return_value=None)

        closed = await bm.close_overlays_and_modals(page=mock_page)
        self.assertTrue(closed)
        mock_page.keyboard.press.assert_awaited_with("Escape")

    async def test_pointer_interception_detection(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value="js-tpl-target__code_panel")

        bm = BrowserManager()
        intercepted, blocker = await bm.is_pointer_intercepted(500, 300, page=mock_page)
        self.assertTrue(intercepted)
        self.assertIn("code_panel", blocker)


class TestRequirement6SemanticPinLookup(unittest.TestCase):
    """6. Semantic pin lookup."""

    def test_arduino_uno_pin_definitions(self):
        arduino = COMPONENTS_CATALOG["arduino_uno"]
        pin_names = {p.name for p in arduino.pins}
        self.assertIn("D6", pin_names)
        self.assertIn("D13", pin_names)
        self.assertIn("5V", pin_names)
        self.assertIn("GND_1", pin_names)
        self.assertIn("A0", pin_names)

    def test_dc_motor_pin_definitions(self):
        motor = COMPONENTS_CATALOG["dc_motor"]
        pin_names = {p.name for p in motor.pins}
        self.assertIn("terminal_1", pin_names)
        self.assertIn("terminal_2", pin_names)


class TestRequirement7And8WireVerification(unittest.IsolatedAsyncioTestCase):
    """7. Successful wire verification and 8. Failed wire verification."""

    async def test_failed_wire_verification_returns_error(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock(return_value=True)

        service = WiringService(mock_bm)
        # Mock _get_circuit_wires to return empty before and after (no wire created)
        service._get_circuit_wires = AsyncMock(return_value=[])
        service._select_wire_color = AsyncMock()

        res = await service.connect_pins(from_x=100, from_y=100, to_x=200, to_y=200)
        self.assertFalse(res["success"])
        self.assertEqual(res.get("error"), "wire_verification_failed")
        self.assertIn("no wire connection was created", res.get("message", ""))

    async def test_successful_wire_verification_returns_created_wire(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock(return_value=True)

        service = WiringService(mock_bm)
        before = [{"id": "_1"}]
        after = [{"id": "_1"}, {"id": "_2", "color": "green", "source": {"component": "Arduino Uno R3"}, "target": {"component": "DC Motor"}}]

        service._get_circuit_wires = AsyncMock(side_effect=[before, after])
        service._select_wire_color = AsyncMock()

        res = await service.connect_pins(from_x=435, from_y=460, to_x=1013, to_y=730, color="green")
        self.assertTrue(res["success"])
        self.assertEqual(res.get("wire_id"), "_2")
        self.assertIn("resolved_endpoints", res)


class TestRequirement9StructuredInspectCircuitResponseSchema(unittest.IsolatedAsyncioTestCase):
    """9. Structured inspect_circuit response schema."""

    async def test_inspect_circuit_schema(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_page.url = "https://www.tinkercad.com/things/test-circuit-demo/editel"
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        service = CircuitsService(mock_bm)
        service._get_current_title = AsyncMock(return_value="Exquisite Duup-Luulia")

        mock_data = {
            "components": [
                {
                    "instance_id": "_308",
                    "type": "DC Motor",
                    "name": "2",
                    "did": "114158",
                    "position": {"x": 718, "y": 232},
                    "pins": [
                        {
                            "name": "1",
                            "connected": True,
                            "connections": [
                                {
                                    "wire_id": "_266",
                                    "color": "green",
                                    "connected_to": {
                                        "instance_id": "_275",
                                        "component": "Arduino Uno R3",
                                        "name": "3",
                                        "pin": "D6",
                                    },
                                }
                            ],
                        },
                        {"name": "2", "connected": False, "connections": []},
                    ],
                }
            ],
            "wires": [
                {
                    "wire_id": "_266",
                    "color": "green",
                    "source": {"instance_id": "_275", "component": "Arduino Uno R3", "name": "3", "pin": "D6"},
                    "target": {"instance_id": "_308", "component": "DC Motor", "name": "2", "pin": "1"},
                }
            ],
            "simulation_running": False,
        }
        mock_page.evaluate = AsyncMock(return_value=mock_data)

        res = await service.inspect_circuit()

        # Validate schema
        self.assertTrue(res["success"])
        self.assertEqual(res["circuit_id"], "test-circuit-demo")
        self.assertEqual(res["title"], "Exquisite Duup-Luulia")
        self.assertIn("components", res)
        self.assertIn("wires", res)
        self.assertIsInstance(res["components"], list)
        self.assertIsInstance(res["wires"], list)
        self.assertEqual(len(res["components"]), 1)
        self.assertEqual(len(res["wires"]), 1)

        comp = res["components"][0]
        self.assertEqual(comp["type"], "DC Motor")
        self.assertEqual(comp["name"], "2")
        self.assertTrue(comp["pins"][0]["connected"])

        wire = res["wires"][0]
        self.assertEqual(wire["color"], "green")
        self.assertEqual(wire["target"]["component"], "DC Motor")


class TestRequirement10NoScreenshotCallDuringNormalOperations(unittest.IsolatedAsyncioTestCase):
    """10. No screenshot call is made during normal inspection or wiring."""

    async def test_inspect_circuit_makes_no_screenshot_call(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_page.url = "https://www.tinkercad.com/things/test-circuit-demo/editel"
        mock_page.evaluate = AsyncMock(return_value={"components": [], "wires": []})
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.take_screenshot = AsyncMock()

        service = CircuitsService(mock_bm)
        service._get_current_title = AsyncMock(return_value="Test Circuit")

        await service.inspect_circuit()
        # Verify ZERO calls to take_screenshot
        mock_bm.take_screenshot.assert_not_called()

    async def test_wiring_makes_no_screenshot_call(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock(return_value=True)
        mock_bm.take_screenshot = AsyncMock()

        service = WiringService(mock_bm)
        service._get_circuit_wires = AsyncMock(side_effect=[[], [{"id": "_1"}]])
        service._select_wire_color = AsyncMock()

        await service.connect_pins(from_x=100, from_y=100, to_x=200, to_y=200)
        # Verify ZERO calls to take_screenshot
        mock_bm.take_screenshot.assert_not_called()


if __name__ == "__main__":
    unittest.main()
