# Copyright (C) 2012, 2013 Igalia S.L.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
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

import base64
import datetime
import getpass
import http.client
import keyring
import multiprocessing
import sys
import urllib
import xml.etree.ElementTree as ElementTree

DEFAULT_PHPREPORT_ADDRESS = "https://beta.phpreport.igalia.com/web/services"
URLS_TO_FETCH_IN_PARALLEL = 10
http.client.HTTPConnection.debuglevel = 0

class Credential(object):
    all_credentials = {}

    @classmethod
    def for_url(cls, url, username=None):
        if not username:
            username = input("Username: ")

        key = (url, username)
        if key in cls.all_credentials:
            return cls.all_credentials[key]

        password = keyring.get_password("PHPReport", username)
        saved = True
        if not password:
            password = getpass.getpass("Password: ")
            saved = False

        credential = Credential(url, username, password, saved)
        cls.all_credentials[key] = credential
        return credential

    def __init__(self, url, username, password, saved):
        self.url = url
        self.username = username
        self.password = password
        self.saved = saved

    def save(self):
        if self.saved:
            return
        if input("Store password for '%s' in keyring? (y/N) " % self.username) != 'y':
            return
        keyring.set_password("PHPReport", self.username, self.password)

    def __eq__(self, other):
        return self.url == other.url and self.username == other.username


class PHPReportObject(object):
    @classmethod
    def find(cls, id):
        return cls.instances[id]

    @classmethod
    def load_all(cls, data, tag):
        instances = PHPReport.create_objects_from_response(data, cls, tag)

        cls.instances = {}
        for instance in instances:
            cls.instances[instance.id] = instance

class Task(PHPReportObject):
    def __init__(self, task_xml):
        self.text = ""
        self.story = ""

        # These might be empty.
        self.project_id = None
        self.project = None
        self.onsite = False
        self.telework = False

        for child in task_xml.getchildren():
            if child.tag == "id":
                self.id = int(child.text)
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

            elif child.tag == "story" and child.text != None:
                self.story = child.text
            elif child.tag == "text" and child.text != None:
                self.text = child.text
            elif child.tag == "phase":
                self.phase = child.text
            elif child.tag == "userId":
                self.user_id = int(child.text)
                self.user = User.find(self.user_id)
            elif child.tag == "projectId" and child.text:
                self.project_id = int(child.text)
                self.project = Project.find(self.project_id)
            elif child.tag == "customerId":
                self.customer_id = int(child.text)
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

        for child in project_xml.getchildren():
            if child.tag == "id":
                self.id = int(child.text)
            if child.tag == "description":
                self.description = child.text
            if child.tag == "initDate" and child.text:
                self.init_date = datetime.datetime.strptime(child.text, "%Y-%m-%d").date()
            if child.tag == "endDate" and child.text:
                self.init_date = datetime.datetime.strptime(child.text, "%Y-%m-%d").date()

    def match(self, term):
        return self.description.lower().find(term) != -1

    def has_ended(self):
        return self.end_date and self.end_date() < datetime.date.today()

    def __lt__(self, other):
        if self.has_ended() and not other.has_ended():
            return True
        if other.has_ended() and not self.has_ended():
            return False
        if self.init_date and other.init_date:
            return self.init_date <  other.init_date
        return self.id < other.id

class User(PHPReportObject):
    def __init__(self, user_xml):
        for child in user_xml.getchildren():
            if child.tag == "id":
                self.id = int(child.text)
            if child.tag == "login":
                self.login = child.text

    def match(self, term):
        return self.login.lower().find(term) != -1

class Customer(PHPReportObject):
    def __init__(self, customer_xml):
        for child in customer_xml.getchildren():
            if child.tag == "id":
                self.id = int(child.text)
            if child.tag == "name":
                self.name = child.text

    def match(self, term):
        return self.name.lower().find(term) != -1

def get_url_contents(url):
    return PHPReport.get_contents_of_url(url)

def fetch_urls_in_parallel(urls):
    pool = multiprocessing.Pool(processes=URLS_TO_FETCH_IN_PARALLEL)
    return pool.map(get_url_contents, urls)

