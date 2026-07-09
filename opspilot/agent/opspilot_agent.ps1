# =====================================================================
#  BVTech OpsPilot Agent  (native PowerShell - zero dependencies)
#  Works on any Windows 10/11 or Server box out of the box: no Python,
#  no .exe, no downloads. Enrolls with a one-time token, then reports a
#  small HEALTH snapshot (CPU/RAM/disk, logged-in user, antivirus,
#  Windows Update status) on a schedule.
#
#  WHAT IT DOES NOT DO (by design): no remote command execution, no
#  screen/keystroke/file capture, no remote control. Telemetry only.
#
#  Actions:
#    enroll <TOKEN> -Url <https://portal>   register this device
#    checkin                                send one health snapshot
#    install <TOKEN> -Url <https://portal>  enroll + schedule (every 5 min + at boot)
#    uninstall                              remove the scheduled task + config
#
#  Config: %ProgramData%\BVTechOpsPilot\agent.json
# =====================================================================
[CmdletBinding()]
param(
  [Parameter(Position = 0)][string]$Action = "checkin",
  [Parameter(Position = 1)][string]$Token = "",
  [string]$Url = ""
)

$ErrorActionPreference = "Stop"
$AgentVersion = "2.1.0-ps"
$DataDir = Join-Path $env:ProgramData "BVTechOpsPilot"
$ConfigPath = Join-Path $DataDir "agent.json"
$AgentPath = Join-Path $DataDir "agent.ps1"
$LogPath = Join-Path $DataDir "agent.log"
$TaskName = "BVTechOpsPilot"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Write-Log($msg) {
  try {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    "$(Get-Date -Format o)  $msg" | Add-Content -Path $LogPath -Encoding utf8
  } catch {}
}

function Load-Config {
  if (Test-Path $ConfigPath) { return (Get-Content $ConfigPath -Raw | ConvertFrom-Json) }
  return $null
}

function Save-Config($cfg) {
  New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
  $cfg | ConvertTo-Json | Set-Content -Path $ConfigPath -Encoding ascii
}

function Normalize-Url($u) {
  $u = ($u + "").Trim().Trim('"').Trim("'").TrimEnd("/")
  if ($u -and ($u -notmatch "://")) { $u = "https://$u" }
  return $u
}

# ---- Telemetry collectors (all native, all best-effort) --------------
function Get-CpuPct {
  try {
    $c = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
    if ($c -ne $null) { return [double]$c }
  } catch {}
  return $null
}

function Get-RamPct {
  try {
    $os = Get-CimInstance Win32_OperatingSystem
    $used = $os.TotalVisibleMemorySize - $os.FreePhysicalMemory
    return [math]::Round(($used / $os.TotalVisibleMemorySize) * 100, 1)
  } catch { return $null }
}

function Get-DiskPct {
  try {
    $d = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    if ($d -and $d.Size -gt 0) {
      return [math]::Round((($d.Size - $d.FreeSpace) / $d.Size) * 100, 1)
    }
  } catch {}
  return $null
}

function Get-LoggedInUser {
  try {
    $u = (Get-CimInstance Win32_ComputerSystem).UserName
    if ($u) { return $u }
  } catch {}
  try {
    $q = (quser 2>$null)
    if ($q) { return (($q | Select-Object -Skip 1 | Select-Object -First 1) -split '\s+')[1] }
  } catch {}
  return $null
}

function Get-AvStatus {
  # Consumer Windows exposes AntiVirusProduct via the Security Center; Server
  # editions don't, so fall back to the Defender module.
  try {
    $av = Get-CimInstance -Namespace "root\SecurityCenter2" -Class AntiVirusProduct -ErrorAction Stop
    if ($av) {
      foreach ($p in @($av)) {
        # productState bit 0x1000 = enabled/on-access scanning active
        if (($p.productState -band 0x1000) -ne 0) { return "on ($($p.displayName))" }
      }
      return "off ($(@($av)[0].displayName))"
    }
  } catch {}
  try {
    $mp = Get-MpComputerStatus -ErrorAction Stop
    if ($mp.RealTimeProtectionEnabled) { return "on (Microsoft Defender)" }
    return "off (Microsoft Defender)"
  } catch {}
  return "unknown"
}

