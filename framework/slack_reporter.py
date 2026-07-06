"""
framework/slack_reporter.py
---------------------------
Python equivalent of TestLogger.cs.

Accumulates per-user test results and sends them to Slack in one message
after all users are processed.  Chunks messages at 3500 chars to stay
within Slack's API limit (mirrors SendInChunks in C#).

Usage
-----
    from framework.slack_reporter import SlackReporter

    reporter = SlackReporter(total_users=len(users))

    reporter.write_log(mobile, passed=True,  test_name="Mobile Number Entered")
    reporter.write_log(mobile, passed=False, test_name="Avatar Screen")

    reporter.send_all_to_slack()   # call once after all users

Configuration
-------------
Set the SLACK_WEBHOOK_URL environment variable.  Falls back to the
hard-coded URL from TestLogger.cs if the variable is not set.
"""

from __future__ import annotations

import datetime
import logging
import os
from collections import defaultdict

logger = logging.getLogger(__name__)

# Set the Slack Incoming Webhook via the SLACK_WEBHOOK_URL env var / repo secret.
# (Never hardcode a webhook here — this repo is public.)
_DEFAULT_WEBHOOK = os.environ.get("SLACK_WEBHOOK_URL", "")
_SLACK_CHUNK_SIZE = 3500


class SlackReporter:
    def __init__(self, total_users: int = 0):
        self._total_users  = total_users
        self._logs_by_user: dict[str, list[str]] = defaultdict(list)
        self._timestamps:   dict[str, str]       = {}
        self._webhook_url   = os.environ.get("SLACK_WEBHOOK_URL", _DEFAULT_WEBHOOK)

    # ------------------------------------------------------------------
    # Public API  (mirrors TestLogger.WriteLog / SendAllLogsToSlack)
    # ------------------------------------------------------------------

    def write_log(self, mobile: str, passed: bool, test_name: str) -> None:
        """Record one test result for *mobile*. Equivalent to WriteLog()."""
        if mobile not in self._timestamps:
            self._timestamps[mobile] = datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        status = "✅" if passed else "❌"
        self._logs_by_user[mobile].append(f"Test: {test_name} , Passed:{status}")
        logger.debug("[%s] logged: %s %s", mobile, test_name, status)

    def send_all_to_slack(self) -> None:
        """Build the full report and POST it to Slack. Equivalent to SendAllLogsToSlack()."""
        if not self._logs_by_user:
            logger.warning("No logs to send to Slack.")
            return

        tested = len(self._logs_by_user)
        lines  = [
            f"Total No. of Schools : {self._total_users}",
            f"Tested No. of Schools : {tested}",
            "",
        ]

        for mobile, tests in self._logs_by_user.items():
            ts = self._timestamps.get(mobile, "")
            lines.append(f"[{ts}]")
            lines.append(f"Mobile Number : {mobile}")
            lines.extend(tests)
            lines.append("")

        full_text = "\n".join(lines)
        self._send_in_chunks(full_text)

        self._logs_by_user.clear()
        self._timestamps.clear()
        logger.info("Slack report sent ✓")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _send_in_chunks(self, text: str) -> None:
        start = 0
        while start < len(text):
            chunk = text[start : start + _SLACK_CHUNK_SIZE]
            self._post_to_slack(chunk)
            start += _SLACK_CHUNK_SIZE

    def _post_to_slack(self, message: str) -> None:
        import json
        import urllib.request

        if not self._webhook_url:
            logger.warning("SLACK_WEBHOOK_URL not set — skipping Slack post.")
            return

        payload  = json.dumps({"text": f"```{message}```"}).encode()
        req      = urllib.request.Request(
            self._webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                logger.debug("Slack response: %s", resp.status)
        except Exception as exc:
            logger.error("Failed to send Slack message: %s", exc)
