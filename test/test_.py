import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from starlib.dataExtractor.community import TwitchAPI

class Test(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.tw_api = TwitchAPI()

    def test_get_user(self):
        self.tw_api.get_user = MagicMock(return_value={"id": "123"})
        self.assertEqual(self.tw_api.get_user("123"), {"id": "123"})

    def test_get_clips(self):
        clips = self.tw_api.get_clips(broadcaster_id=490765956, started_at=datetime.fromisoformat("2024-07-05 23:14:22+08:00"))
        self.assertNotEqual(clips, [])

    @classmethod
    def tearDownClass(self):
        pass

if __name__ == '__main__':
    unittest.main()