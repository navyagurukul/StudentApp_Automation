"""
pages/quiz_page.py
------------------
Page object for the Text-based MCQ quiz that appears after each lesson video.

Paths captured from AltTester Inspector:

    Quiz canvas
        /MCQCanvasNew/TextBasedMCQ_UIC(Clone)

    Options (one child per option, named by GUID)
        /MCQCanvasNew/TextBasedMCQ_UIC(Clone)/OptionParents/{guid}
        /MCQCanvasNew/TextBasedMCQ_UIC(Clone)/OptionParents/{guid}/ResponseTick
            ResponseTick becomes active when that option is the correct answer
            (after the option is tapped + OK submitted).

    Wrong-answer feedback
        /MCQCanvasNew/HintUIC(Clone)
        /MCQCanvasNew/HintUIC(Clone)/RetryButton

The quiz allows up to 2 attempts per question.
"""

from __future__ import annotations

import logging
import time

from alttester import By
from framework.waits import sleep_seconds

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

class _QuizVariant:
    """Per-prefab path bundle. Different prefabs use slightly different naming."""

    def __init__(
        self,
        label: str,
        root: str,
        options_parent_name: str,
        ok_button_name: str = "OKBtn",
        next_button_name: str = "NextBtn",
    ):
        self.label           = label
        self.root            = root
        self.options_parent  = root + "/" + options_parent_name
        self.options_glob    = self.options_parent + "/*"
        self.option_template = self.options_parent + "/{option_id}"
        self.tick_template   = self.options_parent + "/{option_id}/ResponseTick"
        self.ok_button       = root + "/" + ok_button_name
        self.next_button     = root + "/" + next_button_name


# Order matters: variants are probed in order. Add new variants here.
# Note: the three known prefabs use three DIFFERENT spellings of the
# options-parent GameObject AND different casings for OK button — keep exact.
_QUIZ_VARIANTS = [
    _QuizVariant(
        label="text",
        root="//MCQCanvasNew/TextBasedMCQ_UIC(Clone)",
        options_parent_name="OptionParents",
        ok_button_name="OKBtn",
    ),
    _QuizVariant(
        label="image_answer",
        root="//MCQCanvasNew/ImageAnswer_UIC(Clone)",
        options_parent_name="OptionParent",
        ok_button_name="OKBtn",
    ),
    _QuizVariant(
        label="image_question",
        root="//MCQCanvasNew/ImageQuestionUIC(Clone)",
        options_parent_name="OptionsParents",
        ok_button_name="OkButton",  # different casing from the other two
    ),
]

# Quiz-canvas-level paths shared by all variants.
_QUIZ_CANVAS_PATH = "//MCQCanvasNew"
_HINT_ROOT_PATH   = "//MCQCanvasNew/HintUIC(Clone)"
_HINT_RETRY_PATH  = _HINT_ROOT_PATH + "/RetryButton"

# Speech question — doesn't fit the MCQ model. Smoke-test approach is to Skip.
# Captured paths:
#   //MCQCanvasNew/SpeechQuestion_UIC(Clone)/answer/Recorded Text   (recognized text)
#   //MCQCanvasNew/SpeechQuestion_UIC(Clone)/Records                (start-record button)
#   //MCQCanvasNew/SpeechQuestion_UIC(Clone)/Skip/Text (TMP)        (skip button — click the Text child)
#   //MCQCanvasNew/SpeechQuestion_UIC(Clone)/QuestionParent/SoundButton  (play question)
# AltTester needs the Text (TMP) child; clicks on the parent Skip GameObject
# do not register.
_SPEECH_QUESTION_ROOT = "//MCQCanvasNew/SpeechQuestion_UIC(Clone)"
_SPEECH_SKIP_PATH     = _SPEECH_QUESTION_ROOT + "/Skip/Text (TMP)"

# Speech, guided-speech, and text-to-speech questions need real voice input and
# CANNOT be automated — per QA rule we click Skip to move to the next question.
# Every such prefab exposes a "Skip/Text (TMP)" child directly under the quiz
# canvas, so match ANY of them generically (no need for each exact prefab name).
_GENERIC_SKIP_GLOB = "//MCQCanvasNew/*/Skip/Text (TMP)"

