"""
scripts/check_server.py
-----------------------
Preflight check — confirms AltTester server is reachable on port 13000
before running pytest.

Usage:
    python scripts/check_server.py
    → prints OK or error message
"""

import os
import socket
import sys

host = os.environ.get("ALT_HOST", "127.0.0.1")
port = int(os.environ.get("ALT_PORT", "13000"))

try:
    with socket.create_connection((host, port), timeout=5):
        print(f"OK — AltTester server reachable at {host}:{port}")
        sys.exit(0)
except OSError as exc:
    print(f"FAIL — Cannot reach {host}:{port}: {exc}")
    print(
        "\nStartup order required:\n"
        "  1. Open AltTester Desktop (leaves server running on port 13000)\n"
        "  2. Launch the instrumented APK on device\n"
        "  3. Run: .\\scripts\\adb_setup.ps1\n"
        "  4. Run this check again\n"
        "  5. pytest tests/test_login_smoke.py -v"
    )
    sys.exit(1)
