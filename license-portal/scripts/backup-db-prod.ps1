param(
  [string]$OutputDir = "backups/production",
  [string]$DatabaseUrl = $env:DATABASE_URL,
  [string]$EncryptionKey = $env:BACKUP_ENCRYPTION_KEY,
  [int]$CompressionLevel = 9,
  [string]$ComposeService = "postgres",
  [switch]$UseDocker,
  [switch]$SkipUpload,
  [switch]$ForceWeekly,
  [switch]$ForceMonthly
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

function Invoke-CheckedCapture {
  param(
    [string]$Command,
    [string[]]$Arguments
  )

  $Output = & $Command @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code $LASTEXITCODE`: $Command $($Arguments -join ' ')"
  }

  return $Output
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

function New-RandomBytes {
  param([int]$Length)

  $Bytes = New-Object byte[] $Length
  $Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()

  try {
    $Rng.GetBytes($Bytes)
  }
  finally {
    $Rng.Dispose()
  }

  return ,$Bytes
}

function New-DerivedKey {
  param(
    [string]$Secret,
    [byte[]]$Salt
  )

  try {
    $Kdf = [System.Security.Cryptography.Rfc2898DeriveBytes]::new(
      $Secret,
      $Salt,
      200000,
      [System.Security.Cryptography.HashAlgorithmName]::SHA256
    )
  }
  catch {
    $Kdf = [System.Security.Cryptography.Rfc2898DeriveBytes]::new($Secret, $Salt, 200000)
  }

  try {
    return ,$Kdf.GetBytes(32)
  }
  finally {
    $Kdf.Dispose()
  }
}

function Protect-BackupFile {
  param(
    [string]$InputPath,
    [string]$OutputPath,
    [string]$Secret
  )

  $Salt = New-RandomBytes 16
  $Key = New-DerivedKey $Secret $Salt
  $Aes = [System.Security.Cryptography.Aes]::Create()
  $Aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
  $Aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
  $Aes.Key = $Key
  $Aes.GenerateIV()

  $Input = $null
  $Output = $null
  $Crypto = $null
  $Encryptor = $null

  try {
    $Input = [System.IO.File]::OpenRead($InputPath)
    $Output = [System.IO.File]::Create($OutputPath)
    $Magic = [System.Text.Encoding]::ASCII.GetBytes("SSBK1")

    $Output.Write($Magic, 0, $Magic.Length)
    $Output.WriteByte(1)
    $Output.WriteByte($Salt.Length)
    $Output.WriteByte($Aes.IV.Length)
    $Output.Write($Salt, 0, $Salt.Length)
    $Output.Write($Aes.IV, 0, $Aes.IV.Length)

    $Encryptor = $Aes.CreateEncryptor()
    $Crypto = [System.Security.Cryptography.CryptoStream]::new(
      $Output,
      $Encryptor,
      [System.Security.Cryptography.CryptoStreamMode]::Write
    )

    $Input.CopyTo($Crypto)
    $Crypto.FlushFinalBlock()
  }
  finally {
    if ($Crypto) {
      $Crypto.Dispose()
    }
    elseif ($Output) {
      $Output.Dispose()
    }

    if ($Input) {
      $Input.Dispose()
    }

    if ($Encryptor) {
      $Encryptor.Dispose()
    }

    $Aes.Dispose()
  }
}

function Invoke-PgDump {
  param(
    [object]$Connection,
    [string]$OutputPath
  )

  if (-not $UseDocker -and (Test-Commands @("pg_dump"))) {
    $PreviousPassword = $env:PGPASSWORD
    $env:PGPASSWORD = $Connection.Password

    try {
      Invoke-Checked "pg_dump" @(
        "--format=custom",
        "--compress", [string]$CompressionLevel,
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

    return "local pg_dump"
  }

  $ContainerId = Get-DockerContainerId $ComposeService
  $ContainerDumpPath = "/tmp/$(Split-Path -Leaf $OutputPath)"

  Push-Location $ProjectRoot
  try {
    Invoke-Checked "docker" @(
      "compose", "exec", "-T",
      "-e", "PGPASSWORD=$($Connection.Password)",
      $ComposeService,
      "pg_dump",
      "--format=custom",
      "--compress", [string]$CompressionLevel,
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

  return "Docker Compose"
}

function Test-Enabled {
  param([string]$Value)

  if ([string]::IsNullOrWhiteSpace($Value)) {
    return $false
  }

  return @("1", "true", "yes", "on") -contains $Value.Trim().ToLowerInvariant()
}

function Join-BackupPath {
  param(
    [string]$BaseDir,
    [string]$Tier,
    [string]$FileName
  )

  $TierDir = Join-Path $BaseDir $Tier
  New-Item -ItemType Directory -Path $TierDir -Force | Out-Null

  return Join-Path $TierDir $FileName
}

function Invoke-LocalRetention {
  param(
    [string]$Directory,
    [int]$Keep
  )

  $ExpiredFiles = Get-ChildItem -LiteralPath $Directory -Filter "*.dump.enc" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $Keep

  foreach ($File in $ExpiredFiles) {
    Remove-Item -LiteralPath $File.FullName -Force
  }
}

function Get-S3Key {
  param(
    [string]$Prefix,
    [string]$Tier,
    [string]$FileName
  )

  $CleanPrefix = ""
  if (-not [string]::IsNullOrWhiteSpace($Prefix)) {
    $CleanPrefix = $Prefix.Trim("/")
  }

  if ([string]::IsNullOrWhiteSpace($CleanPrefix)) {
    return "$Tier/$FileName"
  }

  return "$CleanPrefix/$Tier/$FileName"
}

function Invoke-Aws {
  param([string[]]$Arguments)

  $AwsArgs = @()
  if (-not [string]::IsNullOrWhiteSpace($env:BACKUP_S3_ENDPOINT_URL)) {
    $AwsArgs += @("--endpoint-url", $env:BACKUP_S3_ENDPOINT_URL)
  }

  $AwsArgs += $Arguments
  Invoke-Checked "aws" $AwsArgs
}

function Invoke-AwsCapture {
  param([string[]]$Arguments)

  $AwsArgs = @()
  if (-not [string]::IsNullOrWhiteSpace($env:BACKUP_S3_ENDPOINT_URL)) {
    $AwsArgs += @("--endpoint-url", $env:BACKUP_S3_ENDPOINT_URL)
  }

  $AwsArgs += $Arguments
  return Invoke-CheckedCapture "aws" $AwsArgs
}

function Invoke-S3Retention {
  param(
    [string]$Bucket,
    [string]$Prefix,
    [string]$Tier,
    [int]$Keep
  )

  $CleanPrefix = ""
  if (-not [string]::IsNullOrWhiteSpace($Prefix)) {
    $CleanPrefix = $Prefix.Trim("/")
  }
  $KeyPrefix = if ([string]::IsNullOrWhiteSpace($CleanPrefix)) { "$Tier/" } else { "$CleanPrefix/$Tier/" }
  $Json = (Invoke-AwsCapture @(
      "s3api", "list-objects-v2",
      "--bucket", $Bucket,
      "--prefix", $KeyPrefix,
      "--output", "json"
    )) -join "`n"

  if ([string]::IsNullOrWhiteSpace($Json)) {
    return
  }

  $Payload = $Json | ConvertFrom-Json
  $Objects = @($Payload.Contents)

  if ($Objects.Count -le $Keep) {
    return
  }

  $ExpiredObjects = $Objects |
    Sort-Object LastModified -Descending |
    Select-Object -Skip $Keep

  foreach ($Object in $ExpiredObjects) {
    Invoke-Aws @("s3", "rm", "s3://$Bucket/$($Object.Key)")
  }
}

Import-DotEnv @(
  (Join-Path $ProjectRoot ".env"),
  (Join-Path $ProjectRoot ".env.local")
)

if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
  $DatabaseUrl = $env:DATABASE_URL
}

