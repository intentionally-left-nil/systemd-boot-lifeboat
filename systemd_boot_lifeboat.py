#! /usr/bin/env python
from __future__ import annotations
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import dataclasses as dc
import datetime
from functools import total_ordering
import hashlib
from itertools import dropwhile, takewhile
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from types import TracebackType
from typing import Any, Dict, Optional, NamedTuple, Type, Union

global DRY_RUN
DRY_RUN = False

class LifeboatError(ValueError):
    pass


def main(*, default_sort_key: str, default_version: str, max_lifeboats: int, default_config_path: Optional[str]):
    if max_lifeboats < 1:
        raise LifeboatError(f'max_lifeboats{max_lifeboats} must be > 1')
    if not default_config_path:
        default_config_path = get_default_config_path()

    configs = get_bootctl_entries()
    default_config = next((x for x in configs if x.path == default_config_path), None)
    if not default_config:
        raise LifeboatError(f'Could not find {default_config_path} in `bootcttl list`')

    print(f'using {default_config.path} as the default config')
    if default_config.is_lifeboat():
        raise LifeboatError(f'{default_config.basename()} is a lifeboat config and cannot be used as the default')

    if not default_config.sort_key:
        default_config = dc.replace(default_config, sort_key=[
                                    default_sort_key], autosave=True)

    if not default_config.version:
        default_config = dc.replace(default_config, version=[default_version], autosave=True)

    lifeboats = [x for x in configs if x.is_lifeboat()]
    lifeboats.sort(reverse=True)  # Sort from newest to oldest
    match = next((x for x in lifeboats if x.equivalent(default_config)), None)
    if match:
        print(f'{default_config.basename()} is already backed up to {match.basename()}\nNothing to do')
    else:
        while len(lifeboats) >= max_lifeboats:
            lifeboat = lifeboats.pop()
            print(f'Deleting old lifeboat {lifeboat.basename()}')
            lifeboat.remove()

        lifeboat = default_config.create_lifeboat(now())


