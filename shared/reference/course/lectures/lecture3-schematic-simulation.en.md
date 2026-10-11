# Lecture 3 - Schematic Simulation (SPICE in Altium Designer)

> Source: `lecture3-schematic-simulation.en.pdf` (25 slides, Dr. Avihai Aharon, "PCB Design"; the slide header says course no. 50177). Text condensed from the slides on 2026-10-11; the slides' screenshots are not reproduced. Slide numbers in `[s.N]` are PDF pages.

## 1. What SPICE is [s.3]
SPICE (Simulation Program with Integrated Circuit Emphasis) is a general-purpose analog circuit simulator. It is used in IC and board-level design to check the integrity of a design and predict circuit behavior before building it.

## 2. Workflow in Altium [s.4-9]
1. Enable the **Mixed Simulation** extension (first time only).
2. Create a new PCB project, then a new schematic sheet.
3. Draw the schematic; add a voltage source (`VSRC`) and the other components (they need simulation models).
4. Open the **Simulation Dashboard** panel. It has four areas: Checking, Configuring, Running, Reviewing.
   - **Verification**: electrical rules checks must pass and every component must have a simulation model. Missing models or source problems are flagged with links to help fix them.
   - **Preparation**: lists the simulation sources and probes (click one to jump to it); more can be added.
   - **Analysis Setup & Run**: choose the analysis type and the output expressions to plot, then run.
   - **Results**: earlier runs are listed; double-click to reopen a waveform.

## 3. Analysis types [s.10-14]
| Analysis | What it does |
|---|---|
| Operating Point | DC operating point; inductors shorted, capacitors open |
| Poles and Zeros | stability of a single-input single-output linear system from the small-signal AC transfer function (DC point found, then linearized) |
| DC Transfer function | DC small-signal: input resistance, output resistance and DC gain at each node |
| DC Sweep | like a curve tracer; sweeps temperature, source voltages/currents, resistances. AC sources zeroed, capacitors open, inductors shorted, digital parts treated as a large resistor to ground |
| Transient | like an oscilloscope: voltage/current versus time over a chosen interval; an Operating Point runs first unless *Use Initial Conditions* is on |
| Fourier | based on the last cycle of the transient data (fundamental 1 kHz -> last 1 ms) |
| AC Sweep | small-signal frequency response; Operating Point first, then a fixed-amplitude sine source swept over a frequency range; usually the output is a transfer function (gain, trans-impedance) |
| Noise | noise contribution of resistors and semiconductors as noise spectral density (V^2/Hz); capacitors, inductors and controlled sources are noise free |
| Temperature sweep | repeats the enabled analyses at each temperature of a range; one curve per temperature |
| Parameter sweep | sweeps a device value in steps (a secondary parameter can also be swept); varies basic components and models, not sub-circuit data |
| Monte Carlo | many runs with component values randomly varied inside their tolerances; same limits as parameter sweep |

## 4. Exercises [s.16-24]
Each exercise: new project -> new schematic -> add components -> add `VSRC` -> open the Simulation Dashboard -> simulate.
1. **Simple voltage divider**: Operating Point and DC Sweep with a DC source.
2. **Diode and resistor**: Operating Point, DC Sweep (DC source), Transient (sinusoidal source).
3. **Zener diode and resistor**: DC Sweep and Transient. To get Vz = -10 V set the diode model parameter `BV=10` (breakdown voltage).
4. **555 astable multivibrator**: Transient, first as is (output oscillates around 1 kHz), then a parameter sweep of CT1 / RA1 / RB1 to see the effect. Uses an Initial Condition component.
5. **Bandpass filter** (centered around 1 kHz): Transient and AC Sweep with a sinusoidal source; import the circuit from another schematic or project; create a schematic library from the schematic with *Design > Make Schematic Library*; export plot data with *File > Export > Chart / Plot / Waveform*.

## 5. Links given in the lecture [s.25]
- A Guide to SPICE Simulation in Altium Designer: https://www.altium.com/documentation/altium-designer/spice-simulation-guide
- Working with the Simulation UI in Altium Designer: https://www.altium.com/documentation/altium-designer/simulation-user-interface
