from datetime import date
from unittest import TestCase

from quintet.broker.ibkr.calendar import parse_next_rth_day


class IbkrCalendarTests(TestCase):
    def test_parse_next_rth_day_reads_first_liquid_hours_segment(self) -> None:
        liquid_hours = (
            "20260618:CLOSED;"
            "20260619:0830-20260619:1500;"
            "20260622:0830-20260622:1500"
        )

        self.assertEqual(parse_next_rth_day(liquid_hours), date(2026, 6, 19))

    def test_parse_next_rth_day_returns_none_when_unparseable(self) -> None:
        self.assertIsNone(parse_next_rth_day("20260618:CLOSED"))
