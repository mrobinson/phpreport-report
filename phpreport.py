# Copyright (C) 2012 Igalia S.L.
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
import httplib
import multiprocessing
import sys
import urllib2 as request
import xml.etree.ElementTree as ElementTree

DEFAULT_PHPREPORT_ADDRESS = "https://phpreport.igalia.com/web/services"
httplib.HTTPConnection.debuglevel = 1

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
            elif child.tag == "story" and child.text != None:
                self.story = child.text
            elif child.tag == "telework":
                self.telework = child.text
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

    def length(self):
        return self.end_time - self.init_time

class Project(PHPReportObject):
    def __init__(self, project_xml):
        for child in project_xml.getchildren():
            if child.tag == "id":
                self.id = int(child.text)
            if child.tag == "description":
                self.description = child.text

    def match(self, term):
        return self.description.lower().find(term) != -1

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

class PHPReport(object):
    users = {}
    projects = {}
    customers = {}

    @classmethod
    def make_request(cls, url):
        auth_header = 'Basic ' + base64.encodestring(cls.username + ':' + cls.password).strip()
        return request.Request(url, None, {"Authorization" : auth_header})

    @classmethod
    def get_contents_of_url(cls, url):
        def sanitize_url_for_display(url):
            return url.replace(cls.password, "<<<your password>>>")

        r = cls.make_request(url)
        try:
            return request.urlopen(r).read()
        except Exception as e:
            print "Could not complete request to %s" % sanitize_url_for_display(url)
            sys.exit(1)

    @classmethod
    def login(cls, username, password, address=DEFAULT_PHPREPORT_ADDRESS):
        cls.username = username
        cls.password = password
        cls.address = address
        cls.projects = {}
        print "Logging in..."
        response = cls.get_contents_of_url("%s/loginService.php?login=%s&password=%s" %
                                            (cls.address, username, password))

        cls.session_id = None
        tree = ElementTree.fromstring(response)
        for child in tree.getchildren():
            if child.tag == "sessionId":
                cls.session_id = child.text

        if not(cls.session_id):
            print "Could not find session id in login response: %s" % response
            sys.exit(1)

        # Use multiprocessing to access all URLs at once to reduce the latency of starting up.
        print "Loading PHPReport data..."
        pool = multiprocessing.Pool(processes=3)
        data = pool.map(get_url_contents, [
            "%s/getCustomerProjectsService.php?sid=%s" % (cls.address, PHPReport.session_id),
            "%s/getAllUsersService.php?sid=%s" % (cls.address, PHPReport.session_id),
            "%s/getUserCustomersService.php?sid=%s" % (cls.address, PHPReport.session_id),
        ])
        Project.load_all(data[0], "project")
        User.load_all(data[1], "user")
        Customer.load_all(data[2], "customer")

    @staticmethod
    def create_objects_from_response(response, cls, tag):
        return [cls(child) for child in ElementTree.fromstring(response).getchildren() if child.tag == tag]

    @classmethod
    def get_tasks_in_range(cls, start_date, end_date, filter=filter):
        tasks = []
        url = "%s/getTasksFiltered.php?sid=%s&filterStartDate=%s&filterEndDate=%s&dateFormat=Y-m-d" % \
              (cls.address, cls.session_id, str(start_date), str(end_date))
        if filter.project != None:
            url += "&projectId=%i" % filter.project.id
        if filter.customer != None:
            url += "&customerId=%i" % filter.customer.id
        if filter.user != None:
            url += "&userId=%i" % filter.user.id
        return cls.create_objects_from_response(cls.get_contents_of_url(url), Task, "task")

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

    def __str__(self):
        if self.project:
            return self.project.description
        if self.customer:
            return self.customer.name
        return self.user.login
