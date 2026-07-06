"""
tests/test_login_smoke.py
-------------------------
Smoke test — direct translation of RunUserFlow() from SceneLoadTests.cs.

Scene flow (from C# source)
-----------------------------
  SplashScreen
    "Type mobile" input  →  "Confrim" button
    ↓
    poll 20 s for one of:
      "Canvas/LoginUIC(Clone)/Select Profile"   → SelectProfile path
      "Canvas/LoginUIC(Clone)/LicenceCode"      → License path
      "Canvas/LanguageDialogue(Clone)"          → Language path
      (none)                                    → went directly to Begin
    ↓
    (SelectProfile path)
      GurdianParent children  →  bg/screen/next
      → "Canvas/LoginUIC(Clone)/Select Your Avatar"  →  bg/screen/save
      → optional "Canvas/LanguageDialogue(Clone)"
    ↓
    check SceneManager.GetActiveScene().name
      == "Begin"        → click "Timeline/EnterScreen/enter button"
                          → WaitUntil scene == "ParentsScreen"
      == "ParentsScreen" → go straight to logout
    ↓
    "ParentCanvas/Home CornerScren/Header/Parent's Corner"  (typo intentional)
    "Canvas PC/parent's Corner/Header/LogOut"
"""

import logging
import time

import pytest

from framework.config_loader import load_test_users
from framework.slack_reporter import SlackReporter
from pages.home_page import HomePage
from pages.login_page import LoginPage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers — imported by test_regression.py
# ---------------------------------------------------------------------------

def _dismiss_begin_screen(alt_session, home_page: HomePage, tap_timeout=60) -> None:
    """
    Click the Skip button on the door enter screen
    (//Canvas/SkipAnim/Text (TMP)) to bypass the intro animation and land
    on ParentsScreen. Replaces the previous enter-button tap, which fired
    the door animation instead of skipping it.
    """
    logger.info("Waiting for Begin scene …")
    alt_session.wait_for_scene("Begin", timeout=90)
    logger.info("Begin scene confirmed.")

    home_page.tap_skip_if_visible(timeout=tap_timeout)
    logger.info("Skip button clicked — waiting for ParentsScreen …")

    _wait_for_parents_screen(alt_session, timeout=60)
    logger.info("ParentsScreen active ✓")


def _wait_for_parents_screen(alt_session, timeout=60) -> None:
    """
    C#: yield return new WaitUntil(() => GetActiveScene().name == "ParentsScreen")
    """
    deadline = time.monotonic() + timeout
    last_scene = None
    while time.monotonic() < deadline:
        try:
            last_scene = alt_session.get_current_scene()
            if last_scene == "ParentsScreen":
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise AssertionError(
        f"ParentsScreen did not become active within {timeout}s.\n"
        f"Current scene is still '{last_scene}'.\n"
        "If still on 'Begin' → enter button onClick didn't fire (check listener wiring "
        "or the assembly arg in _invoke_onclick).\n"
        "If on a loading/transition scene → network or asset-load is slow; raise timeout.\n"
        "If on an unexpected scene → app routed somewhere else after enter."
    )


def _get_current_scene(alt_session) -> str | None:
    try:
        return alt_session.get_current_scene()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

@pytest.mark.smoke
def test_existing_user_login_smoke(alt_session):
    """
    Happy-path smoke for the first configured existing user.
    Translated line-by-line from SceneLoadTests.cs RunUserFlow().
    """
    users = load_test_users()
    user  = users[0]

    if user.get("flow") != "existing":
        pytest.skip("First user is not configured for existing-user flow.")

    reporter   = SlackReporter(total_users=1)
    login_page = LoginPage(alt_session)
    home_page  = HomePage(alt_session)

    # ── 1. Login ──────────────────────────────────────────────────────────
    login_page.wait_for_login_ready(timeout=45)
    login_page.enter_mobile_number(user["mobileNumber"])
    login_page.tap_confirm()
    reporter.write_log(user["mobileNumber"], True, "Mobile Number Entered Test Case")
    logger.info("Login submitted for %s", user["mobileNumber"])

    # ── 2. Post-login panel detection (returns None if app → Begin directly)
    screen = login_page.wait_for_active_screen(timeout=20)
    logger.info("Post-login screen: %s", screen)

    # ── 3. Handle whichever panel appeared ───────────────────────────────
    if screen == "SelectProfile":
        login_page.select_profile_by_index(user.get("profileIndex", 1))
        login_page.tap_select_profile_next()
        reporter.write_log(user["mobileNumber"], True, "Existing User Profile Selected Test Case")
        login_page.tap_avatar_save()
        reporter.write_log(user["mobileNumber"], True, "Existing User Avatar Screen Test Case")
        login_page.handle_language_dialog(user.get("studentLanguageIndex", 0))
        reporter.write_log(user["mobileNumber"], True, "Existing User Language Selection Screen Test Case Passes")

    elif screen == "Language":
        login_page.handle_language_dialog(user.get("studentLanguageIndex", 0))
        reporter.write_log(user["mobileNumber"], True, "Existing User Language Selection Screen Test Case Passes")

    elif screen == "License":
        pytest.skip("License/new-user flow — handled by test_regression.py.")

    # screen is None → app went directly to Begin (handled below)

    # ── 4. C# line 472: check current scene ──────────────────────────────
    current_scene = _get_current_scene(alt_session)
    logger.info("Scene after login flow: %s", current_scene)

    if current_scene == "ParentsScreen":
        reporter.write_log(user["mobileNumber"], True, "ParentsScreen scene became active")
    else:
        # Begin scene (or transitioning to it)
        _dismiss_begin_screen(alt_session, home_page, tap_timeout=60)
        reporter.write_log(user["mobileNumber"], True, "Moved to Pari Animation 1")
        reporter.write_log(user["mobileNumber"], True, "ParentsScreen scene became active")

    # ── 5. Logout ─────────────────────────────────────────────────────────
    home_page.open_parent_corner_and_logout()
    reporter.write_log(user["mobileNumber"], True, "Clicked on Logout button")
    reporter.send_all_to_slack()
    logger.info("✓ Smoke test PASSED for %s", user["mobileNumber"])
