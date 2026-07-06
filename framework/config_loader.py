"""
framework/config_loader.py
--------------------------
Loads test user data from config/test_users.json.

JSON schema matches TestUserDataScriptable.cs / TestUser exactly:

  mobileNumber              str   — mobile number used to log in
  profileIndex              int   — 1-based index of profile to select
  flow                      str   — "existing" | "new"  (Python-only field)
  studentLanguageIndex      int   — language dropdown index
  LicenseCode               str   — license code for new-user flow
  StudentName               str   — student name for registration
  StudentGender             str   — "Male" | "Female"
  StudentClassIndex         int   — class dropdown index
  StudentParentName         str   — parent name for registration
  StudentAlternateMobileNumber int — alternate mobile for registration
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def load_test_users() -> list[dict]:
    """
    Load users from config/test_users.json.
    Falls back to a single user built from environment variables if the
    file is missing (useful for CI pipelines).
    """
    config_path = Path(__file__).resolve().parents[1] / "config" / "test_users.json"

    if config_path.exists():
        with open(config_path, encoding="utf-8") as fh:
            return json.load(fh)

    # CI fallback
    return [
        {
            "mobileNumber": os.environ.get("TEST_MOBILE", ""),
            "profileIndex": int(os.environ.get("TEST_PROFILE_INDEX", "1")),
            "flow": os.environ.get("TEST_FLOW", "existing"),
            "studentLanguageIndex": int(os.environ.get("TEST_LANG_INDEX", "0")),
            "LicenseCode": os.environ.get("TEST_LICENSE_CODE", ""),
            "StudentName": os.environ.get("TEST_STUDENT_NAME", ""),
            "StudentGender": os.environ.get("TEST_STUDENT_GENDER", "Male"),
            "StudentClassIndex": int(os.environ.get("TEST_CLASS_INDEX", "0")),
            "StudentParentName": os.environ.get("TEST_PARENT_NAME", ""),
            "StudentAlternateMobileNumber": int(
                os.environ.get("TEST_ALT_MOBILE", "0")
            ),
        }
    ]
