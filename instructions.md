# Tinkercad MCP Server — Agent Instructions & Best Practices

This guide provides everything an AI agent needs to build, wire, program, and simulate electronic circuits in Autodesk Tinkercad Circuits without ever needing to inspect Python source files.

---

## 1. Quick Start: High-Level Circuit Construction (Recommended)

The fastest and most reliable way to construct a circuit is `tinkercad_build_circuit`. It creates or opens a circuit, places components, connects all wires, injects the Arduino C++ sketch, and optionally starts the simulation in a single atomic call.

### Recommended Call Structure:

```json
{
  "title": "Temperature Controlled Servo",
  "circuit_id": "optional_existing_circuit_id",
  "components": [
    {"name": "Arduino Uno R3", "x": 300, "y": 350},
    {"name": "Temperature Sensor", "x": 650, "y": 250},
    {"name": "Micro Servo", "x": 650, "y": 480}
  ],
  "wires": [
    {"source_component": "Arduino Uno R3", "source_pin": "5V", "target_component": "Temperature Sensor", "target_pin": "power", "color": "red"},
    {"source_component": "Arduino Uno R3", "source_pin": "GND_1", "target_component": "Temperature Sensor", "target_pin": "ground", "color": "black"},
    {"source_component": "Arduino Uno R3", "source_pin": "A0", "target_component": "Temperature Sensor", "target_pin": "vout", "color": "blue"},
    {"source_component": "Arduino Uno R3", "source_pin": "5V", "target_component": "Micro Servo", "target_pin": "power", "color": "red"},
    {"source_component": "Arduino Uno R3", "source_pin": "GND_2", "target_component": "Micro Servo", "target_pin": "ground", "color": "black"},
    {"source_component": "Arduino Uno R3", "source_pin": "D9", "target_component": "Micro Servo", "target_pin": "signal", "color": "orange"}
  ],
  "arduino_code": "#include <Servo.h>\n\nServo tempServo;\nconst int tempPin = A0;\nconst float thresholdC = 30.0;\n\nvoid setup() {\n  Serial.begin(9600);\n  tempServo.attach(9);\n  tempServo.write(0);\n}\n\nvoid loop() {\n  int raw = analogRead(tempPin);\n  float voltage = raw * (5.0 / 1024.0);\n  float tempC = (voltage - 0.5) * 100.0;\n  Serial.print(\"Temp: \"); Serial.print(tempC); Serial.println(\" C\");\n  if (tempC > thresholdC) {\n    tempServo.write(150);\n  } else {\n    tempServo.write(0);\n  }\n  delay(500);\n}",
  "run_simulation": true
}
```

> **Note on Arguments**: Both `components` and `components_json` are supported. Both `wires` and `wires_json` are supported. You can pass raw JSON strings or direct arrays of objects.

---

## 2. Granular Step-by-Step Workflow

If you prefer building incrementally:

1. **Check Session**: `tinkercad_auth_status()`
2. **Open / Create Circuit**:
   - Create new: `tinkercad_create_circuit(name="amazing")`
   - Open existing: `tinkercad_open_circuit(circuit_id="2zkRyaDfhkA")`
3. **Place Components**:
   - `tinkercad_add_component(component_name="Arduino Uno R3", x=300, y=350)`
   - `tinkercad_add_component(component_name="Temperature Sensor", x=650, y=250)`
   - `tinkercad_add_component(component_name="Micro Servo", x=650, y=480)`
4. **Wire Components Semantically**:
   - `tinkercad_connect_component_pins(source_component="Arduino Uno R3", source_pin="5V", target_component="Temperature Sensor", target_pin="power", color="red")`
   - `tinkercad_connect_component_pins(source_component="Arduino Uno R3", source_pin="GND_1", target_component="Temperature Sensor", target_pin="ground", color="black")`
   - `tinkercad_connect_component_pins(source_component="Arduino Uno R3", source_pin="A0", target_component="Temperature Sensor", target_pin="vout", color="blue")`
   - `tinkercad_connect_component_pins(source_component="Arduino Uno R3", source_pin="D9", target_component="Micro Servo", target_pin="signal", color="orange")`
