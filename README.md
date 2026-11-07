# Tinkercad Circuits MCP Server (Python)

A complete **Model Context Protocol (MCP)** server for automating **Autodesk Tinkercad Circuits** using Python, Playwright, and the official Python MCP SDK.

This server enables AI assistants (such as Claude Desktop, Cursor, Antigravity, or custom agents) to programmatically design, wire, code, simulate, and debug electronic circuits directly inside the Tinkercad web interface.

---

## 🤖 AI Agent Quick Reference & Prompts

* **[Agent Instructions (`instructions.md`)](instructions.md)** — Core tool usage rules, canonical component & pin names, and best practices.
* **[Complete Agent Guide (`AGENT_GUIDE.md`)](AGENT_GUIDE.md)** — Full 1-call `tinkercad_build_circuit` examples, pinout references, and conversion formulas.

---

## 🚀 Key Features

* **Authentication & Session Persistence:**
  * One-time login via interactive Chrome window or credentials.
  * Preserves cookies, login tokens, and session state locally in `.tinkercad_profile/`.
  * Support for Autodesk SSO, Google Sign-in, and Tinkercad Classrooms / Nicknames.
* **Performance & Telemetry Route Blocking:**
  * Automatically intercepts and blocks heavy analytics, tracking, and telemetry network calls (Segment, Hotjar, Google Analytics, Optimizely, Datadog) to dramatically accelerate Tinkercad WebGL initialization and reduce CPU/memory load.
  * Bounded evaluation timeouts (12s) with instant SVG DOM fallbacks to eliminate long browser context hangs.
* **UI Pointer Interception Protection:**
  * Proactively collapses the visual Blocks Code Drawer upon circuit creation, opening, and before canvas interactions.
  * Automatically detects transparent Blockly canvas/overlay click interception and ensures seamless placement and wiring.
* **Collision-Avoidance Auto-Layout Engine:**
  * Prevents component stacking at default origin coordinates `(161, -76)`.
  * Automatically separates microcontrollers, breadboards, sensors, actuators, and passives into distinct, non-overlapping canvas zones with safe clearance ($\ge 140\text{px}$) so terminal hitboxes never collide.
* **Bi-directional Pin Alias Normalization:**
  * Seamlessly resolves internal model pin names (`pos`, `neg`) and visible SVG DOM labels (`Vcc`, `GND`, `Trigger`, `Echo`) for HC-SR04 ultrasonic sensors and piezos.
* **Circuit Design Management:**
  * List all existing circuits in your account with titles, IDs, and thumbnail URLs.
  * Open any circuit directly in the editor.
  * Create new circuit designs and rename them.
  * Capture workspace screenshots for visual multimodal inspection.
* **Component Placement & Property Control:**
  * Built-in component catalog (Arduino Uno R3, Micro:bit, Breadboard, Resistors, LEDs, RGB LEDs, Sensors, Motors, LCDs, etc.).
  * Place components onto the canvas at precise or auto-distributed coordinates.
  * Remove components from the workplane.
  * Configure component attributes (e.g., resistance `220 Ω`, LED color `Green`, capacitor values).
* **Pin-to-Pin Wiring:**
  * Route wires between component terminals/pins with custom wire colors (red, black, green, blue, yellow, etc.) and wire styles.
  * Delete wires.
* **Arduino Code Editor:**
  * Read existing sketch code.
  * Automatically switch from Blocks mode to C++ Text mode (handles confirmation dialogs).
  * Inject custom Arduino sketches with `setup()` and `loop()`.
* **Simulation & Diagnostics:**
  * Start and stop the in-browser AVR simulator.
  * Monitor simulation state, elapsed time, and error notifications.
* **Serial Monitor:**
  * Open the Serial Monitor panel.
  * Read output streams printed via `Serial.print()` / `Serial.println()`.
  * Send input strings and commands to the simulated Arduino.
  * Clear the Serial Monitor log.

---

## 📦 Project Structure

