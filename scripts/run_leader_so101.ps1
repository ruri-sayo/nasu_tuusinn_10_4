# Stream both SO-101 leaders from this laptop to the car PC (provisional, F-003).
#
# Usage: powershell -File scripts\run_leader_so101.ps1 -FollowerHost nasc
# Each side runs in its own window; close a window or press Ctrl+C there to stop it.
# Side Effects: opens the leader serial ports; sends UDP 47110/47111; writes logs\.
param(
  [Parameter(Mandatory = $true)][string]$FollowerHost,
  [string]$LeRobotPython = "$env:USERPROFILE\lebot\lerobot\.venv\Scripts\python.exe",
  [string]$HardwareDir = "$env:USERPROFILE\hardware",
  [string[]]$Sides = @('left', 'right')
)
$repo = Split-Path -Parent $PSScriptRoot
foreach ($side in $Sides) {
  Start-Process -FilePath $LeRobotPython -WorkingDirectory $repo -ArgumentList @(
    'scripts\so101_leader_stream.py', '--side', $side,
    '--follower-host', $FollowerHost, '--hardware-dir', "`"$HardwareDir`""
  )
}
