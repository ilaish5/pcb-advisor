# Power — design considerations corpus

Written to be read by a human engineer with no agent involved. `cascade/power.yaml`
is the machine-readable form of the same knowledge; this file is the reasoning behind it.

## Why topology is the pivot

Linear vs switching is the decision that locks the most layout constraints in the
whole power design. A linear regulator asks one question of the layout — can you get
the heat out? A switching regulator asks five, and four of them are about a single
current loop.

Once parts are ordered, reversing this decision means a new schematic and a new board.

## Linear regulators

**The whole problem is heat.** P = (Vin − Vout) × I, dissipated in the package.
12 V → 5 V at 500 mA is 3.5 W, which no SOT-23 survives.

- Compute P, compare against θJA from the datasheet's Thermal Information section.
- Tj = Tambient + P × θJA. Stay under ~70% of the rated maximum.
- In a sealed enclosure, ambient is 50–60 °C, not 25 °C. This halves the budget and
  is the single most common thermal miss.
- Copper pour under the thermal pad, thermal vias to the far side.
- LDOs care about output-capacitor ESR. Some oscillate with a pure ceramic cap.
  Check the stability section, not just the value.

## Switching regulators

**The hot loop is everything.** The loop Vin → SW → L → Cout → GND carries a current
that switches in nanoseconds. Its enclosed area behaves as a loop antenna, and its
area — not its length — sets the radiated emissions.

1. Input capacitor as close to VIN/GND as physically possible. This is the highest-leverage
   placement on the whole board.
2. Keep the SW node copper small. It is the dV/dt aggressor: every volt it swings couples
   into anything nearby. Small enough to carry the current, no larger.
3. Nothing routed under or beside the SW node, on any layer.
4. Feedback trace connects at the output capacitor, and is routed away from the inductor
   and the SW node. It is a high-impedance node listening for millivolts next to a
   part swinging volts.
5. One ground connection between power ground and signal ground, at the output capacitor.

Sources: TI SLYT614; the Layout Guidelines section of any modern buck datasheet
(TPS562201, LM2675, MP2307 all say the same five things).

## Reverse polarity

The most common destructive mistake on a prototype, and the cheapest to prevent.

- Series Schottky: one part, ~0.4 V drop, dissipates I × Vf. Subtract the drop from
  the input voltage before checking dropout.
- Series P-FET: near-zero drop, costs more, and the gate needs a zener or divider if
  the input can exceed Vgs(max).

## Trace width

IPC-2221 §6.2, external layer, 1 oz copper, 10 °C rise:

| current | width |
|---|---|
| 0.5 A | 0.20 mm |
| 1.0 A | 0.33 mm |
| 1.5 A | 0.53 mm |
| 2.0 A | 0.75 mm |
| 3.0 A | 1.25 mm |

Internal layers need roughly twice the width for the same rise. Use
`scripts/trace_width.py` rather than reading off this table — it is here for sanity
checking, not for design.
