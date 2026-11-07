"""Comprehensive catalog of Tinkercad Circuits components, pinouts, and default properties."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ComponentPin(BaseModel):
    name: str
    description: str = ""
    terminal_type: str = "general"  # power, ground, digital, analog, signal, terminal
    aliases: List[str] = Field(default_factory=list)


class ComponentDefinition(BaseModel):
    id: str
    name: str
    category: str
    search_keywords: List[str]
    description: str
    pins: List[ComponentPin] = Field(default_factory=list)
    default_properties: Dict[str, Any] = Field(default_factory=dict)
    did: Optional[str] = None


COMPONENTS_CATALOG: Dict[str, ComponentDefinition] = {
    "arduino_uno": ComponentDefinition(
        id="arduino_uno",
        name="Arduino Uno R3",
        category="Microcontrollers",
        search_keywords=["arduino", "uno", "microcontroller", "atmega328p"],
        description="Standard Arduino Uno R3 development board with ATmega328P.",
        did="132521",
        pins=[
            ComponentPin(name="D0", description="Digital Pin 0 / RX", terminal_type="digital"),
            ComponentPin(name="D1", description="Digital Pin 1 / TX", terminal_type="digital"),
            ComponentPin(name="D2", description="Digital Pin 2 / INT0", terminal_type="digital"),
            ComponentPin(name="D3", description="Digital Pin 3 / PWM", terminal_type="digital"),
            ComponentPin(name="D4", description="Digital Pin 4", terminal_type="digital"),
            ComponentPin(name="D5", description="Digital Pin 5 / PWM", terminal_type="digital"),
            ComponentPin(name="D6", description="Digital Pin 6 / PWM", terminal_type="digital"),
            ComponentPin(name="D7", description="Digital Pin 7", terminal_type="digital"),
            ComponentPin(name="D8", description="Digital Pin 8", terminal_type="digital"),
            ComponentPin(name="D9", description="Digital Pin 9 / PWM", terminal_type="digital"),
            ComponentPin(name="D10", description="Digital Pin 10 / PWM / SS", terminal_type="digital"),
            ComponentPin(name="D11", description="Digital Pin 11 / PWM / MOSI", terminal_type="digital"),
            ComponentPin(name="D12", description="Digital Pin 12 / MISO", terminal_type="digital"),
            ComponentPin(name="D13", description="Digital Pin 13 / SCK / Built-in LED", terminal_type="digital"),
            ComponentPin(name="GND_1", description="Ground pin (Digital header)", terminal_type="ground"),
            ComponentPin(name="AREF", description="Analog reference pin", terminal_type="general"),
            ComponentPin(name="A0", description="Analog Input 0", terminal_type="analog"),
            ComponentPin(name="A1", description="Analog Input 1", terminal_type="analog"),
            ComponentPin(name="A2", description="Analog Input 2", terminal_type="analog"),
            ComponentPin(name="A3", description="Analog Input 3", terminal_type="analog"),
            ComponentPin(name="A4", description="Analog Input 4 / SDA", terminal_type="analog"),
            ComponentPin(name="A5", description="Analog Input 5 / SCL", terminal_type="analog"),
            ComponentPin(name="VIN", description="External Voltage Input", terminal_type="power"),
            ComponentPin(name="GND_2", description="Ground pin (Power header)", terminal_type="ground"),
            ComponentPin(name="GND_3", description="Ground pin (Power header)", terminal_type="ground"),
            ComponentPin(name="5V", description="Regulated 5V output", terminal_type="power"),
            ComponentPin(name="3.3V", description="Regulated 3.3V output", terminal_type="power"),
            ComponentPin(name="RESET", description="Reset pin", terminal_type="general"),
            ComponentPin(name="IOREF", description="I/O Reference voltage", terminal_type="power"),
        ],
        default_properties={},
    ),
    "breadboard_small": ComponentDefinition(
        id="breadboard_small",
        name="Breadboard Small",
        category="General",
        search_keywords=["breadboard", "half", "protoboard", "small breadboard"],
        description="Half-size solderless breadboard with power rails (+/-) and tie-point rows 1-30 (A-E, F-J).",
        pins=[
            ComponentPin(name="power_pos_top", description="Top Positive Power Rail (+)", terminal_type="power", aliases=["+", "pos", "power", "5v", "top_+", "pos_top"]),
            ComponentPin(name="power_neg_top", description="Top Negative Ground Rail (-)", terminal_type="ground", aliases=["-", "neg", "gnd", "ground", "top_-", "neg_top"]),
            ComponentPin(name="power_pos_bot", description="Bottom Positive Power Rail (+)", terminal_type="power", aliases=["bot_+", "pos_bot", "bottom_+"]),
            ComponentPin(name="power_neg_bot", description="Bottom Negative Ground Rail (-)", terminal_type="ground", aliases=["bot_-", "neg_bot", "bottom_-"]),
        ],
        default_properties={},
    ),
    "resistor": ComponentDefinition(
        id="resistor",
        name="Resistor",
        category="Basic",
        search_keywords=["resistor", "resistance", "ohm"],
        description="Two-terminal passive resistor.",
        did="53184",
        pins=[
            ComponentPin(name="terminal_1", description="Terminal 1", terminal_type="terminal"),
            ComponentPin(name="terminal_2", description="Terminal 2", terminal_type="terminal"),
        ],
        default_properties={"resistance": "1", "unit": "kΩ"},
    ),
    "led": ComponentDefinition(
        id="led",
        name="LED",
        category="Basic",
        search_keywords=["led", "light", "diode", "lamp"],
        description="Standard 5mm Light Emitting Diode.",
        did="58422",
        pins=[
            ComponentPin(name="anode", description="Anode (+) longer leg", terminal_type="terminal"),
            ComponentPin(name="cathode", description="Cathode (-) shorter leg / flat edge", terminal_type="terminal"),
        ],
        default_properties={"color": "Red"},
    ),
    "rgb_led": ComponentDefinition(
        id="rgb_led",
        name="RGB LED",
        category="Basic",
        search_keywords=["rgb led", "color led", "tricolor"],
        description="Four-pin RGB LED (Common Cathode).",
        pins=[
            ComponentPin(name="red", description="Red Anode", terminal_type="terminal"),
            ComponentPin(name="cathode", description="Common Cathode (-)", terminal_type="ground"),
            ComponentPin(name="blue", description="Blue Anode", terminal_type="terminal"),
            ComponentPin(name="green", description="Green Anode", terminal_type="terminal"),
        ],
        default_properties={"type": "Common Cathode"},
    ),
    "pushbutton": ComponentDefinition(
        id="pushbutton",
        name="Pushbutton",
        category="Basic",
        search_keywords=["pushbutton", "button", "tactile switch", "switch"],
        description="Momentary tactile pushbutton switch (SPST).",
        pins=[
            ComponentPin(name="terminal_1a", description="Terminal 1a", terminal_type="terminal"),
            ComponentPin(name="terminal_1b", description="Terminal 1b", terminal_type="terminal"),
            ComponentPin(name="terminal_2a", description="Terminal 2a", terminal_type="terminal"),
            ComponentPin(name="terminal_2b", description="Terminal 2b", terminal_type="terminal"),
        ],
        default_properties={},
    ),
    "potentiometer": ComponentDefinition(
        id="potentiometer",
        name="Potentiometer",
        category="Basic",
        search_keywords=["potentiometer", "pot", "variable resistor", "dial"],
        description="Rotary potentiometer (variable resistor / voltage divider).",
        pins=[
            ComponentPin(name="terminal_1", description="Terminal 1", terminal_type="terminal"),
            ComponentPin(name="wiper", description="Wiper (Variable output)", terminal_type="signal"),
            ComponentPin(name="terminal_2", description="Terminal 2", terminal_type="terminal"),
        ],
        default_properties={"resistance": "10", "unit": "kΩ"},
    ),
    "capacitor": ComponentDefinition(
        id="capacitor",
        name="Capacitor",
        category="Basic",
        search_keywords=["capacitor", "ceramic capacitor", "cap"],
        description="Ceramic non-polarized capacitor.",
        pins=[
            ComponentPin(name="terminal_1", description="Terminal 1", terminal_type="terminal"),
            ComponentPin(name="terminal_2", description="Terminal 2", terminal_type="terminal"),
        ],
        default_properties={"capacitance": "100", "unit": "nF"},
    ),
    "slide_switch": ComponentDefinition(
        id="slide_switch",
        name="Slide Switch",
        category="Basic",
        search_keywords=["slide switch", "spdt", "switch", "toggle"],
        description="SPDT slide switch.",
        pins=[
            ComponentPin(name="terminal_1", description="Terminal 1", terminal_type="terminal"),
            ComponentPin(name="common", description="Common terminal", terminal_type="terminal"),
            ComponentPin(name="terminal_2", description="Terminal 2", terminal_type="terminal"),
        ],
        default_properties={},
    ),
    "battery_9v": ComponentDefinition(
        id="battery_9v",
        name="9V Battery",
        category="Power",
        search_keywords=["battery", "9v", "power source", "dc power"],
        description="Standard 9V alkaline battery.",
        pins=[
            ComponentPin(name="positive", description="Positive (+)", terminal_type="power"),
            ComponentPin(name="negative", description="Negative / GND (-)", terminal_type="ground"),
        ],
        default_properties={},
    ),
    "battery_coin": ComponentDefinition(
        id="battery_coin",
        name="Coin Cell 3V",
        category="Power",
        search_keywords=["coin cell", "cr2032", "3v battery", "button cell"],
        description="3V CR2032 coin cell battery.",
        pins=[
            ComponentPin(name="positive", description="Positive (+)", terminal_type="power"),
            ComponentPin(name="negative", description="Negative / GND (-)", terminal_type="ground"),
        ],
        default_properties={},
    ),
    "photoresistor": ComponentDefinition(
        id="photoresistor",
        name="Photoresistor",
        category="Sensors",
        search_keywords=["photoresistor", "ldr", "light sensor", "cds"],
        description="Light Dependent Resistor (LDR).",
        pins=[
            ComponentPin(name="terminal_1", description="Terminal 1", terminal_type="terminal"),
            ComponentPin(name="terminal_2", description="Terminal 2", terminal_type="terminal"),
        ],
        default_properties={},
    ),
    "ultrasonic_sensor_4pin": ComponentDefinition(
        id="ultrasonic_sensor_4pin",
        name="Ultrasonic Distance Sensor (4-pin)",
        category="Sensors",
        search_keywords=[
            "ultrasonic", "ultrasonic sensor", "ultrasonic distance sensor (4-pin)", "ultrasonic distance sensor",
            "distance sensor", "hc-sr04", "sonar", "sonar sensor", "hcsr04", "4-pin ultrasonic", "ultrasonic 4 pin"
        ],
        description="HC-SR04 4-pin ultrasonic distance sensor with separate Trigger and Echo pins (runtime pins: pos, trig, echo, neg).",
        did="219295",
        pins=[
            ComponentPin(name="pos", description="Power (+5V) / VCC / pos", terminal_type="power", aliases=["vcc", "power", "+", "5v"]),
            ComponentPin(name="trig", description="Trigger Pin / trig", terminal_type="signal", aliases=["trigger", "t"]),
            ComponentPin(name="echo", description="Echo Pin / echo", terminal_type="signal", aliases=["e"]),
            ComponentPin(name="neg", description="Ground (GND) / neg", terminal_type="ground", aliases=["gnd", "ground", "-"]),
        ],
        default_properties={},
    ),
    "ultrasonic_sensor_3pin": ComponentDefinition(
        id="ultrasonic_sensor_3pin",
        name="Ultrasonic Distance Sensor",
        category="Sensors",
        search_keywords=[
            "ultrasonic 3 pin", "3-pin ultrasonic", "3 pin distance sensor", "parallax ping",
            "3pin sonar", "3-pin sonar", "3pin ultrasonic", "ping"
        ],
        description="3-pin ultrasonic distance sensor with combined Signal pin (SIG, POS, NEG).",
        did="219294",
        pins=[
            ComponentPin(name="sig", description="Signal Pin", terminal_type="signal", aliases=["signal"]),
            ComponentPin(name="pos", description="Power (+5V)", terminal_type="power", aliases=["vcc", "power", "+", "5v"]),
            ComponentPin(name="neg", description="Ground (GND)", terminal_type="ground", aliases=["gnd", "ground", "-"]),
        ],
        default_properties={},
    ),
    "ultrasonic_sensor": ComponentDefinition(
        id="ultrasonic_sensor",
        name="Ultrasonic Distance Sensor (4-pin)",
        category="Sensors",
        search_keywords=["ultrasonic", "ultrasonic sensor", "distance sensor", "hc-sr04", "sonar", "hcsr04"],
        description="Default 4-pin ultrasonic distance sensor (HC-SR04) with Trigger and Echo pins (runtime pins: pos, trig, echo, neg).",
        did="219295",
        pins=[
            ComponentPin(name="pos", description="Power (+5V) / VCC / pos", terminal_type="power", aliases=["vcc", "power", "+", "5v"]),
            ComponentPin(name="trig", description="Trigger Pin / trig", terminal_type="signal", aliases=["trigger", "t"]),
            ComponentPin(name="echo", description="Echo Pin / echo", terminal_type="signal", aliases=["e"]),
            ComponentPin(name="neg", description="Ground (GND) / neg", terminal_type="ground", aliases=["gnd", "ground", "-"]),
        ],
        default_properties={},
    ),
    "hbridge_motor_driver": ComponentDefinition(
        id="hbridge_motor_driver",
        name="H-bridge Motor Driver",
        category="Power",
        search_keywords=[
            "h-bridge", "motor driver", "l293d", "l293", "hbridge", "h bridge", "driver ic",
            "dual motor driver", "motor controller"
        ],
        description="L293D dual H-bridge motor driver IC for bi-directional control of DC motors.",
        did="112326",
        pins=[
            ComponentPin(name="Enable1", description="Enable 1 & 2 (Speed / PWM)", terminal_type="signal"),
            ComponentPin(name="Input1", description="Input 1 (Direction 1A)", terminal_type="signal"),
            ComponentPin(name="Output1", description="Output 1 (Motor 1 Terminal A)", terminal_type="terminal"),
            ComponentPin(name="GND", description="Ground (Heatsink)", terminal_type="ground"),
            ComponentPin(name="GND1", description="Ground (Heatsink)", terminal_type="ground"),
            ComponentPin(name="Output2", description="Output 2 (Motor 1 Terminal B)", terminal_type="terminal"),
            ComponentPin(name="Input2", description="Input 2 (Direction 1B)", terminal_type="signal"),
            ComponentPin(name="Vs", description="Power 2 / Motor Supply Voltage (+4.5V to +36V)", terminal_type="power"),
            ComponentPin(name="Enable2", description="Enable 3 & 4 (Speed / PWM)", terminal_type="signal"),
            ComponentPin(name="Input3", description="Input 3 (Direction 2A)", terminal_type="signal"),
            ComponentPin(name="Output3", description="Output 3 (Motor 2 Terminal A)", terminal_type="terminal"),
            ComponentPin(name="GND2", description="Ground (Heatsink)", terminal_type="ground"),
            ComponentPin(name="GND3", description="Ground (Heatsink)", terminal_type="ground"),
            ComponentPin(name="Output4", description="Output 4 (Motor 2 Terminal B)", terminal_type="terminal"),
            ComponentPin(name="Input4", description="Input 4 (Direction 2B)", terminal_type="signal"),
            ComponentPin(name="Vss", description="Power 1 / Logic Supply Voltage (+5V)", terminal_type="power"),
        ],
        default_properties={},
    ),
    "pir_sensor": ComponentDefinition(
        id="pir_sensor",
        name="PIR Sensor",
        category="Sensors",
        search_keywords=["pir", "motion sensor", "infrared motion"],
        description="Passive Infrared (PIR) motion sensor.",
        pins=[
            ComponentPin(name="signal", description="Output Signal", terminal_type="signal"),
            ComponentPin(name="power", description="Power (+5V)", terminal_type="power"),
            ComponentPin(name="ground", description="Ground (GND)", terminal_type="ground"),
            ComponentPin(name="out", description="Output Signal", terminal_type="signal"),
            ComponentPin(name="vcc", description="Power (+5V)", terminal_type="power"),
            ComponentPin(name="gnd", description="Ground (GND)", terminal_type="ground"),
        ],
        default_properties={},
    ),
    "tmp36": ComponentDefinition(
        id="tmp36",
        name="Temperature Sensor",
        category="Sensors",
        search_keywords=["tmp36", "temperature", "thermometer", "temp sensor"],
        description="TMP36 precision analog temperature sensor (-40°C to +125°C).",
        pins=[
            ComponentPin(name="power", description="Power (+2.7V to +5.5V)", terminal_type="power"),
            ComponentPin(name="vout", description="Analog Output Voltage", terminal_type="analog"),
            ComponentPin(name="ground", description="Ground (GND)", terminal_type="ground"),
        ],
        default_properties={},
    ),
    "servo": ComponentDefinition(
        id="servo",
        name="Micro Servo",
        category="Output",
        search_keywords=["servo", "micro servo", "motor", "sg90"],
        description="Micro servo motor (0 to 180 degrees positioning).",
        pins=[
            ComponentPin(name="signal", description="PWM Control Signal (Orange/Yellow)", terminal_type="signal"),
            ComponentPin(name="power", description="Power +5V (Red)", terminal_type="power"),
            ComponentPin(name="ground", description="Ground (Brown/Black)", terminal_type="ground"),
        ],
        default_properties={},
    ),
    "piezo": ComponentDefinition(
        id="piezo",
        name="Piezo",
        category="Output",
        search_keywords=["piezo", "buzzer", "speaker", "sound", "beeper"],
        description="Piezo buzzer / speaker for tones and audio signals.",
        pins=[
            ComponentPin(name="positive", description="Positive (+)", terminal_type="terminal", aliases=["pos", "+", "1", "terminal_1", "anode"]),
            ComponentPin(name="negative", description="Negative (-)", terminal_type="terminal", aliases=["neg", "-", "2", "terminal_2", "cathode", "gnd", "ground"]),
        ],
        default_properties={},
    ),
    "dc_motor": ComponentDefinition(
        id="dc_motor",
        name="DC Motor",
        category="Output",
        search_keywords=["dc motor", "motor", "electric motor"],
        description="Standard miniature DC motor.",
        did="114158",
        pins=[
            ComponentPin(name="terminal_1", description="Terminal 1", terminal_type="terminal"),
            ComponentPin(name="terminal_2", description="Terminal 2", terminal_type="terminal"),
        ],
        default_properties={},
    ),
    "lcd_16x2": ComponentDefinition(
        id="lcd_16x2",
        name="LCD 16 x 2",
        category="Output",
        search_keywords=["lcd", "16x2", "display", "screen"],
        description="16x2 character alphanumeric LCD display.",
        pins=[
            ComponentPin(name="gnd", description="Ground", terminal_type="ground"),
            ComponentPin(name="vcc", description="VCC +5V", terminal_type="power"),
            ComponentPin(name="v0", description="Contrast adjustment", terminal_type="analog"),
            ComponentPin(name="rs", description="Register Select", terminal_type="signal"),
            ComponentPin(name="rw", description="Read/Write", terminal_type="signal"),
            ComponentPin(name="e", description="Enable", terminal_type="signal"),
            ComponentPin(name="db4", description="Data Bit 4", terminal_type="digital"),
            ComponentPin(name="db5", description="Data Bit 5", terminal_type="digital"),
            ComponentPin(name="db6", description="Data Bit 6", terminal_type="digital"),
            ComponentPin(name="db7", description="Data Bit 7", terminal_type="digital"),
            ComponentPin(name="led_pos", description="Backlight Anode (+)", terminal_type="power"),
            ComponentPin(name="led_neg", description="Backlight Cathode (-)", terminal_type="ground"),
        ],
        default_properties={},
    ),
    "polarized_capacitor": ComponentDefinition(
        id="polarized_capacitor",
        name="Capacitor Polarized",
        category="Basic",
        search_keywords=["polarized capacitor", "electrolytic capacitor", "capacitor polarized", "electrolytic"],
        description="Polarized electrolytic capacitor with positive anode and negative cathode.",
        did="53185",
        pins=[
            ComponentPin(name="anode", description="Anode (+)", terminal_type="terminal", aliases=["+", "pos", "terminal_1"]),
            ComponentPin(name="cathode", description="Cathode (-)", terminal_type="terminal", aliases=["-", "neg", "terminal_2", "gnd"]),
        ],
        default_properties={"capacitance": "1", "unit": "µF"},
    ),
    "diode": ComponentDefinition(
        id="diode",
        name="Diode",
        category="Basic",
        search_keywords=["diode", "rectifier", "1n4001"],
        description="Standard semiconductor PN junction diode.",
        did="53187",
        pins=[
            ComponentPin(name="anode", description="Anode (+)", terminal_type="terminal", aliases=["+", "pos", "terminal_1"]),
            ComponentPin(name="cathode", description="Cathode (-)", terminal_type="terminal", aliases=["-", "neg", "terminal_2"]),
        ],
        default_properties={},
    ),
    "zener_diode": ComponentDefinition(
        id="zener_diode",
        name="Zener Diode",
        category="Basic",
        search_keywords=["zener", "zener diode"],
        description="Zener diode for voltage regulation and reference.",
        pins=[
            ComponentPin(name="cathode", description="Cathode (-)", terminal_type="terminal", aliases=["-", "neg", "terminal_2"]),
            ComponentPin(name="anode", description="Anode (+)", terminal_type="terminal", aliases=["+", "pos", "terminal_1"]),
        ],
        default_properties={},
    ),
    "inductor": ComponentDefinition(
        id="inductor",
        name="Inductor",
        category="Basic",
        search_keywords=["inductor", "choke", "coil"],
        description="Passive two-terminal inductor.",
        pins=[
            ComponentPin(name="terminal_1", description="Terminal 1", terminal_type="terminal", aliases=["1"]),
            ComponentPin(name="terminal_2", description="Terminal 2", terminal_type="terminal", aliases=["2"]),
        ],
        default_properties={"inductance": "1", "unit": "µH"},
    ),
    "tilt_sensor": ComponentDefinition(
        id="tilt_sensor",
        name="Tilt Sensor",
        category="Sensors",
        search_keywords=["tilt sensor", "tilt switch", "ball switch", "tilt"],
        description="Orientation/tilt sensing switch.",
        pins=[
            ComponentPin(name="terminal_1", description="Terminal 1", terminal_type="terminal", aliases=["1"]),
            ComponentPin(name="terminal_2", description="Terminal 2", terminal_type="terminal", aliases=["2"]),
        ],
        default_properties={},
    ),
    "gas_sensor": ComponentDefinition(
        id="gas_sensor",
        name="Gas Sensor",
        category="Sensors",
        search_keywords=["gas sensor", "mq2", "smoke sensor", "gas"],
        description="Gas and smoke sensor (MQ-2 style).",
        pins=[
            ComponentPin(name="B1", description="Terminal B1", terminal_type="terminal"),
            ComponentPin(name="H1", description="Heater 1", terminal_type="power", aliases=["vcc", "5v"]),
            ComponentPin(name="B2", description="Terminal B2", terminal_type="terminal"),
            ComponentPin(name="A1", description="Terminal A1", terminal_type="terminal"),
            ComponentPin(name="H2", description="Heater 2", terminal_type="ground", aliases=["gnd"]),
            ComponentPin(name="A2", description="Terminal A2", terminal_type="terminal"),
        ],
        default_properties={},
    ),
    "photodiode": ComponentDefinition(
        id="photodiode",
        name="Photodiode",
        category="Sensors",
        search_keywords=["photodiode", "light sensor"],
        description="Semiconductor photodiode light sensor.",
        pins=[
            ComponentPin(name="anode", description="Anode (+)", terminal_type="terminal", aliases=["+", "pos"]),
            ComponentPin(name="cathode", description="Cathode (-)", terminal_type="terminal", aliases=["-", "neg"]),
        ],
        default_properties={},
    ),
    "ambient_light_sensor": ComponentDefinition(
        id="ambient_light_sensor",
        name="Ambient Light Sensor",
        category="Sensors",
        search_keywords=["ambient light sensor", "als", "light sensor"],
        description="Integrated ambient light sensor with analog voltage output.",
        pins=[
            ComponentPin(name="out", description="Analog Output", terminal_type="analog", aliases=["output", "signal", "sig"]),
            ComponentPin(name="vcc", description="Power (+5V)", terminal_type="power", aliases=["power", "+", "5v"]),
            ComponentPin(name="gnd", description="Ground", terminal_type="ground", aliases=["ground", "-"]),
        ],
        default_properties={},
    ),
    "flex_sensor": ComponentDefinition(
        id="flex_sensor",
        name="Flex Sensor",
        category="Sensors",
        search_keywords=["flex sensor", "bend sensor", "flex"],
        description="Variable resistor that changes resistance with flex/bend angle.",
        pins=[
            ComponentPin(name="terminal_1", description="Terminal 1", terminal_type="terminal", aliases=["1"]),
            ComponentPin(name="terminal_2", description="Terminal 2", terminal_type="terminal", aliases=["2"]),
        ],
        default_properties={},
    ),
    "force_sensor": ComponentDefinition(
        id="force_sensor",
        name="Force Sensor",
        category="Sensors",
        search_keywords=["force sensor", "fsr", "pressure sensor", "force"],
        description="Force Sensing Resistor (FSR).",
        pins=[
            ComponentPin(name="terminal_1", description="Terminal 1", terminal_type="terminal", aliases=["1"]),
            ComponentPin(name="terminal_2", description="Terminal 2", terminal_type="terminal", aliases=["2"]),
        ],
        default_properties={},
    ),
    "soil_moisture": ComponentDefinition(
        id="soil_moisture",
        name="Soil Moisture Sensor",
        category="Sensors",
        search_keywords=["soil moisture", "soil moisture sensor", "moisture sensor"],
        description="Two-prong resistive soil moisture sensor.",
        pins=[
            ComponentPin(name="signal", description="Signal Output", terminal_type="analog", aliases=["sig", "out"]),
            ComponentPin(name="power", description="Power (+5V)", terminal_type="power", aliases=["vcc", "+", "5v"]),
            ComponentPin(name="ground", description="Ground", terminal_type="ground", aliases=["gnd", "-"]),
        ],
        default_properties={},
    ),
    "ir_sensor": ComponentDefinition(
        id="ir_sensor",
        name="IR Sensor",
        category="Sensors",
        search_keywords=["ir sensor", "infrared sensor", "ir receiver"],
        description="Infrared receiver / sensor module.",
        pins=[
            ComponentPin(name="out", description="Signal Output", terminal_type="signal", aliases=["signal", "sig"]),
            ComponentPin(name="gnd", description="Ground", terminal_type="ground", aliases=["ground", "-"]),
            ComponentPin(name="vcc", description="Power (+5V)", terminal_type="power", aliases=["power", "+", "5v"]),
        ],
        default_properties={},
    ),
    "keypad_4x4": ComponentDefinition(
        id="keypad_4x4",
        name="Keypad 4x4",
        category="Input",
        search_keywords=["keypad", "4x4 keypad", "matrix keypad"],
        description="4x4 matrix membrane keypad with 8 pins (4 rows, 4 columns).",
        pins=[
            ComponentPin(name="row_1", description="Row 1", terminal_type="signal", aliases=["r1", "1"]),
            ComponentPin(name="row_2", description="Row 2", terminal_type="signal", aliases=["r2", "2"]),
            ComponentPin(name="row_3", description="Row 3", terminal_type="signal", aliases=["r3", "3"]),
            ComponentPin(name="row_4", description="Row 4", terminal_type="signal", aliases=["r4", "4"]),
            ComponentPin(name="col_1", description="Column 1", terminal_type="signal", aliases=["c1", "5"]),
            ComponentPin(name="col_2", description="Column 2", terminal_type="signal", aliases=["c2", "6"]),
            ComponentPin(name="col_3", description="Column 3", terminal_type="signal", aliases=["c3", "7"]),
            ComponentPin(name="col_4", description="Column 4", terminal_type="signal", aliases=["c4", "8"]),
        ],
        default_properties={},
    ),
    "dip_switch_4": ComponentDefinition(
        id="dip_switch_4",
        name="DIP Switch 4",
        category="Basic",
        search_keywords=["dip switch", "dip switch 4", "4 position switch"],
        description="4-position slide DIP switch.",
        pins=[
            ComponentPin(name="1a", description="Switch 1 Terminal A", terminal_type="terminal"),
            ComponentPin(name="1b", description="Switch 1 Terminal B", terminal_type="terminal"),
            ComponentPin(name="2a", description="Switch 2 Terminal A", terminal_type="terminal"),
            ComponentPin(name="2b", description="Switch 2 Terminal B", terminal_type="terminal"),
            ComponentPin(name="3a", description="Switch 3 Terminal A", terminal_type="terminal"),
            ComponentPin(name="3b", description="Switch 3 Terminal B", terminal_type="terminal"),
            ComponentPin(name="4a", description="Switch 4 Terminal A", terminal_type="terminal"),
            ComponentPin(name="4b", description="Switch 4 Terminal B", terminal_type="terminal"),
        ],
        default_properties={},
    ),
    "light_bulb": ComponentDefinition(
        id="light_bulb",
        name="Light Bulb",
        category="Output",
        search_keywords=["light bulb", "bulb", "lamp", "incandescent"],
        description="Incandescent miniature light bulb.",
        pins=[
            ComponentPin(name="terminal_1", description="Terminal 1", terminal_type="terminal", aliases=["1"]),
            ComponentPin(name="terminal_2", description="Terminal 2", terminal_type="terminal", aliases=["2"]),
        ],
        default_properties={},
    ),
    "neopixel": ComponentDefinition(
        id="neopixel",
        name="NeoPixel Ring 12",
        category="Output",
        search_keywords=["neopixel", "ws2812", "rgb ring", "neopixel ring"],
        description="WS2812 addressable RGB LED ring with 12 pixels.",
        pins=[
            ComponentPin(name="in", description="Data Input (IN)", terminal_type="signal", aliases=["data in", "din", "di"]),
            ComponentPin(name="power", description="Power (+5V / PWR)", terminal_type="power", aliases=["vcc", "+", "5v", "pwr"]),
            ComponentPin(name="ground", description="Ground (GND)", terminal_type="ground", aliases=["gnd", "-"]),
            ComponentPin(name="out", description="Data Output (OUT)", terminal_type="signal", aliases=["data out", "dout", "do"]),
        ],
        default_properties={},
    ),
    "seven_segment": ComponentDefinition(
        id="seven_segment",
        name="7 Segment Display",
        category="Output",
        search_keywords=["7 segment", "seven segment", "7-segment display", "led display"],
        description="Single digit 7-segment LED display with decimal point.",
        pins=[
            ComponentPin(name="a", description="Segment A", terminal_type="terminal"),
            ComponentPin(name="b", description="Segment B", terminal_type="terminal"),
            ComponentPin(name="com1", description="Common Anode/Cathode 1", terminal_type="terminal", aliases=["com", "common"]),
            ComponentPin(name="c", description="Segment C", terminal_type="terminal"),
            ComponentPin(name="dp", description="Decimal Point", terminal_type="terminal"),
            ComponentPin(name="d", description="Segment D", terminal_type="terminal"),
            ComponentPin(name="e", description="Segment E", terminal_type="terminal"),
            ComponentPin(name="com2", description="Common Anode/Cathode 2", terminal_type="terminal"),
            ComponentPin(name="f", description="Segment F", terminal_type="terminal"),
            ComponentPin(name="g", description="Segment G", terminal_type="terminal"),
        ],
        default_properties={},
    ),
    "relay_spdt": ComponentDefinition(
        id="relay_spdt",
        name="Relay SPDT",
        category="Power",
        search_keywords=["relay", "spdt relay", "relay spdt"],
        description="Single-pole double-throw electromechanical relay.",
        pins=[
            ComponentPin(name="coil_1", description="Coil Terminal 1", terminal_type="terminal", aliases=["coil1", "1"]),
            ComponentPin(name="coil_2", description="Coil Terminal 2", terminal_type="terminal", aliases=["coil2", "2"]),
            ComponentPin(name="com", description="Common (COM)", terminal_type="terminal", aliases=["common", "5"]),
            ComponentPin(name="no", description="Normally Open (NO)", terminal_type="terminal", aliases=["normally open", "6"]),
            ComponentPin(name="nc", description="Normally Closed (NC)", terminal_type="terminal", aliases=["normally closed", "8"]),
        ],
        default_properties={},
    ),
    "gear_motor": ComponentDefinition(
        id="gear_motor",
        name="Hobby Gearmotor",
        category="Output",
        search_keywords=["gearmotor", "hobby gearmotor", "yellow motor", "tt motor"],
        description="Geared DC motor commonly used in robotics.",
        pins=[
            ComponentPin(name="terminal_1", description="Terminal 1", terminal_type="terminal", aliases=["1"]),
            ComponentPin(name="terminal_2", description="Terminal 2", terminal_type="terminal", aliases=["2"]),
        ],
        default_properties={},
    ),
    "dc_motor_with_encoder": ComponentDefinition(
        id="dc_motor_with_encoder",
        name="DC Motor with Encoder",
        category="Output",
        search_keywords=["motor encoder", "dc motor encoder", "encoder motor"],
        description="DC motor equipped with a quadrature optical encoder.",
        pins=[
            ComponentPin(name="m1", description="Motor Terminal 1", terminal_type="terminal", aliases=["terminal_1"]),
            ComponentPin(name="m2", description="Motor Terminal 2", terminal_type="terminal", aliases=["terminal_2"]),
            ComponentPin(name="vcc", description="Encoder Power (+5V)", terminal_type="power", aliases=["power", "+", "5v"]),
            ComponentPin(name="gnd", description="Encoder Ground", terminal_type="ground", aliases=["ground", "-"]),
            ComponentPin(name="c1", description="Encoder Channel A", terminal_type="signal", aliases=["channel_a", "cha"]),
            ComponentPin(name="c2", description="Encoder Channel B", terminal_type="signal", aliases=["channel_b", "chb"]),
        ],
        default_properties={},
    ),
    "logic_ic_74hc08": ComponentDefinition(
        id="logic_ic_74hc08",
        name="Quad AND Gate 74HC08",
        category="Logic",
        search_keywords=["74hc08", "and gate", "quad and"],
        description="74HC08 quad 2-input positive-AND gates IC.",
        pins=[
            ComponentPin(name="1A", description="Gate 1 Input A", terminal_type="digital"),
            ComponentPin(name="1B", description="Gate 1 Input B", terminal_type="digital"),
            ComponentPin(name="1Y", description="Gate 1 Output Y", terminal_type="digital"),
            ComponentPin(name="2A", description="Gate 2 Input A", terminal_type="digital"),
            ComponentPin(name="2B", description="Gate 2 Input B", terminal_type="digital"),
            ComponentPin(name="2Y", description="Gate 2 Output Y", terminal_type="digital"),
            ComponentPin(name="GND", description="Ground", terminal_type="ground"),
            ComponentPin(name="3Y", description="Gate 3 Output Y", terminal_type="digital"),
            ComponentPin(name="3A", description="Gate 3 Input A", terminal_type="digital"),
            ComponentPin(name="3B", description="Gate 3 Input B", terminal_type="digital"),
            ComponentPin(name="4Y", description="Gate 4 Output Y", terminal_type="digital"),
            ComponentPin(name="4A", description="Gate 4 Input A", terminal_type="digital"),
            ComponentPin(name="4B", description="Gate 4 Input B", terminal_type="digital"),
            ComponentPin(name="VCC", description="Supply Voltage (+5V)", terminal_type="power"),
        ],
        default_properties={},
    ),
    "logic_ic_74hc32": ComponentDefinition(
        id="logic_ic_74hc32",
        name="Quad OR Gate 74HC32",
        category="Logic",
        search_keywords=["74hc32", "or gate", "quad or"],
        description="74HC32 quad 2-input positive-OR gates IC.",
        pins=[
            ComponentPin(name="1A", description="Gate 1 Input A", terminal_type="digital"),
            ComponentPin(name="1B", description="Gate 1 Input B", terminal_type="digital"),
            ComponentPin(name="1Y", description="Gate 1 Output Y", terminal_type="digital"),
            ComponentPin(name="2A", description="Gate 2 Input A", terminal_type="digital"),
            ComponentPin(name="2B", description="Gate 2 Input B", terminal_type="digital"),
            ComponentPin(name="2Y", description="Gate 2 Output Y", terminal_type="digital"),
            ComponentPin(name="GND", description="Ground", terminal_type="ground"),
            ComponentPin(name="3Y", description="Gate 3 Output Y", terminal_type="digital"),
            ComponentPin(name="3A", description="Gate 3 Input A", terminal_type="digital"),
            ComponentPin(name="3B", description="Gate 3 Input B", terminal_type="digital"),
            ComponentPin(name="4Y", description="Gate 4 Output Y", terminal_type="digital"),
            ComponentPin(name="4A", description="Gate 4 Input A", terminal_type="digital"),
            ComponentPin(name="4B", description="Gate 4 Input B", terminal_type="digital"),
            ComponentPin(name="VCC", description="Supply Voltage (+5V)", terminal_type="power"),
        ],
        default_properties={},
    ),
    "logic_ic_74hc04": ComponentDefinition(
        id="logic_ic_74hc04",
        name="Hex Inverter 74HC04",
        category="Logic",
        search_keywords=["74hc04", "hex inverter", "not gate", "inverter"],
        description="74HC04 hex inverter (NOT gate) IC.",
        pins=[
            ComponentPin(name="1A", description="Inverter 1 Input A", terminal_type="digital"),
            ComponentPin(name="1Y", description="Inverter 1 Output Y", terminal_type="digital"),
            ComponentPin(name="2A", description="Inverter 2 Input A", terminal_type="digital"),
            ComponentPin(name="2Y", description="Inverter 2 Output Y", terminal_type="digital"),
            ComponentPin(name="3A", description="Inverter 3 Input A", terminal_type="digital"),
            ComponentPin(name="3Y", description="Inverter 3 Output Y", terminal_type="digital"),
            ComponentPin(name="GND", description="Ground", terminal_type="ground"),
            ComponentPin(name="4Y", description="Inverter 4 Output Y", terminal_type="digital"),
            ComponentPin(name="4A", description="Inverter 4 Input A", terminal_type="digital"),
            ComponentPin(name="5Y", description="Inverter 5 Output Y", terminal_type="digital"),
            ComponentPin(name="5A", description="Inverter 5 Input A", terminal_type="digital"),
            ComponentPin(name="6Y", description="Inverter 6 Output Y", terminal_type="digital"),
            ComponentPin(name="6A", description="Inverter 6 Input A", terminal_type="digital"),
            ComponentPin(name="VCC", description="Supply Voltage (+5V)", terminal_type="power"),
        ],
        default_properties={},
    ),
}


def find_component_candidates(query: str) -> List[ComponentDefinition]:
    """Find component definition candidates by query with strict tiering to avoid ambiguous matching."""
    if not query or not query.strip():
        return []
    q = query.lower().strip()

    # Tier 1: Exact ID match
    if q in COMPONENTS_CATALOG:
        return [COMPONENTS_CATALOG[q]]

    # Also check did match (e.g. "114158")
    for comp in COMPONENTS_CATALOG.values():
        if comp.did and comp.did.lower() == q:
            return [comp]

    # Tier 2: Exact Name match (case-insensitive)
    exact_names = [comp for comp in COMPONENTS_CATALOG.values() if comp.name.lower() == q]
    if exact_names:
        return exact_names

    # Tier 3: Exact Keyword match
    exact_kw = [
        comp for comp in COMPONENTS_CATALOG.values()
        if any(q == kw.lower() for kw in comp.search_keywords)
    ]
    if exact_kw:
        return exact_kw

    # Tier 4: Prefix/word boundary match in component name
    name_prefix = [
        comp for comp in COMPONENTS_CATALOG.values()
        if comp.name.lower().startswith(q) or any(w.startswith(q) for w in comp.name.lower().split())
    ]
    if name_prefix:
        return name_prefix

    # Tier 5: Substring containment in name or keywords (excluding generic short words)
    if len(q) >= 3:
        contain_matches = [
            comp for comp in COMPONENTS_CATALOG.values()
            if q in comp.name.lower() or any(q in kw.lower() for kw in comp.search_keywords)
        ]
        if contain_matches:
            return contain_matches

    # Tier 6: Multi-word query where all tokens appear in name or keywords
    words = [w for w in q.split() if len(w) >= 2]
    if len(words) > 1:
        token_matches = [
            comp for comp in COMPONENTS_CATALOG.values()
            if all(w in comp.name.lower() or any(w in kw.lower() for kw in comp.search_keywords) for w in words)
        ]
        if token_matches:
            return token_matches

    return []


def find_component_by_query(query: str, required_pins: Optional[List[str]] = None) -> Optional[ComponentDefinition]:
    """Find component definition by exact id or unambiguous match, with smart disambiguation."""
    candidates = find_component_candidates(query)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    q = query.lower().strip()

    # Ultrasonic disambiguation:
    # If caller specifies required_pins with 'trig' or 'echo', or query does not say '3-pin'/'3pin'/'3 pin',
    # prioritize the standard 4-pin HC-SR04 sensor.
    if any("ultrasonic" in c.id for c in candidates):
        if "3" in q and ("pin" in q or "3pin" in q or "3-pin" in q):
            for c in candidates:
                if c.id == "ultrasonic_sensor_3pin":
                    return c
        for c in candidates:
            if c.id == "ultrasonic_sensor_4pin" or c.id == "ultrasonic_sensor":
                return c

    # Motor driver disambiguation:
    if any("hbridge" in c.id for c in candidates):
        for c in candidates:
            if c.id == "hbridge_motor_driver":
                return c

    # Filter by required_pins if provided
    if required_pins:
        norm_req = [p.lower().replace("_", "").replace("-", "") for p in required_pins]
        matching_pins = []
        for c in candidates:
            c_pins = [p.name.lower().replace("_", "").replace("-", "") for p in c.pins]
            if all(any(rp in cp or cp in rp for cp in c_pins) for rp in norm_req):
                matching_pins.append(c)
        if len(matching_pins) == 1:
            return matching_pins[0]
        if matching_pins:
            return matching_pins[0]

    # If ambiguous and no disambiguation rule resolved it, return None
    return None


def find_component_by_did(did: Any) -> Optional[ComponentDefinition]:
    """Find component definition by Tinkercad did attribute."""
    if did is None:
        return None
    sdid = str(did).strip().lower()
    for comp in COMPONENTS_CATALOG.values():
        if comp.did and comp.did.lower() == sdid:
            return comp
    return None


def list_components_catalog(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return catalog listing as dicts."""
    results = []
    for comp in COMPONENTS_CATALOG.values():
        if category and comp.category.lower() != category.lower():
            continue
        results.append({
            "id": comp.id,
            "name": comp.name,
            "category": comp.category,
            "description": comp.description,
            "pins": [{"name": p.name, "description": p.description, "type": p.terminal_type} for p in comp.pins],
            "default_properties": comp.default_properties,
        })
    return results