function Get-PatchInfo {
  # Count pending Windows updates via the COM API (available on all Windows).
  try {
    $session = New-Object -ComObject Microsoft.Update.Session
    $searcher = $session.CreateUpdateSearcher()
    $result = $searcher.Search("IsInstalled=0 and IsHidden=0")
    $n = $result.Updates.Count
    if ($n -eq 0) { return @{ status = "up to date"; pending = 0 } }
    return @{ status = "behind ($n pending)"; pending = $n }
  } catch {
    return @{ status = "unknown"; pending = $null }
  }
}

function Get-LocalIp {
  try {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
           Where-Object { $_.IPAddress -notlike "169.254.*" -and $_.IPAddress -ne "127.0.0.1" } |
           Select-Object -First 1).IPAddress
    if ($ip) { return $ip }
  } catch {}
  return $null
}

function Get-InstalledSoftware {
  # Read the uninstall registry keys (fast + reliable - unlike Win32_Product,
  # which is slow and triggers MSI reconfiguration). Covers 64-bit, 32-bit, and
  # per-user installs; de-duplicates by name+version.
  $paths = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
  )
  $seen = @{}
  $out = New-Object System.Collections.ArrayList
  foreach ($p in $paths) {
    try {
      Get-ItemProperty $p -ErrorAction SilentlyContinue | ForEach-Object {
        $name = $_.DisplayName
        if ($name -and -not $_.SystemComponent -and -not $_.ParentKeyName) {
          $ver = "$($_.DisplayVersion)"
          $key = ($name + "|" + $ver).ToLower()
          if (-not $seen.ContainsKey($key)) {
            $seen[$key] = $true
            [void]$out.Add(@{ name = "$name"; version = $ver; publisher = "$($_.Publisher)" })
          }
        }
      }
    } catch {}
  }
  return $out
}

function Get-PendingPatchList {
  try {
    $session = New-Object -ComObject Microsoft.Update.Session
    $searcher = $session.CreateUpdateSearcher()
    $result = $searcher.Search("IsInstalled=0 and IsHidden=0")
    $out = New-Object System.Collections.ArrayList
    foreach ($u in $result.Updates) {
      $sev = "$($u.MsrcSeverity)"; if (-not $sev) { $sev = "unspecified" }
      $kb = ""
      try { if ($u.KBArticleIDs.Count -gt 0) { $kb = "KB$($u.KBArticleIDs.Item(0))" } } catch {}
      [void]$out.Add(@{ name = "$($u.Title)"; kb = $kb; severity = $sev })
    }
    return $out
  } catch { return @() }
}

