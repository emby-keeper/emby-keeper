param(
    [string]$InstallDirectory = (Join-Path $env:LOCALAPPDATA 'Embykeeper'),
    [string]$PackagePath = '',
    [switch]$InstallOnly
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$pythonVersion = '3.11.9'
$pythonDirectory = Join-Path $InstallDirectory "python-$pythonVersion"
$python = Join-Path $pythonDirectory 'python.exe'
$pythonWindowless = Join-Path $pythonDirectory 'pythonw.exe'
$indexes = @('https://pypi.tuna.tsinghua.edu.cn/simple', 'https://pypi.org/simple')
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

function Download-FirstAvailable([string[]]$Urls, [string]$Destination) {
    foreach ($url in $Urls) {
        try {
            Write-Host "Downloading $url"
            Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $Destination -TimeoutSec 120
            return
        } catch {
            Write-Warning "Download failed: $url"
        }
    }
    throw 'All download sources failed. Check the network and try again.'
}

function Install-WithFallback([string[]]$Arguments) {
    foreach ($index in $indexes) {
        Write-Host "Installing from $index"
        & $python @Arguments --index-url $index --timeout 30 --retries 1
        if ($LASTEXITCODE -eq 0) { return }
        Write-Warning "Installation failed using $index; trying the next source."
    }
    throw 'Installation failed with both package sources. Check the network and try again.'
}

try {
    New-Item -ItemType Directory -Force -Path $InstallDirectory | Out-Null
    if (-not (Test-Path $python)) {
        $archive = Join-Path $InstallDirectory 'python-embed.zip'
        $archiveName = "python-$pythonVersion-embed-amd64.zip"
        Download-FirstAvailable @(
            "https://www.python.org/ftp/python/$pythonVersion/$archiveName",
            "https://registry.npmmirror.com/-/binary/python/$pythonVersion/$archiveName"
        ) $archive
        Expand-Archive -Path $archive -DestinationPath $pythonDirectory -Force
        Remove-Item $archive
    }

    $pathFile = Get-ChildItem $pythonDirectory -Filter 'python*._pth' | Select-Object -First 1
    if (-not $pathFile) { throw 'The embedded Python path configuration is missing.' }
    $paths = @(Get-Content $pathFile.FullName | ForEach-Object { $_ -replace '^#\s*import site', 'import site' })
    if ($paths -notcontains 'Lib\site-packages') { $paths += 'Lib\site-packages' }
    Set-Content -Path $pathFile.FullName -Value $paths -Encoding Ascii

    if (-not (Test-Path (Join-Path $pythonDirectory 'Lib/site-packages/pip/__init__.py'))) {
        $getPip = Join-Path $InstallDirectory 'get-pip.py'
        Download-FirstAvailable @('https://bootstrap.pypa.io/get-pip.py') $getPip
        Install-WithFallback @($getPip, '--no-warn-script-location')
        Remove-Item $getPip
    }

    if ($PackagePath) {
        $package = $PackagePath
        $version = 'local-test'
    } else {
        $versionFile = Join-Path $PSScriptRoot 'version.txt'
        if (-not (Test-Path $versionFile)) { throw 'version.txt is missing; use the release ZIP.' }
        $version = (Get-Content $versionFile -Raw).Trim()
        if ($version -notmatch '^\d+\.\d+\.\d+([a-zA-Z0-9.]+)?$') { throw 'Invalid release version.' }
        $package = "embykeeper==$version"
    }
    $marker = Join-Path $InstallDirectory 'installed-version.txt'
    if ($PackagePath -or -not (Test-Path $marker) -or (Get-Content $marker -Raw).Trim() -ne $version) {
        Install-WithFallback @('-m', 'pip', 'install', '--upgrade', '--no-warn-script-location', $package)
        Set-Content -Path $marker -Value $version -Encoding Ascii
    }

    if ($InstallOnly) { exit 0 }

    $passwordFile = Join-Path $InstallDirectory 'panel-password.txt'
    if (-not (Test-Path $passwordFile)) {
        do {
            $securePassword = Read-Host 'Set a password for the Embykeeper panel' -AsSecureString
            $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
            try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
            finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
            if (-not $password -or $password -eq 'your-password') {
                Write-Host 'Choose a non-empty password other than your-password.'
            }
        } while (-not $password -or $password -eq 'your-password')
        $securePassword | ConvertFrom-SecureString | Set-Content -Path $passwordFile -Encoding Ascii
    } else {
        $securePassword = Get-Content $passwordFile | ConvertTo-SecureString
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
        try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    }
    $env:EK_WEBPASS = $password
    Start-Process -FilePath $pythonWindowless -ArgumentList @('-m', 'embykeeper.windows_panel')
} catch {
    Write-Error $_
    exit 1
}