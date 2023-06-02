# Copyright (C) 2012, 2013 Igalia S.L.
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

from __future__ import annotations

import base64
from collections import defaultdict
import dataclasses
import datetime
import getpass
import http.client
import multiprocessing
import sys
import urllib.error
import urllib.request

from typing import Any, ClassVar, Dict, Optional, Type
from xml.etree import ElementTree

import keyring

KEYRING_SERVICE_NAME = "PHPReport"
DEFAULT_PHPREPORT_ADDRESS = "https://phpreport.igalia.com/web/services"
URLS_TO_FETCH_IN_PARALLEL = 10
DEFAULT_DATE = datetime.datetime(1970, 1, 1)
http.client.HTTPConnection.debuglevel = 0


@dataclasses.dataclass()
class Credential:
    all_credentials: ClassVar[Dict[str, Credential]] = dataclasses.field(default={})
    password_manager: ClassVar[Optional[urllib.request.HTTPPasswordMgrWithDefaultRealm]] = None
    url: str
    username: str
    password: str
    saved: bool = False

    @classmethod
    def for_url(cls, url: str, username=None):
        username_and_password = keyring.get_password(KEYRING_SERVICE_NAME, url)
        if username_and_password:
            (username, password) = username_and_password.split(":", 1)
            return Credential(url, username, password, True)

        if url in cls.all_credentials:
            return cls.all_credentials[url]

        if not username:
            username = input("Username: ")
        password = getpass.getpass("Password: ")
        return Credential(url=url, username=username, password=password, saved=False)

    def __post_init__(self):
        self.all_credentials[self.url] = self

    def save(self):
        if self.saved:
            return
        if input(f"Store password for '{self.username}' in keyring? (y/N) ") != "y":
            return
        keyring.set_password(
            KEYRING_SERVICE_NAME, self.url, f"{self.username}:{self.password}"
        )

    def activate(self):
        cls = type(self)
        if cls.password_manager:
            cls.password_manager.add_password(
                None, self.url, self.username, self.password
            )
            return

        cls.password_manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        urllib.request.install_opener(
            urllib.request.build_opener(
                urllib.request.HTTPBasicAuthHandler(cls.password_manager)
            )
        )
        self.activate()

    def __eq__(self, other):
        return self.url == other.url and self.username == other.username


class PHPReportObject:
    instances: Dict[Type, Dict[int, PHPReportObject]] = defaultdict(dict)

    def __init__(self, phpreport_id: int = -1):
        PHPReportObject.instances[type(self)][phpreport_id] = self

    @classmethod
    def all(cls):
        return PHPReportObject.instances[cls].values()

    @classmethod
    def find(cls, phpreport_id: int):
        instances = PHPReportObject.instances[cls]
        if phpreport_id == -1 and -1 not in instances:
            cls() # Create the placeholder value.
        return instances[phpreport_id]

    @classmethod
    def from_element(cls, _: ElementTree.Element) -> PHPReportObject:
        assert False, "Subclasses should override this abstract class method."


@dataclasses.dataclass(frozen=True, eq=True)
class Task(PHPReportObject):
    phpreport_id: int = -1
    user_id: int = -1
    user: User = dataclasses.field(init=False)
    project_id: int = -1
    project: Project = dataclasses.field(init=False)
    text: str = ""
    story: str = ""
    ttype: str = ""
    phase: str = ""
    date: datetime.date = dataclasses.field(default=DEFAULT_DATE.date())
    init_time: datetime.datetime = dataclasses.field(default=DEFAULT_DATE)
    end_time: datetime.datetime = dataclasses.field(default=DEFAULT_DATE)
    onsite: bool = False
    telework: bool = False

    def __post_init__(self):
        super().__init__(self.phpreport_id)
        object.__setattr__(self, "user", User.find(self.user_id))
        object.__setattr__(self, "project", Project.find(self.project_id))

        # There's a bug in PHPReport where 0:00 can be considered 24:00 when it's
        # used as the end time. Work around that now:
        # https://trac.phpreport.igalia.com/ticket/193
        if self.end_time.hour == 0 and self.end_time.minute == 0:
            # We don't want to do this for the special PHPReport zero-hour tasks which
            # are reported as being from 0:00 to 0:00. These tasks should remain listed
            # as zero hours long.
            if not (self.init_time.hour == 0 and self.end_time.minute == 0):
                object.__setattr__(self, "end_time",
                                   self.end_time + datetime.timedelta(hours=24))

    @classmethod
    def from_element(cls, task_xml: ElementTree.Element):
        data: Dict[str, Any] = {child.tag: child.text for child in task_xml if child.text}
        if "date" in data:
            data["date"] = datetime.datetime.strptime(data["date"], "%Y-%m-%d").date()
        def make_time(data, key):
            if key in data:
                data[key] = datetime.datetime.combine(
                    data.get("date", DEFAULT_DATE.date()),
                    datetime.datetime.strptime(data[key], "%H:%M").time()
                )
        make_time(data, "initTime")
        make_time(data, "endTime")

        return cls(
            phpreport_id=int(data.get("id", "-1")),
            user_id=int(data.get("userId", "-1")),
            project_id=int(data.get("projectId", "-1")),
            ttype=data.get("ttype", ""),
            story=data.get("story", ""),
            text=data.get("text", ""),
            phase=data.get("phase", ""),
            date=data.get("date", DEFAULT_DATE.date()),
            init_time=data.get("initTime", DEFAULT_DATE),
            end_time=data.get("endTime", DEFAULT_DATE),
            onsite=data.get("onsite", "") == "true",
            telework=data.get("telework", "") == "true"
        )

    def length(self):
        return self.end_time - self.init_time


