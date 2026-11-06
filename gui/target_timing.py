"""Validated exercise times and atomic persistence; no device I/O."""
import copy
import json
import math
import os
from pathlib import Path
import tempfile

import config as cf
from gui.shooting_session import (
    TARGET_CLASS_SEQUENCE, TARGET_VISIBLE_SECONDS_BY_CLASS,
)

TARGET_LABELS = ("BIA SỐ 6", "BIA SỐ 10", "BIA SỐ 7B", "BIA SỐ 8C")
RAISE_COMMANDS = ("@114#", "@224#", "@334#", "@441#")
HIDE_COMMANDS = {1: "@112#", 0: "@222#", 2: "@332#", 3: "@442#"}
MAX_SETTING_SECONDS = 3600


def hardware_delay_time():
    value = cf.get_setting("shooting.hardware_delay_time", 1.5)
    try:
        value = float(value)
        if not math.isfinite(value) or not 0 <= value < MAX_SETTING_SECONDS:
            return 1.5
        for candidate in _timing_candidates():
            try:
                first_show = validate_times(candidate)[0]["show_seconds"]
                return value if value <= first_show else 1.5
            except ValueError:
                continue
        return 1.5
    except (TypeError, ValueError, OverflowError):
        return 1.5


def validate_times(values, minimum_show=0):
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError("Cần nhập đủ mốc hiện và ẩn cho bốn bia.")
    result = []
    previous_show = 0
    for label, item in zip(TARGET_LABELS, values):
        try:
            shown, hidden = item["show_seconds"], item["hide_seconds"]
            if isinstance(shown, bool) or isinstance(hidden, bool):
                raise ValueError()
            shown, hidden = float(shown), float(hidden)
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ValueError(f"{label}: mốc thời gian phải là số.") from None
        if not (math.isfinite(shown) and math.isfinite(hidden)
                and minimum_show <= shown < hidden <= MAX_SETTING_SECONDS):
            raise ValueError(f"{label}: cần {minimum_show:g} ≤ Hiện < Ẩn ≤ {MAX_SETTING_SECONDS} giây.")
        if shown < previous_show:
            raise ValueError(f"{label}: mốc Hiện phải từ {previous_show:g} giây trở đi theo thứ tự bia.")
        result.append({"show_seconds": shown, "hide_seconds": hidden})
        previous_show = shown
    return result


def _timing_candidates():
    yield cf.get_setting("shooting.target_times", [])
    for legacy in (cf.get_setting("shooting.lora_timeline", []),
                   cf.DEFAULT_CONFIG["shooting"]["lora_timeline"]):
        try:
            if len(legacy) == 4:
                yield [{"show_seconds": item["delay_seconds"],
                        "hide_seconds": float(item["delay_seconds"]) + TARGET_VISIBLE_SECONDS_BY_CLASS[target]}
                       for target, item in zip(TARGET_CLASS_SEQUENCE, legacy)]
        except (KeyError, TypeError, ValueError, OverflowError):
            continue


def get_target_times():
    delay = hardware_delay_time()
    for candidate in _timing_candidates():
        try:
            return validate_times(candidate, delay)
        except ValueError:
            continue
    raise ValueError("Lịch mặc định không hợp lệ.")


def save_timing_settings(values, channel, path=None):
    times = validate_times(values, hardware_delay_time())
    if type(channel) is not int or channel not in (1, 2, 3):
        raise ValueError("Chọn Kênh 1, 2 hoặc 3.")
    destination = Path(cf.CONFIG_PATH if path is None else path)
    try:
        raw = json.loads(destination.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw = {}
    if not isinstance(raw, dict) or not isinstance(raw.get("shooting", {}), dict):
        raise ValueError("File cấu hình có dữ liệu không hợp lệ; chưa lưu thay đổi.")
    raw.setdefault("shooting", {}).update(target_times=times, control_channel=channel)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                         prefix=".timing-", suffix=".tmp", delete=False) as output:
            temporary = output.name
            json.dump(raw, output, ensure_ascii=False, indent=4)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)
    cf.APP_CONFIG["shooting"].update(target_times=copy.deepcopy(times), control_channel=channel)
