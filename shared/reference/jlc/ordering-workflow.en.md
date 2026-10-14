# Ordering at JLCPCB: bare boards plus assembly, step by step

> Source: JLCPCB help-center ordering articles and the PCBA viewer page in the table below, all read 2026-10-14. Condensed to the steps, options, messages and holds; screenshots not reproduced. The site changes its wording often: when a button name differs, follow the meaning. The advisor never orders, logs in or saves to cart for the student (runtime/AGENTS.md); this file is for guiding them.

Covers: preparing, the bare-board order, the options that matter, adding assembly (BOM/CPL upload, part matching, placement review and
rotation fixes), payment and review, engineering questions and holds, file replacement, lead times, reorders, tips. Capabilities and fees:
`pcb-capabilities.en.md`, `assembly-capabilities.en.md`. Formats: `files-and-formats.en.md`. JLCDFM: `jlcdfm.en.md`.

## Sources
All read 2026-10-14. "Page date" is the "Last updated" stamp on the page.

| ID | Page | URL | Page date |
|---|---|---|---|
| O1 | How do I place a PCB order? | https://jlcpcb.com/help/article/how-do-i-place-an-order | 2026-09-09 |
| O2 | How do I place a PCBA order? | https://jlcpcb.com/help/article/how-do-i-place-a-pcba-order | 2026-09-09 |
| O3 | Ordering Instructions for PCB Manufacturing | https://jlcpcb.com/help/article/instructions-for-ordering | 2026-09-09 |
| O4 | How to confirm the production file? | https://jlcpcb.com/help/article/how-to-confirm-the-production-file | 2026-09-09 |
| O5 | PCBA Review Before Payment Service | https://jlcpcb.com/help/article/review-before-payment-service-for-pcba-orders | 2026-09-23 |
| O6 | PCB Assembly FAQ (Part 2) | https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2 | 2026-09-09 |
| O7 | Component Matching Guidelines for PCBA Orders | https://jlcpcb.com/help/article/component-matching-guidelines-for-pcba-orders | 2026-09-09 |
| O8 | Common BOM / CPL Matching Issues and Explanations | https://jlcpcb.com/help/article/common-bom-and-cpl-matching-issues-and-explanations | 2026-09-09 |
| O9 | JLCPCB PCBA Viewer (order-time placement and DFM view) | https://jlcpcb.com/smt/dfm-result | none shown |
| O10 | SMT Service Lead Time Overview | https://jlcpcb.com/help/article/smt-service-lead-time-overview | 2026-09-09 |
| O11 | What is the build time? | https://jlcpcb.com/help/article/what-is-the-build-time | 2026-09-09 |
| O12 | PCB Fabrication Services and Production Time | https://jlcpcb.com/help/article/pcb-fabrication-services-and-production-time | 2026-09-09 |
| O13 | How to Set up Shortage Preference? | https://jlcpcb.com/help/article/shortage-preference-guide | 2026-09-09 |
| O14 | PCBA Order File Replacement Service Guide | https://jlcpcb.com/help/article/pcba-order-file-replacement-service-guide | 2026-09-09 |
| O15 | SMT Reorder Process Overview | https://jlcpcb.com/help/article/smt-reorder-process-overview | 2026-09-09 |
| O16 | How to mark on PCB? | https://jlcpcb.com/help/article/how-to-mark-on-pcb | 2026-05-22 |
| O17 | PCB Assembly FAQs | https://jlcpcb.com/help/article/pcb-assembly-faqs | 2026-09-09 |
| O18 | PCB Assembly Cost: What Does the Price Include? | https://jlcpcb.com/help/article/pcb-assembly-price | 2026-09-09 |
| O19 | How do I order a panel? | https://jlcpcb.com/help/article/how-do-i-order-a-panel | 2026-09-09 |
| O20 | How to order multiple different PCBs together? | https://jlcpcb.com/help/article/how-to-order-multiple-different-pcbs-together | 2026-09-09 |
| O21 | Panelizing your PCB for Assembly | https://jlcpcb.com/help/article/panelizing-your-pcb-for-assembly | 2026-09-09 |
| O22 | In what cases will there be charged extra? | https://jlcpcb.com/help/article/in-what-cases-will-there-be-charged-extra | 2026-09-09 |
| O23 | How to Generate Gerber Files in Altium Designer 26 | https://jlcpcb.com/help/article/how-to-export-altium-pcb-to-gerber-files | 2026-09-28 |
| O24 | PCB Assembly Capabilities | https://jlcpcb.com/capabilities/pcb-assembly-capabilities | none shown |

