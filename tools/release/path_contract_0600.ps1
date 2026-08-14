function ConvertTo-CanonicalAbsolutePath {
  param([Parameter(Mandatory=$true)][string]$Path,[Parameter(Mandatory=$true)][string]$Name)
  if ([string]::IsNullOrWhiteSpace($Path)) { throw "$Name is empty" }
  if ($Path -match '^[A-Za-z]:[^\\/]' -or $Path -match '^[\\/](?![\\/])') { throw "$Name is drive/root-relative" }
  if ($Path.StartsWith('\\?\') -or $Path.StartsWith('\\.\') -or $Path.StartsWith('\??\')) { throw "$Name is an alias path" }
  if ($Path.Length -gt 3 -and ($Path.EndsWith('\') -or $Path.EndsWith('/'))) { throw "$Name has a trailing separator" }
  if (-not [System.IO.Path]::IsPathRooted($Path)) { throw "$Name is relative" }
  $canonical = [System.IO.Path]::GetFullPath($Path)
  if ($Path -cne $canonical) { throw "$Name is not canonical" }
  return $canonical
}

function Assert-FrozenVerifierCaller {
  param(
    [Parameter(Mandatory=$true)][string]$Repository,
    [Parameter(Mandatory=$true)][string]$ExpectedCodeHead
  )
  if ($ExpectedCodeHead -cnotmatch '^[0-9a-f]{40}$') { throw 'ExpectedCodeHead is invalid' }
  $head = (& git.exe -C $Repository rev-parse HEAD 2>$null)
  if ($LASTEXITCODE -ne 0 -or $head -cne $ExpectedCodeHead) { throw 'caller worktree HEAD mismatch' }
  foreach ($relative in @('tools/release/run_0600_gates.py','tools/release/verify_0600_feasibility.py','tools/release/verify_0600_release.py')) {
    $path = Join-Path $Repository ($relative.Replace('/','\'))
    $working = (& git.exe -C $Repository hash-object -- $path 2>$null)
    $committed = (& git.exe -C $Repository rev-parse ($ExpectedCodeHead + ':' + $relative) 2>$null)
    if ($LASTEXITCODE -ne 0 -or $working -cnotmatch '^[0-9a-f]{40}$' -or $working -cne $committed) {
      throw "caller blob mismatch: $relative"
    }
  }
}
