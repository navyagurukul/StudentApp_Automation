"""
pages/language_page.py
----------------------
Kept for import compatibility. Logic is now in LoginPage.handle_language_dialog().
"""
from pages.login_page import LoginPage


class LanguagePage:
    """Thin shim — delegates to LoginPage.handle_language_dialog()."""

    def __init__(self, session):
        self._login_page = LoginPage(session)

    def select_language_index(self, index: int):
        self._index = index

    def tap_save(self):
        self._login_page.handle_language_dialog(
            getattr(self, "_index", 0), timeout=20
        )
