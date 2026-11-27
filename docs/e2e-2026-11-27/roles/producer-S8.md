# Producer – Stage 8 (JLC upload and DFM read)

## Video highlights
- S8-03-jlc-parsed-4layer-45x60.jpg | JLC parses the Gerber zip: 4 layers, 45x60 mm, both sides rendered.
- S8-09-jlc-gerber-viewer-requires-signin-STOP.jpg | JLC's Gerber Viewer wants a login; the producer stops there, nothing signed in.
- S8-07-jlc-default-stack-table.jpg | JLC's default 4-layer stack: the file carries none, the order form decides.
- S8-08-jlc-pcba-toggle-next-stops-here.jpg | Assembly step only continues with NEXT, which would create a cart entry; stopped.

## What I did (JLC: upload and read only; no cart, no order, no payment, no sign-in)
Browser: Windows "Browser 2" (deviceId 26a71dec-…, the one the orchestrator named; it is listed as "Browser 2", not "Browser 1"), my own new tab,
closed at the end. Not signed in to JLC at any time (header showed "Sign In" throughout). File uploaded with `file_upload`:
`projects/Final-E2E-4L/exports/Final-E2E-4L_gerbers.zip` (53,838 bytes, 14 files: G1 G2 GBL GBO GBP GBS GM1 GTL GTO GTP GTS + 3 drill files).

## JLC's answer (what I saw)
- Parse: **"Detected 4 layer board of 45x60mm (1.772x2.362 inches)"**, Layers set to 4, Dimensions 60 * 45, top and bottom renders with the four 3.2 mm corner holes (S8-03).
  Matches the outline file (GM1: 2.3622 x 1.7717 in).
- Price (anonymous, 5 pcs, defaults): **$8.00 web price** ("Special Offer"), build time 3-4 days $0, 2-3 days +$66.20, shipping estimate $25.99 UPS Express Saver, weight 0.17 kg (S8-03, S8-04).
  Defaults JLC filled: FR-4 TG135, 1.6 mm, green, white silk, HASL (with lead), 1 oz outer / 0.5 oz inner, min via 0.3 mm/(0.4/0.45), Flying Probe test.
- **DFM / analysis result: none was shown.** The quote page raised no warning, no error, no "please confirm" message after the parse. The one JLC screen that would show
  an analysis, the **Gerber Viewer, redirected to the sign-in page** (S8-09). Per the rule I stopped there and did not sign in (the browser had pre-filled the form; I did not touch it).
  I did not go to jlcdfm.com. So **JLC's own DFM verdict on this board is UNKNOWN**; what follows under "my offline analysis" is mine, not JLC's.
- Stack-up (lecturer P2): with "Specify Stackup: Yes" JLC offers JLC04161H-7628 and 15 other codes (S8-06). The default "No requirement" 4-layer stack shown by JLC:
  Cu 0.035 / 7628 prepreg 0.2104 / L2 Cu 0.0152 / core 1.065 / L3 Cu 0.0152 / 7628 prepreg 0.2104 / Cu 0.035 mm (S8-07). The Gerbers carry no stack-up; the form decides.
  The project's `notes.md:41` says "select JLC04161H-7628" (good: P2's wording is satisfied in notes), but the order manifest, `README.md` and the exports do not repeat it. I did not select it (that is order configuration; read-only run).
- Via covering: on the 4-layer form JLC's default is **Plugged and "Tented" is greyed out** (S8-05). I suspected our untented-via file caused it, then tested: a fresh quote page with no upload and 4 layers
  shows the same (S8-11); with 2 layers Tented is the default and enabled (S8-10). So that is **JLC's own 4-layer behaviour, not a reaction to our file**. What JLC does with via openings that the Gerber already
  has (untented in the file) under "Plugged" I could not see without the viewer: **unverified**.
- Assembly: with "PCB Assembly" on, the form shows top-side Economic PCBA and a **NEXT** button (S8-08). NEXT is the step that saves the PCB into the cart and goes to the BOM/CPL upload page (and an account is needed),
  so I did not press it and switched the toggle back off. **JLC's BOM/CPL matching (parts found, rotations, positions) was therefore NOT tested.** The system's own `scripts/jlc_live.py` documents the same login wall.

