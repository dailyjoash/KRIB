$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Python virtualenv not found at $python"
}

Write-Host "==> Backend tests"
Push-Location (Join-Path $root "backend")
try {
    & $python manage.py test

    Write-Host "==> Django deploy checks"
    $env:DJANGO_DEBUG = "0"
    $env:DJANGO_SECRET_KEY = "12345678901234567890123456789012345678901234567890"
    $env:DJANGO_ALLOWED_HOSTS = "example.com"
    $env:DJANGO_CORS_ALLOWED_ORIGINS = "https://app.example.com"
    $env:DJANGO_CSRF_TRUSTED_ORIGINS = "https://app.example.com"
    $env:DJANGO_SECURE_SSL_REDIRECT = "1"
    & $python manage.py check --deploy

    Write-Host "==> Static asset collection"
    & $python manage.py collectstatic --noinput
}
finally {
    Pop-Location
}

Write-Host "==> Frontend build"
Push-Location (Join-Path $root "frontend")
try {
    cmd /c npm run build
}
finally {
    Pop-Location
}

if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Host "==> Docker Compose prod config"
    Push-Location $root
    try {
        docker compose -f docker-compose.prod.yml config | Out-Null
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "Skipping Docker validation because docker is not installed in this environment."
}

Write-Host "Release check passed."
