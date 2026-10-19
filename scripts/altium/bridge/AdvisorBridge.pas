{ PCB advisor <-> Altium bridge. Runs inside Altium Designer (DelphiScript).

  The request/response-through-files idea and the way a script is started from the command line are adapted from
  altium-mcp (MIT, Copyright (c) 2025 Siddharth Ahuja, see LICENSE-altium-mcp). Everything else is our own.

  The Python side (scripts/altium/bridge.py) writes <exchange>\request.txt: one command per line, fields separated
  by TAB, a line break inside a text written as the two characters \n. This script runs the commands in order and
  writes <exchange>\response.txt (START first, then one OK/ERR line per command, DONE last) and flushes
  <exchange>\log.txt after every step, so a runtime error (which try/except does not catch and which leaves the
  executor paused) still shows the statement that failed.

  Commands:  PROJECT prj | SCH path | PCB path | SAVEPRJ prj | CLEAR path | PARAM path name value
             FRAME path x y w h text | TITLEBLOCK path | SAVE path | PING }

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