# ---- HTTP helper -----------------------------------------------------
function Invoke-Api($Method, $Uri, $Headers, $BodyObj) {
  $json = if ($BodyObj -ne $null) { $BodyObj | ConvertTo-Json -Depth 6 } else { $null }
  $ua = "BVTechOpsPilotAgent/$AgentVersion"
  return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $Headers `
         -Body $json -ContentType "application/json" -UserAgent $ua -TimeoutSec 45
}

# ---- Actions ---------------------------------------------------------
function Do-Enroll($token, $url) {
  $url = Normalize-Url $url
  if (-not $token) { throw "Enrollment token is required." }
  if (-not $url)   { throw "Portal URL is required (-Url https://portal.bvtech.org)." }
  $osCaption = try { (Get-CimInstance Win32_OperatingSystem).Caption } catch { "Windows" }
  $serial    = try { (Get-CimInstance Win32_BIOS).SerialNumber } catch { $null }
  $body = @{
    enroll_token = $token
    hostname     = $env:COMPUTERNAME
    os           = $osCaption
    serial       = $serial
  }
  $r = Invoke-Api "POST" "$url/api/agent/enroll" @{} $body
  $cfg = [ordered]@{
    url        = $url
    enroll_id  = $r.enroll_id
    agent_key  = $r.agent_key
    device_id  = $r.device_id
    enrolled   = (Get-Date -Format o)
  }
  Save-Config $cfg
  Write-Log "Enrolled as device $($r.device_id) on $url"
  return $cfg
}

function Do-Checkin {
  $cfg = Load-Config
  if (-not $cfg -or -not $cfg.enroll_id) { throw "Not enrolled - run enroll first." }
  $patch = Get-PatchInfo
  $body = @{
    cpu_pct        = Get-CpuPct
    ram_pct        = Get-RamPct
    disk_pct       = Get-DiskPct
    logged_in_user = Get-LoggedInUser
    av_status      = Get-AvStatus
    patch_status   = $patch.status
    ip             = Get-LocalIp
    agent_version  = $AgentVersion
    platform       = "windows"
  }
  $headers = @{ "X-Enroll-Id" = $cfg.enroll_id; "X-Agent-Key" = $cfg.agent_key }
  $r = Invoke-Api "POST" "$($cfg.url)/api/agent/checkin" $headers $body
  Write-Log "Check-in ok (cpu=$($body.cpu_pct) ram=$($body.ram_pct) disk=$($body.disk_pct))"

  # Full inventory (installed software + pending patch list) is heavier, so send
  # it at most hourly instead of every 5-minute tick.
  try {
    $lastFull = $null
    if ($cfg.last_full) { $lastFull = [datetime]::Parse($cfg.last_full) }
    if (-not $lastFull -or ((Get-Date) - $lastFull).TotalMinutes -ge 55) {
      Report-Inventory $cfg $headers
      Report-Patches $cfg $headers
      try { Report-Browser $cfg $headers } catch { Write-Log "Browser report skipped: $_" }
      try { Apply-BrowserPolicy $cfg $headers } catch { Write-Log "Browser policy skipped: $_" }
      $cfg | Add-Member -NotePropertyName last_full -NotePropertyValue (Get-Date -Format o) -Force
      Save-Config $cfg
    }
  } catch { Write-Log "Full inventory skipped: $_" }

  # Run any staff-approved jobs for this device (e.g. patch installs).
  try { Poll-Jobs $cfg $headers } catch { Write-Log "Job poll skipped: $_" }
  return $r
}

function Report-Inventory($cfg, $headers) {
  $sw = Get-InstalledSoftware
  Invoke-Api "POST" "$($cfg.url)/api/agent/inventory" $headers @{ software = @($sw) } | Out-Null
  Write-Log "Reported $($sw.Count) installed apps."
}

function Report-Patches($cfg, $headers) {
  $patches = Get-PendingPatchList
  Invoke-Api "POST" "$($cfg.url)/api/agent/patches" $headers @{ patches = @($patches) } | Out-Null
  Write-Log "Reported $($patches.Count) pending patches."
}


function Get-BrowserApps {
  # v1.23 Browser & SaaS Guardian: what browsers/extensions exist and which
  # web apps this machine actually uses. No dependencies, read-only, best-effort.
  $extensions = @()
  $hostCounts = @{}

  # ---- Chrome + Edge extensions (per user profile) ----
  $chromiumRoots = @(
    @{ Browser = "chrome"; Path = "AppData\Local\Google\Chrome\User Data" },
    @{ Browser = "edge";   Path = "AppData\Local\Microsoft\Edge\User Data" }
  )
  $userDirs = @(Get-ChildItem "C:\Users" -Directory -ErrorAction SilentlyContinue)
  foreach ($u in $userDirs) {
    foreach ($root in $chromiumRoots) {
      $base = Join-Path $u.FullName $root.Path
      if (-not (Test-Path $base)) { continue }
      $profiles = @(Get-ChildItem $base -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq "Default" -or $_.Name -like "Profile *" })
      foreach ($prof in $profiles) {
        $extRoot = Join-Path $prof.FullName "Extensions"
        if (-not (Test-Path $extRoot)) { continue }
        $extDirs = @(Get-ChildItem $extRoot -Directory -ErrorAction SilentlyContinue)
        foreach ($ed in $extDirs) {
          $verDir = @(Get-ChildItem $ed.FullName -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending | Select-Object -First 1)
          if (-not $verDir) { continue }
          $manifest = Join-Path $verDir[0].FullName "manifest.json"
          if (-not (Test-Path $manifest)) { continue }
          try {
            $m = Get-Content $manifest -Raw -ErrorAction Stop | ConvertFrom-Json
            $name = "$($m.name)"
            if ($name -like "__MSG_*") { $name = $ed.Name }
            $perms = ""
            if ($m.permissions) { $perms = (@($m.permissions) -join ",") }
            $extensions += @{ browser = $root.Browser; id = $ed.Name; name = $name;
                              version = "$($m.version)"; permissions = $perms }
          } catch { }
        }
        # ---- web apps: harvest domains from this profile's History (binary scan) ----
        $hist = Join-Path $prof.FullName "History"
        Add-HostCounts $hist $hostCounts
        $bk = Join-Path $prof.FullName "Bookmarks"
        Add-HostCounts $bk $hostCounts
      }
    }
    # ---- Firefox: extensions + places history ----
    $ffRoot = Join-Path $u.FullName "AppData\Roaming\Mozilla\Firefox\Profiles"
    if (Test-Path $ffRoot) {
      $ffProfiles = @(Get-ChildItem $ffRoot -Directory -ErrorAction SilentlyContinue)
      foreach ($fp in $ffProfiles) {
        $extJson = Join-Path $fp.FullName "extensions.json"
        if (Test-Path $extJson) {
          try {
            $fx = Get-Content $extJson -Raw -ErrorAction Stop | ConvertFrom-Json
            foreach ($a in @($fx.addons)) {
              if ("$($a.type)" -ne "extension") { continue }
              if ("$($a.location)" -eq "app-builtin") { continue }
              $nm = "$($a.defaultLocale.name)"
              if (-not $nm) { $nm = "$($a.id)" }
              $extensions += @{ browser = "firefox"; id = "$($a.id)"; name = $nm;
                                version = "$($a.version)"; permissions = "" }
            }
          } catch { }
        }
        Add-HostCounts (Join-Path $fp.FullName "places.sqlite") $hostCounts
      }
    }
  }

  $domains = @()
  $sorted = $hostCounts.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 40
  foreach ($kv in @($sorted)) {
    $domains += @{ host = $kv.Key; hits = [int]$kv.Value }
  }
  return @{ extensions = @($extensions | Select-Object -First 100); domains = @($domains) }
}

function Add-HostCounts($filePath, $counts) {
  # Extract https://host occurrences from a (possibly binary/locked) file by
  # copying it first, then ASCII-scanning. Best-effort; caps big files.
  if (-not (Test-Path $filePath)) { return }
  try {
    $fi = Get-Item $filePath -ErrorAction Stop
    if ($fi.Length -gt 100MB) { return }
    $tmp = Join-Path $env:TEMP ("pulse_bh_" + [System.IO.Path]::GetRandomFileName())
    Copy-Item $filePath $tmp -Force -ErrorAction Stop
    try {
      $bytes = [System.IO.File]::ReadAllBytes($tmp)
      $text = [System.Text.Encoding]::ASCII.GetString($bytes)
      $rx = [regex]"https?://([a-z0-9][a-z0-9\.\-]{2,120})"
      $found = $rx.Matches($text)
      foreach ($m in $found) {
        $h = $m.Groups[1].Value.ToLower().TrimEnd(".")
        if ($h.StartsWith("www.")) { $h = $h.Substring(4) }
        if ($h -notmatch "\.") { continue }
        if ($counts.ContainsKey($h)) { $counts[$h] = $counts[$h] + 1 }
        else { $counts[$h] = 1 }
      }
    } finally {
      Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
  } catch { }
}

function Report-Browser($cfg, $headers) {
  $b = Get-BrowserApps
  Invoke-Api "POST" "$($cfg.url)/api/agent/browser" $headers $b | Out-Null
  Write-Log "Reported $($b.extensions.Count) extensions + $($b.domains.Count) web-app domains."
}

function Apply-BrowserPolicy($cfg, $headers) {
  # Pull this device's browser policy and ENFORCE it (idempotent):
  #   blocked domains    -> hosts-file sinkhole between PULSE markers
  #   blocked extensions -> Chrome/Edge ExtensionInstallBlocklist policy
  #   protect            -> SafeBrowsing (Chrome) + SmartScreen (Edge) forced on
  $pol = Invoke-Api "GET" "$($cfg.url)/api/agent/browser-policy" $headers $null
  if (-not $pol) { return }

  # ---- hosts-file domain blocks ----
  $hostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
  $beginMark = "# BEGIN PULSE BROWSER GUARD"
  $endMark = "# END PULSE BROWSER GUARD"
  try {
    $lines = @()
    if (Test-Path $hostsPath) { $lines = @(Get-Content $hostsPath -ErrorAction Stop) }
    $keep = @()
    $inBlock = $false
    foreach ($ln in $lines) {
      if ($ln -eq $beginMark) { $inBlock = $true; continue }
      if ($ln -eq $endMark) { $inBlock = $false; continue }
      if (-not $inBlock) { $keep += $ln }
    }
    $blockLines = @()
    foreach ($d in @($pol.blocked_domains)) {
      if (-not $d) { continue }
      $blockLines += "0.0.0.0 $d"
      $blockLines += "0.0.0.0 www.$d"
    }
    $newLines = $keep
    if ($blockLines.Count -gt 0) {
      $newLines = $keep + @($beginMark) + $blockLines + @($endMark)
    }
    $oldText = ($lines -join "`n")
    $newText = ($newLines -join "`n")
    if ($oldText -ne $newText) {
      [System.IO.File]::WriteAllLines($hostsPath, $newLines)
      Write-Log "Hosts guard updated ($($blockLines.Count) block lines)."
    }
  } catch { Write-Log "Hosts guard skipped: $_" }

  # ---- Chrome/Edge extension blocklist (policy registry) ----
  $policyRoots = @(
    "HKLM:\SOFTWARE\Policies\Google\Chrome\ExtensionInstallBlocklist",
    "HKLM:\SOFTWARE\Policies\Microsoft\Edge\ExtensionInstallBlocklist"
  )
  foreach ($root in $policyRoots) {
    try {
      if (-not (Test-Path $root)) { New-Item -Path $root -Force | Out-Null }
      # Clear only OUR slots (901-940), then write the current list.
      for ($i = 901; $i -le 940; $i++) {
        Remove-ItemProperty -Path $root -Name "$i" -ErrorAction SilentlyContinue
      }
      $slot = 901
      foreach ($ext in @($pol.blocked_extensions)) {
        if (-not $ext) { continue }
        if ($slot -gt 940) { break }
        New-ItemProperty -Path $root -Name "$slot" -Value "$ext" -PropertyType String -Force | Out-Null
        $slot = $slot + 1
      }
    } catch { Write-Log "Extension blocklist skipped for ${root}: $_" }
  }

  # ---- browser protection hardening ----
  try {
    $chromePol = "HKLM:\SOFTWARE\Policies\Google\Chrome"
    $edgePol = "HKLM:\SOFTWARE\Policies\Microsoft\Edge"
    if ($pol.protect) {
      foreach ($p in @($chromePol, $edgePol)) {
        if (-not (Test-Path $p)) { New-Item -Path $p -Force | Out-Null }
      }
      New-ItemProperty -Path $chromePol -Name "SafeBrowsingProtectionLevel" -Value 1 -PropertyType DWord -Force | Out-Null
      New-ItemProperty -Path $edgePol -Name "SmartScreenEnabled" -Value 1 -PropertyType DWord -Force | Out-Null
      New-ItemProperty -Path $edgePol -Name "SmartScreenPuaEnabled" -Value 1 -PropertyType DWord -Force | Out-Null
    } else {
      Remove-ItemProperty -Path $chromePol -Name "SafeBrowsingProtectionLevel" -ErrorAction SilentlyContinue
      Remove-ItemProperty -Path $edgePol -Name "SmartScreenEnabled" -ErrorAction SilentlyContinue
      Remove-ItemProperty -Path $edgePol -Name "SmartScreenPuaEnabled" -ErrorAction SilentlyContinue
    }
  } catch { Write-Log "Browser protect skipped: $_" }
}

