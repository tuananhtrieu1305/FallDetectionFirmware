param([Parameter(Mandatory=$true)][string]$BrokerAddress)
$ErrorActionPreference = 'Stop'
$ip = $null
if (-not [System.Net.IPAddress]::TryParse($BrokerAddress, [ref]$ip) -or
    $ip.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork -or
    [System.Net.IPAddress]::IsLoopback($ip) -or $BrokerAddress -eq '0.0.0.0') {
    throw 'ESP32 requires the laptop LAN IPv4, not loopback or all interfaces'
}
$repoRoot = Split-Path -Parent $PSScriptRoot
$secretsPath = Join-Path $repoRoot 'build\phase8_2_3\broker\client_secrets.json'
$localPath = Join-Path $repoRoot 'main\network_config.local.h'
if (-not (Test-Path -LiteralPath $localPath)) { throw 'Configure the ignored Wi-Fi local header first' }
$secrets = Get-Content -Raw -LiteralPath $secretsPath | ConvertFrom-Json
if ($secrets.deviceId -notmatch '^[A-Za-z0-9_-]{1,48}$' -or
    $secrets.deviceUsername -notmatch '^[A-Za-z0-9_-]{1,64}$' -or
    $secrets.devicePassword -notmatch '^[a-f0-9]{48}$') {
    throw 'Demo client configuration invalid; no local header changes made'
}
$text = [System.IO.File]::ReadAllText($localPath)
$begin = '/* BEGIN PHASE8_2_3_MQTT_LOCAL */'
$end = '/* END PHASE8_2_3_MQTT_LOCAL */'
$pattern = [regex]::Escape($begin) + '.*?' + [regex]::Escape($end)
$withoutManaged = [regex]::Replace($text, $pattern, '', 'Singleline')
if ($withoutManaged -match '(?m)^\s*#\s*define\s+NETWORK_MQTT_') {
    throw 'MQTT macros already configured outside managed block; review locally to avoid overwriting them'
}
$block = @"
$begin
#define NETWORK_MQTT_BROKER_URI "mqtt://${BrokerAddress}:1883"
#define NETWORK_MQTT_DEVICE_ID "$($secrets.deviceId)"
#define NETWORK_MQTT_USERNAME "$($secrets.deviceUsername)"
#define NETWORK_MQTT_PASSWORD "$($secrets.devicePassword)"
$end
"@
if ($text.Contains($begin) -xor $text.Contains($end)) {
    throw 'Incomplete managed block; review local header first'
}
if ($text.Contains($begin)) {
    $text = [regex]::Replace($text, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{param($match) $block}, 'Singleline')
} else { $text = $text.TrimEnd() + "`r`n`r`n" + $block + "`r`n" }
[System.IO.File]::WriteAllText($localPath, $text, (New-Object System.Text.UTF8Encoding($false)))
Write-Output 'MQTT local block configured; Wi-Fi content preserved. Credentials not printed. Rebuild/flash required.'
