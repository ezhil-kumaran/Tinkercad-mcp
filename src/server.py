"""Model Context Protocol (MCP) Server for Autodesk Tinkercad Circuits."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union
from mcp.server.mcpserver import MCPServer

from .browser.browser_manager import BrowserManager
from .services import (
    AuthService,
    CircuitsService,
    ComponentsService,
    WiringService,
    CodeService,
    SimulationService,
    SerialService,
    CompositeService,
    SchematicService,
)
from .config import logger

# Initialize MCP Server
server = MCPServer("tinkercad-circuits")

# Initialize backend services
browser = BrowserManager.get_instance()
auth_service = AuthService(browser)
circuits_service = CircuitsService(browser)
components_service = ComponentsService(browser)
wiring_service = WiringService(browser)
code_service = CodeService(browser)
simulation_service = SimulationService(browser)
serial_service = SerialService(browser)
schematic_service = SchematicService(browser)
composite_service = CompositeService(
    circuits=circuits_service,
    components=components_service,
    wiring=wiring_service,
    code=code_service,
    simulation=simulation_service,
)


def _format_error(tool_name: str, e: Exception) -> str:
    """Format an exception into a consistent JSON error response without exposing internal paths."""
    logger.error(f"Tool '{tool_name}' failed with error: {e}", exc_info=True)
    return json.dumps({
        "success": False,
        "error": str(e),
        "message": f"Tool '{tool_name}' failed: {e}",
    }, indent=2)


# ============================================================================
# 1. AUTHENTICATION & SESSION TOOLS
# ============================================================================

@server.tool()
async def tinkercad_auth_status() -> str:
    """Check whether the current Tinkercad browser session is authenticated and logged in."""
    try:
        res = await auth_service.get_auth_status()
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_auth_status", e)


@server.tool()
async def tinkercad_login(
    username: Optional[str] = None,
    password: Optional[str] = None,
    interactive: bool = True,
    timeout_seconds: int = 180,
) -> str:
    """Log in to Tinkercad / Autodesk account.

    If interactive is True (recommended for Autodesk SSO, Google Login, or 2FA),
    a visible browser window opens so you can sign in directly once.
    The session is cached permanently in your browser profile directory.
    """
    try:
        res = await auth_service.login(
            username=username,
            password=password,
            interactive=interactive,
            timeout_seconds=timeout_seconds,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_login", e)


@server.tool()
async def tinkercad_open_signup(interactive: bool = True) -> str:
    """Navigate to Tinkercad account creation / join page to create a new Autodesk account."""
    try:
        res = await auth_service.open_signup(interactive=interactive)
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_open_signup", e)


@server.tool()
async def tinkercad_logout() -> str:
    """Log out of the current Tinkercad session and clear persistent browser cookies."""
    try:
        res = await auth_service.logout()
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_logout", e)


@server.tool()
async def tinkercad_restart_browser(headless: Optional[bool] = None) -> str:
    """Restart or recover the persistent Tinkercad browser session and context.

    Use this if the browser window was closed, crashed, or disconnected.
    Automatically closes any dead context and re-opens the browser using the persistent session profile in .tinkercad_profile/.

    Args:
        headless: Optional boolean override for headless mode (True = headless, False = visible window)
    """
    try:
        res = await browser.restart(headless=headless)
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_restart_browser", e)


# ============================================================================
# 2. CIRCUIT DESIGN & NAVIGATION TOOLS
# ============================================================================

@server.tool()
async def tinkercad_list_circuits() -> str:
    """List all existing circuit designs available in the user's Tinkercad account."""
    try:
        res = await circuits_service.list_circuits()
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_list_circuits", e)


@server.tool()
async def tinkercad_open_circuit(
    circuit_id_or_url: Optional[str] = None,
    circuit_id: Optional[str] = None,
) -> str:
    """Open an existing circuit design in the Tinkercad editor by circuit ID or URL.

    Args:
        circuit_id_or_url: Circuit ID or full Tinkercad URL (e.g. '0abcdef123' or 'https://www.tinkercad.com/things/0abcdef123')
        circuit_id: Alias for circuit_id_or_url
    """
    target = circuit_id_or_url or circuit_id
    if not target:
        return json.dumps({
            "success": False,
            "message": "Either circuit_id_or_url or circuit_id must be provided.",
        }, indent=2)
    try:
        res = await circuits_service.open_circuit(circuit_id_or_url=target)
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_open_circuit", e)


@server.tool()
async def tinkercad_create_circuit(title: Optional[str] = None) -> str:
    """Create a brand new circuit design and open it in the editor.

    Args:
        title: Optional custom title to assign to the new circuit.
    """
    try:
        res = await circuits_service.create_circuit(title=title)
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_create_circuit", e)


@server.tool()
async def tinkercad_get_circuit_info() -> str:
    """Get metadata and current status for the currently open circuit (title, ID, simulation state)."""
    try:
        res = await circuits_service.get_circuit_info()
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_get_circuit_info", e)


@server.tool()
async def tinkercad_inspect_circuit() -> str:
    """Perform structured semantic circuit inspection without screenshots.

    Returns complete structured JSON with components, instance IDs, types, positions,
    pins, connection status, and all wire connections from the editor DOM and internal model.
    """
    try:
        res = await circuits_service.inspect_circuit()
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_inspect_circuit", e)


@server.tool()
async def tinkercad_rename_circuit(
    new_title: Optional[str] = None,
    new_name: Optional[str] = None,
) -> str:
    """Rename the currently open circuit in the editor.

    Args:
        new_title: New title to assign to the circuit
        new_name: Alias for new_title
    """
    title = new_title or new_name
    if not title:
        return json.dumps({
            "success": False,
            "message": "Either new_title or new_name must be provided.",
        }, indent=2)
    try:
        res = await circuits_service.rename_circuit(new_title=title)
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_rename_circuit", e)


