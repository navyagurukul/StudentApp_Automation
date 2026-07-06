# StudentApp_Automation

UI test automation for the **English Gurukul Student** app (Unity) using
**AltTester** + Python **pytest**. Page Object Model, with a Slack reporter that
posts per-user results after each run. Translated from the in-repo C# suite
(`csharp/EnglishGurukul.AltTests`).

## Layout

```
├── conftest.py                # alt_session fixture (connects AltDriver)
├── pytest.ini                 # markers: smoke, regression
├── requirements.txt
├── config/
│   ├── defaults.json          # alt_host / alt_port / alt_app_name
│   └── test_users.json        # the students/flows to drive
├── framework/
│   ├── driver_session.py      # AltDriver wrapper (find/tap/set-text/scene waits)
│   ├── slack_reporter.py      # posts per-user pass/fail to Slack
│   ├── config_loader.py · waits.py
├── pages/                     # Page Objects: login, home, registration, language,
│                              #   quiz, stories, wordfun
├── tests/                     # test_login_smoke, test_registration, test_regression,
│                              #   test_stories_flow, test_wordfun_flow
├── scripts/                   # check_server.py, adb_setup.ps1, run_daily.ps1
├── tools/altserver_relay.py   # free AltServer (relay) — run tests without a license
└── .github/workflows/         # ci.yml (sanity) + daily-tests.yml (self-hosted -> Slack)
```

## How it connects

The instrumented app connects out to an **AltServer** at `ws://ALT_HOST:ALT_PORT`
(`127.0.0.1:13000`), and the tests' AltDriver connects to the same server. Over
USB that means `adb reverse tcp:13000 tcp:13000`. The AltServer is either:

- **AltTester Desktop** (official, needs a license), or
- **`tools/altserver_relay.py`** (bundled, license-free) — start it and go.

> The installed APK registers as app-name **`__default__`** (a fresh build uses
> `EnglishGurukulStudentApp`). Set `ALT_APP_NAME` to match what's installed.

## Run locally

```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 1) start the free AltServer relay (or open AltTester Desktop)
python tools/altserver_relay.py --host 127.0.0.1 --port 13000

# 2) bridge the device + launch the app
adb reverse tcp:13000 tcp:13000
adb shell monkey -p com.OritSciencesPrivateLimited.EnglishGurukul.student -c android.intent.category.LAUNCHER 1

# 3) preflight + run
$env:ALT_APP_NAME = "__default__"
python scripts/check_server.py
pytest tests/test_login_smoke.py -v        # or: pytest -v   (whole suite)
```

Results are posted to **Slack** by `framework/slack_reporter.py` (set
`SLACK_WEBHOOK_URL`, else it uses the built-in default).

## Daily CI/CD -> Slack

These tests drive a **real device**, so GitHub's cloud runners can't run them.
Two supported ways to run daily and report to Slack:

- **Self-hosted runner** (`.github/workflows/daily-tests.yml`) — register a
  self-hosted runner on the Windows box with the Pixel
  attached, add repo secret `SLACK_WEBHOOK_URL`. Runs 07:00 IST daily + on demand.
- **Windows Task Scheduler** (`scripts/run_daily.ps1`) — no runner needed; runs
  the same suite locally and posts to Slack:
  ```powershell
  schtasks /Create /TN "StudentApp QA Daily" /SC DAILY /ST 07:00 /F `
    /TR "powershell -NoProfile -ExecutionPolicy Bypass -File `"$PWD\scripts\run_daily.ps1`""
  ```

`.github/workflows/ci.yml` runs a **device-free sanity** check (install + compile
+ `pytest --collect-only`) on every push/PR.

## Markers

`smoke` (quick login sanity) · `regression` (full multi-user flows).
