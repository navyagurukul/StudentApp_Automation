"""
pages/home_page.py
------------------
Page object for the Begin scene and ParentsScreen.

All paths from SceneLoadTests.cs:

    Begin scene
    C#: GameObject.Find("Timeline/EnterScreen/enter button")
        enterButton.onClick.Invoke()

    ParentsScreen logout
    C#: GameObject.Find("ParentCanvas/Home CornerScren")          ← typo: "Scren"
        HomeCornerScreen.transform.Find("Header/Parent's Corner")
        parentCornerButton.onClick.Invoke()
        GameObject.Find("Canvas PC/parent's Corner")
        ParentCornerScreen.transform.Find("Header/LogOut")
        logoutButtonGO.onClick.Invoke()

There is NO Skip button on the Begin scene in this project.
"""

from __future__ import annotations

import logging
import time

from alttester import By
from framework.waits import sleep_seconds

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exact paths from SceneLoadTests.cs
# ---------------------------------------------------------------------------

# C#: GameObject.Find("Timeline/EnterScreen/enter button")
_ENTER_BUTTON_PATH = "//EGTimeline/EnterScreen/enter button"
_SKIP_BUTTON_PATH = "//Canvas/SkipAnim/Text (TMP)"
_PROFILE_DIALOGUE_BUTTON_PATH = "//ParentCanvas/ProfileDialogue(Clone)/BG/Button"

# C#: GameObject.Find("ParentCanvas/Home CornerScren")
#     .transform.Find("Header/Parent's Corner")
_PARENT_CORNER_BTN_PATH = "//ParentCanvas/HomeCorner(Clone)/Header/Parent's Corner/pa img"

# C#: GameObject.Find("Canvas PC/parent's Corner")
#     .transform.Find("Header/LogOut")
_LOGOUT_PATH = "//Canvas PC/ParentCornerUIC(Clone)/Header/LogOut"


