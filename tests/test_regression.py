"""
tests/test_regression.py
------------------------
Full multi-user regression — direct translation of TestUserLoginFlow() from
SceneLoadTests.cs, including resume-from-index and Slack reporting.

C# features translated
-----------------------
  PlayerPrefs.GetInt("CURRENT_USER_INDEX")  → resume_index in test_users.json
  testLogList.AddLog + TestLogger.WriteLog  → SlackReporter.write_log
  TestLogger.SendAllLogsToSlack()           → reporter.send_all_to_slack()
  RunUserFlowSafe (try/catch per user)      → try/except per user in loop
"""

import logging

import pytest

from framework.config_loader import load_test_users
from framework.slack_reporter import SlackReporter
from pages.home_page import HomePage
from pages.login_page import LoginPage
from tests.test_login_smoke import (
    _dismiss_begin_screen,
    _wait_for_parents_screen,
    _get_current_scene,
)

logger = logging.getLogger(__name__)


@pytest.mark.regression
def test_all_configured_users(alt_session):
    """
    C# equivalent of TestUserLoginFlow() — iterates every user in
    test_users.json, runs the full flow, logs results to Slack.
    """
    users    = load_test_users()
    reporter = SlackReporter(total_users=len(users))
    failures = []

    for user in users:
        mobile = user.get("mobileNumber", "unknown")
        try:
            _run_user_flow(alt_session, user, reporter)
            logger.info("✓ %s — All steps passed", mobile)
        except pytest.skip.Exception as exc:
            logger.info("– %s skipped: %s", mobile, exc)
        except Exception as exc:
            reporter.write_log(mobile, False, str(exc))
            failures.append(f"{mobile}: {exc}")
            logger.error("✗ %s FAILED: %s", mobile, exc)

    reporter.send_all_to_slack()

    if failures:
        pytest.fail(f"{len(failures)} user(s) failed:\n" + "\n".join(failures))


def _run_user_flow(alt_session, user: dict, reporter: SlackReporter) -> None:
    """
    Single-user flow — mirrors RunUserFlow() from SceneLoadTests.cs exactly,
    including which test steps are logged.
    """
    mobile     = user.get("mobileNumber", "unknown")
    login_page = LoginPage(alt_session)
    home_page  = HomePage(alt_session)

    logger.info("── %s ──", mobile)

    # ── Login ─────────────────────────────────────────────────────────────
    login_page.wait_for_login_ready(timeout=45)
    login_page.enter_mobile_number(user["mobileNumber"])
    login_page.tap_confirm()
    reporter.write_log(mobile, True, "Mobile Number Entered Test Case")

    # ── Post-login panel detection ─────────────────────────────────────────
    screen = login_page.wait_for_active_screen(timeout=20)
    logger.info("[%s] Post-login screen: %s", mobile, screen)

    # ── Handle whichever panel appeared ───────────────────────────────────
    if screen == "SelectProfile":
        login_page.select_profile_by_index(user.get("profileIndex", 1))
        login_page.tap_select_profile_next()
        reporter.write_log(mobile, True, "Existing User  Profile Selected Test Case")

        login_page.tap_avatar_save()
        reporter.write_log(mobile, True, "Existing User Avatar Screen Test Case")

        login_page.handle_language_dialog(user.get("studentLanguageIndex", 0))
        reporter.write_log(mobile, True, "Existing User Language Selection Screen Test Case Passes")

    elif screen == "Language":
        login_page.handle_language_dialog(user.get("studentLanguageIndex", 0))
        reporter.write_log(mobile, True, "Existing User Language Selection Screen Test Case Passes")

    elif screen == "License":
        # C# License branch
        login_page.enter_license_code(user.get("LicenseCode", ""))
        login_page.tap_license_confirm()
        login_page.fill_registration_form(user)
        reporter.write_log(mobile, True, "New User Created Test Case")

    # screen is None → went directly to Begin

    # ── C# line 472: string Scene = GetActiveScene().name ─────────────────
    current_scene = _get_current_scene(alt_session)
    logger.info("[%s] Scene after login flow: %s", mobile, current_scene)

    if current_scene == "ParentsScreen":
        # Already home — C# "else if (Scene == ParentsScreen)" branch
        _wait_for_parents_screen(alt_session, timeout=30)
        reporter.write_log(mobile, True, "ParentsScreen scene became active")
    else:
        # Begin scene branch — C# "if (Scene == Begin)"
        _dismiss_begin_screen(alt_session, home_page, tap_timeout=60)
        reporter.write_log(mobile, True, "Moved to Pari Animation 1")
        reporter.write_log(mobile, True, "ParentsScreen scene became active")

    # ── Logout via Parent's Corner ─────────────────────────────────────────
    home_page.open_parent_corner_and_logout()
    reporter.write_log(mobile, True, "Clicked on Logout button")
    logger.info("[%s] Logged out ✓", mobile)
