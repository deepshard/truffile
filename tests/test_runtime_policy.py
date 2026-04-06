import unittest

from truffile.schema.runtime_policy import (
    parse_runtime_policy,
    _parse_duration,
    _parse_time_of_day,
    _parse_daily_window,
)


class TestParseDuration(unittest.TestCase):
    def test_minutes(self):
        d = _parse_duration("30m", ctx="test")
        self.assertEqual(d.seconds, 30 * 60)

    def test_hours(self):
        d = _parse_duration("2h", ctx="test")
        self.assertEqual(d.seconds, 2 * 3600)

    def test_seconds(self):
        d = _parse_duration("90s", ctx="test")
        self.assertEqual(d.seconds, 90)

    def test_milliseconds(self):
        d = _parse_duration("500ms", ctx="test")
        self.assertEqual(d.seconds, 0)
        self.assertGreater(d.nanos, 0)

    def test_invalid_format_raises(self):
        with self.assertRaises((ValueError, Exception)):
            _parse_duration("xyz", ctx="test")

    def test_empty_raises(self):
        with self.assertRaises((ValueError, Exception)):
            _parse_duration("", ctx="test")

    def test_zero_duration(self):
        d = _parse_duration("0s", ctx="test")
        self.assertEqual(d.seconds, 0)


class TestParseTimeOfDay(unittest.TestCase):
    def test_hhmm(self):
        result = _parse_time_of_day("09:30", ctx="test")
        self.assertIsNotNone(result)

    def test_hhmmss(self):
        result = _parse_time_of_day("14:30:45", ctx="test")
        self.assertIsNotNone(result)

    def test_midnight(self):
        result = _parse_time_of_day("00:00", ctx="test")
        self.assertIsNotNone(result)

    def test_end_of_day(self):
        result = _parse_time_of_day("23:59", ctx="test")
        self.assertIsNotNone(result)

    def test_invalid_format_raises(self):
        with self.assertRaises((ValueError, Exception)):
            _parse_time_of_day("noon", ctx="test")

    def test_invalid_hour_raises(self):
        with self.assertRaises((ValueError, Exception)):
            _parse_time_of_day("25:00", ctx="test")

    def test_invalid_minute_raises(self):
        with self.assertRaises((ValueError, Exception)):
            _parse_time_of_day("12:60", ctx="test")


class TestParseDailyWindow(unittest.TestCase):
    def test_full_day(self):
        result = _parse_daily_window("00:00-23:59", ctx="test")
        self.assertIsNotNone(result)

    def test_business_hours(self):
        result = _parse_daily_window("09:00-17:00", ctx="test")
        self.assertIsNotNone(result)

    def test_invalid_format_raises(self):
        with self.assertRaises((ValueError, Exception)):
            _parse_daily_window("not-a-window", ctx="test")


class TestParseRuntimePolicy(unittest.TestCase):
    def test_interval_basic(self):
        config = {
            "type": "interval",
            "interval": {"duration": "30m"},
        }
        policy = parse_runtime_policy(config)
        self.assertTrue(policy.HasField("interval"))

    def test_always(self):
        config = {"type": "always"}
        policy = parse_runtime_policy(config)
        self.assertTrue(policy.HasField("always"))

    def test_times_basic(self):
        config = {
            "type": "times",
            "times": {"run_times": ["09:00", "18:00"]},
        }
        policy = parse_runtime_policy(config)
        self.assertTrue(policy.HasField("times"))

    def test_interval_with_daily_window(self):
        config = {
            "type": "interval",
            "interval": {
                "duration": "1h",
                "schedule": {"daily_window": "08:00-22:00"},
            },
        }
        policy = parse_runtime_policy(config)
        self.assertTrue(policy.HasField("interval"))

    def test_missing_type_raises(self):
        with self.assertRaises((ValueError, KeyError)):
            parse_runtime_policy({})

    def test_unknown_type_raises(self):
        with self.assertRaises((ValueError, KeyError)):
            parse_runtime_policy({"type": "cron"})
