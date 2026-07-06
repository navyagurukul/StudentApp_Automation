"""
pages/stories_page.py
---------------------
Page object for the Stories flow:

    HomeCorner → Stories
        → ModulesPrefab (topics list)
            → TopicParent/{topic_id}
                → SubModulesPrefab (subtopics list)
                    → SubTopicParent/Subtopic(Clone)[i]   (one per lesson)
                        → video plays
                            → attempt quiz

Paths captured from the running app:
    //ParentCanvas/HomeCorner(Clone)/CourseParent/Stories
    //ParentCanvas/ModulesPrefab(Clone)/MyTrophiesParent/Mask/TopicParent/{topic_id}
    //ParentCanvas/SubModulesPrefab(Clone)/MyTrophiesParent/Mask/SubTopicParent/Subtopic(Clone)[i]
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

_STORIES_BUTTON_PATH   = "//ParentCanvas/HomeCorner(Clone)/CourseParent/Stories"
_TOPIC_PATH_TEMPLATE   = "//ParentCanvas/ModulesPrefab(Clone)/MyTrophiesParent/Mask/TopicParent/{topic_id}"
_SUBTOPIC_PARENT_PATH  = "//ParentCanvas/SubModulesPrefab(Clone)/MyTrophiesParent/Mask/SubTopicParent"
_SUBTOPIC_INDEX_PATH   = _SUBTOPIC_PARENT_PATH + "/Subtopic(Clone)[{index}]"
_SUBTOPIC_GLOB_PATH    = _SUBTOPIC_PARENT_PATH + "/Subtopic(Clone)"

# Continue-to-next-lesson button on the AutoMove screen between lessons.
_CONTINUE_TO_NEXT_LESSON_PATH = "//ParentCanvas/AutoMovePrefab(Clone)/NextButton"

# Video player Slider — dragging to maxValue skips the remaining playback.
_VIDEO_SCREEN_PATH = "//ParentCanvas/Video Screen(Clone)"
_VIDEO_SLIDER_PATH = _VIDEO_SCREEN_PATH + "/UI/bg/Slider"


class StoriesPage:
    def __init__(self, session):
        self.session = session
        self.driver  = session.driver
        self.quiz    = QuizPage(session)

    # ------------------------------------------------------------------
    # Public flow
    # ------------------------------------------------------------------

    def tap_stories(self, timeout: int = 30) -> None:
        obj = self._wait_for_path(_STORIES_BUTTON_PATH, timeout=timeout)
        if obj is None:
            raise RuntimeError(
                f"Stories button not found at '{_STORIES_BUTTON_PATH}' within {timeout}s.\n"
                "Verify HomeCorner is loaded and the Stories button is active."
            )
        logger.info("Clicking Stories.")
        self._click_or_invoke(obj, label="stories")

    def tap_topic(self, topic_id: str, timeout: int = 30) -> None:
        path = _TOPIC_PATH_TEMPLATE.format(topic_id=topic_id)
        obj = self._wait_for_path(path, timeout=timeout)
        if obj is None:
            raise RuntimeError(
                f"Topic '{topic_id}' not found at '{path}' within {timeout}s.\n"
                "Verify ModulesPrefab is loaded and the topic id is correct."
            )
        logger.info("Clicking topic %s.", topic_id)
        self._click_or_invoke(obj, label=f"topic:{topic_id}")

    def skip_video_via_slider(
        self,
        timeout: int = 30,
        drag_radius_px: int = 600,
        drag_duration_seconds: float = 0.8,
    ) -> bool:
        """
        Skip the lesson video by physically dragging the player Slider
        handle from its current position to far past the right edge.
        Sends a real pointer drag (EventSystem), which works even when the
        video player only listens to pointer-up events (not onValueChanged).

        Returns True on success, False if the slider didn't appear or the
        swipe failed — caller can fall back to waiting for the quiz.
        """
        slider = self._wait_for_path(_VIDEO_SLIDER_PATH, timeout=timeout)
        if slider is None:
            logger.warning(
                "Video slider not found at '%s' within %ds — skip will not happen, "
                "falling back to waiting for the quiz.",
                _VIDEO_SLIDER_PATH, timeout,
            )
            return False

        try:
            center_x = slider.x
            center_y = slider.y
        except Exception as e:
            logger.warning("Could not read slider screen position: %s", e)
            return False

        # Drag horizontally across the slider's center. Overshoot the right
        # edge so the handle clamps to maxValue. Unity Slider ignores drag
        # past its bounds, so overshooting is safe.
        # This AltTester build expects start/end as plain {"x":..,"y":..} dicts.
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

        # ------------------------------------------------------------------
        # Previous approach — kept for reference. Use this if the drag-based
        # skip stops working (e.g., AltTester swipe is flaky on a device or
        # the slider's PointerHandler is rewritten):
        #
        # try:
        #     max_val = slider.get_component_property(
        #         "UnityEngine.UI.Slider", "maxValue", "UnityEngine.UI"
        #     )
        # except Exception:
        #     max_val = 1
        # slider.set_component_property(
        #     "UnityEngine.UI.Slider", "value", max_val, "UnityEngine.UI"
        # )
        # ------------------------------------------------------------------

    def play_all_subtopics(
        self,
        quiz_wait_seconds: int = 300,
        between_lessons_seconds: float = 2.0,
        subtopic_load_timeout: int = 30,
        max_lessons: int = 20,
        video_slider_wait_seconds: int = 30,
    ) -> int:
        """
        Open the first subtopic, then chain through every following lesson
        by waiting for each next quiz to appear.

        Flow per lesson:
            video plays → skip via slider drag → quiz appears → play quiz
                       → (optional Continue tap) → next lesson → ...

        Returns the number of quizzes played. Stops when no further quiz
        appears within quiz_wait_seconds (assumed end of topic) or when
        max_lessons is hit.

        To play each video in full instead of skipping (slower, exercises
        real video playback), comment out the two skip_video_via_slider()
        calls below.
        """
        first_path = _SUBTOPIC_INDEX_PATH.format(index=0)
        first = self._wait_for_path(first_path, timeout=subtopic_load_timeout)
        if first is None:
            raise RuntimeError(
                f"First subtopic not found at '{first_path}'.\n"
                "Verify SubModulesPrefab loaded after the topic was clicked."
            )
        logger.info("Opening first subtopic to start the lesson chain.")
        self._click_or_invoke(first, label="subtopic[0]")

        # Skip the video to jump straight to the quiz. Comment this line
        # out to let the video play in full.
        self.skip_video_via_slider(timeout=video_slider_wait_seconds)

        quizzes_played = 0
        for lesson_num in range(1, max_lessons + 1):
            if not self._wait_for_quiz(total_seconds=quiz_wait_seconds):
                if lesson_num == 1:
                    logger.warning(
                        "Quiz did not appear within %ds after opening the first subtopic. "
                        "Dumping diagnostics:",
                        quiz_wait_seconds,
                    )
                    self._dump_quiz_diagnostics()
                    break
                logger.info(
                    "No further quiz appeared within %ds — topic chain finished "
                    "after %d lesson(s).",
                    quiz_wait_seconds, lesson_num - 1,
                )
                break

            logger.info("Lesson %d — playing quiz.", lesson_num)
            quiz_summary = self.quiz.play_quiz()
            logger.info("Lesson %d quiz summary: %s", lesson_num, quiz_summary)
            quizzes_played += 1

            # After the quiz: tap continue if such a button exists, otherwise
            # assume the app auto-advances and just wait for the next quiz.
            self._tap_continue_to_next_lesson_if_present()
            sleep_seconds(between_lessons_seconds)

            # Skip the next lesson's video. Comment this line out to let
            # each video play in full.
            self.skip_video_via_slider(timeout=video_slider_wait_seconds)
        else:
            logger.warning(
                "Hit max_lessons=%d ceiling — bump it if the topic has more.",
                max_lessons,
            )

        if quizzes_played == 0:
            raise RuntimeError(
                "No quizzes were played. Check the diagnostics dump above "
                "to see what was on screen when the first quiz was expected."
            )
        logger.info("play_all_subtopics done — %d lesson(s) completed.", quizzes_played)
        return quizzes_played

    def _tap_continue_to_next_lesson_if_present(self, timeout: int = 15) -> None:
        """
        After a quiz, the AutoMovePrefab usually appears with a Next button
        that advances to the next lesson. Tap it if present; otherwise
        assume the app auto-advances and return.
        """
        obj = self._wait_for_path(_CONTINUE_TO_NEXT_LESSON_PATH, timeout=timeout)
        if obj is None:
            logger.info(
                "AutoMovePrefab Next button not present within %ds — assuming auto-advance.",
                timeout,
            )
            return
        logger.info("Tapping AutoMovePrefab Next.")
        self._click_or_invoke(obj, label="auto_move_next")

    # ------------------------------------------------------------------
    # Quiz wait
    # ------------------------------------------------------------------

    def _wait_for_quiz(self, total_seconds: int, log_every: int = 30) -> bool:
        """
        Poll for the quiz canvas to appear, logging progress every log_every
        seconds. Returns True as soon as it's found, False after total_seconds.
        """
        elapsed = 0
        logger.info("Waiting up to %ds for video to finish and quiz to appear.", total_seconds)
        while elapsed < total_seconds:
            chunk = min(log_every, total_seconds - elapsed)
            if self.quiz.is_active(timeout=chunk):
                logger.info("Quiz appeared after ~%ds.", elapsed + chunk)
                return True
            elapsed += chunk
            logger.info("  …still waiting for quiz (%ds / %ds).", elapsed, total_seconds)
        return False

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def _dump_quiz_diagnostics(self) -> None:
        """When the quiz can't be found, log what IS on screen so we can fix the paths."""
        try:
            scene = self.driver.get_current_scene()
            logger.warning("  current scene: %s", scene)
        except Exception as e:
            logger.warning("  could not get current scene: %s", e)

        probes = [
            "//MCQCanvasNew",
            "//TextBasedMCQ_UIC(Clone)",
            "//HintUIC(Clone)",
            "//OptionParents",
        ]
        for p in probes:
            try:
                obj = self.driver.find_object(By.PATH, p)
                logger.warning("  probe %s -> %s", p, "FOUND" if obj else "missing")
            except Exception as e:
                logger.warning("  probe %s -> error: %s", p, e)

        try:
            roots = self.driver.find_objects(By.PATH, "//*")
            top_names = sorted({getattr(o, "name", "?") for o in roots[:60]})
            logger.warning("  top GameObjects (sample of %d): %s", len(top_names), top_names)
        except Exception as e:
            logger.warning("  could not enumerate root objects: %s", e)

    # ------------------------------------------------------------------
    # Internal helpers — duplicated from HomePage. Extract into a shared
    # BasePage when a third page object needs them.
    # ------------------------------------------------------------------

    def _count_subtopics(self, timeout: int) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                objs = self.driver.find_objects(By.PATH, _SUBTOPIC_GLOB_PATH)
                if objs:
                    return len(objs)
            except Exception:
                pass
            time.sleep(0.5)
        return 0

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

        self._dump_components(obj, label)
        raise RuntimeError(
            f"Could not click '{label}' — neither EventSystem click nor "
            "UnityEngine.UI.Button.onClick.Invoke succeeded. See logged "
            "component list above to find the real click target."
        )

    def _dump_components(self, obj, label: str = ""):
        try:
            components = obj.get_all_components()
            logger.error("Components on '%s':", label)
            for c in components:
                logger.error(
                    "  - %s  (assembly=%s)",
                    getattr(c, "component_name", c),
                    getattr(c, "assembly_name", "?"),
                )
        except Exception as dump_err:
            logger.error("Failed to dump components for '%s': %s", label, dump_err)