5. **Inject Sketch Code**:
   - `tinkercad_set_code(code="...")` (automatically switches to Text mode and updates CodeMirror)
6. **Simulate & Inspect**:
   - `tinkercad_start_simulation()`
   - `tinkercad_take_screenshot()`
   - `tinkercad_read_serial_monitor()`
   - `tinkercad_stop_simulation()`

---

## 3. Component & Pinout Reference

Use these exact canonical names and terminal pin names:

### Microcontrollers
* **Arduino Uno R3** (`arduino_uno`):
  * **Power Pins**: `5V`, `3.3V`, `VIN`, `IOREF`
  * **Ground Pins**: `GND_1` (digital header), `GND_2` (power header), `GND_3` (power header), or `GND`
  * **Analog Inputs**: `A0`, `A1`, `A2`, `A3`, `A4`, `A5`
  * **Digital / PWM**: `D0` to `D13` (PWM: `D3`, `D5`, `D6`, `D9`, `D10`, `D11`)

### Sensors
* **Temperature Sensor (TMP36)** (`tmp36`):
  * Pins: `power` (+2.7V to +5.5V), `vout` (Analog Output Voltage), `ground` (GND)
  * Voltage-to-Temperature: `tempC = (voltage - 0.5) * 100.0`
* **Ultrasonic Distance Sensor (4-pin HC-SR04)** (`ultrasonic_sensor_4pin`):
  * Pins: `pos` (+5V/VCC), `trig` (Trigger), `echo` (Echo), `neg` (GND)
* **Photoresistor (LDR)** (`photoresistor`):
  * Pins: `terminal_1`, `terminal_2`
* **PIR Sensor** (`pir_sensor`):
  * Pins: `power` (+5V), `signal` (Output Signal), `ground` (GND)

### Actuators & Outputs
* **Micro Servo** (`servo`):
  * Pins: `signal` (PWM Signal / Orange), `power` (+5V / Red), `ground` (GND / Brown)
* **DC Motor** (`dc_motor`):
  * Pins: `terminal_1`, `terminal_2`
* **Piezo (Buzzer)** (`piezo`):
  * Pins: `positive` (+), `negative` (-)
* **LED** (`led`):
  * Pins: `anode` (+ longer leg), `cathode` (- shorter leg)
* **RGB LED** (`rgb_led`):
  * Pins: `red`, `cathode` (Common GND), `blue`, `green`

### General & ICs
* **Breadboard Small** (`breadboard_small`):
  * Top Power Rails: `power_pos_top` (+), `power_neg_top` (-)
  * Bottom Power Rails: `power_pos_bot` (+), `power_neg_bot` (-)
* **Resistor** (`resistor`):
  * Pins: `terminal_1`, `terminal_2`
  * Properties: `resistance="220"`, `unit="Ω"` (or `"1"`, `"kΩ"`)
* **H-bridge Motor Driver (L293D)** (`hbridge_motor_driver`):
  * Pins: `Enable1`, `Input1`, `Output1`, `GND`, `Output2`, `Input2`, `Vs`, `Enable2`, `Input3`, `Output3`, `GND2`, `Output4`, `Input4`, `Vss`

---

## 4. Key Rules to Avoid Bugs

1. **Workspace View**: Always build in `Circuits` (breadboard) view. If you call `tinkercad_get_schematic_svg()`, it will automatically return to `Circuits` view.
2. **Wire Colors**: Standard conventions:
   * Power (+5V): `red`
   * Ground (GND): `black`
   * Analog Signals: `blue` or `yellow`
   * PWM / Digital: `green` or `orange`
3. **TMP36 Conversion Formula**:
   ```cpp
   float voltage = analogRead(A0) * (5.0 / 1024.0);
   float tempC = (voltage - 0.5) * 100.0;
   ```
4. **Micro Servo Angle Limits**:
   Micro servos operate between `0` and `180` degrees. If the user asks for 150 degrees on high temperature:
   ```cpp
   if (tempC > 30.0) {
     myServo.write(150);
   } else {
     myServo.write(0);
   }
   ```
5. **Code Panel Pointer Interception**: The tools automatically manage and dismiss any blocking drawers or code panels before placing components.
