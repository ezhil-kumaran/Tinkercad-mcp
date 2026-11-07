"""Comprehensive unit and security tests for Tinkercad MCP Server tools, security validations, and configurations."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock
from src.catalog.components_catalog import (
    COMPONENTS_CATALOG,
    find_component_by_query,
    list_components_catalog,
)
from src.config import (
    BASE_URL,
    LOGIN_URL,
    JOIN_URL,
    DASHBOARD_URL,
    CIRCUITS_DASHBOARD_URL,
    PROFILE_DIR,
    SCREENSHOTS_DIR,
)
from src.browser.selectors import (
    AUTH_SELECTORS,
    DASHBOARD_SELECTORS,
    EDITOR_SELECTORS,
    COMPONENTS_SELECTORS,
    CODE_SELECTORS,
    SERIAL_SELECTORS,
)
from src.server import server
from src.browser.browser_manager import BrowserManager
from src.services.circuits_service import CircuitsService
from src.services.wiring_service import WiringService
from src.services.components_service import ComponentsService
from src.services.composite_service import CompositeService
from src.services.auth_service import AuthService


class TestTinkercadCatalog(unittest.TestCase):
    """Test component catalog functionality."""

    def test_catalog_not_empty(self):
        self.assertGreater(len(COMPONENTS_CATALOG), 10)

    def test_find_arduino_uno(self):
        comp = find_component_by_query("arduino")
        self.assertIsNotNone(comp)
        self.assertEqual(comp.id, "arduino_uno")
        self.assertTrue(any(p.name == "D13" for p in comp.pins))
        self.assertTrue(any(p.name == "5V" for p in comp.pins))
        self.assertTrue(any(p.name == "GND_1" for p in comp.pins))

    def test_find_led(self):
        comp = find_component_by_query("LED")
        self.assertIsNotNone(comp)
        self.assertEqual(comp.id, "led")
        self.assertTrue(any(p.name == "anode" for p in comp.pins))
        self.assertTrue(any(p.name == "cathode" for p in comp.pins))

    def test_find_resistor(self):
        comp = find_component_by_query("resistor")
        self.assertIsNotNone(comp)
        self.assertEqual(comp.id, "resistor")
        self.assertEqual(comp.default_properties.get("resistance"), "1")

    def test_empty_and_whitespace_query(self):
        self.assertIsNone(find_component_by_query(""))
        self.assertIsNone(find_component_by_query("   "))

    def test_list_components_filtered(self):
        sensors = list_components_catalog(category="Sensors")
        self.assertGreater(len(sensors), 0)
        for s in sensors:
            self.assertEqual(s["category"], "Sensors")


class TestTinkercadConfigAndSelectors(unittest.TestCase):
    """Test configuration paths and selector mappings."""

    def test_urls(self):
        self.assertEqual(BASE_URL, "https://www.tinkercad.com")
        self.assertTrue(LOGIN_URL.endswith("/login"))
        self.assertTrue(JOIN_URL.endswith("/join"))
        self.assertIn("type=circuits", CIRCUITS_DASHBOARD_URL)

    def test_directories_exist(self):
        self.assertTrue(PROFILE_DIR.exists())
        self.assertTrue(SCREENSHOTS_DIR.exists())

    def test_selectors_structure(self):
        self.assertIn("user_avatar", AUTH_SELECTORS)
        self.assertIn("login_button", AUTH_SELECTORS)
        self.assertIn("error_alert", AUTH_SELECTORS)
        self.assertIn("circuits_tab", DASHBOARD_SELECTORS)
        self.assertIn("start_simulation_btn", EDITOR_SELECTORS)
        self.assertIn("stop_simulation_btn", EDITOR_SELECTORS)
        self.assertIn("code_toggle_btn", EDITOR_SELECTORS)
        self.assertIn("search_input", COMPONENTS_SELECTORS)
        self.assertIn("mode_select", CODE_SELECTORS)
        self.assertIn("toggle_btn", SERIAL_SELECTORS)
        self.assertIn("input_field", SERIAL_SELECTORS)

    def test_live_editor_dom_selectors(self):
        """Verify selectors extracted from live Tinkercad Circuits DOM inspection."""
        # Code button: a#CODE_EDITOR_ID with active state
        self.assertIn("a#CODE_EDITOR_ID", EDITOR_SELECTORS["code_toggle_btn"])
        self.assertIn("a#CODE_EDITOR_ID.active", EDITOR_SELECTORS["code_panel_active"])

        # Simulation button: a#SIMULATION_ID with Start / Stop states
        self.assertTrue(any("#SIMULATION_ID" in s for s in EDITOR_SELECTORS["start_simulation_btn"]))
        self.assertTrue(any("#SIMULATION_ID" in s for s in EDITOR_SELECTORS["stop_simulation_btn"]))

        # Title: topnav title text & input
        self.assertIn("#topnav-title-text", EDITOR_SELECTORS["circuit_title"])
        self.assertIn("#topnav-title-input", EDITOR_SELECTORS["circuit_title_input"])

        # Canvas: breadboard tab
        self.assertIn("#breadboardTab", EDITOR_SELECTORS["editor_canvas"])

        # Code panel: Blockly injection container & Text mode textarea
        self.assertIn(".blocklySvg", CODE_SELECTORS["panel"])
        self.assertIn(".injectionDiv", CODE_SELECTORS["panel"])
        self.assertIn("textarea.js-code_editor__textarea", CODE_SELECTORS["code_textarea"])

        # Serial Monitor: toggle button and text container
        self.assertIn("a#SERIAL_MONITOR_ID", SERIAL_SELECTORS["toggle_btn"])
        self.assertIn(".js-code_editor__serial-monitor__content", SERIAL_SELECTORS["output_log"])
        self.assertIn("input.js-code_panel__serial__input", SERIAL_SELECTORS["input_field"])
        self.assertIn("a.js-code_panel__serial__send", SERIAL_SELECTORS["send_btn"])
        self.assertIn("a.js-code_panel__serial__clear", SERIAL_SELECTORS["clear_btn"])
        self.assertIn("a.js-code_panel__serial__toggle_graph", SERIAL_SELECTORS["graph_btn"])

        # Components drawer: search, category, and component cards
        self.assertIn("a#COMPONENT_CATEGORY_SELECT", COMPONENTS_SELECTORS["category_select"])
        self.assertIn("input#q[data-event='component-search']", COMPONENTS_SELECTORS["search_input"])
        self.assertIn("button.js-search-btn", COMPONENTS_SELECTORS["search_btn"])
        self.assertIn(".editor__component_picker__groups__item", COMPONENTS_SELECTORS["component_item"])

        # Toolbar controls: wire colors & serial panel
        self.assertIn(".code_panel__serial", SERIAL_SELECTORS["panel"])
        self.assertTrue(any(".js-wire-color-container" in s for s in EDITOR_SELECTORS["wire_color_dropdown"]))


class TestMCPServerTools(unittest.TestCase):
    """Test that all required MCP tools are properly registered."""

    def setUp(self):
        self.tools = server._tool_manager.list_tools()
        self.tool_names = {t.name for t in self.tools}

    def test_tool_count(self):
        self.assertEqual(len(self.tools), 46)

    def test_auth_tools_registered(self):
        for tool in ["tinkercad_auth_status", "tinkercad_login", "tinkercad_open_signup", "tinkercad_logout", "tinkercad_restart_browser"]:
            self.assertIn(tool, self.tool_names)

    def test_circuit_tools_registered(self):
        for tool in [
            "tinkercad_list_circuits",
            "tinkercad_open_circuit",
            "tinkercad_create_circuit",
            "tinkercad_get_circuit_info",
            "tinkercad_inspect_circuit",
            "tinkercad_rename_circuit",
            "tinkercad_take_screenshot",
            "tinkercad_switch_workspace_view",
            "tinkercad_zoom_canvas",
            "tinkercad_validate_circuit_pre_simulation",
        ]:
            self.assertIn(tool, self.tool_names)

    def test_component_tools_registered(self):
        for tool in ["tinkercad_list_available_components", "tinkercad_add_component", "tinkercad_remove_component", "tinkercad_set_component_property"]:
            self.assertIn(tool, self.tool_names)

    def test_wiring_tools_registered(self):
        for tool in [
            "tinkercad_resolve_terminal",
            "tinkercad_connect_pins",
            "tinkercad_connect_component_pins",
            "tinkercad_connect_and_verify_wires",
            "tinkercad_connect_verified_netlist",
            "tinkercad_delete_wire_between",
            "tinkercad_clear_circuit_wires",
            "tinkercad_route_pin_via_breadboard",
            "tinkercad_move_connection",
            "tinkercad_delete_wire",
            "tinkercad_check_electrical_safety",
        ]:
            self.assertIn(tool, self.tool_names)

    def test_code_tools_registered(self):
        for tool in ["tinkercad_get_code", "tinkercad_set_code"]:
            self.assertIn(tool, self.tool_names)

    def test_simulation_tools_registered(self):
        for tool in ["tinkercad_start_simulation", "tinkercad_stop_simulation", "tinkercad_get_simulation_status"]:
            self.assertIn(tool, self.tool_names)

    def test_serial_tools_registered(self):
        for tool in ["tinkercad_open_serial_monitor", "tinkercad_read_serial_monitor", "tinkercad_send_serial_monitor", "tinkercad_clear_serial_monitor"]:
            self.assertIn(tool, self.tool_names)

    def test_composite_tool_registered(self):
        self.assertIn("tinkercad_build_circuit", self.tool_names)
        self.assertIn("tinkercad_change_pin_and_update_code", self.tool_names)
        self.assertIn("tinkercad_add_servo_with_distance_control", self.tool_names)
        self.assertIn("tinkercad_build_robot_car", self.tool_names)

    def test_schematic_tools_registered(self):
        for tool in [
            "tinkercad_get_schematic_svg",
            "tinkercad_inspect_schematic_connections",
            "tinkercad_verify_schematic_connections",
        ]:
            self.assertIn(tool, self.tool_names)


class TestSecurityAndInputValidation(unittest.TestCase):
    """Test security mitigations: path traversal, SSRF prevention, coordinate bounding, and DoS controls."""

    def test_screenshot_path_traversal_prevention(self):
        bm = BrowserManager.get_instance()
        # Relative traversal
        name1 = bm._sanitize_screenshot_filename("../../../sensitive_file.png")
        self.assertEqual(name1, "sensitive_file.png")
        self.assertNotIn("..", name1)
        self.assertNotIn("/", name1)

        # Windows traversal
        name2 = bm._sanitize_screenshot_filename("..\\..\\Windows\\System32\\bad.png")
        self.assertEqual(name2, "bad.png")
        self.assertNotIn("\\", name2)

        # Absolute paths
        name3 = bm._sanitize_screenshot_filename("C:/foo/bar.png")
        self.assertEqual(name3, "bar.png")

        # Disallowed special characters
        name4 = bm._sanitize_screenshot_filename("photo;rm -rf /")
        self.assertNotIn(";", name4)
        self.assertNotIn(" ", name4)
        self.assertTrue(name4.endswith(".png"))

        # Empty / whitespace
        name5 = bm._sanitize_screenshot_filename("")
        self.assertTrue(name5.startswith("tinkercad_") and name5.endswith(".png"))

    def test_circuit_target_validation_safe(self):
        cs = CircuitsService()
        # Valid ID
        url1 = cs._validate_circuit_target("circuit-123_abc")
        self.assertEqual(url1, "https://www.tinkercad.com/things/circuit-123_abc/editel")

        # Valid /things/ ID
        url2 = cs._validate_circuit_target("/things/0abcdef-uno")
        self.assertEqual(url2, "https://www.tinkercad.com/things/0abcdef-uno/editel")

        # Valid full HTTPS URL
        url3 = cs._validate_circuit_target("https://www.tinkercad.com/things/0abcdef-uno/editel")
        self.assertEqual(url3, "https://www.tinkercad.com/things/0abcdef-uno/editel")

    def test_circuit_target_validation_blocks_attacks(self):
        cs = CircuitsService()
        # SSRF / external host
        with self.assertRaises(ValueError):
            cs._validate_circuit_target("https://attacker.com/evil")

        with self.assertRaises(ValueError):
            cs._validate_circuit_target("http://169.254.169.254/latest/meta-data")

        # Insecure HTTP
        with self.assertRaises(ValueError):
            cs._validate_circuit_target("http://www.tinkercad.com/things/123/editel")

        # Dangerous protocols
        with self.assertRaises(ValueError):
            cs._validate_circuit_target("javascript:alert(1)")

        with self.assertRaises(ValueError):
            cs._validate_circuit_target("file:///etc/passwd")

        # Path traversal
        with self.assertRaises(ValueError):
            cs._validate_circuit_target("../../account/delete")

        # Empty
        with self.assertRaises(ValueError):
            cs._validate_circuit_target("   ")

    def test_wiring_coordinates_bounds(self):
        ws = WiringService()
        valid, msg = ws.validate_wire_coordinates(from_x=-999999, from_y=100, to_x=200, to_y=200)
        self.assertFalse(valid)
        self.assertIn("out of bounds", msg)

        valid2, msg2 = ws.validate_wire_coordinates(from_x=100, from_y=100, to_x=200, to_y=200)
        self.assertTrue(valid2)
        self.assertIsNone(msg2)

    def test_components_coordinates_bounds(self):
        comps = ComponentsService()
        valid, msg = comps.validate_coordinates(x=999999, y=100)
        self.assertFalse(valid)
        self.assertIn("out of bounds", msg)

        valid2, msg2 = comps.validate_coordinates(x=300, y=400)
        self.assertTrue(valid2)
        self.assertIsNone(msg2)

    def test_build_circuit_input_validation(self):
        # Malformed JSON in components_json
        valid1, err1, _, _ = CompositeService.validate_build_inputs(components_json="{broken json")
        self.assertFalse(valid1)
        self.assertIn("Failed to parse", err1)

        # Non-array JSON in components_json
        valid2, err2, _, _ = CompositeService.validate_build_inputs(components_json='{"name": "LED"}')
        self.assertFalse(valid2)
        self.assertIn("must be a JSON array", err2)

        # Too many components (DoS prevention)
        large_comps = [{"name": "LED"} for _ in range(101)]
        valid3, err3, _, _ = CompositeService.validate_build_inputs(components_json=json.dumps(large_comps))
        self.assertFalse(valid3)
        self.assertIn("Too many components", err3)

        # Malformed JSON in wires_json
        valid4, err4, _, _ = CompositeService.validate_build_inputs(wires_json="not a json")
        self.assertFalse(valid4)
        self.assertIn("Failed to parse", err4)

        # Valid payload
        valid5, err5, c, w = CompositeService.validate_build_inputs(
            components_json='[{"name": "LED", "x": 100, "y": 100}]',
            wires_json='[{"from_x": 100, "from_y": 100, "to_x": 200, "to_y": 200}]',
        )
        self.assertTrue(valid5)
        self.assertIsNone(err5)
        self.assertEqual(len(c), 1)
        self.assertEqual(len(w), 1)

    def test_auth_login_credential_check(self):
        auth = AuthService()
        # Missing password when username provided
        valid1, msg1, _ = auth.validate_login_params(username="testuser", password=None)
        self.assertFalse(valid1)
        self.assertIn("Both username and password are required", msg1)

        # Missing username when password provided
        valid2, msg2, _ = auth.validate_login_params(username=None, password="secretpassword")
        self.assertFalse(valid2)
        self.assertIn("Both username and password are required", msg2)

        # Both provided
        valid3, msg3, t = auth.validate_login_params(username="testuser", password="secretpassword", timeout_seconds=180)
        self.assertTrue(valid3)
        self.assertIsNone(msg3)
        self.assertEqual(t, 180)

        # Bounding extreme timeouts
        _, _, bounded_high = auth.validate_login_params(timeout_seconds=999999)
        self.assertEqual(bounded_high, 600)
        _, _, bounded_low = auth.validate_login_params(timeout_seconds=-10)
        self.assertEqual(bounded_low, 10)


class TestToolAliasesAndFixes(unittest.IsolatedAsyncioTestCase):
    """Test parameter aliases and fixes for all 10 reported issues."""

    async def test_build_circuit_unparsed_description_returns_informative_error(self):
        comp = CompositeService()
        res = await comp.build_circuit(description="Make an LED blink on Arduino Uno pin 13")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "unparsed_natural_language_description")
        self.assertIn("components_json", res["message"])

    async def test_build_circuit_empty_inputs_returns_error(self):
        comp = CompositeService()
        res = await comp.build_circuit()
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "no_actionable_inputs")

    async def test_rename_circuit_accepts_new_name_alias(self):
        from unittest.mock import AsyncMock
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        circuits = CircuitsService(mock_bm)
        # Empty title fails validation with expected message
        res_empty = await circuits.rename_circuit(new_name="")
        self.assertFalse(res_empty["success"])
        self.assertIn("cannot be empty", res_empty["message"])

    async def test_open_circuit_accepts_circuit_id_alias(self):
        circuits = CircuitsService()
        # Empty ID fails validation with expected message
        res_empty = await circuits.open_circuit(circuit_id="")
        self.assertFalse(res_empty["success"])
        self.assertIn("cannot be empty", res_empty["message"])

    async def test_add_component_accepts_component_id_alias(self):
        comps = ComponentsService()
        # Empty name and id fails validation with expected message
        res_empty = await comps.add_component(component_id="")
        self.assertFalse(res_empty["success"])
        self.assertIn("Either component_name or component_id", res_empty["message"])

    async def test_connect_component_pins_accepts_all_aliases(self):
        wiring = WiringService()
        # Missing pins returns clear error
        res_missing = await wiring.connect_component_pins(
            component1_id="Arduino Uno R3",
            pin1="D13",
            component2_id=None,
            pin2=None,
        )
        self.assertFalse(res_missing["success"])
        self.assertEqual(res_missing["error"], "missing_required_parameters")
        self.assertIn("connect_component_pins requires", res_missing["message"])


if __name__ == "__main__":
    unittest.main()