class PHPReport(object):
    users = {}
    projects = {}
    customers = {}

    @classmethod
    def get_contents_of_url(cls, url):
        def sanitize_url_for_display(url):
            return url.replace(cls.credential.password, "<<<your password>>>")

        r = urllib.request.Request(url, None)
        try:
            return urllib.request.urlopen(r).read()
        except Exception as e:
            print("Could not complete request to %s" % sanitize_url_for_display(url))
            sys.exit(1)

    @classmethod
    def login(cls, address=DEFAULT_PHPREPORT_ADDRESS, username=None):
        cls.address = address
        cls.projects = {}
        cls.credential = Credential.for_url(address, username)

        password_manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_manager.add_password(None, cls.address, cls.credential.username, cls.credential.password)
        handler = urllib.request.HTTPBasicAuthHandler(password_manager)
        urllib.request.install_opener(urllib.request.build_opener(handler))

        print("Logging in...")
        response = cls.get_contents_of_url("%s/loginService.php?login=%s&password=%s" %
                                            (cls.address, cls.credential.username, cls.credential.password))

        cls.session_id = None
        tree = ElementTree.fromstring(response)
        for child in tree.getchildren():
            if child.tag == "sessionId":
                cls.session_id = child.text

        if not(cls.session_id):
            print("Could not find session id in login response, password likely incorrect: %s" % response)
            sys.exit(1)

        cls.credential.save()

        # Use multiprocessing to access all URLs at once to reduce the latency of starting up.
        print("Loading PHPReport data...")
        responses = fetch_urls_in_parallel([
            "%s/getCustomerProjectsService.php?sid=%s" % (cls.address, PHPReport.session_id),
            "%s/getAllUsersService.php?sid=%s" % (cls.address, PHPReport.session_id),
            "%s/getUserCustomersService.php?sid=%s" % (cls.address, PHPReport.session_id),
        ])
        Project.load_all(responses[0], "project")
        User.load_all(responses[1], "user")
        Customer.load_all(responses[2], "customer")

    @staticmethod
    def create_objects_from_response(response, cls, tag):
        return [cls(child) for child in ElementTree.fromstring(response).getchildren() if child.tag == tag]

    @classmethod
    def get_tasks_for_task_filters(cls, task_filters):
        print("Fetching tasks...")
        responses = fetch_urls_in_parallel([task_filter.to_url(cls) for task_filter in task_filters])
        return [cls.create_objects_from_response(x, Task, "task") for x in responses]

    @classmethod
    def get_tasks_for_day_and_user(cls, date, user):
        tasks = []
        response = cls.get_contents_of_url("%s/getUserTasksService.php?sid=%s&login=%s&date=%s&dateFormat=Y-m-d" %
                                           (cls.address, cls.session_id, user.login, str(date)))
        return cls.create_objects_from_response(response, Task, "task")

class TaskFilter(object):
    def __init__(self, project=None, customer=None, user=None):
        self.project = project
        self.customer = customer
        self.user = user
        self.start_date = None
        self.end_date = None

    def __str__(self):
        if self.project:
            return self.project.description
        if self.customer:
            return self.customer.name
        return self.user.login

    def create_instance_for_dates(self, start_date, end_date):
        task_filter = TaskFilter(project=self.project,
                                 customer=self.customer,
                                 user=self.user)
        task_filter.start_date = start_date
        task_filter.end_date = end_date
        return task_filter

class TaskFilter(TaskFilter):
    def to_url(self, phpreport):
        url = "%s/getTasksFiltered.php?sid=%s&filterStartDate=%s&filterEndDate=%s&dateFormat=Y-m-d" % \
              (phpreport.address, phpreport.session_id, str(self.start_date), str(self.end_date))
        if self.project != None:
            url += "&projectId=%i" % self.project.id
        if self.customer != None:
            url += "&customerId=%i" % self.customer.id
        if self.user != None:
            url += "&userId=%i" % self.user.id
        return url

