[CmdletBinding()]
param(
    [string]$TargetDatabaseUrl = "mysql://krib_user:krib_password@127.0.0.1:3306/krib_db",
    [switch]$PersistEnv
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$sqlitePath = Join-Path $backendDir "db.sqlite3"
$fixtureDir = Join-Path $backendDir "fixtures"
$fixturePath = Join-Path $fixtureDir "sqlite_migration.json"
$envPath = Join-Path $repoRoot ".env"

function Set-ContentUtf8NoBom([string]$path, [string]$value) {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($path, $value, $utf8NoBom)
}

function Get-PythonExecutable {
    $candidates = @(
        (Join-Path $repoRoot ".venv\Scripts\python.exe"),
        (Join-Path $repoRoot "backend\.venv\Scripts\python.exe"),
        (Join-Path $repoRoot "backend\venv\Scripts\python.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        return $pythonCommand.Source
    }

    throw "Python executable not found. Activate or create a virtual environment first."
}

function Convert-ToSqliteUrl([string]$path) {
    $resolved = (Resolve-Path $path).Path -replace "\\", "/"
    return "sqlite:///$resolved"
}

function Set-EnvValue([string]$path, [string]$key, [string]$value) {
    $line = "$key=$value"
    $pattern = "(?m)^$([regex]::Escape($key))=.*$"

    if (Test-Path $path) {
        $content = Get-Content $path -Raw
        if ($content -match $pattern) {
            $content = [regex]::Replace($content, $pattern, $line)
        }
        else {
            if ($content.Length -gt 0 -and -not $content.EndsWith("`n")) {
                $content += "`r`n"
            }
            $content += "$line`r`n"
        }

        Set-ContentUtf8NoBom -path $path -value $content
        return
    }

    Set-ContentUtf8NoBom -path $path -value "$line`r`n"
}

if (-not (Test-Path $sqlitePath)) {
    throw "Legacy SQLite database not found at $sqlitePath"
}

$python = Get-PythonExecutable
New-Item -ItemType Directory -Path $fixtureDir -Force | Out-Null

$originalDatabaseUrl = $env:DATABASE_URL

Push-Location $backendDir
try {
    $env:DATABASE_URL = Convert-ToSqliteUrl $sqlitePath
    Write-Host "==> Exporting legacy SQLite data to $fixturePath"
    $fixtureJson = & $python manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --indent 2 | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "SQLite export failed."
    }
    Set-ContentUtf8NoBom -path $fixturePath -value $fixtureJson

    $env:DATABASE_URL = $TargetDatabaseUrl
    Write-Host "==> Running MySQL migrations against $TargetDatabaseUrl"
    & $python manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) {
        throw "MySQL migrations failed. Ensure MySQL is running and the target database already exists."
    }

    Write-Host "==> Loading exported data into MySQL"
    & $python manage.py loaddata $fixturePath
    if ($LASTEXITCODE -ne 0) {
        throw "MySQL data import failed."
    }

    Write-Host "==> Running Django checks on MySQL"
    & $python manage.py check
    if ($LASTEXITCODE -ne 0) {
        throw "Django checks failed after the MySQL import."
    }
}
finally {
    if ($null -eq $originalDatabaseUrl) {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    }
    else {
        $env:DATABASE_URL = $originalDatabaseUrl
    }

    Pop-Location
}

if ($PersistEnv) {
    Set-EnvValue $envPath "DATABASE_URL" $TargetDatabaseUrl
    Write-Host "Updated $envPath with MySQL connection settings."
}

Write-Host "MySQL cutover complete."
Write-Host "Fixture saved at $fixturePath"
