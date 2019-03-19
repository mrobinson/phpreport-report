from dateutils import DateUtils

import datetime
import unittest

CURRENT_YEAR = datetime.datetime.now().year

class TestDateUtils(unittest.TestCase):
    def test_last_day_of_month(self):
        self.assertEqual(DateUtils.last_day_of_month(2019, 3), 31)
        self.assertEqual(DateUtils.last_day_of_month(2018, 7), 31)
        self.assertEqual(DateUtils.last_day_of_month(2016, 2), 29)
        self.assertEqual(DateUtils.last_day_of_month(2017, 2), 28)

    def test_date_from_string_exact(self):
        dates = DateUtils.date_from_string("01/01/2018")
        self.assertEqual(dates[0], datetime.date(2018, 1, 1))
        self.assertEqual(dates[1], datetime.date(2018, 1, 1))

        dates = DateUtils.date_from_string("31/01/2018")
        self.assertEqual(dates[0], datetime.date(2018, 1, 31))
        self.assertEqual(dates[1], datetime.date(2018, 1, 31))

        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("01/0/2018")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("01/13/2018")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("01/99/2018")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("32/1/2018")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("0/1/2018")

        dates = DateUtils.date_from_string("12/06/2323")
        self.assertEqual(dates[0], datetime.date(2323, 6, 12))
        self.assertEqual(dates[1], datetime.date(2323, 6, 12))

    def test_date_from_string_year(self):
        dates = DateUtils.date_from_string("2018")
        self.assertEqual(dates[0], datetime.date(2018, 1, 1))
        self.assertEqual(dates[1], datetime.date(2018, 12, 31))

        dates = DateUtils.date_from_string("3000")
        self.assertEqual(dates[0], datetime.date(3000, 1, 1))
        self.assertEqual(dates[1], datetime.date(3000, 12, 31))

        dates = DateUtils.date_from_string("1950")
        self.assertEqual(dates[0], datetime.date(1950, 1, 1))
        self.assertEqual(dates[1], datetime.date(1950, 12, 31))

        # We don't support years that don't have four digits.
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("659")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("23")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("1")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("65900")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("100000000000")

    def test_date_from_string_month(self):
        dates = DateUtils.date_from_string("12/2018")
        self.assertEqual(dates[0], datetime.date(2018, 12, 1))
        self.assertEqual(dates[1], datetime.date(2018, 12, 31))

        dates = DateUtils.date_from_string("2/2016")
        self.assertEqual(dates[0], datetime.date(2016, 2, 1))
        self.assertEqual(dates[1], datetime.date(2016, 2, 29))

        dates = DateUtils.date_from_string("02/2016")
        self.assertEqual(dates[0], datetime.date(2016, 2, 1))
        self.assertEqual(dates[1], datetime.date(2016, 2, 29))

        # We don't support years that don't have four digits.
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("02/232")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("111/2012")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("0/2012")

    def test_date_from_string_week(self):
        dates = DateUtils.date_from_string("w1/2019")
        self.assertEqual(dates[0], datetime.date(2018, 12, 31))
        self.assertEqual(dates[1], datetime.date(2019, 1, 6))
        dates = DateUtils.date_from_string("w01/2019")
        self.assertEqual(dates[0], datetime.date(2018, 12, 31))
        self.assertEqual(dates[1], datetime.date(2019, 1, 6))

        dates = DateUtils.date_from_string("w01")
        self.assertEqual(dates[0], DateUtils.from_week_number(CURRENT_YEAR, 1))
        self.assertEqual(dates[1], DateUtils.from_week_number(CURRENT_YEAR, 1, end=True))

        dates = DateUtils.date_from_string("w52/2016")
        self.assertEqual(dates[0], datetime.date(2016, 12, 26))
        self.assertEqual(dates[1], datetime.date(2017, 1, 1))

        dates = DateUtils.date_from_string("w1/2017")
        self.assertEqual(dates[0], datetime.date(2017, 1, 2))
        self.assertEqual(dates[1], datetime.date(2017, 1, 8))

        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("w02/232")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("w111/2012")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("w0/2012")

    def test_date_from_string_quarter(self):
        dates = DateUtils.date_from_string("q1/2019")
        self.assertEqual(dates[0], datetime.date(2019, 1, 1))
        self.assertEqual(dates[1], datetime.date(2019, 3, 31))
        dates = DateUtils.date_from_string("Q1/2019")
        self.assertEqual(dates[0], datetime.date(2019, 1, 1))
        self.assertEqual(dates[1], datetime.date(2019, 3, 31))

        dates = DateUtils.date_from_string("Q2")
        self.assertEqual(dates[0], datetime.date(CURRENT_YEAR, 4, 1))
        self.assertEqual(dates[1], datetime.date(CURRENT_YEAR, 6, 30))

        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("Q2/232")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("Q2/00232")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("Q5/2012")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("Q0/2012")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("Q0234/2012")

    def test_date_from_string_half(self):
        dates = DateUtils.date_from_string("h1/2019")
        self.assertEqual(dates[0], datetime.date(2019, 1, 1))
        self.assertEqual(dates[1], datetime.date(2019, 6, 30))
        dates = DateUtils.date_from_string("H1/2019")
        self.assertEqual(dates[0], datetime.date(2019, 1, 1))
        self.assertEqual(dates[1], datetime.date(2019, 6, 30))

        dates = DateUtils.date_from_string("h2/2019")
        self.assertEqual(dates[0], datetime.date(2019, 7, 1))
        self.assertEqual(dates[1], datetime.date(2019, 12, 31))
        dates = DateUtils.date_from_string("H2/2019")
        self.assertEqual(dates[0], datetime.date(2019, 7, 1))
        self.assertEqual(dates[1], datetime.date(2019, 12, 31))

        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("H2/232")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("H2/00232")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("H5/2012")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("H0/2012")
        with self.assertRaises(ValueError):
            dates = DateUtils.date_from_string("H0234/2012")
if __name__ == '__main__':
    unittest.main()
