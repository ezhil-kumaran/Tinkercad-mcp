"""Unit tests for CodeMirror precedence, code persistence verification,
pin moving, and atomic pin + code updating.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.browser.browser_manager import BrowserManager
from src.services.code_service import CodeService
from src.services.wiring_service import WiringService
from src.services.composite_service import CompositeService


class TestCodeMirrorPrecedenceAndPersistence(unittest.IsolatedAsyncioTestCase):
    """Test CodeMirror priority and persistence verification."""

    async def test_get_code_evaluates_codemirror_first(self):
        """CodeService.get_code should execute JavaScript query preferring CodeMirror."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_page.locator = MagicMock()
        mock_page.locator.return_value.count = AsyncMock(return_value=1)
        mock_page.locator.return_value.all_text_contents = AsyncMock(return_value=[])
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        # Mock evaluate returning code from CodeMirror
        sample_code = "int buzzer_pin = 11;\nvoid setup() {}\nvoid loop() {}"
        mock_page.evaluate = AsyncMock(return_value=sample_code)

        service = CodeService(mock_bm)
        service._ensure_code_panel_open = AsyncMock()
        service._get_current_mode = AsyncMock(return_value="Text")

        res = await service.get_code()
        self.assertTrue(res["success"])
        self.assertEqual(res["code"], sample_code)
        self.assertEqual(res["line_count"], 3)
        self.assertIn(".CodeMirror", mock_page.evaluate.call_args[0][0])

    async def test_set_code_success_with_verified_persistence(self):
        """CodeService.set_code should write via CodeMirror, reload, and verify persistence."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_page.url = "https://www.tinkercad.com/things/test-circuit-demo/editel"
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        code_to_set = "int buzzer_pin = 11;\nvoid setup() {}\nvoid loop() {}"

        # evaluate returns True for setting
        mock_page.evaluate = AsyncMock(return_value=True)
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.reload = AsyncMock()

        service = CodeService(mock_bm)
        service._ensure_code_panel_open = AsyncMock()
        service._switch_to_text_mode = AsyncMock()
        # get_code returns the new code on immediate and reloaded checks
        service.get_code = AsyncMock(return_value={
            "success": True,
            "line_count": 3,
            "code": code_to_set,
        })

        res = await service.set_code(code_to_set, ensure_text_mode=True, verify_persistence=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["verified"])
        self.assertEqual(res["line_count"], 3)
        mock_page.reload.assert_called_once()

    async def test_set_code_fails_when_code_reverts_on_reload(self):
        """CodeService.set_code must return failure if code reverts after reload (Issue 2/5)."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_page.url = "https://www.tinkercad.com/things/test-circuit-demo/editel"
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        new_code = "int buzzer_pin = 11;\nvoid setup() {}\nvoid loop() {}"
        reverted_code = "int buzzer_pin = 10;\nvoid setup() {}\nvoid loop() {}"

        mock_page.evaluate = AsyncMock(return_value=True)
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.reload = AsyncMock()

        service = CodeService(mock_bm)
        service._ensure_code_panel_open = AsyncMock()
        service._switch_to_text_mode = AsyncMock()

        # First get_code (immediate) matches new_code, second (after reload) returns reverted_code
        service.get_code = AsyncMock(side_effect=[
            {"success": True, "line_count": 3, "code": new_code},
            {"success": True, "line_count": 3, "code": reverted_code},
        ])

        res = await service.set_code(new_code, ensure_text_mode=True, verify_persistence=True)
        self.assertFalse(res["success"])
        self.assertFalse(res["verified"])
        self.assertEqual(res["error"], "code_persistence_failed")
        self.assertIn("reverted", res["message"])

    async def test_set_code_fails_when_immediate_readback_mismatches(self):
        """CodeService.set_code fails immediately if live editor did not accept code."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_page.url = "https://www.tinkercad.com/things/test/editel"
        mock_bm.get_page = AsyncMock(return_value=mock_page)

        mock_page.evaluate = AsyncMock(return_value=True)
        mock_page.wait_for_timeout = AsyncMock()

        service = CodeService(mock_bm)
        service._ensure_code_panel_open = AsyncMock()
        service._switch_to_text_mode = AsyncMock()
        service.get_code = AsyncMock(return_value={
            "success": True,
            "line_count": 1,
            "code": "old code",
        })

        res = await service.set_code("different code", ensure_text_mode=True, verify_persistence=True)
        self.assertFalse(res["success"])
        self.assertFalse(res["verified"])
        self.assertEqual(res["error"], "code_not_accepted")

    async def test_set_code_keyboard_fallback_uses_control_a(self):
        """When JS API evaluate returns False, fallback clicks editor and types with Control+a."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_page.url = "https://www.tinkercad.com/things/test/editel"
        mock_page.keyboard = AsyncMock()
        mock_editor_el = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.find_first_matching = AsyncMock(return_value=mock_editor_el)

        # evaluate returns False for JS API update, True for save block
        mock_page.evaluate = AsyncMock(side_effect=[False, True])
        mock_page.wait_for_timeout = AsyncMock()

        service = CodeService(mock_bm)
        service._ensure_code_panel_open = AsyncMock()
        service._switch_to_text_mode = AsyncMock()
        service.get_code = AsyncMock(return_value={
            "success": True,
            "line_count": 2,
            "code": "void setup() {}\nvoid loop() {}",
        })

        res = await service.set_code(
            "void setup() {}\nvoid loop() {}",
            ensure_text_mode=False,
            verify_persistence=False,
        )
        self.assertTrue(res["success"])
        mock_editor_el.click.assert_called_once()
        # Verify lowercase 'Control+a' was pressed (not uppercase 'Control+A')
        mock_page.keyboard.press.assert_any_call("Control+a")
        mock_page.keyboard.insert_text.assert_called_once_with("void setup() {}\nvoid loop() {}")

    async def test_ensure_code_panel_open_unblocks_pointer_events(self):
        """_ensure_code_panel_open must restore pointer-events to auto."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        # evaluate returns False for is_open check, then None for unblocking
        mock_page.evaluate = AsyncMock(side_effect=[False, None, None])
        mock_code_btn = AsyncMock()
        mock_bm.find_first_matching = AsyncMock(return_value=mock_code_btn)
        mock_page.wait_for_timeout = AsyncMock()

        service = CodeService(mock_bm)
        await service._ensure_code_panel_open(mock_page)

        mock_code_btn.click.assert_called_once()
        # Verify pointer-events evaluate call was made
        eval_scripts = [call[0][0] for call in mock_page.evaluate.call_args_list]
        self.assertTrue(any("pointerEvents = 'auto'" in s for s in eval_scripts))

    async def test_get_current_mode_defaults_to_blocks(self):
        """_get_current_mode defaults to 'Blocks' when editor is not text-ready."""
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value="Blocks")

        service = CodeService(mock_bm)
        mode = await service._get_current_mode(mock_page)
        self.assertEqual(mode, "Blocks")


class TestWiringMoveAndEndpointMatching(unittest.IsolatedAsyncioTestCase):
    """Test endpoint matching, wire deletion, and move_connection."""

    def test_endpoint_matches_various_forms(self):
        # Piezo terminal +
        ep_piezo = {"id": "_123", "name": "1", "type": "Piezo", "pin": "+"}
        self.assertTrue(WiringService._endpoint_matches(ep_piezo, "Piezo", "+"))
        self.assertTrue(WiringService._endpoint_matches(ep_piezo, "piezo", "positive"))
        self.assertTrue(WiringService._endpoint_matches(ep_piezo, "buzzer", "+"))
        self.assertFalse(WiringService._endpoint_matches(ep_piezo, "Piezo", "-"))

        # Arduino D10
        ep_arduino = {"id": "_456", "name": "1", "type": "Arduino Uno R3", "pin": "D10"}
        self.assertTrue(WiringService._endpoint_matches(ep_arduino, "Arduino", "D10"))
        self.assertTrue(WiringService._endpoint_matches(ep_arduino, "Arduino Uno R3", "10"))
        self.assertFalse(WiringService._endpoint_matches(ep_arduino, "Arduino", "D11"))

        # DC Motor Terminal 1
        ep_motor = {"id": "_789", "name": "2", "type": "DC Motor", "pin": "Terminal 1"}
        self.assertTrue(WiringService._endpoint_matches(ep_motor, "DC Motor", "Terminal 1"))
        self.assertTrue(WiringService._endpoint_matches(ep_motor, "dc_motor", "1"))
        self.assertFalse(WiringService._endpoint_matches(ep_motor, "DC Motor", "Terminal 2"))

    async def test_delete_wire_between_success(self):
        mock_bm = MagicMock(spec=BrowserManager)
        mock_page = AsyncMock()
        mock_bm.get_page = AsyncMock(return_value=mock_page)
        mock_bm.ensure_canvas_interactive = AsyncMock(return_value=True)

        service = WiringService(mock_bm)
        existing_wire = {
            "id": "_wire_10",
            "color": "green",
            "source": {"id": "_p1", "name": "1", "type": "Piezo", "pin": "+"},
            "target": {"id": "_a1", "name": "1", "type": "Arduino Uno R3", "pin": "D10"},
        }
        # First call has wire, second call (after deletion) is empty
        service._get_circuit_wires = AsyncMock(side_effect=[[existing_wire], []])
        mock_page.evaluate = AsyncMock(return_value=True)
        mock_page.wait_for_timeout = AsyncMock()

        res = await service.delete_wire_between(
            source_component="Piezo",
            source_pin="+",
            target_component="Arduino Uno R3",
            target_pin="D10",
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["wire_id"], "_wire_10")

    async def test_move_connection_success(self):
        mock_bm = MagicMock(spec=BrowserManager)
        service = WiringService(mock_bm)

        service.delete_wire_between = AsyncMock(return_value={"success": True, "wire_id": "_wire_10"})
        service.connect_component_pins = AsyncMock(return_value={
            "success": True,
            "wire_id": "_wire_11",
            "source": {"component": "Piezo", "pin": "+"},
            "target": {"component": "Arduino Uno R3", "pin": "D11"},
        })

        res = await service.move_connection(
            source_component="Piezo",
            source_pin="+",
            old_target_component="Arduino Uno R3",
            old_target_pin="D10",
            new_target_component="Arduino Uno R3",
            new_target_pin="D11",
            color="green",
        )
        self.assertTrue(res["success"])
        self.assertTrue(res["old_wire_deleted"])
        self.assertEqual(res["new_wire_id"], "_wire_11")
        self.assertEqual(res["target"]["pin"], "D11")


class TestCompositeChangePinAndUpdateCode(unittest.IsolatedAsyncioTestCase):
    """Test atomic pin move and code update composite workflow."""

    async def test_change_pin_and_update_code_success(self):
        mock_wiring = MagicMock(spec=WiringService)
        mock_code = MagicMock(spec=CodeService)

        # 1. Wire moved successfully
        mock_wiring.move_connection = AsyncMock(return_value={
            "success": True,
            "old_wire_deleted": True,
            "new_wire_id": "_wire_new",
        })

        # 2. Existing code contains buzzer_pin = 10
        original_code = (
            "int trigger_pin = 2;\n"
            "int echo_pin = 3;\n"
            "int buzzer_pin = 10;\n"
            "void setup() { pinMode(buzzer_pin, OUTPUT); }\n"
        )
        mock_code.get_code = AsyncMock(return_value={"success": True, "code": original_code})
        mock_code.set_code = AsyncMock(return_value={"success": True, "verified": True})

        composite = CompositeService(
            wiring=mock_wiring,
            code=mock_code,
        )

        res = await composite.change_pin_and_update_code(
            component="Piezo",
            component_pin="+",
            old_microcontroller_pin="D10",
            new_microcontroller_pin="D11",
            code_symbol="buzzer_pin",
            microcontroller_name="Arduino Uno R3",
            verify_persistence=True,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["physical_connection"]["new_pin"], "D11")
        self.assertTrue(res["code_update"]["updated"])
        self.assertTrue(res["code_update"]["verified"])

        # Verify that set_code was called with buzzer_pin = 11
        set_call_args = mock_code.set_code.call_args[1]
        self.assertIn("int buzzer_pin = 11;", set_call_args["code"])
        self.assertNotIn("int buzzer_pin = 10;", set_call_args["code"])

    async def test_change_pin_fails_if_physical_wiring_fails(self):
        mock_wiring = MagicMock(spec=WiringService)
        mock_code = MagicMock(spec=CodeService)

        mock_wiring.move_connection = AsyncMock(return_value={
            "success": False,
            "message": "Terminal not found",
        })

        composite = CompositeService(wiring=mock_wiring, code=mock_code)
        res = await composite.change_pin_and_update_code(
            component="Piezo",
            component_pin="+",
            old_microcontroller_pin="D10",
            new_microcontroller_pin="D11",
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "physical_rewiring_failed")
        # Code service should not have been updated
        mock_code.set_code.assert_not_called()


class TestBrowserLifecycleCleanup(unittest.IsolatedAsyncioTestCase):
    """Test graceful cleanup when Playwright transport is already dead."""

    async def test_close_locked_suppresses_none_send_error(self):
        bm = BrowserManager.get_instance()
        mock_ctx = AsyncMock()
        mock_ctx.close = AsyncMock(side_effect=AttributeError("'NoneType' object has no attribute 'send'"))
        mock_pw = AsyncMock()
        mock_pw.stop = AsyncMock(side_effect=RuntimeError("Event loop is closed"))

        bm.context = mock_ctx
        bm.playwright = mock_pw

        # Should complete cleanly without raising exception
        await bm.close_locked()
        self.assertIsNone(bm.context)
        self.assertIsNone(bm.playwright)


if __name__ == "__main__":
    unittest.main()
