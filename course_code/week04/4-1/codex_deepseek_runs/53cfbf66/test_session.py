import unittest
from session import is_active
class SessionTests(unittest.TestCase):
    def test_before(self): self.assertTrue(is_active(99, 100))
    def test_at(self): self.assertFalse(is_active(100, 100))
    def test_after(self): self.assertFalse(is_active(101, 100))
