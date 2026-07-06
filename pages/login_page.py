"""
pages/login_page.py
-------------------
Page object for the full login flow.

Every path is taken verbatim from SceneLoadTests.cs.
Comments show the exact C# line being translated.
"""

from __future__ import annotations

import logging
import time

from alttester import By
from framework.waits import sleep_seconds

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exact names / paths from SceneLoadTests.cs
# ---------------------------------------------------------------------------

# C#: t.name == "Type mobile"
_MOBILE_INPUT_NAME   = "Type mobile"

# C#: t.name == "Confrim"   ← deliberate typo in the Unity project
_CONFIRM_BUTTON_NAME = "Confrim"

# C#: GameObject.Find("Canvas/LoginUIC(Clone)/Select Profile")
_SELECT_PROFILE_NAME  = "Select Profile"

# C#: GameObject.Find("Canvas/LoginUIC(Clone)/LicenceCode")
_LICENSE_NAME         = "LicenceCode"

# C#: GameObject.Find("Canvas/LanguageDialogue(Clone)")
_LANGUAGE_DIALOG_NAME = "LanguageDialogue(Clone)"

# C#: selectProfileScreen.transform.Find("bg/screen/GurdianParent")
_PROFILE_PARENT_PATH  = "//Canvas/LoginUIC(Clone)/Select Profile/bg/screen/GurdianParent"

# C#: selectProfileScreen.transform.Find("bg/screen/next")
_NEXT_BTN_PATH        = "//Canvas/LoginUIC(Clone)/Select Profile/bg/screen/next"

# C#: GameObject.Find("Canvas/LoginUIC(Clone)/Select Your Avatar")
_AVATAR_SCREEN_PATH   = "//Canvas/LoginUIC(Clone)/Select Your Avatar"

# C#: selectAvatarScreen.transform.Find("bg/screen/save")
_AVATAR_SAVE_PATH     = "//Canvas/LoginUIC(Clone)/Select Your Avatar/bg/screen/save"

# Language dialog paths
_LANG_DIALOG_PATH     = "//Canvas/LanguageDialogue(Clone)"
_LANG_LOADING_PATH    = "//Canvas/LanguageDialogue(Clone)/LoadingObject"
_LANG_DROPDOWN_PATH   = "//Canvas/LanguageDialogue(Clone)/Dropdown"
_LANG_SAVE_PATH       = "//Canvas/LanguageDialogue(Clone)/SaveButtonHolder/Button (1)"

# License / new-user paths
_LICENSE_SCREEN_PATH  = "//Canvas/LoginUIC(Clone)/LicenceCode/bg/screen"
_LICENSE_INPUT_PATH   = "//Canvas/LoginUIC(Clone)/LicenceCode/bg/screen/Type mobile"
_LICENSE_CONFIRM_PATH = "//Canvas/LoginUIC(Clone)/LicenceCode/bg/screen/Confrim"

# SelfRegistration paths
_REG_SCREEN_PATH      = "//Canvas/LoginUIC(Clone)/SelfRegistration"
_REG_NAME_PATH        = "//Canvas/LoginUIC(Clone)/SelfRegistration/bg/screen/FormLayout/Name/Type mobile"
_REG_GENDER_MALE_PATH = "//Canvas/LoginUIC(Clone)/SelfRegistration/bg/screen/FormLayout/Gender/Image/Toggle"
_REG_GENDER_FEM_PATH  = "//Canvas/LoginUIC(Clone)/SelfRegistration/bg/screen/FormLayout/Gender/Image (1)/Toggle"
_REG_CLASS_PATH       = "//Canvas/LoginUIC(Clone)/SelfRegistration/bg/screen/FormLayout/Class/Dropdown"
_REG_PARENT_PATH      = "//Canvas/LoginUIC(Clone)/SelfRegistration/bg/screen/FormLayout/Parent/Type mobile/Text Area/Text"
_REG_ALT_MOBILE_PATH  = "//Canvas/LoginUIC(Clone)/SelfRegistration/bg/screen/FormLayout/Mobile/Type mobile/Text Area/Text"
_REG_LANG_PATH        = "//Canvas/LoginUIC(Clone)/SelfRegistration/bg/screen/FormLayout/Language/Dropdown"
_REG_CONFIRM_PATH     = "//Canvas/LoginUIC(Clone)/SelfRegistration/bg/screen/Confrim/Text (TMP)"


