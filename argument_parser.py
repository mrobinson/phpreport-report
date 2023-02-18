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

import argparse
import sys

from phpreport import Customer
from phpreport import TaskFilter
from phpreport import Project
from phpreport import User

class ArgumentParser(argparse.ArgumentParser):
    def __init__(self):
        super().__init__()
        self.add_argument('-l', '--login', type=str,
                          help="login name for PHPReport and TWiki")
        self.add_argument('-p', '--project', type=str,
                          help="only consider tasks matching given project search string")
        self.add_argument('-c', '--customer', type=str,
                          help="only consider tasks matching given customer search string")
        self.add_argument('-u', '--user', type=str,
                          help="only consider tasks logged by the given user")
        self.add_argument('--task-type', dest='task_type', type=str,
                          help="only consider tasks with the given task type")

        # TODO: -w and --week are maintained for backward compatibility. Eventually
        # we should just remove them.
        self.add_argument('-t', '--time', '-w', '--week', type=str, default=None,
                          help="Time range to use for the report. Can be a single time or a range.")

        self.add_argument('-f', '--formatter', choices=['text', 'twiki', 'markdown'],
                          default="text", help="output format for report")
        self.add_argument('--no-story', action='store_false', dest='story',
                          help="Do not include the story tag in the output")

    def parse(self, *args, **kwargs):
        args = ParsedArguments(super().parse_args(*args, **kwargs))
        if not args.project and not args.customer and not args.user and not args.task_type:
            print("Must give either a customer (-c) search string,"
                  " product search string (-p) or task type (--task_type).")
            sys.exit(1)

        if not args.time and not args.project:
            print("Must give either a project (-p), time range (-t),"
                  " or task type (--task-type).")
            sys.exit(1)
        return args


class ParsedArguments():
    def __init__(self, args):
        self.args = args

    def __getattr__(self, name):
        return getattr(self.args, name)

    def to_task_filter(self):
        customer = None
        project = None
        user = None

        def filter_instances(instances, search_string):
            terms = search_string.lower().split(',')

            def matches_all(instance):
                for term in terms:
                    if not instance.match(term):
                        return False
                return True
            return list(filter(matches_all, instances))

        # TODO: We should really support choosing selecting more than one
        # customer or project.
        if self.project is not None:
            projects = filter_instances(list(Project.all()), self.project)
            if not projects:
                print("Could not find any projects matching '%s'" % self.project)
                sys.exit(1)
            elif len(projects) > 1:
                projects.sort(reverse=True)
                project = choose_from_list(projects)
            else:
                project = projects[0]

        if self.customer is not None:
            customers = filter_instances(list(Customer.all()), self.customer)
            if not customers:
                print("Could not find any customers matching '%s'" % self.customer)
                sys.exit(1)
            elif len(customers) > 1:
                customer = choose_from_list(customers)
            else:
                customer = customers[0]

        if self.user is not None:
            users = [x for x in User.all() if x.login == self.user]
            print(users)
            if not users:
                print("Could not find any users matching '%s'" % self.user)
                sys.exit(1)
            elif len(users) > 1:
                user = choose_from_list(users)
            else:
                user = users[0]

        return TaskFilter(project=project, customer=customer, user=user, task_type=self.task_type)

def choose_from_list(items):
    assert len(items) > 1

    print("\nMultiple {0}s matching description. Please choose one:".format(items[0].__class__.__name__.lower()))
    for index, item in enumerate(items):
        print("    {0}. {1}".format(index, item))

    while True:
        try:
            index = int(input(">> "))
            if 0 <= index < len(items):
                return items[index]
        except ValueError:
            pass

        print("Not a valid index. Type a number between 0 and {0} and press enter.".format(len(items) - 1))
