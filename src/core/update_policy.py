"""Persisted, version-specific update reminders; manual checks always bypass them."""
import math


UPDATE_INTERVAL_SECONDS = 24 * 60 * 60


def _timestamp(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else 0
    except (TypeError, ValueError):
        return 0


def should_notify(version, preferences, now):
    if preferences.get('skipped_version') == version:
        return False
    if preferences.get('snoozed_version') == version:
        if now < _timestamp(preferences.get('snooze_until')):
            return False
    if preferences.get('notified_version') == version:
        if now < _timestamp(preferences.get('notified_at')) + UPDATE_INTERVAL_SECONDS:
            return False
    return True


def reminder_changes(action, version, now):
    if action == 'skip':
        return {'skipped_version': version}
    if action == 'later':
        return {'snoozed_version': version, 'snooze_until': now + UPDATE_INTERVAL_SECONDS}
    if action == 'shown':
        return {'notified_version': version, 'notified_at': now}
    raise ValueError('Unknown update reminder action')
