import dataclasses as dc
from systemd_boot_lifeboat import Config, Chroot, ChrootError, FileTracker, pretty_date, main, EXPLICIT_CONFIG_FILE, AUTO_EFI_CONFIG
from multiprocessing.sharedctypes import Value
import os
import shutil
import re
from tempfile import TemporaryDirectory
from typing import Dict, TypedDict, Union
import unittest
from unittest.mock import patch


class TestConfig(unittest.TestCase):
    def setUp(self):
        if os.getuid() != 0:
            self.skipTest('Must run unit tests as root')

        self.maxDiff = None
        self.tmp = TemporaryDirectory()
        self.reset()

        default_path = self.tmp.name
        get_default_path = lambda x: default_path

        self.patcher = patch('systemd_boot_lifeboat.get_default_path', get_default_path)
        self.patcher.start()

    def reset(self):
        for filename in os.listdir(self.tmp.name):
            filepath = os.path.join(self.tmp.name, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
            else:
                shutil.rmtree(filepath)
        os.makedirs(os.path.join(self.tmp.name, 'loader', 'entries'), exist_ok=True)
        os.makedirs(os.path.join(self.tmp.name, 'EFI', 'Arch'), exist_ok=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()
        self.patcher.stop()
        super().tearDown()

    def test_from_bootctl(self):
        class Test(TypedDict):
            name: str
            input: Dict[str, Union[str, list[str]]]
            expected: Config
        tests: list[Test] = [
            Test(
                name="default entry",
                input={"id": "arch.conf", "path": "/efi/loader/entries/arch.conf", "root": "/efi",
                       "title": "Arch Linux", "showTitle": "Arch Linux", "efi": "/EFI/Arch/linux.efi"},
                expected=Config(path="/efi/loader/entries/arch.conf", root="/efi", title=['Arch Linux'], efi=["/EFI/Arch/linux.efi"])),
            Test(
                name="multiple initrd",
                input={"id": "arch.conf", "path": "/efi/loader/entries/arch.conf", "root": "/efi",
                       "title": "Arch Linux", "showTitle": "Arch Linux", "linux": "vmlinuz-linux", "initrd": ["intel-ucode.img", "amd-ucode.img"]},
                expected=Config(path="/efi/loader/entries/arch.conf", root="/efi", title=['Arch Linux'], linux=["vmlinuz-linux"], initrd=["intel-ucode.img", "amd-ucode.img"])),
            Test(
                name="sort key",
                input={"id": "arch.conf", "path": "/efi/loader/entries/arch.conf", "root": "/efi", "sortKey": "test"},
                expected=Config(path="/efi/loader/entries/arch.conf", root="/efi", sort_key=["test"])),
        ]
        for test in tests:
            with self.subTest(test['name']):
                self.assertEqual(test['expected'], Config.from_bootctl(test['input']))

    def test_create_lifeboat(self):
        ts = 12345

        class Test(TypedDict):
            name: str
            config: Config
            expected: Config

        tests: list[Test] = [
            Test(
                name="efi entry",
                config=Config(path=os.path.join(self.tmp.name, "loader/entries/arch.conf"), root=self.tmp.name,
                              title=['Arch Linux'], efi=["/EFI/Arch/linux.efi"], sort_key=["linux"], version=["linux5.19"], autosave=True, type=EXPLICIT_CONFIG_FILE),
                expected=Config(path=os.path.join(self.tmp.name, "loader/entries/lifeboat_12345_arch.conf"), root=self.tmp.name,
                                title=[f'Arch Linux @{pretty_date(ts)}'], efi=["/EFI/Arch/lifeboat_12345_linux.efi"], sort_key=["linux"], version=["-linux5.19-12345"], type=EXPLICIT_CONFIG_FILE)
            ),
            Test(
                name="simple linux entry",
                config=Config(path=os.path.join(self.tmp.name, "loader/entries/arch.conf"), root=self.tmp.name,
                              title=['Arch Linux'], linux=['/vmlinuz-linux'], initrd=['/initramfs-linux.img'], sort_key=["linux"], version=["linux5.19"], type=EXPLICIT_CONFIG_FILE, autosave=True),
                expected=Config(path=os.path.join(self.tmp.name, "loader/entries/lifeboat_12345_arch.conf"), root=self.tmp.name,
                                title=[f'Arch Linux @{pretty_date(ts)}'], linux=["/lifeboat_12345_vmlinuz-linux"], initrd=["/lifeboat_12345_initramfs-linux.img"], sort_key=["linux"], version=["-linux5.19-12345"], type=EXPLICIT_CONFIG_FILE)
            ),
            Test(
                name="auto-generated efi path",
                config=Config(path=os.path.join(self.tmp.name, "/EFI/Arch/linux.efi"), root=self.tmp.name,
                              title=['Arch Linux'], linux=['/EFI/Arch/linux.efi'], sort_key=["linux"], version=["linux5.19"], type=AUTO_EFI_CONFIG, autosave=True),
                expected=Config(path=os.path.join(self.tmp.name, "loader/entries/lifeboat_12345_linux.conf"), root=self.tmp.name,
                                title=[f'Arch Linux @{pretty_date(ts)}'], linux=["/EFI/Arch/lifeboat_12345_linux.efi"], sort_key=["linux"], version=["-linux5.19-12345"], type=EXPLICIT_CONFIG_FILE)
            ),
            Test(
                name="linux with multiple initrd",
                config=Config(path=os.path.join(self.tmp.name, "loader/entries/arch.conf"), root=self.tmp.name,
                              title=['Arch Linux'], linux=['/vmlinuz-linux'],
                              initrd=['/initramfs-linux.img',
                                      '/intel-ucode.img', '/amd-ucode.img'],
                              sort_key=["linux"], version=["linux5.19"], autosave=True, type=EXPLICIT_CONFIG_FILE),
                expected=Config(path=os.path.join(self.tmp.name, "loader/entries/lifeboat_12345_arch.conf"), root=self.tmp.name,
                                title=[f'Arch Linux @{pretty_date(ts)}'], linux=["/lifeboat_12345_vmlinuz-linux"],
                                initrd=["/lifeboat_12345_initramfs-linux.img",
                                        "/lifeboat_12345_intel-ucode.img", '/lifeboat_12345_amd-ucode.img'],
                                sort_key=["linux"], version=["-linux5.19-12345"], type=EXPLICIT_CONFIG_FILE)
            ),
        ]
        for test in tests:
            with self.subTest(test['name']):
                self.reset()
                with open(os.path.join(self.tmp.name, 'EFI', 'Arch', 'linux.efi'), 'w') as fp:
                    fp.write('my cool efi')

                with open(os.path.join(self.tmp.name, 'vmlinuz-linux'), 'w') as fp:
                    fp.write('my cool /linux')

                with open(os.path.join(self.tmp.name, 'initramfs-linux.img'), 'w') as fp:
                    fp.write('my cool /initramfs-linux.img')

                with open(os.path.join(self.tmp.name, 'intel-ucode.img'), 'w') as fp:
                    fp.write('my cool /intel-ucode.img')

                with open(os.path.join(self.tmp.name, 'amd-ucode.img'), 'w') as fp:
                    fp.write('my cool /amd-ucode.img')

                self.assertEqual(test['expected'], dc.replace(test['config'].create_lifeboat(ts), autosave=False))

                if test['config'].efi:
                    with open('/'.join([test['expected'].root, test['expected'].efi[0]]), encoding='utf8') as fp:
                        self.assertEqual('my cool efi', fp.read())

                if test['config'].linux and test['config'].type == EXPLICIT_CONFIG_FILE:
                    with open('/'.join([test['expected'].root, test['expected'].linux[0]]), encoding='utf8') as fp:
                        self.assertEqual('my cool /linux', fp.read())
                if test['config'].linux and test['config'].type == AUTO_EFI_CONFIG:
                    with open('/'.join([test['expected'].root, test['expected'].linux[0]]), encoding='utf8') as fp:
                        self.assertEqual('my cool efi', fp.read())

                for name, path in zip(test['config'].initrd, test['expected'].initrd):
                    with open('/'.join([test['expected'].root, path]), encoding='utf8') as fp:
                        self.assertEqual(f'my cool {name}', fp.read())

    def test_equivalent(self):
        with open(os.path.join(self.tmp.name, 'EFI', 'Arch', 'linux.efi'), 'w') as fp:
            fp.write('my cool efi')
        with open(os.path.join(self.tmp.name, 'EFI', 'Arch', 'lifeboat_12345_linux.efi'), 'w') as fp:
            fp.write('my cool efi')
        with open(os.path.join(self.tmp.name, 'EFI', 'Arch', 'different.efi'), 'w') as fp:
            fp.write('my other efi')

        default_config = Config(path=os.path.join(self.tmp.name, "loader/entries/arch.conf"), root=self.tmp.name,
                                title=['Arch Linux'], efi=["/EFI/Arch/linux.efi"])

        class Test(TypedDict):
            name: str
            config: Config
            compare: Config
            expected: bool
        tests: list[Test] = [
            Test(
                name="identical configs are equivalent",
                config=default_config,
                compare=default_config,
                expected=True
            ),
            Test(
                name="configs with different titles are equivalent",
                config=default_config,
                compare=dc.replace(default_config, title=["my new title"]),
                expected=True
            ),
            Test(
                name="configs with different values are not",
                config=default_config,
                compare=dc.replace(default_config, options=["123"]),
                expected=False
            ),
            Test(
                name="configs pointing to the same efi file are equivalent",
                config=default_config,
                compare=dc.replace(default_config, path=os.path.join(
                    self.tmp.name, "loader/entries/lifeboat_12345_arch.conf")),
                expected=True
            ),
            Test(
                name="configs pointing to different efi files with the different md5 are not equivalent",
                config=default_config,
                compare=dc.replace(default_config, efi=['/EFI/Arch/different.efi']),
                expected=False
            ),
            Test(name="configs missing files are not equivalent",
                 config=default_config,
                 compare=dc.replace(default_config, efi=[]),
                 expected=False
                 ),

        ]
        for test in tests:
            with self.subTest(test['name']):
                actual = test['config'].equivalent(test['compare'])
                self.assertEqual(test['expected'], actual)


class TestChroot(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.tmp = TemporaryDirectory()
        self.tmp2 = TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, 'a', 'b', 'c'), exist_ok=True)
        os.makedirs(os.path.join(self.tmp2.name, 'a', 'b', 'c'), exist_ok=True)
        for path in ['a/a.txt', 'a/b/b.txt', 'a/b/c/c.txt']:
            with open(os.path.join(self.tmp.name, path), 'w', encoding='utf8') as fp:
                fp.write(path)
            with open(os.path.join(self.tmp2.name, path), 'w', encoding='utf8') as fp:
                fp.write(path)

        if os.getuid() != 0:
            self.skipTest('Must run unit tests as root')

    def tearDown(self) -> None:
        self.tmp.cleanup()
        self.tmp2.cleanup()
        super().tearDown()

    def test_chroot(self):
        tests: list[list[str]] = [
            ['/'],
            ['tmp'],
            ['tmp', 'tmp/a'],
            ['tmp/a', 'tmp'],
            ['tmp', 'tmp'],
            ['tmp', 'tmp/a', 'tmp/a/b'],
            ['tmp', 'tmp/a/b', 'tmp/a'],
            ['tmp', 'tmp2'],
            ['tmp', 'tmp2', 'tmp2/a', 'tmp/a'],
        ]
        for test in tests:
            with self.subTest(test):
                roots = []
                for path in test:
                    if path.startswith('tmp2'):
                        roots.append(self.tmp2.name + path[4:])
                    elif path.startswith('tmp'):
                        roots.append(self.tmp.name + path[3:])
                initial_fd_count = fd_count()
                expected_inodes = [inode(x) for x in roots]
                expected_inodes_after_exit = [x for x in reversed(expected_inodes[:-1])]
                expected_inodes_after_exit.append(inode('/'))
                chroots = [Chroot(x) for x in roots]

                for chroot, expected_inode in zip(chroots, expected_inodes):
                    chroot.__enter__()
                    self.assertEqual(expected_inode, inode('/'))
                    pass

                for chroot, expected_inode in zip(reversed(chroots), expected_inodes_after_exit):
                    chroot.__exit__(None, None, None)
                    self.assertEqual(expected_inode, inode('/'))

                self.assertEqual(initial_fd_count, fd_count())
                pass


class TestFileTracker(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.tmp = TemporaryDirectory()
        if os.getuid() != 0:
            self.skipTest('Must run unit tests as root')

    def tearDown(self) -> None:
        self.tmp.cleanup()
        super().tearDown()

    def test_no_op_without_exception(self):
        filepath = os.path.join(self.tmp.name, 'a.txt')
        with FileTracker() as tracker:
            tracker.track(filepath)
            with open(filepath, 'w', encoding='utf8') as fp:
                fp.write('hello')

        with open(filepath, 'r', encoding='utf8') as fp:
            self.assertEqual('hello', fp.read())

    def test_deletes_files_when_exception(self):
        a_path = os.path.join(self.tmp.name, 'a.txt')
        b_path = os.path.join(self.tmp.name, 'b.txt')
        with open(a_path, 'w', encoding='utf8') as fp:
            fp.write('hello')
        with open(b_path, 'w', encoding='utf8') as fp:
            fp.write('hello')

        def run_test():
            with FileTracker() as tracker:
                with Chroot(self.tmp.name):
                    tracker.track('a.txt')
                    tracker.track('b.txt')
                    tracker.track('c.txt')
                    raise ValueError('oh no')
        self.assertRaises(ValueError, run_test)
        self.assertEqual(0, len(os.listdir(self.tmp.name)))

    def test_does_nothing_when_handling_chroot_exception(self):
        a_path = os.path.join(self.tmp.name, 'a.txt')
        with open(a_path, 'w', encoding='utf8') as fp:
            fp.write('hello')

        def run_test():
            with FileTracker() as tracker:
                with Chroot(self.tmp.name):
                    tracker.track('a.txt')
                    raise ChrootError('oh no')
        self.assertRaises(ChrootError, run_test)
        with open(a_path, 'r', encoding='utf8') as fp:
            self.assertEqual('hello', fp.read())


def fd_count() -> int: return len(os.listdir("/proc/self/fd")) - 1
def inode(path) -> int: return os.stat(path).st_ino


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.tmp = TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, 'loader', 'entries'), exist_ok=True)
        os.makedirs(os.path.join(self.tmp.name, 'EFI', 'Arch'), exist_ok=True)

        if os.getuid() != 0:
            self.skipTest('Must run unit tests as root')

        self.patcher = patch('systemd_boot_lifeboat.get_bootctl_entries', lambda *args,
                             **kwargs: self.mock_bootctl_entries(*args, **kwargs))
        self.patcher.start()

        self.ts = 12345
        self.nowpatcher = patch('systemd_boot_lifeboat.now', lambda: self.ts)
        self.nowpatcher.start()

    def tearDown(self) -> None:
        self.tmp.cleanup()
        self.patcher.stop()
        self.nowpatcher.stop()
        super().tearDown()

    def test_end_to_end(self):
        with open(os.path.join(self.tmp.name, 'EFI', 'Arch', 'linux.efi'), 'w') as fp:
            fp.write('my cool efi')
        default_config = Config(path=os.path.join(self.tmp.name, "loader/entries/arch.conf"), root=self.tmp.name,
                                title=['Arch Linux'], efi=["/EFI/Arch/linux.efi"], autosave=True, is_default=True)
        expected_default_config = Config(path=os.path.join(self.tmp.name, "loader/entries/arch.conf"), root=self.tmp.name,
                                         title=['Arch Linux'], efi=["/EFI/Arch/linux.efi"], version=["version123"], sort_key=["linux"])

        def runner(default_config_path=default_config.path, max_lifeboats=2):
            main(default_sort_key='linux',
                 default_version='version123', max_lifeboats=max_lifeboats, default_config_path=default_config_path)

        # Verify the initial lifeboat gets created
        runner()
        self.assertEqual(expected_default_config, self.load_config(expected_default_config.path))
        first_lifeboat = self.load_config(os.path.join(self.tmp.name, 'loader/entries/lifeboat_12345_arch.conf'))
        self.assertListEqual(sorted([expected_default_config, first_lifeboat]),
                             sorted(self.mock_bootctl_entries()))
        self.assertTrue(first_lifeboat.equivalent(expected_default_config))
        with open(os.path.join(self.tmp.name, 'EFI', 'Arch', 'lifeboat_12345_linux.efi'), 'r', encoding='utf8') as fp:
            self.assertEqual("my cool efi", fp.read())

        self.ts = 12346
        # Now, try using the lifeboat config as the default and make sure main() throws
        self.assertRaises(ValueError, lambda: runner(default_config_path=first_lifeboat.path))
        self.ts = 12347

        # Calling the runner when the efi has changed should result in no changes
        runner()
        self.assertListEqual(sorted([expected_default_config, first_lifeboat]),
                             sorted(self.mock_bootctl_entries()))

        # Now if the efi file changes, we should create a new entry
        with open(os.path.join(self.tmp.name, 'EFI', 'Arch', 'linux.efi'), 'w') as fp:
            fp.write('my cool efi2')
        self.ts = 12348
        runner()
        second_lifeboat = self.load_config(os.path.join(self.tmp.name, 'loader/entries/lifeboat_12348_arch.conf'))
        self.assertListEqual(sorted([expected_default_config, first_lifeboat, second_lifeboat]),
                             sorted(self.mock_bootctl_entries()))
        with open(os.path.join(self.tmp.name, 'EFI', 'Arch', 'lifeboat_12348_linux.efi'), 'r', encoding='utf8') as fp:
            self.assertEqual("my cool efi2", fp.read())

        # If the efi file changes again, we should create a new entry and delete the oldest lifeboat
        with open(os.path.join(self.tmp.name, 'EFI', 'Arch', 'linux.efi'), 'w') as fp:
            fp.write('my cool efi3')
        self.ts = 12349
        runner()
        third_lifeboat = self.load_config(os.path.join(self.tmp.name, 'loader/entries/lifeboat_12349_arch.conf'))
        self.assertListEqual(sorted([expected_default_config, second_lifeboat, third_lifeboat]),
                             sorted(self.mock_bootctl_entries()))
        self.assertTrue(third_lifeboat.equivalent(expected_default_config))

    def load_config(self, filepath: str) -> Config:
        config = Config(path=filepath, root=self.tmp.name, autosave=False)
        with open(filepath, 'r', encoding='utf8') as fp:
            for line in fp.readlines():
                key, val = line.strip().split(maxsplit=1)
                key = re.sub('-', '_', key).lower()
                existing = getattr(config, key)
                existing.append(val)
        return config

    def mock_bootctl_entries(self):
        filepaths = [os.path.join(self.tmp.name, 'loader', 'entries', name)
                     for name in os.listdir(os.path.join(self.tmp.name, 'loader', 'entries'))]
        return [self.load_config(x) for x in filepaths]


if 'unittest.util' in __import__('sys').modules:
    # Show full diff in self.assertEqual.
    __import__('sys').modules['unittest.util']._MAX_LENGTH = 999999999


if __name__ == "__main__":
    unittest.main()