class HomePage:
    def __init__(self, session):
        self.session = session
        self.driver  = session.driver

    # ------------------------------------------------------------------
    # Begin scene
    # ------------------------------------------------------------------

    def tap_enter_if_visible(self, timeout=60):
        """
        C#: while ((enterButtonGO == null || !activeInHierarchy) && waitTime < 60f)
                enterButtonGO = GameObject.Find("Timeline/EnterScreen/enter button")
            enterButton.onClick.Invoke()
        """
        obj = self._wait_for_path(_ENTER_BUTTON_PATH, timeout=timeout)
        if obj is None:
            raise RuntimeError(
                f"Enter button not found at '{_ENTER_BUTTON_PATH}' within {timeout}s.\n"
                "Verify the Begin scene is loaded and "
                "Timeline/EnterScreen/enter button is active in the Unity Inspector."
            )
        logger.info("Clicking enter button via EventSystem.")
        self._click_or_invoke(obj, label="enter")

    def tap_skip_if_visible(self, timeout=60):
        """
        C#: while ((skipButtonGO == null || !activeInHierarchy) && waitTime < 60f)
                skipButtonGO = GameObject.Find("//Canvas/SkipAnim/Text (TMP)")
            skipButton.onClick.Invoke()
        """
        obj = self._wait_for_path(_SKIP_BUTTON_PATH, timeout=timeout)
        if obj is None:
            raise RuntimeError(
                f"Skip button not found at '{_SKIP_BUTTON_PATH}' within {timeout}s.\n"
                "Verify the scene is loaded and "
                "Canvas/SkipAnim/Text (TMP) is active in the Unity Inspector."
            )
        logger.info("Clicking skip button via EventSystem.")
        self._click_or_invoke(obj, label="skip")

    def tap_continue_on_profile_dialogue(self, timeout=30):
        """Wait for the ProfileDialogue popup, then click its Continue button."""
        obj = self._wait_for_path(_PROFILE_DIALOGUE_BUTTON_PATH, timeout=timeout)
        if obj is None:
            raise RuntimeError(
                f"Continue button not found at '{_PROFILE_DIALOGUE_BUTTON_PATH}' within {timeout}s.\n"
                "Verify ProfileDialogue(Clone) was instantiated after the enter tap."
            )
        logger.info("Clicking Continue on ProfileDialogue.")
        self._click_or_invoke(obj, label="profile_dialogue_continue")
    
    # ------------------------------------------------------------------
    # ParentsScreen — Parent's Corner → Logout
    # ------------------------------------------------------------------

    def open_parent_corner_and_logout(self):
        """
        Flow:
          1. Dismiss the ProfileDialogue popup by clicking its Continue button.
          2. Open Parent's Corner from the home screen.
          3. Click Logout inside Parent's Corner.

        C#:
            HomeCornerScreen = GameObject.Find("ParentCanvas/Home CornerScren")
            parentCornerButton = HomeCornerScreen.transform.Find("Header/Parent's Corner")
            parentCornerButton.onClick.Invoke()
            ParentCornerScreen = GameObject.Find("Canvas PC/parent's Corner")
            logoutButtonGO = ParentCornerScreen.transform.Find("Header/LogOut")
            logoutButtonGO.onClick.Invoke()
        """
        self.tap_continue_on_profile_dialogue(timeout=30)
        sleep_seconds(1.0)   # wait for dialogue to close

        parent_btn = self._wait_for_path(_PARENT_CORNER_BTN_PATH, timeout=30)
        if parent_btn is None:
            raise RuntimeError(
                f"Parent's Corner button not found at '{_PARENT_CORNER_BTN_PATH}'.\n"
                "Make sure ParentsScreen is fully loaded."
            )
        logger.info("Clicking Parent's Corner.")
        self._click_or_invoke(parent_btn, label="parent_corner")

        sleep_seconds(1.0)   # wait for panel animation

        logout_btn = self._wait_for_path(_LOGOUT_PATH, timeout=30)
        if logout_btn is None:
            raise RuntimeError(
                f"Logout button not found at '{_LOGOUT_PATH}'."
            )
        logger.info("Clicking Logout.")
        self._click_or_invoke(logout_btn, label="logout")

        # Verify logout actually happened — without this, a no-op click
        # silently false-passes. Scene should return to login.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            scene = self.driver.get_current_scene()
            if scene and scene.lower() in ("login", "begin"):
                logger.info("Logout confirmed — scene is now '%s'.", scene)
                return
            time.sleep(0.5)
        raise RuntimeError(
            "Logout click reported success but scene did not change to Login/Begin "
            "within 20s. The button likely has no onClick listener or the logout "
            "flow is broken — check the app, not the test."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _click(self, obj):
        """
        click_object fires onClick through Unity's EventSystem — works even
        when entrance animations have a canvas layer in front of the button.
        Falls back to tap() on older AltTester SDK builds.
        """
        sleep_seconds(0.5)
        try:
            self.driver.click_object(obj)
        except AttributeError:
            obj.tap()

    def _invoke_onclick(self, obj):
        """
        Mirrors C# `button.onClick.Invoke()` — calls the UnityEvent directly,
        bypassing raycast/EventSystem. Use this when a button is visually
        unclickable (covered by an overlay, RaycastTarget off, CanvasGroup
        non-interactable) but its onClick handler should still fire.
        Without this, _click silently no-ops and the test false-passes.
        """
        sleep_seconds(0.3)
        obj.call_component_method(
            "UnityEngine.UI.Button",
            "onClick.Invoke",
            "UnityEngine.UI",
            parameters=[],
        )

    def _click_or_invoke(self, obj, label: str = ""):
        """
        Try EventSystem click first (works for any clickable, including
        custom MonoBehaviours and Image-based buttons). If that raises,
        fall back to invoking UnityEngine.UI.Button.onClick directly.
        If both fail, dump every component on the GameObject so we can
        see what the click actually needs to target.
        """
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
        """Log every component on the GameObject so we can find the real click target."""
        try:
            components = obj.get_all_components()
            logger.error("Components on '%s' (%s):", label, _ENTER_BUTTON_PATH)
            for c in components:
                logger.error(
                    "  - %s  (assembly=%s)",
                    getattr(c, "component_name", c),
                    getattr(c, "assembly_name", "?"),
                )
        except Exception as dump_err:
            logger.error("Failed to dump components for '%s': %s", label, dump_err)

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