function Install-ApprovedPatches($kbsSpec) {
  # Install Windows Updates via the native Update API. $kbsSpec is either the
  # string "all" or an array of KB ids (e.g. "KB5035000"). Returns a result
  # hashtable { exit_code, output }. NEVER installs anything not approved.
  try {
    $session = New-Object -ComObject Microsoft.Update.Session
    $searcher = $session.CreateUpdateSearcher()
    $result = $searcher.Search("IsInstalled=0 and IsHidden=0")
    $toInstall = New-Object -ComObject Microsoft.Update.UpdateColl
    $wantAll = ($kbsSpec -is [string] -and $kbsSpec -eq "all")
    $wantSet = @{}
    if (-not $wantAll) { foreach ($k in @($kbsSpec)) { $wantSet["$k".ToUpper()] = $true } }
    $names = New-Object System.Collections.ArrayList
    foreach ($u in $result.Updates) {
      $match = $wantAll
      if (-not $match) {
        try { foreach ($id in $u.KBArticleIDs) { if ($wantSet.ContainsKey("KB$id")) { $match = $true } } } catch {}
      }
      if ($match) {
        if ($u.EulaAccepted -eq $false) { try { $u.AcceptEula() } catch {} }
        [void]$toInstall.Add($u)
        [void]$names.Add("$($u.Title)")
      }
    }
    if ($toInstall.Count -eq 0) {
      return @{ exit_code = 0; output = "No matching approved updates were pending." }
    }
    $downloader = $session.CreateUpdateDownloader(); $downloader.Updates = $toInstall
    $dl = $downloader.Download()
    $installer = $session.CreateUpdateInstaller(); $installer.Updates = $toInstall
    $ir = $installer.Install()
    # ResultCode: 2 = Succeeded, 3 = Succeeded with errors, others = trouble.
    $ok = ($ir.ResultCode -eq 2 -or $ir.ResultCode -eq 3)
    $reboot = if ($ir.RebootRequired) { " REBOOT REQUIRED." } else { "" }
    $out = "Installed $($toInstall.Count) update(s): " + ($names -join "; ") + ".$reboot (resultCode=$($ir.ResultCode))"
    $code = if ($ok) { 0 } else { 1 }
    return @{ exit_code = $code; output = $out }
  } catch {
    return @{ exit_code = 1; output = "Patch install failed: $_" }
  }
}

