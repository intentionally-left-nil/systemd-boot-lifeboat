import datetime
import os
import tempfile
import time
import unittest

from systemd_boot_lifeboat import Config, Lifeboat, get_default_config, main, md5
from typing import TypedDict


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
                self.assertDictEqual(test[1], c)

    def test_write_config(self):
        conf_name = os.path.join(self.esp.name, 'test_write_config.conf')
        c = Config(conf_name, {'k': 'v', 'k2': 'v2'}, ignore_missing=True)
        c.write()
        with open(conf_name, 'r', encoding='utf8') as fp:
            self.assertEqual('k\tv\nk2\tv2\n', fp.read())

    def test_get_default_config(self):
        self.create_entry('arch.conf', 'k v')
        self.create_loader('missingdefault notarch')
        self.assertRaises(ValueError, lambda: get_default_config(self.esp.name))

        self.create_loader('default arch')
        self.assertEqual({'k': 'v'}, get_default_config(self.esp.name))

    def test_create_lifeboat(self):
        efi_path = self.create_efi('linux.efi', 'my cool efi')
        entry_path = self.create_entry('arch.conf', f'title my cool arch\nefi {efi_path}')

        now = int(time.time())
        c = Config(entry_path)

        lifeboat = Lifeboat.from_default_config(c, now)

        self.assertDictEqual({'title': f'my cool arch@{lifeboat.pretty_date()}',
                             'efi': Lifeboat.lifeboat_path(efi_path, now)}, lifeboat)
        pass

    def test_create_lifeboat_cleans_up_if_writing_fails(self):
        efi_path = self.create_efi('linux.efi', 'my cool efi')
        entry_path = self.create_entry('arch.conf', f'title my cool arch\nefi {efi_path}')
        c = Config(entry_path)
        now = int(time.time())

        # create the lifeboat file so that this will error out later
        self.create_entry(f'lifeboat_{now}_arch.conf', 'already exists')
        self.assertRaises(OSError, lambda: Lifeboat.from_default_config(c, now))
        # Make sure the lifeboat efi is cleaned up
        self.assertFalse(os.path.exists(os.path.join(self.esp.name, 'EFI', 'Arch', f'lifeboat_{now}_linux.efi')))
        pass

    def test_get_existing(self):
        now = int(time.time())
        past = int(time.time()) - 101
        self.create_entry('arch.conf', 'k v')
        now_conf_path = self.create_entry(Lifeboat.lifeboat_path('arch.conf', now), 'k now')
        past_conf_path = self.create_entry(Lifeboat.lifeboat_path('arch.conf', past), 'k past')

        actual = Lifeboat.get_existing(self.esp.name)
        expected = [Lifeboat(now_conf_path), Lifeboat(past_conf_path)]
        self.assertListEqual(sorted(expected), sorted(actual))

    def test_sort_by_timestamp(self):
        now = int(time.time())
        past = int(time.time()) - 1
        past2 = int(time.time()) - 2
        expected = [self.create_entry(Lifeboat.lifeboat_path('arch.conf', x), 'k v') for x in [past2, past, now]]
        actual = [x.filepath for x in Lifeboat.get_existing(self.esp.name)]
        self.assertListEqual(expected, actual)

    def test_equivalent(self):
        efi_path = self.create_efi('linux.efi', 'my cool efi')
        efi_copy_path = self.create_efi('linux_copy.efi', 'my cool efi')
        different_efi_path = self.create_efi('linux_other.efi', 'some other efi')

        class Test(TypedDict):
            name: str
            config: Config
            lifeboat: Lifeboat
            expected: bool
        tests: list[Test] = [
            Test(
                name="identical configs are equivalent",
                config=Config('', {'k': 'v', 'k2': 'v2'}, ignore_missing=True),
                lifeboat=Lifeboat('lifeboat_123_arch.conf', {'k': 'v', 'k2': 'v2'}, ignore_missing=True),
                expected=True
            ),
            Test(
                name="Configs with different titles are equivalent",
                config=Config('', {'title': 'hello', 'k2': 'v2'}, ignore_missing=True),
                lifeboat=Lifeboat('lifeboat_123_arch.conf', {'title': 'world', 'k2': 'v2'}, ignore_missing=True),
                expected=True
            ),
            Test(
                name="Configs with different values are not equivalent",
                config=Config('', {'title': 'hello', 'k2': 'v2'}, ignore_missing=True),
                lifeboat=Lifeboat('lifeboat_123_arch.conf', {'title': 'world',
                                  'k2': 'differentvalue'}, ignore_missing=True),
                expected=False
            ),
            Test(
                name="Configs with extra keys are not equivalent",
                config=Config('', {'title': 'hello', 'k2': 'v2'}, ignore_missing=True),
                lifeboat=Lifeboat('lifeboat_123_arch.conf', {'title': 'hello',
                                  'k2': 'v2', 'k3': 'v3'}, ignore_missing=True),
                expected=False
            ),
            Test(
                name="Configs pointing to the exact efi file are equivalent",
                config=Config('', {'efi': efi_path}, ignore_missing=True),
                lifeboat=Lifeboat('lifeboat_123_arch.conf', {'efi': efi_path}, ignore_missing=True),
                expected=True
            ),
            Test(
                name="Configs pointing to different efi files with the same checksum are equivalent",
                config=Config('', {'efi': efi_path}, ignore_missing=True),
                lifeboat=Lifeboat('lifeboat_123_arch.conf', {'efi': efi_copy_path}, ignore_missing=True),
                expected=True
            ),
            Test(
                name="Configs pointing to different efi files with differnt checksum are not equivalent",
                config=Config('', {'efi': efi_path}, ignore_missing=True),
                lifeboat=Lifeboat('lifeboat_123_arch.conf', {'efi': different_efi_path}, ignore_missing=True),
                expected=False
            ),
            Test(
                name="Configs with missing efi files are not equivalent",
                config=Config('', {'efi': efi_path}, ignore_missing=True),
                lifeboat=Lifeboat('lifeboat_123_arch.conf', {'efi': 'this_file_does_not_exist'}, ignore_missing=True),
                expected=False
            ),
        ]
        for test in tests:
            with self.subTest(test['name']):
                actual = test['lifeboat'].equivalent(test['config'])
                self.assertEqual(test['expected'], actual)

    def test_end_to_end(self):
        efi_path = self.create_efi('linux.efi', 'my cool efi')
        efi_md5 = md5(efi_path)
        first_lifeboat_md5 = efi_md5
        loader_path = self.create_loader('default arch')
        loader_md5 = md5(loader_path)
        entry_path = self.create_entry('arch.conf', f'''
title Arch Linux
efi {efi_path}
''')
        entry_md5 = md5(entry_path)

        config = get_default_config(self.esp.name)

        def ensure_config_untouched():
            self.assertEqual(efi_md5, md5(efi_path))
            self.assertEqual(loader_md5, md5(loader_path))
            self.assertEqual(entry_md5, md5(entry_path))

        # First run, create first lifeboat
        main(esp=self.esp.name, max_lifeboats=2)
        ensure_config_untouched()
        lifeboats = Lifeboat.get_existing(self.esp.name)
        self.assertTrue(len(lifeboats) == 1)
        first_lifeboat = lifeboats[0]
        new_efi_path = lifeboats[0]['efi']
        self.assertEqual(efi_md5, md5(new_efi_path))
        self.assertTrue(first_lifeboat.equivalent(config))

        time.sleep(1)  # Sleep to ensure the next time we run, the timestamp is different

        # Second run, no change
        main(esp=self.esp.name, max_lifeboats=2)
        ensure_config_untouched()
        lifeboats = Lifeboat.get_existing(self.esp.name)
        self.assertTrue(len(lifeboats) == 1)

        # Third run, efi is different - create second lifeboat
        self.create_efi('linux.efi', 'new_efi')
        efi_md5 = md5(efi_path)
        second_lifeboat_md5 = efi_md5
        time.sleep(1)
        main(esp=self.esp.name)
        ensure_config_untouched()
        lifeboats = Lifeboat.get_existing(self.esp.name)
        self.assertTrue(len(lifeboats) == 2)
        self.assertTrue(lifeboats[0].equivalent(first_lifeboat))
        self.assertFalse(lifeboats[0].equivalent(config))
        self.assertEqual(first_lifeboat_md5, md5(lifeboats[0]['efi']))

        second_lifeboat = lifeboats[1]

        self.assertTrue(second_lifeboat.equivalent(config))
        self.assertEqual(second_lifeboat_md5, md5(second_lifeboat['efi']))

        # Fourth run, efi is different. Delete the first_lifeboat and create the third_lifeboat
        self.create_efi('linux.efi', 'new_efi2')
        efi_md5 = md5(efi_path)
        third_lifeboat_md5 = efi_md5
        time.sleep(1)
        main(esp=self.esp.name, max_lifeboats=2)
        ensure_config_untouched()
        lifeboats = Lifeboat.get_existing(self.esp.name)
        self.assertTrue(len(lifeboats) == 2)
        self.assertTrue(lifeboats[0].equivalent(second_lifeboat))
        self.assertFalse(lifeboats[0].equivalent(config))

        third_lifeboat = lifeboats[1]
        self.assertTrue(third_lifeboat.equivalent(config))
        self.assertEqual(third_lifeboat_md5, md5(third_lifeboat['efi']))

        # Make sure the first lifeboat got deleted
        self.assertFalse(os.path.exists(first_lifeboat.filepath))
        self.assertFalse(os.path.exists(first_lifeboat['efi']))

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

    def create_efi(self, name: str, contents: str) -> str:
        efi_path = os.path.join(self.esp.name, 'EFI', 'Arch', name)
        os.makedirs(os.path.dirname(efi_path), exist_ok=True)
        with open(efi_path, 'w', encoding='utf8') as fp:
            fp.write(contents)
        return efi_path


if __name__ == '__main__':
    unittest.main()
