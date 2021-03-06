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

import multiprocessing
import sys
import urllib.error
import urllib.request
from xml.etree import ElementTree

import base64
import datetime
import getpass
import http.client
import keyring

KEYRING_SERVICE_NAME = "PHPReport"
DEFAULT_PHPREPORT_ADDRESS = "https://phpreport.igalia.com/web/services"
URLS_TO_FETCH_IN_PARALLEL = 10
http.client.HTTPConnection.debuglevel = 0


class Credential():
    all_credentials = {}
    password_manager = None

    @classmethod
    def for_url(cls, url, username=None):
        username_and_password = keyring.get_password(KEYRING_SERVICE_NAME, url)
        if username_and_password:
            (username, password) = username_and_password.split(':', 1)
            return Credential(url, username, password, True)

        if url in cls.all_credentials:
            return cls.all_credentials[url]

        if not username:
            username = input("Username: ")
        password = getpass.getpass("Password: ")
        return Credential(url, username, password, False)

    def __init__(self, url, username, password, saved=False):
        self.url = url
        self.username = username
        self.password = password
        self.saved = saved
        self.all_credentials[self.url] = self

    def save(self):
        if self.saved:
            return
        if input("Store password for '%s' in keyring? (y/N) " % self.username) != 'y':
            return
        keyring.set_password(KEYRING_SERVICE_NAME, self.url,
                             "{}:{}".format(self.username, self.password))

    def activate(self):
        cls = type(self)
        if cls.password_manager:
            cls.password_manager.add_password(None, self.url, self.username, self.password)
            return

        cls.password_manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        urllib.request.install_opener(urllib.request.build_opener(
            urllib.request.HTTPBasicAuthHandler(cls.password_manager)))
        self.activate()

    def __eq__(self, other):
        return self.url == other.url and self.username == other.username


class PHPReportObject():
    @classmethod
    def find(cls, phpreport_id):
        return cls.instances[phpreport_id]

    @classmethod
    def load_all(cls, data, tag):
        instances = PHPReport.create_objects_from_response(data, cls, tag)

        cls.instances = {}
        cls.instances[-1] = cls(None)
        for instance in instances:
            cls.instances[instance.phpreport_id] = instance

    @staticmethod
    def id_string_to_integer(string):
        if not string:
            return -1
        return int(string)


class Task(PHPReportObject):
    # pylint: disable=too-many-instance-attributes,too-many-branches
    def __init__(self, task_xml):
        self.text = ""
        self.story = ""

        # These might be empty.
        self.project_id = None
        self.project = None
        self.onsite = False
        self.telework = False

        if not task_xml:
            self.phpreport_id = -1
            self.type = ""
            self.date = self.init_time = self.end_time = datetime.datetime(1970, 1, 1)
            self.project = Project.find(-1)
            return

        for child in task_xml:
            if child.tag == "id":
                self.phpreport_id = int(child.text)
            elif child.tag == "ttype":
                self.type = child.text
            elif child.tag == "date":
                self.date = datetime.datetime.strptime(child.text, "%Y-%m-%d").date()
            elif child.tag == "initTime":
                self.init_time = datetime.datetime.strptime(child.text, "%H:%M")
            elif child.tag == "endTime":
                self.end_time = datetime.datetime.strptime(child.text, "%H:%M")

                # There's a bug in PHPReport where 0:00 can be considered 24:00 when it's
                # used as the end time. Work around that now:
                # https://trac.phpreport.igalia.com/ticket/193
                if self.end_time.hour == 0 and self.end_time.minute == 0:
                    self.end_time += datetime.timedelta(hours=24)

            elif child.tag == "story" and child.text is not None:
                self.story = child.text
            elif child.tag == "text" and child.text is not None:
                self.text = child.text
            elif child.tag == "phase":
                self.phase = child.text
            elif child.tag == "userId":
                self.user_id = PHPReportObject.id_string_to_integer(child.text)
                self.user = User.find(self.user_id)
            elif child.tag == "projectId" and child.text:
                self.project_id = PHPReportObject.id_string_to_integer(child.text)
                self.project = Project.find(self.project_id)
            elif child.tag == "customerId":
                self.customer_id = PHPReportObject.id_string_to_integer(child.text)
            elif child.tag == "taskStoryId":
                self.task_story_id = child.text
            elif child.tag == "telework" and child.text == "true":
                self.telework = True
            elif child.tag == "onsite" and child.text == "true":
                self.onsite = True

    def length(self):
        return self.end_time - self.init_time


class Project(PHPReportObject):
    def __init__(self, project_xml):
        self.init_date = None
        self.end_date = None

        if not project_xml:
            self.phpreport_id = -1
            self.description = "<unknown>"
            self.customer_id = -1
            self.customer = Customer.find(-1)
            self.init_date = self.end_date = datetime.datetime(1970, 1, 1)
            return

        for child in project_xml:
            if child.tag == "id":
                self.phpreport_id = int(child.text)
            if child.tag == "customerId":
                self.customer_id = PHPReportObject.id_string_to_integer(child.text)
                self.customer = Customer.find(self.customer_id)
            if child.tag == "description":
                self.description = child.text
            if child.tag == "initDate" and child.text:
                self.init_date = datetime.datetime.strptime(child.text, "%Y-%m-%d").date()
            if child.tag == "endDate" and child.text:
                self.end_date = datetime.datetime.strptime(child.text, "%Y-%m-%d").date()


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


