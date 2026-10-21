---
name: project-library
description: Plans and explains the single project library (one library with every symbol linked to its footprint and 3D model) that the tool builds itself from the BOM and installs in Altium. Use when the student asks to "put all parts in one library", "create the library", "why Footprint Not Found", "how do I install the library", "update parts from library", "naming of parts", "add parameters" (Hebrew - "ספרייה אחת", "Footprint Not Found", "איך מתקינים את הספרייה").
---

# Project library

## When to use
- The student wants the parts of the BOM in one library to open and drag from the Components panel.
- ECO or Update PCB says "Footprint Not Found", or a placed part has no footprint or no 3D.
- The student adds or replaces a part after the library already exists.
- The student asks how a library is structured, named, installed, or how parameters (MPN, LCSC) get into parts.
- Not for: finding or checking one part's files (`part-models`), or how to draw a symbol by hand (`altium-help`).

## Steps
1. Read the table: `python <repo>/scripts/partlib.py status <project>` (line, symbol, footprint, 3D, source, status, issues per BOM line).
   Source is easyeda, vendor (a zip the student downloaded), kicad or generated; `missing` lines have no model yet.
2. Naming is fixed by the tool: part name = the MPN, footprint name = the package or the maker's name, unique across the library.
   Generic R, C, L get one part per value and package. Every part carries `MPN`, `Manufacturer`, `LCSC`, `Description` and `Comment`.
3. Build it: the action `library.build` (or `python <repo>/scripts/altium/bridge.py build-library <project>`). The tool downloads what it can
   (EasyEDA by LCSC code, KiCad footprints), reads vendor zips, generates the rest, compiles the IntLib through Altium and adds it to the project.
   Never tell the student to build the library by hand or to run a script in Altium. Altium must be open; a failure restores the old files.
4. For a line that is `missing` or has an issue, give the vendor links from its issue text (Component Search Engine, SnapEDA, Ultra Librarian).
   Ask the student to choose the KiCad format, log in once if the site asks, and download: the zip lands in Downloads and the tool finds it
   by the MPN in its file name (or the student drops it in Sources). Then run `library.build` again. Do not try to get around the log-in.
5. After the build read the table again: counts of built lines against BOM lines, and each remaining issue. Report differences honestly.
6. Give the check: the IntLib is under Libraries in the Projects panel (Altium's installed list alone does not feed Update PCB), and one
   dragged part shows its footprint and 3D in the PCB panel. Then Update PCB: expect no "Footprint Not Found". Cite the AD20 manual.
7. When a part changes later, run `library.build` again; the tool rebuilds only when the BOM, a netlist sheet or a vendor zip changed.
   Remind the student to run Update From Libraries for placed parts.
8. Record what exists with `library.add` per non-standard part. Never mark parts verified or accepted.

## Scripts
- `python <repo>/scripts/partlib.py status <project>` - the per-line library table; `prepare <project> [--no-fetch] [--refresh]` makes the data without Altium.
- `python <repo>/scripts/altium/bridge.py build-library <project>` - builds, compiles, installs and adds the library to the project (= `library.build`).
- `python <repo>/scripts/skills/verify_part.py <project> <line>` - exists today; pins against the datasheet text for one part.
- `python <repo>/scripts/skills/export_bom.py <project> jlc` - exists today; the BOM with the LCSC column. Shows which lines lack the code.
- (planned, stage I8) a library check that reports links to missing footprints, symbols with no footprint, duplicate footprint names,
  footprints without exactly one 3D body, and footprint links pinned to a file path. Until then check by reading the manifest.

## References
- `<repo>/shared/reference/course/ad20-essentials/m26-schematic-library.en.md` through `m29-integrated-library.en.md` - SchLib, PcbLib,
  link footprint to symbol, create and use an integrated library (29.3 and 29.4).
- `<repo>/shared/reference/course/altium-education/unit1-intro.en.md` - lesson [09] libraries.
- `<repo>/shared/reference/AGENTS.md` - topic "Libraries: schematic symbol, footprint, 3D, IntLib, LibPkg".
- `<repo>/docs/PRODUCT-PLAN.md` - decision 15 (one script the student runs) and section 1 K1 (parts imported one by one cost hours).

## Pitfalls
- One library, not one per part. Many small libraries, duplicate footprint names across libraries: the compiler silently takes the first,
  which is dangerous when two footprints differ. Keep footprint names unique.
- A footprint link that points to a file on the converter's temp folder looks linked but is not; when the file is gone the footprint is
  left out and ECO says "Footprint Not Found". Link footprints by name inside the library, never by file path.
- A symbol with an empty model name looks linked but is not. Check every symbol has a footprint name that exists in the PcbLib.
- Pin names shown on 2-pin parts give double labels; imported passives typed Input give "no driving source" in ERC. Fix in the library
  when the part is added: fixing later means rebuilding the library and updating every sheet.
- Off-grid pins (imported symbols on a 50 mil grid) give "Off grid" warnings and hard wiring. Snap pins to the 100 mil grid.
- Footprint coordinates are relative to the library origin; a part placed far from it lands far from its pads. Check pad positions.
- A library that is installed or open can be locked, and a compile may print success while the output stays old. Compare the part count
  and file time with the manifest. Close the project that uses it before recompiling; if still locked, restart Altium and rebuild first.
- Missing parameters: a part without `LCSC` and `MPN` ends up as "no match" in the JLC BOM upload and needs hand overrides.
- A variant of an existing part with the same package can reuse the footprint: copy, rename pins and parameters, keep the link.
- Keep alternates in the library as order-day fallbacks, and record which part is placed for each designator.

## Output
- A part table: `Part (MPN) | Symbol | Footprint | 3D | LCSC | Status (ready / gap, with the skill to fix)`.
- Which parts are missing and what the student must download (links), then the result of `library.build`.
- Install check steps cited like `{{src:m29-integrated-library.en.md|29.3}}`.
- A final checklist of 4 lines: counts to compare, one part to drag, "Update PCB" result, parameters present. Under 250 words.