## BOM / CPL checked offline against JLC's assembly format (not by JLC)
- `Final-E2E-4L_BOM_jlc.csv`: header `Comment, Designator, Footprint, LCSC Part #` is the JLC format. 31 lines, 55 designators, **every line has an LCSC number**, no blank. One benign oddity: C10 and C11 are two lines with the same part C19666 (JLC accepts it; just untidy).
- `Final-E2E-4L_cpl.csv`: header `Designator, Mid X, Mid Y, Layer, Rotation` is the JLC format, values with "mm" suffix are accepted by JLC. 55 rows, all Top. **The 55 designators equal the BOM's 55 exactly** (none missing either way).
  Positions X 30.0-75.56 mm, Y 27.0-62.0 mm sit inside the outline (25.4-85.4, 25.4-70.4) and use the same absolute origin as the Gerbers (Board_Origin 0|0). Rotations are raw Altium values (0/90/180/270).
  **Unverified:** JLC corrects rotation per footprint from its own library, and only its assembly preview shows whether U1, U4, U5, J1, J2, D1 and the crystals come out right. The L3 question (J1/J2 origin) cannot be settled without that preview.
- Stock (from the system's own supply data in `bom.json`, checked 2026-11-27 02:14, so about five hours old, not re-checked now): all in stock; the lowest is Y1 C479202 with 302 pcs. 16 of 31 lines are "Extended" parts per that data (JLC charges a feeder fee per distinct Extended part; I did not see JLC's number). The student's 8 LCSC codes (K4) match the codes in `bom.json`; I did not re-query LCSC.

