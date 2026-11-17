# pcb-advisor installer for Windows. Safe to run again: a second run repairs, it never duplicates or deletes.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/ilaish5/pcb-advisor/main/install.ps1 | iex"
#   .\install.ps1            (from a clone or an unpacked ZIP: repairs it in place; install.bat calls this)
#
# Finds Python 3.10+ (offers winget if missing), gets the code (git clone, or the ZIP when git is missing), makes
# .venv, installs requirements, detects Claude Code or Antigravity (asks which to install) and offers the sign-in, runs `pcb.py doctor`, starts the server.
# Questions default to YES (Enter). No administrator rights: winget installs use --scope user.
#
# Settings (environment variables, so they also work through `irm | iex`; -Yes and -Dir <folder> work on the file):
#   PCB_DIR target folder (default: this clone, or %USERPROFILE%\pcb-advisor) | PCB_REPO clone source (default the
#   GitHub URL; a local path works) | PCB_REF branch or tag | PCB_YES=1 no questions | PCB_ENGINE=claude|agy choose
#   the AI engine without asking (nothing installed and PCB_YES=1 means claude) | PCB_NO_ENGINE=1 skip the engine
#   install and sign-in (PCB_NO_CLAUDE=1 is the same) | PCB_NO_START=1 do not start the server | PCB_NO_GIT=1 act as if git is missing (ZIP
#   route) | PCB_ZIP_URL ZIP address or path.
# This file is plain ASCII on purpose (Windows PowerShell 5.1 reads a BOM-less file as the ANSI code page) and never
# calls `exit` (under `iex` that would close the student's terminal).

# ---- the install log: this run's steps, versions and console output, kept on this machine in <install folder>\logs\install-*.log
# (a temp file until the folder exists; its path is printed when something fails). Nothing is uploaded. Every failure here is ignored.
$script:PcbTmpNotes = $null; $script:PcbTmpTrans = $null; $script:PcbDir = $null; $script:PcbStamp = ''
$script:PcbStep = ''; $script:PcbStepFailed = $false; $script:PcbFailed = $false

function Pcb-Note($m) {
    if ($script:PcbTmpNotes) { try { Add-Content -LiteralPath $script:PcbTmpNotes -Value ('{0}  {1}' -f (Get-Date -Format 'HH:mm:ss'), $m) -Encoding UTF8 } catch { } }
}
function Pcb-StepEnd {
    if ($script:PcbStep) { $tag = if ($script:PcbStepFailed) { '[FAIL] ' } else { '[ok]   ' }; Pcb-Note ($tag + $script:PcbStep); $script:PcbStep = '' }
}
function Pcb-StepBegin($name) { Pcb-StepEnd; $script:PcbStep = $name; $script:PcbStepFailed = $false }
function Pcb-Start {
    try {
        $script:PcbStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $tmp = [IO.Path]::GetTempPath()
        $script:PcbTmpNotes = Join-Path $tmp ("pcb-install-$($script:PcbStamp)-notes.txt")
        $trans = Join-Path $tmp ("pcb-install-$($script:PcbStamp)-console.txt")
        Pcb-Note ("install started; PowerShell $($PSVersionTable.PSVersion); " + [Environment]::OSVersion.VersionString)
        Start-Transcript -LiteralPath $trans -Force | Out-Null
        $script:PcbTmpTrans = $trans
    } catch { }
}
function Pcb-Finish {
    if (-not $script:PcbTmpNotes) { return }
    try {
        Pcb-StepEnd
        Pcb-Note ('result: ' + $(if ($script:PcbFailed) { 'FAILED' } else { 'ok' }))
        if ($script:PcbTmpTrans) { try { Stop-Transcript | Out-Null } catch { } }
        $console = ''
        if ($script:PcbTmpTrans -and (Test-Path -LiteralPath $script:PcbTmpTrans)) { $console = [string](Get-Content -Raw -LiteralPath $script:PcbTmpTrans) }
        $console = $console -replace '(?i)(sk-[A-Za-z0-9_-]{16,}|bearer\s+[A-Za-z0-9._~+/=-]{12,}|(token|api[_-]?key|password|secret)\s*[=:]\s*\S+)', '[hidden]'
        $notes = [string](Get-Content -Raw -LiteralPath $script:PcbTmpNotes)
        $dest = $null
        if ($script:PcbDir -and (Test-Path -LiteralPath $script:PcbDir)) {
            try {
                $folder = Join-Path $script:PcbDir 'logs'
                New-Item -ItemType Directory -Force -Path $folder | Out-Null
                $dest = Join-Path $folder ("install-$($script:PcbStamp).log")
            } catch { $dest = $null }
        }
        if (-not $dest) { $dest = Join-Path ([IO.Path]::GetTempPath()) ("pcb-install-$($script:PcbStamp).log") }
        Set-Content -LiteralPath $dest -Value ($notes + "`r`n---- console output ----`r`n" + $console) -Encoding UTF8
        Remove-Item -LiteralPath $script:PcbTmpNotes -ErrorAction SilentlyContinue
        if ($script:PcbTmpTrans) { Remove-Item -LiteralPath $script:PcbTmpTrans -ErrorAction SilentlyContinue }
        $script:PcbTmpNotes = $null; $script:PcbTmpTrans = $null
        if ($script:PcbFailed) { Write-Host "The install log is saved at: $dest" }
    } catch { }
}

