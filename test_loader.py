import tempfile
import os
import time
import unittest

from systemd_boot_lifeboat import Config, get_default_config


class TestConfig(unittest.TestCase):

    def setUp(self):
        self.esp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.esp.name, 'loader', 'entries'), exist_ok=True)
        super().setUp()

    def tearDown(self) -> None:
        self.esp.cleanup()
        super().tearDown()

    def test_parse_config(self):
        tests = [('', {}),
                 ('onecolbad', {}),
                 ('three cols ok', {'three': 'cols ok'}),
                 ('mykey myval', {'mykey': 'myval'}),
                 ('k v\n#commentkey v2', {'k': 'v'}),
                 ('k v\n# commentkey v2', {'k': 'v'}),
                 ('k v\nk\tv2\n k3    v3', {'k': 'v2', 'k3': 'v3'}),
                 ]
        for i, test in enumerate(tests):
            with self.subTest(test[0]):
                conf_path = self.create_entry(f'test_parse_config_{i}.conf', test[0])
                c = Config(conf_path)
                c.load()
                self.assertDictEqual(test[1], c)

    def test_write_config(self):
        conf_name = os.path.join(self.esp.name, 'test_write_config.conf')
        c = Config(conf_name, {'k': 'v', 'k2': 'v2'})
        c.write()
        with open(conf_name, 'r', encoding='utf8') as fp:
            self.assertEqual('k\tv\nk2\tv2\n', fp.read())

    def test_get_default_config(self):
        self.create_entry('arch.conf', 'k v')
        self.create_loader('missingdefault notarch')
        self.assertEqual(None, get_default_config(self.esp.name))

        self.create_loader('default arch')
        self.assertEqual({'k': 'v'}, get_default_config(self.esp.name))

    def test_create_lifeboat(self):
        efi_path = os.path.join(self.esp.name, 'EFI', 'Arch', 'linux.efi')
        os.makedirs(os.path.dirname(efi_path), exist_ok=True)
        with open(efi_path, 'w', encoding='utf8') as fp:
            fp.write("my cool efi")
        entry_path = self.create_entry('arch.conf', f'title my cool arch\nefi {efi_path}')

        now = int(time.time())
        c = Config(entry_path)
        c.load()

        lifeboat = c.create_lifeboat(now)

        self.assertDictEqual({'title': 'my cool arch', 'efi': os.path.join(
            os.path.dirname(efi_path), f'lifeboat_{now}_linux.efi')}, lifeboat)
        pass

    def test_create_lifeboat_cleans_up_if_writing_fails(self):
        efi_path = os.path.join(self.esp.name, 'EFI', 'Arch', 'linux.efi')
        os.makedirs(os.path.dirname(efi_path), exist_ok=True)
        with open(efi_path, 'w', encoding='utf8') as fp:
            fp.write("my cool efi")
        entry_path = self.create_entry('arch.conf', f'title my cool arch\nefi {efi_path}')
        c = Config(entry_path)
        c.load()
        now = int(time.time())

        # create the lifeboat file so that this will error out later
        self.create_entry(f'lifeboat_{now}_arch.conf', 'already exists')
        self.assertRaises(OSError, lambda: c.create_lifeboat(now))
        # Make sure the lifeboat efi is cleaned up
        self.assertFalse(os.path.exists(os.path.join(self.esp.name, 'EFI', 'Arch', f'lifeboat_{now}_linux.efi')))
        pass

    def create_loader(self, contents: str) -> str:
        loader_name = os.path.join(self.esp.name, 'loader', 'loader.conf')
        with open(loader_name, 'w', encoding='utf8') as fp:
            fp.write(contents)
        return loader_name

    def create_entry(self, name: str, contents: str) -> str:
        conf_name = os.path.join(self.esp.name, 'loader', 'entries', name)
        with open(conf_name, 'w', encoding='utf8') as fp:
            fp.write(contents)
        return conf_name


if __name__ == '__main__':
    unittest.main()
