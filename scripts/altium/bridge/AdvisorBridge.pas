{ PCB advisor <-> Altium bridge. Runs inside Altium Designer (DelphiScript).

  The request/response-through-files idea and the way a script is started from the command line are adapted from
  altium-mcp (MIT, Copyright (c) 2025 Siddharth Ahuja, see LICENSE-altium-mcp). Everything else is our own.

  The Python side (scripts/altium/bridge.py) writes <exchange>\request.txt: one command per line, fields separated
  by TAB, a line break inside a text written as the two characters \n. This script runs the commands in order and
  writes <exchange>\response.txt (START first, then one OK/ERR line per command, DONE last) and flushes
  <exchange>\log.txt after every step, so a runtime error (which try/except does not catch and which leaves the
  executor paused) still shows the statement that failed.
  start.flag is written once the script runs and end.flag once, at the very end: Python only stats log.txt while
  the script runs (it must never open these files then; Altium saves them without sharing) and reads them after end.flag.

  Commands:  PROJECT prj | SCH path | PCB path | SAVEPRJ prj | CLEAR path | PARAM path name value
             FRAME path x y w h text | TITLEBLOCK path | SAVE path | PING
             RULE pcb kind name scope1 scope2 priority prop=value... | RULESIN pcb | ADDDOC prj path | OUTJOB path medium basepath

  Library commands (stage L2, see "project library" below):
             LIBCLOSE libpkg schlib pcblib intlib | FPBATCH pcblib spec | FPREMOVE pcblib name
             SYMBATCH schlib spec | SYMREMOVE schlib name | SYMLINK schlib linksfile | SYMPROPS schlib propsfile
             SYMPARAMS schlib paramsfile | HIDEPINS schlib | ATTACH3D spec | SAVELIB path kind
             COMPILE libpkg intlib | CHECKINST intlib

  Drawing a sheet (scripts/altium/draw.py makes the lines): DRAWCHECK path replace | REVERT path (close without saving) | DRAWBEGIN path replace | PLACE path ref libref schlib x y pins
             WIRE path x1 y1 x2 y2 | NETLABEL path x y rot text | POWER path x y rot style text | NOERC path x y

  The create-footprints-batch and create-symbols-batch code below (LibFootprintsBatch, LibMakeSymbol,
  LibSymbolsBatch and their helpers PField, SFloat, PinElec, PinOrient) is ported from altium-mcp,
  server/AltiumScript/pcb_utils.pas and schematic_utils.pas:
      MIT License, Copyright (c) 2025 Siddharth Ahuja (full text in LICENSE-altium-mcp, next to this file).
  The link / properties / 3D / compile code is ported from our own kiln-board LibTool.pas. }

const
    REPLACEALL = 1;
    TAG = '[advisor]';

var
    LogLines : TStringList;
    Resp     : TStringList;
    Dir      : String;
    CurPrj   : String;
    Failed   : Boolean;

{ The other side (Python) only stats these files while the script runs and reads them after end.flag. The retries are a
  second line of defence: a save that finds the file locked would otherwise stop the whole script. }
procedure SaveRetry(SL: TStringList; Path: String);
var
    n : Integer;
    ok : Boolean;
begin
    ok := False;
    n := 0;
    while (not ok) and (n < 6) do
    begin
        try
            SL.SaveToFile(Path);
            ok := True;
        except
            Sleep(50);
        end;
        n := n + 1;
    end;
end;

procedure Flag(Name: String);
var
    F : TStringList;
begin
    F := TStringList.Create;
    try
        F.Add(Name);
        SaveRetry(F, Dir + Name);
    finally
        F.Free;
    end;
end;

procedure Log(Msg: String);
begin
    LogLines.Add(Msg);
    SaveRetry(LogLines, Dir + 'log.txt');
end;

procedure Say(Msg: String);
begin
    if (Copy(Msg, 1, 3) = 'ERR') then Failed := True;
    Resp.Add(Msg);
    SaveRetry(Resp, Dir + 'response.txt');
end;

{ TAB separated field accessor, 0-based; '' past the end }
function Field(S: String; Index: Integer): String;
var
    i, start, idx : Integer;
