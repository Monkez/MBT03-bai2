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

    def __init__(self, started_at, target_delays=(), visible_seconds=None, hardware_delay_time=None,
                 feedback_targets=(), carriage_timeout_seconds=None, display_delays=None):
        self.visible_seconds = dict(TARGET_VISIBLE_SECONDS_BY_CLASS if visible_seconds is None else visible_seconds)
        self.hardware_delay_time = hardware_delay_time or 0
        if display_delays is None:
            display_delays = (self.hardware_delay_time, self.hardware_delay_time)
        self._show_display_delay, self._hide_display_delay = display_delays
        self._hardware_mode = hardware_delay_time is not None
        self._early = TARGET_EARLY_SECONDS if hardware_delay_time is None else 0
        self._late = TARGET_LATE_SECONDS if hardware_delay_time is None else 2 * hardware_delay_time
        self.started_at = started_at
        self.deadline = started_at + MAX_DURATION_SECONDS
        self.stopped_at = None
        self.exposure = None
        self.next_target = 0
        self._raised_at = None
        self._visible_until = None
        self._raised_times = {}
        self._lowered_times = {}
        self._confirmed_hides = set()
        self._feedback_targets = frozenset(feedback_targets)
        self._target_states = {}
        self._feedback_complete = set()
        self._carriage_timeout_seconds = carriage_timeout_seconds
        self._carriage_deadline = None
        self._confirmed_raises = set()
        self._planned_shows = {target: started_at + delay + self._show_display_delay
                               for target, delay in zip(TARGET_CLASS_SEQUENCE, target_delays)}
        self._planned_hides = {
            target: started_at + delay + self.visible_seconds[target]
            for target, delay in zip(TARGET_CLASS_SEQUENCE, target_delays)
        }
        if self._hardware_mode and self._planned_hides:
            self.deadline = max(self._planned_hides.values()) + 4 * self.hardware_delay_time
        self._scheduled = {
            class_id: TargetExposure(
                class_id, max(started_at, started_at + delay - self._early),
                min(started_at + delay + self.visible_seconds[class_id]
                    + self._late, self.deadline),
            )
            for class_id, delay in zip(TARGET_CLASS_SEQUENCE, target_delays)
        }

    def expired(self, now):
        if self._carriage_deadline is not None:
            return now >= self._carriage_deadline
        if self._hardware_mode and not self.all_hides_sent:
            return False
        return now >= self.deadline

    @property
    def all_hides_sent(self):
        return (all(target in self._confirmed_hides for target in TARGET_CLASS_SEQUENCE)
                and self._feedback_targets <= self._feedback_complete)

    def visible_target_classes(self, now):
        if self.stopped_at is not None or self.expired(now):
            return ()
        visible = []
        for target, raised in self._raised_times.items():
            if target in self._feedback_targets:
                states = [shown for at, shown in self._target_states.get(target, ()) if at <= now]
                if states and states[-1]:
                    visible.append(target)
                continue
            if self._hardware_mode and target not in self._confirmed_raises:
                continue
            hidden = self._lowered_times.get(target, raised + self.visible_seconds[target])
            if self._hardware_mode and target not in self._confirmed_hides:
                hidden = float("inf")
            if raised + self._show_display_delay <= now < hidden + self._hide_display_delay:
                visible.append(target)
        return tuple(visible)

    def target_presentation(self, now):
        """Return the focused target and commanded visibility, without scoring grace."""
        if self.stopped_at is not None or self.expired(now):
            return None
        visible = self.visible_target_classes(now)
        if visible:
            return visible[-1], True
        raised = [target for target in TARGET_CLASS_SEQUENCE
                  if target in self._raised_times
                  and (not self._hardware_mode or target in self._confirmed_raises)
                  and self._raised_times[target] + self._show_display_delay <= now]
        if not raised:
            return TARGET_CLASS_SEQUENCE[0], False
        class_id = raised[-1]
        closed_at = self._lowered_times.get(
            class_id, self._raised_times[class_id] + self.visible_seconds[class_id])
        closed_at = min(closed_at + self._hide_display_delay, self.deadline)
        index = TARGET_CLASS_SEQUENCE.index(class_id)
        if index + 1 < len(TARGET_CLASS_SEQUENCE):
            upcoming = TARGET_CLASS_SEQUENCE[index + 1]
            next_show = self._planned_shows.get(upcoming)
            if upcoming in self._raised_times and (
                    not self._hardware_mode or upcoming in self._confirmed_raises):
                next_show = self._raised_times[upcoming] + self._show_display_delay
            if next_show is not None and now >= (closed_at + next_show) / 2:
                class_id = upcoming
        return class_id, False

    def stop(self, now):
        if self.stopped_at is None:
            self.stopped_at = min(now, self.deadline)

    def accepts_receipt(self, received_at):
        end = self.deadline if self.stopped_at is None else self.stopped_at
        if (self.stopped_at is None and self._hardware_mode and not self.all_hides_sent
                and self._carriage_deadline is None):
            end = float("inf")
        return self.started_at <= received_at < end

    def window_for_target(self, class_id):
        return self._scheduled.get(class_id)

    def open_target(self, class_id, now):
        if (self.expired(now) or self.next_target >= len(TARGET_CLASS_SEQUENCE)
                or class_id != TARGET_CLASS_SEQUENCE[self.next_target]):
            return False
        opened_at = max(self.started_at, now - self._early)
        # Reuse the object already attached to shots received before the command.
        self.exposure = self._scheduled.get(class_id) or TargetExposure(class_id, opened_at, now)
        self._scheduled[class_id] = self.exposure
        self.exposure.opened_at = min(self.exposure.opened_at, opened_at)
        self._raised_times[class_id] = now
        self.next_target += 1
        self._update_windows()
        return True

    def _update_windows(self):
        if self._hardware_mode and self._planned_hides:
            self.deadline = max(self._lowered_times.get(target, hidden)
                                for target, hidden in self._planned_hides.items()) + 4 * self.hardware_delay_time
        if self._carriage_deadline is not None:
            self.deadline = self._carriage_deadline
        for class_id in self._raised_times:
            raised_at = self._raised_times[class_id]
            visible_until = min(raised_at + self.visible_seconds[class_id], self.deadline)
            if self._hardware_mode:
                visible_until = self._lowered_times.get(class_id, visible_until)
            else:
                visible_until = min(visible_until, self._lowered_times.get(class_id, visible_until))
            closed_at = min(visible_until + self._late, self.deadline)
            if self._hardware_mode and class_id not in self._confirmed_hides:
                closed_at = float("inf")
            self._scheduled[class_id].closed_at = closed_at
            if self.exposure.class_id == class_id:
                self._raised_at = raised_at
                self._visible_until = visible_until

    def record_target_state(self, target, shown, observed_at):
        """Return True once physical feedback confirms the end of this run."""
        if (target not in self._feedback_targets or target not in self._confirmed_raises
                or self.stopped_at is not None or observed_at < self._raised_times[target]):
            return False
        states = self._target_states.setdefault(target, [])
        if states and observed_at < states[-1][0]:
            return False
        was_shown = any(state for _, state in states)
        if not states or states[-1][1] != shown:
            states.append((observed_at, shown))
        if not shown and (was_shown or target in self._confirmed_hides):
            if target not in self._confirmed_hides:
                self.close_target(target, observed_at, scheduled=True)
                self.confirm_command_sent(target, observed_at, raised=False)
            self._feedback_complete.add(target)
            if target == 3 and self._carriage_deadline is not None:
                self._carriage_deadline = min(self._carriage_deadline, observed_at + 2)
                self._update_windows()
        return target in self._feedback_complete

    def confirm_command_sent(self, class_id, sent_at, *, raised):
        """Align the window with the first serial write, not executor queueing."""
        if (class_id not in self._raised_times or sent_at < self.started_at
                or (not self._hardware_mode and sent_at >= self.deadline)):
            return False
        if raised:
            self._confirmed_raises.add(class_id)
            self._raised_times[class_id] = sent_at
            self._scheduled[class_id].opened_at = max(self.started_at, sent_at - self._early)
            if class_id == 3 and self._carriage_timeout_seconds is not None:
                self._carriage_deadline = sent_at + self._carriage_timeout_seconds
        elif class_id in self._lowered_times:
            self._confirmed_hides.add(class_id)
            self._lowered_times[class_id] = sent_at
            if class_id == 3 and class_id not in self._feedback_targets and self._carriage_deadline is not None:
                self._carriage_deadline = min(self._carriage_deadline, sent_at + self._hide_display_delay + 2)
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
                preferred_class_id in self._raised_times or preferred_class_id == upcoming_class) and (
                not self._hardware_mode or preferred_class_id in self._confirmed_raises):
            preferred = self._scheduled.get(preferred_class_id)
            if preferred is not None and preferred.contains(now):
                return preferred
        if self.next_target < len(TARGET_CLASS_SEQUENCE):
            class_id = TARGET_CLASS_SEQUENCE[self.next_target]
            upcoming = self._scheduled.get(class_id)
            if (upcoming is not None and upcoming.contains(now)
                    and (not self._hardware_mode or class_id in self._confirmed_raises)):
                return upcoming
        # Decoding/UI dispatch can finish after the next target has been raised.
        for class_id in reversed(self._raised_times):
            if self._hardware_mode and class_id not in self._confirmed_raises:
                continue
            exposure = self._scheduled[class_id]
            if exposure.contains(now):
                return exposure
        return None

    @property
    def raised_target_classes(self):
        return tuple(self._raised_times)

    def close_target(self, class_id, now, *, scheduled=False):
        if scheduled:
            if (class_id not in self._raised_times or now < self._raised_times[class_id]
                    or (not self._hardware_mode and now >= self.deadline)):
                return False
            self._lowered_times[class_id] = now
            self._update_windows()
            return True
        if self._hardware_mode:
            if (class_id not in self._raised_times or class_id in self._lowered_times
                    or not self._raised_times[class_id] <= now < self._raised_times[class_id] + self.visible_seconds[class_id]):
                return False
            self._lowered_times[class_id] = now
            self._update_windows()
            return True
        exposure = self.exposure
        if (exposure is None or exposure.class_id != class_id
                or not self._raised_at <= now < (self.deadline if scheduled else self._visible_until)):
            return False
        self._lowered_times[class_id] = now
        self._update_windows()
        return True