@dataclasses.dataclass(frozen=True, eq=True)
class Project(PHPReportObject):
    phpreport_id: int = -1
    description: str = "<description>"
    customer_id: int = -1
    customer: Customer = dataclasses.field(init=False)
    init_date: datetime.date = DEFAULT_DATE.date()
    end_date: datetime.date = DEFAULT_DATE.date()

    def __post_init__(self):
        super().__init__(self.phpreport_id)
        object.__setattr__(self, "customer", Customer.find(self.customer_id))

    @classmethod
    def from_element(cls, project_xml: ElementTree.Element) -> Project:
        data: Dict[str, Any] = {}
        for child in project_xml:
            if child.text and child.tag in ("init", "end"):
                data[child.tag] = datetime.datetime.strptime(child.text, "%Y-%m-%d").date()
            elif child.text:
                data[child.tag] = child.text

        return cls(
            phpreport_id=int(data.get("id", "-1")),
            description=data.get("description", "<description>"),
            customer_id=int(data.get("customerId", "-1")),
            init_date=data.get("init", DEFAULT_DATE.date()),
            end_date=data.get("end", DEFAULT_DATE.date())
        )

    def __str__(self):
        return self.description

    def match(self, term):
        return self.description.lower().find(term) != -1

    def has_ended(self):
        return self.end_date and self.end_date < datetime.date.today()

    def __lt__(self, other):
        if self.has_ended() and not other.has_ended():
            return True
        if other.has_ended() and not self.has_ended():
            return False
        if self.init_date and other.init_date:
            return self.init_date < other.init_date
        return self.phpreport_id < other.phpreport_id


@dataclasses.dataclass(frozen=True, eq=True)
class User(PHPReportObject):
    phpreport_id: int = -1
    login: str = "<unknown>"

    def __post_init__(self):
        super().__init__(self.phpreport_id)

    @classmethod
    def from_element(cls, user_xml: ElementTree.Element) -> User:
        data = {child.tag: child.text for child in user_xml if child.text}
        return cls(
            phpreport_id=int(data.get("id", "-1")),
            login=data.get("login", "-1")
        )

    def __hash__(self):
        return self.phpreport_id.__hash__()

    def __str__(self):
        return self.login

    def __lt__(self, other):
        return self.login < other.login

    def match(self, term):
        return self.login.lower().find(term) != -1


@dataclasses.dataclass(frozen=True, eq=True)
class Customer(PHPReportObject):
    phpreport_id: int = -1
    name: str = "<unknown>"

    def __post_init__(self):
        super().__init__(self.phpreport_id)

    @classmethod
    def from_element(cls, customer_xml: ElementTree.Element) -> Customer:
        data = {child.tag: child.text for child in customer_xml if child.text}
        return cls(
            phpreport_id=int(data.get("id", "-1")),
            name=data.get("name", "-1")
        )

    def __str__(self):
        return self.name

    def match(self, term):
        return self.name.lower().find(term) != -1


def get_url_contents(url):
    return PHPReport.get_contents_of_url(url)


def fetch_urls_in_parallel(urls):
    pool = multiprocessing.Pool(processes=URLS_TO_FETCH_IN_PARALLEL)
    return pool.map(get_url_contents, urls)


