"""
framework/driver_session.py
---------------------------
Wraps AltDriver with helper methods that match the session API used by
all page objects:

    session.driver                        raw AltDriver
    session.find_by_name(name, timeout)   waits for object by name
    session.tap_by_name(name)             finds + taps by name
    session.set_input_text_by_name(name, text)  sets TMP_InputField text

Environment variables:
    ALT_HOST        default 127.0.0.1
    ALT_PORT        default 13000
    ALT_APP_NAME    default EnglishGurukulStudentApp
"""

from __future__ import annotations

import logging
import os
import time

from alttester import AltDriver, By
from alttester.exceptions import NotFoundException, WaitTimeOutException

logger = logging.getLogger(__name__)

_DEFAULT_HOST     = "127.0.0.1"
_DEFAULT_PORT     = 13000
_DEFAULT_APP_NAME = "EnglishGurukulStudentApp"


class AltSession:
    """Thin wrapper around AltDriver — used by all page objects."""

    def __init__(self, driver: AltDriver):
        self.driver = driver

    # ------------------------------------------------------------------
    # Finders
    # ------------------------------------------------------------------

    def find_by_name(self, name: str, timeout: float = 30) -> object:
        """Wait for an enabled object with *name* and return it."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                obj = self.driver.find_object(By.NAME, name)
                if obj and obj.enabled:
                    return obj
            except Exception:
                pass
            time.sleep(0.3)
        raise TimeoutError(
            f"Object '{name}' not found or not enabled within {timeout}s."
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def tap_by_name(self, name: str, timeout: float = 15) -> None:
        """Find an object by name and tap it via Unity's EventSystem."""
        obj = self.find_by_name(name, timeout=timeout)
        _click(self.driver, obj)

    def set_input_text_by_name(self, name: str, text: str, timeout: float = 15) -> None:
        """Find a TMP_InputField by name and set its text."""
        obj = self.find_by_name(name, timeout=timeout)
        obj.set_text(text)

    # ------------------------------------------------------------------
    # Scene helpers
    # ------------------------------------------------------------------

    def wait_for_scene(self, scene_name: str, timeout: float = 90) -> None:
        """Block until the active scene matches *scene_name*."""
        logger.info("Waiting for scene '%s' …", scene_name)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.driver.get_current_scene() == scene_name:
                    logger.info("Scene '%s' is active ✓", scene_name)
                    return
            except Exception:
                pass
            time.sleep(0.5)
        raise TimeoutError(
            f"Scene '{scene_name}' did not become active within {timeout}s."
        )

    def get_current_scene(self) -> str | None:
        try:
            return self.driver.get_current_scene()
        except Exception:
            return None


def _click(driver: AltDriver, obj) -> None:
    """Click via EventSystem; fall back to coordinate tap on old SDKs."""
    from framework.waits import sleep_seconds
    sleep_seconds(0.5)
    try:
        driver.click_object(obj)
    except AttributeError:
        obj.tap()


def get_session() -> AltSession:
    """Create and return a connected AltSession."""
    host     = os.environ.get("ALT_HOST", _DEFAULT_HOST)
    port     = int(os.environ.get("ALT_PORT", _DEFAULT_PORT))
    app_name = os.environ.get("ALT_APP_NAME", _DEFAULT_APP_NAME)

    logger.info("Connecting AltDriver → %s:%d  app='%s'", host, port, app_name)
    driver = AltDriver(host=host, port=port, app_name=app_name)
    logger.info("AltDriver connected ✓")
    return AltSession(driver)
