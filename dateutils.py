# pylint: disable=missing-docstring

# Copyright (C) 2019 Igalia S.L.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import datetime
import calendar
import re

FULL_DATE_REGEX = re.compile(r"^(\d\d?)/(\d\d?)/(\d\d\d\d)")
MONTH_REGEX = re.compile(r"^(\d\d?)/(\d\d\d\d)$")
WEEK_REGEX = re.compile(r"^w(\d\d?)/?(\d\d\d\d)?$", re.IGNORECASE)
QUARTER_REGEX = re.compile(r"^q([1,2,3,4])/?(\d\d\d\d)?$", re.IGNORECASE)
HALF_REGEX = re.compile(r"^h([1,2])/(\d\d\d\d)$", re.IGNORECASE)
YEAR_REGEX = re.compile(r"^(\d\d\d\d)$")


class DateUtils(datetime.date):
    @staticmethod
    def last_day_of_month(year, month):
        return calendar.monthrange(year, month)[1]

    @staticmethod
    def from_week_number(year, week, end=False):
        if week <= 0 or week > 53:
            raise ValueError("Could not parse date")

        week_as_string = "%i %i %i" % (year, week, 1)
        date = datetime.datetime.strptime(week_as_string, "%Y %W %w").date()

        # ISO8601 considers the first week of the year the first one that
        # contains a Thursday, but strptime does not. We need to account
        # for that.
        if datetime.date(year, 1, 4).isoweekday() > 4:
            date -= datetime.timedelta(days=7)

        if end:
            date += datetime.timedelta(days=6)

        # We clear any time component here so that we return a standard date.
        return datetime.datetime(date.year, date.month, date.day)

    @staticmethod
    def from_quarter_number(year, quarter, end=False):
        if end:
            month = (quarter * 3)
            return datetime.datetime(year, month,
                                     DateUtils.last_day_of_month(year, month))
        month = ((quarter - 1) * 3) + 1
        return datetime.datetime(year, month, 1)

    @staticmethod
    def from_half_number(year, half, end=False):
        if end:
            month = (half * 6)
            return datetime.datetime(year, month,
                                     DateUtils.last_day_of_month(year, month))
        month = ((half - 1) * 6) + 1
        return datetime.datetime(year, month, 1)

    @staticmethod
    def from_year(year, end=False):
        if end:
            return datetime.datetime(year, 12,
                                     DateUtils.last_day_of_month(year, 12))
        return datetime.datetime(year, 1, 1)

    @staticmethod
    def from_date_offset(date, day_offset):
        return date + datetime.timedelta(day_offset)

    @staticmethod
    def year_and_week_number(date):
        return date.isocalendar()[:2]

    @classmethod
    def monday(cls, date):
        return cls.from_week_number(*cls.year_and_week_number(date))

    @classmethod
    def next_week(cls, date):
        return cls.from_date_offset(date, 7)

    @classmethod
    def get_weeks_in_date_range(cls, start, end):
        week = start = cls.monday(start)
        end = cls.monday(end)

        weeks = []
        while week <= end:
            weeks.append(week)
            week = cls.next_week(week)
        return weeks

    @staticmethod
    def same_date(date_a, date_b):
        return date_a.year == date_b.year and \
            date_a.month == date_b.month and \
            date_a.day == date_b.day

    @staticmethod
    def format_delta(delta):
        hours = (delta.days * 24) + (delta.seconds // 3600)
        seconds = (delta.seconds // 60) % 60
        return "%02i:%02i" % (hours, seconds)

    @staticmethod
    def date_from_string(string):
        match = FULL_DATE_REGEX.match(string)
        current_year = datetime.datetime.now().year
        if match:
            date = datetime.datetime(int(match.group(3)),
                                     int(match.group(2)),
                                     int(match.group(1)))
            return [date, date]

        match = MONTH_REGEX.match(string)
        if match:
            month = int(match.group(1))
            year = int(match.group(2))
            last_day_of_month = DateUtils.last_day_of_month(year, month)
            return [datetime.datetime(year, month, 1),
                    datetime.datetime(year, month, last_day_of_month)]

        match = WEEK_REGEX.match(string)
        if match:
            week_number = int(match.group(1))
            year = int(match.group(2) or current_year)
            return [DateUtils.from_week_number(year, week_number),
                    DateUtils.from_week_number(year, week_number, end=True)]

        match = QUARTER_REGEX.match(string)
        if match:
            quarter = int(match.group(1))
            year = int(match.group(2) or current_year)
            return [DateUtils.from_quarter_number(year, quarter),
                    DateUtils.from_quarter_number(year, quarter, end=True)]

        match = HALF_REGEX.match(string)
        if match:
            half = int(match.group(1))
            year = int(match.group(2) or current_year)
            return [DateUtils.from_half_number(year, half),
                    DateUtils.from_half_number(year, half, end=True)]

        match = YEAR_REGEX.match(string)
        if match:
            year = int(match.group(1))
            return [DateUtils.from_year(year),
                    DateUtils.from_year(year, end=True)]

        raise ValueError("Could not parse date")

    @classmethod
    def date_range_from_string(cls, string):
        if "-" in string:
            date_strings = string.split("-")
            date1 = cls.date_from_string(date_strings[0].strip())
            date2 = cls.date_from_string(date_strings[1].strip())
            dates = [date1[0], date2[1]]
        else:
            dates = cls.date_from_string(string)
        dates.sort()
        return dates
