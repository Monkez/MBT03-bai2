"""Receipt-time grouping, independent of inference completion order."""
import math


def same_burst(previous, current, threshold):
    if (isinstance(previous, bool) or isinstance(current, bool)
            or not isinstance(previous, (int, float)) or not isinstance(current, (int, float))):
        return False
    gap = current - previous
    return (math.isfinite(previous) and math.isfinite(current) and 0 <= gap < threshold
            and not math.isclose(gap, threshold, rel_tol=0, abs_tol=1e-9))


def burst_groups(records, threshold):
    """Return shot-number spans, using recorded burst IDs when available."""
    groups = []
    previous = None
    for number, record in sorted(records.items()):
        joined = False
        if previous is not None:
            old_number, old = previous
            if record.get("burst_id") is not None and old.get("burst_id") is not None:
                joined = record["burst_id"] == old["burst_id"]
            else:
                joined = (number == old_number + 1 and same_burst(
                    old.get("received_at"), record.get("received_at"), threshold))
        if joined:
            groups[-1].extend(range(previous[0] + 1, number + 1))
        else:
            groups.append([number])
        previous = number, record
    return groups


def single_shot_violations(shots, receipts, threshold, *, limit, final=True, now=None):
    """Assess complete receipt groups; inference completion must not create singles."""
    records = {number: dict(record) for number, record in receipts.items() if 1 <= number <= limit}
    by_number = {}
    for index, shot in enumerate(shots):
        number = int(shot.get("shot_number", index + 1))
        if 1 <= number <= limit:
            by_number[number] = shot
            records[number] = {**shot, **records.get(number, {})}
    groups = burst_groups(records, threshold)
    singles, targets = [], set()
    for index, group in enumerate(groups):
        if len(group) != 1:
            continue
        number = group[0]
        record = records[number]
        at = record.get("received_at")
        valid_time = isinstance(at, (int, float)) and not isinstance(at, bool) and math.isfinite(at)
        if not valid_time and record.get("burst_id") is None:
            continue  # Older/imported data has no evidence of firing cadence.
        if not final and index == len(groups) - 1:
            if not valid_time or now is None or now < at or same_burst(at, now, threshold):
                continue
        singles.append(number)
        target = record.get("displayed_target_index")
        if target not in (0, 1, 2, 3):
            target = by_number.get(number, {}).get("target_index")
        if target not in (0, 1, 2, 3):
            target = record.get("expected_target_index")
        if target in (0, 1, 2, 3):
            targets.add(target)
    return tuple(singles), frozenset(targets)
