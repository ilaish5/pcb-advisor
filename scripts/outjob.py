"""
Generate ready Altium Designer Output Job (OutJob) text file for manufacturing.

Outputs configured:
1. Schematic Prints (PDF container -> <project>_Schematics.pdf)
2. Gerber Files (RS-274X format, Folder Structure container)
3. NC Drill Files (matching units, Folder Structure container)
4. JLC BOM (BOM_PartType, Folder Structure container)
5. Pick and Place / CPL (Pick Place, Folder Structure container)

The linked Altium project directory is treated as read-only.
The file is written into `projects/<project>/exports/<filename>.OutJob`, and the
student is advised to copy it into their Altium project folder.

Based on Altium Designer OutJob format from:
`shared/reference/course/ad20-essentials/m25-fabrication-files.en.md` and
`tests/fixtures/altium/outjob.OutJob`.
"""
import argparse
import json
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import oscompat  # noqa: E402
import workspace  # noqa: E402

OUTJOB_TEMPLATE = """[OutputJobFile]
Version=1.0
Caption=Production Files
Description=Complete JLC fabrication and assembly outputs
VaultGUID=
ItemGUID=
ItemHRID=
RevisionGUID=
RevisionId=
VaultHRID=
AutoItemHRID=
NextRevId=
FolderGUID=
LifeCycleDefinitionGUID=
RevisionNamingSchemeGUID=

[OutputGroup1]
Name=
Description=
TargetOutputMedium=Folder Structure
VariantName=[No Variations]
VariantScope=0
CurrentConfigurationName=
TargetPrinter=Default
PrinterOptions=Record=PrinterOptions|Copies=1|Duplex=1|TrueTypeOptions=3|Collate=1|PrintJobKind=1|PrintWhat=0
OutputMedium1=Print Job
OutputMedium1_Type=Printer
OutputMedium1_Printer=
OutputMedium1_PrinterOptions=Record=PrinterOptions|Copies=1|Duplex=1|TrueTypeOptions=3|Collate=1|PrintJobKind=1|PrintWhat=1
OutputMedium2=PDF
OutputMedium2_Type=Publish
OutputMedium3=Folder Structure
OutputMedium3_Type=GeneratedFiles
OutputMedium4=Video
OutputMedium4_Type=Multimedia

OutputType1=Schematic Print
OutputName1=Schematic Prints
OutputCategory1=Documentation
OutputDocumentPath1=
OutputVariantName1=
OutputEnabled1=1
OutputEnabled1_OutputMedium1=0
OutputEnabled1_OutputMedium2=1
OutputEnabled1_OutputMedium3=0
OutputEnabled1_OutputMedium4=0
OutputDefault1=0
PageOptions1=Record=PageOptions|CenterHorizontal=True|CenterVertical=True|PrintScale=1.00|XCorrection=1.00|YCorrection=1.00|PrintKind=0|BorderSize=5000000|LeftOffset=0|BottomOffset=0|Orientation=2|PaperLength=1000|PaperWidth=1000|Scale=100|PaperSource=7|PrintQuality=-3|MediaType=1|DitherType=10|PrintScaleMode=1|PaperKind=A4|PaperIndex=9
Configuration1_Name1=OutputConfigurationParameter1
Configuration1_Item1=Record=SchPrintView|ShowNoERC=True|ShowParamSet=True|ShowProbe=True|ShowBlanket=True|NoERCSymbolsToShow="Thin Cross","Thick Cross","Small Cross",Checkbox,Triangle|ShowNote=True|ShowNoteCollapsed=True|ShowOpenEnds=True|ExpandDesignator=True|ExpandNetLabel=False|ExpandPort=False|ExpandSheetNum=False|ExpandDocNum=False|PrintArea=0

OutputType2=BOM_PartType
OutputName2=Bill of Materials
OutputCategory2=Report
OutputDocumentPath2=
OutputVariantName2=
OutputEnabled2=1
OutputEnabled2_OutputMedium1=0
OutputEnabled2_OutputMedium2=0
OutputEnabled2_OutputMedium3=1
OutputEnabled2_OutputMedium4=0
OutputDefault2=0
PageOptions2=Record=PageOptions|CenterHorizontal=True|CenterVertical=True|PrintScale=1.00|XCorrection=1.00|YCorrection=1.00|PrintKind=0|BorderSize=5000000|LeftOffset=0|BottomOffset=0|Orientation=2|PaperLength=1000|PaperWidth=1000|Scale=100|PaperSource=7|PrintQuality=-3|MediaType=1|DitherType=10|PrintScaleMode=1|PaperKind=Letter|PaperIndex=1
Configuration2_Name1=ColumnNameFormat
Configuration2_Item1=CaptionAsName
Configuration2_Name2=General
Configuration2_Item2=OpenExported=False|AddToProject=False|ForceFit=False|NotFitted=False|Database=False|DatabasePriority=False|IncludePCBData=False|IncludeVaultData=False|IncludeAlternatives=False|ShowExportOptions=True|TemplateFilename=|BatchMode=5|FormWidth=1427|FormHeight=813|SupplierProdQty=1|SupplierAutoQty=False|SupplierUseCachedPricing=False|SupplierCurrency=<none>
Configuration2_Name3=GroupOrder
Configuration2_Item3=Comment=True|Footprint=True
Configuration2_Name4=SortOrder
Configuration2_Item4=Designator=Up|Comment=Up|Footprint=Up
Configuration2_Name5=VisibleOrder
Configuration2_Item5=Comment=100|Designator=100|Footprint=100|LCSC Part #=100|Quantity=100

OutputType3=Gerber
OutputName3=Gerber Files
OutputCategory3=Fabrication
OutputDocumentPath3=
OutputVariantName3=
OutputEnabled3=1
OutputEnabled3_OutputMedium1=0
OutputEnabled3_OutputMedium2=0
OutputEnabled3_OutputMedium3=1
OutputEnabled3_OutputMedium4=0
OutputDefault3=0
Configuration3_Name1=OutputConfigurationParameter1
Configuration3_Item1=AddToAllLayerClasses.Set= |AddToAllPlots.Set=SerializeLayerHash.Version~2,ClassName~TLayerToBoolean|CentrePlots=False|DrillDrawingSymbol=GraphicsSymbol|DrillDrawingSymbolSize=200000|EmbeddedApertures=True|FilmBorderSize=10000000|FilmXSize=200000000|FilmYSize=160000000|FlashAllFills=False|FlashPadShapes=True|G54OnApertureChange=False|GenerateDRCRulesFile=True|GenerateReliefShapes=True|GerberUnit=Imperial|IncludeUnconnectedMidLayerPads=False|LayerClassesMirror.Set= |LayerClassesPlot.Set= |LeadingAndTrailingZeroesMode=SuppressLeadingZeroes|MaxApertureSize=2500000|MinusApertureTolerance=50|Mirror.Set=SerializeLayerHash.Version~2,ClassName~TLayerToBoolean|MirrorDrillDrawingPlots=False|MirrorDrillGuidePlots=False|NoRegularPolygons=False|NumberOfDecimals=4|OptimizeChangeLocationCommands=True|OriginPosition=Relative|Panelize=False|Plot.Set=SerializeLayerHash.Version~2,ClassName~TLayerToBoolean|PlotPositivePlaneLayers=False|PlotUsedDrillDrawingLayerPairs=True|PlotUsedDrillGuideLayerPairs=True|PlusApertureTolerance=50|Record=GerberView|SoftwareArcs=False|Sorted=False

OutputType4=NC Drill
OutputName4=NC Drill Files
OutputCategory4=Fabrication
OutputDocumentPath4=
OutputVariantName4=
OutputEnabled4=1
OutputEnabled4_OutputMedium1=0
OutputEnabled4_OutputMedium2=0
OutputEnabled4_OutputMedium3=1
OutputEnabled4_OutputMedium4=0
OutputDefault4=0
Configuration4_Name1=OutputConfigurationParameter1
Configuration4_Item1=BoardOutlineType=1|DrillDrawingSymbol=GraphicsSymbol|DrillDrawingSymbolSize=200000|GenerateBoardOutline=False|GenerateDrillDrawingFile=False|GenerateDrillGuideFile=False|GenerateEIAFile=False|GenerateSeparatePlatedNonPlatedFiles=True|HolesPerStepX=1|HolesPerStepY=1|LayerClassesMirror.Set= |LayerClassesPlot.Set= |LeadingAndTrailingZeroesMode=SuppressLeadingZeroes|Mirror.Set=SerializeLayerHash.Version~2,ClassName~TLayerToBoolean|NumberOfDecimals=4|NumberOfUnits=2|OriginPosition=Relative|Plot.Set=SerializeLayerHash.Version~2,ClassName~TLayerToBoolean|Record=DrillView|Units=Imperial

OutputType5=Pick Place
OutputName5=Generates Pick and Place Files
OutputCategory5=Assembly
OutputDocumentPath5=
OutputVariantName5=
OutputEnabled5=1
OutputEnabled5_OutputMedium1=0
OutputEnabled5_OutputMedium2=0
OutputEnabled5_OutputMedium3=1
OutputEnabled5_OutputMedium4=0
OutputDefault5=0
Configuration5_Name1=OutputConfigurationParameter1
Configuration5_Item1=Record=PickPlaceView|Units=Metric|Format=CSV|Separator=Comma|IncludeHeader=True|FilterDNP=True

[PublishSettings]
OutputFilePath2=
ReleaseManaged2=0
OutputBasePath2=Outputs/Documentation
OutputPathMedia2=
OutputPathMediaValue2=
OutputPathOutputer2=[Output Type]
OutputPathOutputerPrefix2=
OutputPathOutputerValue2=
OutputFileName2={project}_Schematics.pdf
OutputFileNameMulti2=
UseOutputNameForMulti2=1
OutputFileNameSpecial2=
OpenOutput2=1
PromptOverwrite2=1
PublishMethod2=0
ZoomLevel2=50
FitSCHPrintSizeToDoc2=1
FitPCBPrintSizeToDoc2=1
GenerateNetsInfo2=1
MarkPins2=1
MarkNetLabels2=1
MarkPortsId2=1
GenerateTOC2=1
ShowComponentParameters2=1
GlobalBookmarks2=0
PDFACompliance2=Disabled
PDFVersion2=Default

OutputFilePath3=
ReleaseManaged3=1
OutputBasePath3=Outputs/Production
OutputPathMedia3=
OutputPathMediaValue3=
OutputPathOutputer3=[Output Type]
OutputPathOutputerPrefix3=
OutputPathOutputerValue3=
OutputFileName3=
OutputFileNameMulti3=
UseOutputNameForMulti3=1
OutputFileNameSpecial3=
OpenOutput3=1

[GeneratedFilesSettings]
RelativeOutputPath2=
OpenOutputs2=1
RelativeOutputPath3=
OpenOutputs3=1
AddToProject3=1
TimestampFolder3=0
UseOutputName3=0
OpenODBOutput3=0
OpenGerberOutput3=0
OpenNCDrillOutput3=0
OpenIPCOutput3=0
EnableReload3=0
"""


