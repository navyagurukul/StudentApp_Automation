"""
tests/test_wordfun_flow.py
--------------------------
WordFun flow smoke test.

Flow exercised:
    Login (first existing user)
        → dismiss Begin scene (enter / skip)
        → Continue on ProfileDialogue
        → tap WordFun on HomeCorner
        → enumerate every topic under TopicParent and, for each:
            open topic → loop every Subtopic(Clone):
                open subtopic → (skip video if present) → attempt quiz
            tap SubModules BackBtn → back to topic list
        → tap Modules BackBtn → back to HomeCorner
        → assert HomeCorner/bg visible
"""

import logging

import pytest

from framework.config_loader import load_test_users
from pages.home_page import HomePage
from pages.login_page import LoginPage
from pages.wordfun_page import WordFunPage
from tests.test_login_smoke import _dismiss_begin_screen, _get_current_scene

logger = logging.getLogger(__name__)


# Max seconds to wait for each quiz to appear after opening a subtopic.
# Video lessons need a generous upper bound; trophy (quiz-only) subtopics
# return well before this.
QUIZ_WAIT_SECONDS = 300


@pytest.mark.smoke
def test_wordfun_play_all_topics(alt_session):
    """
    Open WordFun and play every topic listed under TopicParent. Per topic,
    play every subtopic (skipping video if present, going straight to quiz
    on trophy subtopics). Back-navigate between topics, finishing at
    HomeCorner.
    """
    users = load_test_users()
    user  = users[0]

    if user.get("flow") != "existing":
        pytest.skip("First user is not configured for existing-user flow.")

    login_page    = LoginPage(alt_session)
    home_page     = HomePage(alt_session)
    wordfun_page  = WordFunPage(alt_session)

    # ── 1. Login ─────────────────────────────────────────────────────────
    login_page.wait_for_login_ready(timeout=45)
    login_page.enter_mobile_number(user["mobileNumber"])
    login_page.tap_confirm()
    logger.info("Login submitted for %s", user["mobileNumber"])

    # ── 2. Post-login panel handling ─────────────────────────────────────
    screen = login_page.wait_for_active_screen(timeout=20)
    logger.info("Post-login screen: %s", screen)

    if screen == "SelectProfile":
        login_page.select_profile_by_index(user.get("profileIndex", 1))
        login_page.tap_select_profile_next()
        login_page.tap_avatar_save()
        login_page.handle_language_dialog(user.get("studentLanguageIndex", 0))
    elif screen == "Language":
        login_page.handle_language_dialog(user.get("studentLanguageIndex", 0))
    elif screen == "License":
        pytest.skip("License/new-user flow not covered by this test.")

    # ── 3. Get to ParentsScreen ──────────────────────────────────────────
    if _get_current_scene(alt_session) != "ParentsScreen":
        _dismiss_begin_screen(alt_session, home_page, tap_timeout=60)

    # ── 4. ProfileDialogue Continue ──────────────────────────────────────
    home_page.tap_continue_on_profile_dialogue(timeout=30)

    # ── 5. WordFun → enumerate and play every topic ─────────────────────
    wordfun_page.tap_wordfun(timeout=30)

    summary = wordfun_page.play_all_topics(
        quiz_wait_seconds=QUIZ_WAIT_SECONDS,
        between_lessons_seconds=2.0,
    )

    # ── 6. Verify we're back on HomeCorner ──────────────────────────────
    wordfun_page.assert_at_home_corner(timeout=20)

    assert summary["topics_played"] > 0, (
        "No WordFun topics were played — check TopicParent enumeration."
    )
    assert summary["lessons_played"] > 0, (
        "No lessons were played across any topic — check subtopic detection "
        "or quiz wait timing."
    )
    logger.info(
        "✓ WordFun flow PASSED — %d topic(s), %d lesson(s) total.",
        summary["topics_played"], summary["lessons_played"],
    )