## My offline analysis of the Gerbers (own script, mine not JLC's; approximate, rectangles for pads)
- Holes: 157 plated vias all 0.305 mm; NPTH 2 x 0.60, 2 x 1.00, 4 x 3.2 mm; 4 plated slots 0.80 mm (`SlotHoles-Plated`). Counts and diameters agree with what JLC's parse accepted. Via 0.305 mm is within the 0.3 mm option JLC offers (0.3/(0.4/0.45)).
- **Vias are untented in the file: all 157 of 157 have a 0.71 mm round mask opening at their centre, on top and on bottom** (mask files are negative polarity, so a flash is an opening). This matches Alti's `ISTENTINGTOP=FALSE` and contradicts `notes.md:43` ("Tent vias").
- **Mask webs under 0.10 mm (top):** 112 via-to-pad pairs closer than 0.1 mm, of which **16 have the via opening overlapping a pad opening** (a bare via touching pad copper: solder can wick into the via on HASL). Smallest separated via-pad webs 0.024, 0.038, 0.038, 0.053 mm. Pad-to-pad: four at 0.013 mm (probably adjacent pads of one part that Altium keeps as one opening, or my rectangle approximation; **unverified**) and four at 0.097-0.099 mm (J1, matches the DRC's 0.098). Bottom: one via-pad pair at 0.094 mm. I did not reproduce U1's 0.054 mm dam (U1's pads are obround, my script approximates them); it comes from the Altium DRC in the manifest.
- Not measured: inner pour to NPTH (0.16 mm per Alti, JLC wants 0.2 mm or more), J3 pads to edge (0.30 mm per Alti). Both stay Alti's numbers.

## Lecturer conditions P2 / P3 mapped: did the system catch it?
| Item | JLC showed (anonymous) | Where the system caught it | Verdict |
|---|---|---|---|
| Stack-up is Altium default, order must select JLC04161H-7628 | Option exists; default is "No requirement" (S8-06/07); nothing warns | `notes.md:41` says so; not in the order manifest, README, or on the app's order page as far as the manifest shows | Caught in a note only |
| Untented vias next to pads | No verdict (viewer needs login) | Altium DRC "Minimum Solder Mask Sliver" 252 (manifest `board_check.drc`); the app first blamed the footprints (S6), corrected in round 2; no local tenting check anywhere (`jlc_preset.py` has the sliver rule only; the Rules page cannot set tenting) | Partly: counted, never triaged, cause not removable in the tool |
| U1 mask dam 0.054 mm | No verdict | Inside the 252 sliver violations; the preset's rule is 6 mil (0.152 mm) against JLC's 0.10 mm floor, so it fires but cannot tell "JLC fails this" from "JLC accepts this" | Counted, not classified |
| J1 dam 0.098 mm | No verdict | Same 252 count | Counted, not classified |
| Inner pour 0.16 mm from NPTH | No verdict | **Not caught.** The PlaneClearance rule was skipped by the rule importer (S6 round 2, `rules.json` keeps `M3_Holes_Plane_Gap` kind PlaneClearance) and nothing else measures pour-to-hole | **Missed** |
| J3 pads 0.30 mm from the edge | No verdict | Manifest DRC lists "Board Clearance Constraint (Gap=0mil)" with 7 violations; the rule is 0 mm, not JLC's edge distance | Partly |
| Minimum Annular Ring (IsPad 8 mil) | No verdict | 4 violations in the manifest DRC | Counted |
| Hole counts, sizes, outline, layer count vs the PcbDoc | JLC's parse agrees (4 layers, 45x60) | `gerber_check.py`: hole count/diameters, outline size, layer count | **Caught and right** |

## Findings (the SYSTEM)
- [WRONG] `notes.md:43` says "Tent vias" while the exported Gerbers have all 157 vias open on both sides: evidence `GTS`/`GBS` flashes of 0.028 in at every one of the 157 drill hits, DRC 252 slivers. Why it matters: the student is told one thing and the factory gets the other; on HASL the 16 via openings that overlap pad openings can wick solder. Generic cause: tenting is never written to the board (preset and Extra rules cannot set it), the note is a plan, not a measurement. Fix direction: a local Gerber check ("N vias open on top/bottom") in the pre-order page, and the tenting flag in the importer.
- [WRONG] The pre-order page cannot see mask webs or hole-to-pour distance: nothing in `gerber_check.py`, `outputs_check.py` or `order_check.py` looks at mask flashes, so the two numbers JLC cares most about here (dams under 0.10 mm, copper to NPTH under 0.2 mm) reach the factory unjudged. `scripts/viacheck.py` in my scratchpad did the first in about 80 lines from the Gerbers (`C:\Users\ilaish\AppData\Local\Temp\claude\efecd7ce72b47997\ec93eb84-a4e2-4fb2-bc29-d89ebfcd1838\scratchpad\viacheck.py`), so it is cheap to add.
- [FRICTION] The only JLC verdict the system knows how to read lives behind a JLC login: `dfm.py` ingests a JLCDFM **report PDF** the student exports from their own account (`projects/Final-E2E-4L/checks/` does not exist, so no report was ever ingested for this board), and JLC's Gerber Viewer sent me to sign-in. Anonymous, JLC gives only the parse and the price. The system's DFM page should say so in one line ("JLC shows warnings only after sign-in: export the JLCDFM report and drop it here") and offer its own offline checks as the fallback.
- [FRICTION] The stack-up instruction is in `notes.md` only. The order manifest and the outputs page do not say "select JLC04161H-7628 at order time"; JLC's default is "No requirement", so a student following the page ends with JLC's own stack. One line in the manifest (`order_notes`) would carry P2 to the moment of ordering.
- [FRICTION] Assembly cannot be checked without creating a cart entry: JLC's NEXT button saves to the cart and needs an account. The system's BOM and CPL pass every offline check I could do (format, 55 = 55 designators, all LCSC codes present), but rotation and origin are only visible in JLC's assembly preview. The page should tell the student to look at that preview for exactly the footprints that need rotation correction, instead of implying the CPL is final.
- [COSMETIC] BOM has C10 and C11 as two lines for the same C19666. Merging them is harmless and shortens the BOM.
- Good: the Gerber zip is clean for JLC's parser, 4 layers and the exact 45 x 60 mm were detected, BOM and CPL headers are JLC's own, designator sets are identical, nothing is missing from the zip, and the hole files agree with the PcbDoc.

## Not done / unverified, in one place
JLC's DFM report; the Gerber Viewer; BOM/CPL matching and rotation in JLC; whether JLC plugs or leaves the open vias under "Plugged"; whether JLC applies the 0.054/0.098 mm dams as warnings; inner pour to NPTH (0.16 mm, Alti's number); LCSC stock now (data is five hours old); any claim about price beyond the anonymous $8.00 / $25.99 (assembly price not shown). Nothing was added to a cart, ordered, or paid. Screens: `screens/S8-01` to `S8-11`.