if ([string]::IsNullOrWhiteSpace($EncryptionKey)) {
  $EncryptionKey = $env:BACKUP_ENCRYPTION_KEY
}

if ($env:BACKUP_COMPRESSION_LEVEL -and -not $PSBoundParameters.ContainsKey("CompressionLevel")) {
  $CompressionLevel = [int]$env:BACKUP_COMPRESSION_LEVEL
}

if ($CompressionLevel -lt 0 -or $CompressionLevel -gt 9) {
  throw "BACKUP_COMPRESSION_LEVEL must be between 0 and 9."
}

if ([string]::IsNullOrWhiteSpace($EncryptionKey) -or $EncryptionKey.Length -lt 32) {
  throw "BACKUP_ENCRYPTION_KEY must be set and contain at least 32 characters."
}

$Connection = Read-DatabaseUrl $DatabaseUrl

if ([System.IO.Path]::IsPathRooted($OutputDir)) {
  $BackupBaseDir = $OutputDir
}
else {
  $BackupBaseDir = Join-Path $ProjectRoot $OutputDir
}

$TempDir = Join-Path $BackupBaseDir ".tmp"
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

$Now = Get-Date
$Timestamp = $Now.ToString("yyyy-MM-dd_HH-mm-ss")
$SafeDatabaseName = $Connection.Database -replace "[^a-zA-Z0-9_.-]", "_"
$PlainDumpPath = Join-Path $TempDir "$SafeDatabaseName-$Timestamp.dump"
$EncryptedFileName = "$SafeDatabaseName-$Timestamp.dump.enc"
$DailyPath = Join-BackupPath $BackupBaseDir "daily" $EncryptedFileName

