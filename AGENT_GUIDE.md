# Tinkercad MCP Server — Complete Agent Guide

This documentation guides AI agents on how to interact with Autodesk Tinkercad Circuits through the Model Context Protocol (MCP) server.

## Overview of Available Tools

| Tool | Purpose | Key Parameters |
|---|---|---|
| `tinkercad_build_circuit` | **Primary 1-Call Builder** for complete projects | `title`, `circuit_id`, `components`, `wires`, `arduino_code`, `run_simulation` |
| `tinkercad_auth_status` | Check authentication & login status | None |
| `tinkercad_login` | Log in to Autodesk Tinkercad | `interactive=True` |
| `tinkercad_create_circuit` | Create a new blank circuit design | `name` |
| `tinkercad_open_circuit` | Open an existing circuit by ID | `circuit_id` |
| `tinkercad_inspect_circuit` | Semantic inspection of placed components, pins & wires | None |
| `tinkercad_add_component` | Place a single component onto canvas | `component_name`, `x`, `y` |
| `tinkercad_connect_component_pins` | Wire two components semantically | `source_component`, `source_pin`, `target_component`, `target_pin`, `color` |
| `tinkercad_set_code` | Inject Arduino sketch C++ code | `code`, `ensure_text_mode=True` |
| `tinkercad_get_code` | Read currently active code from editor | None |
| `tinkercad_start_simulation` | Run the simulation | None |
| `tinkercad_stop_simulation` | Stop the simulation | None |
| `tinkercad_read_serial_monitor` | Read output from Arduino Serial Monitor | None |
| `tinkercad_take_screenshot` | Capture image of the current canvas state | None |
| `tinkercad_switch_workspace_view`| Switch view ('circuits', 'schematic', 'components') | `view` |
| `tinkercad_get_schematic_svg` | Capture schematic diagram as vector SVG | `save_path`, `return_to_view='circuits'` |

---

## 1-Call Build Circuit Example: Temperature Controlled Servo

```json
{
  "title": "amazing",
  "circuit_id": "2zkRyaDfhkA",
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
  "arduino_code": "#include <Servo.h>\n\nServo tempServo;\nconst int tempPin = A0;\nconst float highTempC = 30.0;\n\nvoid setup() {\n  Serial.begin(9600);\n  tempServo.attach(9);\n  tempServo.write(0);\n}\n\nvoid loop() {\n  int val = analogRead(tempPin);\n  float voltage = val * (5.0 / 1024.0);\n  float tempC = (voltage - 0.5) * 100.0;\n  Serial.print(\"Temperature: \"); Serial.print(tempC); Serial.println(\" C\");\n  if (tempC > highTempC) {\n    tempServo.write(150);\n  } else {\n    tempServo.write(0);\n  }\n  delay(500);\n}",
  "run_simulation": true
}
```

---

## Canonical Component and Pin Reference

### Arduino Uno R3 (`arduino_uno`)
- **Power**: `5V`, `3.3V`, `VIN`, `IOREF`
- **Ground**: `GND_1` (digital top), `GND_2` (power bottom), `GND_3` (power bottom)
- **Analog**: `A0`, `A1`, `A2`, `A3`, `A4`, `A5`
- **Digital**: `D0` through `D13` (PWM pins: `D3`, `D5`, `D6`, `D9`, `D10`, `D11`)

### Temperature Sensor TMP36 (`tmp36`)
- `power`: Connect to Arduino `5V`
- `vout`: Connect to Arduino `A0`
- `ground`: Connect to Arduino `GND_1` or `GND_2`

### Micro Servo (`servo`)
- `signal`: Connect to PWM pin (e.g. `D9`)
- `power`: Connect to Arduino `5V`
- `ground`: Connect to Arduino `GND_1` or `GND_2`

### 4-pin Ultrasonic Sensor HC-SR04 (`ultrasonic_sensor_4pin`)
- `pos`: Connect to `5V`
- `trig`: Connect to digital pin (e.g. `D7`)
- `echo`: Connect to digital pin (e.g. `D6`)
- `neg`: Connect to `GND`
