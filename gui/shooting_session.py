from dataclasses import dataclass


MAX_DURATION_SECONDS = 85
TARGET_VISIBLE_SECONDS_BY_CLASS = {1: 7, 0: 7, 2: 7, 3: 18}
TARGET_CLASS_SEQUENCE = (1, 0, 2, 3)  # Bia 6, 10, 7B, 8.
TARGET_EARLY_SECONDS = 1
TARGET_LATE_SECONDS = 2


@dataclass
class TargetExposure:
    class_id: int
    opened_at: float
    closed_at: float

    def contains(self, received_at):
        return self.opened_at <= received_at < self.closed_at


class ShootingSession:
    """Track scoring windows separately from commanded visibility."""

    def __init__(self, started_at, target_delays=()):
        self.started_at = started_at
        self.deadline = started_at + MAX_DURATION_SECONDS
        self.exposure = None
        self.next_target = 0
        self._raised_at = None
        self._visible_until = None
        self._scheduled = {
            class_id: TargetExposure(
                class_id, max(started_at, started_at + delay - TARGET_EARLY_SECONDS),
                min(started_at + delay + TARGET_VISIBLE_SECONDS_BY_CLASS[class_id]
                    + TARGET_LATE_SECONDS, self.deadline),
            )
            for class_id, delay in zip(TARGET_CLASS_SEQUENCE, target_delays)
        }

    def expired(self, now):
        return now >= self.deadline

    def open_target(self, class_id, now):
        if (self.expired(now) or self.next_target >= len(TARGET_CLASS_SEQUENCE)
                or class_id != TARGET_CLASS_SEQUENCE[self.next_target]):
            return False
        if self.exposure is not None:
            self.exposure.closed_at = min(self.exposure.closed_at, now - TARGET_EARLY_SECONDS)
        opened_at = max(self.started_at, now - TARGET_EARLY_SECONDS)
        # Reuse the object already attached to shots received before the command.
        self.exposure = self._scheduled.get(class_id) or TargetExposure(class_id, opened_at, now)
        self.exposure.opened_at = min(self.exposure.opened_at, opened_at)
        self.exposure.closed_at = min(
            now + TARGET_VISIBLE_SECONDS_BY_CLASS[class_id] + TARGET_LATE_SECONDS,
            self.deadline,
        )
        self._raised_at = now
        self._visible_until = min(now + TARGET_VISIBLE_SECONDS_BY_CLASS[class_id], self.deadline)
        self.next_target += 1
        return True

    def active_target(self, now):
        if self.expired(now):
            return None
        if self.next_target < len(TARGET_CLASS_SEQUENCE):
            class_id = TARGET_CLASS_SEQUENCE[self.next_target]
            upcoming = self._scheduled.get(class_id)
            if upcoming is not None and upcoming.contains(now):
                return upcoming
        if self.exposure is not None and self.exposure.contains(now):
            return self.exposure
        return None

    def close_target(self, class_id, now):
        exposure = self.exposure
        if (exposure is None or exposure.class_id != class_id
                or not self._raised_at <= now < self._visible_until):
            return False
        self._visible_until = now
        exposure.closed_at = min(exposure.closed_at, now + TARGET_LATE_SECONDS, self.deadline)
        return True
