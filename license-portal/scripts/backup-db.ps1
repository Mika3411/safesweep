param(
  [string]$OutputDir = "backups",
  [string]$DatabaseUrl = $env:DATABASE_URL,
  [string]$ComposeService = "postgres",
  [switch]$UseDocker
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

function Import-DotEnv {
  param([string[]]$Paths)

  foreach ($Path in $Paths) {
    if (-not (Test-Path -LiteralPath $Path)) {
      continue
    }

    foreach ($Line in Get-Content -LiteralPath $Path) {
      $Trimmed = $Line.Trim()
      if ($Trimmed.Length -eq 0 -or $Trimmed.StartsWith("#")) {
        continue
      }

      $EqualsIndex = $Trimmed.IndexOf("=")
      if ($EqualsIndex -le 0) {
        continue
      }

      $Name = $Trimmed.Substring(0, $EqualsIndex).Trim()
      $Value = $Trimmed.Substring($EqualsIndex + 1).Trim()

      if (($Value.StartsWith('"') -and $Value.EndsWith('"')) -or ($Value.StartsWith("'") -and $Value.EndsWith("'"))) {
        $Value = $Value.Substring(1, $Value.Length - 2)
      }

      [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
  }
}

function Read-DatabaseUrl {
  param([string]$Url)

  if ([string]::IsNullOrWhiteSpace($Url)) {
    throw "DATABASE_URL is missing. Set it in the environment or in license-portal/.env."
  }

  $Uri = [System.Uri]$Url
  $UserInfo = $Uri.UserInfo
  $ColonIndex = $UserInfo.IndexOf(":")

  if ($ColonIndex -lt 0) {
    throw "DATABASE_URL must include a username and password."
  }

  $Database = [System.Uri]::UnescapeDataString($Uri.AbsolutePath.TrimStart("/"))
  $Port = $Uri.Port
  if ($Port -lt 0) {
    $Port = 5432
  }

  return [PSCustomObject]@{
    Host = $Uri.Host
    Port = $Port
    Username = [System.Uri]::UnescapeDataString($UserInfo.Substring(0, $ColonIndex))
    Password = [System.Uri]::UnescapeDataString($UserInfo.Substring($ColonIndex + 1))
    Database = $Database
  }
}

function Invoke-Checked {
  param(
    [string]$Command,
    [string[]]$Arguments
  )

  & $Command @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code $LASTEXITCODE`: $Command $($Arguments -join ' ')"
  }
}

function Test-Commands {
  param([string[]]$Commands)

  foreach ($Command in $Commands) {
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
      return $false
    }
  }

  return $true
}

function Get-DockerContainerId {
  param([string]$Service)

  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is not available. Install PostgreSQL client tools or start Docker Desktop."
  }

  Push-Location $ProjectRoot
  try {
    $ContainerId = (& docker compose ps -q $Service).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ContainerId)) {
      throw "Docker Compose service '$Service' is not running. Start it with: docker compose up -d $Service"
    }

    return $ContainerId
  }
  finally {
    Pop-Location
  }
}

if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
  Import-DotEnv @(
    (Join-Path $ProjectRoot ".env"),
    (Join-Path $ProjectRoot ".env.local")
  )
  $DatabaseUrl = $env:DATABASE_URL
}

$Connection = Read-DatabaseUrl $DatabaseUrl

if ([System.IO.Path]::IsPathRooted($OutputDir)) {
  $BackupDir = $OutputDir
}
else {
  $BackupDir = Join-Path $ProjectRoot $OutputDir
}

New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

$Timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$SafeDatabaseName = $Connection.Database -replace "[^a-zA-Z0-9_.-]", "_"
$OutputPath = Join-Path $BackupDir "$SafeDatabaseName-$Timestamp.dump"

if (-not $UseDocker -and (Test-Commands @("pg_dump"))) {
  $PreviousPassword = $env:PGPASSWORD
  $env:PGPASSWORD = $Connection.Password

  try {
    Invoke-Checked "pg_dump" @(
      "--format=custom",
      "--no-owner",
      "--no-privileges",
      "--host", $Connection.Host,
      "--port", [string]$Connection.Port,
      "--username", $Connection.Username,
      "--dbname", $Connection.Database,
      "--file", $OutputPath
    )
  }
  finally {
    $env:PGPASSWORD = $PreviousPassword
  }

  Write-Host "Backup created with local pg_dump: $OutputPath"
  exit 0
}

$ContainerId = Get-DockerContainerId $ComposeService
$ContainerDumpPath = "/tmp/$SafeDatabaseName-$Timestamp.dump"

Push-Location $ProjectRoot
try {
  Invoke-Checked "docker" @(
    "compose", "exec", "-T",
    "-e", "PGPASSWORD=$($Connection.Password)",
    $ComposeService,
    "pg_dump",
    "--format=custom",
    "--no-owner",
    "--no-privileges",
    "--host", $Connection.Host,
    "--port", [string]$Connection.Port,
    "--username", $Connection.Username,
    "--dbname", $Connection.Database,
    "--file", $ContainerDumpPath
  )

  Invoke-Checked "docker" @("cp", "${ContainerId}:$ContainerDumpPath", $OutputPath)
  Invoke-Checked "docker" @("compose", "exec", "-T", $ComposeService, "rm", "-f", $ContainerDumpPath)
}
finally {
  Pop-Location
}

Write-Host "Backup created with Docker Compose: $OutputPath"
