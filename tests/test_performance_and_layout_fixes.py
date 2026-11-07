"""Tests for performance optimizations, code drawer pointer protection, auto-layout collision avoidance, and ultrasonic pin alias resolution."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.browser.browser_manager import BrowserManager
from src.services.circuits_service import CircuitsService
from src.services.components_service import ComponentsService
from src.services.wiring_service import WiringService


class TestTrackerRouteBlocking(unittest.IsolatedAsyncioTestCase):
    """Test telemetry and tracking script interception to accelerate WebGL loading."""

    async def test_route_blocking_registers_analytics_patterns(self):
        mock_context = AsyncMock()
        await BrowserManager._setup_route_blocking(mock_context)
        mock_context.route.assert_called_once()
        args = mock_context.route.call_args[0]
        pattern = args[0]
        # Verify regex matches common heavy tracking domains
        self.assertTrue(pattern.search("https://www.google-analytics.com/analytics.js"))
        self.assertTrue(pattern.search("https://cdn.segment.io/analytics.js/v1/token"))
        self.assertTrue(pattern.search("https://static.hotjar.com/c/hotjar-123.js"))
        self.assertTrue(pattern.search("https://cdn.optimizely.com/js/123.js"))
        self.assertTrue(pattern.search("https://browser-intake-datadoghq.com/api/v2/rum"))
        self.assertFalse(pattern.search("https://www.tinkercad.com/things/editel"))


class TestCodeDrawerInterceptionDefense(unittest.IsolatedAsyncioTestCase):
    """Test that Code drawer is proactively closed and pointer interception is prevented."""

    async def test_open_circuit_proactively_closes_code_panel(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_page.is_closed = MagicMock(return_value=False)
        mock_page.url = "https://www.tinkercad.com/things/abc12345/editel"
        mock_page.evaluate = AsyncMock(return_value="My Circuit")
        mock_page.wait_for_timeout = AsyncMock()
        mock_bm.navigate = AsyncMock(return_value=mock_page)
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.find_first_matching = AsyncMock(return_value=AsyncMock())
        mock_bm.close_code_panel = AsyncMock(return_value=True)

        service = CircuitsService(mock_bm)
        res = await service.open_circuit("abc12345")
        self.assertTrue(res["success"])
        mock_bm.close_code_panel.assert_awaited_once()

    async def test_create_circuit_proactively_closes_code_panel(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_page.url = "https://www.tinkercad.com/things/test-circuit-demo/editel"
        mock_page.is_closed = MagicMock(return_value=False)
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.wait_for_url = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body><div id='breadboardTab'></div></body></html>")
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.navigate = AsyncMock(return_value=mock_page)

        mock_btn = AsyncMock()
        mock_btn.click = AsyncMock()
        mock_canvas = AsyncMock()
        mock_bm.find_first_matching = AsyncMock(side_effect=[mock_btn, mock_btn, mock_canvas, None, None])

        mock_page.evaluate = AsyncMock(side_effect=[
            False,  # is_missing (404 check)
            1,      # canvas_count
            "dune", # current title
        ])
        mock_bm.close_code_panel = AsyncMock(return_value=True)

        circuits_service = CircuitsService(mock_bm)
        res = await circuits_service.create_circuit(title="dune")
        self.assertTrue(res["success"])
        mock_bm.close_code_panel.assert_awaited_once()

    async def test_add_component_detects_drop_point_interception(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.close_code_panel = AsyncMock(return_value=True)
        mock_bm.ensure_components_drawer_open = AsyncMock(return_value=True)
        mock_bm.close_overlays_and_modals = AsyncMock(return_value=True)

        # First pointer check (click on card) is clear; second check (canvas drop) is intercepted by Code panel
        mock_bm.is_pointer_intercepted = AsyncMock(side_effect=[
            (False, None),  # click_x, click_y
            (True, "blocklySvg"),  # target_x, target_y
        ])

        mock_page.evaluate = AsyncMock(side_effect=[
            True,  # _ensure_all_components_category
            [],    # before_instances
            {      # card_match_info
                "selected": {"index": 0, "title": "LED", "clickX": 950, "clickY": 300},
                "matches": [{"title": "LED"}]
            },
            None,  # pointer-events injection
            {      # placed_verification
                "verified": True,
                "instance_id": "_led_1",
                "name": "1",
                "type": "LED",
                "pins": ["anode", "cathode"],
            }
        ])
        mock_page.mouse.click = AsyncMock()
        mock_page.mouse.move = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()

        service = ComponentsService(mock_bm)
        service._find_non_overlapping_coordinates = AsyncMock(return_value=(600, 300))

        res = await service.add_component("LED", x=600, y=300)
        self.assertTrue(res["success"])
        # Verify close_code_panel was called to clear the obstruction
        self.assertGreaterEqual(mock_bm.close_code_panel.await_count, 1)


class TestCollisionAvoidanceAutoLayout(unittest.IsolatedAsyncioTestCase):
    """Test intelligent auto-layout to prevent stacking components at identical coordinates."""

    async def test_zero_origin_stacking_is_intercepted_and_offset(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        service = ComponentsService(mock_bm)
        service._get_canvas_bounds = AsyncMock(return_value={"x": 50, "y": 100, "width": 1000, "height": 700})
        mock_page.evaluate = AsyncMock(return_value=[])

        # Placing at (161, -76) which is Tinkercad's default zero origin
        tx, ty = await service._find_non_overlapping_coordinates(
            mock_page, requested_x=161, requested_y=-76, comp_name="Arduino Uno R3"
        )
        # Verify coordinate was moved away from (161, -76)
        self.assertNotEqual((tx, ty), (161, -76))
        self.assertGreater(tx, 200)
        self.assertGreater(ty, 200)

    async def test_distinct_zones_for_controller_breadboard_sensor_actuator(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        service = ComponentsService(mock_bm)
        service._get_canvas_bounds = AsyncMock(return_value={"x": 50, "y": 100, "width": 1000, "height": 700})
        mock_page.evaluate = AsyncMock(return_value=[])

        # Auto-layout without coordinates
        ard_x, ard_y = await service._find_non_overlapping_coordinates(
            mock_page, requested_x=None, requested_y=None, comp_name="Arduino Uno R3"
        )
        bb_x, bb_y = await service._find_non_overlapping_coordinates(
            mock_page, requested_x=None, requested_y=None, comp_name="Breadboard Small"
        )
        sensor_x, sensor_y = await service._find_non_overlapping_coordinates(
            mock_page, requested_x=None, requested_y=None, comp_name="Ultrasonic Distance Sensor"
        )
        piezo_x, piezo_y = await service._find_non_overlapping_coordinates(
            mock_page, requested_x=None, requested_y=None, comp_name="Piezo"
        )

        coords = [(ard_x, ard_y), (bb_x, bb_y), (sensor_x, sensor_y), (piezo_x, piezo_y)]
        # Ensure all four positions are distinct and well-spaced
        self.assertEqual(len(set(coords)), 4)
        for i in range(len(coords)):
            for j in range(i + 1, len(coords)):
                import math
                dist = math.hypot(coords[i][0] - coords[j][0], coords[i][1] - coords[j][1])
                self.assertGreaterEqual(dist, 140, f"Distance between {coords[i]} and {coords[j]} is too small ({dist}px)")


class TestUltrasonicPinResolution(unittest.TestCase):
    """Test ultrasonic pin aliases resolution between VCC/GND and pos/neg."""

    def test_pins_match_semantically_ultrasonic_power(self):
        self.assertTrue(WiringService._pins_match_semantically("vcc", "pos"))
        self.assertTrue(WiringService._pins_match_semantically("VCC", "pos"))
        self.assertTrue(WiringService._pins_match_semantically("pos", "Power"))
        self.assertTrue(WiringService._pins_match_semantically("5V", "pos"))

    def test_pins_match_semantically_ultrasonic_ground(self):
        self.assertTrue(WiringService._pins_match_semantically("gnd", "neg"))
        self.assertTrue(WiringService._pins_match_semantically("GND", "neg"))
        self.assertTrue(WiringService._pins_match_semantically("ground", "neg"))
        self.assertTrue(WiringService._pins_match_semantically("neg", "GND"))

    def test_pins_match_semantically_ultrasonic_trig_and_echo(self):
        self.assertTrue(WiringService._pins_match_semantically("trigger", "trig"))
        self.assertTrue(WiringService._pins_match_semantically("Trig", "Trigger"))
        self.assertTrue(WiringService._pins_match_semantically("echo", "Echo"))


class TestExclusionRadiusAndOriginTracking(unittest.IsolatedAsyncioTestCase):
    """Test origin tracking and exclusion radius to prevent components stacking on top of each other."""

    def test_exclusion_radius_by_component_type(self):
        # Breadboard large requires largest clearance (~190px)
        self.assertEqual(ComponentsService.get_component_exclusion_radius("Breadboard"), 190)
        self.assertEqual(ComponentsService.get_component_exclusion_radius("Breadboard Small"), 140)
        # Arduino Uno requires ~150px
        self.assertEqual(ComponentsService.get_component_exclusion_radius("Arduino Uno R3"), 150)
        # Motors / Servos ~110px
        self.assertEqual(ComponentsService.get_component_exclusion_radius("Micro Servo"), 110)
        self.assertEqual(ComponentsService.get_component_exclusion_radius("HC-SR04 Ultrasonic Distance Sensor"), 110)
        # Sensors ~85px
        self.assertEqual(ComponentsService.get_component_exclusion_radius("PIR Sensor"), 85)
        # Passives ~60px
        self.assertEqual(ComponentsService.get_component_exclusion_radius("LED"), 60)
        self.assertEqual(ComponentsService.get_component_exclusion_radius("Resistor"), 60)

    async def test_overlapping_requested_coordinates_are_displaced(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        service = ComponentsService(mock_bm)

        # Place component 1 at (300, 300)
        service.record_placed_origin(instance_id="_ard_1", name="Arduino Uno R3", x=300, y=300)
        origins = service.get_placed_origins()
        self.assertEqual(len(origins), 1)
        self.assertEqual(origins[0]["x"], 300)
        self.assertEqual(origins[0]["y"], 300)

        # Agent tries to place component 2 at (300, 300) - direct collision!
        cand_x, cand_y = await service._find_non_overlapping_coordinates(
            mock_page, requested_x=300, requested_y=300, comp_name="Micro Servo"
        )
        # Verify component 2 was displaced away from (300, 300)
        import math
        dist = math.hypot(cand_x - 300, cand_y - 300)
        self.assertGreaterEqual(dist, 180, f"Component was placed too close to existing origin ({dist}px)")

    async def test_multiple_identical_requests_spread_out(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        service = ComponentsService(mock_bm)

        # 3 components requested at identical (400, 400)
        c1_x, c1_y = await service._find_non_overlapping_coordinates(
            mock_page, requested_x=400, requested_y=400, comp_name="Breadboard Small"
        )
        self.assertEqual((c1_x, c1_y), (400, 400))
        service.record_placed_origin(instance_id="_bb_1", name="Breadboard Small", x=c1_x, y=c1_y)

        c2_x, c2_y = await service._find_non_overlapping_coordinates(
            mock_page, requested_x=400, requested_y=400, comp_name="Arduino Uno R3"
        )
        self.assertNotEqual((c2_x, c2_y), (400, 400))
        service.record_placed_origin(instance_id="_ard_1", name="Arduino Uno R3", x=c2_x, y=c2_y)

        c3_x, c3_y = await service._find_non_overlapping_coordinates(
            mock_page, requested_x=400, requested_y=400, comp_name="Micro Servo"
        )
        self.assertNotEqual((c3_x, c3_y), (400, 400))
        self.assertNotEqual((c3_x, c3_y), (c2_x, c2_y))

        # All 3 have unique coordinates
        self.assertEqual(len({(c1_x, c1_y), (c2_x, c2_y), (c3_x, c3_y)}), 3)

    async def test_remove_component_clears_origin(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.find_first_matching = AsyncMock(return_value=None)
        mock_page.mouse.click = AsyncMock()
        mock_page.keyboard.press = AsyncMock()

        service = ComponentsService(mock_bm)
        service.record_placed_origin(instance_id="_servo_1", name="Micro Servo", x=500, y=500)
        self.assertEqual(len(service.get_placed_origins()), 1)

        # Remove at coordinates (500, 500)
        res = await service.remove_component(x=500, y=500)
        self.assertTrue(res["success"])
        self.assertEqual(len(service.get_placed_origins()), 0)


class TestCanvasZoomOperations(unittest.IsolatedAsyncioTestCase):
    """Test canvas zoom operations (fit, out, in)."""

    async def test_zoom_canvas_fit(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock()
        mock_bm.find_first_matching = AsyncMock(return_value=None)
        mock_page.evaluate = AsyncMock(return_value=True)

        from src.services.circuits_service import CircuitsService
        cs = CircuitsService(mock_bm)
        res = await cs.zoom_canvas(action="fit")
        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "fit")

    async def test_zoom_canvas_out(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock()
        mock_bm.find_first_matching = AsyncMock(return_value=None)
        mock_page.mouse.wheel = AsyncMock()
        mock_page.keyboard.press = AsyncMock()

        from src.services.circuits_service import CircuitsService
        cs = CircuitsService(mock_bm)
        res = await cs.zoom_canvas(action="out", steps=2)
        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "out")
        self.assertEqual(res["steps"], 2)
        mock_page.mouse.wheel.assert_called_with(0, 360)

    async def test_zoom_canvas_in(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock()
        mock_bm.find_first_matching = AsyncMock(return_value=None)
        mock_page.mouse.wheel = AsyncMock()
        mock_page.keyboard.press = AsyncMock()

        from src.services.circuits_service import CircuitsService
        cs = CircuitsService(mock_bm)
        res = await cs.zoom_canvas(action="in", steps=1)
        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "in")
        mock_page.mouse.wheel.assert_called_with(0, -180)

    async def test_zoom_canvas_invalid_action(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        from src.services.circuits_service import CircuitsService
        cs = CircuitsService(mock_bm)
        res = await cs.zoom_canvas(action="invalid_action")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "invalid_zoom_action")


if __name__ == "__main__":
    unittest.main()
