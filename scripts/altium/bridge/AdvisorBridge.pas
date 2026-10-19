{ PCB advisor <-> Altium bridge. Runs inside Altium Designer (DelphiScript).

  The request/response-through-files idea and the way a script is started from the command line are adapted from
  altium-mcp (MIT, Copyright (c) 2025 Siddharth Ahuja, see LICENSE-altium-mcp). Everything else is our own.

  The Python side (scripts/altium/bridge.py) writes <exchange>\request.txt: one command per line, fields separated
  by TAB, a line break inside a text written as the two characters \n. This script runs the commands in order and
  writes <exchange>\response.txt (START first, then one OK/ERR line per command, DONE last) and flushes
  <exchange>\log.txt after every step, so a runtime error (which try/except does not catch and which leaves the
  executor paused) still shows the statement that failed.

  Commands:  PROJECT prj | SCH path | PCB path | SAVEPRJ prj | CLEAR path | PARAM path name value
             FRAME path x y w h text | TITLEBLOCK path | SAVE path | PING
             RULE pcb kind name scope1 scope2 priority prop=value... | ADDDOC prj path | OUTJOB path medium basepath }

const
    REPLACEALL = 1;
    TAG = '[advisor]';

var
    LogLines : TStringList;
    Resp     : TStringList;
    Dir      : String;
    CurPrj   : String;

procedure Log(Msg: String);
begin
    LogLines.Add(Msg);
    LogLines.SaveToFile(Dir + 'log.txt');
end;

procedure Say(Msg: String);
begin
    Resp.Add(Msg);
    Resp.SaveToFile(Dir + 'response.txt');
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

{ RULE pcb kind name scope1 scope2 priority prop=value ...  updates the rule of that name, else adds one (the priority field is unused: Altium refuses it) }
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
    if Old then
        R.BeginModify
    else
        R := NewRule(Field(Line, 2));
    if (R = nil) then
    begin
        Say('ERR rule kind not supported ' + Field(Line, 2));
        Exit;
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
        R.EndModify
    else
        B.AddPCBObject(R);
    Log('rule ' + Field(Line, 3));
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

{ OUTJOB path medium basepath: generate the files of one Folder Structure container of the OutJob }
procedure RunOutJob(Path: String; Medium: String; Base: String);
var
    D : IDispatch;
begin
    D := Client.GetDocumentByPath(Path);
    if (D = nil) then D := Client.OpenDocument('OUTPUTJOB', Path);
    if (D = nil) then
    begin
        Say('ERR could not open the OutJob ' + Path);
        Exit;
    end;
    Client.ShowDocument(D);
    ResetParameters;
    AddStringParameter('Action', 'Run');
    AddStringParameter('OutputMedium', Medium);
    AddStringParameter('ObjectKind', 'OutputBatch');
    AddStringParameter('OutputBasePath', Base);
    RunProcess('WorkspaceManager:GenerateReport');
    Log('outjob ran ' + Medium);
end;

procedure Dispatch(Line: String);
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
    else if (Cmd = 'ADDDOC') then AddDocument(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'OUTJOB') then RunOutJob(Field(Line, 1), Field(Line, 2), Field(Line, 3))
    else if (Cmd = 'PING') then Log('ping')
    else Say('ERR unknown command ' + Cmd);
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
        for i := 0 to Req.Count - 1 do
        begin
            if (Trim(Req[i]) <> '') then
            begin
                Dispatch(Req[i]);
                Say('OK ' + IntToStr(i));
            end;
        end;
        Say('DONE');
    finally
        Req.Free;
    end;
end;
