$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path $env:LOCALAPPDATA 'Programs\Bulkrr'
$venv = Join-Path $dest '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
Write-Host '=== Bulkrr v1.5 installer ===' -ForegroundColor Cyan
Write-Host 'Installs Bulkrr locally, with its own private Python environment.'
Write-Host 'Python may be installed for your Windows account using the official WinGet package.'
Write-Host 'No Radarr/Sonarr credentials are requested by the installer.'
$ok = Read-Host 'Proceed with installation and necessary downloads? (Y/N)'
if ($ok -notin @('y','Y','yes','YES')) { throw 'Installation cancelled by user.' }
function Find-Python {
    $paths = @()
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $found = (& $py.Source -3.12 -c 'import sys;print(sys.executable)' 2>$null | Select-Object -First 1)
            if ($LASTEXITCODE -eq 0 -and (Test-Path $found)) { return $found }
        } catch {}
    }
    $candidates = @(
      (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
      (Join-Path $env:ProgramFiles 'Python312\python.exe'),
      $(if (${env:ProgramFiles(x86)}) { Join-Path ${env:ProgramFiles(x86)} 'Python312\python.exe' })
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    foreach ($reg in @('HKCU:\Software\Python\PythonCore\3.12\InstallPath','HKLM:\Software\Python\PythonCore\3.12\InstallPath')) {
        try {
            $val = (Get-Item $reg -ErrorAction Stop).GetValue('ExecutablePath')
            if ($val -and (Test-Path $val)) { return $val }
        } catch {}
    }
    return $null
}
$basePython = Find-Python
if (-not $basePython) {
    Write-Host 'Python 3.12 not found. Installing official Python 3.12 using WinGet...' -ForegroundColor Yellow
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw 'WinGet is unavailable. Install App Installer from Microsoft Store, then rerun this installer.'
    }
    & winget.exe install --id Python.Python.3.12 --exact --source winget --scope user --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "Python installation failed (exit $LASTEXITCODE)." }
    $basePython = Find-Python
    if (-not $basePython) { throw 'Python was installed but could not be located. Restart Windows and rerun Install Bulkrr.bat.' }
}
Write-Host "Using Python: $basePython" -ForegroundColor Green
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item (Join-Path $root 'bulkrr.py') (Join-Path $dest 'bulkrr.py') -Force
Copy-Item (Join-Path $root 'requirements.txt') (Join-Path $dest 'requirements.txt') -Force
foreach ($asset in @('Bulkrr.ico','Bulkrr.png','Bulkrr-splash.png')) {
    Copy-Item (Join-Path $root $asset) (Join-Path $dest $asset) -Force
}
if (-not (Test-Path $python)) {
    Write-Host 'Creating isolated Bulkrr environment...'
    & $basePython -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create the private Python environment.' }
}
Write-Host 'Installing graphical interface and credential storage packages...'
& $python -m pip install --disable-pip-version-check -r (Join-Path $dest 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check internet access and rerun the installer.' }
& $python -m py_compile (Join-Path $dest 'bulkrr.py')
if ($LASTEXITCODE -ne 0) { throw 'Application validation failed.' }
# Launch directly with pythonw.exe; no VBScript launcher is required.
$pyw = Join-Path $venv 'Scripts\pythonw.exe'
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'Bulkrr.lnk'
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pyw
$shortcut.Arguments = '"' + (Join-Path $dest 'bulkrr.py') + '"'
$shortcut.WorkingDirectory = $dest
$shortcut.Description = 'Bulkrr - Radarr and Sonarr bulk importer'
$shortcut.IconLocation = (Join-Path $dest 'Bulkrr.ico') + ',0'
$shortcut.Save()
# Remove the old broken launcher if it exists.
$oldLauncher = Join-Path $dest 'Launch Bulkrr.vbs'
if (Test-Path $oldLauncher) { Remove-Item $oldLauncher -Force }
Write-Host "Bulkrr installed in: $dest" -ForegroundColor Green
Write-Host "Desktop shortcut created: $shortcutPath" -ForegroundColor Green
Write-Host 'Starting Bulkrr...'
Start-Process -FilePath $pyw -ArgumentList ('"' + (Join-Path $dest 'bulkrr.py') + '"') -WorkingDirectory $dest
