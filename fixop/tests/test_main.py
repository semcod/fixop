import unittest
from fixop.main import fix_operation, get_version

class TestFixOperation(unittest.TestCase):
    def test_fix_operation_string(self):
        """Test fix_operation with string input"""
        self.assertEqual(fix_operation("  test  "), "test")

    def test_fix_operation_non_string(self):
        """Test fix_operation with non-string input"""
        self.assertEqual(fix_operation(123), 123)
        self.assertEqual(fix_operation([1, 2, 3]), [1, 2, 3])

    def test_get_version(self):
        """Test get_version function"""
        self.assertEqual(get_version(), "0.1.0")

if __name__ == '__main__':
    unittest.main()