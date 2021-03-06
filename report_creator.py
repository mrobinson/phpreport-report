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
#

import datetime
import enum
import itertools
import re
import textwrap

from dateutils import DateUtils
from phpreport import PHPReport
from phpreport import TaskFilter

class PeriodOfWork():
    def __init__(self, start_date, num_days, task_filter=TaskFilter(), tasks=None):
        self.start_date = start_date
        self.num_days = num_days
        self.users = set()
        self.tasks = tasks
        self.task_filter = task_filter.create_same_filter_with_different_dates(
            self.start_date,
            DateUtils.from_date_offset(self.start_date, num_days - 1))

    def get_users(self):
        return self.users

    def set_tasks(self, tasks):
        self.tasks = []
        for task in tasks:
            self.add_task(task)

    def add_task(self, task):
        self.tasks.append(task)
        self.users.add(task.user)

    def add_task_if_starts_in_period(self, task):
        ending_date = DateUtils.from_date_offset(self.start_date, self.num_days)
        if task.date < self.start_date:
            return False
        if task.date >= ending_date:
            return False
        self.add_task(task)
        return True

    def filter_tasks(self, date=None, day_offset=None,
                     user=None, only_onsite=False):
        if date is None and day_offset is not None:
            date = DateUtils.from_date_offset(self.start_date, day_offset)

        def filter_task(task):
            if user is not None and task.user != user:
                return False
            if date is not None and not DateUtils.same_date(task.date, date):
                return False
            if only_onsite and not task.onsite:
                return False
            return True
        return list(filter(filter_task, self.tasks))

    def get_all_dates(self):
        return [DateUtils.from_date_offset(self.start_date, offset)
                for offset in range(0, self.num_days)]

    def time_worked(self, date=None, day_offset=None,
                    user=None, only_onsite=False):
        return sum([task.length() for task in
                    self.filter_tasks(date, day_offset, user, only_onsite)],
                   datetime.timedelta())

    @staticmethod
    def fetch_tasks_for_all(periods):
        filters = [period.task_filter for period in periods]
        tasks = PHPReport.get_tasks_for_task_filters(filters)
        for pair in zip(periods, tasks):
            pair[0].set_tasks(pair[1])


class WeekOfWork(PeriodOfWork):
    def __init__(self, year, week, task_filter=TaskFilter(), tasks=None):
        self.week = week
        self.year = year
        date = DateUtils.from_week_number(year, week)
        super(WeekOfWork, self).__init__(date, 7, task_filter, tasks)

    def __str__(self):
        return "Week %i of %i" % (self.week, self.year)

    def short_string(self):
        return "Week {}/{} ".format(self.week, self.year)

    def wiki_string(self):
        return "Week%i-%i" % (self.week, self.year)

    @classmethod
    def create_array_of_weeks_between_dates(cls, start, end, task_filter):
        week_dates = DateUtils.get_weeks_in_date_range(start, end)
        weeks = [cls(*DateUtils.year_and_week_number(week_date),
                     task_filter=task_filter, tasks=[]) for week_date in week_dates]
        return weeks

    @classmethod
    def create_from_string(cls, string, task_filter):
        dates = DateUtils.date_range_from_string(string)
        weeks = cls.create_array_of_weeks_between_dates(dates[0], dates[1],
                                                        task_filter)

        cls.fetch_tasks_for_all(weeks)

        return weeks

    @classmethod
    def create_for_entire_project(cls, task_filter):
        assert task_filter.project

        tasks = PHPReport.get_tasks_for_task_filters([task_filter])
        tasks = [item for sublist in tasks for item in sublist]
        if not tasks:
            return []

        first_date = last_date = tasks[0].date
        for task in tasks[1:]:
            if task.date < first_date:
                first_date = task.date
            if task.date > last_date:
                last_date = task.date

        weeks = cls.create_array_of_weeks_between_dates(first_date, last_date,
                                                        task_filter)

        def add_task_to_weeks(task):
            for week in weeks:
                if week.add_task_if_starts_in_period(task):
                    return
            raise Exception("Could not assign task to week.")

        for task in tasks:
            add_task_to_weeks(task)

        return weeks


