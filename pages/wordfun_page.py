"""
pages/wordfun_page.py
---------------------
Page object for the WordFun flow:

    HomeCorner → WordFun
        → ModulesPrefab (topic list)
            → TopicParent/{topic_id}   (one tap per topic, looped)
                → SubModulesPrefab (subtopic list)
                    → SubTopicParent/Subtopic(Clone)[i]   (one per lesson)
                        → either:  video → quiz   (regular subtopic)
                        →     or:  quiz only      (trophy subtopic — no video)
                → SubModulesPrefab/Header/BackBtn  (back to topic list)
        → ModulesPrefab/Header/BackBtn   (back to HomeCorner)

Paths captured from the running app:
    //ParentCanvas/HomeCorner(Clone)/CourseParent/WordFun
    //ParentCanvas/ModulesPrefab(Clone)/MyTrophiesParent/Mask/TopicParent/{topic_id}
    //ParentCanvas/SubModulesPrefab(Clone)/MyTrophiesParent/Mask/SubTopicParent/Subtopic(Clone)[i]
    //ParentCanvas/SubModulesPrefab(Clone)/Header/BackBtn
    //ParentCanvas/ModulesPrefab(Clone)/Header/BackBtn
    //ParentCanvas/HomeCorner(Clone)/bg

Trophy detection: trophy subtopics have no video, so skip_video_via_slider
returns False and _wait_for_quiz picks up the quiz directly — no explicit
trophy probe needed.
"""

from __future__ import annotations

import logging
import time

from alttester import By
from framework.waits import sleep_seconds
from pages.quiz_page import QuizPage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_WORDFUN_BUTTON_PATH      = "//ParentCanvas/HomeCorner(Clone)/CourseParent/WordFun"
_HOME_CORNER_BG_PATH      = "//ParentCanvas/HomeCorner(Clone)/bg"

_MODULES_BACK_BTN_PATH    = "//ParentCanvas/ModulesPrefab(Clone)/Header/BackBtn"
_SUBMODULES_BACK_BTN_PATH = "//ParentCanvas/SubModulesPrefab(Clone)/Header/BackBtn"

# Pagination button on the module list — taps reveal the next batch of topics.
_MODULES_MORE_BTN_PATH    = "//ParentCanvas/ModulesPrefab(Clone)/MoreButton"

_TOPIC_PARENT_PATH        = "//ParentCanvas/ModulesPrefab(Clone)/MyTrophiesParent/Mask/TopicParent"
_TOPIC_GLOB_PATH          = _TOPIC_PARENT_PATH + "/*"
_TOPIC_PATH_TEMPLATE      = _TOPIC_PARENT_PATH + "/{topic_id}"

_SUBTOPIC_PARENT_PATH     = "//ParentCanvas/SubModulesPrefab(Clone)/MyTrophiesParent/Mask/SubTopicParent"
_SUBTOPIC_INDEX_PATH      = _SUBTOPIC_PARENT_PATH + "/Subtopic(Clone)[{index}]"
_SUBTOPIC_GLOB_PATH       = _SUBTOPIC_PARENT_PATH + "/Subtopic(Clone)"

# Continue-to-next-lesson button on the AutoMove screen between lessons.
_CONTINUE_TO_NEXT_LESSON_PATH = "//ParentCanvas/AutoMovePrefab(Clone)/NextButton"

# Video player Slider — dragging to maxValue skips the remaining playback.
# Absent on trophy subtopics, which is how we detect the quiz-only case.
_VIDEO_SCREEN_PATH = "//ParentCanvas/Video Screen(Clone)"
_VIDEO_SLIDER_PATH = _VIDEO_SCREEN_PATH + "/UI/bg/Slider"