class LoginPage:
    def __init__(self, session):
        self.session = session
        self.driver  = session.driver

    # ------------------------------------------------------------------
    # Login screen
    # C#: mobileInput.text = user.mobileNumber → confirmButton.onClick.Invoke()
    # ------------------------------------------------------------------

    def wait_for_login_ready(self, timeout=45):
        """C#: while (loginScreen == null && waitTime < 30f)"""
        self.session.find_by_name(_MOBILE_INPUT_NAME, timeout=timeout)
        logger.info("Login screen ready.")

    def enter_mobile_number(self, mobile_number: str):
        self.session.set_input_text_by_name(_MOBILE_INPUT_NAME, mobile_number)
        sleep_seconds(0.5)
        logger.info("Mobile number entered.")

    def tap_confirm(self):
        """C#: confirmButton.onClick.Invoke()"""
        self.session.tap_by_name(_CONFIRM_BUTTON_NAME)
        logger.info("Tapped Confrim.")

    # ------------------------------------------------------------------
    # Post-login screen detection
    #
    # C# (lines 163-204): polls for SelectProfile / LicenceCode /
    # LanguageDialogue with a 20 s timeout.  If none appear, activeScreen
    # stays null — no exception is thrown.  Returns None here for the same
    # behaviour.
    # ------------------------------------------------------------------

    def wait_for_active_screen(self, timeout=20) -> str | None:
        """
        Returns "SelectProfile", "License", "Language", or None.

        None = no panel appeared; app went directly to Begin / ParentsScreen.
        Mirrors C# line 163: while (activeScreen == null && timer < timeout).
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            sp = self._find_active_by_name(_SELECT_PROFILE_NAME)
            lc = self._find_active_by_name(_LICENSE_NAME)
            lg = self._find_active_by_name(_LANGUAGE_DIALOG_NAME)

            if sp and not lc and not lg:
                logger.info("Active screen: SelectProfile")
                return "SelectProfile"
            if lc and not sp and not lg:
                logger.info("Active screen: License")
                return "License"
            if lg and not sp and not lc:
                logger.info("Active screen: Language")
                return "Language"

            time.sleep(0.3)

        logger.info(
            "No post-login panel within %ss — app likely went to Begin/ParentsScreen.",
            timeout,
        )
        return None   # ← not a failure; caller checks scene next

    # ------------------------------------------------------------------
    # SelectProfile flow  (existing user)
    # C#: profileButtons[profileIndex].onClick.Invoke()
    #     nextButton.onClick.Invoke()
    # ------------------------------------------------------------------

    def select_profile_by_index(self, profile_index: int):
        """C#: profilesParent.GetComponentsInChildren<Button>(true)[profileIndex-1]"""
        try:
            buttons = self.driver.find_objects_by_path(
                _PROFILE_PARENT_PATH + "/*", enabled=True
            )
        except Exception:
            buttons = []
        if not buttons:
            buttons = self.driver.find_objects(By.PATH, _PROFILE_PARENT_PATH + "//Button")

        index = max(0, profile_index - 1)
        if index >= len(buttons):
            index = 0
        self._click(buttons[index])
        logger.info("Selected profile index %d.", profile_index)

    def tap_select_profile_next(self):
        """C#: selectProfileScreen.transform.Find("bg/screen/next")"""
        obj = self._wait_for_path(_NEXT_BTN_PATH, timeout=15)
        if obj is None:
            raise RuntimeError(f"Next button not found at '{_NEXT_BTN_PATH}'")
        self._click(obj)
        logger.info("Tapped SelectProfile Next.")

    def tap_avatar_save(self):
        """
        C#: while (selectAvatarScreen == null … waitTime < 30f)
            avatarNextButton.onClick.Invoke()
        """
        if self._wait_for_path(_AVATAR_SCREEN_PATH, timeout=30) is None:
            raise RuntimeError(f"Avatar screen not found at '{_AVATAR_SCREEN_PATH}'")
        save = self._wait_for_path(_AVATAR_SAVE_PATH, timeout=15)
        if save is None:
            raise RuntimeError(f"Avatar save not found at '{_AVATAR_SAVE_PATH}'")
        self._click(save)
        logger.info("Tapped Avatar Save.")

    # ------------------------------------------------------------------
    # Language dialog  (SelectProfile path + Language-only path)
    # C#: while (languageLoading.gameObject.activeInHierarchy) yield return null
    #     languageDropdown.value = user.StudentLanguageIndex
    #     LanguageSaveButton.onClick.Invoke()
    # ------------------------------------------------------------------

    def handle_language_dialog(self, language_index: int, timeout=20):
        """
        Silently returns if the dialog never appears (preference already set).
        C#: if (languageDialog == null) { languageDialogHandled = true; }
        """
        dialog = self._wait_for_path(_LANG_DIALOG_PATH, timeout=timeout)
        if dialog is None:
            logger.info("Language dialog not shown (already set).")
            return

        # Wait for LoadingObject to become inactive
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                loading = self.driver.find_object(By.PATH, _LANG_LOADING_PATH)
                if not loading.enabled:
                    break
            except Exception:
                break
            time.sleep(0.2)

        # Set dropdown value
        try:
            dropdown = self.driver.find_object(By.PATH, _LANG_DROPDOWN_PATH)
            dropdown.set_component_property(
                "TMPro.TMP_Dropdown", "value", "Unity.TextMeshPro", str(language_index)
            )
        except Exception as exc:
            logger.warning("Language dropdown set failed: %s", exc)

        save = self._wait_for_path(_LANG_SAVE_PATH, timeout=10)
        if save is None:
            raise RuntimeError(f"Language save not found at '{_LANG_SAVE_PATH}'")
        self._click(save)
        logger.info("Language saved (index=%d).", language_index)

    # ----------------------------------------------------------tsts--------
    # License / new-user flow
    # C#: licenseInput.text = user.LicenseCode
    #     licenseConfirmButton.onClick.Invoke()
    #     ... fill SelfRegistration form ...
    #     confirmRegButton.onClick.Invoke()
    # ------------------------------------------------------------------

    def enter_license_code(self, license_code: str):
        field = self._wait_for_path(_LICENSE_INPUT_PATH, timeout=20)
        if field is None:
            raise RuntimeError(f"License input not found at '{_LICENSE_INPUT_PATH}'")
        field.set_text(license_code)
        sleep_seconds(0.3)

    def tap_license_confirm(self):
        btn = self._wait_for_path(_LICENSE_CONFIRM_PATH, timeout=10)
        if btn is None:
            raise RuntimeError(f"License Confirm not found at '{_LICENSE_CONFIRM_PATH}'")
        self._click(btn)

    def fill_registration_form(self, user: dict):
        """
        C#: fills StudentName, Gender toggles, Class dropdown,
            StudentParentName, StudentAlternateMobileNumber,
            Language dropdown, then clicks SelfRegistration/bg/screen/Confrim.
        """
        # Wait for registration screen
        if self._wait_for_path(_REG_SCREEN_PATH, timeout=60) is None:
            raise RuntimeError(f"SelfRegistration screen not found at '{_REG_SCREEN_PATH}'")

        # Student name
        name_field = self._wait_for_path(_REG_NAME_PATH, timeout=15)
        if name_field:
            name_field.set_text(user.get("StudentName", ""))

        # Gender
        gender = user.get("StudentGender", "Male")
        if gender == "Male":
            male = self._wait_for_path(_REG_GENDER_MALE_PATH, timeout=10)
            if male:
                self._click(male)
        else:
            female = self._wait_for_path(_REG_GENDER_FEM_PATH, timeout=10)
            if female:
                self._click(female)

        # Class dropdown
        class_dd = self._wait_for_path(_REG_CLASS_PATH, timeout=10)
        if class_dd:
            class_dd.set_component_property(
                "TMPro.TMP_Dropdown", "value", "Unity.TextMeshPro",
                str(user.get("StudentClassIndex", 0))
            )

        # Parent name
        parent_field = self._wait_for_path(_REG_PARENT_PATH, timeout=10)
        if parent_field:
            parent_field.set_text(user.get("StudentParentName", ""))

        # Alternate mobile
        alt_field = self._wait_for_path(_REG_ALT_MOBILE_PATH, timeout=10)
        if alt_field:
            alt_field.set_text(str(user.get("StudentAlternateMobileNumber", "")))

        # Language dropdown — wait for options to populate (C#: while options.Count == 0)
        lang_dd = self._wait_for_path(_REG_LANG_PATH, timeout=50)
        if lang_dd:
            lang_dd.set_component_property(
                "TMPro.TMP_Dropdown", "value", "Unity.TextMeshPro",
                str(user.get("studentLanguageIndex", 0))
            )

        # Confirm
        confirm = self._wait_for_path(_REG_CONFIRM_PATH, timeout=10)
        if confirm is None:
            raise RuntimeError(f"Registration Confirm not found at '{_REG_CONFIRM_PATH}'")
        self._click(confirm)
        logger.info("Registration form submitted.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _click(self, obj):
        sleep_seconds(0.5)
        try:
            self.driver.click_object(obj)
        except AttributeError:
            obj.tap()

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

    def _find_active_by_name(self, name: str):
        try:
            obj = self.driver.find_object(By.NAME, name)
            if obj and obj.enabled:
                return obj
        except Exception:
            pass
        return None