@total_ordering
@dc.dataclass(frozen=True, kw_only=True)
class Config:
    path: str
    root: str
    autosave: bool = False
    is_default: bool = False
    title: list[str] = dc.field(default_factory=list)
    version: list[str] = dc.field(default_factory=list)
    machine_id: list[str] = dc.field(default_factory=list)
    sort_key: list[str] = dc.field(default_factory=list)
    linux: list[str] = dc.field(default_factory=list)
    initrd: list[str] = dc.field(default_factory=list)
    efi: list[str] = dc.field(default_factory=list)
    options: list[str] = dc.field(default_factory=list)
    devicetree: list[str] = dc.field(default_factory=list)
    devicetree_overlay: list[str] = dc.field(default_factory=list)
    architecture: list[str] = dc.field(default_factory=list)

    CONF_FIELDS = {'title', 'version', 'machine_id', 'sort_key', 'linux', 'initrd',
                   'efi', 'options', 'devicetree', 'devicetree_overlay', 'architecture'}
    METADATA_FIELDS = {'path', 'root', 'autosave'}
    BOOTCTL_FIELDS = CONF_FIELDS | {'path', 'root', 'is_default'}
    FIELDS_WITH_FILES = {'linux', 'initrd', 'efi'}
    EQUIVALENCY_IGNORE_FIELDS = METADATA_FIELDS | {'title', 'version', 'is_default'}

    @ classmethod
    def from_bootctl(cls, data: Dict[str, Union[str, list[str]]]) -> Config:
        def unbox(x: Union[str, list[str]]) -> str: return x[0] if isinstance(x, list) else x
        def box(x: Union[str, list[str]]) -> list[str]: return x if isinstance(x, list)else [x]
        # Convert camelCase into snake_case (simple version)
        data = {re.sub(r'([a-z])([A-Z])', r'\1_\2', k).lower(): v for k, v in data.items()}
        fieldTypes = {field.name: field.type for field in dc.fields(Config)}
        args: Any = {
            key: box(value) if fieldTypes[key] == 'list[str]' else unbox(value)
            for key, value in data.items()
            if key in cls.BOOTCTL_FIELDS
        }
        c = Config(**args)
        return c

    def __post_init__(self):
        if self.autosave:
            self.write()

    def basename(self) -> str: return os.path.basename(self.path)

    def create_lifeboat(self, ts: int) -> Config:
        # We want our version to be lower than the config version, so prefix it with -
        # Then, we want lifeboats to be sorted in-order according to their timestamp, so add that to the end of the existing version
        # See https://systemd.io/BOOT_LOADER_SPECIFICATION/#version-order
        with FileTracker() as tracker:
            new_args: Dict[str, list[str]] = {}
            with Chroot(self.root):
                for field in self.FIELDS_WITH_FILES:
                    new_args[field] = []
                    for file in getattr(self, field):
                        dest = self._lifeboat_path(file, ts)
                        copy_file(file, dest)
                        tracker.track(dest)
                        new_args[field].append(dest)

            if self.title:
                title = self.title[0]
            else:
                title = self.basename()

            config = dc.replace(self,
                                path=self._lifeboat_path(self.path, ts),
                                title=[f'{title} @{pretty_date(ts)}'],
                                version=[f'-{self.version[0]}-{ts}'],
                                autosave=True,
                                **new_args)
        return config

    def is_lifeboat(self) -> bool:
        try:
            self.timestamp()
            return True
        except ValueError:
            return False

    def timestamp(self) -> int:
        try:
            match = re.search(r'^lifeboat_(\d+)_', self.basename())
            if match is None:
                raise LifeboatError(f"{self.path} does not contain a timestamp")
            return int(match.group(1))
        except Exception as e:
            raise LifeboatError(f'{self.basename()} is not a lifeboat with a valid timestamp') from e

    def equivalent(self, other: Config) -> bool:
        try:
            return all(
                {self._md5(filepath) for filepath in getattr(self, field)} == {self._md5(filepath) for filepath in getattr(other, field)} if field in Config.FIELDS_WITH_FILES
                else getattr(self, field) == getattr(other, field)
                for field in Config.CONF_FIELDS - Config.EQUIVALENCY_IGNORE_FIELDS)
        except Md5Error as e:
            print(
                f'Warning: Could not open {e.filepath}. The config can not be considered equivalent because this file is missing')
            return False

    def to_conf(self) -> str:
        return '\n'.join([f'{re.sub("_", "-", field)}\t{val}'
                          for field in Config.CONF_FIELDS
                          for val in getattr(self, field)])

    def write(self):
        try:
            with Chroot('/'), open(self.path, 'w' if self.autosave else 'x', encoding='utf8') as fp:
                conf = self.to_conf()
                global DRY_RUN
                if DRY_RUN:
                    print(f"--dry-run prevents writing to {self.path}")
                else:
                    fp.write(conf)
                print(f'Created boot entry {next(iter(self.title), self.basename())} with contents:\n{conf}\n\n')
        except Exception as e:
            raise LifeboatError(f'Could not save config {self.basename()}') from e

    def remove(self):
        for field in Config.FIELDS_WITH_FILES:
            for file in getattr(self, field):
                delete_file(self.root, file)
        delete_file('/', self.path)

    def _md5(self, filepath) -> str:
        with Chroot(self.root):
            try:
                with open(filepath, 'rb') as fp:
                    return hashlib.md5(fp.read()).hexdigest()
            except Exception as e:
                raise Md5Error(filepath, f'Could not determine the md5 has for {filepath}') from e

    def _lifeboat_path(self, filepath: str, ts: int) -> str:
        dir = os.path.dirname(filepath)
        name = os.path.basename(filepath)
        return os.path.join(dir, f"lifeboat_{ts}_{name}")

    def __lt__(self, other: Config) -> bool:
        if self.is_lifeboat() and other.is_lifeboat():
            return self.timestamp() < other.timestamp()
        elif self.is_lifeboat() and not other.is_lifeboat():
            return False
        else:
            return self.path < other.path


def now() -> int: return int(time.time())


def pretty_date(ts: int) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%b %-d, %Y (%H:%M)")


class ChrootError(LifeboatError):
    pass


class Md5Error(LifeboatError):
    def __init__(self, filepath, *args, **kwargs):
        self.filepath = filepath
        super().__init__(*args, **kwargs)
    pass


class Chroot:
    class Root(NamedTuple):
        fd: int
        path: str
    roots: list[Root] = []

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.skip = False

    def __enter__(self):
        try:
            if (Chroot.roots and Chroot.roots[-1].path == self.filepath) or (self.filepath == '/' and not Chroot.roots):
                self.skip = True  # Nothing to do, we are already in the correct chroot
                return
            if not Chroot.roots:
                Chroot.roots.append(Chroot.Root(fd=os.open('/', os.O_RDONLY), path='/'))

            if len(Chroot.roots) > 1:
                os.fchdir(Chroot.roots[0].fd)
                os.chroot('.')
            root = Chroot.Root(fd=os.open(self.filepath, os.O_RDONLY), path=self.filepath)
            os.fchdir(root.fd)
            os.chroot('.')
            os.chdir('/')
            Chroot.roots.append(root)
            Chroot.current_path = self.filepath
        except Exception as e:
            raise ChrootError(f'Could not chroot to {self.filepath}') from e

    def __exit__(
        self, exc_type: Optional[Type[BaseException]], exc: Optional[BaseException], traceback: Optional[TracebackType]
    ) -> Optional[bool]:
        if self.skip:
            return
        try:
            os.close(Chroot.roots.pop().fd)
            os.fchdir(Chroot.roots[-1].fd)
            os.chroot('.')
            os.chdir('/')

            if len(Chroot.roots) == 1:
                os.close(Chroot.roots.pop().fd)
        except Exception as e:
            raise ChrootError(f'Could not recover chroot from {self.filepath}') from e


