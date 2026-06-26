param(
    [string]$Python = "",
    [string]$Name = "SafeSweep",
    [switch]$NoDesktopShortcut,
    [switch]$Console
)

$ErrorActionPreference = "Stop"

if (-not $Python) {
    $bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $bundledPython) {
        $Python = $bundledPython
    } else {
        $Python = "python"
    }
}

$AssetDir = "src\unused_file_finder\assets"
$Icon = Join-Path $AssetDir "nettoyeur-fichiers.ico"
$ExePath = Join-Path "dist" "$Name.exe"

& $Python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) {
    throw "Installation des dependances de build echouee."
}

$ResolvedExePath = $null
if (Test-Path -LiteralPath $ExePath) {
    $ResolvedExePath = (Resolve-Path -LiteralPath $ExePath).Path
    $Running = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $ResolvedExePath }
    if ($Running) {
        $Ids = ($Running | Select-Object -ExpandProperty Id) -join ", "
        throw "Impossible de reconstruire l'executable car il est deja lance (PID: $Ids). Fermez l'application puis relancez le build."
    }
}

$WindowMode = if ($Console) { "--console" } else { "--windowed" }
$PyInstallerArgs = @(
    "--clean",
    "--noconfirm",
    "--onefile",
    $WindowMode,
    "--name",
    $Name,
    "--paths",
    "src",
    "--icon",
    $Icon,
    "--add-data",
    "$AssetDir;unused_file_finder\assets",
    "src\app.py"
)

& $Python -m PyInstaller @PyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "Build PyInstaller echoue."
}

$FinalExePath = (Resolve-Path (Join-Path "dist" "$Name.exe")).Path
Write-Host "Executable cree: $FinalExePath"

if (-not $NoDesktopShortcut -and -not $Console) {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    if ($Desktop -and (Test-Path $Desktop)) {
        $ShortcutPath = Join-Path $Desktop "SafeSweep.lnk"
        $Shell = New-Object -ComObject WScript.Shell
        $Shortcut = $Shell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = $FinalExePath
        $Shortcut.WorkingDirectory = Split-Path $FinalExePath
        $Shortcut.IconLocation = "$FinalExePath,0"
        $Shortcut.Description = "SafeSweep smart file cleanup"
        $Shortcut.Save()
        Write-Host "Raccourci bureau cree: $ShortcutPath"
    } else {
        Write-Warning "Bureau introuvable, raccourci non cree."
    }
}
