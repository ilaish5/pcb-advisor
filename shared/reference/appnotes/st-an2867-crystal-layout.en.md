# ST AN2867 crystal layout guidance (summary)

> Source: ST application note AN2867, "Oscillator design guide for STM8AF/AL/S and STM32 microcontrollers", Rev 10 (Aug 2015), read 2026-11-27. Summary in our own words; the note itself is copyrighted and is not copied. Newer revisions exist (Rev 12, Jan 2020, and later) and this file was not checked against them.

## Sources
| ID | Page | URL | Read |
|---|---|---|---|
| A1 | AN2867 Rev 10, PDF, copy hosted by Raltron | https://www.raltron.com/webproducts/technical/technical_notes/Oscillator-design-guide-for-STM8S-STM8A-and-STM32-microcontrollers-ST-MICRO-1.pdf | 2026-11-27 |
| A2 | AN2867 current PDF on st.com (fetch timed out, not read) | https://www.st.com/resource/en/application_note/an2867-oscillator-design-guide-for-stm8afals-and-stm32-microcontrollers-stmicroelectronics.pdf | not read |

## PCB design guidelines (A1 § 5.1)
- Keep stray capacitance and inductance low. High values can cause overtone or harmonic oscillation and slow start-up.
- Mount the crystal as close as possible to the MCU, so the tracks are short.
- Put a ground-connected guard ring around the crystal connections. Long tracks can act as antennas.
- Route fast signals away from the oscillator tracks and parts.
- Put a dedicated ground plane under the oscillator ("local ground plane, other layer" in Figure 10), joined to the MCU ground at the nearest MCU ground pin. A metal-can crystal case should not be tied to it.
- Use a conformal coating over the LSE crystal, its load caps and the OSC_IN / OSC_OUT tracks: leakage can stop start-up in humid conditions.
- The bad example in the note: no ground around the oscillator, tracks too long, unequal capacitances on the two sides, tracks coupling to each other, too many test points. Symmetric load caps are part of the guidance.

## What the note does not say
- No numeric maximum track length: only "short" and "as close as possible".
- No via rule (no ban, no maximum count) in the text. Figures 10-19 are drawings and were not read as text.
- No explicit rule about which layers other signals may use under the load caps, beyond the local ground plane underneath and "keep other signals away".
- No load-cap placement distance in mm.

## Gain margin rule (A1 § 3.4, § 4.2)
- If the MCU datasheet gives the oscillator transconductance gm: gain margin = gm / gm_crit must be above 5.
- If the datasheet gives gm_crit_max instead: the crystal's gm_crit must be below that value.
- gm_crit = 4 x ESR x (2 x pi x F)^2 x (C0 + CL)^2. With an external series resistor use ESR + R_ext.