# Trophy subtopics open a Start popup before the quiz. The popup lives on a
# separate PopUps canvas — note the doubled "PopUps/PopUps". Once Start is
# tapped, the same MCQ/speech/jumble quiz UI takes over.
#
# We probe several candidate roots / Start paths because the EventSystem
# click sometimes fails on the Text (TMP) child (no raycast target) and
# sometimes fails on the parent Start (different prefab build).
_TROPHY_POPUP_ROOTS = [
    "//PopUps/PopUps/TrophyMCQPopup(Clone)",
    "//PopUps/TrophyMCQPopup(Clone)",
    "//TrophyMCQPopup(Clone)",
]
_TROPHY_START_SUFFIXES = [
    "/BOX/Start/Text (TMP)",   # Text child (sometimes the only raycastable element)
    "/BOX/Start",              # parent Button (needed for onClick.Invoke)
]

# After Start, the trophy quiz screen renders MCQCanvasNew with its BG
# child visible. Used as a checkpoint that the click landed us on the
# quiz screen before regular quiz polling takes over.
_TROPHY_QUIZ_SCREEN_PATH = "//MCQCanvasNew/BG"

# After a trophy quiz finishes, TrophyResultUIC appears with a Review
# button and an Assement Review > Next button (Assement is misspelled in
# the prefab — keep exact). Review opens a per-answer review screen;
# Next advances past the trophy and back into the AutoMove flow.
_TROPHY_RESULT_ROOT      = "//Canvas PopUps/PopUps/TrophyResultUIC(Clone)"
_TROPHY_REVIEW_BTN_PATH  = _TROPHY_RESULT_ROOT + "/ReviewBtn"
_TROPHY_REVIEW_NEXT_PATH = _TROPHY_RESULT_ROOT + "/AssementReview/NextBtn"

# Some subtopics have multiple parts (A / B / C) shown as thumbnails
# inside a ResumeQuizPopUp. Click each thumbnail to play that part;
# when all parts are done, dismiss the popup via the Cross x button.
_RESUME_POPUP_ROOT       = "//Canvas PopUps/PopUps/ResumeQuizPopUp(Clone)"
_RESUME_THUMB_GLOB       = (
    _RESUME_POPUP_ROOT
    + "/BOX/Mask/Selection/VideoIcons(Clone)/LayOutGoup/*/Border/Thumbnail Image"
)
_RESUME_CROSS_BTN_PATH   = _RESUME_POPUP_ROOT + "/BOX/Cross x button"

# Safety cap for multi-part subtopics — a single subtopic with more than
# this many parts indicates a runaway loop. Raise if a real subtopic
# legitimately has more parts.
_MAX_PARTS_PER_SUBTOPIC = 10

# Safety cap on MoreButton taps — guards against runaway pagination if
# MoreButton keeps appearing forever.
_MAX_MORE_BUTTON_TAPS = 20


