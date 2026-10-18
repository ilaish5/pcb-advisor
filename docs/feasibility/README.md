# Feasibility scripts (2026-10-11)

Throw-away probes that proved the items in `docs/PRODUCT-PLAN.md` section 9. Not product code: the project folder is
passed as the first argument or the `PROJECT_DIR` environment variable, and the output is printed. Use them as the
reference for the real implementation. Run with any Python that has `olefile` (`python -I <script>`).

| script | proves |
|---|---|
| `feas_altium.py` | SchDoc `FileHeader` records (`[u32 len, high byte = binary flag][|KEY=VAL|...]`): components (RECORD=1), pins (2), designators (34), wires (27), net labels / power ports (25/17), parameters (41). PcbDoc storages, Components6, Nets6 |
| `feas_pcb.py` | PcbDoc `Rules6/Data` (records have a 2-byte prefix before the u32 length) and `Pads6/Data` (binary: type byte 2, then 6 sub-records; sub 5 = layer [0], net u16 [3:5], component u16 [7:9], x/y int32 [13:21], size x/y int32 [21:29], units 1/10000 mil). Pad -> net map (TC_FAULT = Q5D-1, TP8, U3-13, U6-25) |
| `feas_ad20.py <dir>` | The same readers on other Altium versions: every PcbDoc / SchDoc under a folder (run it on `tests/fixtures/altium`) |
| `feas_jlc.py [C-codes]` | JLC public parts API (no login): POST `https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList` `{"keyword","currentPage","pageSize","searchSource":"search"}` -> `data.componentPageInfo.list`: stockCount, componentLibraryType, componentPrices, dataManualUrl, dataManualFileAccessId, lcscGoodsUrl, attributes. No lifecycle field. Datasheet PDF: GET `https://jlcpcb.com/api/file/downloadByFileSystemAccessId/<dataManualFileAccessId>` (the LCSC `dataManualUrl` is an HTML viewer, not a PDF) |
| `feas_rul.py` | Altium `.RUL` (Design > Rules > Export Rules): one rule per line, the same `KEY=VALUE` record as `Rules6`, ends with `¶` (0xB6) + CRLF, latin-1. Import of a script-written one-rule file verified in AD26 |

Also verified by hand (see PRODUCT-PLAN section 9): Altium install = `HKLM\SOFTWARE\Altium\Builds\*` (ProgramsInstallPath,
Version); recent projects = `HKCU\Software\Altium\<build>\DesignExplorer\Recent Documents` (RecentDocumentN values).
`agy` print mode and stream-json stdin: `docs/ENGINES.md` section 5.
