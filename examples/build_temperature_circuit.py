"""Example script: Construct, wire, program, and simulate a Temperature-Controlled Servo circuit in Tinkercad.

Components:
- Arduino Uno R3 (Microcontroller)
- Temperature Sensor [TMP36] (Analog temperature sensing)
- Micro Servo (Position indicator)

Behavior:
The sketch reads analog temperature from the TMP36 on pin A0, calculates degrees Celsius,
and sweeps the Micro Servo on PWM pin D9 when high temperature is detected.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("SystemRoot", r"C:\Windows")
os.environ.setdefault("WINDIR", r"C:\Windows")
os.environ.setdefault("TINKERCAD_HEADLESS", "false")

from src.browser.browser_manager import BrowserManager
from src.services.circuits_service import CircuitsService
from src.services.components_service import ComponentsService
from src.services.wiring_service import WiringService
from src.services.code_service import CodeService
from src.services.simulation_service import SimulationService


ARDUINO_CODE = """// Temperature Sensor Monitor with Servo Indicator
#include <Servo.h>

const int tempPin = A0;
const int servoPin = 9;
Servo tempServo;

void setup()
{
  Serial.begin(9600);
  tempServo.attach(servoPin);
  tempServo.write(0);
  Serial.println("Temperature System Online");
}

void loop()
{
  int raw = analogRead(tempPin);
  float voltage = raw * (5.0 / 1024.0);
  float tempC = (voltage - 0.5) * 100.0;
  int angle = map(constrain((int)tempC, 0, 100), 0, 100, 0, 180);
  tempServo.write(angle);

  Serial.print("Temp: ");
  Serial.print(tempC);
  Serial.print(" C | Angle: ");
  Serial.println(angle);
  delay(1000);
}
"""


async def main() -> None:
    print("--- Starting Temperature-Controlled Servo Circuit Builder ---")
    bm = BrowserManager.get_instance()
    bm.current_headless = False

    circuits_svc = CircuitsService(bm)
    comps_svc = ComponentsService(bm)
    wiring_svc = WiringService(bm)
    code_svc = CodeService(bm)
    sim_svc = SimulationService(bm)

    circuit_id = sys.argv[1] if len(sys.argv) > 1 else None

    # 1. Open existing circuit or create a new one
    if circuit_id:
        print(f"Opening existing circuit '{circuit_id}'...")
        res = await circuits_svc.open_circuit(circuit_id)
        if not res.get("success"):
            print(f"Failed to open circuit: {res.get('message')}")
            return
    else:
        print("Creating new circuit 'Temperature Controlled Servo'...")
        res = await circuits_svc.create_circuit("Temperature Controlled Servo")
        if not res.get("success"):
            print(f"Failed to create circuit: {res.get('message')}")
            return
        circuit_id = res.get("circuit_id")

    page = await bm.get_page()
    await page.wait_for_timeout(3000)

    # 2. Inspect existing components
    info = await circuits_svc.inspect_circuit()
    existing_comps = info.get("components", [])
    print(f"Detected {len(existing_comps)} existing components.")

    arduino_id = None
    temp_id = None
    servo_id = None

    for c in existing_comps:
        t = c.get("type", "").lower()
        if "arduino" in t:
            arduino_id = c.get("instance_id")
        elif "temperature" in t or "tmp36" in t:
            temp_id = c.get("instance_id")
        elif "servo" in t:
            servo_id = c.get("instance_id")

    # 3. Add missing components
    if not arduino_id:
        print("Placing Arduino Uno R3...")
        add_res = await comps_svc.add_component(component_name="Arduino Uno R3", x=200, y=200)
        arduino_id = add_res.get("instance_id")
        print(f"Arduino placed: {arduino_id}")

    if not temp_id:
        print("Placing TMP36 Temperature Sensor...")
        add_res = await comps_svc.add_component(component_name="Temperature Sensor [TMP36]", x=500, y=150)
        temp_id = add_res.get("instance_id")
        print(f"Temperature sensor placed: {temp_id}")

    if not servo_id:
        print("Placing Micro Servo...")
        add_res = await comps_svc.add_component(component_name="Micro Servo", x=500, y=350)
        servo_id = add_res.get("instance_id")
        print(f"Micro Servo placed: {servo_id}")

    # 4. Wire the components
    print("Wiring components...")
    connections = [
        # TMP36 -> Arduino
        (temp_id, "vout", arduino_id, "A0", "green"),
        (temp_id, "power", arduino_id, "5V", "red"),
        (temp_id, "ground", arduino_id, "GND2", "black"),
        # Servo -> Arduino
        (servo_id, "Signal", arduino_id, "D9", "orange"),
        (servo_id, "Power", arduino_id, "5V", "red"),
        (servo_id, "Ground", arduino_id, "GND1", "black"),
    ]

    for src_id, src_pin, tgt_id, tgt_pin, color in connections:
        if src_id and tgt_id:
            w_res = await wiring_svc.connect_component_pins(
                source_component=src_id,
                source_pin=src_pin,
                target_component=tgt_id,
                target_pin=tgt_pin,
                color=color,
            )
            print(f"Wire {src_pin} -> {tgt_pin}: {'OK' if w_res.get('success') else 'Failed'}")

    # 5. Inject sketch code with cloud persistence verification
    print("Injecting Arduino code and verifying cloud persistence...")
    code_res = await code_svc.set_code(ARDUINO_CODE, ensure_text_mode=True, verify_persistence=True)
    print("Code injection status:", code_res.get("message"))

    # 6. Run simulation
    print("Starting simulation...")
    sim_res = await sim_svc.start_simulation()
    print("Simulation status:", sim_res.get("message"))
    await page.wait_for_timeout(3000)

    # 7. Capture screenshot
    screenshots_dir = PROJECT_ROOT / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    shot_path = screenshots_dir / "temperature_circuit_demo.png"
    await page.screenshot(path=str(shot_path))
    print(f"Screenshot saved to {shot_path}")

    # 8. Stop simulation
    await sim_svc.stop_simulation()
    print("--- Circuit Setup & Verification Complete ---")


if __name__ == "__main__":
    asyncio.run(main())