begin
    Result := '';
    idx := 0;
    start := 1;
    for i := 1 to Length(S) do
    begin
        if (S[i] = #9) then
        begin
            if (idx = Index) then
            begin
                Result := Copy(S, start, i - start);
                Exit;
            end;
            idx := idx + 1;
            start := i + 1;
        end;
    end;
    if (idx = Index) then
        Result := Copy(S, start, Length(S) - start + 1);
end;

{ Writes the file for sure: the document is marked modified first, a plain save of an unmodified new document does nothing }
procedure SaveByPath(Path: String);
var
    D : IDispatch;
begin
    D := Client.GetDocumentByPath(Path);
    if (D = nil) then
    begin
        Say('ERR not open in Altium: ' + Path);
        Exit;
    end;
    D.Modified := True;
    D.DoFileSave('');
    { saved is saved: a mark that stays on (the save itself, a repour, a rule check) would make the next step refuse the board as
      'unsaved changes'; the Python side reads the file back after every save, so a save that did not happen shows there }
    if (IntToStr(D.Modified) <> '0') then
    begin
        D.SetModified(False);
        Log('cleared the modified mark left after the save');
    end;
    Log('saved ' + Path);
end;

procedure OpenProject(Path: String);
var
    P : IDispatch;
begin
    P := GetWorkspace.DM_GetProjectFromPath(Path);
    if (P = nil) then
    begin
        ResetParameters;
        AddStringParameter('ObjectKind', 'Project');
        AddStringParameter('FileName', Path);
        RunProcess('WorkspaceManager:OpenObject');
        P := GetWorkspace.DM_GetProjectFromPath(Path);
    end;
    if (P = nil) then
    begin
        Say('ERR could not open project ' + Path);
        Exit;
    end;
    P.DM_SetAsCurrentProject;
    CurPrj := Path;
    Log('project ' + Path);
end;

{ A new document is created in the focused project, renamed and written to Path }
procedure NewDocument(Kind: String; Path: String);
var
    D, P : IDispatch;
begin
    GetWorkspace.DM_CreateNewDocument(Kind);
    D := Client.CurrentView.OwnerDocument;
    D.DoSafeChangeFileNameAndSave(Path, Kind);
    Log('renamed ' + Path);
    SaveByPath(Path);
    P := GetWorkspace.DM_GetProjectFromPath(CurPrj);
    if (Kind = 'PCB') and (P <> nil) then
    begin
        { a new PCB lands in Free Documents: add it to the project }
        P.DM_AddSourceDocument(Path);
        Log('added to project ' + Path);
    end;
end;

function SchOf(Path: String): IDispatch;
begin
    Result := SchServer.GetSchDocumentByPath(Path);
    if (Result = nil) then
    begin
        Client.OpenDocument('SCH', Path);
        Result := SchServer.GetSchDocumentByPath(Path);
    end;
end;

{ Removes every text frame whose text starts with the advisor tag (one at a time, an iterator does not survive a removal) }
procedure ClearFrames(Path: String);
var
    Sch, It, O, Found : IDispatch;
    n : Integer;
begin
    Sch := SchOf(Path);
    n := 0;
    repeat
        Found := nil;
        It := Sch.SchIterator_Create;
        It.AddFilter_ObjectSet(MkSet(eTextFrame));
        O := It.FirstSchObject;
        while (O <> nil) and (Found = nil) do
        begin
            if (Pos(TAG, O.Text) = 1) then Found := O;
            O := It.NextSchObject;
        end;
        Sch.SchIterator_Destroy(It);
        if (Found <> nil) then
        begin
            Sch.RemoveSchObject(Found);
            n := n + 1;
        end;
    until (Found = nil);
    Log('cleared ' + IntToStr(n) + ' frames in ' + Path);
end;

procedure SetParam(Path: String; Name: String; Value: String);
var
    Sch, It, O, Mine : IDispatch;
begin
    Sch := SchOf(Path);
    Mine := nil;
    It := Sch.SchIterator_Create;
    It.AddFilter_ObjectSet(MkSet(eParameter));
    O := It.FirstSchObject;
    while (O <> nil) do
    begin
        if (UpperCase(O.Name) = UpperCase(Name)) then Mine := O;
        O := It.NextSchObject;
    end;
    Sch.SchIterator_Destroy(It);
    if (Mine <> nil) then
        Mine.Text := Value
    else
    begin
        Mine := SchServer.SchObjectFactory(eParameter, eCreate_Default);
        Mine.Name := Name;
        Mine.Text := Value;
        Mine.IsHidden := True;
        Sch.AddSchObject(Mine);
    end;
    Log('param ' + Name);
end;

procedure AddFrame(Path: String; X, Y, W, H: Integer; Txt: String);
var
    Sch, F : IDispatch;
begin
    Sch := SchOf(Path);
    F := SchServer.SchObjectFactory(eTextFrame, eCreate_Default);
    F.Location := Point(MilsToCoord(X), MilsToCoord(Y));
    F.Corner := Point(MilsToCoord(X + W), MilsToCoord(Y + H));
    F.Text := Txt;
    F.ShowBorder := True;
    F.WordWrap := True;
    Sch.RegisterSchObjectInContainer(F);
    Log('frame at ' + IntToStr(X) + ',' + IntToStr(Y));
end;

procedure TitleBlock(Path: String);
var
    Sch : IDispatch;
begin
    Sch := SchOf(Path);
    Sch.TitleBlockOn := True;
    Log('title block on');
end;

{ The PCB of a path: the open one, else opened. PCBServer does not exist until a PCB was opened once. }
function BoardOf(Path: String): IDispatch;
var
    D : IDispatch;
begin
    Result := nil;
    if (PCBServer <> nil) then
        Result := PCBServer.GetPCBBoardByPath(Path);
    if (Result = nil) then
    begin
        D := Client.OpenDocument('PCB', Path);
        if (D <> nil) then D.Focus;
        if (PCBServer <> nil) then
            Result := PCBServer.GetPCBBoardByPath(Path);
    end;
end;

function FindRule(Board: IDispatch; Name: String): IDispatch;
var
    It, R : IDispatch;
begin
    Result := nil;
    It := Board.BoardIterator_Create;
    It.AddFilter_ObjectSet(MkSet(eRuleObject));
    It.AddFilter_LayerSet(AllLayers);
    It.AddFilter_Method(eProcessAll);
    R := It.FirstPCBObject;
    while (R <> nil) and (Result = nil) do
    begin
        if (R.Name = Name) then Result := R;
        R := It.NextPCBObject;
    end;
    Board.BoardIterator_Destroy(It);
end;

function NewRule(Kind: String): IDispatch;
begin
    Result := nil;
    if (Kind = 'Clearance') then Result := PCBServer.PCBRuleFactory(eRule_Clearance)
    else if (Kind = 'Width') then Result := PCBServer.PCBRuleFactory(eRule_MaxMinWidth)
    else if (Kind = 'RoutingVias') then Result := PCBServer.PCBRuleFactory(eRule_RoutingViaStyle)
    else if (Kind = 'HoleSize') then Result := PCBServer.PCBRuleFactory(eRule_MaxMinHoleSize)
    else if (Kind = 'MinimumAnnularRing') then Result := PCBServer.PCBRuleFactory(eRule_MinimumAnnularRing)
    else if (Kind = 'SolderMaskExpansion') then Result := PCBServer.PCBRuleFactory(eRule_SolderMaskExpansion)
    else if (Kind = 'PasteMaskExpansion') then Result := PCBServer.PCBRuleFactory(eRule_PasteMaskExpansion)
    else if (Kind = 'HoleToHoleClearance') then Result := PCBServer.PCBRuleFactory(eRule_HoleToHoleClearance)
    else if (Kind = 'SilkToSolderMaskClearance') then Result := PCBServer.PCBRuleFactory(eRule_SilkToSolderMaskClearance)
    else if (Kind = 'SilkToSilkClearance') then Result := PCBServer.PCBRuleFactory(eRule_SilkToSilkClearance)
    else if (Kind = 'ComponentClearance') then Result := PCBServer.PCBRuleFactory(eRule_ComponentClearance)
    else if (Kind = 'MinimumSolderMaskSliver') then Result := PCBServer.PCBRuleFactory(eRule_MinimumSolderMaskSliver)
    else if (Kind = 'ViasUnderSMD') then Result := PCBServer.PCBRuleFactory(eRule_ViasUnderSMD)
    else if (Kind = 'BoardOutlineClearance') then Result := PCBServer.PCBRuleFactory(eRule_BoardOutlineClearance);
end;

{ One rule property; lengths arrive as integers in Altium's internal unit (1 mil = 10000) }
procedure SetProp(R: IDispatch; Name: String; Value: Integer);
var
    L : Integer;
begin
    if (Name = 'Gap') then R.Gap := Value
    else if (Name = 'VerticalGap') then R.VerticalGap := Value
    else if (Name = 'MinSolderMaskSliver') then R.MinSolderMaskSliver := Value
    else if (Name = 'SilkToMaskGap') then R.SilkToMaskGap := Value
    else if (Name = 'SilkToSilkClearance') then R.SilkToSilkClearance := Value
    else if (Name = 'Expansion') then R.Expansion := Value
    else if (Name = 'MinLimit') then R.MinLimit := Value
    else if (Name = 'MaxLimit') then R.MaxLimit := Value
    else if (Name = 'MinimumRing') then R.Minimum := Value
    else if (Name = 'MinHoleWidth') then R.MinHoleWidth := Value
    else if (Name = 'MaxHoleWidth') then R.MaxHoleWidth := Value
    else if (Name = 'PreferedHoleWidth') then R.PreferedHoleWidth := Value
    else if (Name = 'MinWidth') then R.MinWidth := Value
    else if (Name = 'MaxWidth') then R.MaxWidth := Value
    else if (Name = 'PreferedWidth') then R.PreferedWidth := Value
    else if (Name = 'Allowed') then R.Allowed := (Value <> 0)
    else if (Name = 'LayerMinWidth') then begin for L := 1 to 32 do R.MinWidth[L] := Value; end
    else if (Name = 'LayerMaxWidth') then begin for L := 1 to 32 do R.MaxWidth[L] := Value; end
    else if (Name = 'LayerFavoredWidth') then begin for L := 1 to 32 do R.FavoredWidth[L] := Value; end
    else Say('ERR unknown rule property ' + Name);
end;

{ A whole number, optionally negative: checked before StrToInt, whose failure inside PreProcess/PostProcess would leave
  the editor in a command (every later save then asks about a copy) }
function IsInt(S: String): Boolean;
var
    i : Integer;
begin
    Result := (S <> '') and (S <> '-');
    for i := 1 to Length(S) do
        if not (((S[i] >= '0') and (S[i] <= '9')) or ((i = 1) and (S[i] = '-'))) then Result := False;
end;

{ RULE pcb kind name scope1 scope2 priority prop=value ...  updates the rule of that name, else adds one (the priority field is unused: Altium refuses it).
  The editor's own model is told (PreProcess, BoardRegisteration / BeginModify+EndModify messages, PostProcess), as altium-mcp does:
  a rule only added to the board object can be missing from what a later save from Altium writes. No Exit between PreProcess and PostProcess. }
procedure ApplyRule(Line: String);
var
    B, R : IDispatch;
    Old  : Boolean;
    i, p : Integer;
    Item : String;
begin
    B := BoardOf(Field(Line, 1));
    if (B = nil) then
    begin
        Say('ERR could not open the PCB ' + Field(Line, 1));
        Exit;
    end;
    R := FindRule(B, Field(Line, 3));
    Old := (R <> nil);
    if not Old then R := NewRule(Field(Line, 2));
    if (R = nil) then
    begin
        Say('ERR rule kind not supported ' + Field(Line, 2));
        Exit;
    end;
    i := 7;
    while (Field(Line, i) <> '') do
    begin
        Item := Field(Line, i);
        if not IsInt(Copy(Item, Pos('=', Item) + 1, Length(Item))) then
        begin
            Say('ERR rule value is not a whole number ' + Item);
            Exit;
        end;
        i := i + 1;
    end;
    PCBServer.PreProcess;
    if Old then
    begin
        PCBServer.SendMessageToRobots(R.I_ObjectAddress, c_Broadcast, PCBM_BeginModify, c_NoEventData);
        R.BeginModify;
    end;
    R.Name := Field(Line, 3);
    R.Scope1Expression := Field(Line, 4);
    R.Scope2Expression := Field(Line, 5);
    i := 7;
    while (Field(Line, i) <> '') do
    begin
        Item := Field(Line, i);
        p := Pos('=', Item);
        SetProp(R, Copy(Item, 1, p - 1), StrToInt(Copy(Item, p + 1, Length(Item))));
        i := i + 1;
    end;
    if Old then
    begin
        R.EndModify;
        PCBServer.SendMessageToRobots(R.I_ObjectAddress, c_Broadcast, PCBM_EndModify, c_NoEventData);
    end
    else
    begin
        B.AddPCBObject(R);
        PCBServer.SendMessageToRobots(B.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, R.I_ObjectAddress);
    end;
    PCBServer.PostProcess;
    Log('rule ' + Field(Line, 3));
end;

{ RULESIN pcb  the names of the rules on the board Altium holds in memory (not the file): log lines "RULEIN name", then
  "RULESIN n" (the end marker). "RULESIN none" when that board is not open. }
procedure RulesIn(Path: String);
var
    B, It, R : IDispatch;
    N : Integer;
begin
    B := nil;
    if (PCBServer <> nil) then B := PCBServer.GetPCBBoardByPath(Path);
    if (B = nil) then
    begin
        Log('RULESIN none');
        Exit;
    end;
    N := 0;
    It := B.BoardIterator_Create;
    It.AddFilter_ObjectSet(MkSet(eRuleObject));
    It.AddFilter_LayerSet(AllLayers);
    It.AddFilter_Method(eProcessAll);
    R := It.FirstPCBObject;
    while (R <> nil) do
    begin
        Log('RULEIN ' + R.Name);
        N := N + 1;
        R := It.NextPCBObject;
    end;
    B.BoardIterator_Destroy(It);
    Log('RULESIN ' + IntToStr(N));
end;

{ An existing document (an OutJob) becomes part of the project }
procedure AddDocument(Prj: String; Path: String);
var
    P : IDispatch;
begin
    P := GetWorkspace.DM_GetProjectFromPath(Prj);
    if (P = nil) then
    begin
        Say('ERR project not open ' + Prj);
        Exit;
    end;
    P.DM_AddSourceDocument(Path);
    Log('added to project ' + Path);
end;

{ ======================================================================== project library (stage L2) }

{ pipe separated field accessor, 0-based; '' past the end (a spec file line) }
function PField(S: String; Index: Integer): String;
var
    i, start, idx : Integer;
begin
    Result := '';
    idx := 0;
    start := 1;
    for i := 1 to Length(S) do
    begin
        if (S[i] = '|') then
        begin
            if (idx = Index) then
            begin
                Result := Copy(S, start, i - start);
                Exit;
            end;
            idx := idx + 1;
            start := i + 1;
        end;
    end;
    if (idx = Index) then
        Result := Copy(S, start, Length(S) - start + 1);
end;

{ locale safe StrToFloat: the spec files always use '.' }
function SFloat(S: String): Double;
begin
    S := Trim(S);
    if (S = '') then
    begin
        Result := 0;
        Exit;
    end;
    S := StringReplace(S, '.', DecimalSeparator, REPLACEALL);
    Result := StrToFloat(S);
end;

function SameFile(A: String; B: String): Boolean;
begin
    Result := (UpperCase(A) = UpperCase(B));
end;

{ Opens (or finds) a library document, brings it to the front and checks that the FOCUSED document is the one
  asked for: the batch code writes into whatever is focused, and a wrong focus puts parts into another library. }
function FocusLib(Path: String; Kind: String): Boolean;
var
    D, V : IDispatch;
    N : Integer;
begin
    Result := False;
    D := Client.GetDocumentByPath(Path);
    if (D = nil) then D := Client.OpenDocument(Kind, Path);
    if (D = nil) then
    begin
        Say('ERR cannot open ' + Path);
        Exit;
    end;
    { the focus can lag behind ShowDocument (a SchLib saved a moment ago still in front): ask again }
    for N := 1 to 5 do
    begin
        Client.ShowDocument(D);
        Sleep(500);
        V := Client.CurrentView;
        if (V <> nil) then
            if SameFile(V.OwnerDocument.FileName, Path) then Break;
    end;
    if (V = nil) then
    begin
        Say('ERR no focused document after opening ' + Path);
        Exit;
    end;
    if (not SameFile(V.OwnerDocument.FileName, Path)) then
    begin
        Say('ERR the focused document is ' + V.OwnerDocument.FileName + ', not ' + Path);
        Exit;
    end;
    Log('focus ' + Path);
    Result := True;
end;

{ OUTJOB path medium basepath: generate the files of one Folder Structure container of the OutJob }
procedure RunOutJob(Path: String; Medium: String; Base: String);
var
    P, D : IDispatch;
begin
    { an OutJob Altium holds under Free Documents (the project file lists it, the open project does not) has no
      data source: GenerateReport writes nothing. It joins the open project first. }
    P := GetWorkspace.DM_GetProjectFromPath(CurPrj);
    if (P = nil) then
    begin
        Say('ERR project not open ' + CurPrj);
        Exit;
    end;
    D := GetWorkspace.DM_GetDocumentFromPath(Path);
    if (D <> nil) then
        if (not SameFile(D.DM_Project.DM_ProjectFullPath, CurPrj)) then D := nil;
    if (D = nil) then
    begin
        P.DM_AddSourceDocument(Path);
        Log('added to project ' + Path);
    end;
    { GenerateReport runs the FOCUSED OutJob: an already open one left behind the PcbDoc wrote nothing }
    if (not FocusLib(Path, 'OUTPUTJOB')) then Exit;
    D := GetWorkspace.DM_GetDocumentFromPath(Path);
    if (D = nil) then
    begin
        Say('ERR the OutJob is not in the open project ' + CurPrj);
        Exit;
    end;
    if (not SameFile(D.DM_Project.DM_ProjectFullPath, CurPrj)) then
    begin
        Say('ERR the OutJob is open under ' + D.DM_Project.DM_ProjectFullPath + ', not ' + CurPrj);
        Exit;
    end;
    ResetParameters;
    AddStringParameter('Action', 'Run');
    AddStringParameter('OutputMedium', Medium);
    AddStringParameter('ObjectKind', 'OutputBatch');
    AddStringParameter('OutputBasePath', Base);
    RunProcess('WorkspaceManager:GenerateReport');
    Log('outjob ran ' + Medium);
end;

procedure SaveLib(Path: String; Kind: String);
var
    D : IDispatch;
begin
    D := Client.GetDocumentByPath(Path);
    if (D = nil) then
    begin
        Say('ERR not open in Altium: ' + Path);
        Exit;
    end;
    D.SetModified(True);
    D.DoFileSave(Kind);
    if (IntToStr(D.Modified) <> '0') then D.SetModified(False);        { saved is saved: see SaveByPath }
    Log('saved ' + Path);
end;

{ closes a document without saving, every instance of it }
procedure CloseDocByPath(Path: String);
var
    D : IDispatch;
    n : Integer;
begin
    n := 0;
    D := Client.GetDocumentByPath(Path);
    while (D <> nil) and (n < 5) do
    begin
        D.SetModified(False);
        Client.CloseDocument(D);
        n := n + 1;
        D := Client.GetDocumentByPath(Path);
    end;
    if (n > 0) then Log('closed ' + Path);
end;

{ LIBCLOSE libpkg schlib pcblib intlib: nothing of the old library stays open or installed, so the files can be replaced }
procedure LibClose(LibPkg: String; SchLib: String; PcbLib: String; IntLib: String);
var
    Prj : IDispatch;
    i   : Integer;
    Paths : TStringList;
begin
    Prj := GetWorkspace.DM_GetProjectFromPath(LibPkg);
    if (Prj <> nil) then
    begin
        Paths := TStringList.Create;
        for i := 0 to Prj.DM_LogicalDocumentCount - 1 do
            Paths.Add(Prj.DM_LogicalDocuments(i).DM_FullPath);
        for i := 0 to Paths.Count - 1 do
            CloseDocByPath(Paths[i]);
        Paths.Free;
        Prj.DM_SetAsCurrentProject;
        ResetParameters;
        AddStringParameter('ObjectKind', 'FocusedProject');
        RunProcess('WorkspaceManager:CloseObject');
        Log('closed the library package');
    end;
    CloseDocByPath(SchLib);
    CloseDocByPath(PcbLib);
    if (FileExists(IntLib)) then
    begin
        IntegratedLibraryManager.UninstallLibrary(IntLib);
        Log('uninstalled ' + IntLib);
    end;
end;

{ A layer by its name. String2Layer gave 0 (no layer) for 'Multi-Layer', which left through-hole pads on no layer;
  the constant is used for that one. }
function LayerOf(Name: String): Integer;
begin
    if (UpperCase(Name) = 'MULTI-LAYER') or (UpperCase(Name) = 'MULTI LAYER') then
        Result := eMultiLayer
    else
        Result := String2Layer(Name);
end;

{ ---------------------------------------------------------------- footprints }

{ FPBATCH pcblib spec: ported from altium-mcp CreateFootprintsBatch. Spec lines (mils, relative to the library origin):
    FPLIB|path (ignored here: the path is the command's field)  FOOTPRINT|name|description
    PAD|name|x|y|rot|layer|plated|hole|hole_type|hole_w|hole_rot|xsize|ysize|shape[|corner_pct[|mode|...]]
    TRACK|x1|y1|x2|y2|width|layer   ARC|cx|cy|r|start|end|width|layer   FILL|x1|y1|x2|y2|rot|layer
    REGION|layer|kind|x1|y1|x2|y2|...   TEXT|x|y|size|width|rot|layer|mirror|ttf|text }
procedure LibFootprintsBatch(LibPath: String; SpecPath: String);
var
    PcbLib  : IPCB_Library;
    LibComp : IPCB_LibComponent;
    Lines   : TStringList;
    Pad     : IPCB_Pad;
    Track   : IPCB_Track;
    Arc     : IPCB_Arc;
    Fill    : IPCB_Fill;
    Text    : IPCB_Text;
    Region  : IPCB_Region;
    Contour : IPCB_Contour;
    Line, Kind, FieldValue : String;
    Created, Errors, i, V : Integer;
begin
    if (not FileExists(SpecPath)) then
    begin
        Say('ERR spec file not found ' + SpecPath);
        Exit;
    end;
    if (not FocusLib(LibPath, 'PcbLib')) then Exit;
    PcbLib := PCBServer.GetCurrentPCBLibrary;
    if (PcbLib = nil) then
    begin
        Say('ERR no PCB library is active');
        Exit;
    end;
    Lines := TStringList.Create;
    Lines.LoadFromFile(SpecPath);
    LibComp := nil;
    Created := 0;
    Errors := 0;
    for i := 0 to Lines.Count - 1 do
    begin
        Line := Lines[i];
        Kind := UpperCase(Trim(PField(Line, 0)));
        try
            if (Kind = 'FOOTPRINT') then
            begin
                LibComp := PCBServer.CreatePCBLibComp;
                LibComp.Name := Trim(PField(Line, 1));
                LibComp.Description := PField(Line, 2);
                PcbLib.RegisterComponent(LibComp);
                Created := Created + 1;
                Log('footprint ' + LibComp.Name);
            end
            else if (LibComp <> nil) and (Kind = 'PAD') then
            begin
                Pad := PCBServer.PCBObjectFactory(ePadObject, eNoDimension, eCreate_Default);
                Pad.Name := PField(Line, 1);
                FieldValue := Trim(PField(Line, 15));
                if (FieldValue <> '') then
                    Pad.Mode := StrToInt(FieldValue)
                else
                    Pad.Mode := ePadMode_Simple;
                Pad.x := MilsToCoord(SFloat(PField(Line, 2)));
                Pad.y := MilsToCoord(SFloat(PField(Line, 3)));
                Pad.Layer := LayerOf(Trim(PField(Line, 5)));
                Pad.Plated := (Trim(PField(Line, 6)) = '1');
                Pad.HoleSize := MilsToCoord(SFloat(PField(Line, 7)));
                Pad.HoleType := StrToInt(Trim(PField(Line, 8)));
                Pad.HoleWidth := MilsToCoord(SFloat(PField(Line, 9)));
                Pad.HoleRotation := SFloat(PField(Line, 10));
                Pad.TopXSize := MilsToCoord(SFloat(PField(Line, 11)));
                Pad.TopYSize := MilsToCoord(SFloat(PField(Line, 12)));
                Pad.TopShape := StrToInt(Trim(PField(Line, 13)));
                FieldValue := Trim(PField(Line, 14));
                if (FieldValue <> '') then
                    Pad.StackCRPctOnLayer[eTopLayer] := StrToInt(FieldValue);
                if (Pad.Mode <> ePadMode_Simple) then
                begin
                    Pad.MidXSize := MilsToCoord(SFloat(PField(Line, 16)));
                    Pad.MidYSize := MilsToCoord(SFloat(PField(Line, 17)));
                    Pad.MidShape := StrToInt(Trim(PField(Line, 18)));
                    Pad.BotXSize := MilsToCoord(SFloat(PField(Line, 19)));
                    Pad.BotYSize := MilsToCoord(SFloat(PField(Line, 20)));
                    Pad.BotShape := StrToInt(Trim(PField(Line, 21)));
                end;
                Pad.Rotation := SFloat(PField(Line, 4));
                LibComp.AddPCBObject(Pad);
                PCBServer.SendMessageToRobots(Pad.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);
            end
            else if (LibComp <> nil) and (Kind = 'TRACK') then
            begin
                Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
                Track.x1 := MilsToCoord(SFloat(PField(Line, 1)));
                Track.y1 := MilsToCoord(SFloat(PField(Line, 2)));
                Track.x2 := MilsToCoord(SFloat(PField(Line, 3)));
                Track.y2 := MilsToCoord(SFloat(PField(Line, 4)));
                Track.Width := MilsToCoord(SFloat(PField(Line, 5)));
                Track.Layer := LayerOf(Trim(PField(Line, 6)));
                LibComp.AddPCBObject(Track);
                PCBServer.SendMessageToRobots(Track.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);
            end
            else if (LibComp <> nil) and (Kind = 'ARC') then
            begin
                Arc := PCBServer.PCBObjectFactory(eArcObject, eNoDimension, eCreate_Default);
                Arc.XCenter := MilsToCoord(SFloat(PField(Line, 1)));
                Arc.YCenter := MilsToCoord(SFloat(PField(Line, 2)));
                Arc.Radius := MilsToCoord(SFloat(PField(Line, 3)));
                Arc.StartAngle := SFloat(PField(Line, 4));
                Arc.EndAngle := SFloat(PField(Line, 5));
                Arc.LineWidth := MilsToCoord(SFloat(PField(Line, 6)));
                Arc.Layer := LayerOf(Trim(PField(Line, 7)));
                LibComp.AddPCBObject(Arc);
                PCBServer.SendMessageToRobots(Arc.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);
            end
            else if (LibComp <> nil) and (Kind = 'FILL') then
            begin
                Fill := PCBServer.PCBObjectFactory(eFillObject, eNoDimension, eCreate_Default);
                Fill.x1Location := MilsToCoord(SFloat(PField(Line, 1)));
                Fill.y1Location := MilsToCoord(SFloat(PField(Line, 2)));
                Fill.x2Location := MilsToCoord(SFloat(PField(Line, 3)));
                Fill.y2Location := MilsToCoord(SFloat(PField(Line, 4)));
                Fill.Rotation := SFloat(PField(Line, 5));
                Fill.Layer := LayerOf(Trim(PField(Line, 6)));
                LibComp.AddPCBObject(Fill);
                PCBServer.SendMessageToRobots(Fill.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);
            end
            else if (LibComp <> nil) and (Kind = 'REGION') then
            begin
                Region := PCBServer.PCBObjectFactory(eRegionObject, eNoDimension, eCreate_Default);
                Contour := PCBServer.PCBContourFactory;
                V := 3;
                while (Trim(PField(Line, V)) <> '') do
                begin
                    Contour.AddPoint(MilsToCoord(SFloat(PField(Line, V))), MilsToCoord(SFloat(PField(Line, V + 1))));
                    V := V + 2;
                end;
                Region.SetOutlineContour(Contour);
                Region.Layer := LayerOf(Trim(PField(Line, 1)));
                Region.Kind := StrToInt(Trim(PField(Line, 2)));
                LibComp.AddPCBObject(Region);
                PCBServer.SendMessageToRobots(Region.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);
            end
            else if (LibComp <> nil) and (Kind = 'TEXT') then
            begin
                Text := PCBServer.PCBObjectFactory(eTextObject, eNoDimension, eCreate_Default);
                Text.XLocation := MilsToCoord(SFloat(PField(Line, 1)));
                Text.YLocation := MilsToCoord(SFloat(PField(Line, 2)));
                Text.Size := MilsToCoord(SFloat(PField(Line, 3)));
                Text.Width := MilsToCoord(SFloat(PField(Line, 4)));
                Text.Layer := LayerOf(Trim(PField(Line, 6)));
                Text.MirrorFlag := (Trim(PField(Line, 7)) = '1');
                Text.UseTTFonts := (Trim(PField(Line, 8)) = '1');
                Text.Text := PField(Line, 9);
                Text.Rotation := SFloat(PField(Line, 5));
                LibComp.AddPCBObject(Text);
                PCBServer.SendMessageToRobots(Text.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);
            end;
        except
            Errors := Errors + 1;
            Log('primitive error on line ' + IntToStr(i + 1) + ': ' + Copy(Line, 1, 60));
        end;
    end;
    Lines.Free;
    Log('footprints created ' + IntToStr(Created) + ', primitive errors ' + IntToStr(Errors));
    if (Errors > 0) then Say('ERR ' + IntToStr(Errors) + ' footprint primitives were refused (see the log)');
end;

procedure LibFootprintRemove(LibPath: String; Name: String);
var
    PcbLib : IPCB_Library;
    Comp   : IPCB_LibComponent;
begin
    if (not FocusLib(LibPath, 'PcbLib')) then Exit;
    PcbLib := PCBServer.GetCurrentPCBLibrary;
    Comp := PcbLib.GetComponentByName(Name);
    if (Comp = nil) then
    begin
        Log('footprint ' + Name + ' not present');
        Exit;
    end;
    PcbLib.RemoveComponent(Comp);
    Log('removed footprint ' + Name + ', left ' + IntToStr(PcbLib.ComponentCount));
end;

{ ATTACH3D spec: LIB|pcblib then FP|footprint|step|rx|ry|rz|dx_mil|dy_mil|seat (ported from LibTool.pas).
  seat=1 puts an SMD model's bottom on the board; seat=0 keeps a through-hole model's own Z. }
procedure LibAttach3D(SpecPath: String);
var
    Lines  : TStringList;
    i      : Integer;
    Line, Path : String;
    PcbLib : IPCB_Library;
    Comp   : IPCB_LibComponent;
    Body   : IPCB_ComponentBody;
    Model  : IPCB_Model;
    It     : IPCB_GroupIterator;
    Prim   : IPCB_Primitive;
    R      : TCoordRect;
    X0, Y0, Added : Integer;
    Has3D  : Boolean;
begin
    Lines := TStringList.Create;
    Lines.LoadFromFile(SpecPath);
    Path := '';
    PcbLib := nil;
    Added := 0;
    X0 := 0;
    Y0 := 0;
    for i := 0 to Lines.Count - 1 do
    begin
        Line := Lines[i];
        if (PField(Line, 0) = 'LIB') then
        begin
            if (Path <> '') then SaveLib(Path, 'PcbLib');
            Path := PField(Line, 1);
            if (not FocusLib(Path, 'PcbLib')) then Exit;
            PcbLib := PCBServer.GetCurrentPCBLibrary;
            X0 := PcbLib.Board.XOrigin;
            Y0 := PcbLib.Board.YOrigin;
            Log('3D into ' + Path);
        end
        else if (PField(Line, 0) = 'FP') and (PcbLib <> nil) then
        begin
            Comp := PcbLib.GetComponentByName(PField(Line, 1));
            if (Comp = nil) then
            begin
                Say('ERR footprint not found for 3D: ' + PField(Line, 1));
                Exit;
            end;
            { only the current footprint's primitives are live on the board }
            PcbLib.SetBoardToComponentByName(PField(Line, 1));
            Has3D := False;
            It := Comp.GroupIterator_Create;
            It.AddFilter_ObjectSet(MkSet(eComponentBodyObject));
            Prim := It.FirstPCBObject;
            if (Prim <> nil) then Has3D := True;
            Comp.GroupIterator_Destroy(It);
            if Has3D then
            begin
                Log('FP ' + PField(Line, 1) + ' already has a 3D body, skipped');
                Continue;
            end;
            Log('FP ' + PField(Line, 1));
            Body := PCBServer.PCBObjectFactory(eComponentBodyObject, eNoDimension, eCreate_Default);
            Model := Body.ModelFactory_FromFilename(PField(Line, 2), False);
            Model.SetState(SFloat(PField(Line, 3)), SFloat(PField(Line, 4)), SFloat(PField(Line, 5)), 0);
            Body.Model := Model;
            Body.SetState_FromModel;
            Log('  raw standoff=' + FloatToStr(CoordToMils(Body.StandoffHeight)));
            if (PField(Line, 8) = '1') and (Abs(CoordToMils(Body.StandoffHeight)) > 0.5) then
            begin
                Model.SetState(SFloat(PField(Line, 3)), SFloat(PField(Line, 4)), SFloat(PField(Line, 5)), -Body.StandoffHeight);
                Body.Model := Model;
                Body.SetState_FromModel;
            end;
            { a new body sits at absolute 0,0; the footprint origin is the board origin }
            Body.MoveByXY(X0 + MilsToCoord(SFloat(PField(Line, 6))), Y0 + MilsToCoord(SFloat(PField(Line, 7))));
            PCBServer.PreProcess;
            PcbLib.Board.AddPCBObject(Body);
            PCBServer.SendMessageToRobots(PcbLib.Board.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, Body.I_ObjectAddress);
            PCBServer.PostProcess;
            PcbLib.Board.ViewManager_FullUpdate;
            R := Body.BoundingRectangle;
            Log('  body x[' + FloatToStr(CoordToMils(R.Left - X0)) + '..' + FloatToStr(CoordToMils(R.Right - X0)) +
                '] y[' + FloatToStr(CoordToMils(R.Bottom - Y0)) + '..' + FloatToStr(CoordToMils(R.Top - Y0)) +
                '] h=' + FloatToStr(CoordToMils(Body.OverallHeight)) + ' standoff=' + FloatToStr(CoordToMils(Body.StandoffHeight)));
            Added := Added + 1;
        end;
    end;
    if (Path <> '') then SaveLib(Path, 'PcbLib');
    Lines.Free;
    Log('3D bodies attached ' + IntToStr(Added));
end;

{ FPINFO pcblib name: logs what the footprint holds in Altium's memory (debug aid) }
procedure LibFootprintInfo(LibPath: String; Name: String);
var
    PcbLib : IPCB_Library;
    Comp   : IPCB_LibComponent;
    It     : IPCB_GroupIterator;
    Prim   : IPCB_Primitive;
    nPad, nOther : Integer;
begin
    if (not FocusLib(LibPath, 'PcbLib')) then Exit;
    PcbLib := PCBServer.GetCurrentPCBLibrary;
    Comp := PcbLib.GetComponentByName(Name);
    if (Comp = nil) then
    begin
        Say('ERR no footprint ' + Name);
        Exit;
    end;
    PcbLib.SetBoardToComponentByName(Name);
    nPad := 0;
    nOther := 0;
    It := Comp.GroupIterator_Create;
    Prim := It.FirstPCBObject;
    while (Prim <> nil) do
    begin
        if (Prim.ObjectId = ePadObject) then
        begin
            nPad := nPad + 1;
            Log('pad [' + Prim.Name + '] layer ' + IntToStr(Prim.Layer));
        end
        else
            nOther := nOther + 1;
        Prim := It.NextPCBObject;
    end;
    Comp.GroupIterator_Destroy(It);
    Log('footprint ' + Name + ': pads ' + IntToStr(nPad) + ', other ' + IntToStr(nOther));
end;

{ ---------------------------------------------------------------- symbols }

function PinElec(ElecType: String): TPinElectrical;
begin
    if (ElecType = 'eElectricHiZ') then Result := eElectricHiZ
    else if (ElecType = 'eElectricInput') then Result := eElectricInput
    else if (ElecType = 'eElectricIO') then Result := eElectricIO
    else if (ElecType = 'eElectricOpenCollector') then Result := eElectricOpenCollector
    else if (ElecType = 'eElectricOpenEmitter') then Result := eElectricOpenEmitter
    else if (ElecType = 'eElectricOutput') then Result := eElectricOutput
    else if (ElecType = 'eElectricPower') then Result := eElectricPower
    else Result := eElectricPassive;
end;

function PinOrient(Orient: String): TRotationBy90;
begin
    if (Orient = 'eRotate90') then Result := eRotate90
    else if (Orient = 'eRotate180') then Result := eRotate180
    else if (Orient = 'eRotate270') then Result := eRotate270
    else Result := eRotate0;
end;

{ One symbol into the focused SchLib (ported from altium-mcp CreateSchematicSymbol / BatchCreateOne).
  Pins: number|name|electrical|orientation|x|y|owner_part|length.  Graphics: kind|part|width|... as in the spec. }
function LibMakeSymbol(SymName: String; SymDesc: String; Pins: TStringList; Gfx: TStringList): Boolean;
var
    CurrentLib : ISch_Lib;
    Comp       : ISch_Component;
    SchPin     : ISch_Pin;
    R          : ISch_Rectangle;
    SchLine    : ISch_Line;
    Poly       : ISch_Polyline;
    Pg         : ISch_Polygon;
    SchArc     : ISch_Arc;
    I, V, VCount, GPart, GWidth, MinX, MaxY, PX, PY : Integer;
    Entry, GType, FieldValue : String;
begin
    Result := False;
    CurrentLib := SchServer.GetCurrentSchDocument;
    if (CurrentLib = nil) then Exit;
    if (CurrentLib.ObjectID <> eSchLib) then Exit;
    Comp := SchServer.SchObjectFactory(eSchComponent, eCreate_Default);
    if (Comp = nil) then Exit;
    Comp.CurrentPartID := 1;
    Comp.DisplayMode := 0;
    Comp.PartCount := 1;
    Comp.LibReference := SymName;
    Comp.ComponentDescription := SymDesc;
    Comp.Designator.Text := 'U?';

    MinX := 9999;
    MaxY := -9999;
    for I := 0 to Pins.Count - 1 do
    begin
        PX := StrToInt(Trim(PField(Pins[I], 4)));
        PY := StrToInt(Trim(PField(Pins[I], 5)));
        if (PX < MinX) then MinX := PX;
        if (PY > MaxY) then MaxY := PY;
    end;
    if (Pins.Count = 0) then
    begin
        MinX := 300;
        MaxY := 1000;
    end;
    Comp.Designator.Location := Point(MilsToCoord(MinX), MilsToCoord(MaxY + 100));

    for I := 0 to Gfx.Count - 1 do
    begin
        Entry := Trim(Gfx[I]);
        if (Entry = '') then Continue;
        GType := LowerCase(Trim(PField(Entry, 0)));
        FieldValue := Trim(PField(Entry, 1));
        if (FieldValue <> '') then GPart := StrToInt(FieldValue) else GPart := 1;
        FieldValue := Trim(PField(Entry, 2));
        if (FieldValue <> '') then GWidth := StrToInt(FieldValue) else GWidth := 1;
        if (GType = 'line') then
        begin
            SchLine := SchServer.SchObjectFactory(eLine, eCreate_Default);
            SchLine.LineWidth := GWidth;
            SchLine.Location := Point(MilsToCoord(SFloat(PField(Entry, 3))), MilsToCoord(SFloat(PField(Entry, 4))));
            SchLine.Corner := Point(MilsToCoord(SFloat(PField(Entry, 5))), MilsToCoord(SFloat(PField(Entry, 6))));
            SchLine.OwnerPartId := GPart;
            SchLine.OwnerPartDisplayMode := 0;
            Comp.AddSchObject(SchLine);
        end
        else if (GType = 'polyline') then
        begin
            Poly := SchServer.SchObjectFactory(ePolyline, eCreate_Default);
            Poly.LineWidth := GWidth;
            VCount := 0;
            while (Trim(PField(Entry, 3 + VCount)) <> '') do VCount := VCount + 1;
            VCount := VCount div 2;
            Poly.VerticesCount := VCount;
            for V := 1 to VCount do
                Poly.Vertex[V] := Point(MilsToCoord(SFloat(PField(Entry, 3 + (V - 1) * 2))),
                                        MilsToCoord(SFloat(PField(Entry, 4 + (V - 1) * 2))));
            Poly.OwnerPartId := GPart;
            Poly.OwnerPartDisplayMode := 0;
            Comp.AddSchObject(Poly);
        end
        else if (GType = 'polygon') then
        begin
            Pg := SchServer.SchObjectFactory(ePolygon, eCreate_Default);
            Pg.LineWidth := GWidth;
            Pg.IsSolid := (Trim(PField(Entry, 3)) = '1');
            Pg.AreaColor := $00B0FFFF;
            Pg.Color := $00FF0000;
            VCount := 0;
            while (Trim(PField(Entry, 4 + VCount)) <> '') do VCount := VCount + 1;
            VCount := VCount div 2;
            Pg.VerticesCount := VCount;
            for V := 1 to VCount do
                Pg.Vertex[V] := Point(MilsToCoord(SFloat(PField(Entry, 4 + (V - 1) * 2))),
                                      MilsToCoord(SFloat(PField(Entry, 5 + (V - 1) * 2))));
            Pg.OwnerPartId := GPart;
            Pg.OwnerPartDisplayMode := 0;
            Comp.AddSchObject(Pg);
        end
        else if (GType = 'rectangle') then
        begin
            R := SchServer.SchObjectFactory(eRectangle, eCreate_Default);
            R.LineWidth := GWidth;
            R.IsSolid := (Trim(PField(Entry, 3)) = '1');
            R.AreaColor := $00B0FFFF;
            R.Color := $00FF0000;
            R.Location := Point(MilsToCoord(SFloat(PField(Entry, 4))), MilsToCoord(SFloat(PField(Entry, 5))));
            R.Corner := Point(MilsToCoord(SFloat(PField(Entry, 6))), MilsToCoord(SFloat(PField(Entry, 7))));
            R.OwnerPartId := GPart;
            R.OwnerPartDisplayMode := 0;
            Comp.AddSchObject(R);
        end
        else if (GType = 'arc') then
        begin
            SchArc := SchServer.SchObjectFactory(eArc, eCreate_Default);
            SchArc.LineWidth := GWidth;
            SchArc.Location := Point(MilsToCoord(SFloat(PField(Entry, 3))), MilsToCoord(SFloat(PField(Entry, 4))));
            SchArc.Radius := MilsToCoord(SFloat(PField(Entry, 5)));
            SchArc.StartAngle := SFloat(PField(Entry, 6));
            SchArc.EndAngle := SFloat(PField(Entry, 7));
            SchArc.OwnerPartId := GPart;
            SchArc.OwnerPartDisplayMode := 0;
            Comp.AddSchObject(SchArc);
        end;
    end;

    for I := 0 to Pins.Count - 1 do
    begin
        Entry := Pins[I];
        SchPin := SchServer.SchObjectFactory(ePin, eCreate_Default);
        if (SchPin = nil) then Continue;
        SchPin.Designator := Trim(PField(Entry, 0));
        SchPin.Name := PField(Entry, 1);
        SchPin.Electrical := PinElec(Trim(PField(Entry, 2)));
        SchPin.Orientation := PinOrient(Trim(PField(Entry, 3)));
        SchPin.Location := Point(MilsToCoord(StrToInt(Trim(PField(Entry, 4)))), MilsToCoord(StrToInt(Trim(PField(Entry, 5)))));
        FieldValue := Trim(PField(Entry, 7));
        if (FieldValue <> '') then SchPin.PinLength := MilsToCoord(SFloat(FieldValue));
        FieldValue := Trim(PField(Entry, 6));
        if (FieldValue <> '') then SchPin.OwnerPartId := StrToInt(FieldValue) else SchPin.OwnerPartId := 1;
        SchPin.OwnerPartDisplayMode := 0;
        Comp.AddSchObject(SchPin);
    end;

    CurrentLib.AddSchComponent(Comp);
    SchServer.RobotManager.SendMessage(nil, c_BroadCast, SCHM_PrimitiveRegistration, Comp.I_ObjectAddress);
    CurrentLib.CurrentSchComponent := Comp;
    CurrentLib.GraphicallyInvalidate;
    Result := True;
end;

{ SYMBATCH schlib spec: ported from altium-mcp CreateSymbolsBatch. SYMBOL|name|description|parts, then its PIN| and GRAPHIC| lines }
procedure LibSymbolsBatch(LibPath: String; SpecPath: String);
var
    Lines, Pins, Gfx : TStringList;
    Line, Kind, CurName, CurDesc : String;
    i, Created, Failed2 : Integer;
begin
    if (not FileExists(SpecPath)) then
    begin
        Say('ERR spec file not found ' + SpecPath);
        Exit;
    end;
    if (not FocusLib(LibPath, 'SchLib')) then Exit;
    Lines := TStringList.Create;
    Pins := TStringList.Create;
    Gfx := TStringList.Create;
    Lines.LoadFromFile(SpecPath);
    CurName := '';
    CurDesc := '';
    Created := 0;
    Failed2 := 0;
    for i := 0 to Lines.Count do
    begin
        if (i < Lines.Count) then
        begin
            Line := Lines[i];
            Kind := UpperCase(Trim(PField(Line, 0)));
        end
        else
        begin
            Line := '';
            Kind := 'SYMBOL';        { flush the last symbol }
        end;
        if (Kind = 'SYMBOL') then
        begin
            if (CurName <> '') then
            begin
                Log('symbol ' + CurName);
                if LibMakeSymbol(CurName, CurDesc, Pins, Gfx) then
                    Created := Created + 1
                else
                begin
                    Failed2 := Failed2 + 1;
                    Log('symbol refused: ' + CurName);
                end;
            end;
            Pins.Clear;
            Gfx.Clear;
            CurName := Trim(PField(Line, 1));
            CurDesc := PField(Line, 2);
        end
        else if (Kind = 'PIN') then
            Pins.Add(Copy(Line, 5, Length(Line)))
        else if (Kind = 'GRAPHIC') then
            Gfx.Add(Copy(Line, 9, Length(Line)));
    end;
    Lines.Free;
    Pins.Free;
    Gfx.Free;
    Log('symbols created ' + IntToStr(Created) + ', refused ' + IntToStr(Failed2));
    if (Failed2 > 0) then Say('ERR ' + IntToStr(Failed2) + ' symbols were refused (see the log)');
end;

procedure LibSymbolRemove(LibPath: String; Name: String);
var
    Lib    : ISch_Lib;
    It     : ISch_Iterator;
    Comp, Victim : ISch_Component;
begin
    if (not FocusLib(LibPath, 'SchLib')) then Exit;
    Lib := SchServer.GetCurrentSchDocument;
    Victim := nil;
    It := Lib.SchLibIterator_Create;
    It.AddFilter_ObjectSet(MkSet(eSchComponent));
    Comp := It.FirstSchObject;
    while (Comp <> nil) do
    begin
        if (Comp.LibReference = Name) then Victim := Comp;
        Comp := It.NextSchObject;
    end;
    Lib.SchIterator_Destroy(It);
    if (Victim <> nil) then
    begin
        Lib.RemoveSchComponent(Victim);
        Log('removed symbol ' + Name);
    end
    else
        Log('symbol ' + Name + ' not present');
end;

{ SYMLINK schlib linksfile: Symbol=Footprint lines; the footprint is linked by NAME (never a file path) }
procedure LibLinkFootprints(LibPath: String; LinksPath: String);
var
    Lib   : ISch_Lib;
    It    : ISch_Iterator;
    Comp  : ISch_Component;
    Impl  : ISch_Implementation;
    Links : TStringList;
    Fp    : String;
    n     : Integer;
begin
    if (not FocusLib(LibPath, 'SchLib')) then Exit;
    Lib := SchServer.GetCurrentSchDocument;
    Links := TStringList.Create;
    Links.LoadFromFile(LinksPath);
    n := 0;
    It := Lib.SchLibIterator_Create;
    It.AddFilter_ObjectSet(MkSet(eSchComponent));
    Comp := It.FirstSchObject;
    while (Comp <> nil) do
    begin
        Fp := Links.Values[Comp.LibReference];
        if (Fp <> '') then
        begin
            Impl := Comp.AddSchImplementation;
            Impl.ModelName := Fp;
            Impl.ModelType := 'PCBLIB';
            Impl.IsCurrent := True;
            Impl.UseComponentLibrary := True;
            n := n + 1;
        end;
        Comp := It.NextSchObject;
    end;
    Lib.SchIterator_Destroy(It);
    Links.Free;
    Lib.GraphicallyInvalidate;
    Log('linked ' + IntToStr(n));
end;

{ SYMPROPS schlib propsfile: Symbol=Prefix|Comment  ->  designator "Prefix?" and the comment }
procedure LibSetProps(LibPath: String; PropsPath: String);
var
    Lib   : ISch_Lib;
    It, PIt : ISch_Iterator;
    Comp  : ISch_Component;
    Prm   : ISch_Parameter;
    Props : TStringList;
    V     : String;
    n     : Integer;
begin
    if (not FocusLib(LibPath, 'SchLib')) then Exit;
    Lib := SchServer.GetCurrentSchDocument;
    Props := TStringList.Create;
    Props.LoadFromFile(PropsPath);
    n := 0;
    It := Lib.SchLibIterator_Create;
    It.AddFilter_ObjectSet(MkSet(eSchComponent));
    Comp := It.FirstSchObject;
    while (Comp <> nil) do
    begin
        V := Props.Values[Comp.LibReference];
        if (V <> '') then
        begin
            Comp.Designator.Text := PField(V, 0) + '?';
            Comp.Comment.Text := PField(V, 1);
            { the Comment parameter by name too: the property alone did not always persist }
            PIt := Comp.SchIterator_Create;
            PIt.AddFilter_ObjectSet(MkSet(eParameter));
            Prm := PIt.FirstSchObject;
            while (Prm <> nil) do
            begin
                if (UpperCase(Prm.Name) = 'COMMENT') then Prm.Text := PField(V, 1);
                Prm := PIt.NextSchObject;
            end;
            Comp.SchIterator_Destroy(PIt);
            n := n + 1;
        end;
        Comp := It.NextSchObject;
    end;
    Lib.SchIterator_Destroy(It);
    Props.Free;
    Lib.GraphicallyInvalidate;
    Log('designator and comment set on ' + IntToStr(n));
end;

function FindParam(Comp: ISch_Component; Name: String): ISch_Parameter;
var
    PIt : ISch_Iterator;
    Prm : ISch_Parameter;
begin
    Result := nil;
    PIt := Comp.SchIterator_Create;
    PIt.AddFilter_ObjectSet(MkSet(eParameter));
    Prm := PIt.FirstSchObject;
    while (Prm <> nil) do
    begin
        if (UpperCase(Prm.Name) = UpperCase(Name)) then Result := Prm;
        Prm := PIt.NextSchObject;
    end;
    Comp.SchIterator_Destroy(PIt);
end;

{ SYMPARAMS schlib paramsfile: lines Symbol|Name|Value  ->  a hidden parameter on the symbol (changed when it exists) }
procedure LibSetParams(LibPath: String; ParamsPath: String);
var
    Lib   : ISch_Lib;
    It    : ISch_Iterator;
    Comp  : ISch_Component;
    Prm   : ISch_Parameter;
    Pars  : TStringList;
    i, n  : Integer;
begin
    if (not FocusLib(LibPath, 'SchLib')) then Exit;
    Lib := SchServer.GetCurrentSchDocument;
    Pars := TStringList.Create;
    Pars.LoadFromFile(ParamsPath);
    n := 0;
    It := Lib.SchLibIterator_Create;
    It.AddFilter_ObjectSet(MkSet(eSchComponent));
    Comp := It.FirstSchObject;
    while (Comp <> nil) do
    begin
        for i := 0 to Pars.Count - 1 do
            if (PField(Pars[i], 0) = Comp.LibReference) and (PField(Pars[i], 1) <> '') then
            begin
                Prm := FindParam(Comp, PField(Pars[i], 1));
                if (Prm <> nil) then
                    Prm.Text := PField(Pars[i], 2)
                else
                begin
                    Prm := SchServer.SchObjectFactory(eParameter, eCreate_Default);
                    Prm.Name := PField(Pars[i], 1);
                    Prm.Text := PField(Pars[i], 2);
                    Prm.IsHidden := True;
                    Comp.AddSchObject(Prm);
                    SchServer.RobotManager.SendMessage(Comp.I_ObjectAddress, c_BroadCast, SCHM_PrimitiveRegistration, Prm.I_ObjectAddress);
                end;
                n := n + 1;
            end;
        Comp := It.NextSchObject;
    end;
    Lib.SchIterator_Destroy(It);
    Pars.Free;
    Lib.GraphicallyInvalidate;
    Log('parameters set ' + IntToStr(n));
end;

function PinCountOf(C: ISch_Component): Integer;
var
    PIt : ISch_Iterator;
    P   : ISch_Pin;
begin
    Result := 0;
    PIt := C.SchIterator_Create;
    PIt.AddFilter_ObjectSet(MkSet(ePin));
    P := PIt.FirstSchObject;
    while (P <> nil) do
    begin
        Result := Result + 1;
        P := PIt.NextSchObject;
    end;
    C.SchIterator_Destroy(PIt);
end;

{ HIDEPINS schlib: pin NAMES off on every 2-pin symbol (the numbers stay) }
procedure LibHidePinNames(LibPath: String);
var
    Lib   : ISch_Lib;
    It, PIt : ISch_Iterator;
    C     : ISch_Component;
    P     : ISch_Pin;
    changed : Integer;
begin
    if (not FocusLib(LibPath, 'SchLib')) then Exit;
    Lib := SchServer.GetCurrentSchDocument;
    changed := 0;
    It := Lib.SchLibIterator_Create;
    It.AddFilter_ObjectSet(MkSet(eSchComponent));
    C := It.FirstSchObject;
    while (C <> nil) do
    begin
        if (PinCountOf(C) = 2) then
        begin
            PIt := C.SchIterator_Create;
            PIt.AddFilter_ObjectSet(MkSet(ePin));
            P := PIt.FirstSchObject;
            while (P <> nil) do
            begin
                if P.ShowName then
                begin
                    P.ShowName := False;
                    changed := changed + 1;
                end;
                P := PIt.NextSchObject;
            end;
            C.SchIterator_Destroy(PIt);
        end;
        C := It.NextSchObject;
    end;
    Lib.SchIterator_Destroy(It);
    Lib.GraphicallyInvalidate;
    Log('pin names hidden ' + IntToStr(changed));
end;

{ ---------------------------------------------------------------- package }

{ Altium resolves a placed part's library by FILE NAME: another installed library of the same name (an older copy of the
  project) would win. Uninstalls every other one and logs "uninstalled same-name <path>". }
procedure UninstallSameName(IntLib: String);
var
    i : Integer;
    P : String;
begin
    for i := IntegratedLibraryManager.InstalledLibraryCount - 1 downto 0 do
    begin
        P := IntegratedLibraryManager.InstalledLibraryPath(i);
        if (UpperCase(ExtractFileName(P)) = UpperCase(ExtractFileName(IntLib))) and (not SameFile(P, IntLib)) then
        begin
            IntegratedLibraryManager.UninstallLibrary(P);
            Log('uninstalled same-name ' + P);
        end;
    end;
end;

{ COMPILE libpkg intlib: closes the package's open documents, compiles and installs the IntLib (ported from LibTool.pas).
  A source document that is open (a Free Document) is silently left out of the IntLib, and a modified one raises a
  "save?" box nobody can answer, so: refuse when one is modified. }
procedure LibCompile(LibPkg: String; IntLib: String);
var
    Prj  : IDispatch;
    Doc  : IDispatch;
    i, Dirty : Integer;
    OutPath : String;
begin
    Prj := GetWorkspace.DM_GetProjectFromPath(LibPkg);
    if (Prj = nil) then Prj := GetWorkspace.DM_OpenProject(LibPkg, True);
    if (Prj = nil) then
    begin
        Say('ERR cannot open ' + LibPkg);
        Exit;
    end;
    OutPath := Prj.DM_GetOutputPath + '\' + ChangeFileExt(ExtractFileName(LibPkg), '.IntLib');
    Log('output ' + OutPath);
    Dirty := 0;
    for i := 0 to Prj.DM_LogicalDocumentCount - 1 do
    begin
        Doc := Client.GetDocumentByPath(Prj.DM_LogicalDocuments(i).DM_FullPath);
        if (Doc <> nil) then
            if Doc.Modified then
            begin
                Dirty := Dirty + 1;
                Log('modified: ' + Doc.FileName);
            end;
    end;
    if (Dirty > 0) then
    begin
        Say('ERR ' + IntToStr(Dirty) + ' modified source documents are open; they were not saved');
        Exit;
    end;
    for i := 0 to Prj.DM_LogicalDocumentCount - 1 do
        CloseDocByPath(Prj.DM_LogicalDocuments(i).DM_FullPath);
    IntegratedLibraryManager.UninstallLibrary(IntLib);
    Prj.DM_Compile;
    Log('compiled');
    UninstallSameName(IntLib);
    IntegratedLibraryManager.InstallLibrary(IntLib);
    Log('installed, components=' + IntToStr(IntegratedLibraryManager.GetComponentCount(IntLib)));
end;

{ INSTALL intlib: (re)install an IntLib that exists on disk, used to put the previous library back after a failed build }
procedure LibInstall(IntLib: String);
begin
    if (not FileExists(IntLib)) then
    begin
        Say('ERR no such file ' + IntLib);
        Exit;
    end;
    IntegratedLibraryManager.UninstallLibrary(IntLib);
    UninstallSameName(IntLib);
    IntegratedLibraryManager.InstallLibrary(IntLib);
    Log('installed ' + IntLib);
end;

{ CHECKINST intlib: logs INSTALLED yes/no from Altium's own list of installed libraries }
procedure LibCheckInstalled(IntLib: String);
var
    i, n : Integer;
    Found : Boolean;
begin
    Found := False;
    n := IntegratedLibraryManager.InstalledLibraryCount;
    for i := 0 to n - 1 do
        if SameFile(IntegratedLibraryManager.InstalledLibraryPath(i), IntLib) then Found := True;
    if Found then
        Log('INSTALLED yes ' + IntLib)
    else
        Log('INSTALLED no ' + IntLib);
end;

{ ---- drawing a sheet: parts from the project SchLib, wire stubs, net labels, power ports, No ERC.
  The layout and every coordinate come from Python (scripts/altium/draw.py); this side only creates the objects. ---- }

function RotOf(N: Integer): Integer;
begin
    if (N = 1) then Result := eRotate90
    else if (N = 2) then Result := eRotate180
    else if (N = 3) then Result := eRotate270
    else Result := eRotate0;
end;

function CountKind(Sch: IDispatch; Kind: Integer): Integer;
var
    It, O : IDispatch;
begin
    Result := 0;
    It := Sch.SchIterator_Create;
    It.AddFilter_ObjectSet(MkSet(Kind));
    O := It.FirstSchObject;
    while (O <> nil) do
    begin
        Result := Result + 1;
        O := It.NextSchObject;
    end;
    Sch.SchIterator_Destroy(It);
end;

{ removes every object of a kind, one at a time (an iterator does not survive a removal) }
procedure RemoveKind(Sch: IDispatch; Kind: Integer);
var
    It, O, Found : IDispatch;
begin
    repeat
        Found := nil;
        It := Sch.SchIterator_Create;
        It.AddFilter_ObjectSet(MkSet(Kind));
        Found := It.FirstSchObject;
        Sch.SchIterator_Destroy(It);
        if (Found <> nil) then Sch.RemoveSchObject(Found);
    until (Found = nil);
end;

{ everything the drawing commands make or wipe, counted (a sheet with wires and labels but no part is not empty either) }
function DrawnCount(Sch: IDispatch): Integer;
begin
    Result := CountKind(Sch, eSchComponent) + CountKind(Sch, eWire) + CountKind(Sch, eNetLabel) + CountKind(Sch, ePowerObject)
              + CountKind(Sch, eNoERC) + CountKind(Sch, eJunction) + CountKind(Sch, ePort);
end;

{ DRAWCHECK path replace: the sheet may be drawn on. Refused when Altium holds unsaved changes in it (a backup of the file would
  not cover them) or when anything is on it and replace is not 1. Changes nothing. }
procedure DrawCheck(Path: String; Replace: String);
var
    Sch, D : IDispatch;
    n      : Integer;
begin
    D := Client.GetDocumentByPath(Path);
    if (D <> nil) then
        if (IntToStr(D.Modified) <> '0') then      { 'if D.Modified' reads a true value as false here }
        begin
            Say('ERR the sheet is open in Altium with unsaved changes; save or close it first. Nothing was changed');
            Exit;
        end;
    Sch := SchOf(Path);
    if (Sch = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    n := DrawnCount(Sch);
    if (n > 0) and (Replace <> '1') then
    begin
        Say('ERR the sheet already has ' + IntToStr(n) + ' objects (parts, wires, labels); nothing was changed');
        Exit;
    end;
    Log('drawcheck ' + IntToStr(n) + ' objects');
end;

{ DRAWBEGIN path replace: the sheet is wiped only when replace is 1 (DRAWCHECK ran before, this is the second lock) }
procedure DrawBegin(Path: String; Replace: String);
var
    Sch : IDispatch;
    n   : Integer;
begin
    Sch := SchOf(Path);
    if (Sch = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    n := DrawnCount(Sch);
    if (n > 0) and (Replace <> '1') then
    begin
        Say('ERR the sheet already has ' + IntToStr(n) + ' objects (parts, wires, labels); nothing was changed');
        Exit;
    end;
    if (n > 0) then
    begin
        RemoveKind(Sch, eSchComponent);
        RemoveKind(Sch, eWire);
        RemoveKind(Sch, eNetLabel);
        RemoveKind(Sch, ePowerObject);
        RemoveKind(Sch, eNoERC);
        RemoveKind(Sch, eJunction);
        RemoveKind(Sch, ePort);
    end;
    ClearFrames(Path);
    Log('drawbegin ' + IntToStr(n) + ' objects removed');
end;

{ PLACE path ref libref schlib x y pins: the component comes from the SchLib FILE (an IntLib name or path gives nil, and a
  part placed any other way has no pins). It must have the pin count the library symbol has, or the run stops. }
procedure PlacePart(Path: String; Ref: String; LibRef: String; SchLib: String; X, Y, Pins: Integer);
var
    Sch  : IDispatch;
    C    : ISch_Component;
    Got  : Integer;
begin
    Sch := SchOf(Path);
    if (Sch = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    C := SchServer.LoadComponentFromLibrary(LibRef, SchLib);
    if (C = nil) then
    begin
        Say('ERR ' + Ref + ': symbol ' + LibRef + ' not found in ' + SchLib);
        Exit;
    end;
    C.Designator.Text := Ref;
    Sch.AddSchObject(C);
    C.MoveToXY(MilsToCoord(X), MilsToCoord(Y));       { after the add: this moves the pins too, setting Location does not }
    Got := PinCountOf(C);
    if (Got <> Pins) then
    begin
        Say('ERR ' + Ref + ' (' + LibRef + ') was placed with ' + IntToStr(Got) + ' pins, the library symbol has ' + IntToStr(Pins));
        Exit;
    end;
    Log('placed ' + Ref + ' ' + LibRef + ' pins=' + IntToStr(Got));
end;

procedure DrawWire(Path: String; X1, Y1, X2, Y2: Integer);
var
    Sch, W : IDispatch;
begin
    Sch := SchOf(Path);
    if (Sch = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    W := SchServer.SchObjectFactory(eWire, eCreate_Default);
    W.InsertVertex := 1;
    W.SetState_Vertex(1, Point(MilsToCoord(X1), MilsToCoord(Y1)));
    W.InsertVertex := 2;
    W.SetState_Vertex(2, Point(MilsToCoord(X2), MilsToCoord(Y2)));
    Sch.RegisterSchObjectInContainer(W);
end;

procedure DrawNetLabel(Path: String; X, Y, Rot: Integer; Txt: String);
var
    Sch, L : IDispatch;
begin
    Sch := SchOf(Path);
    if (Sch = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    L := SchServer.SchObjectFactory(eNetLabel, eCreate_Default);
    L.Location := Point(MilsToCoord(X), MilsToCoord(Y));
    L.Text := Txt;
    L.Orientation := RotOf(Rot);
    Sch.RegisterSchObjectInContainer(L);
end;

procedure DrawPower(Path: String; X, Y, Rot, Style: Integer; Txt: String);
var
    Sch, P : IDispatch;
begin
    Sch := SchOf(Path);
    if (Sch = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    P := SchServer.SchObjectFactory(ePowerObject, eCreate_Default);
    P.Location := Point(MilsToCoord(X), MilsToCoord(Y));
    P.Text := Txt;
    P.Style := Style;
    P.Orientation := RotOf(Rot);
    Sch.RegisterSchObjectInContainer(P);
end;

procedure DrawNoErc(Path: String; X, Y: Integer);
var
    Sch, N : IDispatch;
begin
    Sch := SchOf(Path);
    if (Sch = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    N := SchServer.SchObjectFactory(eNoERC, eCreate_Default);
    N.Location := Point(MilsToCoord(X), MilsToCoord(Y));
    Sch.RegisterSchObjectInContainer(N);
end;

{ ---------------------------------------------------------------- PCB placement and routing (scripts/altium/layout.py makes the lines)
  Every command works on the board of the path. Positions are mm. }

function MmCoord(S: String): Integer;
begin
    Result := MilsToCoord(SFloat(S) / 0.0254);
end;

{ what a student can have drawn on a board is not ours to count or wipe: only components and copper (signal layers, vias) are }
function PcbIsCopper(O: IDispatch; Kind: Integer): Boolean;
begin
    Result := False;
    if (Kind <> eComponentObject) and (Kind <> eNetObject) then
        if O.InComponent then Exit;                  { the copper of a footprint belongs to the footprint: never counted, never removed }
    Result := True;
    if (Kind = eComponentObject) or (Kind = eViaObject) or (Kind = eNetObject) then Exit;
    if (Kind = eRegionObject) and (O.Kind <> eRegionKind_Copper) then
    begin
        Result := False;
        Exit;
    end;
    Result := (O.Layer = eTopLayer) or (O.Layer = eBottomLayer) or ((O.Layer >= eMidLayer1) and (O.Layer <= eMidLayer30));
end;

function PcbObjCount(B: IDispatch; Kind: Integer): Integer;
var
    It, O : IDispatch;
begin
    Result := 0;
    It := B.BoardIterator_Create;
    It.AddFilter_ObjectSet(MkSet(Kind));
    It.AddFilter_LayerSet(AllLayers);
    It.AddFilter_Method(eProcessAll);
    O := It.FirstPCBObject;
    while (O <> nil) do
    begin
        if PcbIsCopper(O, Kind) then Result := Result + 1;
        O := It.NextPCBObject;
    end;
    B.BoardIterator_Destroy(It);
end;

{ removes every object of a kind from the board, one at a time (an iterator does not survive a removal) }
procedure PcbRemoveKind(B: IDispatch; Kind: Integer);
var
    It, O : IDispatch;
    L     : TInterfaceList;
    i     : Integer;
begin
    L := TInterfaceList.Create;          { collected first (an iterator does not survive a removal), then removed: linear, not quadratic }
    It := B.BoardIterator_Create;
    It.AddFilter_ObjectSet(MkSet(Kind));
    It.AddFilter_LayerSet(AllLayers);
    It.AddFilter_Method(eProcessAll);
    O := It.FirstPCBObject;
    while (O <> nil) do
    begin
        if PcbIsCopper(O, Kind) then L.Add(O);
        O := It.NextPCBObject;
    end;
    B.BoardIterator_Destroy(It);
    PCBServer.PreProcess;
    for i := 0 to L.Count - 1 do
    begin
        O := L.Items[i];
        B.RemovePCBObject(O);
    end;
    PCBServer.PostProcess;
    L.Free;
end;

function PcbPlacedCount(B: IDispatch): Integer;
begin
    Result := PcbObjCount(B, eComponentObject) + PcbObjCount(B, eTrackObject) + PcbObjCount(B, eViaObject)
              + PcbObjCount(B, eArcObject) + PcbObjCount(B, ePolyObject) + PcbObjCount(B, eRegionObject) + PcbObjCount(B, eFillObject);
end;

{ PCBCHECK path replace: the board may be placed on. Refused when Altium holds unsaved changes in it or anything is on it and
  replace is not 1. Logs the outline box (mils) so that the Python side can tell the placeholder outline of a new board from a drawn one. }
procedure PcbCheck(Path: String; Replace: String; Mode: String);
var
    B, D, O, R, S1, S2 : IDispatch;
    n, i, rectok       : Integer;
    straight           : Integer;
    bx0, bx1, by0, by1 : Integer;
begin
    D := Client.GetDocumentByPath(Path);
    if (D <> nil) then
        if (IntToStr(D.Modified) <> '0') then
        begin
            Say('ERR the board is open in Altium with unsaved changes; save or close it first. Nothing was changed');
            Exit;
        end;
    B := BoardOf(Path);
    if (B = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    n := PcbPlacedCount(B);
    if (Mode = 'route') then n := n - PcbObjCount(B, eComponentObject);        { routing: only the copper counts, parts are meant to be there }
    O := B.BoardOutline;
    R := O.BoundingRectangle;
    { BoundingRectangle is cached: right after OUTLINE changed the corners (same session, before the file is reopened) it still
      holds the old box although the corners and the saved file are new. Straight edges: take the box from the corners. }
    straight := 1;
    for i := 0 to O.PointCount - 1 do
        if (O.Segments[i].Kind <> 0) then straight := 0;
    if (straight = 1) and (O.PointCount >= 3) then
    begin
        bx0 := O.Segments[0].vx; bx1 := bx0; by0 := O.Segments[0].vy; by1 := by0;
        for i := 1 to O.PointCount - 1 do
        begin
            S1 := O.Segments[i];
            if (S1.vx < bx0) then bx0 := S1.vx;
            if (S1.vx > bx1) then bx1 := S1.vx;
            if (S1.vy < by0) then by0 := S1.vy;
            if (S1.vy > by1) then by1 := S1.vy;
        end;
    end
    else
    begin
        bx0 := R.Left; bx1 := R.Right; by0 := R.Bottom; by1 := R.Top;
    end;
    rectok := 0;                                   { four points and every edge horizontal or vertical: a real rectangle }
    if (O.PointCount = 4) then
    begin
        rectok := 1;
        for i := 0 to 3 do
        begin
            S1 := O.Segments[i];
            S2 := O.Segments[(i + 1) mod 4];
            if (S1.vx <> S2.vx) and (S1.vy <> S2.vy) then rectok := 0;
        end;
        if (bx1 = bx0) or (by1 = by0) then rectok := 0;
    end;
    Log('pcbcheck rect=' + IntToStr(rectok) + ' objects=' + IntToStr(n) + ' parts=' + IntToStr(PcbObjCount(B, eComponentObject)) + ' tracks=' + IntToStr(PcbObjCount(B, eTrackObject)) + ' vias=' + IntToStr(PcbObjCount(B, eViaObject)) + ' arcs=' + IntToStr(PcbObjCount(B, eArcObject))
        + ' polys=' + IntToStr(PcbObjCount(B, ePolyObject)) + ' regions=' + IntToStr(PcbObjCount(B, eRegionObject)) + ' fills=' + IntToStr(PcbObjCount(B, eFillObject))
        + ' outline_pts=' + IntToStr(O.PointCount) + ' box_mil=' + IntToStr(CoordToMils(bx0)) + ',' + IntToStr(CoordToMils(by0)) + ','
        + IntToStr(CoordToMils(bx1)) + ',' + IntToStr(CoordToMils(by1)));
    if (n > 0) and (Replace <> '1') then
    begin
        if (Mode = 'route') then Say('ERR the board already has ' + IntToStr(n) + ' tracks, vias or pours; nothing was changed')
        else Say('ERR the board already has ' + IntToStr(n) + ' parts or copper objects; nothing was changed');
        Exit;
    end;
end;

function NetOf(B: IDispatch; Name: String): IDispatch;
var
    It, N : IDispatch;
begin
    Result := nil;
    It := B.BoardIterator_Create;
    It.AddFilter_ObjectSet(MkSet(eNetObject));
    It.AddFilter_LayerSet(AllLayers);
    It.AddFilter_Method(eProcessAll);
    N := It.FirstPCBObject;
    while (N <> nil) and (Result = nil) do
    begin
            if (N.Name = Name) then Result := N;
        N := It.NextPCBObject;
    end;
    B.BoardIterator_Destroy(It);
    if (Result = nil) then
    begin
        Result := PCBServer.PCBObjectFactory(eNetObject, eNoDimension, eCreate_Default);
        Result.Name := Name;
        B.AddPCBObject(Result);
    end;
end;

{ ROUTEBEGIN path replace: with replace 1 the copper on signal layers (tracks, vias, arcs, pours, copper regions, fills) goes; parts stay }
procedure PcbRouteBegin(Path: String; Replace: String);
var
    B : IDispatch;
    n : Integer;
begin
    B := BoardOf(Path);
    if (B = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    n := PcbPlacedCount(B) - PcbObjCount(B, eComponentObject);
    if (n > 0) and (Replace <> '1') then
    begin
        Say('ERR the board already has ' + IntToStr(n) + ' tracks, vias or pours; nothing was changed');
        Exit;
    end;
    if (n > 0) then
    begin
        PcbRemoveKind(B, eTrackObject);
        Log('removed tracks');
        PcbRemoveKind(B, eViaObject);
        Log('removed vias');
        PcbRemoveKind(B, eArcObject);
        PcbRemoveKind(B, ePolyObject);
        PcbRemoveKind(B, eRegionObject);
        PcbRemoveKind(B, eFillObject);
        Log('removed the rest of the copper');
    end;
    Log('routebegin ' + IntToStr(n) + ' objects removed');
end;

{ TRACK path layer x1 y1 x2 y2 width net }
procedure PcbTrack(Path: String; Layer: String; X1, Y1, X2, Y2, W, NetName: String);
var
    B, T, N : IDispatch;
begin
    B := BoardOf(Path);
    if (B = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    N := NetOf(B, NetName);
    PCBServer.PreProcess;
    T := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
    T.X1 := MmCoord(X1);
    T.Y1 := MmCoord(Y1);
    T.X2 := MmCoord(X2);
    T.Y2 := MmCoord(Y2);
    T.Width := MmCoord(W);
    if (Layer = 'bottom') then T.Layer := eBottomLayer else T.Layer := eTopLayer;
    B.AddPCBObject(T);
    T.Net := N;
    N.AddPCBObject(T);
    PCBServer.SendMessageToRobots(B.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, T.I_ObjectAddress);
    PCBServer.PostProcess;
end;

{ VIA path x y diameter hole net: a through via, top to bottom }
procedure PcbVia(Path: String; X, Y, Dia, Hole, NetName: String);
var
    B, V, N : IDispatch;
begin
    B := BoardOf(Path);
    if (B = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    N := NetOf(B, NetName);
    PCBServer.PreProcess;
    V := PCBServer.PCBObjectFactory(eViaObject, eNoDimension, eCreate_Default);
    V.X := MmCoord(X);
    V.Y := MmCoord(Y);
    V.Size := MmCoord(Dia);
    V.HoleSize := MmCoord(Hole);
    V.LowLayer := eTopLayer;
    V.HighLayer := eBottomLayer;
    B.AddPCBObject(V);
    V.Net := N;
    N.AddPCBObject(V);
    PCBServer.SendMessageToRobots(B.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, V.I_ObjectAddress);
    PCBServer.PostProcess;
end;

{ POLY path layer net x0 y0 x1 y1: a solid copper pour of the net on the layer over the box, poured over the same net only, dead copper
  removed, poured once the tracks are there (the pour keeps the board's clearance rule around everything else) }
procedure PcbPoly(Path: String; Layer: String; NetName: String; X0, Y0, X1, Y1: String);
var
    B, P, N, S : IDispatch;
    i          : Integer;
begin
    B := BoardOf(Path);
    if (B = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    N := NetOf(B, NetName);
    PCBServer.PreProcess;
    P := PCBServer.PCBObjectFactory(ePolyObject, eNoDimension, eCreate_Default);
    P.PolyHatchStyle := ePolySolid;
    P.PourOver := ePolygonPourOver_SameNet;
    P.RemoveDead := True;
    if (Layer = 'bottom') then P.Layer := eBottomLayer else P.Layer := eTopLayer;
    P.PointCount := 4;
    for i := 0 to 3 do
    begin
        S := P.Segments[i];
        S.Kind := ePolySegmentLine;
        if (i = 0) or (i = 3) then S.vx := MmCoord(X0) else S.vx := MmCoord(X1);
        if (i = 0) or (i = 1) then S.vy := MmCoord(Y0) else S.vy := MmCoord(Y1);
        P.Segments[i] := S;
    end;
    B.AddPCBObject(P);
    P.Net := N;
    N.AddPCBObject(P);
    PCBServer.SendMessageToRobots(B.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, P.I_ObjectAddress);
    P.Rebuild;
    PCBServer.PostProcess;
    Log('poly ' + NetName + ' ' + Layer + ' ' + X0 + ' ' + Y0 + ' ' + X1 + ' ' + Y1);
end;

procedure PcbBegin(Path: String; Replace: String);
var
    B : IDispatch;
    n : Integer;
begin
    B := BoardOf(Path);
    if (B = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    n := PcbPlacedCount(B);
    if (n > 0) and (Replace <> '1') then
    begin
        Say('ERR the board already has ' + IntToStr(n) + ' parts or copper objects; nothing was changed');
        Exit;
    end;
    if (n > 0) then
    begin
        PcbRemoveKind(B, eTrackObject);
        Log('removed tracks');
        PcbRemoveKind(B, eViaObject);
        Log('removed vias');
        PcbRemoveKind(B, eArcObject);
        Log('removed arcs');
        PcbRemoveKind(B, ePolyObject);
        Log('removed polys');
        PcbRemoveKind(B, eRegionObject);
        Log('removed regions');
        PcbRemoveKind(B, eFillObject);
        Log('removed fills');
        PcbRemoveKind(B, eComponentObject);
        Log('removed components');
        PcbRemoveKind(B, eNetObject);
    end;
    Log('pcbbegin ' + IntToStr(n) + ' objects removed');
end;

{ OUTLINE path x0 y0 x1 y1: the four corners of the board outline (a new board starts with a four point placeholder) }
procedure PcbOutline(Path: String; X0, Y0, X1, Y1: String);
var
    B, O, S : IDispatch;
    i       : Integer;
begin
    B := BoardOf(Path);
    if (B = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    O := B.BoardOutline;
    if (O.PointCount <> 4) then
    begin
        Say('ERR the board outline has ' + IntToStr(O.PointCount) + ' points, not the 4 of a rectangle; nothing was changed');
        Exit;
    end;
    PCBServer.PreProcess;
    O.Invalidate;
    for i := 0 to 3 do
    begin
        S := O.Segments[i];
        if (i = 0) or (i = 3) then S.vx := MmCoord(X0) else S.vx := MmCoord(X1);
        if (i = 0) or (i = 1) then S.vy := MmCoord(Y0) else S.vy := MmCoord(Y1);
        O.Segments[i] := S;
    end;
    O.Rebuild;
    O.Validate;
    PCBServer.PostProcess;
    Log('outline ' + X0 + ' ' + Y0 + ' ' + X1 + ' ' + Y1);
end;

{ number of free (not part of a footprint) tracks and arcs on Mechanical 1 }
function PcbOutlineLayerCount(B: IDispatch): Integer;
var
    It, O : IDispatch;
    k     : Integer;
begin
    Result := 0;
    for k := 0 to 1 do
    begin
        It := B.BoardIterator_Create;
        if (k = 0) then It.AddFilter_ObjectSet(MkSet(eTrackObject)) else It.AddFilter_ObjectSet(MkSet(eArcObject));
        It.AddFilter_LayerSet(MkSet(eMechanical1));
        It.AddFilter_Method(eProcessAll);
        O := It.FirstPCBObject;
        while (O <> nil) do
        begin
            if (not O.InComponent) then Result := Result + 1;
            O := It.NextPCBObject;
        end;
        B.BoardIterator_Destroy(It);
    end;
end;

{ OUTLINEDRAW path x0 y0 x1 y1 width: the rectangle as four closed tracks on Mechanical 1 (what Design > Board Shape > Create Primitives
  From Board Shape draws; the OutJob's outline Gerber .GM1 comes from that layer). A drawing somebody made there is never touched:
  nothing is drawn when the layer already holds a free track or arc. Logs "outlinedraw drawn=4" or "outlinedraw drawn=0 existing=N". }
procedure PcbOutlineDraw(Path: String; X0, Y0, X1, Y1, W: String);
var
    B, T : IDispatch;
    n, i : Integer;
    ax, ay, bx, by : Integer;
begin
    B := BoardOf(Path);
    if (B = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    n := PcbOutlineLayerCount(B);
    if (n > 0) then
    begin
        Log('outlinedraw drawn=0 existing=' + IntToStr(n));
        Exit;
    end;
    PCBServer.PreProcess;
    for i := 0 to 3 do
    begin
        if (i = 0) then begin ax := MmCoord(X0); ay := MmCoord(Y0); bx := MmCoord(X1); by := MmCoord(Y0); end;
        if (i = 1) then begin ax := MmCoord(X1); ay := MmCoord(Y0); bx := MmCoord(X1); by := MmCoord(Y1); end;
        if (i = 2) then begin ax := MmCoord(X1); ay := MmCoord(Y1); bx := MmCoord(X0); by := MmCoord(Y1); end;
        if (i = 3) then begin ax := MmCoord(X0); ay := MmCoord(Y1); bx := MmCoord(X0); by := MmCoord(Y0); end;
        T := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
        T.X1 := ax;
        T.Y1 := ay;
        T.X2 := bx;
        T.Y2 := by;
        T.Width := MmCoord(W);
        T.Layer := eMechanical1;
        B.AddPCBObject(T);
        PCBServer.SendMessageToRobots(B.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, T.I_ObjectAddress);
    end;
    PCBServer.PostProcess;
    Log('outlinedraw drawn=4 existing=0');
end;

{ PLACEFP path ref footprint pcblib x y rot libref: the footprint comes from the project PcbLib and is linked the way Update PCB
  links it (designator, source designator, library reference, footprint library) so that a later Update PCB matches it }
procedure PcbPlace(Path: String; Ref: String; Pattern: String; PcbLib: String; X, Y, Rot, LibRef, Value, LX, LY, LH, LLine, SrcId, SrcPath: String);
var
    B, Lib, C, It, P : IDispatch;
    n                : Integer;
begin
    B := BoardOf(Path);
    if (B = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    if (B.GetPcbComponentByRefDes(Ref) <> nil) then
    begin
        Say('ERR ' + Ref + ' is already on the board');
        Exit;
    end;
    Lib := PCBServer.LoadCompFromLibrary(Pattern, PcbLib);
    if (Lib = nil) then
    begin
        Say('ERR ' + Ref + ': footprint ' + Pattern + ' not found in ' + PcbLib);
        Exit;
    end;
    PCBServer.PreProcess;
    C := PCBServer.PCBObjectFactory(eComponentObject, eNoDimension, eCreate_Default);
    C.Pattern := Pattern;
    C.Name.Text := Ref;
    C.Layer := eTopLayer;
    n := 0;
    It := Lib.GroupIterator_Create;
    P := It.FirstPCBObject;
    while (P <> nil) do
    begin
        C.AddPCBObject(P.Replicate);
        n := n + 1;
        P := It.NextPCBObject;
    end;
    Lib.GroupIterator_Destroy(It);
    B.AddPCBObject(C);
    C.SourceDesignator := Ref;
    C.SourceLibReference := LibRef;
    C.SourceFootprintLibrary := ExtractFileName(PcbLib);
    if (SrcId <> '') then C.SourceUniqueId := SrcId;
    if (SrcPath <> '') then C.SourceHierarchicalPath := SrcPath;
    C.MoveToXY(MmCoord(X), MmCoord(Y));
    C.Rotation := SFloat(Rot);
    if (Value <> '') then C.Comment.Text := Value;
    C.CommentOn := False;
    C.NameOn := True;
    if (LH <> '') then
    begin
        C.Name.UseTTFonts := False;
        C.Name.Rotation := 0;
        C.Name.Size := MmCoord(LH);
        C.Name.Width := MmCoord(LLine);
        C.Name.XLocation := MmCoord(LX) - MmCoord(FloatToStr(Length(Ref) * 0.6 * SFloat(LH) / 2));
        C.Name.YLocation := MmCoord(LY) - MmCoord(FloatToStr(SFloat(LH) / 2));
    end;
    PCBServer.SendMessageToRobots(B.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, C.I_ObjectAddress);
    PCBServer.PostProcess;
    Log('placed ' + Ref + ' ' + Pattern + ' primitives=' + IntToStr(n));
end;

procedure PcbPadNet(Path: String; Ref: String; PadName: String; NetName: String);
var
    B, C, P, N, It : IDispatch;
    k              : Integer;
begin
    B := BoardOf(Path);
    if (B = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    C := B.GetPcbComponentByRefDes(Ref);
    if (C = nil) then
    begin
        Say('ERR ' + Ref + ' is not on the board');
        Exit;
    end;
    k := 0;
    PCBServer.PreProcess;
    N := NetOf(B, NetName);
    It := C.GroupIterator_Create;
    It.AddFilter_ObjectSet(MkSet(ePadObject));
    P := It.FirstPCBObject;
    while (P <> nil) do
    begin
        if (P.Name = PadName) then
        begin
            P.Net := N;
            N.AddPCBObject(P);          { without this the pad shows the net in Altium but the saved file has none }
            k := k + 1;
        end;
        P := It.NextPCBObject;
    end;
    C.GroupIterator_Destroy(It);
    PCBServer.PostProcess;
    if (k = 0) then Say('ERR ' + Ref + ': the footprint ' + C.Pattern + ' has no pad ' + PadName)
    else Log('padnet ' + Ref + '-' + PadName + ' ' + NetName + ' x' + IntToStr(k));
end;

{ PCBEXTENT path ref: the bounding box Altium itself gives the placed part (without its designator and comment), mils }
procedure PcbExtent(Path: String; Ref: String);
var
    B, C, R : IDispatch;
begin
    B := BoardOf(Path);
    if (B = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    C := B.GetPcbComponentByRefDes(Ref);
    if (C = nil) then
    begin
        Say('ERR ' + Ref + ' is not on the board');
        Exit;
    end;
    R := C.BoundingRectangleNoNameComment;
    Log('extent ' + Ref + ' ' + IntToStr(CoordToMils(R.Left)) + ' ' + IntToStr(CoordToMils(R.Bottom)) + ' ' + IntToStr(CoordToMils(R.Right)) + ' '
        + IntToStr(CoordToMils(R.Top)));
end;

{ DRC path report: the batch design rule check by script (no dialog); the text report is written to report }
procedure PcbDrc(Path: String; Report: String);
var
    B  : IDispatch;
    ok : Boolean;
begin
    B := BoardOf(Path);
    if (B = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    if FileExists(Report) then DeleteFile(Report);
    ok := B.RunBatchDesignRuleCheck(Report, eDRC_Text, False, False);       { False also means 'violations found' }
    if (not FileExists(Report)) then
    begin
        Say('ERR the design rule check did not write its report');
        Exit;
    end;
    Log('drc ' + Report + ' clean=' + BoolToStr(ok, True));
end;

{ 1 when Altium holds the document open with unsaved changes (0 when closed or clean) }
function DocDirty(Path: String): Integer;
var
    D : IDispatch;
begin
    Result := 0;
    D := Client.GetDocumentByPath(Path);
    if (D <> nil) then
        if (IntToStr(D.Modified) <> '0') then Result := 1;
end;

{ DOCSTATE path: logs whether Altium holds the document open with unsaved changes. Changes nothing. }
procedure DocState(Path: String);
var
    D : IDispatch;
begin
    D := Client.GetDocumentByPath(Path);
    if (D = nil) then Log('docstate closed')
    else Log('docstate open modified=' + IntToStr(DocDirty(Path)));
end;

procedure DispatchStep(Line: String);
var
    Cmd : String;
begin
    Cmd := Field(Line, 0);
    Log('> ' + Cmd);
    if (Cmd = 'PROJECT') then OpenProject(Field(Line, 1))
    else if (Cmd = 'SCH') then NewDocument('SCH', Field(Line, 1))
    else if (Cmd = 'PCB') then NewDocument('PCB', Field(Line, 1))
    else if (Cmd = 'SAVEPRJ') then SaveByPath(Field(Line, 1))
    else if (Cmd = 'SAVE') then SaveByPath(Field(Line, 1))
    else if (Cmd = 'CLEAR') then ClearFrames(Field(Line, 1))
    else if (Cmd = 'PARAM') then SetParam(Field(Line, 1), Field(Line, 2), Field(Line, 3))
    else if (Cmd = 'TITLEBLOCK') then TitleBlock(Field(Line, 1))
    else if (Cmd = 'FRAME') then
        AddFrame(Field(Line, 1), StrToInt(Field(Line, 2)), StrToInt(Field(Line, 3)),
                 StrToInt(Field(Line, 4)), StrToInt(Field(Line, 5)),
                 StringReplace(Field(Line, 6), '\n', #13#10, REPLACEALL))
    else if (Cmd = 'RULE') then ApplyRule(Line)
    else if (Cmd = 'RULESIN') then RulesIn(Field(Line, 1))
    else if (Cmd = 'ADDDOC') then AddDocument(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'OUTJOB') then RunOutJob(Field(Line, 1), Field(Line, 2), Field(Line, 3))
    else if (Cmd = 'LIBCLOSE') then LibClose(Field(Line, 1), Field(Line, 2), Field(Line, 3), Field(Line, 4))
    else if (Cmd = 'FPBATCH') then LibFootprintsBatch(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'FPREMOVE') then LibFootprintRemove(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'SYMBATCH') then LibSymbolsBatch(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'SYMREMOVE') then LibSymbolRemove(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'SYMLINK') then LibLinkFootprints(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'SYMPROPS') then LibSetProps(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'SYMPARAMS') then LibSetParams(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'HIDEPINS') then LibHidePinNames(Field(Line, 1))
    else if (Cmd = 'ATTACH3D') then LibAttach3D(Field(Line, 1))
    else if (Cmd = 'SAVELIB') then SaveLib(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'COMPILE') then LibCompile(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'INSTALL') then LibInstall(Field(Line, 1))
    else if (Cmd = 'CHECKINST') then LibCheckInstalled(Field(Line, 1))
    else if (Cmd = 'FPINFO') then LibFootprintInfo(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'DRAWCHECK') then DrawCheck(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'REVERT') then CloseDocByPath(Field(Line, 1))
    else if (Cmd = 'DRAWBEGIN') then DrawBegin(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'PLACE') then
        PlacePart(Field(Line, 1), Field(Line, 2), Field(Line, 3), Field(Line, 4), StrToInt(Field(Line, 5)),
                  StrToInt(Field(Line, 6)), StrToInt(Field(Line, 7)))
    else if (Cmd = 'WIRE') then
        DrawWire(Field(Line, 1), StrToInt(Field(Line, 2)), StrToInt(Field(Line, 3)), StrToInt(Field(Line, 4)), StrToInt(Field(Line, 5)))
    else if (Cmd = 'NETLABEL') then
        DrawNetLabel(Field(Line, 1), StrToInt(Field(Line, 2)), StrToInt(Field(Line, 3)), StrToInt(Field(Line, 4)), Field(Line, 5))
    else if (Cmd = 'POWER') then
        DrawPower(Field(Line, 1), StrToInt(Field(Line, 2)), StrToInt(Field(Line, 3)), StrToInt(Field(Line, 4)),
                  StrToInt(Field(Line, 5)), Field(Line, 6))
    else if (Cmd = 'NOERC') then DrawNoErc(Field(Line, 1), StrToInt(Field(Line, 2)), StrToInt(Field(Line, 3)))
    else if (Cmd = 'PCBCHECK') then PcbCheck(Field(Line, 1), Field(Line, 2), Field(Line, 3))
    else if (Cmd = 'ROUTEBEGIN') then PcbRouteBegin(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'TRACK') then
        PcbTrack(Field(Line, 1), Field(Line, 2), Field(Line, 3), Field(Line, 4), Field(Line, 5), Field(Line, 6), Field(Line, 7), Field(Line, 8))
    else if (Cmd = 'VIA') then PcbVia(Field(Line, 1), Field(Line, 2), Field(Line, 3), Field(Line, 4), Field(Line, 5), Field(Line, 6))
    else if (Cmd = 'POLY') then PcbPoly(Field(Line, 1), Field(Line, 2), Field(Line, 3), Field(Line, 4), Field(Line, 5), Field(Line, 6), Field(Line, 7))
    else if (Cmd = 'PCBBEGIN') then PcbBegin(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'OUTLINE') then PcbOutline(Field(Line, 1), Field(Line, 2), Field(Line, 3), Field(Line, 4), Field(Line, 5))
    else if (Cmd = 'OUTLINEDRAW') then PcbOutlineDraw(Field(Line, 1), Field(Line, 2), Field(Line, 3), Field(Line, 4), Field(Line, 5), Field(Line, 6))
    else if (Cmd = 'PLACEFP') then
        PcbPlace(Field(Line, 1), Field(Line, 2), Field(Line, 3), Field(Line, 4), Field(Line, 5), Field(Line, 6), Field(Line, 7), Field(Line, 8),
                 Field(Line, 9), Field(Line, 10), Field(Line, 11), Field(Line, 12), Field(Line, 13), Field(Line, 14), Field(Line, 15))
    else if (Cmd = 'PCBEXTENT') then PcbExtent(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'PADNET') then PcbPadNet(Field(Line, 1), Field(Line, 2), Field(Line, 3), Field(Line, 4))
    else if (Cmd = 'PCBSAVE') then SaveByPath(Field(Line, 1))
    else if (Cmd = 'DRC') then PcbDrc(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'DOCSTATE') then DocState(Field(Line, 1))
    else if (Cmd = 'PING') then Log('ping')
    else Say('ERR unknown command ' + Cmd);
end;

procedure Dispatch(Line: String);
var
    Cmd : String;
    Was : Integer;
    D   : IDispatch;
begin
    Cmd := Field(Line, 0);
    Was := 0;
    { a read-only step must leave the document as it found it: the batch DRC and the read-backs can mark an unchanged document modified }
    if (Cmd = 'DRC') or (Cmd = 'PCBEXTENT') or (Cmd = 'PCBCHECK') or (Cmd = 'FPINFO') or (Cmd = 'DRAWCHECK') then Was := DocDirty(Field(Line, 1)) + 1;
    DispatchStep(Line);
    if (Was = 1) and (not Failed) then
    begin
        D := Client.GetDocumentByPath(Field(Line, 1));
        if (D <> nil) then
            if (IntToStr(D.Modified) <> '0') then
            begin
                D.SetModified(False);
                Log('cleared the modified mark a read-only ' + Cmd + ' left');
            end;
    end;
end;

procedure Run;
var
    Req : TStringList;
    i   : Integer;
begin
    Dir := 'C:\Users\Public\pcb-advisor-bridge\';
    LogLines := TStringList.Create;
    Resp := TStringList.Create;
    Req := TStringList.Create;
    try
        Req.LoadFromFile(Dir + 'request.txt');
        Say('START');
        Flag('start.flag');
        Failed := False;
        i := 0;
        while (i < Req.Count) and (not Failed) do      { a refused step ends the run: later steps would work on its mess }
        begin
            if (Trim(Req[i]) <> '') then
            begin
                Dispatch(Req[i]);
                if (not Failed) then Say('OK ' + IntToStr(i));
            end;
            i := i + 1;
        end;
        if (not Failed) then Say('DONE');
        Flag('end.flag');
    finally
        Req.Free;
    end;
end;
