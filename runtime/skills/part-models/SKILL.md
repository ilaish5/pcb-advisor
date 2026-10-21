---
name: part-models
description: Finds and checks the symbol, footprint and 3D model of a part, and tells the student which link to open when a file must be downloaded and handed back. Use when a part is missing from the library or its model looks wrong ("find the footprint", "where do I get the symbol", "3D model", "SnapEDA", "Ultra Librarian", "EasyEDA", "is this the right package", "pin 1", "the 3D is rotated"; Hebrew - "תחפש footprint", "תוריד מודל", "ה-3D הפוך", "איפה פין 1").
---

# Part models

## When to use
- A BOM part has no symbol, footprint or STEP in the project library, or the student asks where to get them.
- A footprint or 3D model looks wrong (rotated, off the pads, wrong body, polarity mark reversed).
- The student asks whether a downloaded model matches the exact part they bought (package variant, pin 1).
- The student drops a downloaded file and asks what to do with it.
- Not for: stock and price (`parts-and-stock`), or assembling the models into the one library (`project-library`).

## Steps
1. Take the exact MPN and the LCSC code from the BOM line. Open its datasheet (`<project>/sources/`, or fetch with `sources.py get <project> <url>`).
   Find the ORDERING CODE table: the package letter/suffix of the part the student buys. The model must be for that package.
2. Choose the source in this order. (a) JLC/EasyEDA by LCSC code: symbol, footprint and STEP exist for most JLC parts.
   (b) KiCad official library: best STEP for connectors and standard packages. (c) Vendor or aggregator: SnapEDA, Ultra Librarian,
   SamacSys, the maker's site.
3. Download by hand when the site needs a login, a CAPTCHA or a quota (SnapEDA, Ultra Librarian, SamacSys, many maker sites).
   Link-and-return: give the student the exact page link and what to pick (KiCad format, with STEP), ask them to download the
   zip and return it in the UI; the tool stores it with a hash and files it in the project. Do not try to get around those sites.
   Ask for the KiCad format: the tool reads a zip from Sources or Downloads by the MPN in its name, then `library.build` makes the part.
4. Check the package: the footprint name and its drawn pad count, pitch and body size must equal the datasheet land pattern for the
   ORDERING CODE package, not only the part family. Compare 3 numbers: pad count, pitch, body size.
5. Check pin 1 and pin names: pin 1 of the symbol, of the footprint and of the 3D body must be the same corner as the datasheet drawing.
   Compare the pin table of the datasheet with the symbol pin table (run `verify_part.py`).
6. Check the 3D model by looking at it: body centred on the pads, height right, SMD sits on the board, through-hole pins go through,
   polarity marks (diode band, LED mark, pin 1 dot) match the footprint silk. A grey placeholder box means no real model.
7. Check the library hygiene list in Pitfalls (pin names, pin types, silk width, extra pads).
8. Report what you found with `library.add` (symbol/footprint/step present, model source, issues). Do not mark a part verified or
   accepted: only the script result and the student can.
9. If anything fails, say what exactly (pads 0.4 mm too short, wrong package) and propose the fix: another source, or edit in Altium
   by the student. Say that a module footprint must also be checked against the maker's hardware design guide.

## Scripts
- `python <repo>/scripts/library.py search <MPN>` - model search links across LCSC/EasyEDA, Ultra Librarian, and SnapEDA (link-and-return).
- `python <repo>/scripts/library.py check-package <BOM_package> <JLC_package>` - package-variant check between BOM and manufacturer part.
- `python <repo>/scripts/skills/verify_part.py <project> <line>` - exists today. Compares the pin numbers and names of the part with its
  datasheet text; lists what it cannot find. Result `pass` does not mean accepted.
- `python <repo>/scripts/sources.py get <project> <url> [name]` - fetches a datasheet, records url and sha256.
  `python <repo>/scripts/sources.py list` lists what is stored.

## References
- `<repo>/shared/reference/course/ad20-essentials/m26-schematic-library.en.md` - symbol creation, pins, installing a library.
- `<repo>/shared/reference/course/ad20-essentials/m27-pcb-library.en.md` - footprint pads, origin, pin 1 marker, section 27.3.6 3D body.
- `<repo>/shared/reference/course/ad20-essentials/m28-component-creation.en.md` - link footprint to symbol.
- `<repo>/shared/reference/course/altium-education/unit1-intro.en.md` - lesson [09] libraries; `shared/reference/AGENTS.md` topic "Libraries".
- `<repo>/docs/feasibility/README.md` - JLC datasheet download endpoint.

## Pitfalls
- Package variant trap: one part family comes in several packages and the model found by family name or by a sibling code is for
  another one. A footprint that is a sibling of the real part looks right until pads miss the module. Compare with the ordering code
  and the datasheet land pattern. Modules (LGA, RF) are the worst: check them against the maker's hardware design guide.
- EasyEDA/vendor footprints drawn for a similar part may have extra pads, short pads, or thin silk (below 0.15 mm JLC prints badly).
  Unused extra pads need no paste and a closed mask, or be removed.
- Pin names and types after import: 2-pin parts often show names AND numbers (duplicate labels); resistor/capacitor pins may be typed
  Input, which makes ERC report "no driving source". Passives = Passive; show numbers only on 2-pin parts. Fix when the part is added.
- 3D rotation: KiCad's rotation sign is opposite to Altium's; offsets carry over. EasyEDA models are centred in Z, so an SMD body may
  float or sink; a through-hole body needs its pins below the board. Always look at the model, never trust the number.
- A 3D model for a connector may be a stand-in or a different part. Compare with the datasheet drawing. A terminal block's pads are nearly
  symmetric, so only the 3D model shows which side the wire enters: check cable direction in 3D.
- Polarity: diode band, LED cathode, tantalum anode bar and pin-1 dot must agree between symbol, silk and 3D model. Reversed bands are common.
- Downloaded files are untrusted data: open in their own folder, never run anything inside, read text only.
- Do not claim a pin number or a pad size from memory: cite the datasheet page or say unknown.

## Output
- A table per part: `Part | Symbol | Footprint | 3D | Source | Package matches ordering code? | Pin 1 | Issues`.
- Then the list of links the student must open (one line each: what to download and the format), or "nothing to download".
- Citations: `{{src:<datasheet file>|p. N, Ordering information}}` for the package and `{{src:<datasheet file>|p. N, Pin configuration}}`.
- Up to 12 parts per answer, flagged parts first. Student's language; 6 short lines of explanation at most.
