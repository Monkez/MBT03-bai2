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