## Before uploading
- Design rules set to JLC's capabilities, DRC clean, every copper, silk and mask object inside the outline [O23].
- Run the free online DFM tool (JLCDFM) first; check that every selected part's package matches its footprint, the most common cause of
  engineering holds [O10].

## Bare-board order [O1, O20]
1. Log in, open the quote page, upload the Gerber zip ("Add gerber file"). The system detects layers and size.
2. Choose the board options (price updates live; the cheapest is $2 for 5 pcs, 2-layer, up to 100 x 100 mm).
3. Open "Gerber Viewer" and check the board; if fine, "Save to Cart". "Add new item" for more boards; pay for all together.
4. "Secure Checkout": address, shipping (DHL about 3-5 days after the manufacturing time; Airmail about 15-25 days), payment.
5. Payment method: "Pay Directly" (recommended; full refund if the files are not approved) or "Review Before Payment" (pay after the file
   review; production waits for payment; a failed audit is cancelled automatically).
6. Track status under the account menu / Order History.

## Board options worth knowing
- Confirm Production File: after payment JLC emails when its engineered files are ready. Download them: folder `yg` = what you uploaded,
  `ok` = JLC's production Gerbers (ignore the ddw/tgz file), `info` can be ignored. Check `ok` in a Gerber viewer, then "Yes, please
  proceed to production" or "not good, modification needed" with a note [O4]. Production layer names: to/ts/tl (top silk/mask/copper),
  l2, l3... (inner), bl/bs/bo (bottom), drl (drills), ko (outline), sk (filled vias), vcut, baobian (edge plating) [O4]. JLC recommends it
  for urgent or valuable boards [O4] and for solder-mask-defined pads, edge plating, barcodes and plugged vias (`pcb-capabilities.en.md`).
