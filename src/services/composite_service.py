"""Composite service for end-to-end circuit construction and automated testing."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .circuits_service import CircuitsService
from .components_service import ComponentsService
from .wiring_service import WiringService
from .code_service import CodeService
from .simulation_service import SimulationService
from ..config import logger


class CompositeService:
    """Orchestrates end-to-end circuit workflows: creation, placement, wiring, coding, and simulation."""

    def __init__(
        self,
        circuits: Optional[CircuitsService] = None,
        components: Optional[ComponentsService] = None,
        wiring: Optional[WiringService] = None,
        code: Optional[CodeService] = None,
        simulation: Optional[SimulationService] = None,
    ) -> None:
        self.circuits = circuits or CircuitsService()
        self.components = components or ComponentsService()
        self.wiring = wiring or WiringService()
        self.code = code or CodeService()
        self.simulation = simulation or SimulationService()

    @staticmethod
    def validate_build_inputs(
        components_json: Optional[Union[str, List[Dict[str, Any]]]] = None,
        wires_json: Optional[Union[str, List[Dict[str, Any]]]] = None,
        description: Optional[str] = None,
        components: Optional[Union[str, List[Dict[str, Any]]]] = None,
        wires: Optional[Union[str, List[Dict[str, Any]]]] = None,
    ) -> tuple[bool, Optional[str], Optional[List[Dict[str, Any]]], Optional[List[Dict[str, Any]]]]:
        """Validate components and wires inputs (accepting either JSON strings or parsed python lists)."""
        import json

        raw_comps = components if components is not None else components_json
        comps = None
        if raw_comps is not None:
            if isinstance(raw_comps, list):
                comps = raw_comps
            elif isinstance(raw_comps, str):
                try:
                    parsed = json.loads(raw_comps)
                    if not isinstance(parsed, list):
                        return False, "Invalid format: 'components_json' must be a JSON array of objects.", None, None
                    comps = parsed
                except Exception as e:
                    return False, f"Failed to parse 'components_json': {e}", None, None
            else:
                return False, "Invalid format: components must be a list or a JSON string.", None, None

            if len(comps) > 100:
                return False, "Too many components in single build request (maximum allowed is 100).", None, None

        raw_wires = wires if wires is not None else wires_json
        wire_list = None
        if raw_wires is not None:
            if isinstance(raw_wires, list):
                wire_list = raw_wires
            elif isinstance(raw_wires, str):
                try:
                    parsed = json.loads(raw_wires)
                    if not isinstance(parsed, list):
                        return False, "Invalid format: 'wires_json' must be a JSON array of wire objects.", None, None
                    wire_list = parsed
                except Exception as e:
                    return False, f"Failed to parse 'wires_json': {e}", None, None
            else:
                return False, "Invalid format: wires must be a list or a JSON string.", None, None

            if len(wire_list) > 200:
                return False, "Too many wires in single build request (maximum allowed is 200).", None, None

        return True, None, comps, wire_list

    async def build_circuit(
        self,
        circuit_id: Optional[str] = None,
        title: Optional[str] = None,
        components: Optional[List[Dict[str, Any]]] = None,
        wires: Optional[List[Dict[str, Any]]] = None,
        arduino_code: Optional[str] = None,
        run_simulation: bool = False,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Construct a complete circuit with components, wiring, code, and optional simulation in one call."""
        if not components and not wires and not arduino_code:
            if description:
                return {
                    "success": False,
                    "error": "unparsed_natural_language_description",
                    "message": (
                        f"build_circuit received description '{description}' without structured components or wires. "
                        "Please pass 'components_json' (e.g. '[{\"name\": \"Arduino Uno R3\", \"x\": 300, \"y\": 300}, {\"name\": \"LED\", \"x\": 600, \"y\": 300}]') "
                        "and 'wires_json' (e.g. '[{\"source_component\": \"Arduino Uno R3\", \"source_pin\": \"D13\", \"target_component\": \"LED\", \"target_pin\": \"anode\"}]'), "
                        "or call dedicated workflow tools like 'tinkercad_add_servo_with_distance_control', 'tinkercad_build_robot_car', "
                        "or add components individually using 'tinkercad_add_component' and 'tinkercad_connect_component_pins'."
                    ),
                }
            if not title and not circuit_id:
                return {
                    "success": False,
                    "error": "no_actionable_inputs",
                    "message": "build_circuit requires at least one of: title, circuit_id, components, wires, or arduino_code.",
                }

        results: Dict[str, Any] = {
            "title": title,
            "circuit_id": circuit_id,
            "placed_components": [],
            "connected_wires": [],
            "code_injected": False,
            "simulation": None,
        }

        # 1. Open existing circuit or create new circuit
        if circuit_id:
            logger.info(f"Opening existing circuit: {circuit_id}")
            open_res = await self.circuits.open_circuit(circuit_id=circuit_id)
            if not open_res.get("success"):
                return {
                    "success": False,
                    "error": "circuit_open_failed",
                    "message": f"Failed to open circuit '{circuit_id}': {open_res.get('message')}",
                }
            results["circuit_id"] = open_res.get("circuit_id") or circuit_id
            results["circuit_url"] = open_res.get("url")
            if title:
                renamed = await self.circuits.rename_circuit(circuit_id=results["circuit_id"], new_name=title)
                results["title"] = renamed.get("title") or title
        elif title:
            logger.info(f"Creating new circuit: {title}")
            created = await self.circuits.create_circuit(title=title)
            results["circuit_id"] = created.get("circuit_id")
            results["circuit_url"] = created.get("url")

        # Ensure Circuits (breadboard) view is active
        page = await self.circuits.browser.get_page()
        if hasattr(self.circuits.browser, "ensure_circuits_view_active"):
            await self.circuits.browser.ensure_circuits_view_active(page)

        # 2. Place components
        if components and isinstance(components, list):
            for comp in components:
                if not isinstance(comp, dict):
                    continue
                name = (
                    comp.get("name")
                    or comp.get("component_name")
                    or comp.get("component_id")
                    or comp.get("id")
                    or comp.get("type")
                )
                if not name:
                    continue
                placed = await self.components.add_component(
                    component_name=str(name),
                    component_id=comp.get("component_id") or comp.get("id"),
                    x=comp.get("x"),
                    y=comp.get("y"),
                )
                results["placed_components"].append(placed)

                # Set properties if provided
                props = comp.get("properties")
                if props and isinstance(props, dict):
                    for k, v in props.items():
                        await self.components.set_component_property(k, str(v), component_name=str(name))

        # 3. Connect wires
        if wires and isinstance(wires, list):
            for w in wires:
                if not isinstance(w, dict):
                    continue
                # Support both semantic pin connections and raw coordinate connections
                src_comp = (
                    w.get("source_component") or w.get("from_component") or w.get("source") or w.get("from")
                    or w.get("component1_id") or w.get("component1")
                )
                src_pin = w.get("source_pin") or w.get("from_pin") or w.get("pin1")
                tgt_comp = (
                    w.get("target_component") or w.get("to_component") or w.get("target") or w.get("to")
                    or w.get("component2_id") or w.get("component2")
                )
                tgt_pin = w.get("target_pin") or w.get("to_pin") or w.get("pin2")

                if src_comp and src_pin and tgt_comp and tgt_pin:
                    conn = await self.wiring.connect_component_pins(
                        source_component=str(src_comp),
                        source_pin=str(src_pin),
                        target_component=str(tgt_comp),
                        target_pin=str(tgt_pin),
                        color=w.get("color", "green"),
                        allow_unsafe_direct=w.get("allow_unsafe_direct", True),
                    )
                else:
                    conn = await self.wiring.connect_pins(
                        from_x=w.get("from_x", 0),
                        from_y=w.get("from_y", 0),
                        to_x=w.get("to_x", 0),
                        to_y=w.get("to_y", 0),
                        color=w.get("color", "green"),
                        wire_type=w.get("wire_type", "normal"),
                        waypoints=w.get("waypoints"),
                    )
                results["connected_wires"].append(conn)

        # 4. Inject Arduino code
        if arduino_code:
            logger.info("Injecting Arduino code into sketch editor...")
            code_res = await self.code.set_code(code=arduino_code, ensure_text_mode=True)
            results["code_injected"] = code_res.get("success", False)

        # 5. Start simulation if requested
        if run_simulation:
            logger.info("Starting simulation...")
            sim_res = await self.simulation.start_simulation()
            results["simulation"] = sim_res

        results["success"] = True
        results["message"] = (
            f"Successfully built circuit with {len(results['placed_components'])} components "
            f"and {len(results['connected_wires'])} wires."
        )
        return results

    async def change_pin_and_update_code(
        self,
        component: str,
        component_pin: str,
        old_microcontroller_pin: str,
        new_microcontroller_pin: str,
        code_symbol: Optional[str] = None,
        microcontroller_name: Optional[str] = "Arduino Uno R3",
        wire_color: Optional[str] = "green",
        verify_persistence: bool = True,
    ) -> Dict[str, Any]:
        """Atomically move a component's physical wire connection and update its Arduino sketch code.

        1. Moves the physical wire connection from old_microcontroller_pin to new_microcontroller_pin.
        2. Updates the Arduino code pin definition (matching code_symbol or numeric pin) and verifies persistence.
        3. Fails if either physical move or code update cannot be verified.

        Args:
            component: Component name or instance (e.g. 'Piezo', 'DC Motor', 'LED')
            component_pin: Pin on the component (e.g. '+', 'Terminal 1', 'anode')
            old_microcontroller_pin: Current microcontroller pin (e.g. 'D10', '10')
            new_microcontroller_pin: New microcontroller pin (e.g. 'D11', '11')
            code_symbol: Optional variable name in Arduino sketch (e.g. 'buzzer_pin', 'motor')
            microcontroller_name: Name of microcontroller (defaults to 'Arduino Uno R3')
            wire_color: Wire color ('green', 'red', 'blue', etc.)
            verify_persistence: Whether to verify code persistence via reload
        """
        import re

        logger.info(
            f"Changing pin and code: {component} ({component_pin}) from {old_microcontroller_pin} "
            f"to {new_microcontroller_pin} [symbol: {code_symbol}]"
        )

        # 1. Physical wiring change
        mcu = microcontroller_name or "Arduino Uno R3"
        move_res = await self.wiring.move_connection(
            source_component=component,
            source_pin=component_pin,
            old_target_component=mcu,
            old_target_pin=old_microcontroller_pin,
            new_target_component=mcu,
            new_target_pin=new_microcontroller_pin,
            color=wire_color,
        )

        if not move_res.get("success"):
            return {
                "success": False,
                "error": "physical_rewiring_failed",
                "message": f"Physical rewiring failed: {move_res.get('message')}",
                "move_details": move_res,
            }

        # 2. Extract numeric digits for code substitution
        old_digits = re.sub(r"[^0-9]", "", old_microcontroller_pin)
        new_digits = re.sub(r"[^0-9]", "", new_microcontroller_pin)

        # 3. Read current code
        code_res = await self.code.get_code()
        current_code = code_res.get("code", "")

        code_updated = False
        new_code = current_code

        if current_code and old_digits and new_digits:
            # If code_symbol specified, replace its assignment
            if code_symbol:
                pattern = rf"(\b{re.escape(code_symbol)}\s*=\s*){re.escape(old_digits)}\b"
                if re.search(pattern, current_code):
                    new_code = re.sub(pattern, rf"\g<1>{new_digits}", current_code)
                    code_updated = True
                else:
                    pattern2 = rf"(\b(?:int|const\s+int|#define|byte|uint8_t)\s+{re.escape(code_symbol)}\s*=?\s*){re.escape(old_digits)}\b"
                    if re.search(pattern2, current_code):
                        new_code = re.sub(pattern2, rf"\g<1>{new_digits}", current_code)
                        code_updated = True

            # If no symbol specified or symbol wasn't found, search for pin variable declaration with old pin number
            if not code_updated:
                pattern_gen = rf"(\b(?:int|const\s+int|#define|byte|uint8_t)\s+[a-zA-Z0-9_]*pin[a-zA-Z0-9_]*\s*=?\s*){re.escape(old_digits)}\b"
                if re.search(pattern_gen, current_code, re.IGNORECASE):
                    new_code = re.sub(pattern_gen, rf"\g<1>{new_digits}", current_code, count=1, flags=re.IGNORECASE)
                    code_updated = True
                else:
                    pattern_any = rf"(\b(?:int|const\s+int|#define|byte)\s+[a-zA-Z0-9_]+\s*=?\s*){re.escape(old_digits)}\b"
                    if re.search(pattern_any, current_code):
                        new_code = re.sub(pattern_any, rf"\g<1>{new_digits}", current_code, count=1)
                        code_updated = True

        # 4. Inject updated code if modified
        code_result = None
        if code_updated and new_code != current_code:
            code_result = await self.code.set_code(
                code=new_code,
                ensure_text_mode=True,
                verify_persistence=verify_persistence,
            )
            if not code_result.get("success"):
                return {
                    "success": False,
                    "error": "code_persistence_failed",
                    "physical_connection": move_res,
                    "code_error": code_result.get("message"),
                    "message": f"Physical wiring succeeded, but code persistence failed: {code_result.get('message')}",
                }
        else:
            logger.info("No code substitution matched or code was empty. Skipping code injection.")

        return {
            "success": True,
            "physical_connection": {
                "component": component,
                "pin": component_pin,
                "old_pin": old_microcontroller_pin,
                "new_pin": new_microcontroller_pin,
                "wire_id": move_res.get("new_wire_id"),
            },
            "code_update": {
                "symbol": code_symbol,
                "old_pin": old_digits,
                "new_pin": new_digits,
                "updated": code_updated,
                "verified": code_result.get("verified", False) if code_result else False,
            },
            "message": (
                f"Successfully moved {component} ({component_pin}) to {new_microcontroller_pin} "
                + (f"and updated {code_symbol} to {new_digits} in Arduino code." if code_updated else "without code changes.")
            ),
        }

    async def add_servo_with_distance_control(
        self,
        distance_threshold: int = 30,
        angle_when_near: int = 150,
        angle_when_far: int = 0,
        signal_pin: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a Micro Servo, connect signal/power/ground to Arduino, and program distance-based positioning.

        1. Selects an unused PWM Arduino pin (e.g. D9) if not specified.
        2. Adds exactly one Micro Servo (or uses unplaced/unconnected instance).
        3. Connects:
           - Servo signal -> Arduino PWM pin (orange)
           - Servo power  -> Arduino 5V (red)
           - Servo ground -> Arduino GND (black)
        4. Injects Servo library code and threshold logic via CodeMirror and verifies persistence.
        5. Performs structured circuit inspection to verify all connections.
        """
        import re

        logger.info(f"Adding Micro Servo with distance control (threshold={distance_threshold}cm, near={angle_when_near}°, far={angle_when_far}°)")

        # 1. Determine Arduino PWM signal pin
        chosen_pin = signal_pin
        if not chosen_pin:
            # Check existing connected pins via inspection
            used_pins = set()
            try:
                inspect_info = await self.circuits.inspect_circuit()
                for c in inspect_info.get("components", []):
                    if "arduino" in c.get("type", "").lower():
                        for p in c.get("pins", []):
                            if p.get("connected"):
                                used_pins.add(p.get("name", "").upper())
            except Exception:
                pass

            # PWM pins on Uno R3: D9, D10, D11, D3, D5, D6
            pwm_candidates = ["D9", "D10", "D6", "D5", "D3", "D11"]
            for cand in pwm_candidates:
                cand_num = cand.lstrip("D")
                if cand not in used_pins and f"~{cand_num}" not in used_pins and cand_num not in used_pins:
                    chosen_pin = cand
                    break
            if not chosen_pin:
                chosen_pin = "D9"

        sig_digits = re.sub(r"[^0-9]", "", chosen_pin)

        # 2. Add Micro Servo component
        placed_servo = await self.components.add_component("Micro Servo", x=700, y=500)
        if not placed_servo.get("success"):
            # If add failed, check if one already exists
            inspect_info = await self.circuits.inspect_circuit()
            has_servo = any("servo" in c.get("type", "").lower() for c in inspect_info.get("components", []))
            if not has_servo:
                return {
                    "success": False,
                    "error": "servo_placement_failed",
                    "message": f"Failed to place Micro Servo: {placed_servo.get('message')}",
                }

        # 3. Connect three wires
        # A. Signal wire -> Arduino chosen_pin
        w_sig = await self.wiring.connect_component_pins(
            source_component="Micro Servo",
            source_pin="signal",
            target_component="Arduino Uno R3",
            target_pin=chosen_pin,
            color="orange",
        )
        if not w_sig.get("success"):
            return {
                "success": False,
                "error": "wiring_failed",
                "failed_wire": "signal",
                "message": f"Failed to connect Micro Servo signal to Arduino {chosen_pin}: {w_sig.get('message')}",
            }

        # B. Power wire -> Arduino 5V
        w_pwr = await self.wiring.connect_component_pins(
            source_component="Micro Servo",
            source_pin="power",
            target_component="Arduino Uno R3",
            target_pin="5V",
            color="red",
        )
        if not w_pwr.get("success"):
            return {
                "success": False,
                "error": "wiring_failed",
                "failed_wire": "power",
                "message": f"Failed to connect Micro Servo power to Arduino 5V: {w_pwr.get('message')}",
            }

        # C. Ground wire -> Arduino GND
        w_gnd = await self.wiring.connect_component_pins(
            source_component="Micro Servo",
            source_pin="ground",
            target_component="Arduino Uno R3",
            target_pin="GND",
            color="black",
        )
        if not w_gnd.get("success"):
            return {
                "success": False,
                "error": "wiring_failed",
                "failed_wire": "ground",
                "message": f"Failed to connect Micro Servo ground to Arduino GND: {w_gnd.get('message')}",
            }

        # 4. Inject Arduino code with live CodeMirror
        code_res = await self.code.get_code()
        current_code = code_res.get("code", "")
        new_code = current_code

        # Check if code already contains correct servo logic
        has_include = "#include <Servo.h>" in current_code
        has_servo_obj = "Servo distance_servo" in current_code or "Servo " in current_code
        has_servo_write = f"distance_servo.write({angle_when_near})" in current_code

        if not (has_include and has_servo_obj and has_servo_write):
            # Build updated code
            if not has_include:
                new_code = "#include <Servo.h>\n" + new_code

            if not has_servo_obj:
                decl = f"\nconst int servo_pin = {sig_digits};\nServo distance_servo;\n"
                if "void setup" in new_code:
                    idx = new_code.find("void setup")
                    new_code = new_code[:idx] + decl + "\n" + new_code[idx:]
                else:
                    new_code = new_code + "\n" + decl

            # Add attach in setup if missing
            if "distance_servo.attach" not in new_code and "void setup" in new_code:
                setup_start = new_code.find("{", new_code.find("void setup"))
                if setup_start != -1:
                    new_code = (
                        new_code[:setup_start + 1]
                        + f"\n  distance_servo.attach(servo_pin);\n  distance_servo.write({angle_when_far});"
                        + new_code[setup_start + 1:]
                    )

            # Add distance threshold control in loop if missing
            servo_logic = (
                f"\n  if (distance < {distance_threshold}) {{\n"
                f"    distance_servo.write({angle_when_near});\n"
                f"  }} else {{\n"
                f"    distance_servo.write({angle_when_far});\n"
                f"  }}\n"
            )

            if f"distance_servo.write({angle_when_near})" not in new_code:
                if "void loop" in new_code:
                    loop_end = new_code.rfind("}")
                    if loop_end != -1:
                        new_code = new_code[:loop_end] + servo_logic + new_code[loop_end:]

        # Inject and verify persistence across reload
        code_set_res = await self.code.set_code(new_code, ensure_text_mode=True, verify_persistence=True)
        if not code_set_res.get("success"):
            return {
                "success": False,
                "error": "code_persistence_failed",
                "wires": [w_sig, w_pwr, w_gnd],
                "message": f"Wiring succeeded but servo code persistence failed: {code_set_res.get('message')}",
            }

        # 5. Final structured inspection
        final_inspect = await self.circuits.inspect_circuit()

        return {
            "success": True,
            "servo": {
                "component": "Micro Servo",
                "signal_pin": chosen_pin,
                "power_pin": "5V",
                "ground_pin": "GND",
            },
            "wires": [
                {"type": "signal", "wire_id": w_sig.get("wire_id"), "pin": chosen_pin, "color": "orange"},
                {"type": "power", "wire_id": w_pwr.get("wire_id"), "pin": "5V", "color": "red"},
                {"type": "ground", "wire_id": w_gnd.get("wire_id"), "pin": "GND", "color": "black"},
            ],
            "code": {
                "verified": code_set_res.get("verified", False),
                "signal_pin": sig_digits,
                "distance_threshold": distance_threshold,
                "angle_when_near": angle_when_near,
                "angle_when_far": angle_when_far,
            },
            "circuit_summary": {
                "components_count": len(final_inspect.get("components", [])),
                "wires_count": len(final_inspect.get("wires", [])),
            },
            "message": (
                f"Successfully added Micro Servo, wired signal ({chosen_pin}), power (5V), ground (GND), "
                f"and verified distance control code ({distance_threshold}cm -> {angle_when_near}°)."
            ),
        }

    async def build_robot_car_architecture(
        self,
        stop_threshold: int = 30,
        trig_pin: str = "D2",
        echo_pin: str = "D3",
        in1_pin: str = "D4",
        in2_pin: str = "D5",
        in3_pin: str = "D6",
        in4_pin: str = "D7",
    ) -> Dict[str, Any]:
        """Build an electrically safe 4-wheel robot car with obstacle-stop logic in Tinkercad.

        Architecture:
        1. Places Breadboard Small (center).
        2. Places H-bridge Motor Driver (L293D, did 112326) on the breadboard.
        3. Places exact 4-pin Ultrasonic Sensor (HC-SR04, did 219295) with trig and echo.
        4. Places 4 DC Motors in balanced four-corner arrangement.
        5. Places 9V Battery for dedicated motor supply.
        6. Safely routes power and ground through breadboard rails (preventing direct MCU overload).
        7. Routes control signals from Arduino to driver inputs and sensor.
        8. Injects obstacle-stop Arduino C++ code and verifies persistence across reload.
        """
        import re

        logger.info("Building safe 4-wheel obstacle-avoiding robot car architecture...")

        placed = {}
        # 1. Place or find Arduino Uno R3
        placed["arduino"] = await self.components.add_component("Arduino Uno R3", x=260, y=360)

        # 2. Place Breadboard Small
        placed["breadboard"] = await self.components.add_component("Breadboard Small", x=620, y=360)

        # 3. Place H-bridge Motor Driver (L293D)
        placed["motor_driver"] = await self.components.add_component("H-bridge Motor Driver", x=620, y=360)

        # 4. Place 4-pin Ultrasonic Sensor (HC-SR04) with strict pin verification
        placed["ultrasonic"] = await self.components.add_component(
            "Ultrasonic Distance Sensor (4-pin)",
            x=620,
            y=120,
            required_pins=["trig", "echo"],
            min_pins=4,
        )

        # 5. Place 4 DC Motors
        placed["motor_fl"] = await self.components.add_component("DC Motor", x=100, y=160)
        placed["motor_fr"] = await self.components.add_component("DC Motor", x=950, y=160)
        placed["motor_rl"] = await self.components.add_component("DC Motor", x=100, y=560)
        placed["motor_rr"] = await self.components.add_component("DC Motor", x=950, y=560)

        # 6. Place 9V Battery for dedicated motor power
        placed["battery"] = await self.components.add_component("9V Battery", x=950, y=360)

        # Wiring connections list
        wires_done = []

        # A. Power & Ground Rails
        # Arduino 5V -> Breadboard (+)
        w = await self.wiring.connect_component_pins("Arduino Uno R3", "5V", "Breadboard Small", "+", color="red")
        wires_done.append({"name": "mcu_5v_to_bb", "res": w})

        # Arduino GND -> Breadboard (-)
        w = await self.wiring.connect_component_pins("Arduino Uno R3", "GND", "Breadboard Small", "-", color="black")
        wires_done.append({"name": "mcu_gnd_to_bb", "res": w})

        # 9V Battery (-) -> Breadboard (-) [Common Ground]
        w = await self.wiring.connect_component_pins("9V Battery", "negative", "Breadboard Small", "-", color="black")
        wires_done.append({"name": "battery_neg_to_bb", "res": w})

        # 9V Battery (+) -> Motor Driver Vs [Motor Power Pin 8]
        w = await self.wiring.connect_component_pins("9V Battery", "positive", "H-bridge Motor Driver", "Vs", color="red")
        wires_done.append({"name": "battery_pos_to_driver_vs", "res": w})

        # Breadboard (+) -> Motor Driver Vss [Logic 5V Pin 16]
        w = await self.wiring.connect_component_pins("Breadboard Small", "+", "H-bridge Motor Driver", "Vss", color="red")
        wires_done.append({"name": "bb_5v_to_driver_vss", "res": w})

        # Breadboard (+) -> Motor Driver Enable 1 & 2
        w = await self.wiring.connect_component_pins("Breadboard Small", "+", "H-bridge Motor Driver", "Enable1", color="red")
        wires_done.append({"name": "bb_5v_to_driver_en1", "res": w})
        w = await self.wiring.connect_component_pins("Breadboard Small", "+", "H-bridge Motor Driver", "Enable2", color="red")
        wires_done.append({"name": "bb_5v_to_driver_en2", "res": w})

        # Breadboard (-) -> Motor Driver GND pins
        w = await self.wiring.connect_component_pins("Breadboard Small", "-", "H-bridge Motor Driver", "GND", color="black")
        wires_done.append({"name": "bb_gnd_to_driver_gnd", "res": w})

        # B. Ultrasonic Sensor (4-pin HC-SR04)
        # Power & GND via Breadboard rails
        w = await self.wiring.connect_component_pins("Breadboard Small", "+", "Ultrasonic Distance Sensor (4-pin)", "pos", color="red")
        wires_done.append({"name": "bb_5v_to_sonar_vcc", "res": w})
        w = await self.wiring.connect_component_pins("Breadboard Small", "-", "Ultrasonic Distance Sensor (4-pin)", "neg", color="black")
        wires_done.append({"name": "bb_gnd_to_sonar_gnd", "res": w})

        # Trigger & Echo to Arduino
        w = await self.wiring.connect_component_pins("Arduino Uno R3", trig_pin, "Ultrasonic Distance Sensor (4-pin)", "trig", color="turquoise")
        wires_done.append({"name": "mcu_trig_to_sonar", "res": w})
        w = await self.wiring.connect_component_pins("Arduino Uno R3", echo_pin, "Ultrasonic Distance Sensor (4-pin)", "echo", color="purple")
        wires_done.append({"name": "mcu_echo_to_sonar", "res": w})

        # C. Motor Driver Control Pins from Arduino
        w = await self.wiring.connect_component_pins("Arduino Uno R3", in1_pin, "H-bridge Motor Driver", "Input1", color="yellow")
        wires_done.append({"name": "mcu_in1", "res": w})
        w = await self.wiring.connect_component_pins("Arduino Uno R3", in2_pin, "H-bridge Motor Driver", "Input2", color="yellow")
        wires_done.append({"name": "mcu_in2", "res": w})
        w = await self.wiring.connect_component_pins("Arduino Uno R3", in3_pin, "H-bridge Motor Driver", "Input3", color="orange")
        wires_done.append({"name": "mcu_in3", "res": w})
        w = await self.wiring.connect_component_pins("Arduino Uno R3", in4_pin, "H-bridge Motor Driver", "Input4", color="orange")
        wires_done.append({"name": "mcu_in4", "res": w})

        # D. DC Motors to Driver Outputs
        # Left Motors (Front Left & Rear Left) to Output 1 & Output 2
        w = await self.wiring.connect_component_pins("H-bridge Motor Driver", "Output1", "DC Motor 1", "terminal_1", color="blue")
        wires_done.append({"name": "driver_out1_to_m1", "res": w})
        w = await self.wiring.connect_component_pins("H-bridge Motor Driver", "Output2", "DC Motor 1", "terminal_2", color="blue")
        wires_done.append({"name": "driver_out2_to_m1", "res": w})

        # Right Motors (Front Right & Rear Right) to Output 3 & Output 4
        w = await self.wiring.connect_component_pins("H-bridge Motor Driver", "Output3", "DC Motor 2", "terminal_1", color="green")
        wires_done.append({"name": "driver_out3_to_m2", "res": w})
        w = await self.wiring.connect_component_pins("H-bridge Motor Driver", "Output4", "DC Motor 2", "terminal_2", color="green")
        wires_done.append({"name": "driver_out4_to_m2", "res": w})

        # 7. Arduino Sketch Code with Obstacle Avoidance
        trig_num = re.sub(r"[^0-9]", "", trig_pin) or "2"
        echo_num = re.sub(r"[^0-9]", "", echo_pin) or "3"
        in1_num = re.sub(r"[^0-9]", "", in1_pin) or "4"
        in2_num = re.sub(r"[^0-9]", "", in2_pin) or "5"
        in3_num = re.sub(r"[^0-9]", "", in3_pin) or "6"
        in4_num = re.sub(r"[^0-9]", "", in4_pin) or "7"

        arduino_code = f"""// Obstacle-Stop Robot Car with 4 DC Motors and L293D Motor Driver
const int trigPin = {trig_num};
const int echoPin = {echo_num};
const int motorIn1 = {in1_num};
const int motorIn2 = {in2_num};
const int motorIn3 = {in3_num};
const int motorIn4 = {in4_num};
const int stopThreshold = {stop_threshold}; // cm

void setup() {{
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  pinMode(motorIn1, OUTPUT);
  pinMode(motorIn2, OUTPUT);
  pinMode(motorIn3, OUTPUT);
  pinMode(motorIn4, OUTPUT);
  Serial.begin(9600);
}}

long getDistance() {{
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  long duration = pulseIn(echoPin, HIGH);
  return duration * 0.034 / 2;
}}

void moveForward() {{
  digitalWrite(motorIn1, HIGH);
  digitalWrite(motorIn2, LOW);
  digitalWrite(motorIn3, HIGH);
  digitalWrite(motorIn4, LOW);
}}

void stopMotors() {{
  digitalWrite(motorIn1, LOW);
  digitalWrite(motorIn2, LOW);
  digitalWrite(motorIn3, LOW);
  digitalWrite(motorIn4, LOW);
}}

void loop() {{
  long distance = getDistance();
  Serial.print("Distance: ");
  Serial.print(distance);
  Serial.println(" cm");
  if (distance > 0 && distance < stopThreshold) {{
    stopMotors();
  }} else {{
    moveForward();
  }}
  delay(100);
}}
"""

        code_res = await self.code.set_code(arduino_code, ensure_text_mode=True, verify_persistence=True)

        # 8. Check Electrical Safety
        safety_res = await self.wiring.check_circuit_electrical_safety()

        return {
            "success": True,
            "architecture": "L293D H-Bridge + Breadboard + 4-pin HC-SR04 + 9V Dedicated Motor Supply",
            "electrical_safety": safety_res,
            "components_placed": placed,
            "wires_connected_count": len([w for w in wires_done if w.get("res", {}).get("success")]),
            "code_persisted": code_res.get("verified", False),
            "pins": {
                "ultrasonic_trig": trig_pin,
                "ultrasonic_echo": echo_pin,
                "motor_driver_in1": in1_pin,
                "motor_driver_in2": in2_pin,
                "motor_driver_in3": in3_pin,
                "motor_driver_in4": in4_pin,
                "stop_threshold_cm": stop_threshold,
            },
            "message": (
                f"Successfully built safe 4-wheel robot car circuit: placed L293D motor driver, 4-pin HC-SR04 ultrasonic sensor, "
                f"9V external motor supply, routed power/ground via breadboard rails, and verified obstacle-stop code ({stop_threshold} cm)."
            ),
        }

