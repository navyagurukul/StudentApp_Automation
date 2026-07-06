# adb_setup.ps1
# Reverse port 13000 so AltTester on PC can reach the app on the Android device.
# Run this after launching the instrumented APK on the device.

adb reverse tcp:13000 tcp:13000
Write-Host "ADB reverse tcp:13000 set."