class WordFunPage:
    def __init__(self, session):
        self.session = session
        self.driver  = session.driver
        self.quiz    = QuizPage(session)

    # ------------------------------------------------------------------
    # Public flow
    # ------------------------------------------------------------------

    def tap_wordfun(self, timeout: int = 30) -> None:
        obj = self._wait_for_path(_WORDFUN_BUTTON_PATH, timeout=timeout)
        if obj is None:
            raise RuntimeError(
                f"WordFun button not found at '{_WORDFUN_BUTTON_PATH}' within {timeout}s.\n"
                "Verify HomeCorner is loaded and the WordFun button is active."
            )
        logger.info("Clicking WordFun.")
        self._click_or_invoke(obj, label="wordfun")

    def list_topic_ids(self, timeout: int = 30) -> list[str]:
        """
        Enumerate every TopicParent child, expanding via MoreButton until
        no new topics appear. Returns names (GUIDs) in hierarchy order;
        that determines play order.
        """
        seen: list[str] = []
        seen_set: set[str] = set()

        # Initial fetch — must find at least one topic or we error out.
        initial = self._enumerate_topic_ids_once(timeout=timeout)
        for tid in initial:
            if tid not in seen_set:
                seen.append(tid)
                seen_set.add(tid)

        if not seen:
            raise RuntimeError(
                f"No topics found under '{_TOPIC_PARENT_PATH}' within {timeout}s. "
                "Verify ModulesPrefab loaded after tapping WordFun."
            )

        # Expand via MoreButton as long as it's present and reveals new ids.
        for tap_num in range(_MAX_MORE_BUTTON_TAPS):
            more = self._wait_for_path(_MODULES_MORE_BTN_PATH, timeout=2)
            if more is None:
                break
            logger.info("Tapping MoreButton (#%d) to reveal additional topics.", tap_num + 1)
            try:
                self._click_or_invoke(more, label=f"more_button[{tap_num}]")
            except Exception as e:
                logger.warning("MoreButton tap failed: %s — stopping pagination.", e)
                break
            sleep_seconds(1.0)

            current = self._enumerate_topic_ids_once(timeout=5)
            added = 0
            for tid in current:
                if tid not in seen_set:
                    seen.append(tid)
                    seen_set.add(tid)
                    added += 1
            logger.info("MoreButton revealed %d new topic(s).", added)
            if added == 0:
                break  # MoreButton still present but no new topics — stop.

        logger.info("WordFun topics (%d total): %s", len(seen), seen)
        return seen

    def _enumerate_topic_ids_once(self, timeout: int) -> list[str]:
        """Single-shot enumeration of children under TopicParent."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                children = self.driver.find_objects(By.PATH, _TOPIC_GLOB_PATH)
            except Exception as e:
                logger.warning("find_objects on '%s' failed: %s", _TOPIC_GLOB_PATH, e)
                children = []
            ids: list[str] = []
            for c in children:
                name = getattr(c, "name", None)
                if isinstance(name, str) and name.strip():
                    ids.append(name)
            if ids:
                return ids
            time.sleep(0.5)
        return []

    def tap_topic(self, topic_id: str, timeout: int = 30) -> None:
        path = _TOPIC_PATH_TEMPLATE.format(topic_id=topic_id)
        obj = self._wait_for_path(path, timeout=timeout)
        if obj is None:
            raise RuntimeError(
                f"Topic '{topic_id}' not found at '{path}' within {timeout}s."
            )
        logger.info("Clicking topic %s.", topic_id)
        self._click_or_invoke(obj, label=f"topic:{topic_id}")

    def play_all_topics(
        self,
        quiz_wait_seconds: int = 300,
        between_lessons_seconds: float = 2.0,
        subtopic_load_timeout: int = 30,
        max_lessons_per_topic: int = 20,
        video_slider_wait_seconds: int = 5,
        topic_load_timeout: int = 30,
    ) -> dict:
        """
        Enumerate every topic, play all subtopics in each, back-navigate
        between topics, and finally back-navigate to HomeCorner.

        video_slider_wait_seconds is deliberately short (5s) — when a trophy
        subtopic has no video, we want to fall through to the quiz quickly
        rather than waiting the full 30s. Regular subtopics still get
        quiz_wait_seconds for the quiz to appear.

        Returns a dict: {"topics_played": N, "lessons_played": N, "topic_results": [...]}.
        """
        topic_ids = self.list_topic_ids(timeout=topic_load_timeout)

        results: list[dict] = []
        for i, topic_id in enumerate(topic_ids):
            logger.info(
                "=== WordFun topic %d/%d: %s ===",
                i + 1, len(topic_ids), topic_id,
            )
            self.tap_topic(topic_id, timeout=topic_load_timeout)

            try:
                lessons = self.play_all_subtopics_in_current_topic(
                    quiz_wait_seconds=quiz_wait_seconds,
                    between_lessons_seconds=between_lessons_seconds,
                    subtopic_load_timeout=subtopic_load_timeout,
                    max_lessons=max_lessons_per_topic,
                    video_slider_wait_seconds=video_slider_wait_seconds,
                )
            except Exception as e:
                logger.error("Topic %s aborted: %s", topic_id, e)
                lessons = 0

            results.append({"topic_id": topic_id, "lessons_played": lessons})

            # After each topic's subtopics finish, back to the topic list.
            # If we're already past the last topic, this still leaves us on
            # ModulesPrefab so the next iteration finds the next topic.
            self._tap_back_to_topic_list()

        # All topics done — back to HomeCorner.
        self._tap_back_to_home_corner()

        total_lessons = sum(r["lessons_played"] for r in results)
        summary = {
            "topics_played": len(results),
            "lessons_played": total_lessons,
            "topic_results": results,
        }
        logger.info("WordFun summary: %s", summary)
        return summary

    def play_all_subtopics_in_current_topic(
        self,
        quiz_wait_seconds: int = 300,
        between_lessons_seconds: float = 2.0,
        subtopic_load_timeout: int = 30,
        max_lessons: int = 20,
        video_slider_wait_seconds: int = 5,
    ) -> int:
        """
        Open the first subtopic. Then route based on what popup appears:
          • Multi-part popup (ResumeQuizPopUp) → loop every thumbnail,
            playing each part as a separate session; close popup via X.
          • Trophy popup (TrophyMCQPopup) → tap Start, play trophy quiz,
            dismiss TrophyResultUIC.
          • Neither → regular flow: skip video → quiz.

        After each lesson, re-probe between-lesson popups (AutoMove Next
        or trophy/multi-part popup re-appearance).
        """
        first_path = _SUBTOPIC_INDEX_PATH.format(index=0)
        first = self._wait_for_path(first_path, timeout=subtopic_load_timeout)
        if first is None:
            logger.warning(
                "No first subtopic at '%s' within %ds — topic has no playable lessons.",
                first_path, subtopic_load_timeout,
            )
            return 0
        logger.info("Opening first subtopic to start the lesson chain.")
        self._click_or_invoke(first, label="subtopic[0]")
        sleep_seconds(1.0)

        # Multi-part subtopic? Loop through every thumbnail.
        parts_played = self._play_all_multi_parts_if_present(
            quiz_wait_seconds=quiz_wait_seconds,
            video_slider_wait_seconds=video_slider_wait_seconds,
        )
        if parts_played > 0:
            logger.info("Multi-part subtopic complete — %d part(s) played.", parts_played)
            return parts_played

        # Not multi-part — run a single lesson chain.
        return self._play_lesson_chain(
            quiz_wait_seconds=quiz_wait_seconds,
            between_lessons_seconds=between_lessons_seconds,
            max_lessons=max_lessons,
            video_slider_wait_seconds=video_slider_wait_seconds,
        )

    def _play_lesson_chain(
        self,
        quiz_wait_seconds: int,
        between_lessons_seconds: float,
        max_lessons: int,
        video_slider_wait_seconds: int,
    ) -> int:
        """
        Run lessons in sequence until no further quiz appears.
        Routes each lesson through trophy / video paths automatically.
        """
        is_trophy = self._dismiss_trophy_popup_if_present()
        if not is_trophy:
            self.skip_video_via_slider(timeout=video_slider_wait_seconds)

        quizzes_played = 0
        for lesson_num in range(1, max_lessons + 1):
            if not self._wait_for_quiz(total_seconds=quiz_wait_seconds):
                logger.info(
                    "No further quiz appeared within %ds — chain finished "
                    "after %d lesson(s).",
                    quiz_wait_seconds, lesson_num - 1,
                )
                break

            logger.info(
                "Lesson %d — playing %s quiz.",
                lesson_num, "trophy" if is_trophy else "regular",
            )
            quiz_summary = self.quiz.play_quiz(is_trophy=is_trophy)
            logger.info("Lesson %d quiz summary: %s", lesson_num, quiz_summary)
            quizzes_played += 1

            # Trophy lessons end with TrophyResultUIC; regular lessons end
            # with AutoMovePrefab. Probe both — only the matching one acts.
            self._dismiss_trophy_result_popup_if_present()
            self._tap_continue_to_next_lesson_if_present()
            sleep_seconds(between_lessons_seconds)

            # Next lesson might shift trophy/regular — re-probe.
            is_trophy = self._dismiss_trophy_popup_if_present()
            if not is_trophy:
                self.skip_video_via_slider(timeout=video_slider_wait_seconds)
        else:
            logger.warning(
                "Hit max_lessons=%d ceiling — bump it if this topic has more.",
                max_lessons,
            )

        return quizzes_played

    def _play_all_multi_parts_if_present(
        self,
        quiz_wait_seconds: int,
        video_slider_wait_seconds: int,
    ) -> int:
        """
        If a ResumeQuizPopUp is open with thumbnails, loop through each
        one in hierarchy order, playing the corresponding part. After all
        parts are done, tap the Cross x button to close the popup.

        Returns the number of parts played (0 if no multi-part popup).
        """
        if self._wait_for_path(_RESUME_POPUP_ROOT, timeout=3) is None:
            return 0

        initial = self._list_resume_thumbnails(timeout=5)
        if not initial:
            logger.warning(
                "Multi-part popup detected at '%s' but no thumbnails matched "
                "'%s'. Closing popup and returning.",
                _RESUME_POPUP_ROOT, _RESUME_THUMB_GLOB,
            )
            self._tap_resume_popup_close_if_present()
            return 0

        total_parts = len(initial)
        logger.info("Multi-part subtopic detected — %d part(s) to play.", total_parts)
        if total_parts > _MAX_PARTS_PER_SUBTOPIC:
            logger.warning(
                "Capping at %d parts (found %d). Raise _MAX_PARTS_PER_SUBTOPIC if a real "
                "subtopic legitimately has more.",
                _MAX_PARTS_PER_SUBTOPIC, total_parts,
            )
            total_parts = _MAX_PARTS_PER_SUBTOPIC

        parts_played = 0
        for part_index in range(total_parts):
            # Re-find thumbnails each iteration — the popup may close and
            # reopen between parts, invalidating saved references.
            thumbs = self._list_resume_thumbnails(timeout=10)
            if part_index >= len(thumbs):
                logger.warning(
                    "Expected thumbnail[%d] but only %d visible — stopping multi-part loop.",
                    part_index, len(thumbs),
                )
                break

            logger.info("Multi-part: opening part %d/%d.", part_index + 1, total_parts)
            try:
                self._click_or_invoke(thumbs[part_index], label=f"multi_part_thumb[{part_index}]")
            except Exception as e:
                logger.warning("Multi-part thumbnail %d tap failed: %s", part_index, e)
                continue
            sleep_seconds(1.0)

            # Play this part — could be trophy or regular video+quiz.
            is_trophy = self._dismiss_trophy_popup_if_present()
            if not is_trophy:
                self.skip_video_via_slider(timeout=video_slider_wait_seconds)
            if self._wait_for_quiz(total_seconds=quiz_wait_seconds):
                quiz_summary = self.quiz.play_quiz(is_trophy=is_trophy)
                logger.info("Multi-part part %d quiz summary: %s", part_index + 1, quiz_summary)
            else:
                logger.warning(
                    "Multi-part part %d: quiz did not appear within %ds — "
                    "skipping to next part.",
                    part_index + 1, quiz_wait_seconds,
                )

            # End-of-part popups (trophy result or AutoMove). Either may
            # bring us back to the ResumeQuizPopUp for the next thumbnail.
            self._dismiss_trophy_result_popup_if_present()
            self._tap_continue_to_next_lesson_if_present()
            sleep_seconds(1.5)

            parts_played += 1

        # All parts done — close the popup via X if still open.
        self._tap_resume_popup_close_if_present()
        return parts_played

    def _list_resume_thumbnails(self, timeout: int = 5) -> list:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                thumbs = self.driver.find_objects(By.PATH, _RESUME_THUMB_GLOB)
                if thumbs:
                    return list(thumbs)
            except Exception:
                pass
            time.sleep(0.3)
        return []

    def _tap_resume_popup_close_if_present(self, timeout: int = 5) -> None:
        cross = self._wait_for_path(_RESUME_CROSS_BTN_PATH, timeout=timeout)
        if cross is None:
            logger.info(
                "Resume popup Cross x button not present within %ds — assuming popup already closed.",
                timeout,
            )
            return
        logger.info("Tapping Cross x to close ResumeQuizPopUp.")
        self._click_or_invoke(cross, label="resume_popup_close")
        sleep_seconds(1.0)

    def _dismiss_trophy_result_popup_if_present(self, timeout: int = 10) -> bool:
        """
        Tap ReviewBtn then AssementReview/NextBtn on TrophyResultUIC if
        the popup is visible. Returns True if the popup was found.
        """
        review = self._wait_for_path(_TROPHY_REVIEW_BTN_PATH, timeout=timeout)
        if review is None:
            return False
        logger.info("Trophy result popup — tapping Review.")
        self._click_or_invoke(review, label="trophy_review")
        sleep_seconds(1.5)

        nxt = self._wait_for_path(_TROPHY_REVIEW_NEXT_PATH, timeout=15)
        if nxt is None:
            logger.warning(
                "Trophy review Next button not found at '%s' within 15s. "
                "Result popup may have auto-dismissed.",
                _TROPHY_REVIEW_NEXT_PATH,
            )
            return True
        logger.info("Tapping Next on trophy review.")
        self._click_or_invoke(nxt, label="trophy_review_next")
        sleep_seconds(1.0)
        return True

    def assert_at_home_corner(self, timeout: int = 15) -> None:
        """Verify HomeCorner/bg is visible. Used at end of flow."""
        bg = self._wait_for_path(_HOME_CORNER_BG_PATH, timeout=timeout)
        if bg is None:
            raise RuntimeError(
                f"Did not return to HomeCorner — '{_HOME_CORNER_BG_PATH}' "
                f"not visible within {timeout}s."
            )
        logger.info("✓ HomeCorner is visible.")

    # ------------------------------------------------------------------
    # Back navigation
    # ------------------------------------------------------------------

    def _tap_back_to_topic_list(self, timeout: int = 15) -> None:
        """
        Tap the SubModulesPrefab Header BackBtn to return from the subtopic
        list back to the topic list. Logged-and-skipped if not present (some
        states auto-advance straight back).
        """
        obj = self._wait_for_path(_SUBMODULES_BACK_BTN_PATH, timeout=timeout)
        if obj is None:
            logger.info(
                "SubModules BackBtn not present within %ds — assuming already "
                "back at the topic list.",
                timeout,
            )
            return
        logger.info("Tapping SubModules BackBtn (back to topic list).")
        self._click_or_invoke(obj, label="back_to_topic_list")
        sleep_seconds(1.0)

    def _tap_back_to_home_corner(self, timeout: int = 15) -> None:
        """
        Tap the ModulesPrefab Header BackBtn to return from the topic list
        back to HomeCorner. Logged-and-skipped if not present.
        """
        obj = self._wait_for_path(_MODULES_BACK_BTN_PATH, timeout=timeout)
        if obj is None:
            logger.info(
                "Modules BackBtn not present within %ds — assuming already "
                "back at HomeCorner.",
                timeout,
            )
            return
        logger.info("Tapping Modules BackBtn (back to HomeCorner).")
        self._click_or_invoke(obj, label="back_to_home_corner")
        sleep_seconds(1.0)

    # ------------------------------------------------------------------
    # Video skip
    # ------------------------------------------------------------------

    def skip_video_via_slider(
        self,
        timeout: int = 5,
        drag_radius_px: int = 600,
        drag_duration_seconds: float = 0.8,
    ) -> bool:
        """
        Skip the lesson video by dragging the player Slider past its right
        edge. Returns True on success, False if no slider appeared (trophy
        subtopic) or the swipe failed — caller falls back to waiting for the
        quiz directly.

        Lifted from StoriesPage.skip_video_via_slider but with a shorter
        default timeout so trophy subtopics return quickly.
        """
        slider = self._wait_for_path(_VIDEO_SLIDER_PATH, timeout=timeout)
        if slider is None:
            logger.info(
                "No video slider within %ds — likely a trophy subtopic, "
                "going straight to quiz.",
                timeout,
            )
            return False

        try:
            center_x = slider.x
            center_y = slider.y
        except Exception as e:
            logger.warning("Could not read slider screen position: %s", e)
            return False

        start = {"x": center_x - drag_radius_px // 2, "y": center_y}
        end   = {"x": center_x + drag_radius_px,      "y": center_y}

        logger.info(
            "Dragging video slider from (%d, %d) to (%d, %d) over %.2fs.",
            int(start["x"]), int(start["y"]), int(end["x"]), int(end["y"]),
            drag_duration_seconds,
        )
        try:
            self.driver.swipe(start, end, duration=drag_duration_seconds)
            return True
        except Exception as e:
            logger.warning(
                "Slider drag failed (%s). The video will continue playing "
                "and the quiz wait will pick it up naturally.",
                e,
            )
            return False

    def _tap_continue_to_next_lesson_if_present(self, timeout: int = 15) -> None:
        obj = self._wait_for_path(_CONTINUE_TO_NEXT_LESSON_PATH, timeout=timeout)
        if obj is None:
            logger.info(
                "AutoMovePrefab Next button not present within %ds — assuming auto-advance.",
                timeout,
            )
            return
        logger.info("Tapping AutoMovePrefab Next.")
        self._click_or_invoke(obj, label="auto_move_next")

    def _dismiss_trophy_popup_if_present(self, timeout: int = 5) -> bool:
        """
        If TrophyMCQPopup is visible, tap its Start button so the trophy
        quiz can begin. Returns True if the popup was found and Start was
        tapped, False if no popup appeared within timeout.

        Probes multiple candidate root paths (singular/doubled PopUps) and
        both /Start and /Start/Text (TMP) leaves, trying each with both
        EventSystem click and onClick.Invoke. Dumps children of the popup
        root if every attempt fails, so we can see the real button names.
        """
        popup_root = self._find_first_existing_path(_TROPHY_POPUP_ROOTS, timeout=timeout)
        if popup_root is None:
            return False
        logger.info("Trophy popup detected at '%s' — tapping Start.", popup_root)

        for suffix in _TROPHY_START_SUFFIXES:
            path = popup_root + suffix
            obj = self._wait_for_path(path, timeout=2)
            if obj is None:
                logger.info("  Start candidate '%s' not present, trying next.", path)
                continue
            try:
                self._click_or_invoke(obj, label=f"trophy_start[{suffix}]")
                # Confirm the popup actually went away within 2s. If it's
                # still on screen, the click didn't register — try the
                # next candidate.
                if self._wait_for_path(popup_root, timeout=2) is None:
                    # Popup dismissed — wait briefly for the trophy quiz
                    # screen to render so the regular quiz polling
                    # doesn't race against the canvas load.
                    quiz_screen = self._wait_for_path(_TROPHY_QUIZ_SCREEN_PATH, timeout=10)
                    if quiz_screen is None:
                        logger.warning(
                            "Trophy popup dismissed but '%s' not visible within 10s — "
                            "quiz polling may still pick it up shortly.",
                            _TROPHY_QUIZ_SCREEN_PATH,
                        )
                    else:
                        logger.info("Trophy quiz screen (%s) rendered.", _TROPHY_QUIZ_SCREEN_PATH)
                    sleep_seconds(0.5)
                    return True
                logger.info("  Click on '%s' did not dismiss popup; trying next candidate.", path)
            except Exception as e:
                logger.warning("  Click on '%s' raised: %s", path, e)

        # Every candidate failed — dump children of the popup root so we
        # can see the actual Start GameObject name and fix the path.
        self._dump_children(popup_root)
        raise RuntimeError(
            f"Trophy popup detected at '{popup_root}' but could not tap Start "
            f"via any candidate in {_TROPHY_START_SUFFIXES}. See logged "
            "children above to identify the real Start button name."
        )

    def _find_first_existing_path(self, candidate_paths: list[str], timeout: int):
        """Return the first path that resolves to a visible object within timeout, or None."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for path in candidate_paths:
                try:
                    obj = self.driver.find_object(By.PATH, path)
                    if obj and obj.enabled:
                        return path
                except Exception:
                    continue
            time.sleep(0.3)
        return None

    def _dump_children(self, root_path: str) -> None:
        """Log immediate and grand-children of a GameObject for diagnosing missing paths."""
        try:
            kids = self.driver.find_objects(By.PATH, root_path + "/*")
            names = sorted({getattr(c, "name", "?") for c in kids})
            logger.error("Children of '%s' (%d): %s", root_path, len(names), names)
        except Exception as e:
            logger.error("Could not enumerate children of '%s': %s", root_path, e)
        try:
            grand = self.driver.find_objects(By.PATH, root_path + "/*/*")
            names = sorted({getattr(c, "name", "?") for c in grand})
            logger.error("Grand-children of '%s' (%d): %s", root_path, len(names), names)
        except Exception as e:
            logger.error("Could not enumerate grand-children of '%s': %s", root_path, e)

    # ------------------------------------------------------------------
    # Quiz wait
    # ------------------------------------------------------------------

    def _wait_for_quiz(self, total_seconds: int, log_every: int = 30) -> bool:
        elapsed = 0
        logger.info("Waiting up to %ds for quiz to appear.", total_seconds)
        while elapsed < total_seconds:
            chunk = min(log_every, total_seconds - elapsed)
            if self.quiz.is_active(timeout=chunk):
                logger.info("Quiz appeared after ~%ds.", elapsed + chunk)
                return True
            elapsed += chunk
            logger.info("  …still waiting for quiz (%ds / %ds).", elapsed, total_seconds)
        return False

    # ------------------------------------------------------------------
    # Internal helpers — duplicated from StoriesPage.
    # Extract into a shared BasePage when a fourth page object needs them.
    # ------------------------------------------------------------------

    def _wait_for_path(self, path: str, timeout: int):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                obj = self.driver.find_object(By.PATH, path)
                if obj and obj.enabled:
                    return obj
            except Exception:
                pass
            time.sleep(0.3)
        return None

    def _click(self, obj):
        sleep_seconds(0.5)
        try:
            self.driver.click_object(obj)
        except AttributeError:
            obj.tap()

    def _invoke_onclick(self, obj):
        sleep_seconds(0.3)
        obj.call_component_method(
            "UnityEngine.UI.Button",
            "onClick.Invoke",
            "UnityEngine.UI",
            parameters=[],
        )

    def _click_or_invoke(self, obj, label: str = ""):
        try:
            self._click(obj)
            return
        except Exception as click_err:
            logger.warning("EventSystem click failed on '%s': %s", label, click_err)

        try:
            self._invoke_onclick(obj)
            return
        except Exception as invoke_err:
            logger.warning("onClick.Invoke failed on '%s': %s", label, invoke_err)

        raise RuntimeError(
            f"Could not click '{label}' — neither EventSystem click nor "
            "UnityEngine.UI.Button.onClick.Invoke succeeded."
        )