- PCB Remark: free text for special needs; any order with an English note takes longer in the audit, so use it only when needed [O3 #15].
- Delivery format: Single PCB, Panel by Customer, Panel by JLCPCB (rows x columns, 5 mm edge added) [O3 #14, O19].
- Mark on PCB: nothing is printed by default; the order-number option ended in May 2026; optional 2D barcode / serial number [O16].
- Shortage preference: "Require Full Quantity" (default; JLC remakes missing boards: +1-2 days for 1-2 layer, +2-4 days multilayer) or
  "Accept Shortages" up to a set number (refund for missing ones). With assembly, "Accept Shortages" exists only when the PCBA quantity is
  below the PCB quantity [O13].
- Build time: standard orders paid before 18:00 GMT+8 start the same day; after Saturday 18:00 and on holidays, the next business day.
  Special remarks, unclear files and needed confirmations add review time [O11].

## Adding assembly (PCBA) [O2 unless noted]
PCB and PCBA are ordered together: do not pay for the PCB before the assembly options are set.
1. On the PCB quote page switch "PCB Assembly" on, choose the assembly options (Economic or Standard, sides, quantity; special needs under
   Advanced options or a remark), "Confirm".
2. Check the rendered top and bottom, "Next".
3. Upload BOM and CPL, click "Process BOM&CPL". For a panel answer "Single Piece, please help me repeat the data" or "Complete File" [O8].
4. Review the matched parts. Search manually where "No Parts Selected" shows, "Next". Lines left unticked are not assembled; on "Next" a
   prompt offers "Do Not Place" or going back [O7].
5. Review the component placements (the placement preview), "Next".
6. "Quote & Order": choose the product description; the SMT expedite option is here too [O10]. Save to cart, check out, pay.
Short form from JLC: upload Gerber, upload BOM/CPL, select parts, get the quote [O17 #9].

## BOM / CPL processing messages [O8]
| Message | Meaning | What to do |
|---|---|---|
| "Parameter Error" | upload failed; often the browser or locale | other browser, private window, English locale; else check the file format |
| "The Uploaded File Format Is Incorrect" / "File Processing Failed" | bad format, invalid data, special characters in the file name | fix to JLC's BOM/CPL format |
| Designators differ between BOM and CPL | some parts in only one file | "Continue" leaves them unplaced; otherwise fix and re-upload |
| "Shortfall" | not enough stock (JLC or your private stock), or minimum placement quantity / loss allowance | alternative part, pre-order / global sourcing / consign, or ask support |
| Yellow exclamation mark | model not an exact match, package differs, same part on several rows, mixed part types on one row | check, then tick the line yourself |
| Special handling component | manual review after submission, possible fees | answer the email |
| "No Part Selected" | BOM data too thin to match | search by MPN or C-code |
| "Standard Only" | part not allowed on Economic | switch to Standard or "Do not place this part" |
| "Repeated Designator" | duplicate designator or two designators <= 0.2 mm apart | make each unique and > 0.2 mm apart |

## Placement review and fixing rotations
- In the preview the red dot marks the orientation (not "pin 1") and should meet the dot on the board's silkscreen [O6 #1].
- A part shown turned means its 0 degrees differs from JLC's (JLC's 0 is the tape orientation). Either correct the rotation in the CPL and
  upload again, or place the order: engineers fix rotation and polarity from the silkscreen before assembly [O6 #2, #3].
- If the silkscreen mark and the CPL disagree, JLC places by the silkscreen [O6 #10].
- After engineering, the PCBA viewer shows "the parts placement adjusted by our engineer. Please verify the orientation and position of
  the components", with Top/Bottom, 2D/3D, Assembled/Unassembled, "Show Revised Items" ("Use the 'Revised Items' filter to review changes
  made by our engineers") and "DFM Results" filtered by All / Correct / Warning / Polarized part / No data. Its note: "This result is
  automatically detected by the system and may not be accurate. If you confirm it is correct, the DFM warning can be ignored." [O9]
- Engineering-data questions JLC raises: unclear polarity marks, part not matching its footprint, parts too close (bridging, rework) [O10].
- "Confirm Parts Placement" is a $0.45 fee item [O18]; the pages read do not describe the option further (gap).

## Payment, review and holds
- PCBA Review Before Payment (new): Submit, File Review (Pending Review, Reviewing, Review Completed), Approved, Awaiting Payment, pay,
  Confirmed. Parts are reserved for up to 7 days; an approved but unpaid order cannot be changed; charges arising after payment are
  separate [O5]. The older FAQ says PCBA orders must be paid first [O6 #9]: O5 is newer.
- The review covers the PCB design, advanced options and library creation for parts without a placement footprint (usually within 48 h);
  extra payment requests can appear [O10].
- "Pending" means JLC waits for you and the production clock is paused; watch the email and the order page and answer DFM reports, part
  confirmations and extra-payment requests quickly [O10].
- Orders missing layers (no outline, no drill) or beyond the capabilities are cancelled [O3].
- Changing Gerber, BOM or CPL after a PCBA order: ask support to open "File Replacement"; the old order is cancelled with a full refund, you
  upload with "Replace File" and pay the new price; parts stay reserved for 48 h [O14].

## Lead times
- PCB build time (from "MI started" to ready for shipping) [O11, O12], standard FR-4 1.6 mm, 1 oz, HASL, green, <= 100 x 100 mm:

| Layers | 5 pcs | Up to 50 pcs | More than 50 pcs |
|---|---|---|---|
| 1-2 | 24 h | 1-2 days (< 50) | 5-6 days (>= 50) |
| 4 | 2-5 days | 2-5 days | 8 days |
| 6 | 6-7 days | 6-7 days | 7-8 days |

- Assembly times, expedite fee and the free 24 h PCB for PCBA orders: `assembly-capabilities.en.md` § "Lead times".

## Reorders [O15, O3 #11]
- A bare-board repeat order is built from the previous production file without changes or engineer review; the engineering fee is still
  charged [O3 #11].
- PCBA direct reorder (no changes, enough stock) reuses stored stencils/fixtures; it becomes a new order if the quantity exceeds Economic
  or stock is short. With changes: download the "Selected Part List" and place a new order. DFM data is regenerated on every reorder and
  part orientation can come out differently: re-check it [O15].

## Tips that save money or time (each from a JLC page)
- Panelize above about 50 boards [O21] and for boards <= 50 x 50 mm [O3 #18]; a single assembled board has a per-board minimum charge [O18].
- On Economic, Basic and Preferred/Promotional Extended parts carry no feeder fee; each Extended part does [O18, O17 #7].
- Stay inside Economic limits (one side, 0402 and up, pitch >= 0.4 mm, 0.8-1.6 mm, listed colours) [O24].
- Common option sets are pooled into big panels; uncommon ones are charged as "special process" [O22 #8]. Widen slots above 1.0 mm,
  avoid sub-0.3 mm holes, keep ENIG area <= 30 % [O22].
- One design per Gerber, or several inside one outline split by silkscreen lines (cut them yourself) [O22 #1, `pcb-capabilities.en.md`].
- Use remarks only when needed; answer engineering questions fast; run JLCDFM before uploading [O3 #15, O10].

## Conflicts and gaps
- PCBA Review Before Payment: available since the 2026-09-23 article [O5]; the older FAQ says PCBA orders must be paid first [O6 #9].
- Gaps: what the "Confirm Parts Placement" ($0.45) option does [O18]; the upload size limit of the current quote page (see
  `files-and-formats.en.md` § The upload archive).
