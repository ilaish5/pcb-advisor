# Diagram Operations and Live Editing

The agent edits the block diagram directly via `idea.diagram.edit` actions.

## Direct Edit vs Diagram Proposal
- Use `idea.diagram.edit` for live, incremental changes: adding or updating blocks, connecting buses or power rails, grouping into domain frames, or auto-layout. Applied immediately without waiting for student approval.
- Use `idea.diagram` (whole-diagram proposal) only for complete architectural overhauls or structural rewrites where the student should approve the entire replacement first.

## Operations Reference
The `idea.diagram.edit` action accepts a list of ops (`ops: [...]`, capped at 100 ops). Missing coordinates are placed automatically near related shapes.

1. `add_shape`: `{"op": "add_shape", "id": "chg", "text": "Charger\nBQ24075", "type": "box", "domain": "power", "x": 160, "y": 80, "w": 120, "h": 60}`
   - `id`: unique shape id.
   - `text`: short label: part name + one-line role (use `\n` for subtitle).
   - `domain`: optional colour domain: `power`, `sensing`, `mcu`, `comms`, `rf`, `drive`, `io`, `ui` (anything else is refused).
   - `strokeStyle`: `dashed` for a safety path block (emergency stop, hardware cut).
   - `x`, `y`, `w`, `h`: optional coordinates and size.
2. `update_shape`: `{"op": "update_shape", "id": "chg", "text": "Charger\nBQ24075 (500mA)", "domain": "power"}`
3. `delete_shape`: `{"op": "delete_shape", "id": "chg"}` (also removes all incident connectors).
4. `add_connector`: `{"op": "add_connector", "id": "c1", "from": "usb", "to": "chg", "label": "5V", "arrows": "to"}`
   - `from`, `to`: shape IDs, or `{"shape": "mcu", "point": "top-left"}` to pick the side or corner (`top`, `bottom`,
     `left`, `right`, `top-left`, `top-right`, `bottom-left`, `bottom-right`) so two links do not share one point.
   - `label`: bus name, voltage, or protocol (e.g., "5V", "3V3", "I2C", "SPI", "UART").
   - `style`: `solid`, `dashed`, `thick`.
   - `arrows`: `none`, `to`, `both`.
5. `update_connector`: `{"op": "update_connector", "id": "c1", "label": "5V 500mA"}`
6. `delete_connector`: `{"op": "delete_connector", "id": "c1"}`
7. `add_frame`: `{"op": "add_frame", "id": "f_pwr", "title": "Power Subsystem", "around": ["usb", "chg", "ldo"]}`
   - `around`: list of shape IDs to enclose (bounds computed automatically with padding). Or specify `x`, `y`, `w`, `h`.
   - `domain`: optional style domain for the frame border.
8. `update_frame`: `{"op": "update_frame", "id": "f_pwr", "title": "Power Subsystem (5V/3.3V)"}`
9. `delete_frame`: `{"op": "delete_frame", "id": "f_pwr"}`
10. `auto_layout`: `{"op": "auto_layout"}` (rearranges shapes left-to-right following connectors; recalculates enclosing frames).

## Default style: the system block diagram (owner's choice, 2026-10-14)
Draw every new block diagram this way unless the student asks for another layout. Model: the real-project controller's
presentation diagram.

- **Board frame.**
  - One frame is the board itself, titled with what it is (e.g. "Custom 4-Layer PCB (main controller board)").
  - Everything on the board goes inside it.
  - Everything off the board goes outside it, at the edge it connects from: the supply or adapter, sensors, the
    display and buttons, loads and relays, the cloud or phone, the STOP input.
- **Blocks.** One per function, not per part.
  - Text is two lines: the part or function name (it renders bold), then one plain line saying what it does.
  - Examples: "MP2315 & AP2112\nOn-board voltage converters", "STM32F411 (MCU)\nSystem brain and control".
  - Refs and details go in `role`, not on the canvas.