# Jumble-up sentence builder — tap every JumbleWordBtn in order, then OK.
# Note the casing: this prefab uses "OkButton", not "OKBtn" like the MCQs.
#
# The interactive element is /AnswerBlock/Demo two levels under the button —
# clicking JumbleWordBtn(Clone) directly does not register, so the glob below
# targets the Demo children. AnswerParent (commented) is where selected words
# render after each tap; it's useful for verification, not for clicking.
_JUMBLE_QUESTION_ROOT = "//MCQCanvasNew/JumbleUp_UIC(Clone)"
_JUMBLE_WORD_GLOB     = _JUMBLE_QUESTION_ROOT + "/AnswerPanel/QuestionParent/JumbleWordBtn(Clone)/AnswerBlock/Demo"
_JUMBLE_OK_PATH       = _JUMBLE_QUESTION_ROOT + "/OkButton/Text (TMP)"
_JUMBLE_NEXT_PATH     = _JUMBLE_QUESTION_ROOT + "/NextButton/Text (TMP)"
# _JUMBLE_ANSWER_PARENT = _JUMBLE_QUESTION_ROOT + "/AnswerPanel/AnswerParent"

MAX_ATTEMPTS_PER_QUESTION = 2


class QuizPage:
    def __init__(self, session):
        self.session = session
        self.driver  = session.driver

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_active(self, timeout: int = 5) -> bool:
        """Return True if any quiz variant (text or image) is currently visible."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._active_variant() is not None:
                return True
            time.sleep(0.5)
        return False

    def _active_variant(self):
        """Return the QuizVariant currently on screen, or None."""
        for v in _QUIZ_VARIANTS:
            try:
                obj = self.driver.find_object(By.PATH, v.root)
                if obj is not None:
                    return v
            except Exception:
                continue
        return None

    def play_quiz(
        self,
        max_questions: int = 20,
        question_load_timeout: int = 30,
        is_trophy: bool = False,
    ) -> dict:
        """
        Loop questions until the quiz UI disappears or max_questions is hit.
        Returns a summary dict: {"answered": N, "correct": N, "wrong": N}.

        Pass is_trophy=True for trophy quizzes — those don't show
        right/wrong feedback and don't offer retry, so questions auto-
        advance on OK and the per-question wait is much shorter.
        """
        summary = {"answered": 0, "correct": 0, "wrong": 0, "skipped": 0}
        for q in range(max_questions):
            kind, payload = self._wait_for_any_question(timeout=question_load_timeout)
            if kind is None:
                logger.info("Quiz UI gone after %d questions — quiz finished.", q)
                break

            if kind == "skip":
                # speech / guided-speech / text-to-speech — can't be automated
                logger.info("Question %d is a speech/guided-speech/text-to-speech "
                            "question (not automatable) — clicking Skip.", q + 1)
                self._click_or_invoke(payload, label="question_skip")
                summary["answered"] += 1
                summary["skipped"] += 1
            elif kind == "jumble":
                outcome = self._handle_jumble_question()
                summary["answered"] += 1
                summary["skipped"] += 1
                logger.info("Question %d (jumble) outcome: %s.", q + 1, outcome)
            else:
                outcome = self.answer_current_question(payload, is_trophy=is_trophy)
                summary["answered"] += 1
                summary[outcome] = summary.get(outcome, 0) + 1
                logger.info(
                    "Question %d (%s%s) outcome: %s.",
                    q + 1, payload.label, " trophy" if is_trophy else "", outcome,
                )

            # Brief pause between questions for the next one to load.
            sleep_seconds(1.5)
        else:
            logger.warning(
                "Hit max_questions=%d ceiling — quiz may have more questions. "
                "Raise the limit if needed.",
                max_questions,
            )

        return summary

    def answer_current_question(self, variant=None, is_trophy: bool = False) -> str:
        """
        Try option[0], then on wrong-answer retry try option[1].
        Tap Next at the end to advance to the next question regardless
        of right/wrong on the final attempt.
        Returns "correct" or "wrong" for regular MCQs; "answered" for trophy.

        Trophy mode (is_trophy=True): no retry button is shown and no
        right/wrong feedback is rendered — the question auto-advances on
        OK. Single attempt, no feedback wait, no Next tap.

        If variant is None, the active variant is auto-detected. Pass it
        explicitly when called from a loop that already resolved it.
        """
        if variant is None:
            variant = self._active_variant()
            if variant is None:
                raise RuntimeError("No quiz variant is currently active.")

        option_ids = self._list_option_ids(variant)
        if not option_ids:
            raise RuntimeError(
                f"No option GameObjects found under '{variant.options_parent}'."
            )

        if is_trophy:
            chosen = option_ids[0]
            logger.info("Trophy attempt (%s) — tapping option %s.", variant.label, chosen)
            self._tap_option(variant, chosen)
            self._tap_ok(variant)
            return "answered"

        final_outcome = "wrong"
        for attempt in range(MAX_ATTEMPTS_PER_QUESTION):
            chosen = option_ids[attempt] if attempt < len(option_ids) else option_ids[-1]
            logger.info(
                "Attempt %d/%d (%s) — tapping option %s.",
                attempt + 1,
                MAX_ATTEMPTS_PER_QUESTION,
                variant.label,
                chosen,
            )
            self._tap_option(variant, chosen)
            self._tap_ok(variant)

            outcome = self._wait_for_feedback(variant, timeout=10)
            if outcome == "correct":
                final_outcome = "correct"
                break
            if outcome == "wrong":
                if attempt < MAX_ATTEMPTS_PER_QUESTION - 1:
                    self._tap_retry()
                    continue
                # Out of attempts — fall through to Next
                break
            # outcome == "unknown" — neither tick nor hint appeared in time.
            logger.warning("No quiz feedback within 10s — assuming question advanced.")
            break

        self._tap_next(variant)
        return final_outcome

    # ------------------------------------------------------------------
    # Internal — option enumeration and tapping
    # ------------------------------------------------------------------

    def _list_option_ids(self, variant) -> list[str]:
        """Return child GameObject names (GUIDs) under the variant's OptionParent(s)."""
        try:
            children = self.driver.find_objects(By.PATH, variant.options_glob)
        except Exception as e:
            logger.error("find_objects on '%s' failed: %s", variant.options_glob, e)
            return []
        ids: list[str] = []
        for c in children:
            name = getattr(c, "name", None)
            if isinstance(name, str):
                ids.append(name)
        logger.info("Found %d %s option(s): %s", len(ids), variant.label, ids)
        return ids

    def _wait_for_variant_with_options(self, timeout: int):
        """Wait until any variant is on-screen AND has at least one option child."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            variant = self._active_variant()
            if variant is not None and self._list_option_ids(variant):
                return variant
            time.sleep(0.5)
        return None

    def _wait_for_any_question(self, timeout: int):
        """
        Poll for any kind of question to appear on the quiz canvas.
        Returns (kind, payload):
          ("skip",   skip_button) if a speech / guided-speech / text-to-speech
                                  question is active (not automatable — Skip it)
          ("jumble", None)        if a JumbleUp prefab is active
          ("mcq",    variant)     if a MCQ variant is active with options
          (None, None)            on timeout
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            skip_btn = self._find_skip_button()
            if skip_btn is not None:
                return ("skip", skip_btn)
            if self._jumble_question_visible():
                return ("jumble", None)
            variant = self._active_variant()
            if variant is not None and self._list_option_ids(variant):
                return ("mcq", variant)
            time.sleep(0.5)
        return (None, None)

    def _find_skip_button(self):
        """Return the Skip button of any unautomatable question (speech,
        guided-speech, text-to-speech), or None. All such prefabs expose a
        'Skip/Text (TMP)' child directly under the quiz canvas, so one glob
        catches every variant."""
        try:
            objs = self.driver.find_objects(By.PATH, _GENERIC_SKIP_GLOB)
        except Exception:
            return None
        for o in objs:
            try:
                if o.enabled:
                    return o
            except Exception:
                continue
        return None

    def _speech_question_visible(self) -> bool:
        try:
            obj = self.driver.find_object(By.PATH, _SPEECH_QUESTION_ROOT)
            return obj is not None
        except Exception:
            return False

    def _skip_speech_question(self) -> str:
        """Tap the Skip button on a SpeechQuestion. Returns 'skipped'."""
        obj = self._wait_for_path(_SPEECH_SKIP_PATH, timeout=10)
        if obj is None:
            raise RuntimeError(
                f"Speech Skip button not found at '{_SPEECH_SKIP_PATH}'."
            )
        logger.info("Skipping speech question via Skip button.")
        self._click_or_invoke(obj, label="speech_skip")
        return "skipped"

    def _jumble_question_visible(self) -> bool:
        try:
            obj = self.driver.find_object(By.PATH, _JUMBLE_QUESTION_ROOT)
            return obj is not None
        except Exception:
            return False

    def _handle_jumble_question(self) -> str:
        """
        Tap every JumbleWordBtn(Clone)/AnswerBlock/Demo in hierarchy order,
        then OK, retry once if marked wrong, then Next.
        Hierarchy order is unlikely to be the correct sentence order, so this
        is a smoke pass — proves the flow works without verifying correctness.
        """
        for attempt in range(MAX_ATTEMPTS_PER_QUESTION):
            self._tap_all_jumble_blocks()

            ok = self._wait_for_path(_JUMBLE_OK_PATH, timeout=10)
            if ok is None:
                raise RuntimeError(f"Jumble OK button not found at '{_JUMBLE_OK_PATH}'.")
            logger.info("Tapping jumble OK (attempt %d/%d).", attempt + 1, MAX_ATTEMPTS_PER_QUESTION)
            self._click_or_invoke(ok, label="jumble_ok")

            sleep_seconds(1.0)
            if self._hint_visible() and attempt < MAX_ATTEMPTS_PER_QUESTION - 1:
                logger.info("Jumble marked wrong — tapping retry and retrying word order.")
                self._tap_retry()
                sleep_seconds(0.5)
                continue
            break

        nxt = self._wait_for_path(_JUMBLE_NEXT_PATH, timeout=10)
        if nxt is not None:
            logger.info("Tapping jumble Next.")
            self._click_or_invoke(nxt, label="jumble_next")
        else:
            logger.info("Jumble Next button not found — assuming auto-advance.")
        return "skipped"

    def _tap_all_jumble_blocks(self) -> None:
        try:
            blocks = self.driver.find_objects(By.PATH, _JUMBLE_WORD_GLOB)
        except Exception as e:
            logger.error("find_objects on '%s' failed: %s", _JUMBLE_WORD_GLOB, e)
            blocks = []
        if not blocks:
            raise RuntimeError(
                f"No jumble word blocks found at '{_JUMBLE_WORD_GLOB}'."
            )

        logger.info("Tapping %d jumble word blocks in hierarchy order.", len(blocks))
        for i, block in enumerate(blocks):
            try:
                self._click_or_invoke(block, label=f"jumble_word[{i}]")
                sleep_seconds(0.3)
            except Exception as e:
                logger.warning("Failed to tap jumble block %d: %s", i, e)

    def _tap_option(self, variant, option_id: str) -> None:
        path = variant.option_template.format(option_id=option_id)
        obj = self._wait_for_path(path, timeout=10)
        if obj is None:
            raise RuntimeError(f"Option '{option_id}' not found at '{path}'.")
        self._click_or_invoke(obj, label=f"option:{option_id}")

    # Each prefab spells its OK / Next button slightly differently.
    # Try the variant's configured name first, then these fallbacks so the
    # test doesn't crash on the first casing mismatch we discover.
    _OK_CANDIDATES   = ["OKBtn", "OkButton", "OkBtn", "OKButton"]
    _NEXT_CANDIDATES = ["NextBtn", "NextButton", "NxtBtn"]

    def _tap_ok(self, variant) -> None:
        obj, path = self._find_first(variant, variant.ok_button, self._OK_CANDIDATES, timeout=10)
        if obj is None:
            self._dump_prefab_children(variant.root)
            raise RuntimeError(
                f"OK button not found under '{variant.root}'. "
                f"Tried: {variant.ok_button} + fallbacks {self._OK_CANDIDATES}. "
                "See children dump above and update the variant's ok_button_name."
            )
        logger.info("Tapping OK at %s.", path)
        self._click_or_invoke(obj, label="quiz_ok")

    def _tap_next(self, variant) -> None:
        obj, path = self._find_first(variant, variant.next_button, self._NEXT_CANDIDATES, timeout=15)
        if obj is None:
            self._dump_prefab_children(variant.root)
            raise RuntimeError(
                f"Next button not found under '{variant.root}'. "
                f"Tried: {variant.next_button} + fallbacks {self._NEXT_CANDIDATES}. "
                "If the quiz is over, this is expected — bump play_quiz()'s "
                "early-exit check to detect the end-of-quiz screen instead."
            )
        logger.info("Tapping Next at %s.", path)
        self._click_or_invoke(obj, label="quiz_next")

    def _find_first(self, variant, primary_path: str, fallback_names: list, timeout: int):
        """Try primary_path first, then each fallback name under variant.root. Returns (obj, path) or (None, None)."""
        paths = [primary_path]
        for name in fallback_names:
            alt = variant.root + "/" + name
            if alt not in paths:
                paths.append(alt)
        # First pass with the configured timeout on the primary; short retries on fallbacks
        primary = self._wait_for_path(primary_path, timeout=timeout)
        if primary is not None:
            return primary, primary_path
        for p in paths[1:]:
            obj = self._wait_for_path(p, timeout=2)
            if obj is not None:
                return obj, p
        return None, None

    def _dump_prefab_children(self, root_path: str) -> None:
        """List immediate children of a prefab so we can see actual button names."""
        try:
            children = self.driver.find_objects(By.PATH, root_path + "/*")
        except Exception as e:
            logger.error("Could not enumerate children of '%s': %s", root_path, e)
            return
        names = sorted({getattr(c, "name", "?") for c in children})
        logger.error("Children of '%s' (%d): %s", root_path, len(names), names)

    def _tap_retry(self) -> None:
        obj = self._wait_for_path(_HINT_RETRY_PATH, timeout=10)
        if obj is None:
            raise RuntimeError(
                f"Retry button not found at '{_HINT_RETRY_PATH}' after wrong answer."
            )
        logger.info("Tapping Retry on HintUIC.")
        self._click_or_invoke(obj, label="quiz_retry")

    # ------------------------------------------------------------------
    # Internal — feedback detection
    # ------------------------------------------------------------------

    def _wait_for_feedback(self, variant, timeout: int) -> str:
        """
        Poll for one of:
          - any ResponseTick under the variant's options parent goes active → "correct"
          - HintUIC(Clone) becomes visible → "wrong"
        Returns "correct", "wrong", or "unknown" on timeout.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._any_response_tick_visible(variant):
                return "correct"
            if self._hint_visible():
                return "wrong"
            time.sleep(0.25)
        return "unknown"

    def _any_response_tick_visible(self, variant) -> bool:
        glob = variant.options_parent + "/*/ResponseTick"
        try:
            ticks = self.driver.find_objects(By.PATH, glob)
        except Exception:
            return False
        for t in ticks:
            try:
                if t.enabled:
                    return True
            except Exception:
                continue
        return False

    def _hint_visible(self) -> bool:
        try:
            hint = self.driver.find_object(By.PATH, _HINT_ROOT_PATH)
        except Exception:
            return False
        if hint is None:
            return False
        try:
            return bool(hint.enabled)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal — generic click + wait helpers (mirrors HomePage / StoriesPage).
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
        sleep_seconds(0.3)
        try:
            self.driver.click_object(obj)
        except AttributeError:
            obj.tap()

    def _invoke_onclick(self, obj):
        sleep_seconds(0.2)
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
