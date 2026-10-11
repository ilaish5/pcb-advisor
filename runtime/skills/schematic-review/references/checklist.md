# Schematic review checklist (general; read the datasheet of each part, cite its page)

## 1. Power pins and decoupling
- Every VDD/VCC/AVDD pin has its own decoupling capacitor at the pin, value from the datasheet "power supply" or "decoupling"
  section. Count the VDD pins on the package and count the caps.
- Analog supply (VDDA/AVCC) often wants a ferrite or RC plus a small and a large cap. Follow the datasheet figure.
- Bulk cap near each regulator output. The datasheet gives min, often max, capacitance and an ESR range for stability.
- Ceramic caps lose capacity with DC bias (a 10 V part at 5 V can lose half). Check the derating if the datasheet is strict.
- Regulator pins with a MAX capacitance (BIAS, VCC, soft-start, bootstrap): compare both ends of the allowed range.

## 2. Resets and boot
- Reset pin: pull-up value, optional cap, button to ground. Check whether the pull-up is internal.
- Boot-mode pins: defined level in the normal case, and a way to change it (button or jumper) if the student wants the
  chip's built-in loader (for example USB DFU or UART). Read which interface the vendor's boot-loader note allows.
- Programming/debug connector: power, ground, clock, data, reset. Read the pinout from the tool's manual, not from memory.

## 3. Pull-ups and pull-downs
- Open-drain or open-collector output, I2C lines, wired-OR: needs a pull-up. Value from bus speed and capacitance
  (`course/altium-education/unit4-routing-signal-integrity.en.md` [29]).
- Push-pull output: no pull-up. If a safe default is wanted when the driver is dead, the pull-DOWN is the fail-safe.
- Inputs that can float (buttons, enables, chip selects): need a defined level, external or internal.
- Check internal pulls in the datasheet before adding external ones (USB D+ pull-up, GPIO pulls, boot pins).

## 4. Output types
- Look for "output structure", "open drain", or VOH/VOL with the load current. VOH within about 0.5 V of VCC = push-pull.
- Level shifting is needed when two parts run at different I/O voltage. Compare VIH/VIL of the receiver with VOH/VOL of the driver.

## 5. Unconnected and unused pins
- Datasheet says NC: leave open. Datasheet says "connect to GND/VCC": do it. Unused GPIO: follow the vendor note.
- In Altium a pin left open on purpose gets a No-ERC cross so the ERC stays readable.

## 6. Absolute maximum and operating limits
- Every net voltage against the abs-max and recommended range of every pin on that net (including connectors going off-board).
- Reverse polarity, ESD and over-voltage on external connectors: is there a protection part where the datasheet suggests one?
- Current: LED resistors, GPIO source/sink limits, regulator output current against the sum of the loads.

## 7. Crystal and clocks
- Load capacitors from the crystal's CL: C = 2 x (CL - Cstray), stray about 3-5 pF. Cite the crystal and MCU pages.
- Frequency inside the MCU's allowed range, and inside the range the boot loader / USB needs.

## Swap (MCU or key part replaced)
1. Get the old and the new datasheet pin tables for the same package. Build a table: pin number | old function | new function.
2. Pins whose function changed: what net is connected there? (GPIO moved, power pin became GPIO, GPIO became a regulator pin.)
3. Pins that now need a part (core-regulator capacitor, boot pin, reference cap) or no longer need one (internal pull-up).
4. Peripherals the design uses: same pins on the new part? The alternate-function map is a table in the datasheet.
5. Supply voltage, crystal range and USB clock requirement of the new part.
6. Programming path and boot mode of the new part.
7. Library: same footprint? Pin types set? At ECO, designators must be kept; a renamed part must be renamed on the PCB first,
   or ECO deletes it and adds a new one.
Report as: added / removed / moved / unchanged-but-recheck, each with a datasheet page.
