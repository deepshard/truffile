import re
from typing import Any, Dict, List, Optional, Tuple
from google.protobuf.duration_pb2 import Duration
from truffle.app import background_pb2

_DAY_BIT = {
    "sat": 0,
    "fri": 1,
    "thu": 2,
    "wed": 3,
    "tue": 4,
    "mon": 5,
    "sun": 6,
}

_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$")

def _parse_time_of_day(s: str, *, ctx: str):
    m = _TIME_RE.match(s or "")
    if not m:
        raise ValueError(f"{ctx}: invalid time '{s}', expected HH:MM or HH:MM:SS")
    hh = int(m.group(1))
    mm = int(m.group(2))
    ss = int(m.group(3) or "0")
    if not (0 <= hh <= 23): raise ValueError(f"{ctx}: hour out of range: {hh}")
    if not (0 <= mm <= 59): raise ValueError(f"{ctx}: minute out of range: {mm}")
    if not (0 <= ss <= 59): raise ValueError(f"{ctx}: second out of range: {ss}")
    return hh, mm, ss

def _set_time_of_day(msg_time_of_day, s: str, *, ctx: str) -> None:
    hh, mm, ss = _parse_time_of_day(s, ctx=ctx)
    msg_time_of_day.hour = hh
    msg_time_of_day.minute = mm
    msg_time_of_day.second = ss

def _parse_daily_window(v: Any, *, ctx: str) -> Optional[Tuple[str, str]]:
    if v is None:
        return None
    if isinstance(v, str):
        parts = v.split("-", 1)
        if len(parts) != 2:
            raise ValueError(f"{ctx}: daily_window must be 'HH:MM-HH:MM[:SS]'")
        start_s = parts[0].strip()
        end_s = parts[1].strip()
        _parse_time_of_day(start_s, ctx=f"{ctx}.daily_window start")
        _parse_time_of_day(end_s, ctx=f"{ctx}.daily_window end")
        return start_s, end_s
    if isinstance(v, dict):
        start_s = v.get("start")
        end_s = v.get("end")
        if not isinstance(start_s, str) or not isinstance(end_s, str):
            raise ValueError(f"{ctx}: daily_window dict must have string start/end")
        _parse_time_of_day(start_s, ctx=f"{ctx}.daily_window start")
        _parse_time_of_day(end_s, ctx=f"{ctx}.daily_window end")
        return start_s, end_s
    raise ValueError(f"{ctx}: daily_window must be string or object")

def _day_mask_from_allowed_days(days: List[str], *, ctx: str) -> int:
    forbidden = 0
    allowed_bits = set()
    for d in days:
        if not isinstance(d, str):
            raise ValueError(f"{ctx}: day entries must be strings")
        k = d.strip().lower()[:3]
        if k not in _DAY_BIT:
            raise ValueError(f"{ctx}: unknown day '{d}' (use sun/mon/tue/wed/thu/fri/sat)")
        allowed_bits.add(_DAY_BIT[k])
    if not allowed_bits:
        raise ValueError(f"{ctx}: allowed_days cannot be empty")
    for k, bit in _DAY_BIT.items():
        if bit not in allowed_bits:
            forbidden |= (1 << bit)
    return forbidden

def _day_mask_from_forbidden_days(days: List[str], *, ctx: str) -> int:
    forbidden = 0
    for d in days:
        if not isinstance(d, str):
            raise ValueError(f"{ctx}: day entries must be strings")
        k = d.strip().lower()[:3]
        if k not in _DAY_BIT:
            raise ValueError(f"{ctx}: unknown day '{d}' (use sun/mon/tue/wed/thu/fri/sat)")
        forbidden |= (1 << _DAY_BIT[k])
    if forbidden == 0b1111111:
        raise ValueError(f"{ctx}: forbidden_days forbids all days (invalid)")
    return forbidden

_DUR_RE = re.compile(r"^\s*(\d+)\s*(ms|s|m|h|d)\s*$", re.IGNORECASE)

def _parse_duration(s: str, *, ctx: str) -> Duration:
    if not isinstance(s, str):
        raise ValueError(f"{ctx}: duration must be a string like '15m' or '2h'")
    m = _DUR_RE.match(s)
    if not m:
        raise ValueError(f"{ctx}: invalid duration '{s}' (use ms/s/m/h/d)")
    n = int(m.group(1))
    unit = m.group(2).lower()
    seconds = 0
    nanos = 0
    if unit == "ms":
        seconds = n // 1000
        nanos = (n % 1000) * 1_000_000
    elif unit == "s":
        seconds = n
    elif unit == "m":
        seconds = n * 60
    elif unit == "h":
        seconds = n * 3600
    elif unit == "d":
        seconds = n * 86400
    dur = Duration()
    dur.seconds = seconds
    dur.nanos = nanos
    return dur


