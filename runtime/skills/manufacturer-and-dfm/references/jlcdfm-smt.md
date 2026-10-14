# JLCDFM SMT assembly report (jlcdfm.com)

## What SMT DFM checks
JLCDFM assembly analysis checks the Pick and Place (CPL) data and Bill of Materials (BOM) against component package
models and PCB land patterns:
- **Pad/footprint vs part leads**: pin outer/inner edge overhang, pin without pad, lead area overlapping pad, pad size
  vs terminal dimensions.
- **Component spacing and clearance**: courtyard-to-courtyard clearance, component collision, body overlaps.
- **Polarity and pin 1 orientation**: pin 1 indicator match, diode and polarized capacitor orientation, rotation angle.
- **Board edge clearances**: tall parts near rails/conveyor edges (requires >= 1.5–3 mm clearance for assembly tooling).
- **Fiducial marks**: presence of optical fiducial marks on panel and surface-mount layers.
- **Solder paste and stencil**: stencil apertures vs pad geometry, excessive or starved solder paste coverage.
- **BOM vs CPL mismatch**: missing designators, unplaced components, package variant mismatch with LCSC parts.

## Common findings and fixes
- **"Lead area overlapping pad" or "Pin outer edge" (many items)**: Usually JLC's internal 3D/lead model is slightly
  offset or rotated relative to the Altium footprint library. If pin 1 and overall pad dimensions match the manufacturer
  datasheet, mark as `model` artifact. Do not alter standard footprints to fit inaccurate 3D models.
- **Component collision (Danger)**: Real courtyard overlap between adjacent parts or tall electrolytic caps. Check 3D
  view in Altium. If parts physically touch, adjust placement and spacing.
- **Rotation mismatch (90° or 180°)**: JLC component orientation in Pick and Place files often differs from standard IPC
  zero-orientation. Fix in the CPL export rotation offset table, never by rotating the schematic symbol or footprint.
- **Pin 1 or diode polarity reversed**: Verify cathode mark or pin 1 dot against both silkscreen overlay and component
  datasheet. Correct orientation in CPL.
- **Component too close to board edge (Warning)**: Parts hanging over v-score cut lines or break-off tabs may be sheared
  during de-panelization. Pull back components at least 1 mm from routed edges and 2 mm from v-grooves.
- **Unmatched BOM line or missing CPL coordinate**: Ensure every fitted SMT line has valid mid-point coordinates (Mid X,
  Mid Y in mm), surface layer (Top/Bottom), and matching LCSC Part #.

## How to triage
Use the triage table for each flagged SMT finding:
- `Section`: `SMT DFM>Component assembly analysis`
- `Check`: Specific check name from JLCDFM report (e.g., "Pin outer edge", "Component collision", "Pad spacing")
- `Level`: Danger, Warning, or Info based on JLC severity
- `Verdict`:
  - `real`: True clearance violation, physical collision, or unplaced component requiring layout/BOM fix.
  - `model`: 3D model misorientation, package lead simulation artifact, or nominal vendor model discrepancy.
  - `by design`: Intended edge connector protrusion, intentional fiducial arrangement, or custom pad geometry.
  - `unknown`: Needs further datasheet or 3D inspection before placement freeze.
- `Fix`: Specify actionable resolution (e.g., "Adjust CPL rotation by +90 deg", "Move C12 0.5mm away from edge").
- `Evidence`: Cite slice image filename, component designator, or manufacturer datasheet package drawing.
