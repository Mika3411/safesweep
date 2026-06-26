param(
  [string]$InputFile,
  [string]$OutputFile,
  [string]$EncryptionKey = $env:BACKUP_ENCRYPTION_KEY,
  [switch]$Force
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

function Resolve-BackupInput {
  param([string]$Path)

  if ([string]::IsNullOrWhiteSpace($Path)) {
    $BackupDir = Join-Path $ProjectRoot "backups/production"
    $LatestBackup = Get-ChildItem -Path $BackupDir -Filter "*.dump.enc" -File -Recurse -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending |
      Select-Object -First 1

    if ($null -eq $LatestBackup) {
      throw "No encrypted backup found in $BackupDir."
    }

    return $LatestBackup.FullName
  }

  if ([System.IO.Path]::IsPathRooted($Path)) {
    return (Resolve-Path -LiteralPath $Path).Path
  }

  return (Resolve-Path -LiteralPath (Join-Path $ProjectRoot $Path)).Path
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

function Read-ExactBytes {
  param(
    [System.IO.Stream]$Stream,
    [int]$Length
  )

  $Buffer = New-Object byte[] $Length
  $Offset = 0

  while ($Offset -lt $Length) {
    $Read = $Stream.Read($Buffer, $Offset, $Length - $Offset)
    if ($Read -le 0) {
      throw "Encrypted backup is truncated."
    }

    $Offset += $Read
  }

  return ,$Buffer
}

function Unprotect-BackupFile {
  param(
    [string]$InputPath,
    [string]$OutputPath,
    [string]$Secret
  )

  $Input = $null
  $Output = $null
  $Crypto = $null
  $Decryptor = $null
  $Aes = $null

  try {
    $Input = [System.IO.File]::OpenRead($InputPath)
    $Magic = [System.Text.Encoding]::ASCII.GetString((Read-ExactBytes $Input 5))

    if ($Magic -ne "SSBK1") {
      throw "Unsupported encrypted backup format."
    }

    $Version = $Input.ReadByte()
    if ($Version -ne 1) {
      throw "Unsupported encrypted backup version: $Version."
    }

    $SaltLength = $Input.ReadByte()
    $IvLength = $Input.ReadByte()

    if ($SaltLength -le 0 -or $IvLength -le 0) {
      throw "Encrypted backup header is invalid."
    }

    $Salt = Read-ExactBytes $Input $SaltLength
    $Iv = Read-ExactBytes $Input $IvLength
    $Key = New-DerivedKey $Secret $Salt

    $Aes = [System.Security.Cryptography.Aes]::Create()
    $Aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
    $Aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
    $Aes.Key = $Key
    $Aes.IV = $Iv

    $Decryptor = $Aes.CreateDecryptor()
    $Crypto = [System.Security.Cryptography.CryptoStream]::new(
      $Input,
      $Decryptor,
      [System.Security.Cryptography.CryptoStreamMode]::Read
    )
    $Output = [System.IO.File]::Create($OutputPath)

    $Crypto.CopyTo($Output)
  }
  finally {
    if ($Output) {
      $Output.Dispose()
    }

    if ($Crypto) {
      $Crypto.Dispose()
    }
    elseif ($Input) {
      $Input.Dispose()
    }

    if ($Decryptor) {
      $Decryptor.Dispose()
    }

    if ($Aes) {
      $Aes.Dispose()
    }
  }
}

Import-DotEnv @(
  (Join-Path $ProjectRoot ".env"),
  (Join-Path $ProjectRoot ".env.local")
)

if ([string]::IsNullOrWhiteSpace($EncryptionKey)) {
  $EncryptionKey = $env:BACKUP_ENCRYPTION_KEY
}

if ([string]::IsNullOrWhiteSpace($EncryptionKey) -or $EncryptionKey.Length -lt 32) {
  throw "BACKUP_ENCRYPTION_KEY must be set and contain at least 32 characters."
}

$InputPath = Resolve-BackupInput $InputFile

if ([string]::IsNullOrWhiteSpace($OutputFile)) {
  $RestoreDir = Join-Path $ProjectRoot "backups/restore"
  New-Item -ItemType Directory -Path $RestoreDir -Force | Out-Null
  $OutputFileName = (Split-Path -Leaf $InputPath) -replace "\.enc$", ""
  $OutputPath = Join-Path $RestoreDir $OutputFileName
}
elseif ([System.IO.Path]::IsPathRooted($OutputFile)) {
  $OutputPath = $OutputFile
}
else {
  $OutputPath = Join-Path $ProjectRoot $OutputFile
}

$OutputParent = Split-Path -Parent $OutputPath
if (-not [string]::IsNullOrWhiteSpace($OutputParent)) {
  New-Item -ItemType Directory -Path $OutputParent -Force | Out-Null
}

if ((Test-Path -LiteralPath $OutputPath) -and -not $Force) {
  throw "Output file already exists: $OutputPath. Pass -Force to overwrite it."
}

Unprotect-BackupFile $InputPath $OutputPath $EncryptionKey

Write-Host "Encrypted backup decrypted."
Write-Host "Input: $InputPath"
Write-Host "Output: $OutputPath"
