"""
conftest.py
-----------
Pytest session fixture. Provides the ``alt_session`` fixture used by all tests.
"""

import sys
from pathlib import Path

import pytest

# Ensure "from framework..." and "from pages..." imports work when pytest
# is invoked from the Automation/ directory.
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


@pytest.fixture(scope="module")
def alt_session():
    from framework.driver_session import get_session
    session = get_session()
    yield session
    session.driver.stop()
