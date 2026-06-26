param(
    [string]$InnoCompiler = "",
    [string]$AppVersion = "",
    [switch]$SkipExeBuild,
    [switch]$InstallInnoSetup
)

$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$ExeName = "SafeSweep.exe"
$ExePath = Join-Path $Root "dist\$ExeName"
$InstallerScript = Join-Path $Root "installer\SafeSweep.iss"

function Get-AppVersion {
    $InitPath = Join-Path $Root "src\unused_file_finder\__init__.py"
    $Content = Get-Content -LiteralPath $InitPath -Raw
    if ($Content -match '__version__\s*=\s*"([^"]+)"') {
        return $Matches[1]
    }

    return "1.0.0"
}

function Find-InnoCompiler {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        if (-not (Test-Path -LiteralPath $ExplicitPath)) {
            throw "Compilateur Inno Setup introuvable: $ExplicitPath"
        }
        return (Resolve-Path -LiteralPath $ExplicitPath).Path
    }

    $Command = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }

    $Candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 5\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 5\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 5\ISCC.exe"
    )

    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate) {
            return $Candidate
        }
    }

    return $null
}

if (-not $AppVersion) {
    $AppVersion = Get-AppVersion
}

if (-not $SkipExeBuild) {
    & (Join-Path $Root "Build-Exe.ps1") -Name "SafeSweep" -NoDesktopShortcut
    if ($LASTEXITCODE -ne 0) {
        throw "Build de l'executable echoue."
    }
}

if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "Executable introuvable: $ExePath. Lancez .\Build-Exe.ps1 ou retirez -SkipExeBuild."
}

$ResolvedInnoCompiler = Find-InnoCompiler -ExplicitPath $InnoCompiler

if (-not $ResolvedInnoCompiler -and $InstallInnoSetup) {
    $Winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $Winget) {
        throw "Inno Setup n'est pas installe et winget.exe est introuvable."
    }

    & $Winget.Source install --id JRSoftware.InnoSetup --source winget --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Installation d'Inno Setup via winget echouee."
    }
    $ResolvedInnoCompiler = Find-InnoCompiler -ExplicitPath ""
}

if (-not $ResolvedInnoCompiler) {
    throw "Inno Setup n'est pas installe. Installez-le puis relancez .\Build-Installer.ps1, ou utilisez .\Build-Installer.ps1 -InstallInnoSetup."
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "dist\installer") | Out-Null

& $ResolvedInnoCompiler $InstallerScript "/DAppVersion=$AppVersion"
if ($LASTEXITCODE -ne 0) {
    throw "Compilation de l'installer Inno Setup echouee."
}

$SetupPath = Join-Path $Root "dist\installer\SafeSweep-Setup-$AppVersion.exe"
if (-not (Test-Path -LiteralPath $SetupPath)) {
    throw "Build termine mais setup introuvable: $SetupPath"
}

Write-Host "Installer cree: $SetupPath"