class User(PHPReportObject):
    def __init__(self, user_xml):
        if not user_xml:
            self.phpreport_id = -1
            self.login = "<unknown>"
            return

        for child in user_xml:
            if child.tag == "id":
                self.phpreport_id = int(child.text)
            if child.tag == "login":
                self.login = child.text

    def __str__(self):
        return self.login

    def __lt__(self, other):
        return self.login < other.login

    def match(self, term):
        return self.login.lower().find(term) != -1


class Customer(PHPReportObject):
    def __init__(self, customer_xml):
        if not customer_xml:
            self.phpreport_id = -1
            self.name = "<unknown>"
            return

        for child in customer_xml:
            if child.tag == "id":
                self.phpreport_id = int(child.text)
            if child.tag == "name":
                self.name = child.text

    def __str__(self):
        return self.name

    def match(self, term):
        return self.name.lower().find(term) != -1


def get_url_contents(url):
    return PHPReport.get_contents_of_url(url)


def fetch_urls_in_parallel(urls):
    pool = multiprocessing.Pool(processes=URLS_TO_FETCH_IN_PARALLEL)
    return pool.map(get_url_contents, urls)


class PHPReport():
    users = {}
    projects = {}
    customers = {}

    @classmethod
    def get_contents_of_url(cls, url):
        def sanitize_url_for_display(url):
            return url.replace(cls.credential.password, "<<<your password>>>")

        request = urllib.request.Request(url, None)
        try:
            return urllib.request.urlopen(request).read()
        except urllib.error.URLError:
            print("Could not complete request to %s" % sanitize_url_for_display(url))
            sys.exit(1)

    @classmethod
    def send_login_request(cls, address, username, password):
        url = "%s/loginService.php" % address
        request = urllib.request.Request(url, None)
        auth_string = bytes('%s:%s' % (username, password), 'UTF-8')
        request.add_header("Authorization", "Basic %s" % base64.b64encode(auth_string))
        try:
            return urllib.request.urlopen(request).read()
        except urllib.error.URLError:
            print("Could not complete login request to %s" % url)
            sys.exit(1)

    @classmethod
    def login(cls, address=DEFAULT_PHPREPORT_ADDRESS, username=None):
        cls.address = address
        cls.projects = {}
        cls.credential = Credential.for_url(address, username)
        cls.credential.activate()

        print("Logging in...")
        response = cls.send_login_request(cls.address, cls.credential.username, cls.credential.password)

        cls.session_id = None
        tree = ElementTree.fromstring(response)
        for child in tree:
            if child.tag == "sessionId":
                cls.session_id = child.text

        if not cls.session_id:
            print("Could not find session id in login response, password likely incorrect: %s" % response)
            sys.exit(1)

        cls.credential.save()

        # Use multiprocessing to access all URLs at once to reduce the latency of starting up.
        print("Loading PHPReport data...")
        responses = fetch_urls_in_parallel([
            "%s/getProjectsService.php?sid=%s" % (cls.address, PHPReport.session_id),
            "%s/getAllUsersService.php?sid=%s" % (cls.address, PHPReport.session_id),
            "%s/getUserCustomersService.php?sid=%s" % (cls.address, PHPReport.session_id),
        ])
        Customer.load_all(responses[2], "customer")
        User.load_all(responses[1], "user")
        Project.load_all(responses[0], "project")

    @staticmethod
    def create_objects_from_response(response, cls, tag):
        return [cls(child) for child in ElementTree.fromstring(response) if child.tag == tag]

    @classmethod
    def get_tasks_for_task_filters(cls, task_filters):
        print("Fetching tasks...")
        responses = fetch_urls_in_parallel([task_filter.to_url(cls) for task_filter in task_filters])
        return [cls.create_objects_from_response(x, Task, "task") for x in responses]

    @classmethod
    def get_tasks_for_task_filter(cls, task_filter):
        contents = PHPReport.get_contents_of_url(task_filter.to_url(cls))
        return cls.create_objects_from_response(contents, Task, "task")


class TaskFilter():
    def __init__(self, project=None, customer=None, user=None):
        self.project = project
        self.customer = customer
        self.user = user
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
        task_filter = TaskFilter(project=self.project,
                                 customer=self.customer,
                                 user=self.user)
        task_filter.start_date = start_date
        task_filter.end_date = end_date
        return task_filter

    def to_url(self, phpreport):
        url = "%s/getTasksFiltered.php?sid=%s&dateFormat=Y-m-d" % \
              (phpreport.address, phpreport.session_id)
        if self.start_date:
            url += "&filterStartDate=%s" % self.start_date.strftime("%Y-%m-%d")
        if self.end_date:
            url += "&filterEndDate=%s" % self.end_date.strftime("%Y-%m-%d")
        if self.project is not None:
            url += "&projectId=%i" % self.project.phpreport_id
        if self.customer is not None:
            url += "&customerId=%i" % self.customer.phpreport_id
        if self.user is not None:
            url += "&userId=%i" % self.user.phpreport_id
        return url