function Poll-Jobs($cfg, $headers) {
  # Pull approved jobs for this device and run the ones we understand. Today we
  # only handle winupdate jobs (governed patch installs) - other job languages
  # are left for the console/remote flow and reported as unsupported.
  try {
    $resp = Invoke-Api "GET" "$($cfg.url)/api/agent/jobs" $headers $null
  } catch { return }
  foreach ($j in @($resp.jobs)) {
    $res = $null
    if ($j.language -eq "winupdate") {
      $kbs = "all"
      try { $parsed = ($j.content | ConvertFrom-Json); if ($parsed.kbs) { $kbs = $parsed.kbs } } catch {}
      Write-Log "Running winupdate job $($j.id) (kbs=$kbs)"
      $res = Install-ApprovedPatches $kbs
      # Refresh the reported pending set after installing.
      try { Report-Patches $cfg $headers } catch {}
    } else {
      $res = @{ exit_code = 1; output = "Unsupported job language '$($j.language)' for this agent." }
    }
    try {
      Invoke-Api "POST" "$($cfg.url)/api/agent/jobs/$($j.id)/result" $headers `
        @{ exit_code = [int]$res.exit_code; output = "$($res.output)" } | Out-Null
      Write-Log "Reported job $($j.id) result (exit=$($res.exit_code))"
    } catch { Write-Log "Failed to report job $($j.id): $_" }
  }
}

function Register-Task {
  # A Scheduled Task that runs one check-in at startup AND every 5 minutes,
  # forever, as SYSTEM. No long-lived process to die - each tick is a fresh,
  # ~2-second run. Far more reliable than a background loop.
  $psexe = (Get-Command powershell.exe).Source
  $args = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$AgentPath`" checkin"
  $action = New-ScheduledTaskAction -Execute $psexe -Argument $args
  $atStartup = New-ScheduledTaskTrigger -AtStartup
  $repeating = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
                 -RepetitionInterval (New-TimeSpan -Minutes 5) `
                 -RepetitionDuration ([TimeSpan]::MaxValue)
  $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
                -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
  Register-ScheduledTask -TaskName $TaskName -Action $action `
    -Trigger @($atStartup, $repeating) -Principal $principal -Settings $settings -Force | Out-Null
  Write-Log "Scheduled task '$TaskName' registered (startup + every 5 min)."
}

function Do-Install($token, $url) {
  New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
  # Persist this very script so the scheduled task can re-run it (skip if we're
  # already running from the install location).
  if ($PSCommandPath -and ((Resolve-Path $PSCommandPath).Path -ne $AgentPath)) {
    Copy-Item -Path $PSCommandPath -Destination $AgentPath -Force
  }
  $cfg = Do-Enroll $token $url
  Register-Task
  # Immediate first check-in so the device shows up in seconds, not minutes.
  try { Do-Checkin | Out-Null } catch { Write-Log "First check-in failed: $_" }
  return $cfg
}

function Do-Uninstall {
  try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop } catch {}
  try { Remove-Item -Recurse -Force $DataDir -ErrorAction Stop } catch {}
  Write-Host "BVTech OpsPilot agent removed."
}

# ---- Dispatch --------------------------------------------------------
try {
  switch ($Action.ToLower()) {
    "enroll"    { Do-Enroll $Token $Url | Out-Null; Write-Host "Enrolled." }
    "checkin"   { Do-Checkin | Out-Null }
    "install"   { Do-Install $Token $Url | Out-Null; Write-Host "Installed and enrolled." }
    "uninstall" { Do-Uninstall }
    default     { Write-Host "Unknown action '$Action'. Use enroll|checkin|install|uninstall." ; exit 2 }
  }
  exit 0
} catch {
  Write-Log "ERROR ($Action): $_"
  Write-Host "ERROR: $_"
  exit 1
}
