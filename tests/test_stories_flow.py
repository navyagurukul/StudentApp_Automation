"""
tests/test_stories_flow.py
--------------------------
Stories flow smoke test.

Flow exercised:
    Login (first existing user)
        → dismiss Begin scene (enter / skip)
        → Continue on ProfileDialogue
        → tap Stories on HomeCorner
        → tap target topic by id
        → loop every Subtopic(Clone):
            open subtopic → wait for video → attempt quiz
"""

import logging

import pytest

from framework.config_loader import load_test_users
from pages.home_page import HomePage
from pages.login_page import LoginPage
from pages.stories_page import StoriesPage
from tests.test_login_smoke import _dismiss_begin_screen, _get_current_scene

logger = logging.getLogger(__name__)


# Target topic id — captured from the running app.
# Path: //ParentCanvas/ModulesPrefab(Clone)/MyTrophiesParent/Mask/TopicParent/<id>
TARGET_TOPIC_ID = "3b8a7c30-85b7-4fae-8a82-0012b9c2529f"

# Max seconds to wait for the quiz to appear after opening a subtopic.
# The video plays for an unknown duration; the test polls for the quiz canvas
# instead of sleeping a fixed time. Set this to a safe upper bound on the
# longest lesson video in the topic.
QUIZ_WAIT_SECONDS = 300


@pytest.mark.smoke
def test_stories_topic_play_all_subtopics(alt_session):
    """
    Open the target topic and play every subtopic in order,
    attempting the quiz after each video.
    """
    users = load_test_users()
    user  = users[0]

    if user.get("flow") != "existing":
        pytest.skip("First user is not configured for existing-user flow.")

    login_page   = LoginPage(alt_session)
    home_page    = HomePage(alt_session)
    stories_page = StoriesPage(alt_session)

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

    # ── 5. Stories → Topic → loop subtopics ─────────────────────────────
    stories_page.tap_stories(timeout=30)
    stories_page.tap_topic(TARGET_TOPIC_ID, timeout=30)

    played = stories_page.play_all_subtopics(
        quiz_wait_seconds=QUIZ_WAIT_SECONDS,
        between_lessons_seconds=2.0,
    )

    assert played > 0, "No subtopics were played — check SubModulesPrefab path."
    logger.info("✓ Stories flow PASSED — played %d subtopics.", played)
