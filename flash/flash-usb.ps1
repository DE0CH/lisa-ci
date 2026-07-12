# Raw-writes an ISO image to a physical disk. Refuses anything that is not
# the approved target: USB bus, "Verbatim" in the name, and < 64 GB.
param(
    [Parameter(Mandatory)][string]$IsoPath,
    [Parameter(Mandatory)][int]$DiskNumber
)
$ErrorActionPreference = 'Stop'

$disk = Get-Disk -Number $DiskNumber
if ($disk.BusType -ne 'USB') { throw "Disk $DiskNumber bus is $($disk.BusType), not USB - aborting" }
if ($disk.FriendlyName -notmatch 'Verbatim') { throw "Disk $DiskNumber is '$($disk.FriendlyName)', not the approved Verbatim stick - aborting" }
if ($disk.Size -gt 64GB) { throw "Disk $DiskNumber is $([math]::Round($disk.Size/1GB,1)) GB, larger than expected - aborting" }

$iso = Get-Item $IsoPath
if ($iso.Length -gt $disk.Size) { throw "ISO larger than target disk" }
Write-Host "Target: disk $DiskNumber $($disk.FriendlyName) $([math]::Round($disk.Size/1GB,1))GB"
Write-Host "Image : $($iso.FullName) ($([math]::Round($iso.Length/1MB,1)) MB)"

Write-Host "Clearing existing partitions..."
Set-Disk -Number $DiskNumber -IsReadOnly $false
try { Clear-Disk -Number $DiskNumber -RemoveData -RemoveOEM -Confirm:$false } catch { Write-Host "Clear-Disk: $_ (continuing)" }

Write-Host "Writing image (partition table deferred to last, so Windows cannot auto-mount mid-write)..."
$src = [System.IO.File]::OpenRead($iso.FullName)
$dst = New-Object System.IO.FileStream("\\.\PhysicalDrive$DiskNumber", [System.IO.FileMode]::Open, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None, [int]4MB, [System.IO.FileOptions]::WriteThrough)
$buf = New-Object byte[] (4MB)
$firstBlock = New-Object byte[] (4MB)
$firstLen = $src.Read($firstBlock, 0, $firstBlock.Length)
if ($firstLen % 512 -ne 0) { $pad = 512 - ($firstLen % 512); [Array]::Clear($firstBlock, $firstLen, $pad); $firstLen += $pad }
$dst.Seek($firstLen, [System.IO.SeekOrigin]::Begin) | Out-Null
$total = [long]$firstLen; $sw = [Diagnostics.Stopwatch]::StartNew()
while (($n = $src.Read($buf, 0, $buf.Length)) -gt 0) {
    # Pad the final chunk to the 512-byte sector boundary raw device writes require
    if ($n % 512 -ne 0) {
        $pad = 512 - ($n % 512)
        [Array]::Clear($buf, $n, $pad)
        $n += $pad
    }
    $dst.Write($buf, 0, $n)
    $total += $n
    if ($total % 256MB -eq 0) { Write-Host ("  {0:N0} MB written" -f ($total/1MB)) }
}
Write-Host "Writing deferred first block (partition table)..."
$dst.Seek(0, [System.IO.SeekOrigin]::Begin) | Out-Null
$dst.Write($firstBlock, 0, $firstLen)
$dst.Flush(); $dst.Close(); $src.Close()
Write-Host ("Wrote {0:N0} bytes in {1:N0}s" -f $total, $sw.Elapsed.TotalSeconds)

Write-Host "Verifying (reading back and hashing)..."
$rd = New-Object System.IO.FileStream("\\.\PhysicalDrive$DiskNumber", [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read, [int]4MB, [System.IO.FileOptions]::None)
$sha = [Security.Cryptography.SHA256]::Create()
$remaining = $iso.Length
while ($remaining -gt 0) {
    $want = [int][math]::Min([long]$buf.Length, [long]([math]::Ceiling($remaining / 512) * 512))
    $n = $rd.Read($buf, 0, $want)
    if ($n -le 0) { throw "short read during verify" }
    $use = [int][math]::Min($n, $remaining)
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
