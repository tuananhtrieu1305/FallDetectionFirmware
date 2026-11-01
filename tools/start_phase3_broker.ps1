param(
    [string]$ListenAddress = '127.0.0.1',
    [string]$DeviceId = 'waist-esp32s3-001'
)
$ErrorActionPreference = 'Stop'
if ($DeviceId -notmatch '^[A-Za-z0-9_-]{1,48}$') { throw 'Invalid device ID' }
$parsedAddress = $null
if (-not [System.Net.IPAddress]::TryParse($ListenAddress, [ref]$parsedAddress) -or
    $parsedAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork -or
    $ListenAddress -eq '0.0.0.0') {
    throw 'Choose a specific laptop IPv4 address or 127.0.0.1; never all interfaces'
}
$repoRoot = Split-Path -Parent $PSScriptRoot
$brokerDirectory = Join-Path $repoRoot 'build\phase8_2_3\broker'
$configDirectory = Join-Path $brokerDirectory 'config'
$containerName = 'fall-phase3-broker'
$image = 'eclipse-mosquitto:2'
function Invoke-Docker {
    param([string[]]$DockerArguments)
    & docker @DockerArguments
    if ($LASTEXITCODE -ne 0) { throw 'Docker operation failed; existing configuration preserved' }
}
Invoke-Docker -DockerArguments @('version', '--format', '{{.Server.Version}}')
$existing = & docker ps -a --filter "name=^/$containerName`$" --format '{{.Names}}'
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Docker containers' }
if ($existing) {
    throw "Container $containerName already exists. Inspect it first; this script will not replace it."
}
New-Item -ItemType Directory -Path $brokerDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $configDirectory -Force | Out-Null
$secretsPath = Join-Path $brokerDirectory 'client_secrets.json'
if (Test-Path -LiteralPath $secretsPath) {
    $secrets = Get-Content -Raw -LiteralPath $secretsPath | ConvertFrom-Json
    if ($secrets.deviceId -ne $DeviceId) { throw 'Existing credentials belong to another device ID' }
} else {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $deviceBytes = New-Object byte[] 24
        $backendBytes = New-Object byte[] 24
        $rng.GetBytes($deviceBytes)
        $rng.GetBytes($backendBytes)
    } finally { $rng.Dispose() }
    $secrets = [pscustomobject]@{
        deviceId = $DeviceId
        deviceUsername = 'phase3-device'
        devicePassword = [BitConverter]::ToString($deviceBytes).Replace('-', '').ToLowerInvariant()
        backendUsername = 'phase3-backend'
        backendPassword = [BitConverter]::ToString($backendBytes).Replace('-', '').ToLowerInvariant()
    }
    $secrets | ConvertTo-Json | Set-Content -LiteralPath $secretsPath -Encoding Ascii
}
$config = @'
listener 1883
allow_anonymous false
password_file /mosquitto/config/passwords
acl_file /mosquitto/config/acl
persistence false
log_dest stdout
log_type all
'@
Set-Content -LiteralPath (Join-Path $configDirectory 'mosquitto.conf') -Value $config -Encoding Ascii
$acl = @"
user phase3-device
topic read iot/devices/$DeviceId/command
topic write iot/devices/$DeviceId/status
topic write iot/devices/$DeviceId/event
topic write iot/devices/$DeviceId/location
topic write iot/devices/$DeviceId/health

user phase3-backend
topic read iot/devices/$DeviceId/#
topic write iot/devices/$DeviceId/command
"@
Set-Content -LiteralPath (Join-Path $configDirectory 'acl') -Value $acl -Encoding Ascii
Invoke-Docker -DockerArguments @('pull', $image)
$imageDigest = & docker image inspect $image --format '{{index .RepoDigests 0}}'
if ($LASTEXITCODE -ne 0) { throw 'Cannot record broker image digest' }
Set-Content -LiteralPath (Join-Path $brokerDirectory 'image_digest.txt') -Value $imageDigest -Encoding Ascii
$mount = "${configDirectory}:/mosquitto/config"
$passwordArguments = @('run', '--rm', '-v', $mount, $image, 'mosquitto_passwd', '-b')
# Mosquitto 2.1 refuses -c when the file already exists. Reuse the password
# database when rebinding the demo broker; do not discard existing credentials.
if (-not (Test-Path -LiteralPath (Join-Path $configDirectory 'passwords'))) {
    $passwordArguments += '-c'
} else {
    # The password administration utility runs as root and expects root-owned
    # input; the server ownership is restored after both accounts are updated.
    Invoke-Docker -DockerArguments @('run', '--rm', '-v', $mount, $image,
        'chown', '0:0', '/mosquitto/config/passwords')
}
$passwordArguments += @('/mosquitto/config/passwords', $secrets.deviceUsername, $secrets.devicePassword)
Invoke-Docker -DockerArguments $passwordArguments
Invoke-Docker -DockerArguments @('run', '--rm', '-v', $mount, $image,
    'mosquitto_passwd', '-b', '/mosquitto/config/passwords',
    $secrets.backendUsername, $secrets.backendPassword)
Invoke-Docker -DockerArguments @('run', '--rm', '-v', $mount, $image,
    'chown', '1883:1883', '/mosquitto/config/passwords', '/mosquitto/config/acl')
Invoke-Docker -DockerArguments @('run', '--rm', '-v', $mount, $image,
    'chmod', '0600', '/mosquitto/config/passwords', '/mosquitto/config/acl')
Invoke-Docker -DockerArguments @('run', '-d', '--name', $containerName,
    '-p', "${ListenAddress}:1883:1883", '-v', $mount, $image)
Start-Sleep -Seconds 2
$running = & docker inspect $containerName --format '{{.State.Running}}'
if ($LASTEXITCODE -ne 0 -or $running -ne 'true') {
    & docker logs $containerName
    throw 'Broker exited during startup; container retained for diagnosis'
}
Write-Output "Broker started on ${ListenAddress}:1883; auth required; ACL scoped to one device."
Write-Output "Private client configuration: $secretsPath (Git ignored; do not paste into chat)."
if ($ListenAddress -eq '127.0.0.1') {
    Write-Output 'Loopback test only. ESP32 later needs the laptop LAN IP and a broker bound to that IP.'
}
