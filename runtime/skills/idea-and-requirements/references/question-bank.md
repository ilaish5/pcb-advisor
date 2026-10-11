# Question bank (idea-and-requirements)

Each entry: why it matters, what it decides next. Use only the entries that are still open.

## Power source and budget
- Why: the source sets the regulator type, input protection, connector and charger. Peak current (a radio or motor burst) sets track
  width and bulk capacitor size. A late change from USB to battery redoes the power sheet.
- Next: list voltage and current per rail, then pick parts per rail.

## Flashing and debug
- Why: decides a connector or a BOOT button, and the MCU family. USB DFU in ROM needs the USB pins wired to a connector and a way to
  pull BOOT0 high at power-up. SWD needs a header (or pads) and a programmer.
- Next: MCU choice; header or test pads; BOOT button; USB connector. Cite the MCU reference manual or ST boot-mode note.

## Cable sides and enclosure
- Why: plug direction and edge are fixed by the box. The 3D view shows a mistake only after placement.
- Next: connector list with edge and entry direction; mounting holes; height limit.

## UI
- Why: a display and buttons need MCU pins, a connector, and often a different edge.
- Next: pin budget of the MCU.

## Memory
- Why: external flash adds a footprint, a bus and cost. Internal memory is free if it is enough.
- Next: size estimate; NOR flash before NAND when only logs are stored.

## Assembly at JLC
- Why: Basic parts have no extra fee, Extended parts add a fee per part type, "Standard only" parts block the cheaper Economic service.
  Through-hole parts and some modules may not be assembled at all.
- Next: `parts-and-stock` for the real parts, with stock and price at the planned quantity.

## Size, layers, height
- Why: layer count sets stackup and rules; a height limit conflicts with tall connectors.
