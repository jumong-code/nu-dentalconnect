$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $Host.UI.RawUI.WindowTitle = "NU DentalConnect - Setup" } catch {}

$TL = [string][char]0x256D; $TR = [string][char]0x256E
$BL = [string][char]0x2570; $BR = [string][char]0x256F
$HL = [string][char]0x2500; $VL = [string][char]0x2502
$Full = [string][char]0x2588; $Empty = [string][char]0x2591
$TotalSteps = 6
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Say($text, $color = "White") { Write-Host "  $text" -ForegroundColor $color }
function Good($text) { Write-Host "  + $text" -ForegroundColor Green }
function Bad($text)  { Write-Host "  x $text" -ForegroundColor Red }

function Box($lines, $borderColor = "Magenta", $textColor = "White", $width = 50) {
    Write-Host ("  " + $TL + ($HL * $width) + $TR) -ForegroundColor $borderColor
    foreach ($l in $lines) {
        $pad = [Math]::Max(0, $width - $l.Length)
        $left = [int][Math]::Floor($pad / 2)
        $right = $pad - $left
        Write-Host ("  " + $VL) -NoNewline -ForegroundColor $borderColor
        Write-Host ((" " * $left) + $l + (" " * $right)) -NoNewline -ForegroundColor $textColor
        Write-Host $VL -ForegroundColor $borderColor
    }
    Write-Host ("  " + $BL + ($HL * $width) + $BR) -ForegroundColor $borderColor
}

function Step($n, $title) {
    $filled = [int][Math]::Round(($n / $TotalSteps) * 20)
    $bar = ($Full * $filled) + ($Empty * (20 - $filled))
    Write-Host
    Write-Host ("  " + ($HL * 54)) -ForegroundColor DarkMagenta
    Write-Host ("  " + $title) -ForegroundColor Cyan
    Write-Host ("  Step $n of $TotalSteps  " + $bar) -ForegroundColor Magenta
    Write-Host
}

function Ask($label) {
    Write-Host "  > " -NoNewline
    Write-Host "$label " -NoNewline -ForegroundColor Yellow
    return (Read-Host).Trim()
}

function AskSecret($label) {
    Write-Host "  > " -NoNewline
    Write-Host "$label " -NoNewline -ForegroundColor Yellow
    $secure = Read-Host -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

function Wait-Enter($text) {
    Write-Host
    Write-Host "  > $text" -ForegroundColor Yellow
    [void](Read-Host)
}

function Invoke-Pretty {
    param([string]$Message, [string]$FilePath = $venvPython, [string]$ArgumentString, [string]$Done)
    $outLog = Join-Path $env:TEMP "dentalconnect_out.log"
    $errLog = Join-Path $env:TEMP "dentalconnect_err.log"
    $p = Start-Process -FilePath $FilePath -ArgumentList $ArgumentString -WorkingDirectory $PSScriptRoot `
         -NoNewWindow -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog
    $null = $p.Handle
    $frames = "|", "/", "-", "\"
    $colors = "Magenta", "Cyan", "Yellow", "Green"
    $i = 0
    while (-not $p.HasExited) {
        Write-Host ("`r  " + $frames[$i % 4] + " " + $Message + "   ") -NoNewline -ForegroundColor $colors[$i % 4]
        Start-Sleep -Milliseconds 120
        $i++
    }
    $p.WaitForExit()
    Write-Host ("`r" + (" " * 78) + "`r") -NoNewline

    if ($p.ExitCode -ne 0) {
        Bad "This step did not complete."
        $details = @(Get-Content $errLog -Tail 12 -ErrorAction SilentlyContinue)
        if ($details.Count -eq 0) { $details = @(Get-Content $outLog -Tail 12 -ErrorAction SilentlyContinue) }
        if ($details.Count -gt 0) {
            Say "Output:" Yellow
            foreach ($d in $details) { Write-Host "    $d" -ForegroundColor DarkYellow }
        }
        Remove-Item $outLog, $errLog -ErrorAction SilentlyContinue
        throw "Step failed: $Message"
    }
    Remove-Item $outLog, $errLog -ErrorAction SilentlyContinue
    Good $Done
}