class AggregateReport():
    def __init__(self, time_periods, formatter, header, wiki_string):
        self.header = header
        self.wiki_string = wiki_string
        self.time_periods = time_periods
        self.formatter = formatter
        self.parent = None

    @staticmethod
    def generate_report_for_period(period, table_contents):
        amount = period.time_worked()
        amount_onsite = period.time_worked(only_onsite=True)

        hours_worked_string = DateUtils.format_delta_as_hours(amount)
        if amount_onsite:
            hours_worked_string += " (%s onsite)" % \
                    DateUtils.format_delta_as_hours(amount_onsite)

        table_contents.append([period.short_string(), hours_worked_string])
        return (amount, amount_onsite)

    def generate_report(self):
        self.formatter.generate_header(self.header)

        table_contents = []
        total = datetime.timedelta()
        total_onsite = datetime.timedelta()
        for period in self.time_periods:
            (time, time_onsite) = AggregateReport.generate_report_for_period(period, table_contents)
            total += time
            total_onsite += time_onsite

        self.formatter.generate_table(table_contents, has_headers=False)

        self.formatter.generate_header(
            "Total hours worked: %s" % DateUtils.format_delta_as_hours(total))
        self.formatter.generate_header(
            "Total onsite hours worked: %s" % DateUtils.format_delta_as_hours(total_onsite))
        return self.formatter.flatten()


class DetailedReport():
    def __init__(self, time_period, parent, formatter, include_story=True):
        if parent:
            header = "{0} for {1}".format(time_period, parent.header)
            wiki_string = "{0}-{1}".format(parent.wiki_string, time_period.wiki_string())
        else:
            header = "{0} for {1}".format(time_period, str(time_period.task_filter))
            wiki_string = time_period.wiki_string()

        self.header = header
        self.wiki_string = wiki_string
        self.time_period = time_period
        self.formatter = formatter
        self.parent = parent
        self.include_story = include_story
        self.pieces = []

    @staticmethod
    def format_date(date):
        return date.strftime("%d %b")

    def time_worked(self, user=None, total=False):
        if total:
            return [DateUtils.format_delta_as_hours(self.time_period.time_worked(user=user))]
        all_dates = self.time_period.get_all_dates()
        return [DateUtils.format_delta_as_hours(self.time_period.time_worked(date=x, user=user)) for x in all_dates]

    def generate_hours(self):
        table = []
        table.append([""] + list(map(DetailedReport.format_date, self.time_period.get_all_dates())) + ["Total"])
        for user in sorted(self.time_period.get_users()):
            table.append([user.login] +
                         self.time_worked(user=user) +
                         self.time_worked(user=user, total=True))
        table.append(["everyone"] +
                     self.time_worked() +
                     self.time_worked(total=True))
        self.formatter.generate_table(table)

        onsite_time = self.time_period.time_worked(only_onsite=True)
        if onsite_time > datetime.timedelta(0):
            self.formatter.generate_large_text("Onsite hours worked: %s" % DateUtils.format_delta_as_hours(onsite_time))

    def get_stories_for_day_and_user(self, user, date):
        tasks_for_day = self.time_period.filter_tasks(date=date, user=user)

        def get_story(task):
            story = ""
            if self.include_story:
                story += self.formatter.format_story(task.story)
            if story:
                story += " "
            return story

        all_stories = [get_story(task) + task.text for task in tasks_for_day]

        # Many times people add a lot of duplicate descriptions. Just output one of each.
        all_stories = set(all_stories)

        # Strip out duplicated whitespace
        return re.compile(r'\s+').sub(' ', " ".join(all_stories)).strip()

    def generate_stories_for_user(self, user):
        self.formatter.generate_section_header("Stories for %s" % user.login)

        all_dates = self.time_period.get_all_dates()
        contents = [(date.strftime("%A"), self.get_stories_for_day_and_user(user, date)) for date in all_dates]
        self.formatter.generate_aligned_list(contents)

    def generate_report(self):
        self.pieces = []
        self.formatter.generate_header(self.header)
        self.generate_hours()
        for user in sorted(self.time_period.users):
            self.generate_stories_for_user(user)
        return self.formatter.flatten()


class TextFormatter():
    def __init__(self):
        self.pieces = []

    def generate_table_row(self, columns, lengths, header=False):
        format_string = ""
        for length in lengths:
            format_string += "%%-%i.%is  " % (length, length)
        self.pieces.append(format_string % tuple(columns))
        self.pieces.append("\n")

    @staticmethod
    def generate_column_length_list(table):
        lengths = [list(map(len, x)) for x in table]  # Generate a table of lengths.
        # Turn the table of lengths into a row of max lengths for each column.
        return list(map(max, list(zip(*lengths))))

    def generate_table(self, table, has_headers=True):
        if not table:
            return

        lengths = TextFormatter.generate_column_length_list(table)
        self.generate_table_row(table[0], lengths, header=has_headers)
        for row in table[1:]:
            self.generate_table_row(row, lengths)

    def generate_aligned_list(self, contents):
        first_column_size = max([len(content[0]) for content in contents])
        format_string = "%%%i.%is: %%s\n" % (first_column_size, first_column_size)

        indent = (first_column_size + 2) * ' '  # Enough to account for the day name offset.
        width = 80 - len(indent)
        for content in contents:
            second_column = textwrap.fill(content[1],
                                          break_long_words=False,  # Don't break URLs.
                                          width=width,
                                          initial_indent=indent,
                                          subsequent_indent=indent).strip()
            self.pieces.append(format_string % (content[0], second_column))

    def generate_header(self, header):
        self.pieces.append("\n%s\n" % header)

    def generate_section_header(self, header):
        self.pieces.append("\n%s\n" % header)

    def generate_large_text(self, text):
        self.pieces.append("%s\n" % text)

    @classmethod
    def format_story(cls, story):
        if story:
            return "[{}]".format(story)
        return ""

    def flatten(self):
        return "".join(self.pieces)


