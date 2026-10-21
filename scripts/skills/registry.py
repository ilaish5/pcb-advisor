"""What the agent can do - the list the Skills page shows. `available` skills have a
script in this folder; the others do not exist yet and say so."""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

SKILLS = [
    {"name": "Check availability", "script": "check_availability.py",
     "what": "LCSC (JLCPCB parts search), and Mouser with an API key. Every value is stored with its supplier and time."},
    {"name": "Compare prices", "script": "compare_prices.py",
     "what": "Per supplier, from the stored checks, including lines nobody stocks."},
    {"name": "Verify pins vs datasheet", "script": "verify_part.py",
     "what": "Compares a part's pin numbers and names with its datasheet text and flags what it cannot find."},
    {"name": "Render schematic from netlist", "script": "render_sheet.py",
     "what": "Sheets in the labels-and-short-stubs style, drawn from netlist/<sheet>.json and the BOM."},
    {"name": "Export BOM for manufacturer", "script": "export_bom.py",
     "what": "JLC, PCBWay and generic CSV. Unfitted and unbought lines are listed, not dropped."},
    {"name": "Export CPL (pick and place) for JLC", "script": "export_cpl.py",
     "what": "exports/<project>_cpl.csv from the linked PcbDoc: Designator, Mid X, Mid Y, Layer, Rotation, in mm from the board origin."},
    {"name": "Download models", "script": None,
     "what": "SnapEDA, Ultra Librarian: symbol, footprint, STEP. Not built here yet."},
    {"name": "Build part from datasheet", "script": None,
     "what": "For parts with no ready model. Not built here yet."},
    {"name": "Convert & build Altium library", "script": None,
     "what": "SchLib + PcbLib to IntLib needs Altium on Windows. This tool writes the library package and manifest."},
]


def listing():
    return [{"name": s["name"], "what": s["what"], "script": s["script"],
             "available": bool(s["script"]) and (HERE / s["script"]).exists()} for s in SKILLS]