class FileTracker:
    class File(NamedTuple):
        path: str
        root: str

    def __init__(self):
        self.files: list[FileTracker.File] = []

    def __enter__(self) -> FileTracker: return self

    def track(self, filepath: str):
        self.files.append(FileTracker.File(path=filepath, root=Chroot.roots[-1].path if Chroot.roots else '/'))

    def __exit__(
        self, exc_type: Optional[Type[BaseException]], exc: Optional[BaseException], traceback: Optional[TracebackType]
    ) -> Optional[bool]:
        if exc is not None and not isinstance(exc, ChrootError):
            for file in self.files:
                delete_file(file.root, file.path)
        return False


def bootctl(args: list[str]) -> str:
    command = ['bootctl', '--no-pager']
    command.extend(args)
    with Chroot('/'):
        return subprocess.run(command, stdout=subprocess.PIPE).stdout.decode('utf8').strip()


def get_bootctl_entries() -> list[Config]:
    entries = json.loads(bootctl(['--json=short', 'list']))
    return [Config.from_bootctl(x) for x in entries if 'root' in x]


def get_default_path(path_type: str) -> str:
    return bootctl([f'--print-{path_type}-path'])


def get_default_config_path() -> str:
    entries = get_bootctl_entries()
    defaults = [x for x in entries if x.is_default]
    if len(defaults) != 1:
        raise LifeboatError('Could not determine the default entry from bootctl')
    return defaults[0].path


def copy_file(src: str, dest: str):
    global DRY_RUN
    if not os.path.exists(src):
        raise LifeboatError(
            f"Copying {os.path.basename(src)} to {os.path.basename(dest)} failed because {os.path.basename(src)} doesn't exist")
    print(f'Copying {src} to {dest}')
    if os.path.exists(dest):
        raise LifeboatError(f'Copying {os.path.basename(src)} failed because {os.path.basename(dest)} already exists')

    if DRY_RUN:
        print(f'--dry-run prevents copying {os.path.basename(src)} to {os.path.basename(dest)}')
        return
    try:
        shutil.copy2(src, dest)
        st = os.stat(src)
        os.chown(dest, st.st_uid, st.st_gid)
    except Exception as e:
        raise LifeboatError(f'Error copying {os.path.basename(src)} to {os.path.basename(dest)} failed') from e


def delete_file(root: str, filepath: str):
    if not filepath:
        print(f'Refusing to delete empty file at {root}')
        return

    with Chroot(root):
        global DRY_RUN
        if DRY_RUN:
            print(f'--dry-run prevents deleting {root}:{filepath}')
            return
        try:
            os.remove(filepath)
            print(f'Removed {root}:{filepath}')
        except OSError as e:
            print(f'Error {e} removing {root}:{filepath}, continuing')
            pass


if __name__ == '__main__':
    current_version = subprocess.run(['uname', '-r'], stdout=subprocess.PIPE).stdout.decode('utf8').strip()
    parser = ArgumentParser(description='Clone the boot entry if it has changed',
                            formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('-n', '--max-lifeboats', type=int, default=2)
    parser.add_argument('--default-sort-key', help='Default sort key to use, if not present', default='linux')
    parser.add_argument('--default-version', help='Default sort key to use, if not present', default=current_version)
    parser.add_argument('-c', '--default-config-path',
                        help='Fully qualified location to the conf file to use as a template for creating new lifeboats', default=None)
    parser.add_argument('--dry-run', help='Print what would actually happen, but take no action',
                        action='store_true', default=False)
    args = vars(parser.parse_args())
    if args.pop('dry_run', False):
        print('Setting dry run mode on')
        DRY_RUN = True

    try:
        main(**args)
    except LifeboatError as e:
        print(e)
        sys.exit(1)
    except Exception as e:
        print(traceback.format_exc())
        sys.exit(1)