- **Colour by domain:**
  - power: supply and converters;
  - sensing: sensors and ADCs;
  - mcu: the controller;
  - comms: modem, radio and cloud;
  - drive: drivers, relays and loads;
  - ui: display and buttons.
  The MCU block is the largest, in the middle.
- **Flow left to right:** inputs on the left, the MCU in the centre, outputs and the outside world on the right,
  the user interface and storage below.
- **Links.**
  - Every link has a short label: the voltage ("12V DC", "3.3V") or the bus ("SPI", "UART", "I²C / GPIO",
    "4G LTE").
  - Its colour is the domain of the block it serves.
  - The arrow points the way power or data flows.
  - Pick points (`top-left`, `bottom`, ...) so links do not overlap.
- **Safety paths:** a block and link that cut power in hardware are `dashed`, in the drive colour.
- **Size:** 10 to 14 blocks. Keep detail (decoupling, test points, resistors) out.

## Style Guidelines
- Keep text short: component name + one-line role (e.g., "MCU\nSTM32G030", "IMU\nBMI270", "LDO\nAP2112K-3.3").
- Connectors carry clear bus or voltage labels ("5V", "3V3", "I2C", "SPI", "SWD").
- Inside a big board frame, smaller frames may group a domain (Power, Radio) when the student asks for it.

## Examples

### Example 1: Power Chain
```json
{
  "type": "idea.diagram.edit",
  "reason": "Add USB-C power input, Li-ion charger, and 3.3V LDO",
  "ops": [
    {"op": "add_shape", "id": "usb", "text": "USB-C\nInput 5V", "domain": "power"},
    {"op": "add_shape", "id": "chg", "text": "Charger\nBQ24075", "domain": "power"},
    {"op": "add_shape", "id": "bat", "text": "Battery\n1S LiPo 3.7V", "domain": "power"},
    {"op": "add_shape", "id": "ldo", "text": "LDO\nAP2112K-3.3", "domain": "power"},
    {"op": "add_connector", "from": "usb", "to": "chg", "label": "5V"},
    {"op": "add_connector", "from": "bat", "to": "chg", "label": "VBAT", "arrows": "both"},
    {"op": "add_connector", "from": "chg", "to": "ldo", "label": "VOUT (3.8-5V)"},
    {"op": "add_frame", "id": "f_pwr", "title": "Power Domain", "around": ["usb", "chg", "bat", "ldo"]}
  ]
}
```

### Example 2: MCU and Buses
```json
{
  "type": "idea.diagram.edit",
  "reason": "Connect MCU to sensors and debug interface",
  "ops": [
    {"op": "add_shape", "id": "mcu", "text": "MCU\nSTM32G030K8", "domain": "mcu"},
    {"op": "add_shape", "id": "imu", "text": "IMU Sensor\nBMI270", "domain": "sensing"},
    {"op": "add_shape", "id": "swd", "text": "SWD Debug\nTag-Connect", "domain": "mcu"},
    {"op": "add_connector", "from": "mcu", "to": "imu", "label": "I2C (400kHz)", "arrows": "both"},
    {"op": "add_connector", "from": "swd", "to": "mcu", "label": "SWDIO / SWCLK", "arrows": "both"}
  ]
}
```

### Example 3: Dashed Domain Frame
```json
{
  "type": "idea.diagram.edit",
  "reason": "Group RF subsystem into a domain frame",
  "ops": [
    {"op": "add_shape", "id": "rf_mod", "text": "LoRa Transceiver\nSX1262", "domain": "rf"},
    {"op": "add_shape", "id": "ant", "text": "Antenna\nSMA Connector", "domain": "rf"},
    {"op": "add_connector", "from": "rf_mod", "to": "ant", "label": "RF 868MHz", "arrows": "both"},
    {"op": "add_frame", "id": "f_rf", "title": "RF Domain (50 Ohm)", "around": ["rf_mod", "ant"], "domain": "rf"}
  ]
}
```
