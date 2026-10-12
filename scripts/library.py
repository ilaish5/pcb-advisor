"""Altium component library helpers.

Capabilities:
  1. model_search_links: Web search URLs (LCSC/EasyEDA, Ultra Librarian, SnapEDA) for an MPN.
  2. check_package_variant: Verify package string compatibility between BOM, JLC, and datasheet.
  3. generate_library_build_script: DelphiScript and README for the student to compile an IntLib in Altium.
"""
import argparse
import pathlib
import re
import sys
import urllib.parse


def model_search_links(mpn: str) -> dict:
    """Generate model search URLs across popular part model repositories for an MPN."""
    clean = mpn.strip()
    q = urllib.parse.quote(clean)
    return {
        "mpn": clean,
        "links": {
            "LCSC": f"https://www.lcsc.com/search?q={q}",
            "EasyEDA": f"https://easyeda.com/editor#search={q}",
            "Ultra Librarian": f"https://www.ultralibrarian.com/search?q={q}",
            "SnapEDA": f"https://www.snapeda.com/search/?q={q}",
        },
        "instructions": (
            "Link-and-return workflow: search the model, download the Altium-compatible symbol/footprint/3D zip, "
            "and upload the file back to the project library. Do not drive Altium directly."
        ),
    }


def _normalize_pkg(pkg: str) -> str:
    """Normalize a package string for comparison (remove case, whitespace, delimiters, metric aliases)."""
    if not pkg:
        return ""
    s = pkg.lower().strip()
    # Strip metric millimeter dimensions like 7x7mm or metric capacitor designations like (2012 Metric)
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"_\d+x\d+.*", "", s)
    # Remove hyphens, underscores, spaces
    s = re.sub(r"[\s\-_/,.]+", "", s)
    return s


def check_package_variant(
    bom_package: str,
    jlc_package: str = None,
    datasheet_text: str = None,
) -> dict:
    """Check package consistency across BOM, JLC manufacturer data, and datasheet.

    Returns a dict with:
        match: bool
        warning: str or None
        bom_package: str
        jlc_package: str or None
        details: list of notes
    """
    details = []
    warning = None
    match = True

    b_norm = _normalize_pkg(bom_package or "")
    j_norm = _normalize_pkg(jlc_package or "")

    # Compare BOM package vs JLC package
    if b_norm and j_norm:
        # Check direct or substring equivalence (e.g. 'qfp48' in 'lqfp48' or '0805' in 'c0805')
        if b_norm != j_norm and b_norm not in j_norm and j_norm not in b_norm:
            match = False
            warning = (
                f"Package mismatch warning: BOM package '{bom_package}' differs from "
                f"JLC part package '{jlc_package}'."
            )
            details.append(warning)
        else:
            details.append(f"BOM package '{bom_package}' matches JLC package '{jlc_package}'.")
    elif not b_norm:
        match = False
        warning = "Package warning: BOM line specifies no package."
        details.append(warning)

    # Check datasheet text if provided
    datasheet_found = None
    if datasheet_text and bom_package:
        # Look for the package keyword in the text
        pattern = re.compile(re.escape(bom_package.strip()), re.IGNORECASE)
        if pattern.search(datasheet_text):
            datasheet_found = True
            details.append(f"Package '{bom_package}' confirmed found in datasheet text.")
        else:
            # Check normalized keyword
            clean_kw = re.sub(r"[^A-Za-z0-9]", "", bom_package)
            if clean_kw and re.search(clean_kw, re.sub(r"[^A-Za-z0-9]", "", datasheet_text), re.IGNORECASE):
                datasheet_found = True
                details.append(f"Package '{bom_package}' found in datasheet text (normalized).")
            else:
                datasheet_found = False
                ds_warn = f"Package notice: '{bom_package}' not explicitly matched in available datasheet text."
                details.append(ds_warn)
                if match:  # only override if no severe mismatch yet
                    warning = ds_warn

    return {
        "match": match,
        "warning": warning,
        "bom_package": bom_package,
        "jlc_package": jlc_package,
        "datasheet_found": datasheet_found,
        "details": details,
    }


