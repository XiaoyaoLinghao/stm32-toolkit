[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Check", "Bootstrap")]
    [string]$Mode,

    [Parameter(Mandatory = $true)]
    [string]$PluginRoot,

    [Parameter(Mandatory = $true)]
    [string]$PluginData,

    [Parameter(Mandatory = $true)]
    [string]$ProjectDir
)

$ErrorActionPreference = "Stop"
$RuntimeVersion = "0.2.0"

function Resolve-ClaudePath {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value,
        [switch]$MustExist
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name is empty; Claude inline path substitution is required"
    }
    if ($Value -match '\$\{CLAUDE_(PLUGIN_ROOT|PLUGIN_DATA|PROJECT_DIR)\}') {
        throw "$Name contains an unresolved Claude placeholder"
    }
    if ($Value -notmatch '^(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|$)|//[^/]+/[^/]+(?:/|$))') {
        throw "$Name must be an absolute path"
    }

    $resolved = [System.IO.Path]::GetFullPath($Value)
    if ($MustExist -and -not (Test-Path -LiteralPath $resolved -PathType Container)) {
        throw "$Name does not identify an existing directory"
    }
    return $resolved
}

function Find-BootstrapPython {
    foreach ($name in @("python", "python3", "py")) {
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $command) {
            continue
        }
        $probe = & $command.Source -c "import json, sys; print(json.dumps({'version': '.'.join(map(str, sys.version_info[:3])), 'supported': sys.version_info >= (3, 10)}))" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $probe) {
            continue
        }
        try {
            $metadata = $probe | ConvertFrom-Json
        } catch {
            continue
        }
        if ($metadata.supported -eq $true) {
            return [ordered]@{ path = $command.Source; version = $metadata.version; supported = $true }
        }
    }
    return $null
}

try {
    # Resolve every Claude-owned path before any command can create or modify files.
    $resolvedPluginRoot = Resolve-ClaudePath -Name "PluginRoot" -Value $PluginRoot -MustExist
    $resolvedPluginData = Resolve-ClaudePath -Name "PluginData" -Value $PluginData
    $resolvedProjectDir = Resolve-ClaudePath -Name "ProjectDir" -Value $ProjectDir -MustExist
    $package = Join-Path $resolvedPluginRoot "tools/stm32-toolkit"
    if (-not (Test-Path -LiteralPath $package -PathType Container)) {
        throw "PluginRoot does not contain tools/stm32-toolkit"
    }
    $runtime = Join-Path $resolvedPluginData "runtime/$RuntimeVersion"
    $runtimePython = Join-Path $runtime "Scripts/python.exe"
    $bootstrapPython = Find-BootstrapPython

    if ($Mode -eq "Check") {
        $result = [ordered]@{
            mode = "CHECK"
            runtime = [ordered]@{
                path = $runtime.Replace("\", "/")
                present = (Test-Path -LiteralPath $runtimePython -PathType Leaf)
                version = $null
            }
            bootstrapPython = if ($bootstrapPython) { $bootstrapPython } else { [ordered]@{ available = $false; supported = $false } }
            project = $resolvedProjectDir.Replace("\", "/")
            mutated = $false
            authorizationRequired = -not (Test-Path -LiteralPath $runtimePython -PathType Leaf)
        }
        if ($result.runtime.present) {
            $result.runtime.version = (& $runtimePython -m stm32_toolkit.cli version)
            if ($LASTEXITCODE -ne 0) { throw "managed runtime version check failed" }
            $doctor = & $runtimePython -m stm32_toolkit.cli --project-root $resolvedProjectDir doctor --json
            if ($LASTEXITCODE -ne 0) { throw "toolkit doctor failed" }
            $result.doctor = $doctor | ConvertFrom-Json
        }
        $result | ConvertTo-Json -Depth 20
        exit 0
    }

    if (-not $bootstrapPython) {
        throw "Host Python 3.10+ is required to create the managed runtime"
    }
    if (Test-Path -LiteralPath $runtimePython -PathType Leaf) {
        throw "managed runtime already exists; use Check before deciding whether repair is needed"
    }

    & $bootstrapPython.path -m venv $runtime
    if ($LASTEXITCODE -ne 0) { throw "runtime creation failed" }
    & $runtimePython -m pip install $package
    if ($LASTEXITCODE -ne 0) { throw "toolkit installation failed" }
    & $runtimePython -m stm32_toolkit.cli --project-root $resolvedProjectDir doctor --json
    if ($LASTEXITCODE -ne 0) { throw "toolkit doctor failed" }
} catch {
    [Console]::Error.WriteLine("setup-stm32-env: " + $_.Exception.Message)
    exit 2
}
