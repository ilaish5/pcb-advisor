---
name: parts-and-stock
description: Checks every BOM line against JLC as it is entered and returns a table of stock, price at quantity, Basic/Extended/Preferred, assembly caveats, cost per board, a risk flag and in-stock alternatives. Use when the student adds or changes a part or asks "is it in stock", "how much does the BOM cost", "Basic or Extended", "why Standard only", "find a cheaper or in-stock replacement", "is this part obsolete" (Hebrew - "יש במלאי?", "כמה עולה הלוח", "תמצא חלופה").
---

# Parts and stock

## When to use
- A BOM line is added, or its MPN or value is edited: the tool checks it in the background. Read `stock_check` of the line in
  CURRENT STATE: `missing` or `stale` (over 24 h) run the script; `checking` wait; `fresh` use the stored numbers with their time.
- The student asks for stock, price, cost per board, Basic/Extended, or a cheaper or in-stock alternative.
- Before the schematic is called done and before the BOM is exported.
- The student asks if a part is obsolete: answer only from JLC signals and say lifecycle is unknown.
- Not for: symbol, footprint or 3D files (`part-models`), or the pre-upload BOM/CPL check (`manufacturer-and-dfm`).

## Steps
1. List the BOM lines to check: only the lines the student changed, or all lines for a full check. Read the line as entered (MPN,
   value, package, quantity per board). Ask the board count if unknown; default to the student's planned quantity.
2. Run the stock check (Scripts) only for lines whose `stock_check` is `missing` or `stale`; a `fresh` one already has a script
   result with its `checked_at`. Never give stock or price from memory, and never delay the answer for a check that is `checking`.
3. For each line, confirm the JLC hit is the SAME part: model name equals the MPN as entered (`exact`), and the package matches.
   A search hit that is a sibling (other suffix, other package, other maker) is not a match: mark the line "no exact match".
4. Read the type: Basic (no fee), Preferred Extended (no fee), Extended (fixed fee per part type). Count Extended types.
5. Compute cost per board = unit price at the quantity bought x quantity per board. Basic parts are bought exactly; others may have a
   minimum purchase. Add the feeder fee only for Extended types. Show the total and the Extended count.
6. Set the risk flag (see Pitfalls): out of stock, low stock (stock below need plus a margin), no exact match, Extended with a Basic
   option in the same package, high cost share, possible Standard-only assembly.
7. For each flagged line search alternatives: same package and electrical specs, in stock, preferably Basic. Compare the key
   specs against the datasheet of both parts before proposing. Give at most 2 alternatives per line with the reason.
8. Propose changes with `bom.propose` (reason + sources). Never change the BOM yourself; the student approves.
9. For "Standard only" or any assembly-service question say what is known: the scripts do not return that field. Tell the student where
   to look on the JLC parts or BOM-upload page, and mark it "unknown until checked".
10. If the JLC query fails, say so and store nothing. A line that was not checked must never look like "no stock".
11. Design vs ordering, by footprint. While designing, a line is fixed by value + package + pins. At ordering (action
    `order.check`) a line out of stock or short may take another MPN / LCSC code FREELY when the alternative has the
    same footprint and function (identical land pattern, and same pin names, or for a plain passive the same value, kind and ratings;
    its `match` is "same"): propose `bom.propose` with `changes`
    `{mpn, lcsc, manufacturer, footprint_lock}` and the reason "order-only swap: same footprint"; the library and the board
    stay as they are. Match "different" or "unknown" is a design change (library rebuild + PCB update): propose it without a
    `footprint_lock`, and say it changes the board. Never claim "same package" means the same footprint.

## Scripts
- `python <repo>/scripts/skills/check_availability.py <project> [LINE ...]` - Searches JLC by MPN, returns stock, unit price at 10 pcs,
  LCSC code, model name, library type, package, datasheet URL, `exact`, and `checked_at`; writes the supply log.
- `python <repo>/scripts/jlc.py [search <kw> | part <mpn> | alternatives <kw> [pkg]]` - JLC client with disk cache. Searches parts, best MPN match,
  or in-stock alternatives with the same package.
- `python <repo>/scripts/skills/compare_prices.py <project>` - Cost per board from the stored checks (JLC row only).

## References
- `<repo>/docs/feasibility/README.md` - what the JLC endpoint returns (stock, library type, prices, datasheet link) and what it lacks.
- `<repo>/docs/PRODUCT-PLAN.md` - section 1 K2 (stock found too late), section 7 decisions 2, 8, 19 (stock in table, obsolete signals).
- `<repo>/shared/reference/course/altium-education/unit2-schematics-libraries.en.md` - [15]-[19] and [22] choosing parts, MOQ, supply chain.
- `<repo>/shared/reference/jlc/assembly-capabilities.en.md` - Basic/Preferred/Extended fees (Economic vs Standard), Standard-only limits, sourcing channels.

## Pitfalls
- Stock changes daily. A number without its query time is worthless; stale numbers (earlier session) must be re-run before BOM export.
- A name search returns lookalikes: other suffix (tape vs tube, "A" version), other package, other maker. Check model, package and
  the datasheet ordering code. A different suffix can change behaviour; read what the suffix means before accepting it.
- Basic vs Extended is a cost decision. Each Extended type adds a fixed fee, so 10 Extended types are expensive on a 2-board run.
  If the same value exists as Basic in the same package, say so. A wanted value or color may exist only as Extended (for example some LED colors).
- Do not buy more capacity than the requirement needs. A large memory or a big module can cost many times a small one with the
  same pads. Re-read the requirement before accepting an expensive line.
- Modules (LGA, castellated), fine-pitch and odd parts may be assembled only in the Standard service, which is dearer and rules out
  the Economic one. The tool cannot see it: warn early, let the student confirm on the JLC page.
- Through-hole connectors and terminals often are not stocked for assembly; flag every THT line.
- "Obsolete": JLC has no lifecycle field. Stock 0, low stock or "cannot buy" are signals only; a dead part with stock is not caught.
  Say that lifecycle is unknown, never "active".
- Low stock: flag when stock is below the need for all boards plus a margin (use need + 10 as the minimum margin), not only at 0.
- A suffix chosen for a corner case (for example a variant with a different reset or watchdog behaviour): check whether the circuit
  can reach that case before paying for or avoiding the variant.
- Put the LCSC code in the part description/BOM; a line without it fails the JLC BOM matching later.

## Output
- One table, columns: `Line | MPN as entered | LCSC | Type | Stock | Unit price @qty | Cost/board | Risk | Alternative (LCSC, reason)`.
- Under it: total parts cost, Extended type count and fee, boards assumed, and the lines needing a student check (Standard-only unknown).
- Cite the data once: `{{src:JLC query "<keyword>" <ISO time>}}`, or the supply-log entry with its `checked_at`.
- At most 15 rows shown; if more, show flagged lines first and say how many are fine. Student's language; part names stay in English.