```
Tinkercad-mcp/
├── .venv/                         # Python virtual environment
├── .tinkercad_profile/            # Persistent browser session & cookies (gitignored)
├── screenshots/                   # Workspace screenshots captured by tools
├── requirements.txt               # pip dependencies
├── pyproject.toml                 # Package definition & CLI entry points
├── src/
│   ├── config.py                  # Environment settings, timeouts, and URLs
│   ├── main.py                    # Stdio MCP server runner
│   ├── server.py                  # MCPServer instance and tool definitions
│   ├── browser/
│   │   ├── browser_manager.py     # Playwright persistent context & page lifecycle
│   │   └── selectors.py           # Robust DOM selectors for Tinkercad Circuits
│   ├── catalog/
│   │   └── components_catalog.py  # Electronic parts, pinouts, and default properties
│   ├── services/
│   │   ├── auth_service.py        # Login, signup, logout, auth status
│   │   ├── circuits_service.py    # List, open, create, rename circuits
│   │   ├── components_service.py  # Place, remove, configure components
│   │   ├── wiring_service.py      # Route wires between terminals
│   │   ├── code_service.py        # Read and inject Arduino C++ sketch code
│   │   ├── simulation_service.py  # Start, stop, and monitor simulator
│   │   ├── serial_service.py      # Serial monitor read, send, clear
│   │   └── composite_service.py   # High-level build_circuit workflow
│   └── cli/
│       ├── login_cli.py           # Interactive browser login helper
│       └── list_tools_cli.py      # Command to list and verify all MCP tools
└── tests/
    └── test_tools.py              # Unit tests for tools, catalog, and config
```

---

## 🛠️ Setup Instructions

### 1. Prerequisites
* **Python 3.10+** (Python 3.12 recommended)
* **pip** and **venv**

### 2. Virtual Environment & Dependencies
If not already created:
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
# source .venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Install Playwright Chromium browser
playwright install chromium
```

### 3. One-Time Authentication
Run the interactive login command to sign into your Tinkercad / Autodesk account:
```bash
python -m src.cli.login_cli
```
* A Google Chrome browser window will open at `https://www.tinkercad.com/login`.
* Log in with your Autodesk ID, Google account, or student nickname.
* Once you land on your Tinkercad dashboard, the CLI will automatically detect your login, save your session cookies in `.tinkercad_profile/`, and exit.

### 4. Verify Registered Tools
To inspect the 45 registered MCP tools:
```bash
python -m src.cli.list_tools_cli
```

### 5. Run Unit Tests
```bash
python -m unittest discover tests
```

### 6. Run End-to-End Example (Optional)
To programmatically build, wire, program, and simulate a complete temperature-controlled servo circuit:
```bash
python examples/build_temperature_circuit.py
```

---

## 🔌 Connecting to MCP Clients

