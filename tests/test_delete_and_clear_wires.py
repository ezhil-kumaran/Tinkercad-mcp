"""Tests for tinkercad_delete_wire_between and tinkercad_clear_circuit_wires."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from src.browser.browser_manager import BrowserManager
from src.services.wiring_service import WiringService


class TestDeleteAndClearWires(unittest.IsolatedAsyncioTestCase):
    """Test suite for semantic wire deletion and circuit wire clearing."""

    async def test_delete_wire_between_success(self):
        """Successfully locates and deletes wire matching endpoints without coordinates."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock()

        service = WiringService(mock_bm)

        existing_wires = [
            {"id": "w1", "source": {"type": "Arduino Uno R3", "pin": "5V"}, "target": {"type": "Ultrasonic Distance Sensor (4-pin)", "pin": "pos"}},
            {"id": "w2", "source": {"type": "Arduino Uno R3", "pin": "D11"}, "target": {"type": "Piezo", "pin": "+"}},
        ]
        # First call finds w2; second call after deletion confirms w2 is gone
        service._get_circuit_wires = AsyncMock(side_effect=[existing_wires, [existing_wires[0]]])

        mock_page.evaluate = AsyncMock(return_value=True)
        mock_page.wait_for_timeout = AsyncMock()

        res = await service.delete_wire_between(
            source_component="Arduino Uno R3",
            source_pin="D11",
            target_component="Piezo",
            target_pin="+",
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["deleted_wire_id"], "w2")
        self.assertIn("D11", res["source"])
        self.assertIn("Piezo", res["target"])

    async def test_delete_wire_between_not_found(self):
        """Returns error when no wire connects specified endpoints."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock()

        service = WiringService(mock_bm)
        service._get_circuit_wires = AsyncMock(return_value=[])

        res = await service.delete_wire_between(
            source_component="Arduino Uno R3",
            source_pin="D9",
            target_component="Micro Servo",
            target_pin="Signal",
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "wire_not_found")

    async def test_clear_all_circuit_wires(self):
        """Clears all wires in the circuit canvas."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock()

        service = WiringService(mock_bm)
        mock_page.evaluate = AsyncMock(return_value={"success": True, "removed_count": 6, "remaining_count": 0})

        res = await service.clear_circuit_wires(component_name=None, verify_persistence=False)

        self.assertTrue(res["success"])
        self.assertEqual(res["removed_count"], 6)
        self.assertEqual(res["remaining_count"], 0)

    async def test_clear_circuit_wires_for_specific_component(self):
        """Clears only wires attached to a specific component."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock()

        service = WiringService(mock_bm)
        mock_page.evaluate = AsyncMock(return_value={"success": True, "removed_count": 2, "remaining_count": 4})

        res = await service.clear_circuit_wires(component_name="Piezo", verify_persistence=False)

        self.assertTrue(res["success"])
        self.assertEqual(res["removed_count"], 2)
        self.assertEqual(res["remaining_count"], 4)

    async def test_delete_wire_component_guard_prevents_destruction(self):
        """Rejects deletion and prevents pressing Delete when coordinates target a component."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        service = WiringService(mock_bm)
        # Mock element check discovering a component (e.g. Breadboard / Servo)
        mock_page.evaluate = AsyncMock(return_value={
            "is_component": True,
            "component": "Breadboard Small",
            "message": "Safety guard: Target at (500, 400) is inside component 'Breadboard Small'.",
        })

        res = await service.delete_wire(500, 400)

        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "destructive_action_prevented")
        self.assertIn("Safety guard", res["message"])
        # Crucial: mouse click and keyboard press Delete must NEVER be called
        mock_page.mouse.click.assert_not_called()
        mock_page.keyboard.press.assert_not_called()

    async def test_delete_wire_no_wire_at_coordinates(self):
        """Aborts cleanly without pressing Delete when no wire is found at coordinates."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        service = WiringService(mock_bm)
        mock_page.evaluate = AsyncMock(return_value={
            "is_wire": False,
            "message": "No wire segment found at or near (200, 200).",
        })

        res = await service.delete_wire(200, 200)

        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "no_wire_at_coordinates")
        mock_page.mouse.click.assert_not_called()
        mock_page.keyboard.press.assert_not_called()

    async def test_delete_wire_success_on_verified_wire(self):
        """Successfully deletes wire when verified wire segment is found at coordinates."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.find_first_matching = AsyncMock(return_value=None)

        service = WiringService(mock_bm)
        # 1st evaluate: wire found with click target (205, 305)
        # 2nd evaluate: component selection check returns None (no component selected)
        # 3rd evaluate: save circuit editor state
        mock_page.evaluate = AsyncMock(side_effect=[
            {"is_wire": True, "click_x": 205, "click_y": 305},
            None,
            None,
        ])

        res = await service.delete_wire(200, 300)

        self.assertTrue(res["success"])
        self.assertIn("deleted successfully", res["message"])
        mock_page.mouse.click.assert_called_once_with(205, 305)
        mock_page.keyboard.press.assert_any_call("Delete")

    async def test_delete_wire_aborts_if_component_selected_by_click(self):
        """Aborts and clears selection if clicking wire coordinates accidentally selected a component."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        service = WiringService(mock_bm)
        # 1st evaluate: wire pre-check passes
        # 2nd evaluate: selection check reports a component got selected
        mock_page.evaluate = AsyncMock(side_effect=[
            {"is_wire": True, "click_x": 205, "click_y": 305},
            "Micro Servo",
        ])

        res = await service.delete_wire(200, 300)

        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "destructive_action_prevented")
        self.assertIn("Micro Servo", res["message"])
        # Must press Escape to deselect, and NEVER press Delete
        mock_page.keyboard.press.assert_called_once_with("Escape")

    async def test_delete_wire_between_never_blind_deletes_when_removal_fails(self):
        """delete_wire_between never falls back to blind Delete keypress when removal fails."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock()
        mock_bm.find_first_matching = AsyncMock(return_value=None)

        service = WiringService(mock_bm)
        existing_wires = [
            {"id": "w1", "source": {"type": "Arduino Uno R3", "pin": "D11"}, "target": {"type": "Piezo", "pin": "+"}},
        ]
        # Wire exists before and still exists after failed removal
        service._get_circuit_wires = AsyncMock(side_effect=[existing_wires, existing_wires])
        # evaluate returns False (removal failed)
        mock_page.evaluate = AsyncMock(return_value=False)

        res = await service.delete_wire_between(
            source_component="Arduino Uno R3",
            source_pin="D11",
            target_component="Piezo",
            target_pin="+",
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "wire_deletion_failed")
        # Ensure Delete key was NEVER pressed blindly!
        press_calls = [call.args[0] for call in mock_page.keyboard.press.call_args_list]
        self.assertNotIn("Delete", press_calls)


if __name__ == "__main__":
    unittest.main()
