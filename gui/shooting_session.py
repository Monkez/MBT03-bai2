from dataclasses import dataclass


MAX_DURATION_SECONDS = 75
TARGET_VISIBLE_SECONDS = 7
TARGET_CLASS_SEQUENCE = (1, 0, 2, 3)  # Bia 6, 10, 7B, 8.


@dataclass
class TargetExposure:
    class_id: int
    opened_at: float
    closed_at: float

    def contains(self, received_at):
        return self.opened_at <= received_at < self.closed_at


class ShootingSession:
    """Track commanded exposure windows using the PC's monotonic clock."""

    def __init__(self, started_at):
        self.deadline = started_at + MAX_DURATION_SECONDS
        self.exposure = None
        self.next_target = 0

    def expired(self, now):
        return now >= self.deadline

    def open_target(self, class_id, now):
        if (self.expired(now) or self.next_target >= len(TARGET_CLASS_SEQUENCE)
                or class_id != TARGET_CLASS_SEQUENCE[self.next_target]):
            return False
        if self.exposure is not None:
            self.exposure.closed_at = min(self.exposure.closed_at, now)
        self.exposure = TargetExposure(
            class_id, now, min(now + TARGET_VISIBLE_SECONDS, self.deadline)
        )
        self.next_target += 1
        return True

    def active_target(self, now):
        if self.exposure is not None and self.exposure.contains(now):
            return self.exposure
        return None

    def close_target(self, class_id, now):
        exposure = self.active_target(now)
        if exposure is None or exposure.class_id != class_id:
            return False
        exposure.closed_at = now
        return True
