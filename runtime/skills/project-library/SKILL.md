---
name: project-library
description: Plans and explains the single project library (one library with every symbol linked to its footprint and 3D model) that one Altium script, run by the student, builds from the checked part files. Use when the student asks to "put all parts in one library", "create the library", "why Footprint Not Found", "how do I install the library", "update parts from library", "naming of parts", "add parameters" (Hebrew - "ספרייה אחת", "Footprint Not Found", "איך מתקינים את הספרייה").
---

# Project library

## When to use
- The student wants the parts of the BOM in one library to open and drag from the Components panel.
- ECO or Update PCB says "Footprint Not Found", or a placed part has no footprint or no 3D.
- The student adds or replaces a part after the library already exists.
- The student asks how a library is structured, named, installed, or how parameters (MPN, LCSC) get into parts.
- Not for: finding or checking one part's files (`part-models`), or how to draw a symbol by hand (`altium-help`).

## Steps
1. List the BOM parts and, for each, whether `part-models` has a checked symbol, footprint and STEP. Build only from parts that passed
   the checks there. List the gaps first and send the student back to `part-models` for them.
2. Fix the naming before building. Library part name = the MPN (exact, no spaces). Footprint name = package plus the maker's name, unique
   across the library. Generic R, C, L get one part per value and package, with the value in the description.
3. Fix the parameters every part carries: `MPN`, `Manufacturer`, `LCSC` (the C-number), `Description` (value, tolerance, rating; the LCSC
   code also in the Description), `Comment` (what the sheet shows). The JLC BOM later takes the LCSC code from these.
4. Check pin names and types and footprint links in the part files (see Pitfalls) before the build.
5. Generate the library build script and the manifest (Scripts). The tool writes them; it does not run anything in Altium.
6. Give the student the exact steps to run the script in Altium (what to open, which procedure to run) and where the result is.
   Use the AD20 manual for the menu names, and cite them. Say clearly: this step is done by the student.
7. Give the install check: after the build, the library is in Components panel > Installed Libraries, and one dragged part shows its
   footprint and 3D in the PCB panel. Then Update PCB: expect no "Footprint Not Found".
8. After the student returns the result (or a screenshot), compare the count of parts and footprints with the manifest; report differences.
9. When a part changes later, regenerate only that part, rebuild, and remind the student to run Update From Libraries for placed parts.
10. Record the library state with `library.add` per non-standard part (what exists, source, issues). Never mark parts verified.

## Scripts
- `python <repo>/scripts/library.py build-script <project> [--out exports]` - writes the Altium build script and README to compile an IntLib.
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
- The student steps as a numbered list (3-8 lines) to run the build and install, with `{{src:m29-integrated-library.en.md|29.3}}` style citations.
- A final checklist of 4 lines: counts to compare, one part to drag, "Update PCB" result, parameters present. Under 250 words.