def generate_outjob(project: str, filename: str | None = None, out_dir: pathlib.Path | None = None) -> dict[str, Any]:
    """
    Generate an Altium OutJob text file into the project's exports directory.
    Returns path, file name, list of outputs, and user instructions.
    """
    if out_dir is None:
        pdir = workspace.project_dir(project)
        out_dir = pdir / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = pathlib.Path(filename or "").name  # never leave exports/
    if not filename:
        filename = f"{project}.OutJob"
    if not filename.lower().endswith(".outjob"):
        filename += ".OutJob"

    target = out_dir / filename
    content = OUTJOB_TEMPLATE.format(project=project)
    target.write_text(content, encoding="utf-8")

    outputs = [
        {"name": "Schematic Prints", "type": "Schematic Print", "target": "PDF (<project>_Schematics.pdf)"},
        {"name": "Bill of Materials", "type": "BOM_PartType", "target": "JLC CSV BOM"},
        {"name": "Gerber Files", "type": "Gerber RS-274X", "target": "Outputs/Production/Gerber"},
        {"name": "NC Drill Files", "type": "NC Drill", "target": "Outputs/Production/NC Drill (Plated/Non-Plated)"},
        {"name": "Generates Pick and Place Files", "type": "Pick Place", "target": "Outputs/Production/CPL CSV (mm)"},
    ]

    instruction = (
        f"OutJob file created at '{target}'.\n"
        "Notice: The linked Altium project folder is read-only for pcb-advisor.\n"
        "To generate files in Altium: copy this .OutJob file into your Altium project folder, "
        "add it to your project in Altium (Project > Add Existing to Project), open it, "
        "and click 'Generate content' under the Folder Structure container."
    )

    return {
        "ok": True,
        "path": str(target),
        "file": target.name,
        "outputs": outputs,
        "instruction": instruction,
    }


def main(argv=None):
    oscompat.utf8_stdio()
    ap = argparse.ArgumentParser(description="Generate ready Altium OutJob file")
    ap.add_argument("project", nargs="?", default="demo", help="Project name")
    ap.add_argument("--filename", "-f", help="Output filename (default <project>.OutJob)")
    ap.add_argument("--out", "-o", help="Custom output directory")
    args = ap.parse_args(argv)

    out_dir = pathlib.Path(args.out) if args.out else None
    res = generate_outjob(args.project, filename=args.filename, out_dir=out_dir)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
