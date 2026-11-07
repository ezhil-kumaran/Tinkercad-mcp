"""Tests for Breadboard smart hole distribution and multi-wire resolution.

Verifies:
1. Breadboard power rail pin matching and semantic equivalence (+, -, y1, z1, etc.).
2. Breadboard tie-point 5-hole strip group equivalence (1f == 1g in group fj1, 1a == 1b in group ae1).
3. Separation across trough (1f != 1a) and columns (1f != 2f).
4. Breadboard terminal categorization (power, ground, tie-point).
5. Breadboard terminal resolution in resolve_terminal and resolve_instance_terminal.
6. Inspect circuit wire mapping to breadboard endpoints.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock
from src.services.wiring_service import WiringService
from src.services.circuits_service import CircuitsService


class TestBreadboardWiring(unittest.IsolatedAsyncioTestCase):
    """Unit tests for Breadboard terminal allocation and wiring logic."""

    def test_breadboard_power_rail_semantic_matching(self):
        """Verify semantic alias matching for breadboard positive and negative rails."""
        # Positive rail matches
        self.assertTrue(WiringService._pins_match_semantically("+", "power_pos_top"))
        self.assertTrue(WiringService._pins_match_semantically("+", "y1"))
        self.assertTrue(WiringService._pins_match_semantically("+ (y1)", "+"))
        self.assertTrue(WiringService._pins_match_semantically("pos", "y5"))
        self.assertTrue(WiringService._pins_match_semantically("5V", "power_pos_bot"))
        self.assertTrue(WiringService._pins_match_semantically("w1", "power"))

        # Negative rail matches
        self.assertTrue(WiringService._pins_match_semantically("-", "power_neg_top"))
        self.assertTrue(WiringService._pins_match_semantically("-", "z1"))
        self.assertTrue(WiringService._pins_match_semantically("- (z1)", "-"))
        self.assertTrue(WiringService._pins_match_semantically("gnd", "z10"))
        self.assertTrue(WiringService._pins_match_semantically("ground", "power_neg_bot"))
        self.assertTrue(WiringService._pins_match_semantically("x1", "neg"))

        # Cross polarity must NOT match
        self.assertFalse(WiringService._pins_match_semantically("+", "-"))
        self.assertFalse(WiringService._pins_match_semantically("y1", "z1"))
        self.assertFalse(WiringService._pins_match_semantically("5V", "GND"))

    def test_breadboard_tie_point_strip_group_matching(self):
        """Verify that holes in the same 5-hole vertical strip match as the same electrical node."""
        # Same column in group fj (f, g, h, i, j): all share the same conductive clip
        self.assertTrue(WiringService._pins_match_semantically("1f", "1g"))
        self.assertTrue(WiringService._pins_match_semantically("1f", "1j"))
        self.assertTrue(WiringService._pins_match_semantically("f1", "g1"))
        self.assertTrue(WiringService._pins_match_semantically("15h", "15i"))

        # Same column in group ae (a, b, c, d, e): all share the same conductive clip
        self.assertTrue(WiringService._pins_match_semantically("1a", "1b"))
        self.assertTrue(WiringService._pins_match_semantically("1a", "1e"))
        self.assertTrue(WiringService._pins_match_semantically("a1", "e1"))
        self.assertTrue(WiringService._pins_match_semantically("30c", "30d"))

        # Across the center divider trough (group ae vs group fj): MUST NOT MATCH
        self.assertFalse(WiringService._pins_match_semantically("1a", "1f"))
        self.assertFalse(WiringService._pins_match_semantically("1e", "1f"))
        self.assertFalse(WiringService._pins_match_semantically("a1", "j1"))

        # Across different columns: MUST NOT MATCH
        self.assertFalse(WiringService._pins_match_semantically("1f", "2f"))
        self.assertFalse(WiringService._pins_match_semantically("1a", "2a"))
        self.assertFalse(WiringService._pins_match_semantically("10g", "11g"))

    def test_breadboard_pin_categorization(self):
        """Verify pin categorization for breadboard rails vs tie-points."""
        # Rails
        self.assertEqual(WiringService._categorize_pin("+", "Breadboard Small"), "power")
        self.assertEqual(WiringService._categorize_pin("power_pos_top", "Breadboard Small"), "power")
        self.assertEqual(WiringService._categorize_pin("y1", "Breadboard Small"), "power")
        self.assertEqual(WiringService._categorize_pin("-", "Breadboard Small"), "ground")
        self.assertEqual(WiringService._categorize_pin("power_neg_top", "Breadboard Small"), "ground")
        self.assertEqual(WiringService._categorize_pin("z1", "Breadboard Small"), "ground")

        # Tie points
        cat_1f = WiringService._categorize_pin("1f", "Breadboard Small")
        self.assertIn(cat_1f, ("passive", "other"))
        cat_1a = WiringService._categorize_pin("1a", "Breadboard Small")
        self.assertIn(cat_1a, ("passive", "other"))

    async def test_resolve_terminal_breadboard_distribution(self):
        """Verify resolve_terminal successfully calls page evaluate and returns breadboard data."""
        mock_browser = MagicMock()
        mock_page = AsyncMock()
        mock_browser.get_page = AsyncMock(return_value=mock_page)
        mock_browser.ensure_canvas_interactive = AsyncMock()

        # Mock page.evaluate returning a cleanly distributed rail coordinate
        mock_page.evaluate = AsyncMock(return_value={
            "success": True,
            "component": "Breadboard Small",
            "instance_id": "_279",
            "name": "1",
            "pin": "+ (y2)",
            "x": 218,
            "y": 353,
            "is_breadboard": True,
            "hole": "y2",
            "group": "top_pos"
        })

        svc = WiringService(mock_browser)
        res = await svc.resolve_terminal("Breadboard Small", "+")

        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("component"), "Breadboard Small")
        self.assertEqual(res.get("instance_id"), "_279")
        self.assertEqual(res.get("hole"), "y2")
        self.assertEqual(res.get("x"), 218)
        self.assertEqual(res.get("y"), 353)

    async def test_resolve_instance_terminal_breadboard(self):
        """Verify resolve_instance_terminal resolves breadboard tie-points on exact instance."""
        mock_browser = MagicMock()
        mock_page = AsyncMock()
        mock_browser.get_page = AsyncMock(return_value=mock_page)
        mock_browser.ensure_canvas_interactive = AsyncMock()

        mock_page.evaluate = AsyncMock(return_value={
            "success": True,
            "error": None,
            "is_suspicious": False,
            "instance_id": "_279",
            "component_type": "Breadboard Small",
            "name": "1",
            "pin": "1f",
            "requested_pin": "1f",
            "x": 105,
            "y": 420,
            "out_of_bounds": False,
            "message": None
        })

        svc = WiringService(mock_browser)
        res = await svc.resolve_instance_terminal(
            instance_id="_279",
            pin_query="1f",
            component_hint="Breadboard Small",
            page=mock_page
        )

        self.assertTrue(res.get("success"))
        self.assertFalse(res.get("is_suspicious"))
        self.assertEqual(res.get("instance_id"), "_279")
        self.assertEqual(res.get("pin"), "1f")
        self.assertEqual(res.get("x"), 105)
        self.assertEqual(res.get("y"), 420)

    async def test_inspect_circuit_includes_breadboard_wire_endpoints(self):
        """Verify inspect_circuit returns structured wire endpoints when target is on breadboard."""
        mock_browser = MagicMock()
        mock_page = AsyncMock()
        mock_page.url = "https://www.tinkercad.com/things/test-bb-demo/editel"
        mock_browser.get_page = AsyncMock(return_value=mock_page)

        # Mock inspect_circuit return with wire connected to breadboard hole y1
        mock_page.evaluate = AsyncMock(return_value={
            "circuit_id": "test-bb-demo",
            "title": "Breadboard Test",
            "components": [
                {
                    "instance_id": "_270",
                    "type": "Arduino Uno R3",
                    "name": "1",
                    "pins": [{"name": "5V", "connected": True}]
                },
                {
                    "instance_id": "_279",
                    "type": "Breadboard Small",
                    "name": "1",
                    "pins": [{"name": "y1", "connected": True}]
                }
            ],
            "wires": [
                {
                    "wire_id": "w_5v",
                    "color": "red",
                    "source": {
                        "instance_id": "_270",
                        "component": "Arduino Uno R3",
                        "name": "1",
                        "pin": "5V"
                    },
                    "target": {
                        "instance_id": "_279",
                        "component": "Breadboard Small",
                        "name": "1",
                        "pin": "y1"
                    }
                }
            ]
        })

        circ_svc = CircuitsService(mock_browser)
        data = await circ_svc.inspect_circuit()

        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("detected_wires_count"), 1)
        wire = data["wires"][0]
        self.assertEqual(wire["source"]["pin"], "5V")
        self.assertIsNotNone(wire["target"])
        self.assertEqual(wire["target"]["component"], "Breadboard Small")
        self.assertEqual(wire["target"]["pin"], "y1")


if __name__ == "__main__":
    unittest.main()
