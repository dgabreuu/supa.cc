[CmdletBinding()]
param(
    [switch] $Yes,
    [switch] $DryRun,
    [switch] $Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SupabaseVersion = "2.109.1"
$SupaCcVersion = "0.5.5"
$SupabaseReleaseUrl = "https://github.com/supabase/cli/releases/download/v$SupabaseVersion"
$SupabaseArtifactAmd64 = "supabase_2.109.1_windows_amd64.zip"
$SupabaseArtifactArm64 = "supabase_2.109.1_windows_arm64.zip"
$PythonVersion = "3.14.6"
$PythonInstallerAmd64 = "python-3.14.6-amd64.exe"
$PythonInstallerArm64 = "python-3.14.6-arm64.exe"
$PythonInstallerSha256Amd64 = "14b3e9a710a3fcf0bd9b55ab6b60412bd91227563f813fc49040cabc0209e0bd"
$PythonInstallerSha256Arm64 = "517412448c44f0583c994723640e208ca82723e340b0cb6a667696ba2eea63fc"
$script:Phase = "planning"
$script:Plan = [System.Collections.Generic.List[string]]::new()

function Show-Usage {
    @"
Install Supa.cc and its required runtime dependencies.

Usage: install.ps1 [-Yes] [-DryRun] [-Help]

  -Yes      Skip the Supa.cc confirmation. Native system prompts remain.
  -DryRun   Print the installation plan without changing the system.
  -Help     Show this help.
"@
}

function Stop-Installation {
    param([Parameter(Mandatory)][string] $Message)
    throw "Supa.cc installer failed during $($script:Phase): $Message"
}

function Invoke-Python {
    param(
        [Parameter(Mandatory)] $Python,
        [Parameter(Mandatory)][string[]] $Arguments
    )
    $allArguments = @($Python.PrefixArguments) + $Arguments
    & $Python.Command @allArguments
    if ($LASTEXITCODE -ne 0) {
        Stop-Installation "Python command failed."
    }
}

function Test-PythonCandidate {
    param([string] $Command, [string[]] $PrefixArguments)
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        return $false
    }
    $arguments = @($PrefixArguments) + @(
        "-c",
        "import sys; raise SystemExit(sys.version_info < (3, 11))"
    )
    & $Command @arguments 2>$null
    return $LASTEXITCODE -eq 0
}

function Get-CompatiblePython {
    if (Test-PythonCandidate -Command "py" -PrefixArguments @("-3")) {
        return [pscustomobject]@{
            Command = "py"
            PrefixArguments = @("-3")
        }
    }
    foreach ($candidate in @("python", "python3")) {
        if (Test-PythonCandidate -Command $candidate -PrefixArguments @()) {
            return [pscustomobject]@{
                Command = $candidate
                PrefixArguments = @()
            }
        }
    }
    return $null
}

function Test-PipxModule {
    param($Python)
    if (-not $Python) {
        return $false
    }
    $arguments = @($Python.PrefixArguments) + @("-m", "pipx", "--version")
    & $Python.Command @arguments *> $null
    return $LASTEXITCODE -eq 0
}

function Get-Architecture {
    $architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    switch ($architecture) {
        "X64" { return "amd64" }
        "Arm64" { return "arm64" }
        default { Stop-Installation "Only Windows x64 and arm64 are supported." }
    }
}

function Test-SupabaseCompatible {
    $command = Get-Command "supabase" -ErrorAction SilentlyContinue
    if (-not $command) {
        return $false
    }
    try {
        $output = (& $command.Source --version 2>$null | Out-String).Trim()
        $match = [regex]::Match($output, "(?m)(?:^|\s)(\d+\.\d+\.\d+)(?:\s|$)")
        return $match.Success -and ([version]$match.Groups[1].Value -ge [version]$SupabaseVersion)
    }
    catch {
        return $false
    }
}

function Get-SupaChannel {
    $command = Get-Command "supa.cc" -ErrorAction SilentlyContinue
    if (-not $command) {
        return "missing"
    }
    $path = $command.Source
    if ($path -match "[\\/]pipx[\\/]venvs[\\/]supa(?:-cc|\.cc)[\\/]" -or
        $path -match "[\\/]\.local[\\/]bin[\\/]") {
        return "pipx"
    }
    return "other"
}

function Test-SupaCompatible {
    $command = Get-Command "supa.cc" -ErrorAction SilentlyContinue
    if (-not $command) {
        return $false
    }
    try {
        $output = (& $command.Source --version 2>$null | Out-String).Trim()
        $match = [regex]::Match($output, "(?m)(?:^|\s)(\d+\.\d+\.\d+)(?:\s|$)")
        return $match.Success -and ([version]$match.Groups[1].Value -ge [version]$SupaCcVersion)
    }
    catch {
        return $false
    }
}

function Assert-InstallationChannel {
    $channel = Get-SupaChannel
    if ($channel -ne "missing" -and $channel -ne "pipx") {
        Stop-Installation "Supa.cc is already installed through '$channel'. Remove it before using the pipx bootstrap."
    }
}

