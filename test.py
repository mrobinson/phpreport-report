import datetime
import unittest
from xml.etree import ElementTree

import phpreport
from phpreport import Customer, PHPReportObject, Project, Task, User

class TestUser(unittest.TestCase):
    def setUp(self):
        PHPReportObject.instances.clear()

    def test_empty(self):
        user = User()
        self.assertIs(user, User.find(-1))
        self.assertIsInstance(user, User)
        self.assertEqual(user.phpreport_id, -1)
        self.assertEqual(user.login, "<unknown>")

    def test_simple_parse(self):
        element = ElementTree.fromstring("""
            <user>
                <id>22</id>
                <login>testuser</login>
                <userGroups/>
            </user>""")
        user = User.from_element(element)
        self.assertIs(user, User.find(22))
        self.assertIsInstance(user, User)
        self.assertEqual(user.phpreport_id, 22)
        self.assertEqual(user.login, "testuser")


class TestCustomer(unittest.TestCase):
    def test_empty(self):
        Customer()
        customer = Customer.find(-1)
        self.assertIsInstance(customer, Customer)
        self.assertEqual(customer.phpreport_id, -1)
        self.assertEqual(customer.name, "<unknown>")

    def test_simple_parse(self):
        element = ElementTree.fromstring("""
            <customer>
                <id>99</id>
                <sectorId>1</sectorId>
                <name>Custom Er</name>
                <type>large</type>
                <url>http://customer.com</url>
            </customer>""")
        customer = Customer.from_element(element)
        self.assertIs(customer, Customer.find(99))
        self.assertEqual(customer.phpreport_id, 99)
        self.assertEqual(customer.name, "Custom Er")


class TestProject(unittest.TestCase):
    def test_empty(self):
        project = Project()
        self.assertIs(project, Project.find(-1))
        self.assertIsInstance(project, Project)
        self.assertEqual(project.phpreport_id, -1)
        self.assertEqual(project.description, "<description>")
        self.assertEqual(project.customer_id, -1)
        self.assertIs(project.customer, Customer.find(-1))
        self.assertEqual(project.init_date, phpreport.DEFAULT_DATE.date())
        self.assertEqual(project.end_date, phpreport.DEFAULT_DATE.date())

    def test_simple_parse(self):
        element = ElementTree.fromstring("""
        <project>
            <id>230</id>
            <areaId>3</areaId>
            <customerId>-1</customerId>
            <activation/>
            <invoice>203</invoice>
            <description>Very cool</description>
            <customerName>&lt;unknown&gt;</customerName>
            <fullDescription>Very very cool</fullDescription>
            <init format="Y-m-d">2016-09-29</init>
            <end format="Y-m-d">2018-02-13</end>
            <estHours>24</estHours>
            <type>per_goals</type>
            <movedHours/>
            <schedType/>
            </project>""")
        project = Project.from_element(element)
        self.assertIs(project, Project.find(230))
        self.assertIsInstance(project, Project)
        self.assertEqual(project.phpreport_id, 230)
        self.assertEqual(project.description, "Very cool")
        self.assertEqual(project.customer_id, -1)
        self.assertIs(project.customer, Customer.find(-1))
        self.assertEqual(project.init_date, datetime.date(2016, 9, 29))
        self.assertEqual(project.end_date, datetime.date(2018, 2, 13))

class TestTask(unittest.TestCase):
    def test_empty(self):
        task = Task()
        self.assertIs(task, Task.find(-1))
        self.assertEqual(task.phpreport_id, -1)
        self.assertEqual(task.user_id, -1)
        self.assertIs(task.user, User.find(-1))
        self.assertEqual(task.project_id, -1)
        self.assertEqual(task.project, Project.find(-1))
        self.assertEqual(task.text, "")
        self.assertEqual(task.story, "")
        self.assertEqual(task.ttype, "")
        self.assertEqual(task.date, phpreport.DEFAULT_DATE.date())
        self.assertEqual(task.init_time, phpreport.DEFAULT_DATE)
        self.assertEqual(task.end_time, phpreport.DEFAULT_DATE + datetime.timedelta(days=1))
        self.assertFalse(task.onsite)
        self.assertFalse(task.telework)

    def test_simple_parse(self):
        element = ElementTree.fromstring("""
            <task>
                <id>200291</id>
                <date format="Y-m-d">2023-02-17</date>
                <initTime>03:30</initTime>
                <endTime>08:22</endTime>
                <story>likely</story>
                <telework>true</telework>
                <onsite>true</onsite>
                <ttype>implementation</ttype>
                <text>Adding a test for parsing of tasks.</text>
                <phase>fase</phase>
                <userId>-1</userId>
                <projectId>-1</projectId>
            </task>""")
        task = Task.from_element(element)
        self.assertIs(task, Task.find(200291))
        self.assertEqual(task.phpreport_id, 200291)
        self.assertEqual(task.user_id, -1)
        self.assertIs(task.user, User.find(-1))
        self.assertEqual(task.project_id, -1)
        self.assertEqual(task.project, Project.find(-1))
        self.assertEqual(task.text, "Adding a test for parsing of tasks.")
        self.assertEqual(task.story, "likely")
        self.assertEqual(task.ttype, "implementation")
        self.assertEqual(task.date, datetime.date(2023, 2, 17))
        self.assertEqual(task.init_time, datetime.datetime(2023, 2, 17, 3, 30))
        self.assertEqual(task.end_time, datetime.datetime(2023, 2, 17, 8, 22))
        self.assertTrue(task.onsite)
        self.assertTrue(task.telework)


if __name__ == '__main__':
    unittest.main()