class TwikiFormatter(TextFormatter):
    def generate_table_row(self, columns, lengths=None, header=False, highlight_first=True):
        first = "| *%s* "
        if not highlight_first:
            first = "| %s"

        if header:
            format_string = first + (len(columns) - 2) * " | *%s*" + " | *%s* |"
        else:
            format_string = first + (len(columns) - 2) * " | %s" + " | %s |"

        self.pieces.append(format_string % tuple(columns))
        self.pieces.append("\n")

    def generate_table(self, table, has_headers=True):
        if len(table) < 10 or has_headers:
            return super(TwikiFormatter, self).generate_table(table, has_headers)

        def chunks_of_n(list_to_chunk, num_chunks):
            for i in range(0, len(list_to_chunk), num_chunks):
                yield list_to_chunk[i:i + num_chunks]

        def transpose_table(table):
            return list(map(list, itertools.zip_longest(*table, fillvalue=['', ''])))

        table = transpose_table(chunks_of_n(table, 10))
        for row in table:
            row = sum(row, [])
            self.generate_table_row(row, highlight_first=False)

    def generate_header(self, header):
        self.pieces.append("\n---++%s\n" % header)

    def generate_section_header(self, header):
        self.pieces.append("\n---++++%s\n" % header)

    def generate_aligned_list(self, contents):
        for content in contents:
            self.pieces.append("   * *%s* - %s\n" % (content[0], content[1]))


class MarkdownFormatter(TextFormatter):
    def generate_table(self, table, has_headers=True):
        return ""

    def generate_header(self, header):
        self.pieces.append("\n# %s\n" % header)

    def generate_section_header(self, header):
        self.pieces.append("\n## %s\n" % header)

    def generate_aligned_list(self, contents):
        self.pieces.append("\n")
        for content in contents:
            self.pieces.append(" * **%s** %s\n" % (content[0], content[1]))

    def format_story(self, story):
        if story:
            return "*{}*".format(story)
        return ""


class ReportCreator():
    class Mode(enum.Enum):
        PROJECT, AGGREGATE, DETAIL = range(3)

    def __init__(self, args):
        self.args = args
        self.task_filter = args.to_task_filter()

        if not args.time:
            self.time_periods = WeekOfWork.create_for_entire_project(self.task_filter)
            self.mode = ReportCreator.Mode.PROJECT

        elif args.time:
            self.time_periods = WeekOfWork.create_from_string(args.time, self.task_filter)
            if len(self.time_periods) > 1:
                self.mode = ReportCreator.Mode.AGGREGATE
            else:
                self.mode = ReportCreator.Mode.DETAIL

        self.parent_report = None
        self.reports = []

    def formatter(self):
        if self.args.formatter == "twiki":
            return TwikiFormatter()
        if self.args.formatter == "markdown":
            return MarkdownFormatter()
        return TextFormatter()

    def create_parent_report(self):
        if self.mode == ReportCreator.Mode.PROJECT:
            project = self.task_filter.project
            return AggregateReport(self.time_periods, self.formatter(),
                                   project.description,
                                   re.sub(r'[^a-zA-Z0-9]', '', project.description) + "Report")

        if self.mode == ReportCreator.Mode.AGGREGATE:
            return AggregateReport(self.time_periods, self.formatter(),
                                   "%s to %s for %s" %
                                   (self.time_periods[0],
                                    self.time_periods[-1],
                                    self.time_periods[0].task_filter),
                                   "%sTo%s" %
                                   (self.time_periods[0].wiki_string(),
                                    self.time_periods[-1].wiki_string()))
        return None

    def create_reports(self):
        self.parent_report = self.create_parent_report()

        for period in self.time_periods:
            self.reports.append(DetailedReport(time_period=period,
                                               parent=self.parent_report,
                                               formatter=self.formatter(),
                                               include_story=self.args.story))