def parse_runtime_policy(schedule_cfg_data: Dict[str, Any]) -> background_pb2.BackgroundAppRuntimePolicy:
    if not isinstance(schedule_cfg_data, dict):
        raise ValueError("default_schedule must be an object")

    policy_type = schedule_cfg_data.get("type")
    if policy_type not in ("interval", "times", "always"):
        raise ValueError(f"Invalid default_schedule.type: {policy_type}")

    runtime_policy = background_pb2.BackgroundAppRuntimePolicy()

    if policy_type == "always":
        runtime_policy.always.SetInParent()
        return runtime_policy

    if policy_type == "interval":
        interval_obj = schedule_cfg_data.get("interval")
        if not isinstance(interval_obj, dict):
            raise ValueError("default_schedule.interval must be an object")

        dur_s = interval_obj.get("duration", None)
        if not isinstance(dur_s, str):
            raise ValueError("default_schedule.interval.duration must be a string")
        runtime_policy.interval.duration.CopyFrom(_parse_duration(dur_s, ctx="default_schedule.interval.duration"))

        sched = interval_obj.get("schedule", {})
        if sched is None:
            sched = {}
        if not isinstance(sched, dict):
            raise ValueError("default_schedule.interval.schedule must be an object")

        allowed_days = sched.get("allowed_days")
        forbidden_days = sched.get("forbidden_days")
        if allowed_days is not None and forbidden_days is not None:
            raise ValueError("Provide only one of schedule.allowed_days or schedule.forbidden_days")

        if allowed_days is not None:
            if not isinstance(allowed_days, list):
                raise ValueError("schedule.allowed_days must be a list")
            runtime_policy.interval.schedule.weekly_window.day_mask = _day_mask_from_allowed_days(
                allowed_days, ctx="default_schedule.interval.schedule.allowed_days"
            )
        elif forbidden_days is not None:
            if not isinstance(forbidden_days, list):
                raise ValueError("schedule.forbidden_days must be a list")
            runtime_policy.interval.schedule.weekly_window.day_mask = _day_mask_from_forbidden_days(
                forbidden_days, ctx="default_schedule.interval.schedule.forbidden_days"
            )
        else:
            runtime_policy.interval.schedule.weekly_window.day_mask = 0

        dw = _parse_daily_window(sched.get("daily_window"), ctx="default_schedule.interval.schedule")
        if dw is not None:
            start_s, end_s = dw
            runtime_policy.interval.schedule.daily_window.SetInParent()
            _set_time_of_day(runtime_policy.interval.schedule.daily_window.daily_start_time, start_s,
                             ctx="default_schedule.interval.schedule.daily_window.start")
            _set_time_of_day(runtime_policy.interval.schedule.daily_window.daily_end_time, end_s,
                             ctx="default_schedule.interval.schedule.daily_window.end")

        return runtime_policy

    if policy_type == "times":
        times_obj = schedule_cfg_data.get("times")
        if not isinstance(times_obj, dict):
            raise ValueError("default_schedule.times must be an object")

        run_times = times_obj.get("run_times")
        if not isinstance(run_times, list) or not run_times:
            raise ValueError("default_schedule.times.run_times must be a non-empty list of time strings")

        for i, t in enumerate(run_times):
            if not isinstance(t, str):
                raise ValueError("default_schedule.times.run_times must contain strings")
            tod = runtime_policy.times.run_times.add()
            _set_time_of_day(tod, t, ctx=f"default_schedule.times.run_times[{i}]")

        allowed_days = times_obj.get("allowed_days")
        forbidden_days = times_obj.get("forbidden_days")
        if allowed_days is not None and forbidden_days is not None:
            raise ValueError("Provide only one of times.allowed_days or times.forbidden_days")

        if allowed_days is not None:
            if not isinstance(allowed_days, list):
                raise ValueError("times.allowed_days must be a list")
            runtime_policy.times.weekly_window.day_mask = _day_mask_from_allowed_days(
                allowed_days, ctx="default_schedule.times.allowed_days"
            )
        elif forbidden_days is not None:
            if not isinstance(forbidden_days, list):
                raise ValueError("times.forbidden_days must be a list")
            runtime_policy.times.weekly_window.day_mask = _day_mask_from_forbidden_days(
                forbidden_days, ctx="default_schedule.times.forbidden_days"
            )
        else:
            runtime_policy.times.weekly_window.day_mask = 0

        return runtime_policy

    raise RuntimeError("unreachable")
