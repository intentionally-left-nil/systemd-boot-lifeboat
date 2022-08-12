import tempfile
import os
from collections import OrderedDict
import unittest

from systemd_boot_lifeboat import Config


class TestConfig(unittest.TestCase):
    def test_parse_config(self):
        tests = [('', {}),
                 ('onecolbad', {}),
                 ('three cols bad', {}),
                 ('mykey myval', {'mykey': 'myval'}),
                 ('k v\n#commentkey v2', {'k': 'v'}),
                 ('k v\n# commentkey v2', {'k': 'v'}),
                 ('k v\nk\tv2\n k3    v3', {'k': 'v2', 'k3': 'v3'}),
                 ]
        with tempfile.TemporaryDirectory() as tmpdirname:
            for i, test in enumerate(tests):
                with self.subTest(test[0]):
                    conf_name = os.path.join(tmpdirname, f'test_parse_config_{i}.conf')
                    with open(conf_name, 'w', encoding='utf8') as fp:
                        fp.write(test[0])

                    c = Config(conf_name)
                    self.assertDictEqual(test[1], c)

    def test_write_config(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            conf_name = os.path.join(tmpdirname, f'test_write_config.conf')
            with open(conf_name, 'w', encoding='utf8') as fp:
                fp.write('k   v\n#comment\n\nk2\tv2')
            c = Config(conf_name)
            c.write()
            with open(conf_name, 'r', encoding='utf8') as fp:
                self.assertEqual('k\tv\nk2\tv2\n', fp.read())


if __name__ == '__main__':
    unittest.main()