@server.tool()
async def tinkercad_switch_workspace_view(view: str) -> str:
    """Switch the editor view using the workspace switcher ('circuits', 'schematic', or 'components').

    Args:
        view: Target view ('circuits'/'breadboard', 'schematic', 'components'/'component_list').
    """
    try:
        res = await circuits_service.switch_workspace_view(view=view)
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_switch_workspace_view", e)


@server.tool()
async def tinkercad_zoom_canvas(action: str = "fit", steps: int = 1) -> str:
    """Zoom or adjust the Tinkercad circuit canvas view to expand workspace or fit all components.

    Args:
        action: Zoom action:
            - 'fit': Zoom to fit all components into view (shortcut 'f')
            - 'out': Zoom out to expand visible canvas workspace
            - 'in': Zoom in for detailed inspection
            - 'reset': Reset view scale
        steps: Number of zoom steps to apply (default: 1, range 1-10)
    """
    try:
        res = await circuits_service.zoom_canvas(action=action, steps=steps)
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_zoom_canvas", e)


@server.tool()
async def tinkercad_validate_circuit_pre_simulation() -> str:
    """Perform pre-simulation checks on circuit integrity, electrical current limits, motor drivers, and code readiness."""
    try:
        res = await circuits_service.validate_circuit_pre_simulation()
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_validate_circuit_pre_simulation", e)


@server.tool()
async def tinkercad_take_screenshot(
    filename: Optional[str] = None, full_page: bool = False
) -> str:
    """Capture a screenshot of the Tinkercad editor workspace for visual inspection.

    Returns the path where the image is saved and image dimensions.
    """
    try:
        res = await browser.take_screenshot(filename=filename, full_page=full_page)
        # Exclude base64 from summary to keep JSON response compact
        summary = {
            "success": True,
            "saved_path": res["path"],
            "filename": res["filename"],
            "width": res["width"],
            "height": res["height"],
            "message": f"Screenshot successfully saved to {res['path']}",
        }
        return json.dumps(summary, indent=2)
    except Exception as e:
        return _format_error("tinkercad_take_screenshot", e)


# ============================================================================
# 3. COMPONENT TOOLS
# ============================================================================

@server.tool()
async def tinkercad_list_available_components(
    category: Optional[str] = None, search: Optional[str] = None
) -> str:
    """List or search electronic components in the Tinkercad catalog (e.g. Arduino Uno, LED, Resistor).

    Args:
        category: Filter by category (e.g. 'Microcontrollers', 'Basic', 'Sensors', 'Output', 'Power')
        search: Keyword search string (e.g. 'arduino', 'led', 'motor', 'ultrasonic')
    """
    try:
        res = await components_service.list_available_components(category=category, search=search)
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_list_available_components", e)


