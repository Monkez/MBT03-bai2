from dataclasses import dataclass


MAX_DURATION_SECONDS = 85
TARGET_VISIBLE_SECONDS_BY_CLASS = {1: 7, 0: 7, 2: 7, 3: 18}
TARGET_CLASS_SEQUENCE = (1, 0, 2, 3)  # Bia 6, 10, 7B, 8.
TARGET_EARLY_SECONDS = 2
TARGET_LATE_SECONDS = 4


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
        self.stopped_at = None
        self.exposure = None
        self.next_target = 0
        self._raised_at = None
        self._visible_until = None
        self._raised_times = {}
        self._lowered_times = {}
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

    def stop(self, now):
        if self.stopped_at is None:
            self.stopped_at = min(now, self.deadline)

    def accepts_receipt(self, received_at):
        end = self.deadline if self.stopped_at is None else self.stopped_at
        return self.started_at <= received_at < end

    def window_for_target(self, class_id):
        return self._scheduled.get(class_id)

    def open_target(self, class_id, now):
        if (self.expired(now) or self.next_target >= len(TARGET_CLASS_SEQUENCE)
                or class_id != TARGET_CLASS_SEQUENCE[self.next_target]):
            return False
        opened_at = max(self.started_at, now - TARGET_EARLY_SECONDS)
        # Reuse the object already attached to shots received before the command.
        self.exposure = self._scheduled.get(class_id) or TargetExposure(class_id, opened_at, now)
        self._scheduled[class_id] = self.exposure
        self.exposure.opened_at = min(self.exposure.opened_at, opened_at)
        self._raised_times[class_id] = now
        self.next_target += 1
        self._update_windows()
        return True

    def _update_windows(self):
        for class_id in self._raised_times:
            raised_at = self._raised_times[class_id]
            visible_until = min(raised_at + TARGET_VISIBLE_SECONDS_BY_CLASS[class_id], self.deadline)
            visible_until = min(visible_until, self._lowered_times.get(class_id, visible_until))
            closed_at = min(visible_until + TARGET_LATE_SECONDS, self.deadline)
            self._scheduled[class_id].closed_at = closed_at
            if self.exposure.class_id == class_id:
                self._raised_at = raised_at
                self._visible_until = visible_until

    def confirm_command_sent(self, class_id, sent_at, *, raised):
        """Align the window with the first serial write, not executor queueing."""
        if class_id not in self._raised_times or not self.started_at <= sent_at < self.deadline:
            return False
        if raised:
            self._raised_times[class_id] = sent_at
            self._scheduled[class_id].opened_at = max(self.started_at, sent_at - TARGET_EARLY_SECONDS)
        elif class_id in self._lowered_times:
            self._lowered_times[class_id] = sent_at
        else:
            return False
        self._update_windows()
        return True

    def active_target(self, now, preferred_class_id=None):
        if self.expired(now):
            return None
        # Grace periods may overlap: retain each target's full allowance and
        # select the detected target once inference has identified it.
        upcoming_class = (TARGET_CLASS_SEQUENCE[self.next_target]
                          if self.next_target < len(TARGET_CLASS_SEQUENCE) else None)
        if preferred_class_id is not None and (
                preferred_class_id in self._raised_times or preferred_class_id == upcoming_class):
            preferred = self._scheduled.get(preferred_class_id)
            if preferred is not None and preferred.contains(now):
                return preferred
        if self.next_target < len(TARGET_CLASS_SEQUENCE):
            class_id = TARGET_CLASS_SEQUENCE[self.next_target]
            upcoming = self._scheduled.get(class_id)
            if upcoming is not None and upcoming.contains(now):
                return upcoming
        # Decoding/UI dispatch can finish after the next target has been raised.
        for class_id in reversed(self._raised_times):
            exposure = self._scheduled[class_id]
            if exposure.contains(now):
                return exposure
        return None

    def close_target(self, class_id, now):
        exposure = self.exposure
        if (exposure is None or exposure.class_id != class_id
                or not self._raised_at <= now < self._visible_until):
            return False
        self._lowered_times[class_id] = now
        self._update_windows()
        return True
