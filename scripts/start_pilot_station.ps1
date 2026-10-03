# Start the operator station on this laptop (provisional, 2026-10-04 layout).
#
# The hub runs on the car PC; this laptop opens the booth and pilot pages on it
# and, unless -NoArm, streams both SO-101 leaders to the car PC.
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts\start_pilot_station.ps1
#   -Layout tb|bt|equirect   360° frame layout for the pilot page (default tb, X4 webcam mode)
#   -NoArm                   do not start the leader streams
# Side Effects: opens two Chrome windows (camera, microphone); starts the leader
# processes (serial ports, UDP to the car PC).
param(
  [string]$Hub = 'nasc.tailffb95c.ts.net',
  [string]$FollowerHost = 'nasc',
  [ValidateSet('tb', 'bt', 'equirect')][string]$Layout = 'tb',
  [switch]$NoArm
)
$ErrorActionPreference = 'Stop'
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'

try {
  $status = Invoke-RestMethod "https://$Hub/status" -TimeoutSec 8
  Write-Host ("hub: car_media={0} car_ctrl={1} car_state={2}" -f `
      $status.roles.car_media, $status.roles.car_ctrl, $status.control.car_state)
} catch {
  Write-Warning "hub https://$Hub/ is not reachable. Start the hub on the car PC first (PORT=5324 scripts/run_hub.sh)."
  exit 1
}

Start-Process $chrome -ArgumentList '--new-window', "https://$Hub/booth/"
Start-Sleep -Seconds 2
Start-Process $chrome -ArgumentList '--new-window', "https://$Hub/pilot/?layout=$Layout"

if (-not $NoArm) {
  & (Join-Path $PSScriptRoot 'run_leader_so101.ps1') -FollowerHost $FollowerHost
}
