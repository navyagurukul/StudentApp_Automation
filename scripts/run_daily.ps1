# Daily student-app UI run -> Slack. Point Windows Task Scheduler at this file.
# Reliable device path (no self-hosted GitHub runner needed): starts the free
# AltServer relay, bridges the device, launches the app, and runs the suite —
# the tests self-report to Slack via framework/slack_reporter.py.
#
# Register the task (07:00 daily):
#   schtasks /Create /TN "StudentApp QA Daily" /SC DAILY /ST 07:00 /F ^
#     /TR "powershell -NoProfile -ExecutionPolicy Bypass -File \"C:\path\to\scripts\run_daily.ps1\""

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
Set-Location $root

$env:ALT_HOST = "127.0.0.1"
$env:ALT_PORT = "13000"
# Installed APK registers as __default__ (a fresh build uses EnglishGurukulStudentApp).
if (-not $env:ALT_APP_NAME) { $env:ALT_APP_NAME = "__default__" }
# Set SLACK_WEBHOOK_URL in the environment (or the framework falls back to its default).

$pkg = "com.OritSciencesPrivateLimited.EnglishGurukul.student"

# 1) start the free relay (AltServer) if nothing is on 13000
if (-not (Get-NetTCPConnection -State Listen -LocalPort 13000 -ErrorAction SilentlyContinue)) {
    Start-Process python -ArgumentList "-u","tools/altserver_relay.py","--host","127.0.0.1","--port","13000"
    Start-Sleep -Seconds 3
}

# 2) bridge device + fresh launch (clean login state + pre-granted permissions)
adb reverse tcp:13000 tcp:13000
adb shell pm clear $pkg
# allow notifications (shown before entering the number) + mic (speech questions)
adb shell pm grant $pkg android.permission.POST_NOTIFICATIONS
adb shell pm grant $pkg android.permission.RECORD_AUDIO
adb shell monkey -p $pkg -c android.intent.category.LAUNCHER 1

# 3) preflight + wait for the app to connect to the relay (fresh boot is slow)
python scripts/check_server.py
$ok = $false
for ($i = 0; $i -lt 20; $i++) {
    python -c "from alttester import AltDriver; a=AltDriver(host='127.0.0.1',port=13000,app_name='__default__',timeout=8); a.get_current_scene(); a.stop()"
    if ($LASTEXITCODE -eq 0) { $ok = $true; break }
    Start-Sleep -Seconds 8
}

# 4) run (tests post to Slack on completion)
python -m pytest -v -ra --html=reports/report.html --self-contained-html
exit $LASTEXITCODE