### A. Claude Desktop
Add this to your `claude_desktop_config.json` (`%APPDATA%\Claude\claude_desktop_config.json` on Windows, or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "tinkercad-circuits": {
      "command": "python",
      "args": ["-m", "src.main"],
      "cwd": "/path/to/Tinkercad-mcp"
    }
  }
}
```

> **Windows Note**: Use absolute path to the venv Python executable, for example:
> `"command": "C:\\path\\to\\Tinkercad-mcp\\.venv\\Scripts\\python.exe"` and `"cwd": "C:\\path\\to\\Tinkercad-mcp"`.
> **macOS / Linux Note**: Use `"command": "/path/to/Tinkercad-mcp/.venv/bin/python"` and `"cwd": "/path/to/Tinkercad-mcp"`.

### B. Cursor (.cursor/mcp.json)
Create or edit `.cursor/mcp.json` in your project workspace:

```json
{
  "mcpServers": {
    "tinkercad": {
      "command": "python",
      "args": ["-m", "src.main"],
      "cwd": "/path/to/Tinkercad-mcp"
    }
  }
}
```

### C. Testing with MCP Inspector
You can test the server interactively via the official MCP Inspector:
```bash
npx @modelcontextprotocol/inspector .venv/Scripts/python.exe -m src.main
```

---

## 📚 Complete Tools Reference (45 Tools)

### 1. Authentication & Session
* `tinkercad_auth_status()`: Checks if current session is authenticated.
* `tinkercad_login(username, password, interactive, timeout_seconds)`: Performs interactive or automated login and caches session.
* `tinkercad_open_signup(interactive)`: Opens Tinkercad account creation page.
* `tinkercad_logout()`: Logs out and clears stored session cookies.
* `tinkercad_restart_browser(headless)`: Restarts or recovers the persistent Playwright browser context using `.tinkercad_profile/` without needing to restart the MCP server process. Automatically closes stale/crashed contexts and opens a clean, connected session.

### 2. Circuit Design Management
* `tinkercad_list_circuits()`: Lists all existing circuit designs in the account (titles, IDs, URLs, thumbnails).
* `tinkercad_open_circuit(circuit_id_or_url)`: Opens an existing circuit in the editor.
* `tinkercad_create_circuit(title)`: Creates a new circuit and loads the editor.
* `tinkercad_get_circuit_info()`: Retrieves active circuit title, URL, component count, and simulation state.
* `tinkercad_inspect_circuit()`: Performs semantic circuit inspection returning structured components, pins with `connected_to` metadata, and wire connections without taking screenshots.
* `tinkercad_rename_circuit(new_title)`: Renames the currently open circuit.
* `tinkercad_take_screenshot(filename, full_page)`: Captures a PNG screenshot of the workspace.
* `tinkercad_switch_workspace_view(view)`: Switches the editor view between `'circuits'` (breadboard view), `'schematic'` (schematic diagram), and `'components'` (BOM component list).
* `tinkercad_validate_circuit_pre_simulation()`: Performs comprehensive pre-simulation checks: verifies component integrity, checks wire endpoints, detects electrical overcurrent violations (>40 mA limits), verifies motor driver presence, and checks Arduino code mode (Text vs Blocks).

### 3. Component Management
* `tinkercad_list_available_components(category, search)`: Lists electronic components with pinouts and properties.
* `tinkercad_add_component(component_name, x, y, required_pins, min_pins)`: Places a component on canvas by exact stable identity, rejects ambiguous matches and hidden chevrons, verifies pin counts and required pins (e.g. 4-pin HC-SR04 vs 3-pin sensor), and cleans up mismatched components automatically.
* `tinkercad_remove_component(component_name, x, y)`: Deletes a component from the canvas.
* `tinkercad_set_component_property(property_name, value, unit)`: Adjusts component attributes (resistance, color, name).

### 4. Wiring & Connections
* `tinkercad_connect_verified_netlist(connections, circuit_id, clear_existing, verify_each, verify_persistence)`: Verified, instance-aware netlist wiring workflow. Resolves exact instance IDs (e.g. `_269`, `_291`), normalizes pin aliases (`vcc`/`power`/`pos` -> power, `gnd`/`ground`/`neg` -> ground, `out`/`signal` -> signal, `anode`/`cathode`), scopes terminal resolution strictly to each component's SVG element, rejects power-to-ground shorts (`short_circuit=true`), same-component self-wires, direct motor connections, duplicate pairs, and suspicious mappings (`stale_terminal_mapping=true`). Wires one connection at a time with instant model verification and confirms all connections survive post-reload cloud persistence.
* `tinkercad_resolve_terminal(component, pin, component_name)`: Resolves a component terminal's exact SVG identity and canvas screen coordinates.
* `tinkercad_connect_component_pins(source_component, source_pin, target_component, target_pin, color, allow_unsafe_direct)`: Semantically connects two named component pins, enforces electrical safety by rejecting direct motor connections to MCU I/O pins (>40 mA violation), resolves coordinates via SVG transforms with fallback to internal connection API, and automatically routes via Breadboard when ground pins are exhausted.
* `tinkercad_connect_and_verify_wires(connections, circuit_id_or_url, clear_existing_wires, code, expected_wire_count, verify_after_each, reload_after_each, verify_persistence, run_schematic_erc)`: Robust multi-wire orchestration tool. Accepts connections as dicts or list-of-lists (e.g. `[["Arduino Uno R3", "D2", "Ultrasonic Distance Sensor (4-pin)", "trig", "blue"], ...]`). Dynamically discovers terminals with `getScreenCTM`, skips duplicate existing connections, optionally clears messy wiring (`clear_existing_wires=True`), optionally uploads and verifies sketch code (`code="..."`), allocates distinct Arduino GND pins, settles autosave, verifies post-reload persistence, checks expected wire counts, and executes Schematic Electrical Rule Checks (ERC) to prevent shorts and floating pins.
* `tinkercad_delete_wire_between(source_component, source_pin, target_component, target_pin)`: Finds and deletes a specific wire connecting two component pins semantically without needing canvas coordinates. Strictly removes wire via internal model and UI dispatch without blind `Delete` keypresses, preventing accidental component deletion.
* `tinkercad_clear_circuit_wires(component_name, verify_persistence)`: Clears all wires in the circuit canvas (or all wires attached to a specific component) to cleanly reset messy wiring in a single call. Uses native Playwright `path.wire-segment` UI element deletion and internal model cleanup with autosave debounce wait (4.5s) to guarantee cloud persistence across page reloads.
* `tinkercad_check_electrical_safety()`: Validates electrical ratings across all circuit wires, detecting ATmega328P 40 mA pin limit violations, inductive load isolation, missing motor drivers, and missing external battery supplies.
* `tinkercad_route_pin_via_breadboard(component, pin, rail, color, microcontroller_name)`: Routes a component pin to a Breadboard power or ground rail when microcontroller pins are full or conflicted, ensuring a common rail linked to the microcontroller.
* `tinkercad_connect_pins(from_x, from_y, to_x, to_y, color, wire_type)`: (Low-level) Connects two terminals with a colored wire by screen coordinates and verifies wire creation.
* `tinkercad_move_connection(source_component, source_pin, old_target_component, old_target_pin, new_target_component, new_target_pin, color)`: Moves an existing wire connection from an old target pin to a new target pin and verifies both removal and creation.
* `tinkercad_delete_wire(x, y)`: Clicks on a wire and deletes it with strict safety guards: verifies `elementFromPoint(x, y)` is a wire segment, aborts with `destructive_action_prevented` if targeting a component (e.g. Breadboard, Servo, PIR), and clears focus if a component is accidentally selected.

### 5. Arduino Code Editor
* `tinkercad_get_code()`: Reads the sketch source code from the live CodeMirror editor (prioritizing CodeMirror over hidden textareas).
* `tinkercad_set_code(code, ensure_text_mode, verify_persistence)`: Switches to Text mode, updates the live CodeMirror model, and verifies persistence across project reload.

### 6. Simulation Control
* `tinkercad_start_simulation(wait_seconds)`: Starts the circuit simulation and waits for active state.
* `tinkercad_stop_simulation()`: Stops the simulation.
* `tinkercad_get_simulation_status()`: Checks whether simulation is running, elapsed time, and errors.

### 7. Serial Monitor
* `tinkercad_open_serial_monitor()`: Opens the Serial Monitor panel.
* `tinkercad_read_serial_monitor(last_n_lines)`: Reads output lines from the Serial Monitor.
* `tinkercad_send_serial_monitor(text)`: Transmits input commands to the Arduino.
* `tinkercad_clear_serial_monitor()`: Clears the Serial Monitor log.

### 8. Composite Workflows
* `tinkercad_build_circuit(title, components_json, wires_json, arduino_code, run_simulation)`: High-level tool to build, wire, program, and simulate a circuit in a single operation.
* `tinkercad_change_pin_and_update_code(component, component_pin, old_microcontroller_pin, new_microcontroller_pin, code_symbol, microcontroller_name, wire_color, verify_persistence)`: Atomically moves a physical wire connection to a new microcontroller pin and updates the pin number in the Arduino sketch with verified persistence.
* `tinkercad_add_servo_with_distance_control(distance_threshold, angle_when_near, angle_when_far, signal_pin)`: Adds a Micro Servo, connects signal, power (5V), and ground (GND) to Arduino, and injects distance-triggered positioning code with persistence verification.
* `tinkercad_build_robot_car(title, distance_threshold_cm, motor_driver_model, run_simulation)`: Builds an obstacle-avoiding 4-motor robot car using safe electrical architecture: Arduino Uno, 4 DC motors, L293D H-bridge motor driver, 4-pin HC-SR04 ultrasonic sensor, Breadboard Small with power/ground rails, 9V external motor supply, common ground, and verified persistent obstacle-stop Arduino code.

### 9. Schematic Analysis & Connection Verification (ERC)
* `tinkercad_get_schematic_svg(save_path, switch_to_schematic, return_to_view)`: Switches to schematic view, captures the complete standalone schematic SVG diagram (with component symbols, designators, and wire paths), and saves it to disk (`screenshots/schematic_<timestamp>.svg`).
* `tinkercad_inspect_schematic_connections()`: Traces the complete electrical netlist from the schematic and circuit model using Union-Find, grouping mutually connected pins into canonical Electrical Nets (`Net_1`, `Net_2`, etc.) and identifying unconnected pins.
* `tinkercad_verify_schematic_connections(strict)`: Performs Electrical Rule Checks (ERC) on the schematic connections to detect:
  * **Power-to-Ground Short Circuits:** Flags catastrophic direct shorts between power rails (5V, 3.3V, VIN, VCC) and ground rails (GND, GND1, GND2, GND3).
  * **Component Self-Shorts:** Flags 2-terminal devices (Piezo, LED, Resistor, Motor, Capacitor) where both pins are tied to the exact same net.
  * **Floating Power or Ground:** Flags active sensors and ICs (HC-SR04 Ultrasonic VCC/GND, PIR, TMP36, Servo, Motor Driver, LCD) left unconnected.
  * **Pin Connection Conflicts:** Flags passive devices (such as Piezo (+)) improperly bridged to 3 or more conflicting pins.
  * Provides actionable step-by-step fix recommendations for every violation.

---

## 💡 Example AI Prompts

> **"Check my Tinkercad login status, and list all my circuit designs."**

> **"Create a new circuit named 'Arduino Blink Test', add an Arduino Uno R3 and a Red LED, wire D13 to the LED anode and GND to cathode, upload the blink sketch, and start the simulation."**

> **"Read the serial monitor output from my running circuit and report the temperature readings."**

---

## 📄 License
MIT License.