# Runs a native command with its output shown AND written to the log (Windows PowerShell 5.1 transcripts miss native output).
# $LASTEXITCODE is the command's own when this returns.
function Pcb-Run {
    $exe = $args[0]; $rest = @(); if ($args.Count -gt 1) { $rest = $args[1..($args.Count - 1)] }
    Pcb-Note ('run: ' + (($args | ForEach-Object { "$_" }) -join ' '))
    & $exe @rest 2>&1 | ForEach-Object { $line = "$_"; Write-Host $line; Pcb-Note ('  ' + $line) }
}

function Install-PcbAdvisor {
    param([string[]]$Argv)
    Pcb-Start
    $done = $false
    try { Install-PcbAdvisorCore -Argv $Argv; $done = $true }
    finally {
        if (-not $done) { $script:PcbFailed = $true; Pcb-Note 'stopped by an unexpected error' }
        Pcb-Finish
    }
}

function Install-PcbAdvisorCore {
    param([string[]]$Argv)
    $ErrorActionPreference = 'Continue'       # native tools write progress to stderr; we check $LASTEXITCODE ourselves
    try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072 } catch { }

    $yes = ($env:PCB_YES -eq '1') -or ($Argv -contains '-Yes')
    $repoUrl = if ($env:PCB_REPO) { $env:PCB_REPO } else { 'https://github.com/ilaish5/pcb-advisor.git' }
    $ref = $env:PCB_REF
    $zipRef = if ($ref) { $ref } else { 'main' }
    $zipUrl = if ($env:PCB_ZIP_URL) { $env:PCB_ZIP_URL } else { "https://github.com/ilaish5/pcb-advisor/archive/refs/heads/$zipRef.zip" }

    function Say($m) { Write-Host $m }
    function Step($m) { Pcb-StepBegin $m; Write-Host ''; Write-Host "== $m" }
    function Fail($m) { $script:PcbFailed = $true; $script:PcbStepFailed = $true; Pcb-Note "FAIL: $m"; Write-Host ''; Write-Host "ERROR: $m" -ForegroundColor Red }

    # Y/n, Enter = yes. No console to ask on (CI, redirected input) = the default.
    function Ask($q) {
        if ($yes) { return $true }
        $interactive = $true
        try { if ([Console]::IsInputRedirected) { $interactive = $false } } catch { }
        if (-not $interactive) { return $true }
        $a = Read-Host "$q [Y/n]"
        return -not ($a -match '^(n|no)$')
    }

    # winget changes PATH for NEW terminals only; re-read it so this one sees the new program.
    function Refresh-Path {
        $m = [Environment]::GetEnvironmentVariable('Path', 'Machine')
        $u = [Environment]::GetEnvironmentVariable('Path', 'User')
        $env:Path = "$m;$u"
    }

    function Find-Python {
        $tries = @(@('py', '-3'), @('python'), @('python3'))
        foreach ($t in $tries) {
            $cmd = Get-Command $t[0] -ErrorAction SilentlyContinue
            if (-not $cmd) { continue }
            if ($cmd.Source -like '*WindowsApps*') { continue }      # the Microsoft Store shortcut, not Python
            $pre = @(); if ($t.Count -gt 1) { $pre = $t[1..($t.Count - 1)] }
            $out = & $cmd.Source @pre -c "import sys; print(sys.executable) if sys.version_info >= (3,10) else sys.exit(1)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) { return ($out | Select-Object -First 1) }
        }
        $known = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending
        foreach ($k in $known) {
            & $k.FullName -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $k.FullName }
        }
        return $null
    }

    function Winget-Install($id) {
        Write-Host "Installing $id with winget. This can take a few minutes; wait for it to finish..."
    & winget install -e --id $id --scope user --accept-package-agreements --accept-source-agreements 2>&1 | ForEach-Object { Write-Host "$_"; Pcb-Note ("  $_") }
        Refresh-Path
    }

    # ---- where
    $dir = $env:PCB_DIR
    for ($i = 0; $i -lt $Argv.Count - 1; $i++) { if ($Argv[$i] -eq '-Dir') { $dir = $Argv[$i + 1] } }
    if (-not $dir) {
        if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'pcb.py'))) { $dir = $PSScriptRoot }
        else { $dir = Join-Path $env:USERPROFILE 'pcb-advisor' }
    }
    $script:PcbDir = $dir
    Pcb-Note "install folder: $dir"

    # ---- 1. Python
    Step 'Python'
    $py = Find-Python
    if (-not $py -and (Get-Command winget -ErrorAction SilentlyContinue)) {
        if (Ask 'Python 3.10 or newer was not found. Install it with winget (no administrator needed)?') {
            Winget-Install 'Python.Python.3.12'
            $py = Find-Python
        }
    }
    if (-not $py) {
        Fail 'Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH"), open a NEW terminal, and run this again.'
        return
    }
    Say "using $py"
    try { Pcb-Note ('python: ' + $py + ' = ' + ((& $py --version 2>&1) -join ' ')) } catch { }

    # ---- 2. the code
    Step "pcb-advisor code in $dir"
    $haveGit = [bool](Get-Command git -ErrorAction SilentlyContinue)
    if (-not $haveGit -and $env:PCB_NO_GIT -ne '1' -and -not (Test-Path (Join-Path $dir '.git')) -and (Get-Command winget -ErrorAction SilentlyContinue)) {
        if (Ask 'git is not installed (needed for the in-app Update). Install it with winget?') {
            Winget-Install 'Git.Git'
            $haveGit = [bool](Get-Command git -ErrorAction SilentlyContinue)
            if (-not $haveGit -and (Test-Path "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe")) {
                $env:Path = "$env:LOCALAPPDATA\Programs\Git\cmd;$env:Path"; $haveGit = $true
            }
        }
    }
    if ($env:PCB_NO_GIT -eq '1') { $haveGit = $false }
    try { Pcb-Note ('git: ' + $(if ($haveGit) { (& git --version 2>&1) -join ' ' } else { 'not found (the ZIP route is used)' })) } catch { }
    $dirHasGit = Test-Path (Join-Path $dir '.git')
    $dirHasCode = Test-Path (Join-Path $dir 'pcb.py')
    if ($dirHasGit -and $haveGit) {
        $dirty = & git -C $dir status --porcelain --untracked-files=no 2>$null
        if ($dirty) { Say 'you have local edits, so the code was left as it is' }
        else {
            & git -C $dir pull --ff-only 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) { Say 'up to date (git pull)' } else { Say 'kept the current version (could not pull; this is fine offline)' }
        }
    }
    elseif ($dirHasCode -and $haveGit -and (Ask 'This folder is a ZIP copy. Turn it into a git clone so the in-app Update works? (projects and settings stay)')) {
        # reset --hard rewrites only the tool's own files; projects\, config.json and .venv are untracked and untouched.
        $br = if ($ref) { $ref } else { 'main' }
        $ok = $true
        foreach ($a in @(@('init', '-q'), @('remote', 'add', 'origin', $repoUrl), @('fetch', '-q', 'origin', $br),
                         @('reset', '-q', '--hard', 'FETCH_HEAD'), @('branch', '-q', '-M', $br), @('branch', '-q', '-u', "origin/$br"))) {
            & git -C $dir @a 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) { $ok = $false; break }
        }
        if ($ok) { Say "now a git clone on ${br}: Update works" }
        else {
            Remove-Item -Recurse -Force (Join-Path $dir '.git') -ErrorAction SilentlyContinue
            Say 'could not turn it into a clone (network?); kept the ZIP copy as it was'
        }
    }
    elseif ($dirHasCode) { Say 'found an existing install, keeping it' }
    else {
        if ((Test-Path $dir) -and (Get-ChildItem $dir -Force -ErrorAction SilentlyContinue | Select-Object -First 1)) {
            Fail "$dir exists and is not pcb-advisor. Pick another folder: set PCB_DIR=C:\some\folder"
            return
        }
        if ($haveGit) {
            Write-Host 'Downloading pcb-advisor with git (a minute or two)...'
            Pcb-Run git clone $repoUrl $dir
            if ($LASTEXITCODE -ne 0) { Fail 'git clone failed (network, or a proxy: set HTTPS_PROXY).'; return }
            if ($ref) { & git -C $dir checkout $ref 2>&1 | Out-Null }
        }
        else {
            Say 'WARNING: git is not installed, so this uses the ZIP download. Everything works, but the in-app Update stays off.'
            Say '         To get Update later, install git (winget install -e --id Git.Git) and run this installer again.'
            $tmp = Join-Path ([IO.Path]::GetTempPath()) ('pcb-' + [Guid]::NewGuid().ToString('N'))
            New-Item -ItemType Directory -Path $tmp | Out-Null
            $zip = Join-Path $tmp 'src.zip'
            Write-Host 'Downloading the pcb-advisor ZIP (a minute or two)...'
            try {
                if ($zipUrl -match '^https?://') { Invoke-WebRequest -Uri $zipUrl -OutFile $zip -UseBasicParsing }
                else { Copy-Item -LiteralPath ($zipUrl -replace '^file:///', '') -Destination $zip }
                Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $tmp 'x') -Force
            } catch { Fail "could not get or unpack the ZIP: $_"; return }
            $found = Get-ChildItem (Join-Path $tmp 'x') -Recurse -Filter pcb.py -Depth 2 | Select-Object -First 1
            if (-not $found) { Fail 'the ZIP does not contain pcb.py'; return }
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
            Copy-Item -Path (Join-Path $found.DirectoryName '*') -Destination $dir -Recurse -Force
            Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
        }
    }
    if (-not (Test-Path (Join-Path $dir 'pcb.py'))) { Fail "pcb.py is missing in $dir"; return }
    Set-Location -LiteralPath $dir

    # ---- 3. venv + requirements + workspace
    Step 'Private Python environment'
    $venvPy = Join-Path $dir '.venv\Scripts\python.exe'
    if (Test-Path $venvPy) {
        & $venvPy -m pip --version 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { Remove-Item -Recurse -Force (Join-Path $dir '.venv') }
    }
    elseif (Test-Path (Join-Path $dir '.venv')) { Remove-Item -Recurse -Force (Join-Path $dir '.venv') }
    if (-not (Test-Path $venvPy)) {
        Pcb-Run $py -m venv (Join-Path $dir '.venv')
        if ($LASTEXITCODE -ne 0) { Fail 'could not create .venv'; return }
    }
    Write-Host 'Updating pip (a few seconds)...'
    Pcb-Run $venvPy -m pip install --quiet --upgrade pip
    Write-Host 'Installing the Python libraries from requirements.txt. This can take a few minutes and prints nothing until it is done; wait...'
    Pcb-Run $venvPy -m pip install --quiet -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Fail 'installing requirements failed (network or proxy?)'; return }
    & $venvPy pcb.py init
    if ($LASTEXITCODE -ne 0) { Fail 'pcb.py init failed'; return }

    # ---- 4. AI engine (Claude Code or Antigravity) + sign-in
    function Find-Claude {
        $c = Get-Command claude -ErrorAction SilentlyContinue
        if ($c) { return $c.Source }
        $p = Join-Path $env:USERPROFILE '.local\bin\claude.exe'
        if (Test-Path $p) { return $p }
        return $null
    }
    function Find-Agy {
        $c = Get-Command agy -ErrorAction SilentlyContinue
        if ($c) { return $c.Source }
        $p = Join-Path $env:LOCALAPPDATA 'agy\bin\agy.exe'
        if (Test-Path $p) { return $p }
        return $null
    }
    # agent.provider as the person set it in the workspace config.json ('' = never set, so the default applies).
    function Get-SetProvider {
        $cfg = if ($env:PCB_ADVISOR_CONFIG) { $env:PCB_ADVISOR_CONFIG }
               elseif ($env:PCB_ADVISOR_HOME) { Join-Path $env:PCB_ADVISOR_HOME 'config.json' }
               else { Join-Path $dir 'config.json' }
        try {
            $j = Get-Content -Raw -LiteralPath $cfg -ErrorAction Stop | ConvertFrom-Json
            if ($j.agent -and $j.agent.provider) { return [string]$j.agent.provider }
        } catch { }
        return ''
    }
    # False when nobody can answer (CI, redirected input, PCB_YES): then there is no question and no interactive step.
    function Can-Prompt {
        if ($yes) { return $false }
        try { if ([Console]::IsInputRedirected) { return $false } } catch { }
        return $true
    }
    if ($env:PCB_NO_CLAUDE -ne '1' -and $env:PCB_NO_ENGINE -ne '1') {
        Step 'AI engine (Claude Code or Antigravity)'
        $claude = Find-Claude
        $agy = Find-Agy
        $engine = ''                  # 'claude' or 'agy'
        $setProvider = $false         # write agent.provider to the config
        $asked = $false               # the person already said which one, so no second install question
        $explicit = Get-SetProvider
        if ($env:PCB_ENGINE -eq 'claude' -or $env:PCB_ENGINE -eq 'agy') {
            $engine = $env:PCB_ENGINE; $setProvider = $true
        }
        elseif ($explicit -eq 'antigravity') { $engine = 'agy'; Say 'The workspace is set to Antigravity; keeping it.' }
        elseif ($explicit -eq 'claude_code') { $engine = 'claude'; Say 'The workspace is set to Claude Code; keeping it.' }
        elseif ($claude -and $agy) { $engine = 'claude'; Say 'Both found; using Claude Code. Switch in Settings > Engine.' }
        elseif ($agy) { $engine = 'agy'; $setProvider = $true; Say 'Only Antigravity (agy) found; setting it as the engine.' }
        elseif ($claude) { $engine = 'claude' }
        else {
            $pick = '1'
            if (Can-Prompt) {
                Say 'Which AI engine do you have an account for?'
                Say '  1) Claude Code (Claude Pro/Max)'
                Say '  2) Antigravity (Google account)'
                $pick = Read-Host 'Enter = 1'
            }
            if ($pick.Trim() -eq '2') { $engine = 'agy'; $setProvider = $true } else { $engine = 'claude' }
            $asked = $true
        }
        if ($engine -eq 'claude' -and -not $claude) {
            if ($asked -or (Ask 'Claude Code is not installed. Install it now (official installer)?')) {
                Write-Host 'Downloading and installing Claude Code (a minute or two)...'
                try { Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression } catch { Say "The Claude Code installer failed ($_). See docs\ENGINES.md." }
                Refresh-Path
                $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
                $claude = Find-Claude
            }
        }
        if ($engine -eq 'agy' -and -not $agy) {
            if ($asked -or (Ask 'Antigravity (agy) is not installed. Install it now (official installer)?')) {
                Write-Host 'Downloading and installing Antigravity (a minute or two)...'
                try { Invoke-RestMethod https://antigravity.google/cli/install.ps1 | Invoke-Expression } catch { Say "The Antigravity installer failed ($_). See docs\ENGINES.md." }
                Refresh-Path
                $env:Path = "$env:LOCALAPPDATA\agy\bin;$env:Path"
                $agy = Find-Agy
            }
        }
        if ($setProvider) {
            $prov = if ($engine -eq 'agy') { 'antigravity' } else { 'claude_code' }
            & $venvPy pcb.py config agent.provider $prov | Out-Null
            Say "engine set to $prov"
        }
        try { Pcb-Note ('engine: ' + $engine + '; claude: ' + $(if ($claude) { $claude } else { 'not found' }) + '; agy: ' + $(if ($agy) { $agy } else { 'not found' })) } catch { }
        if ($engine -eq 'claude' -and $claude) {
            Say "found $claude"
            & $claude auth status 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                if (Ask 'Sign in to Claude now? (a browser window opens; finish there)') {
                    & $claude auth login
                    & $claude auth status 2>&1 | Out-Null
                    if ($LASTEXITCODE -eq 0) { Say 'signed in' } else { Say 'still not signed in; the app will show how to fix it' }
                }
            }
            else { Say 'signed in' }
        }
        elseif ($engine -eq 'agy' -and $agy) {
            Say "found $agy"
            # agy has no status command: the first run opens the Google sign-in in the browser.
            Say 'To sign in: run `agy` once and sign in with your Google account in the browser, then exit it.'
            if ((Can-Prompt) -and (Ask 'Run agy now to sign in?')) { & $agy }
        }
    }

    # ---- 5. doctor, then start
    Step 'Checking everything'
    Write-Host 'Running the checks (up to a minute; they look for Claude, Altium and the network)...'
    Pcb-Run $venvPy pcb.py doctor --exit-start
    if ($LASTEXITCODE -ne 0) {
        Say ''
        Say 'The server cannot start yet. Fix the FIX lines above, then run this installer again.'
        $script:PcbFailed = $true; $script:PcbStepFailed = $true
        return
    }
    Say ''
    Say "Installed in $dir. Next time: double-click start.bat in that folder."
    if ($env:PCB_NO_START -eq '1') { return }
    Pcb-Finish        # the install is over: save its log now
    $port = if ($env:PCB_ADVISOR_PORT) { $env:PCB_ADVISOR_PORT } else { '8931' }
    Step "Starting pcb-advisor (http://localhost:$port) in its own window."
    # Its own window: closing this installer does not stop the server. Close the new window (or press Ctrl+C there) to stop it.
    Start-Process -FilePath (Join-Path $dir 'start.bat') -WorkingDirectory $dir
    Say 'The pcb-advisor window opened and the browser follows in a few seconds. You can close this installer window.'
}

Install-PcbAdvisor -Argv $args