class PHPReport:
    users: Dict[int, User] = {}
    projects: Dict[int, Project] = {}
    customers: Dict[int, Customer] = {}

    @classmethod
    def get_contents_of_url(cls, url):
        def sanitize_url_for_display(url):
            return url.replace(cls.credential.password, "<<<your password>>>")

        request = urllib.request.Request(url, None)
        try:
            return urllib.request.urlopen(request).read()
        except urllib.error.URLError:
            print(f"Could not complete request to {sanitize_url_for_display(url)}")
            sys.exit(1)

    @classmethod
    def send_login_request(cls, address, username, password):
        url = f"{address}/loginService.php"
        request = urllib.request.Request(url, None)
        auth_string = bytes(f"{username}:{password}", "UTF-8")
        request.add_header("Authorization", f"Basic {base64.b64encode(auth_string)}")
        try:
            return urllib.request.urlopen(request).read()
        except urllib.error.URLError:
            print(f"Could not complete login request to {url}")
            sys.exit(1)

    @classmethod
    def login(cls, address=DEFAULT_PHPREPORT_ADDRESS, username=None):
        cls.address = address
        cls.credential = Credential.for_url(address, username)
        cls.credential.activate()

        print("Logging in...")
        response = cls.send_login_request(
            cls.address, cls.credential.username, cls.credential.password
        )

        cls.session_id = None
        tree = ElementTree.fromstring(response)
        for child in tree:
            if child.tag == "sessionId":
                cls.session_id = child.text

        if not cls.session_id:
            print("Could not find session id in login response, "
                  f"password likely incorrect: {response}"
            )
            sys.exit(1)

        cls.credential.save()

        # Use multiprocessing to access all URLs at once to reduce the latency of starting up.
        print("Loading PHPReport data...")
        responses = fetch_urls_in_parallel(
            [
                f"{cls.address}/getProjectsService.php?sid={PHPReport.session_id}",
                f"{cls.address}/getAllUsersService.php?sid={PHPReport.session_id}",
                f"{cls.address}/getUserCustomersService.php?sid={PHPReport.session_id}"
            ]
        )

        PHPReport.create_objects_from_response(responses[2], Customer, "customer")
        PHPReport.create_objects_from_response(responses[1], User, "user")
        PHPReport.create_objects_from_response(responses[0], Project, "project")

    @staticmethod
    def create_objects_from_response(response, cls, tag):
        element = ElementTree.fromstring(response)
        return [
            cls.from_element(child) for child in element if child.tag == tag
        ]

    @classmethod
    def get_tasks_for_task_filters(cls, task_filters):
        print("Fetching tasks...")
        responses = fetch_urls_in_parallel(
            [task_filter.to_url(cls) for task_filter in task_filters]
        )
        return [cls.create_objects_from_response(x, Task, "task") for x in responses]

    @classmethod
    def get_tasks_for_task_filter(cls, task_filter):
        contents = PHPReport.get_contents_of_url(task_filter.to_url(cls))
        return cls.create_objects_from_response(contents, Task, "task")


class TaskFilter:
    def __init__(self, project=None, customer=None, user=None, task_type=None):
        self.project = project
        self.customer = customer
        self.user = user
        self.task_type = task_type
        self.start_date = None
        self.end_date = None

    @classmethod
    def from_dates(cls, start_date, end_date):
        task_filter = TaskFilter()
        task_filter.start_date = start_date
        task_filter.end_date = end_date
        return task_filter

    def __str__(self):
        if self.project:
            return self.project.description
        if self.customer:
            return self.customer.name
        return self.user.login

    def create_same_filter_with_different_dates(self, start_date, end_date):
        task_filter = TaskFilter(
            project=self.project,
            customer=self.customer,
            user=self.user,
            task_type=self.task_type
        )
        task_filter.start_date = start_date
        task_filter.end_date = end_date
        return task_filter

    def to_url(self, phpreport):
        url = (
            f"{phpreport.address}/getTasksFiltered.php" 
            f"?sid={phpreport.session_id}&dateFormat=Y-m-d"
        )
        if self.start_date:
            url += f"&filterStartDate={self.start_date.strftime('%Y-%m-%d')}"
        if self.end_date:
            url += f"&filterEndDate={self.end_date.strftime('%Y-%m-%d')}"
        if self.project is not None:
            url += f"&projectId={self.project.phpreport_id}"
        if self.customer is not None:
            url += f"&customerId={self.customer.phpreport_id}"
        if self.user is not None:
            url += f"&userId={self.user.phpreport_id}"
        if self.task_type is not None:
            url += f"&type={self.task_type}"
        return url
