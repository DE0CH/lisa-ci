# Reads back the first <ISO length> bytes of a physical disk and compares
# SHA256 against the ISO. Standalone so a verify can run without rewriting.
param(
    [Parameter(Mandatory)][string]$IsoPath,
    [Parameter(Mandatory)][int]$DiskNumber
)
$ErrorActionPreference = 'Stop'
$iso = Get-Item $IsoPath
$rd = New-Object System.IO.FileStream("\\.\PhysicalDrive$DiskNumber", [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read, [int]4MB, [System.IO.FileOptions]::None)
$sha = [Security.Cryptography.SHA256]::Create()
$buf = New-Object byte[] (4MB)
$remaining = [long]$iso.Length
while ($remaining -gt 0) {
    $want = [int][math]::Min([long]$buf.Length, [long]([math]::Ceiling($remaining / 512) * 512))
    $n = $rd.Read($buf, 0, $want)
    if ($n -le 0) { throw "short read during verify" }
    $use = [int][math]::Min([long]$n, $remaining)
    $sha.TransformBlock($buf, 0, $use, $null, 0) | Out-Null
    $remaining -= $use
}
$sha.TransformFinalBlock($buf, 0, 0) | Out-Null
$rd.Close()
$diskHash = -join ($sha.Hash | ForEach-Object { $_.ToString('x2') })
$isoHash = (Get-FileHash -Algorithm SHA256 $iso.FullName).Hash.ToLower()
Write-Host "ISO  sha256: $isoHash"
Write-Host "Disk sha256: $diskHash"
if ($diskHash -ne $isoHash) { throw "VERIFY FAILED - hashes differ" }
Write-Host "FLASH VERIFIED OK"
