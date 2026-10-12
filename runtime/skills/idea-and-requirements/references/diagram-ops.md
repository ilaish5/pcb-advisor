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
   - `domain`: optional style domain (`power`, `digital`, `analog`, `mcu`, `rf`, `sensor`, `ui`).
   - `x`, `y`, `w`, `h`: optional coordinates and size.
2. `update_shape`: `{"op": "update_shape", "id": "chg", "text": "Charger\nBQ24075 (500mA)", "domain": "power"}`
3. `delete_shape`: `{"op": "delete_shape", "id": "chg"}` (also removes all incident connectors).
4. `add_connector`: `{"op": "add_connector", "id": "c1", "from": "usb", "to": "chg", "label": "5V", "arrows": "to"}`
   - `from`, `to`: shape IDs.
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

## Style Guidelines
- Keep text short: component name + one-line role (e.g., "MCU\nSTM32G030", "IMU\nBMI270", "LDO\nAP2112K-3.3").
- Connectors carry clear bus or voltage labels ("5V", "3V3", "I2C", "SPI", "SWD").
- Use frames with dashed borders to delineate functional domains (Power, MCU, Radio, Sensor).

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
    {"op": "add_shape", "id": "imu", "text": "IMU Sensor\nBMI270", "domain": "sensor"},
    {"op": "add_shape", "id": "swd", "text": "SWD Debug\nTag-Connect", "domain": "digital"},
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
