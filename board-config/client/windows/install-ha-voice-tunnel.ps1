[CmdletBinding()]
param(
    [string]$BoardHost = '192.168.50.141',
    [string]$SshKey = 'C:\SPB_Data\.ssh\mb35x8_ed25519',
    [int]$LocalPort = 8123
)

$ErrorActionPreference = 'Stop'
$taskName = 'HomeMate HA Voice Tunnel'
$sshExe = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'

if (-not (Test-Path -LiteralPath $sshExe -PathType Leaf)) {
    throw "OpenSSH client is missing: $sshExe"
}
if (-not (Test-Path -LiteralPath $SshKey -PathType Leaf)) {
    throw "SSH key is missing: $SshKey"
}
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    throw "Scheduled task already exists: $taskName"
}
if (Get-NetTCPConnection -State Listen -LocalPort $LocalPort -ErrorAction SilentlyContinue) {
    throw "Local port is already in use: $LocalPort"
}

$arguments = @(
    '-N'
    '-L', "127.0.0.1:${LocalPort}:127.0.0.1:8123"
    '-i', $SshKey
    '-o', 'BatchMode=yes'
    '-o', 'ExitOnForwardFailure=yes'
    '-o', 'ServerAliveInterval=30'
    '-o', 'ServerAliveCountMax=3'
    "forlinx@$BoardHost"
) -join ' '

$action = New-ScheduledTaskAction -Execute $sshExe -Argument $arguments
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal `
    -UserId $userId `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'Localhost SSH tunnel to Home Assistant so Chrome can use Assist microphone' | Out-Null

Start-ScheduledTask -TaskName $taskName
Write-Output "Open Home Assistant at http://localhost:${LocalPort} and sign in once."