function Add-PlanItem {
    param([string] $Item)
    $script:Plan.Add($Item)
}

function Build-Plan {
    param([string] $Architecture, $Python)
    $script:Plan.Clear()
    if (-not $Python) {
        if (Get-Command "winget" -ErrorAction SilentlyContinue) {
            Add-PlanItem "Install Python 3.14 for the current user with winget"
        }
        else {
            Add-PlanItem "Download the official pinned Python $PythonVersion $Architecture installer and verify SHA-256"
        }
    }
    if (-not (Test-SupabaseCompatible)) {
        $artifact = if ($Architecture -eq "arm64") { $SupabaseArtifactArm64 } else { $SupabaseArtifactAmd64 }
        Add-PlanItem "Download $SupabaseReleaseUrl/$artifact"
        Add-PlanItem "Download $SupabaseReleaseUrl/checksums.txt and require a valid SHA-256 checksum"
        Add-PlanItem "Install Supabase CLI in the current user's application directory"
    }
    $supaChannel = Get-SupaChannel
    if ($supaChannel -eq "missing") {
        if (-not (Test-PipxModule -Python $Python)) {
            Add-PlanItem "python -m pip install --user pipx"
        }
        Add-PlanItem "python -m pipx ensurepath"
        Add-PlanItem "python -m pipx install supa.cc"
        Add-PlanItem "Update the persistent user PATH and current PowerShell PATH"
    }
    elseif (-not (Test-SupaCompatible)) {
        if (-not (Test-PipxModule -Python $Python)) {
            Add-PlanItem "python -m pip install --user pipx"
        }
        Add-PlanItem "python -m pipx upgrade supa.cc"
    }
    Add-PlanItem "Run supa.cc --version"
    Add-PlanItem "Run supa.cc doctor --installation-check"
}

function Write-Plan {
    param([string] $Architecture)
    Write-Output "Supa.cc installation plan (windows/$Architecture):"
    foreach ($item in $script:Plan) {
        Write-Output "  - $item"
    }
}

function Confirm-Plan {
    if ($Yes) {
        return
    }
    if ([Console]::IsInputRedirected) {
        Stop-Installation "No interactive console is available. Re-run with -Yes after reviewing the plan."
    }
    $answer = Read-Host "Continue? [y/N]"
    if ($answer -notmatch "^(?i:y|yes)$") {
        Stop-Installation "Installation cancelled."
    }
}

function Test-Checksum {
    param(
        [Parameter(Mandatory)][string] $Artifact,
        [Parameter(Mandatory)][string] $Checksums
    )
    $fileName = [IO.Path]::GetFileName($Artifact)
    $expected = $null
    foreach ($line in Get-Content -LiteralPath $Checksums) {
        $match = [regex]::Match(
            $line,
            "^([0-9a-fA-F]{64})\s+" + [regex]::Escape($fileName) + "$"
        )
        if ($match.Success) {
            $expected = $match.Groups[1].Value.ToLowerInvariant()
            break
        }
    }
    if (-not $expected) {
        Stop-Installation "Missing or invalid checksum for $fileName."
    }
    $actual = (Get-FileHash -LiteralPath $Artifact -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
        Stop-Installation "SHA-256 checksum mismatch for $fileName."
    }
}

function Get-RefreshedPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    return (@($machinePath, $userPath) | Where-Object { $_ }) -join ";"
}

function Add-UserPath {
    param([Parameter(Mandatory)][string] $Directory)
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $entries = @($userPath -split ";" | Where-Object { $_ })
    if ($entries -notcontains $Directory) {
        $updated = (@($Directory) + $entries) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $updated, "User")
    }
    $currentEntries = @($env:PATH -split ";")
    if ($currentEntries -notcontains $Directory) {
        $env:PATH = "$Directory;$env:PATH"
    }
}

function Install-Python {
    param([string] $Architecture, [string] $TemporaryDirectory)
    $script:Phase = "Python installation"
    if (Get-Command "winget" -ErrorAction SilentlyContinue) {
        & winget install --id Python.Python.3.14 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            Stop-Installation "winget could not install Python."
        }
    }
    else {
        $fileName = if ($Architecture -eq "arm64") { $PythonInstallerArm64 } else { $PythonInstallerAmd64 }
        $url = "https://www.python.org/ftp/python/$PythonVersion/$fileName"
        $destination = Join-Path $TemporaryDirectory $fileName
        $expected = if ($Architecture -eq "arm64") { $PythonInstallerSha256Arm64 } else { $PythonInstallerSha256Amd64 }
        Invoke-WebRequest -Uri $url -OutFile $destination -UseBasicParsing
        $actual = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expected) {
            Stop-Installation "Python installer SHA-256 checksum mismatch."
        }
        $process = Start-Process -FilePath $destination -ArgumentList @(
            "/quiet",
            "InstallAllUsers=0",
            "PrependPath=1",
            "Include_test=0"
        ) -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            Stop-Installation "The official Python installer failed."
        }
    }
    $env:PATH = Get-RefreshedPath
    $python = Get-CompatiblePython
    if (-not $python) {
        Stop-Installation "Python 3.11 or newer is unavailable after installation."
    }
    return $python
}

