"""Unit tests covering the AI testing agent review requirements:
1. Exact 4-pin Ultrasonic Distance Sensor (HC-SR04) selection and 3-pin rejection.
2. Safe motor architecture:
   - H-bridge Motor Driver (L293D) catalog & 16-pin mapping.
   - Detection and rejection of direct DC motor-to-Arduino I/O pin connections (>40 mA overcurrent violation).
3. Pre-simulation circuit validation (electrical safety, motor driver presence, code mode verification).
4. Workspace switcher view changing (Circuits, Schematic, Components).
5. Transactional robot car creation with external power supply and verified obstacle-stop code.
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
from src.services.code_service import CodeService
from src.services.composite_service import CompositeService


class TestUltrasonicSensorDisambiguationAndPinCount(unittest.TestCase):
    """Requirement: Select exact 4-pin Ultrasonic Distance Sensor / HC-SR04 when code uses trig and echo.
    Reject 3-pin ultrasonic components for trigger/echo workflows.
    """

    def test_ultrasonic_4pin_catalog_definition(self):
        comp = find_component_by_query("ultrasonic_sensor_4pin")
        self.assertIsNotNone(comp)
        self.assertEqual(comp.id, "ultrasonic_sensor_4pin")
        self.assertEqual(comp.name, "Ultrasonic Distance Sensor (4-pin)")
        self.assertEqual(comp.did, "219295")
        pin_names = [p.name for p in comp.pins]
        self.assertEqual(len(pin_names), 4)
        self.assertIn("pos", pin_names)
        self.assertIn("trig", pin_names)
        self.assertIn("echo", pin_names)
        self.assertIn("neg", pin_names)

    def test_ultrasonic_3pin_catalog_definition(self):
        comp = find_component_by_query("ultrasonic_sensor_3pin")
        self.assertIsNotNone(comp)
        self.assertEqual(comp.id, "ultrasonic_sensor_3pin")
        self.assertEqual(comp.name, "Ultrasonic Distance Sensor")
        self.assertEqual(comp.did, "219294")
        pin_names = [p.name for p in comp.pins]
        self.assertEqual(len(pin_names), 3)
        self.assertIn("sig", pin_names)
        self.assertIn("pos", pin_names)
        self.assertIn("neg", pin_names)
        self.assertNotIn("trig", pin_names)
        self.assertNotIn("echo", pin_names)

    def test_default_ultrasonic_query_picks_4pin_hc_sr04(self):
        # Queries for ultrasonic / hc-sr04 / sonar default to 4-pin HC-SR04
        for q in ["ultrasonic", "ultrasonic sensor", "HC-SR04", "sonar", "distance sensor"]:
            comp = find_component_by_query(q)
            self.assertIsNotNone(comp, f"Failed for query: {q}")
            self.assertEqual(comp.id, "ultrasonic_sensor_4pin")
            self.assertEqual(comp.did, "219295")

    def test_3pin_explicit_query_picks_3pin_sensor(self):
        # Explicit query for 3-pin sensor picks 3-pin Ping sensor
        for q in ["3-pin ultrasonic", "ultrasonic 3 pin", "3pin sonar", "ultrasonic_sensor_3pin"]:
            comp = find_component_by_query(q)
            self.assertIsNotNone(comp, f"Failed for query: {q}")
            self.assertEqual(comp.id, "ultrasonic_sensor_3pin")
            self.assertEqual(comp.did, "219294")

    def test_query_with_required_pins_trig_echo_resolves_4pin(self):
        comp = find_component_by_query("ultrasonic", required_pins=["trig", "echo"])
        self.assertIsNotNone(comp)
        self.assertEqual(comp.id, "ultrasonic_sensor_4pin")


class TestSafeMotorArchitectureAndDriver(unittest.TestCase):
    """Requirement: Never connect DC motors directly to Arduino I/O pins (>40 mA limit).
    Provide L293D H-bridge motor driver with external supply.
    """

    def test_hbridge_driver_catalog_definition(self):
        comp = find_component_by_query("hbridge_motor_driver")
        self.assertIsNotNone(comp)
        self.assertEqual(comp.id, "hbridge_motor_driver")
        self.assertEqual(comp.name, "H-bridge Motor Driver")
        self.assertEqual(comp.did, "112326")
        self.assertEqual(len(comp.pins), 16)

        pin_names = [p.name for p in comp.pins]
        expected_pins = [
            "Enable1", "Input1", "Output1", "GND", "GND1", "Output2", "Input2", "Vs",
            "Enable2", "Input3", "Output3", "GND2", "GND3", "Output4", "Input4", "Vss"
        ]
        for ep in expected_pins:
            self.assertIn(ep, pin_names)

    def test_find_motor_driver_by_common_aliases(self):
        for q in ["l293d", "l293", "h-bridge", "hbridge", "motor driver", "H-bridge Motor Driver"]:
            comp = find_component_by_query(q)
            self.assertIsNotNone(comp, f"Failed for query: {q}")
            self.assertEqual(comp.id, "hbridge_motor_driver")


class TestElectricalSafetyAndOvercurrentRejection(unittest.IsolatedAsyncioTestCase):
    """Requirement: Validate circuit electrical safety and prevent direct DC motor-to-Arduino connections."""

    async def test_direct_motor_connection_detected_in_safety_check(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        service = WiringService(mock_bm)
        sample_wires = [
            {
                "id": "_wire_unsafe_1",
                "color": "green",
                "source": {"type": "Arduino Uno R3", "pin": "D6", "name": "1"},
                "target": {"type": "DC Motor", "pin": "Terminal 1", "name": "Motor 1"},
            },
            {
                "id": "_wire_unsafe_2",
                "color": "green",
                "source": {"type": "Arduino Uno R3", "pin": "D7", "name": "1"},
                "target": {"type": "DC Motor", "pin": "Terminal 1", "name": "Motor 2"},
            },
        ]
        service._get_circuit_wires = AsyncMock(return_value=sample_wires)

        # Mock evaluate returning safety check analysis
        mock_page.evaluate = AsyncMock(return_value={
            "is_safe": False,
            "violations_count": 2,
            "warnings_count": 1,
            "violations": [
                {
                    "rule": "OVERCURRENT_I_O_PIN",
                    "severity": "CRITICAL",
                    "message": "Direct connection between Motor 1 and Arduino I/O pin D6 exceeds safe 40 mA limit (measured/estimated ~44.4 mA).",
                },
                {
                    "rule": "OVERCURRENT_I_O_PIN",
                    "severity": "CRITICAL",
                    "message": "Direct connection between Motor 2 and Arduino I/O pin D7 exceeds safe 40 mA limit (measured/estimated ~44.4 mA).",
                },
            ],
            "warnings": [
                {
                    "rule": "MISSING_MOTOR_DRIVER",
                    "severity": "HIGH",
                    "message": "Circuit contains DC motors but no H-bridge Motor Driver (L293D).",
                }
            ],
            "direct_motor_connections": [
                {"motor": "Motor 1", "arduino_pin": "D6", "estimated_current_ma": 44.4},
                {"motor": "Motor 2", "arduino_pin": "D7", "estimated_current_ma": 44.4},
            ],
            "circuit_overview": {"has_arduino": True, "has_motor_driver": False, "has_motors": True},
        })

        res = await service.check_circuit_electrical_safety()
        self.assertFalse(res["is_safe"])
        self.assertEqual(res["violations_count"], 2)
        self.assertIn("OVERCURRENT_I_O_PIN", [v["rule"] for v in res["violations"]])
        self.assertIn("D6", res["violations"][0]["message"])

    async def test_connect_component_pins_rejects_direct_motor_unless_forced(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        service = WiringService(mock_bm)

        # Attempt to connect Arduino D6 directly to DC Motor Terminal 1 without allow_unsafe_direct
        res = await service.connect_component_pins(
            source_component="Arduino Uno R3",
            source_pin="D6",
            target_component="DC Motor",
            target_pin="Terminal 1",
            allow_unsafe_direct=False,
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "electrical_safety_violation")
        self.assertIn("40 mA", res["message"])
        self.assertIn("H-bridge Motor Driver", res["recommendation"])


class TestPreSimulationCircuitValidation(unittest.IsolatedAsyncioTestCase):
    """Requirement: Comprehensive pre-simulation checks."""

    async def test_pre_simulation_fails_when_safety_violations_exist(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        circuits_service = CircuitsService(mock_bm)
        circuits_service.inspect_circuit = AsyncMock(return_value={
            "success": True,
            "title": "Robot Car",
            "components": [{"type": "Arduino Uno R3"}, {"type": "DC Motor"}],
            "wires": [{"id": "_1"}],
        })

        with patch("src.services.wiring_service.WiringService.check_circuit_electrical_safety") as mock_safety:
            mock_safety.return_value = {
                "is_safe": False,
                "violations_count": 1,
                "violations": [{"rule": "OVERCURRENT_I_O_PIN", "message": "Direct motor connection to D6"}],
                "circuit_overview": {"has_arduino": True, "has_motors": True, "has_motor_driver": False},
            }
            with patch("src.services.code_service.CodeService.get_code") as mock_code:
                mock_code.return_value = {"success": True, "mode": "Text", "code": "void setup(){}"}
                res = await circuits_service.validate_circuit_pre_simulation()
                self.assertTrue(res["success"])
                self.assertFalse(res["ready_for_simulation"])
                self.assertIn("failed", res["message"].lower())

    async def test_pre_simulation_passes_for_safe_circuit(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        circuits_service = CircuitsService(mock_bm)
        circuits_service.inspect_circuit = AsyncMock(return_value={
            "success": True,
            "title": "Safe Robot Car",
            "components": [
                {"type": "Arduino Uno R3"},
                {"type": "H-bridge Motor Driver"},
                {"type": "DC Motor"},
                {"type": "Ultrasonic Distance Sensor (4-pin)"},
            ],
            "wires": [{"id": "_1"}, {"id": "_2"}],
        })

        with patch("src.services.wiring_service.WiringService.check_circuit_electrical_safety") as mock_safety:
            mock_safety.return_value = {
                "is_safe": True,
                "violations_count": 0,
                "violations": [],
                "circuit_overview": {
                    "has_arduino": True,
                    "has_motors": True,
                    "has_motor_driver": True,
                    "has_external_battery": True,
                },
            }

            with patch("src.services.code_service.CodeService.get_code") as mock_code:
                mock_code.return_value = {
                    "success": True,
                    "mode": "Text",
                    "code": "const int trigPin = 2;\nconst int echoPin = 3;\nconst int m1 = 4;\n",
                }

                res = await circuits_service.validate_circuit_pre_simulation()
                self.assertTrue(res["success"])
                self.assertTrue(res["ready_for_simulation"])
                self.assertIn("ready to simulate", res["message"].lower())


class TestWorkspaceSwitcher(unittest.IsolatedAsyncioTestCase):
    """Requirement: Workspace switcher buttons (Circuits, Schematic, Components)."""

    async def test_switch_workspace_view_schematic(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.click = AsyncMock()
        mock_page.locator = MagicMock(return_value=mock_locator)
        mock_bm.find_first_matching = AsyncMock(return_value=mock_locator)
        mock_page.evaluate = AsyncMock(return_value=True)

        service = CircuitsService(mock_bm)
        res = await service.switch_workspace_view("schematic")
        self.assertTrue(res["success"])
        self.assertEqual(res["target_view"], "Schematic")
        self.assertTrue(res["is_active"])
        mock_locator.click.assert_awaited_once()

    async def test_switch_workspace_view_invalid_name_fails(self):
        service = CircuitsService(MagicMock(spec=BrowserManager))
        res = await service.switch_workspace_view("non_existent_view")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "invalid_view")


class TestEmptyCircuitValidationAndCreation(unittest.IsolatedAsyncioTestCase):
    """Requirement: Empty circuit validation, dashboard navigation, and 404 rejection."""

    async def test_pre_simulation_fails_on_empty_circuit(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        circuits_service = CircuitsService(mock_bm)
        circuits_service.inspect_circuit = AsyncMock(return_value={
            "success": True,
            "title": "Empty Circuit",
            "components": [],
            "wires": [],
        })

        with patch("src.services.wiring_service.WiringService.check_circuit_electrical_safety") as mock_safety:
            mock_safety.return_value = {
                "is_safe": True,
                "violations_count": 0,
                "violations": [],
                "circuit_overview": {"has_arduino": False, "has_motors": False, "has_motor_driver": False},
            }
            with patch("src.services.code_service.CodeService.get_code") as mock_code:
                mock_code.return_value = {"success": True, "mode": "none", "code": ""}
                res = await circuits_service.validate_circuit_pre_simulation()
                self.assertTrue(res["success"])
                self.assertFalse(res["ready_for_simulation"])
                self.assertIn("failed", res["message"].lower())
                failures = [c["name"] for c in res["checks"] if c["status"] == "fail"]
                self.assertIn("Component Integrity", failures)

    async def test_pre_simulation_fails_on_unconnected_arduino(self):
        mock_bm = MagicMock(spec=BrowserManager)
        circuits_service = CircuitsService(mock_bm)
        circuits_service.inspect_circuit = AsyncMock(return_value={
            "success": True,
            "title": "Unconnected Arduino",
            "components": [{"type": "Arduino Uno R3"}],
            "wires": [],
        })

        with patch("src.services.wiring_service.WiringService.check_circuit_electrical_safety") as mock_safety:
            mock_safety.return_value = {
                "is_safe": True,
                "violations_count": 0,
                "violations": [],
                "circuit_overview": {"has_arduino": True, "has_motors": False, "has_motor_driver": False},
            }
            with patch("src.services.code_service.CodeService.get_code") as mock_code:
                mock_code.return_value = {"success": True, "mode": "Text", "code": "void setup(){}"}
                res = await circuits_service.validate_circuit_pre_simulation()
                self.assertTrue(res["success"])
                self.assertFalse(res["ready_for_simulation"])
                failures = [c["name"] for c in res["checks"] if c["status"] == "fail"]
                self.assertIn("Wiring Integrity", failures)

    async def test_create_circuit_via_dashboard_navigates_and_verifies_canvas(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_page.url = "https://www.tinkercad.com/things/test-circuit-demo/editel"
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.wait_for_url = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body><div id='breadboardTab'></div></body></html>")
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.navigate = AsyncMock(return_value=mock_page)

        # Mock create button, circuits menu click, and canvas
        mock_btn = AsyncMock()
        mock_btn.click = AsyncMock()
        mock_canvas = AsyncMock()
        mock_bm.find_first_matching = AsyncMock(side_effect=[mock_btn, mock_btn, mock_canvas, None, None])

        # Canvas check evaluation returns canvas_count = 1
        mock_page.evaluate = AsyncMock(side_effect=[
            False,  # is_missing (404 check)
            1,      # canvas_count
            "dune", # current title
        ])

        circuits_service = CircuitsService(mock_bm)
        res = await circuits_service.create_circuit(title="dune")
        self.assertTrue(res["success"])
        self.assertEqual(res["circuit_id"], "test-circuit-demo")
        mock_bm.navigate.assert_any_call("https://www.tinkercad.com/dashboard?type=circuits", wait_until="domcontentloaded", timeout=35000)

    async def test_create_circuit_fails_if_page_is_404(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_page.url = "https://www.tinkercad.com/things/new?type=circuits"
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.wait_for_url = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>Sorry, that page is missing</body></html>")
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.navigate = AsyncMock(return_value=mock_page)

        mock_btn = AsyncMock()
        mock_btn.click = AsyncMock()
        mock_bm.find_first_matching = AsyncMock(return_value=mock_btn)
        mock_page.evaluate = AsyncMock(return_value=True)  # is_missing: True

        circuits_service = CircuitsService(mock_bm)
        res = await circuits_service.create_circuit(title="dune")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "circuit_creation_failed")
        self.assertIn("Sorry, that page is missing", res["message"])


class TestPiezoWiringAndEndpointDisambiguation(unittest.IsolatedAsyncioTestCase):
    """Requirement: Piezo terminal resolution, avoiding negative -> positive mapping, and index query isolation."""

    def test_piezo_negative_terminal_never_matches_positive(self):
        # In runtime, Piezo pins are '+' and '-'
        ep_piezo_pos = {"id": "_piezo_1", "name": "1", "type": "Piezo", "pin": "+"}
        ep_piezo_neg = {"id": "_piezo_1", "name": "1", "type": "Piezo", "pin": "-"}

        # Querying '-' or 'negative' or 'gnd' MUST match negative and NOT positive
        self.assertTrue(WiringService._endpoint_matches(ep_piezo_neg, "Piezo", "-"))
        self.assertTrue(WiringService._endpoint_matches(ep_piezo_neg, "Piezo", "negative"))
        self.assertTrue(WiringService._endpoint_matches(ep_piezo_neg, "Piezo", "neg"))
        self.assertTrue(WiringService._endpoint_matches(ep_piezo_neg, "Piezo", "gnd"))

        self.assertFalse(WiringService._endpoint_matches(ep_piezo_pos, "Piezo", "-"))
        self.assertFalse(WiringService._endpoint_matches(ep_piezo_pos, "Piezo", "negative"))
        self.assertFalse(WiringService._endpoint_matches(ep_piezo_pos, "Piezo", "neg"))
        self.assertFalse(WiringService._endpoint_matches(ep_piezo_pos, "Piezo", "gnd"))

        # Querying '+' or 'positive' MUST match positive and NOT negative
        self.assertTrue(WiringService._endpoint_matches(ep_piezo_pos, "Piezo", "+"))
        self.assertTrue(WiringService._endpoint_matches(ep_piezo_pos, "Piezo", "positive"))
        self.assertTrue(WiringService._endpoint_matches(ep_piezo_pos, "Piezo", "pos"))

        self.assertFalse(WiringService._endpoint_matches(ep_piezo_neg, "Piezo", "+"))
        self.assertFalse(WiringService._endpoint_matches(ep_piezo_neg, "Piezo", "positive"))

    def test_query_sensor_1_does_not_match_piezo(self):
        ep_piezo = {"id": "_dev_piezo", "name": "1", "type": "Piezo", "pin": "+"}
        # 'sensor 1', 'sensor', 'ultrasonic' must never match Piezo even if its default name is '1'
        self.assertFalse(WiringService._endpoint_matches(ep_piezo, "sensor 1", "+"))
        self.assertFalse(WiringService._endpoint_matches(ep_piezo, "sensor 1", "TRIG"))
        self.assertFalse(WiringService._endpoint_matches(ep_piezo, "sensor", "+"))
        self.assertFalse(WiringService._endpoint_matches(ep_piezo, "ultrasonic", "TRIG"))


class TestComponentPersistenceVerification(unittest.IsolatedAsyncioTestCase):
    """Requirement: verify_persistence on add_component."""

    async def test_add_component_with_verify_persistence_success(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_components_drawer_open = AsyncMock(return_value=True)
        mock_bm.is_pointer_intercepted = AsyncMock(return_value=(False, None))

        service = ComponentsService(mock_bm)
        service._get_canvas_bounds = AsyncMock(return_value={"x": 100, "y": 100, "width": 800, "height": 600})

        mock_page.evaluate = AsyncMock(side_effect=[
            True,  # _ensure_all_components_category
            [],    # beforeIds
            {      # card_match_info
                "selected": {"index": 0, "title": "Piezo", "clickX": 500, "clickY": 500},
                "matches": [{"title": "Piezo"}],
            },
            {      # placed_verification
                "verified": True,
                "instance_id": "_piezo_1",
                "name": "1",
                "type": "Piezo",
                "pins": ["+", "-"],
            },
            None,  # ce.root.save()
            True,  # persisted after reload check
        ])
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.reload = AsyncMock()
        mock_page.mouse.click = AsyncMock()
        mock_page.mouse.move = AsyncMock()

        res = await service.add_component("Piezo", x=500, y=500, verify_persistence=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["verified"])
        self.assertEqual(res["instance_id"], "_piezo_1")
        mock_page.reload.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
