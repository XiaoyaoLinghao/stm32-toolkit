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