@server.tool()
async def tinkercad_add_component(
    component_name: Optional[str] = None,
    component_id: Optional[str] = None,
    circuit_id: Optional[str] = None,
    x: Optional[int] = None,
    y: Optional[int] = None,
    required_pins: Optional[List[str]] = None,
    min_pins: Optional[int] = None,
    verify_persistence: bool = False,
) -> str:
    """Place an electronic component onto the circuit canvas by name/type.

    Supports automatic disambiguation (e.g. prioritizing 4-pin HC-SR04 for ultrasonic sensor requests),
    post-placement pin verification, and optional persistence verification across page reload.

    Args:
        component_name: Name or keyword of component (e.g. 'Arduino Uno R3', 'LED', 'Resistor', 'Breadboard Small', 'H-bridge Motor Driver')
        component_id: Alias for component_name (accepts catalog ID or component name)
        circuit_id: Optional circuit ID to open before placing component
        x: Optional canvas X coordinate
        y: Optional canvas Y coordinate
        required_pins: Optional list of pin names that must exist on the component (e.g. ['trig', 'echo'])
        min_pins: Optional minimum required pin count (e.g. 4 for HC-SR04)
        verify_persistence: Optional flag to verify component survives page reload
    """
    target = component_name or component_id
    if not target:
        return json.dumps({
            "success": False,
            "message": "Either component_name or component_id must be provided.",
        }, indent=2)
    try:
        if circuit_id:
            await circuits_service.open_circuit(circuit_id)
        res = await components_service.add_component(
            component_name=target,
            x=x,
            y=y,
            required_pins=required_pins,
            min_pins=min_pins,
            verify_persistence=verify_persistence,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_add_component", e)


@server.tool()
async def tinkercad_remove_component(
    component_name: Optional[str] = None, x: Optional[int] = None, y: Optional[int] = None
) -> str:
    """Delete a component from the canvas by name or canvas coordinates."""
    try:
        res = await components_service.remove_component(component_name=component_name, x=x, y=y)
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_remove_component", e)


@server.tool()
async def tinkercad_set_component_property(
    property_name: str,
    value: str,
    unit: Optional[str] = None,
    instance_id: Optional[str] = None,
    component_name: Optional[str] = None,
) -> str:
    """Update a property on a component (e.g. resistance='220' unit='Ω', color='Green').

    Automatically selects the component if instance_id or component_name is provided,
    or selects the most recently placed component.

    Args:
        property_name: 'resistance', 'color', 'capacitance', 'name', etc.
        value: New value (e.g. '220', 'Red', 'Green', '10')
        unit: Optional unit for electrical values (e.g. 'Ω', 'kΩ', 'MΩ', 'µF', 'nF')
        instance_id: Optional component instance ID (auto-selects component on canvas)
        component_name: Optional component name or type (auto-selects component on canvas)
    """
    try:
        res = await components_service.set_component_property(
            property_name=property_name,
            value=value,
            unit=unit,
            instance_id=instance_id,
            component_name=component_name,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_set_component_property", e)


# ============================================================================
# 4. WIRING & CONNECTIONS TOOLS
# ============================================================================

@server.tool()
async def tinkercad_resolve_terminal(
    component: str,
    pin: str,
    component_name: Optional[str] = None,
) -> str:
    """Resolve a component terminal's exact identity and screen coordinates on the canvas.

    Supports Micro Servo ('signal', 'power', 'ground'), Arduino Uno R3 ('D9', '5V', 'GND'),
    motors, sensors, and passive components.

    Args:
        component: Component name or type (e.g. 'Micro Servo', 'Arduino Uno R3', 'LED')
        pin: Terminal or pin name (e.g. 'signal', 'power', 'ground', 'D9', '5V', 'GND')
        component_name: Optional specific instance name if multiple of same type exist
    """
    try:
        res = await wiring_service.resolve_terminal(
            component_query=component,
            pin_query=pin,
            component_name=component_name,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_resolve_terminal", e)


@server.tool()
async def tinkercad_connect_component_pins(
    source_component: Optional[str] = None,
    source_pin: Optional[str] = None,
    target_component: Optional[str] = None,
    target_pin: Optional[str] = None,
    color: Optional[str] = "green",
    allow_unsafe_direct: bool = False,
    # Common parameter aliases
    component1_id: Optional[str] = None,
    pin1: Optional[str] = None,
    component2_id: Optional[str] = None,
    pin2: Optional[str] = None,
    from_component: Optional[str] = None,
    from_pin: Optional[str] = None,
    to_component: Optional[str] = None,
    to_pin: Optional[str] = None,
) -> str:
    """Connect two named component pins semantically and verify the resulting wire connection.

    Resolves component identities and exact pin terminal coordinates from the structured DOM model,
    routes the wire, and confirms the resulting connection in the circuit state.
    Protects against overcurrent violations by preventing direct DC motor to microcontroller I/O pin connections.

    Args:
        source_component: Source component name/type or instance id (e.g. 'Arduino Uno R3', 'Arduino', 'Motor 1', 'H-bridge Motor Driver')
        source_pin: Source terminal/pin name (e.g. 'D6', 'D13', 'GND', '5V', 'Input1', 'Output1', 'trig')
        target_component: Target component name/type or instance id (e.g. 'DC Motor', 'Motor 2', 'LED', 'Ultrasonic Distance Sensor (4-pin)')
        target_pin: Target terminal/pin name (e.g. 'Terminal 1', '1', 'cathode', 'anode', 'echo')
        color: Wire color ('green', 'black', 'red', 'blue', 'yellow', 'orange', 'white', 'purple', 'brown')
        allow_unsafe_direct: If True, bypasses electrical safety check preventing direct motor-to-Arduino connections
        component1_id: Alias for source_component
        pin1: Alias for source_pin
        component2_id: Alias for target_component
        pin2: Alias for target_pin
        from_component: Alias for source_component
        from_pin: Alias for source_pin
        to_component: Alias for target_component
        to_pin: Alias for target_pin
    """
    src = source_component or component1_id or from_component
    sp = source_pin or pin1 or from_pin
    tgt = target_component or component2_id or to_component
    tp = target_pin or pin2 or to_pin

    if not src or not sp or not tgt or not tp:
        return json.dumps({
            "success": False,
            "error": "missing_required_parameters",
            "message": (
                "Missing required parameters. Required: source_component + source_pin + target_component + target_pin. "
                f"Received: source_component={src!r}, source_pin={sp!r}, target_component={tgt!r}, target_pin={tp!r}"
            ),
        }, indent=2)

    try:
        res = await wiring_service.connect_component_pins(
            source_component=src,
            source_pin=sp,
            target_component=tgt,
            target_pin=tp,
            color=color,
            allow_unsafe_direct=allow_unsafe_direct,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_connect_component_pins", e)


@server.tool()
async def tinkercad_connect_and_verify_wires(
    connections: Union[List[Dict[str, Any]], List[List[str]]],
    circuit_id_or_url: Optional[str] = None,
    clear_existing_wires: bool = False,
    code: Optional[str] = None,
    expected_wire_count: Optional[int] = None,
    verify_after_each: bool = True,
    reload_after_each: bool = False,
    verify_persistence: bool = True,
    run_schematic_erc: bool = True,
) -> str:
    """Robust, multi-connection wiring workflow that connects wires sequentially, verifies persistence, and validates schematic ERC.

    Features:
    - Accepts connection list as dicts or simple tuples/lists: e.g. [["Arduino Uno R3", "D2", "Ultrasonic Distance Sensor (4-pin)", "trig", "green"], ...]
    - Optional wire clearing: `clear_existing_wires=True` resets messy wiring before applying the clean netlist.
    - Integrated code upload: `code="..."` updates and verifies Arduino sketch in the same workflow.
    - Dynamic terminal discovery: Resolves fresh SVG screen coordinates immediately before every wire operation.
    - Duplicate wire prevention: Detects already-connected endpoint pairs and skips redundant wires.
    - Ground pin management: Automatically picks unused Arduino GND pins (GND1, GND2, GND3) or routes via Breadboard.
    - Autosave settling and reload persistence verification: Confirms wires survive circuit reload.
    - Schematic ERC validation: Runs Electrical Rule Checks to catch 5V-to-GND shorts, component self-shorts, and floating active VCC/GND pins.

    Args:
        connections: List of connection dicts or tuples/lists [source_comp, source_pin, target_comp, target_pin, (optional) color]
        circuit_id_or_url: Optional circuit ID or URL to open first (if not already in editor)
        clear_existing_wires: If True, clears all existing wires before applying new connections
        code: Optional Arduino C++ sketch code to inject and verify
        expected_wire_count: Optional expected final wire count to validate after completion
        verify_after_each: If True, verifies each wire in circuit model immediately after placement
        reload_after_each: If True, reloads after each wire (use for strict debugging)
        verify_persistence: If True, performs autosave wait and final reload verification
        run_schematic_erc: If True, runs Electrical Rule Checks to ensure circuit integrity
    """
    try:
        res = await wiring_service.connect_and_verify_wires(
            connections=connections,
            circuit_id_or_url=circuit_id_or_url,
            clear_existing_wires=clear_existing_wires,
            code=code,
            expected_wire_count=expected_wire_count,
            verify_after_each=verify_after_each,
            reload_after_each=reload_after_each,
            verify_persistence=verify_persistence,
            run_schematic_erc=run_schematic_erc,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_connect_and_verify_wires", e)


@server.tool()
async def tinkercad_connect_verified_netlist(
    connections: Any,
    circuit_id: Optional[str] = None,
    clear_existing: bool = True,
    verify_each: bool = True,
    verify_persistence: bool = True,
) -> str:
    """Connect a complete circuit netlist with instance-aware endpoint resolution,

    strict electrical pre-validation (power-to-ground shorts, self-wires, motor direct-drive),
    per-instance SVG terminal scoping, fail-fast per-wire verification, and cloud reload persistence.

    Example input:
    [
        ["Arduino:_269", "D9", "Servo:_291", "Signal"],
        ["Arduino:_269", "5V", "Servo:_291", "Power"],
        ["Arduino:_269", "GND1", "Servo:_291", "Ground"],
        ["Arduino:_269", "D2", "PIR:_282", "OUT"],
        ["Arduino:_269", "5V", "PIR:_282", "VCC"],
        ["Arduino:_269", "GND2", "PIR:_282", "GND"],
        ["Arduino:_269", "D13", "Resistor:_283", "1"],
        ["Resistor:_283", "2", "LED:_280", "Anode"],
        ["LED:_280", "Cathode", "Arduino:_269", "GND3"]
    ]

    Args:
        connections: List of connection tuples/dicts or JSON string.
        circuit_id: Optional circuit ID or URL to open first.
        clear_existing: If True, safely clears all existing wires before applying netlist.
        verify_each: If True, verifies each wire in the model immediately after placement and stops on error.
        verify_persistence: If True, triggers cloud autosave, reloads editor, and verifies that every connection persisted.
    """
    try:
        res = await wiring_service.connect_verified_netlist(
            circuit_id=circuit_id,
            connections=connections,
            clear_existing=clear_existing,
            verify_each=verify_each,
            verify_persistence=verify_persistence,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_connect_verified_netlist", e)


@server.tool()
async def tinkercad_route_pin_via_breadboard(
    component: str,
    pin: str,
    rail: str = "ground",
    color: Optional[str] = "black",
    microcontroller_name: str = "Arduino Uno R3",
) -> str:
    """Connect a component pin to a Breadboard power or ground rail when microcontroller pins are full or conflicted.

    Args:
        component: Component name or instance ID (e.g. 'Micro Servo', 'LED', 'Piezo')
        pin: Component terminal name (e.g. 'ground', 'power', 'cathode', 'anode')
        rail: 'ground' (negative rail '-') or 'power' (positive rail '+')
        color: Wire color (defaults to 'black' for ground, 'red' for power)
        microcontroller_name: Name of microcontroller (defaults to 'Arduino Uno R3')
    """
    try:
        res = await wiring_service.route_pin_via_breadboard(
            component=component,
            pin=pin,
            rail=rail,
            color=color,
            microcontroller_name=microcontroller_name,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_route_pin_via_breadboard", e)


@server.tool()
async def tinkercad_connect_pins(
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
    color: Optional[str] = "green",
    wire_type: Optional[str] = "normal",
) -> str:
    """(Low-level) Connect two points on the circuit canvas with a wire using raw screen coordinates.

    Verifies that a wire was actually created and snapped to terminals.

    Args:
        from_x: X coordinate of source terminal
        from_y: Y coordinate of source terminal
        to_x: X coordinate of destination terminal
        to_y: Y coordinate of destination terminal
        color: Wire color ('green', 'black', 'red', 'blue', 'yellow', 'orange', 'white', 'purple', 'brown')
        wire_type: Wire style ('normal', 'hookup', 'alligator')
    """
    try:
        res = await wiring_service.connect_pins(
            from_x=from_x,
            from_y=from_y,
            to_x=to_x,
            to_y=to_y,
            color=color,
            wire_type=wire_type,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_connect_pins", e)


@server.tool()
async def tinkercad_move_connection(
    source_component: str,
    source_pin: str,
    old_target_component: str,
    old_target_pin: str,
    new_target_component: str,
    new_target_pin: str,
    color: Optional[str] = "green",
) -> str:
    """Move a wire connection from an old target terminal to a new target terminal.

    Args:
        source_component: Source component name/type or instance id (e.g. 'Piezo', 'LED', 'DC Motor')
        source_pin: Source terminal/pin name (e.g. '+', 'anode', 'Terminal 1')
        old_target_component: Old target component name (e.g. 'Arduino Uno R3')
        old_target_pin: Old target terminal/pin name (e.g. 'D10', '10')
        new_target_component: New target component name (e.g. 'Arduino Uno R3')
        new_target_pin: New target terminal/pin name (e.g. 'D11', '11')
        color: Wire color ('green', 'red', 'black', 'blue', etc.)
    """
    try:
        res = await wiring_service.move_connection(
            source_component=source_component,
            source_pin=source_pin,
            old_target_component=old_target_component,
            old_target_pin=old_target_pin,
            new_target_component=new_target_component,
            new_target_pin=new_target_pin,
            color=color,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_move_connection", e)


@server.tool()
async def tinkercad_delete_wire(x: int, y: int) -> str:
    """Click on a wire at specified canvas coordinates and delete it."""
    try:
        res = await wiring_service.delete_wire(x=x, y=y)
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_delete_wire", e)


@server.tool()
async def tinkercad_delete_wire_between(
    source_component: str,
    source_pin: str,
    target_component: str,
    target_pin: str,
) -> str:
    """Find and delete a specific wire connecting two component pins without needing coordinates.

    Args:
        source_component: Source component name or ID (e.g. 'Arduino Uno R3', 'Piezo')
        source_pin: Source pin or terminal name (e.g. 'D11', '+', 'GND')
        target_component: Target component name or ID
        target_pin: Target pin or terminal name
    """
    try:
        res = await wiring_service.delete_wire_between(
            source_component=source_component,
            source_pin=source_pin,
            target_component=target_component,
            target_pin=target_pin,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_delete_wire_between", e)


@server.tool()
async def tinkercad_clear_circuit_wires(
    component_name: Optional[str] = None,
    verify_persistence: bool = False,
) -> str:
    """Clear all wires in the circuit, or all wires connected to a specific component.

    Useful for resetting messy wiring or rewiring cleanly in one step without deleting components.

    Args:
        component_name: Optional component name or ID to restrict wire deletion to (deletes all circuit wires if omitted)
        verify_persistence: If True, waits for autosave and reloads to confirm wire deletion persisted
    """
    try:
        res = await wiring_service.clear_circuit_wires(
            component_name=component_name,
            verify_persistence=verify_persistence,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_clear_circuit_wires", e)


# ============================================================================
# 5. CODE EDITOR TOOLS
# ============================================================================

@server.tool()
async def tinkercad_get_code() -> str:
    """Read the current Arduino C++ sketch or code from the editor."""
    try:
        res = await code_service.get_code()
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_get_code", e)


@server.tool()
async def tinkercad_set_code(
    code: str,
    ensure_text_mode: bool = True,
    verify_persistence: bool = True,
) -> str:
    """Write/inject Arduino C++ source code into the CodeMirror editor and verify persistence.

    Args:
        code: Full Arduino C++ source code (including setup() and loop())
        ensure_text_mode: If True, automatically confirms switching from Blocks to Text mode.
        verify_persistence: If True, verifies code was accepted and persists across project reload.
    """
    try:
        res = await code_service.set_code(
            code=code,
            ensure_text_mode=ensure_text_mode,
            verify_persistence=verify_persistence,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_set_code", e)


# ============================================================================
# 6. SIMULATION CONTROL TOOLS
# ============================================================================

@server.tool()
async def tinkercad_start_simulation(wait_seconds: int = 2) -> str:
    """Start running the circuit simulation and verify active execution."""
    try:
        res = await simulation_service.start_simulation(wait_seconds=wait_seconds)
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_start_simulation", e)


@server.tool()
async def tinkercad_stop_simulation() -> str:
    """Stop the running circuit simulation."""
    try:
        res = await simulation_service.stop_simulation()
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_stop_simulation", e)


@server.tool()
async def tinkercad_get_simulation_status() -> str:
    """Check if simulation is actively running, view elapsed simulator time, and check for errors."""
    try:
        res = await simulation_service.get_simulation_status()
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_get_simulation_status", e)


# ============================================================================
# 7. SERIAL MONITOR TOOLS
# ============================================================================

@server.tool()
async def tinkercad_open_serial_monitor() -> str:
    """Open or focus the Arduino Serial Monitor drawer."""
    try:
        res = await serial_service.open_serial_monitor()
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_open_serial_monitor", e)


@server.tool()
async def tinkercad_read_serial_monitor(last_n_lines: int = 50) -> str:
    """Read logged lines from the Arduino Serial Monitor."""
    try:
        res = await serial_service.read_serial_monitor(last_n_lines=last_n_lines)
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_read_serial_monitor", e)


@server.tool()
async def tinkercad_send_serial_monitor(text: str) -> str:
    """Send text input or serial commands to the running Arduino via the Serial Monitor."""
    try:
        res = await serial_service.send_serial_monitor(text=text)
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_send_serial_monitor", e)


@server.tool()
async def tinkercad_clear_serial_monitor() -> str:
    """Clear all text output from the Serial Monitor."""
    try:
        res = await serial_service.clear_serial_monitor()
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_clear_serial_monitor", e)


# ============================================================================
# 8. COMPOSITE WORKFLOW TOOL
# ============================================================================

@server.tool()
async def tinkercad_build_circuit(
    circuit_id: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    components_json: Optional[Union[str, List[Dict[str, Any]]]] = None,
    wires_json: Optional[Union[str, List[Dict[str, Any]]]] = None,
    components: Optional[Union[str, List[Dict[str, Any]]]] = None,
    wires: Optional[Union[str, List[Dict[str, Any]]]] = None,
    arduino_code: Optional[str] = None,
    code: Optional[str] = None,
    run_simulation: bool = False,
) -> str:
    """Build a complete circuit in one call: place components, connect wires, upload code, and optionally simulate.

    Args:
        circuit_id: Optional existing circuit ID to build within (e.g. '2zkRyaDfhkA'). If omitted, creates a new circuit using title.
        title: Optional title for the new or renamed circuit.
        description: Optional natural language description or summary of the circuit.
        components_json: List of component objects or JSON string array, e.g. [{"name": "Arduino Uno R3", "x": 300, "y": 300}, {"name": "LED", "x": 600, "y": 300}].
        wires_json: List of wire connection objects or JSON string array, e.g. [{"source_component": "Arduino Uno R3", "source_pin": "D13", "target_component": "LED", "target_pin": "anode"}].
        components: Alias for components_json (accepts list or JSON string).
        wires: Alias for wires_json (accepts list or JSON string).
        arduino_code: Arduino C++ sketch code.
        code: Alias for arduino_code.
        run_simulation: Whether to start simulation after building.
    """
    effective_code = arduino_code if arduino_code is not None else code
    valid, err_msg, comps, wire_list = CompositeService.validate_build_inputs(
        components_json=components_json,
        wires_json=wires_json,
        description=description,
        components=components,
        wires=wires,
    )
    if not valid:
        return json.dumps({
            "success": False,
            "error": err_msg,
            "message": err_msg,
        }, indent=2)

    try:
        res = await composite_service.build_circuit(
            circuit_id=circuit_id,
            title=title,
            components=comps,
            wires=wire_list,
            arduino_code=effective_code,
            run_simulation=run_simulation,
            description=description,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_build_circuit", e)


@server.tool()
async def tinkercad_change_pin_and_update_code(
    component: str,
    component_pin: str,
    old_microcontroller_pin: str,
    new_microcontroller_pin: str,
    code_symbol: Optional[str] = None,
    microcontroller_name: Optional[str] = "Arduino Uno R3",
    wire_color: Optional[str] = "green",
    verify_persistence: bool = True,
) -> str:
    """Atomically move a physical wire connection and update its Arduino sketch code with persistence verification.

    Args:
        component: Name or type of component (e.g. 'Piezo', 'Buzzer', 'DC Motor', 'LED')
        component_pin: Terminal on the component (e.g. '+', 'Terminal 1', 'anode')
        old_microcontroller_pin: Current pin on microcontroller (e.g. 'D10', '10')
        new_microcontroller_pin: Destination pin on microcontroller (e.g. 'D11', '11')
        code_symbol: Optional variable name in Arduino sketch code (e.g. 'buzzer_pin', 'motor')
        microcontroller_name: Microcontroller name (defaults to 'Arduino Uno R3')
        wire_color: Color of the new wire ('green', 'red', 'blue', etc.)
        verify_persistence: Verify that the code update persists across project reload
    """
    try:
        res = await composite_service.change_pin_and_update_code(
            component=component,
            component_pin=component_pin,
            old_microcontroller_pin=old_microcontroller_pin,
            new_microcontroller_pin=new_microcontroller_pin,
            code_symbol=code_symbol,
            microcontroller_name=microcontroller_name,
            wire_color=wire_color,
            verify_persistence=verify_persistence,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_change_pin_and_update_code", e)


@server.tool()
async def tinkercad_add_servo_with_distance_control(
    distance_threshold: int = 30,
    angle_when_near: int = 150,
    angle_when_far: int = 0,
    signal_pin: Optional[str] = None,
) -> str:
    """Add a Micro Servo, connect signal, power (5V), and ground (GND), and program distance-triggered positioning.

    Args:
        distance_threshold: Distance in centimeters below which the servo turns (default 30)
        angle_when_near: Angle in degrees when object is closer than threshold (default 150)
        angle_when_far: Angle in degrees when object is farther than threshold (default 0)
        signal_pin: Optional PWM pin on Arduino (e.g. 'D9'). If omitted, selects an unused PWM pin automatically.
    """
    try:
        res = await composite_service.add_servo_with_distance_control(
            distance_threshold=distance_threshold,
            angle_when_near=angle_when_near,
            angle_when_far=angle_when_far,
            signal_pin=signal_pin,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_add_servo_with_distance_control", e)


@server.tool()
async def tinkercad_check_electrical_safety() -> str:
    """Analyze the current circuit for electrical safety and component current ratings.

    Detects:
    1. Direct DC motor to microcontroller I/O pin connections (exceeding ATmega328P 40 mA rating).
    2. Missing motor driver IC (e.g. L293D H-bridge) for inductive loads.
    3. Missing external power supply for high-drain motors.
    4. Common ground connectivity.
    """
    try:
        res = await wiring_service.check_circuit_electrical_safety()
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_check_electrical_safety", e)


@server.tool()
async def tinkercad_build_robot_car(
    stop_threshold: int = 30,
    trig_pin: str = "D2",
    echo_pin: str = "D3",
    in1_pin: str = "D4",
    in2_pin: str = "D5",
    in3_pin: str = "D6",
    in4_pin: str = "D7",
) -> str:
    """Build a complete, electrically safe 4-wheel obstacle-stopping robot car in Tinkercad.

    Creates an organized layout:
    - Arduino Uno R3 + Breadboard Small
    - H-bridge Motor Driver (L293D) for inductive isolation
    - Exact 4-pin Ultrasonic Sensor (HC-SR04) with verified Trig and Echo pins
    - 4 DC Motors driven via L293D outputs
    - 9V Battery providing dedicated motor power with common ground
    - Power & ground routed cleanly through breadboard rails
    - Injects and verifies persistent Arduino obstacle-stop code (threshold in cm)

    Args:
        stop_threshold: Obstacle detection threshold distance in cm (default 30)
        trig_pin: Arduino pin connected to HC-SR04 Trigger (default 'D2')
        echo_pin: Arduino pin connected to HC-SR04 Echo (default 'D3')
        in1_pin: Arduino pin for Motor Driver Input 1 (default 'D4')
        in2_pin: Arduino pin for Motor Driver Input 2 (default 'D5')
        in3_pin: Arduino pin for Motor Driver Input 3 (default 'D6')
        in4_pin: Arduino pin for Motor Driver Input 4 (default 'D7')
    """
    try:
        res = await composite_service.build_robot_car_architecture(
            stop_threshold=stop_threshold,
            trig_pin=trig_pin,
            echo_pin=echo_pin,
            in1_pin=in1_pin,
            in2_pin=in2_pin,
            in3_pin=in3_pin,
            in4_pin=in4_pin,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_build_robot_car", e)


# ============================================================================
# 10. SCHEMATIC ANALYSIS & CONNECTION VERIFICATION TOOLS
# ============================================================================

@server.tool()
async def tinkercad_get_schematic_svg(
    save_path: Optional[str] = None,
    switch_to_schematic: bool = True,
    return_to_view: Optional[str] = "circuits",
) -> str:
    """Capture the complete schematic SVG diagram from Tinkercad and save it to disk.

    Extracts clean vector SVG data, junction dots, component symbols (U1, DIST1, etc.),
    and wire paths directly from the schematic canvas.

    Args:
        save_path: Optional output path (defaults to screenshots/schematic_<timestamp>.svg).
        switch_to_schematic: If True, switches workspace view to Schematic view first.
        return_to_view: Optional view name ('circuits'/'breadboard') to return to after capture.
    """
    try:
        res = await schematic_service.get_schematic_svg(
            save_path=save_path,
            switch_to_schematic=switch_to_schematic,
            return_to_view=return_to_view,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_get_schematic_svg", e)


@server.tool()
async def tinkercad_inspect_schematic_connections() -> str:
    """Inspect and extract the complete electrical netlist from the schematic and circuit model.

    Groups all connected pins into canonical Electrical Nets (Net_1, Net_2, etc.) using
    Union-Find tracing, classifies net types (Power, Ground, Signal, Short Circuit),
    and lists all unconnected pins.
    """
    try:
        res = await schematic_service.inspect_schematic_connections()
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_inspect_schematic_connections", e)


@server.tool()
async def tinkercad_verify_schematic_connections(strict: bool = True) -> str:
    """Perform Electrical Rule Checks (ERC) on the schematic connections to detect and prevent wiring flaws.

    Verifies:
    1. Power-to-Ground Shorts: Flags any net connecting 5V/VCC directly to GND (catastrophic short).
    2. Component Self-Shorts: Flags 2-terminal components (Piezo, LED, Resistor, Motor) where both pins share the same net.
    3. Floating Power or Ground: Flags active sensors/ICs (HC-SR04 Ultrasonic VCC/GND, PIR, TMP36, Servo, Motor Driver) left unconnected.
    4. Pin Connection Conflicts: Flags passive devices (Piezo) bridged to 3+ contradictory pins.
    5. Actionable recommendations and fix instructions for each detected violation.

    Args:
        strict: If True, fails whenever any critical ERC violation is detected.
    """
    try:
        res = await schematic_service.verify_schematic_connections(strict=strict)
        return json.dumps(res, indent=2)
    except Exception as e:
        return _format_error("tinkercad_verify_schematic_connections", e)


# ============================================================================
# 8. MCP RESOURCES
# ============================================================================

@server.resource(
    "tinkercad://instructions",
    name="Agent Instructions & Best Practices",
    description="Comprehensive guide on building circuits, pinouts, and 1-call build signatures",
    mime_type="text/markdown",
)
def get_mcp_instructions() -> str:
    """Return agent instructions and best practices."""
    import pathlib
    inst_path = pathlib.Path(__file__).parent.parent / "instructions.md"
    if inst_path.exists():
        return inst_path.read_text(encoding="utf-8")
    return "Tinkercad MCP Server Instructions"


@server.resource(
    "tinkercad://pinouts",
    name="Canonical Component Pinout Reference",
    description="Exact terminal pin names and formulas for microcontrollers, sensors, and actuators",
    mime_type="application/json",
)
def get_mcp_pinouts() -> str:
    """Return JSON table of canonical pin names for popular components."""
    pinouts = {
        "Arduino Uno R3": {
            "power": ["5V", "3V3", "VIN", "IOREF"],
            "grounds": ["GND1", "GND2", "GND3"],
            "analog": ["A0", "A1", "A2", "A3", "A4", "A5"],
            "digital": [f"D{i}" for i in range(14)],
            "pwm": ["D3", "D5", "D6", "D9", "D10", "D11"],
        },
        "Temperature Sensor [TMP36]": {
            "terminals": ["Vs", "Vout", "Gnd"],
            "aliases": {"power": "Vs", "vcc": "Vs", "vout": "Vout", "signal": "Vout", "ground": "Gnd", "gnd": "Gnd"},
            "formula": "tempC = (voltage - 0.5) * 100.0",
        },
        "Micro Servo": {
            "terminals": ["Power", "Signal", "Ground"],
            "aliases": {"power": "Power", "signal": "Signal", "ground": "Ground"},
            "wire_colors": {"Power": "red", "Signal": "orange", "Ground": "black"},
        },
        "Ultrasonic Distance Sensor (HC-SR04)": {
            "terminals": ["pos", "trig", "echo", "neg"],
            "aliases": {"vcc": "pos", "power": "pos", "gnd": "neg", "ground": "neg", "trigger": "trig"},
            "formula": "distanceCm = (durationMicroseconds * 0.0343) / 2.0",
        },
        "Piezo (Buzzer)": {
            "terminals": ["Positive", "Negative"],
            "aliases": {"pos": "Positive", "+": "Positive", "neg": "Negative", "-": "Negative"},
        },
        "LED": {
            "terminals": ["Anode", "Cathode"],
            "aliases": {"pos": "Anode", "+": "Anode", "neg": "Cathode", "-": "Cathode"},
        },
        "H-bridge Motor Driver (L293D)": {
            "terminals": [
                "Enable 1,2", "Input 1", "Output 1", "Ground 1", "Ground 2", "Output 2", "Input 2", "Power 2 (Vmotor)",
                "Enable 3,4", "Input 3", "Output 3", "Ground 3", "Ground 4", "Output 4", "Input 4", "Power 1 (Vlogic)",
            ],
        },
    }
    return json.dumps(pinouts, indent=2)


@server.resource(
    "tinkercad://examples/build_circuit",
    name="Working Build Circuit Payloads",
    description="Ready-to-use JSON payloads for tinkercad_build_circuit",
    mime_type="application/json",
)
def get_mcp_examples() -> str:
    """Return working build circuit example payloads."""
    examples = {
        "temperature_controlled_servo": {
            "title": "amazing",
            "components": [
                {"name": "Arduino Uno R3", "x": 300, "y": 350},
                {"name": "Temperature Sensor", "x": 650, "y": 250},
                {"name": "Micro Servo", "x": 650, "y": 480},
            ],
            "wires": [
                {"source_component": "Temperature Sensor", "source_pin": "Vs", "target_component": "Arduino Uno R3", "target_pin": "5V", "color": "red"},
                {"source_component": "Temperature Sensor", "source_pin": "Gnd", "target_component": "Arduino Uno R3", "target_pin": "GND2", "color": "black"},
                {"source_component": "Temperature Sensor", "source_pin": "Vout", "target_component": "Arduino Uno R3", "target_pin": "A0", "color": "blue"},
                {"source_component": "Micro Servo", "source_pin": "Power", "target_component": "Arduino Uno R3", "target_pin": "5V", "color": "red"},
                {"source_component": "Micro Servo", "source_pin": "Ground", "target_component": "Arduino Uno R3", "target_pin": "GND1", "color": "black"},
                {"source_component": "Micro Servo", "source_pin": "Signal", "target_component": "Arduino Uno R3", "target_pin": "D9", "color": "orange"},
            ],
            "arduino_code": "#include <Servo.h>\n\nServo myServo;\nconst int tempPin = A0;\nconst int servoPin = 9;\n\nvoid setup() {\n  myServo.attach(servoPin);\n  myServo.write(0);\n}\n\nvoid loop() {\n  float voltage = analogRead(tempPin) * (5.0 / 1024.0);\n  float tempC = (voltage - 0.5) * 100.0;\n  if (tempC > 30.0) myServo.write(150);\n  else myServo.write(0);\n  delay(500);\n}",
            "run_simulation": True,
        }
    }
    return json.dumps(examples, indent=2)


# ============================================================================
# 9. MCP PROMPTS
# ============================================================================

@server.prompt(
    name="build_circuit",
    description="Guidance prompt for designing, wiring, and programming an electronic circuit in Tinkercad",
)
def prompt_build_circuit(project_name: str, goal: str) -> str:
    """Return structured system prompt for building a complete circuit."""
    return f"""You are tasked with building the '{project_name}' circuit in Autodesk Tinkercad Circuits to achieve: {goal}.

RECOMMENDED WORKFLOW:
1. Use `tinkercad_build_circuit` as your primary 1-call builder with:
   - title: "{project_name}"
   - components: list of {{"name": ..., "x": ..., "y": ...}}
   - wires: list of {{"source_component": ..., "source_pin": ..., "target_component": ..., "target_pin": ..., "color": ...}}
   - arduino_code: complete C++ sketch
   - run_simulation: true

2. PIN RULES:
   - Arduino Uno R3: 5V, 3.3V, GND1, GND2, GND3, A0-A5, D0-D13.
   - Temperature Sensor (TMP36): Vs (Power), Vout (Analog Out), Gnd (Ground).
   - Micro Servo: Power (5V), Signal (PWM, e.g. D9), Ground (GND).
   - Ultrasonic (HC-SR04): pos (5V), trig (D2), echo (D3), neg (GND).

3. ELECTRICAL SAFETY:
   - Never wire DC motors directly to Arduino I/O pins (exceeds 40mA rating). Use L293D H-bridge.
   - Connect common ground between power sources.

4. VERIFICATION:
   - Use `tinkercad_take_screenshot` to confirm visual layout.
   - Use `tinkercad_read_serial_monitor` to observe sensor outputs during simulation.
"""


@server.prompt(
    name="safety_check",
    description="Prompt for auditing electrical safety, current limits, and short circuits",
)
def prompt_safety_check(circuit_id: Optional[str] = None) -> str:
    """Return prompt for performing an electrical safety audit."""
    target = f"circuit '{circuit_id}'" if circuit_id else "the current active circuit"
    return f"""Please perform a comprehensive electrical safety check on {target}.
1. Call `tinkercad_check_electrical_safety` to detect overcurrent or DC motor violations.
2. Call `tinkercad_verify_schematic_connections` with strict=True to check:
   - Power-to-Ground short circuits.
   - Component self-shorts.
   - Floating active sensors or microcontrollers.
3. Review any issues found and suggest exact wiring corrections.
"""