function Install-SupabaseCli {
    param([string] $Architecture, [string] $TemporaryDirectory)
    if (Test-SupabaseCompatible) {
        return
    }
    $script:Phase = "Supabase CLI installation"
    $artifact = if ($Architecture -eq "arm64") { $SupabaseArtifactArm64 } else { $SupabaseArtifactAmd64 }
    $archivePath = Join-Path $TemporaryDirectory $artifact
    $checksumsPath = Join-Path $TemporaryDirectory "checksums.txt"
    Invoke-WebRequest -Uri "$SupabaseReleaseUrl/$artifact" -OutFile $archivePath -UseBasicParsing
    Invoke-WebRequest -Uri "$SupabaseReleaseUrl/checksums.txt" -OutFile $checksumsPath -UseBasicParsing
    Test-Checksum -Artifact $archivePath -Checksums $checksumsPath
    $expanded = Join-Path $TemporaryDirectory "supabase"
    Expand-Archive -LiteralPath $archivePath -DestinationPath $expanded
    $installDirectory = Join-Path $env:LOCALAPPDATA "Supa.cc\bin"
    New-Item -ItemType Directory -Path $installDirectory -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $expanded "supabase.exe") -Destination (Join-Path $installDirectory "supabase.exe") -Force
    Add-UserPath -Directory $installDirectory
}

function Install-SupaCc {
    param($Python)
    $channel = Get-SupaChannel
    if ($channel -ne "missing" -and (Test-SupaCompatible)) {
        return
    }
    $script:Phase = "pipx and Supa.cc installation"
    if (-not (Test-PipxModule -Python $Python)) {
        Invoke-Python -Python $Python -Arguments @("-m", "pip", "install", "--user", "pipx")
    }
    if ($channel -eq "missing") {
        Invoke-Python -Python $Python -Arguments @("-m", "pipx", "ensurepath")
        Invoke-Python -Python $Python -Arguments @("-m", "pipx", "install", "supa.cc")
    }
    else {
        Invoke-Python -Python $Python -Arguments @("-m", "pipx", "upgrade", "supa.cc")
    }
    $environmentArguments = @($Python.PrefixArguments) + @("-m", "pipx", "environment", "--value", "PIPX_BIN_DIR")
    $pipxBin = (& $Python.Command @environmentArguments | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $pipxBin) {
        Stop-Installation "pipx did not report its application directory."
    }
    Add-UserPath -Directory $pipxBin
}

function Test-FinalInstallation {
    $script:Phase = "final validation"
    & "supa.cc" --version
    if ($LASTEXITCODE -ne 0) {
        Stop-Installation "Supa.cc version validation failed."
    }
    & "supa.cc" doctor --installation-check
    if ($LASTEXITCODE -eq 0) {
        return
    }
    Write-Warning "The software is installed, but Windows Credential Manager or the environment is still blocked."
    if ([Console]::IsInputRedirected) {
        Stop-Installation "Resolve the reported requirement and run 'supa.cc doctor --installation-check' again."
    }
    Read-Host "Resolve the native credential-store issue, then press Enter to retry" | Out-Null
    & "supa.cc" doctor --installation-check
    if ($LASTEXITCODE -ne 0) {
        Stop-Installation "The installation check is still blocked; apply the reported remediation and retry."
    }
}

function Invoke-Main {
    if ($Help) {
        Show-Usage
        return
    }
    $script:Phase = "environment detection"
    $architecture = Get-Architecture
    Assert-InstallationChannel
    $python = Get-CompatiblePython
    Build-Plan -Architecture $architecture -Python $python
    Write-Plan -Architecture $architecture
    Confirm-Plan

    if ($DryRun) {
        Write-Output "Dry run complete; no changes were made."
        return
    }

    $temporaryDirectory = Join-Path ([IO.Path]::GetTempPath()) ("supa-cc-install-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $temporaryDirectory | Out-Null
    try {
        if (-not $python) {
            $python = Install-Python -Architecture $architecture -TemporaryDirectory $temporaryDirectory
        }
        Install-SupabaseCli -Architecture $architecture -TemporaryDirectory $temporaryDirectory
        Install-SupaCc -Python $python
        Test-FinalInstallation
        Write-Output "Supa.cc is ready."
    }
    finally {
        if (Test-Path -LiteralPath $temporaryDirectory) {
            Remove-Item -LiteralPath $temporaryDirectory -Recurse -Force
        }
    }
}

if ($MyInvocation.InvocationName -ne ".") {
    try {
        Invoke-Main
        exit 0
    }
    catch {
        Write-Error $_.Exception.Message
        exit 1
    }
}