def generate_library_build_script(
    project_name: str,
    schlib: str = None,
    pcblib: str = None,
) -> tuple[str, str]:
    """Generate an Altium DelphiScript (.pas) and README.md for the student to build an IntLib.

    Does not run Altium. The student runs the script or follows the 4 manual steps in Altium Designer.
    """
    safe_name = re.sub(r"[^\w-]", "_", project_name or "ProjectLibrary")
    schlib_name = schlib or f"{safe_name}.SchLib"
    pcblib_name = pcblib or f"{safe_name}.PcbLib"
    intlib_name = f"{safe_name}.IntLib"
    libpkg_name = f"{safe_name}.LibPkg"

    script_content = f"""{{..............................................................................}}
{{ Altium Designer DelphiScript: Build Integrated Library                      }}
{{ Target: {intlib_name:<68} }}
{{ Generated by PCB Advisor for project: {safe_name:<46} }}
{{..............................................................................}}
{{ INSTRUCTIONS FOR STUDENT:                                                   }}
{{ 1. In Altium Designer, go to File » Run Script... (or DXP » Run Script...)   }}
{{ 2. Select this file (Build_IntLib.pas) and click BuildIntegratedLibrary      }}
{{ 3. The script will create {libpkg_name}, add {schlib_name} and {pcblib_name},}}
{{    compile {intlib_name}, and install it into your Components panel.         }}
{{..............................................................................}}

Procedure BuildIntegratedLibrary;
Var
    Workspace   : IWorkspace;
    Project     : IProject;
    Document    : IDocument;
    BaseDir     : String;
    PkgPath     : String;
    SchPath     : String;
    PcbPath     : String;
Begin
    Workspace := GetWorkspace;
    If Workspace = Nil Then
    Begin
        ShowMessage('Error: No active Altium Designer workspace found.');
        Exit;
    End;

    BaseDir := ExtractFilePath(GetCurrentScriptPath);
    PkgPath := BaseDir + '{libpkg_name}';
    SchPath := BaseDir + '{schlib_name}';
    PcbPath := BaseDir + '{pcblib_name}';

    // 1. Create or open the Integrated Library Package (.LibPkg)
    Project := Workspace.OpenProjectOrDocument(PkgPath);
    If Project = Nil Then
    Begin
        Project := Workspace.CreateProject('Integrated Library', PkgPath);
    End;

    If Project = Nil Then
    Begin
        ShowMessage('Failed to create or open library project: ' + PkgPath);
        Exit;
    End;

    // 2. Add schematic library and PCB footprint library if they exist
    If FileExists(SchPath) Then
    Begin
        Document := Project.AddDocument(SchPath);
    End;

    If FileExists(PcbPath) Then
    Begin
        Document := Project.AddDocument(PcbPath);
    End;

    // 3. Compile the Integrated Library project
    ResetParameters;
    AddStringParameter('ObjectKind', 'Project');
    AddStringParameter('Action', 'Compile');
    RunProcess('WorkspaceManager:Compile');

    ShowMessage('Integrated library build complete: ' + '{intlib_name}' + #13#10 +
                'Check Project Outputs folder or Components panel.');
End;
"""

    readme_content = f"""# How to Build the Integrated Library ({intlib_name})

This package was prepared by PCB Advisor to build a single integrated library (**`{intlib_name}`**)
from your project component models.

> **Course Reference**: AD20 Essentials Module 29: *Integrated Library* (§ 29.3 Create Integrated Library Project, § 29.4 Using the New Library).

---

## Option A: One-Script Build (Automated)

1. Open **Altium Designer**.
2. Go to menu **File » Run Script...** (or shortcut `DXP » Run Script...`).
3. Click **Browse...**, select `Build_IntLib.pas` from this folder, and choose the procedure **`BuildIntegratedLibrary`**.
4. Click **OK**. Altium will create `{libpkg_name}`, link `{schlib_name}` and `{pcblib_name}`, and compile `{intlib_name}`.

---

## Option B: Manual Steps in Altium Designer (AD20 Essentials § 29.3)

If you prefer to compile manually in Altium Designer:

1. **Create Library Project**:
   - Menu: **File » New » Library » Integrated Library**.
   - Save the project as **`{libpkg_name}`** in this folder.
2. **Add Component Libraries**:
   - In the **Projects** panel, right-click `{libpkg_name}` and select **Add Existing to Project...**.
   - Select both **`{schlib_name}`** and **`{pcblib_name}`** and click Open.
3. **Compile Library**:
   - Right-click `{libpkg_name}` in the Projects panel and select **Compile Integrated Library {libpkg_name}**.
   - Check the **Messages** panel (`View » Panels » Messages`) for any missing pin or footprint warnings.
4. **Install & Verify (§ 29.4)**:
   - Menu **File » Open**, navigate to `Project Outputs for {safe_name}`, select **`{intlib_name}`**, and choose **Install Library**.
   - Open the **Components** panel (`View » Panels » Components`) and verify all components appear with symbol, footprint, and 3D preview.
"""

    return script_content, readme_content


def write_library_build_package(
    output_dir: str | pathlib.Path,
    project_name: str,
    schlib: str = None,
    pcblib: str = None,
) -> dict:
    """Write Build_IntLib.pas and README.md into the designated output directory."""
    out_path = pathlib.Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    script_str, readme_str = generate_library_build_script(project_name, schlib, pcblib)

    pas_file = out_path / "Build_IntLib.pas"
    readme_file = out_path / "README.md"

    pas_file.write_text(script_str, encoding="utf-8")
    readme_file.write_text(readme_str, encoding="utf-8")

    return {
        "script": str(pas_file),
        "readme": str(readme_file),
        "project": project_name,
    }


def main(argv=None):
    import oscompat
    oscompat.utf8_stdio()
    ap = argparse.ArgumentParser(description="PCB component library tools")
    sub = ap.add_subparsers(dest="cmd")

    s_p = sub.add_parser("search", help="Get model search links for an MPN")
    s_p.add_argument("mpn", help="Manufacturer Part Number")

    c_p = sub.add_parser("check-package", help="Verify package compatibility")
    c_p.add_argument("bom_package", help="Package from BOM line")
    c_p.add_argument("jlc_package", nargs="?", default=None, help="Package from JLC / datasheet")

    b_p = sub.add_parser("build-script", help="Generate Altium library build script and README")
    b_p.add_argument("project", help="Project name")
    b_p.add_argument("--out", default="exports", help="Output directory")

    args = ap.parse_args(argv)

    if args.cmd == "search":
        res = model_search_links(args.mpn)
        print(f"Model search links for MPN '{res['mpn']}':")
        for name, url in res["links"].items():
            print(f"  {name:<16}: {url}")
        print(f"\n{res['instructions']}")
        return 0

    elif args.cmd == "check-package":
        res = check_package_variant(args.bom_package, args.jlc_package)
        status_str = "MATCH" if res["match"] else "MISMATCH / WARNING"
        print(f"Package variant check: [{status_str}]")
        for d in res["details"]:
            print(f"  - {d}")
        return 0 if res["match"] else 1

    elif args.cmd == "build-script":
        res = write_library_build_package(args.out, args.project)
        print(f"Generated library build package for '{args.project}':")
        print(f"  Script: {res['script']}")
        print(f"  Readme: {res['readme']}")
        return 0

    else:
        ap.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
