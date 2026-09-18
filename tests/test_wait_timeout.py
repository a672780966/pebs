import unittest

from pebs.benchmark import runner


class WaitTimeoutTests(unittest.TestCase):
    def test_timeout_follows_run_budget(self):
        self.assertEqual(runner._wait_timeout({"budget_seconds": 14400}), 15000.0)

    def test_timeout_has_a_floor(self):
        self.assertEqual(runner._wait_timeout({"budget_seconds": 300}), 3600.0)

    def test_timeout_tolerates_missing_budget(self):
        self.assertEqual(runner._wait_timeout({}), 3600.0)


if __name__ == "__main__":
    unittest.main()
