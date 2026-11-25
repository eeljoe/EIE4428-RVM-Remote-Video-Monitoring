# Open inbound TCP 8080 for the RVM demo.
#
# The connection arrives on two different Windows networks: the WLAN is
# classified "Public" on this machine and the Tailscale adapter is "Private",
# so the rule has to cover every profile.  Adding it needs administrator
# rights; when this script is started from Start-RVM.bat without them, it
# relaunches itself elevated (one UAC prompt) and waits for the rule to appear.

$ruleName = 'RVM 8080'
$port = 8080

$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[firewall] inbound rule '$ruleName' already present."
    exit 0
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]$identity
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "[firewall] one-time administrator approval needed to open TCP $port ..."
    # The project path contains spaces, so the script path must be quoted inside
    # the single argument string; -ArgumentList does not quote elements itself.
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    try {
        Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $arguments
    }
    catch {
        Write-Host "[firewall] approval was refused: $($_.Exception.Message)"
        Write-Host "[firewall] right-click Start-RVM.bat and choose 'Run as administrator'."
        exit 1
    }

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        if (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue) {
            Write-Host "[firewall] inbound rule '$ruleName' added."
            exit 0
        }
    }

    Write-Host "[firewall] the rule did not appear - approve the UAC prompt, or run as administrator."
    exit 1
}

New-NetFirewallRule `
    -DisplayName $ruleName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort $port `
    -Profile Any | Out-Null

Write-Host "[firewall] inbound rule '$ruleName' added for TCP $port (profiles: Any)."
exit 0