$DumpMode = Invoke-PgDump $Connection $PlainDumpPath

try {
  Protect-BackupFile $PlainDumpPath $DailyPath $EncryptionKey
}
finally {
  if (Test-Path -LiteralPath $PlainDumpPath) {
    Remove-Item -LiteralPath $PlainDumpPath -Force
  }
}

$CreatedBackups = @(
  [PSCustomObject]@{ Tier = "daily"; Path = $DailyPath }
)

if ($ForceWeekly -or $Now.DayOfWeek -eq [System.DayOfWeek]::Monday) {
  $WeeklyPath = Join-BackupPath $BackupBaseDir "weekly" $EncryptedFileName
  Copy-Item -LiteralPath $DailyPath -Destination $WeeklyPath -Force
  $CreatedBackups += [PSCustomObject]@{ Tier = "weekly"; Path = $WeeklyPath }
}

if ($ForceMonthly -or $Now.Day -eq 1) {
  $MonthlyPath = Join-BackupPath $BackupBaseDir "monthly" $EncryptedFileName
  Copy-Item -LiteralPath $DailyPath -Destination $MonthlyPath -Force
  $CreatedBackups += [PSCustomObject]@{ Tier = "monthly"; Path = $MonthlyPath }
}

Invoke-LocalRetention (Join-Path $BackupBaseDir "daily") 7
Invoke-LocalRetention (Join-Path $BackupBaseDir "weekly") 4
Invoke-LocalRetention (Join-Path $BackupBaseDir "monthly") 12

if (-not $SkipUpload -and (Test-Enabled $env:BACKUP_UPLOAD_ENABLED)) {
  if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw "BACKUP_UPLOAD_ENABLED is true, but the AWS CLI is not available."
  }

  if ([string]::IsNullOrWhiteSpace($env:BACKUP_S3_BUCKET)) {
    throw "BACKUP_S3_BUCKET must be set when BACKUP_UPLOAD_ENABLED is true."
  }

  foreach ($Backup in $CreatedBackups) {
    $Key = Get-S3Key $env:BACKUP_S3_PREFIX $Backup.Tier (Split-Path -Leaf $Backup.Path)
    Invoke-Aws @("s3", "cp", $Backup.Path, "s3://$($env:BACKUP_S3_BUCKET)/$Key")
  }

  Invoke-S3Retention $env:BACKUP_S3_BUCKET $env:BACKUP_S3_PREFIX "daily" 7
  Invoke-S3Retention $env:BACKUP_S3_BUCKET $env:BACKUP_S3_PREFIX "weekly" 4
  Invoke-S3Retention $env:BACKUP_S3_BUCKET $env:BACKUP_S3_PREFIX "monthly" 12
}
else {
  Write-Host "S3 upload skipped. Set BACKUP_UPLOAD_ENABLED=true to enable it."
}

Write-Host "Production backup created with $DumpMode."
foreach ($Backup in $CreatedBackups) {
  Write-Host "$($Backup.Tier): $($Backup.Path)"
}
