"""Idle automation state machine tests (cross-platform)."""

from __future__ import annotations

import unittest

from app.idle_monitor import IdleAutomationState


class IdleAutomationStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = IdleAutomationState()
        self.state.initialize(1000)

    def test_does_not_trigger_while_idle_period_already_processed(self) -> None:
        self.state.on_automation_started(1000)
        self.state.on_automation_completed(1000)

        self.assertTrue(self.state.automation_triggered_for_current_idle_period)
        self.assertFalse(self.state.should_trigger_automation(300.0, 180.0))

    def test_user_activity_after_automation_resets_idle_period(self) -> None:
        self.state.on_automation_started(1000)
        self.state.on_automation_completed(1000)

        self.state.poll_for_activity_reset(1005)

        self.assertFalse(self.state.automation_triggered_for_current_idle_period)
        self.assertTrue(self.state.should_trigger_automation(180.0, 180.0))

    def test_mouse_movement_before_first_automation_does_not_require_manual_reset(self) -> None:
        self.assertTrue(self.state.should_trigger_automation(180.0, 180.0))

        self.state.poll_for_activity_reset(1005)

        self.assertFalse(self.state.automation_triggered_for_current_idle_period)

    def test_user_activity_during_automation_detected(self) -> None:
        self.state.on_automation_started(1000)

        self.assertTrue(self.state.has_user_activity_since_automation_started(1001))

    def test_cancelled_automation_allows_future_trigger(self) -> None:
        self.state.on_automation_started(1000)
        self.state.on_automation_cancelled()

        self.assertFalse(self.state.automation_in_progress)
        self.assertTrue(self.state.should_trigger_automation(180.0, 180.0))


if __name__ == "__main__":
    unittest.main()