try {
    Clear-Host
    Write-Host
    Box @("", "NU DentalConnect", "First-Time Setup", "") "Magenta" "Cyan"
    Write-Host
    Say "Welcome. Let's get your website ready." Cyan
    Say "This takes about a minute. Follow the prompts below." Gray

    Step 1 "Python environment"
    if (Test-Path $venvPython) {
        Good "Virtual environment (.venv) already exists."
    } else {
        if (Get-Command py -ErrorAction SilentlyContinue)          { $sysPy = "py";     $pyArgs = "-3 -m venv .venv" }
        elseif (Get-Command python -ErrorAction SilentlyContinue)  { $sysPy = "python"; $pyArgs = "-m venv .venv" }
        else { throw "Python was not found on this computer. Install Python 3 (enable 'Add Python to PATH') and run this script again." }
        Invoke-Pretty -Message "Creating virtual environment..." -FilePath $sysPy -ArgumentString $pyArgs -Done "Virtual environment created."
        if (!(Test-Path $venvPython)) { throw "The virtual environment was not created. Please try again." }
    }

    Step 2 "Dependencies"
    if (!(Test-Path "requirements.txt")) { throw "requirements.txt was not found in this folder." }
    Invoke-Pretty -Message "Installing dependencies (this may take a minute)..." `
        -ArgumentString "-m pip install --disable-pip-version-check -r requirements.txt" `
        -Done "Dependencies installed."

    Step 3 "Environment configuration"
    if (Test-Path ".env") {
        Good ".env already exists. Keeping it unchanged."
    } else {
        if (!(Test-Path ".env.example")) { throw ".env.example was not found, so .env could not be created." }
        Copy-Item ".env.example" ".env"
        Good "Created .env from .env.example."
        Say "Notepad will open next. Fill in DATABASE_URL, SECRET_KEY and your" Cyan
        Say "email settings, then save and close it." Cyan
        Wait-Enter "Press Enter to open Notepad"
        Start-Process notepad.exe -ArgumentList ".env" -Wait
        Good "Settings saved."
    }

    Step 4 "Database"
    $createDb = 'CREATE DATABASE IF NOT EXISTS `dentalconnect` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;'
    Say "Create an empty database first. In phpMyAdmin, open the SQL tab," Cyan
    Say "paste the statement below, and click Go:" Cyan
    Write-Host
    Write-Host ("  " + $VL + " " + $createDb) -ForegroundColor White
    Set-Clipboard -Value $createDb
    Write-Host
    Say "Copied to your clipboard. Press Ctrl+V to paste." Green
    Wait-Enter "Press Enter once the database exists and .env is configured"

    $env:FLASK_APP = "run.py"
    Invoke-Pretty -Message "Applying database migrations..." -ArgumentString "-m flask db upgrade" -Done "Database schema is ready."

    Step 5 "Administrator account"
    $make = Ask "Create an administrator account now? (Y/n)"
    if ($make -notmatch '^(n|no)$') {
        do { $adminName = Ask "Full name:" } while (-not $adminName)
        do {
            $adminEmail = Ask "Email address:"
            $okEmail = $adminEmail -match '^[^@\s]+@[^@\s]+\.[^@\s]+$'
            if (-not $okEmail) { Say "That does not look like a valid email address. Please try again." Yellow }
        } while (-not $okEmail)
        do { $adminPhone = Ask "Phone number (e.g. +639171234567):" } while (-not $adminPhone)

        Say "Choose a password. Characters are hidden as you type." Cyan
        while ($true) {
            $pw1 = AskSecret "Password (minimum 8 characters):"
            $pw2 = AskSecret "Confirm password:"
            if ($pw1.Length -lt 8) { Say "Password must be at least 8 characters." Yellow; continue }
            if ($pw1 -ne $pw2)     { Say "Passwords do not match. Please try again." Yellow; continue }
            break
        }

        $pyCode = @'
import os
from werkzeug.security import generate_password_hash

def q(v):
    return "'" + v.replace("\\", "\\\\").replace("'", "''") + "'"

name = os.environ["DC_ADMIN_NAME"]
email = os.environ["DC_ADMIN_EMAIL"]
phone = os.environ["DC_ADMIN_PHONE"]
pw = os.environ["DC_ADMIN_PASSWORD"]
h = generate_password_hash(pw)

print("INSERT INTO `users`")
print("  (`full_name`, `email`, `password_hash`, `role`, `phone`,")
print("   `is_active`, `email_verified`, `approval_status`, `auth_version`, `created_at`)")
print("VALUES")
print("  (" + q(name) + ", " + q(email) + ", " + q(h) + ", 'admin', " + q(phone) + ",")
print("   1, 1, 'approved', 0, CURRENT_TIMESTAMP);")
'@

        try {
            $env:DC_ADMIN_NAME = $adminName
            $env:DC_ADMIN_EMAIL = $adminEmail
            $env:DC_ADMIN_PHONE = $adminPhone
            $env:DC_ADMIN_PASSWORD = $pw1
            $env:PYTHONIOENCODING = "utf-8"
            $sqlLines = $pyCode | & $venvPython -
            if ($LASTEXITCODE -ne 0) { throw "Could not generate the administrator SQL. Please try again." }
        } finally {
            Remove-Item Env:DC_ADMIN_NAME, Env:DC_ADMIN_EMAIL, Env:DC_ADMIN_PHONE, Env:DC_ADMIN_PASSWORD, Env:PYTHONIOENCODING -ErrorAction SilentlyContinue
            $pw1 = $null; $pw2 = $null
        }

        $sql = ($sqlLines -join "`n")
        Set-Clipboard -Value $sql

        Write-Host
        Good "Administrator SQL generated."
        Write-Host
        foreach ($line in $sqlLines) { Write-Host ("  " + $VL + " " + $line) -ForegroundColor White }
        Write-Host
        Say "Copied to your clipboard. It contains a password hash, not your password." Green
        Say "In phpMyAdmin: select 'dentalconnect' > SQL tab > paste > Go." Cyan
        Wait-Enter "Press Enter once the statement has been run"
        Good "Administrator account created."
    } else {
        Say "Skipping administrator account." Gray
    }

    Step 6 "Launch"
    while ($true) {
        Say "Select how to start the site:" Cyan
        Write-Host "     [1] Debug mode       - auto-reloads on code changes" -ForegroundColor Green
        Write-Host "     [2] Production mode  - Waitress server" -ForegroundColor Yellow
        Write-Host "     [Q] Not now          - start later" -ForegroundColor DarkGray
        Write-Host
        $choice = Ask "Selection:"
        if ($choice -eq "1")                  { & "$PSScriptRoot\start_debug.ps1"; break }
        elseif ($choice -eq "2")              { & "$PSScriptRoot\start_production.ps1"; break }
        elseif ($choice -match '^(q|quit)$')  {
            Write-Host
            Box @("", "Setup complete", "Start later with start_debug.ps1", "or start_production.ps1", "") "Green" "White"
            Write-Host
            break
        }
        else { Say "Please enter 1, 2 or Q." Yellow; Write-Host }
    }

} catch {
    Write-Host
    Write-Host "  ! An error occurred:" -ForegroundColor Red
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host
    Say "You can safely run this script again." Cyan
    Say "If this was the database step, verify DATABASE_URL in .env" Gray
    Say "and confirm that MySQL is running." Gray
    Write-Host
    Write-Host "  Press Enter to close this window..." -ForegroundColor DarkGray
    [void][System.Console]::ReadLine()
}