{ Acceptance oracle probe: read-only questions to a running Altium Designer, independent of the product's bridge.
  Request: <Dir>\request.txt, one command per line, fields separated by TAB. Answer: <Dir>\response.txt (START, then one line per
  command, DONE last) and <Dir>\log.txt; end.flag when finished. Nothing here changes a document: DRC writes only a report file
  (Altium's own text report), COMPILE writes a plain-text list, CLOSE closes documents WITHOUT saving (only those under a given folder).

  DRC <pcb> <report>            open the board by path, run Altium's batch design rule check, Altium writes <report>
  COMPILE <prj> <out>           compile the project, write violations and nets (pins per net) to <out>
  OPEN <prefix> <out>           list open documents whose path starts with <prefix>
  CLOSE <prefix>                close (no save) every open document whose path starts with <prefix>
  MODAL <text>                  show a message box in Altium (a modal dialog raised by the oracle); returns when it is closed
  PING }

var
    Dir      : String;
    LogLines : TStringList;
    Resp     : TStringList;
    Failed   : Boolean;

procedure SaveRetry(SL: TStringList; Path: String);
var
    n  : Integer;
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

function StartsWith(S, Prefix: String): Boolean;
begin
    Result := (Length(S) >= Length(Prefix)) and (UpperCase(Copy(S, 1, Length(Prefix))) = UpperCase(Prefix));
end;

procedure ProbeDrc(Path: String; Report: String);
var
    B  : IDispatch;
    D  : IDispatch;
    ok : Boolean;
begin
    B := nil;
    if (PCBServer <> nil) then B := PCBServer.GetPCBBoardByPath(Path);
    if (B = nil) then
    begin
        D := Client.OpenDocument('PCB', Path);
        if (D <> nil) then D.Focus;
        if (PCBServer <> nil) then B := PCBServer.GetPCBBoardByPath(Path);
    end;
    if (B = nil) then
    begin
        Say('ERR could not open ' + Path);
        Exit;
    end;
    if FileExists(Report) then DeleteFile(Report);
    ok := B.RunBatchDesignRuleCheck(Report, eDRC_Text, False, False);
    if (not FileExists(Report)) then
    begin
        Say('ERR the design rule check did not write its report');
        Exit;
    end;
    Log('drc ' + Report + ' clean=' + BoolToStr(ok, True));
end;

procedure ProbeCompile(PrjPath: String; Outp: String);
var
    Prj, Doc, Net, Pin, Viol : IDispatch;
    i, j, n : Integer;
    SL : TStringList;
begin
    Log('compile: project ' + PrjPath);
    Prj := GetWorkspace.DM_GetProjectFromPath(PrjPath);
    if (Prj = nil) then Prj := GetWorkspace.DM_OpenProject(PrjPath, False);
    if (Prj = nil) then
    begin
        Say('ERR cannot open ' + PrjPath);
        Exit;
    end;
    Log('compile: DM_Compile of ' + PrjPath);
    Prj.DM_Compile;
    Log('compile: DM_Compile returned');
    SL := TStringList.Create;
    try
        n := Prj.DM_ViolationCount;
        SL.Add('VIOLATIONS ' + IntToStr(n));
        for i := 0 to n - 1 do
        begin
            Viol := Prj.DM_Violations(i);
            SL.Add('V' + #9 + Viol.DM_ErrorLevelString + #9 + Viol.DM_ShortDescriptorString + #9 + Viol.DM_LongDescriptorString);
        end;
        Doc := Prj.DM_DocumentFlattened;
        if (Doc = nil) then Doc := Prj.DM_TopLevelPhysicalDocument;
        if (Doc = nil) then
        begin
            SL.Add('NODOC');
        end
        else
        begin
            SL.Add('NETS ' + IntToStr(Doc.DM_NetCount));
            for i := 0 to Doc.DM_NetCount - 1 do
            begin
                Net := Doc.DM_Nets(i);
                for j := 0 to Net.DM_PinCount - 1 do
                begin
                    Pin := Net.DM_Pins(j);
                    SL.Add('P' + #9 + Net.DM_NetName + #9 + Pin.DM_FullName);
                end;
            end;
        end;
        SL.SaveToFile(Outp);
    finally
        SL.Free;
    end;
    Log('compile ' + Outp);
end;

{ the documents of every open project whose file lies under Prefix (the scratch copy), plus the project file itself }
procedure ProbeOpen(Prefix: String; Outp: String);
var
    i, k : Integer;
    P    : IDispatch;
    Path : String;
    D    : IDispatch;
    SL   : TStringList;
begin
    SL := TStringList.Create;
    try
        for i := 0 to GetWorkspace.DM_ProjectCount - 1 do
        begin
            P := GetWorkspace.DM_Projects(i);
            if StartsWith(P.DM_ProjectFullPath, Prefix) then
            begin
                SL.Add('PRJ' + #9 + P.DM_ProjectFullPath);
                for k := 0 to P.DM_LogicalDocumentCount - 1 do
                begin
                    Path := P.DM_LogicalDocuments(k).DM_FullPath;
                    D := Client.GetDocumentByPath(Path);
                    if (D <> nil) then SL.Add('DOC' + #9 + Path + #9 + IntToStr(D.Modified));
                end;
            end;
        end;
        SL.SaveToFile(Outp);
    finally
        SL.Free;
    end;
    Log('open listed');
end;

procedure ProbeClose(Prefix: String);
var
    i, k, n, tries : Integer;
    P    : IDispatch;
    Path : String;
    D    : IDispatch;
begin
    n := 0;
    for i := 0 to GetWorkspace.DM_ProjectCount - 1 do
    begin
        P := GetWorkspace.DM_Projects(i);
        if StartsWith(P.DM_ProjectFullPath, Prefix) then
            for k := 0 to P.DM_LogicalDocumentCount - 1 do
            begin
                Path := P.DM_LogicalDocuments(k).DM_FullPath;
                tries := 0;
                D := Client.GetDocumentByPath(Path);
                while (D <> nil) and (tries < 5) do
                begin
                    D.SetModified(False);
                    Client.CloseDocument(D);
                    n := n + 1;
                    tries := tries + 1;
                    D := Client.GetDocumentByPath(Path);
                end;
            end;
    end;
    Log('closed ' + IntToStr(n));
end;

procedure Dispatch(Line: String);
var
    Cmd : String;
begin
    Cmd := Field(Line, 0);
    Log('> ' + Cmd);
    if (Cmd = 'DRC') then ProbeDrc(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'COMPILE') then ProbeCompile(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'OPEN') then ProbeOpen(Field(Line, 1), Field(Line, 2))
    else if (Cmd = 'CLOSE') then ProbeClose(Field(Line, 1))
    else if (Cmd = 'MODAL') then
    begin
        Log('modal up');
        ShowMessage(Field(Line, 1));
        Log('modal closed');
    end
    else if (Cmd = 'PING') then Log('ping')
    else Say('ERR unknown command ' + Cmd);
end;

procedure Run;
var
    Req : TStringList;
    i   : Integer;
begin
    Dir := 'C:\Users\Public\acc-probe\';
    LogLines := TStringList.Create;
    Resp := TStringList.Create;
    Req := TStringList.Create;
    try
        Req.LoadFromFile(Dir + 'request.txt');
        Say('START');
        Flag('start.flag');
        Failed := False;
        i := 0;
        while (i < Req.Count) and (not Failed) do
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
