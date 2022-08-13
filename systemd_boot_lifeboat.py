#!/usr/bin/env python
from __future__ import annotations
from collections import OrderedDict
from functools import total_ordering
from multiprocessing.sharedctypes import Value

import datetime
import errno
import hashlib
import os
import re
import shutil
import time


def main(*, esp, max_lifeboats=2):
    if max_lifeboats <= 1:
        raise ValueError(f'max_lifeboats{max_lifeboats} must be > 1')

    config = get_default_config(esp)
    existing_lifeboats = Lifeboat.get_existing(esp)
    for lifeboat in existing_lifeboats:
        if lifeboat.equivalent(config):
            print(f'{config.basename()} is already backed up to {lifeboat.basename()}\n Nothing to do')
            return

    while len(existing_lifeboats) >= max_lifeboats:
        lifeboat = existing_lifeboats[0]
        existing_lifeboats = existing_lifeboats[1:]
        print(f'Deleting old lifeboat {lifeboat.basename}')
        lifeboat.remove()

    now = int(time.time())
    lifeboat = Lifeboat.from_default_config(config, now)
    print(f'Created new backup to {lifeboat.basename()}')


class Config(OrderedDict[str, str]):
    filepath: str

    def __init__(self, filepath: str, *args, **kwargs):
        ignore_missing = kwargs.pop('ignore_missing', None)
        super().__init__(*args, **kwargs)
        self.filepath = filepath
        try:
            with open(self.filepath, 'r', encoding='utf8') as fp:
                lines = fp.readlines()
                lines = [x.strip() for x in lines]
                lines = [x for x in lines if not x.startswith('#')]
                keyvals = [x.split(maxsplit=1) for x in lines]
                keyvals = [x for x in keyvals if len(x) == 2]
                for [key, val] in keyvals:
                    self[key] = val
        except OSError:
            if not ignore_missing:
                raise

    def basename(self) -> str:
        return os.path.basename(self.filepath)

    def write(self):
        with open(self.filepath, 'x', encoding='utf8') as fp:
            lines = [f"{key}\t{value}\n" for [key, value] in self.items()]
            fp.writelines(lines)


def copy(src: str, target: str):
    print(f'copying {src} to {target}')
    if os.path.exists(target):
        print(f'target already exists: {target}')
        raise OSError(errno.EEXIST, os.strerror(errno.EEXIST))
    shutil.copy2(src, target)
    st = os.stat(src)
    os.chown(target, st.st_uid, st.st_gid)


def delete_file(filepath: str):
    try:
        os.remove(filepath)
        print(f'Removed {filepath}')
    except OSError:
        pass


def md5(filepath: str) -> str:
    with open(filepath, 'rb') as fp:
        return hashlib.md5(fp.read()).hexdigest()


@total_ordering
class Lifeboat(Config):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timestamp()  # side effect to ensure the filepath is valid

    def timestamp(self) -> int:
        match = re.search(r'^lifeboat_(\d+)_', self.basename())
        if match is None:
            raise ValueError(f"{self.filepath} does not contain a timestamp")
        return int(match.group(1))

    def pretty_date(self) -> str:
        return datetime.datetime.fromtimestamp(self.timestamp()).strftime("%b %-d %Y %-H:%-M")

    @ classmethod
    def get_existing(cls, esp: str) -> list[Lifeboat]:
        config_dir = os.path.join(esp, 'loader', 'entries')
        config_paths = [os.path.join(config_dir, x) for x in os.listdir(config_dir) if x.startswith('lifeboat_')]
        return sorted([cls(x) for x in config_paths])

    @ classmethod
    def lifeboat_path(cls, filepath: str, ts: int) -> str:
        dir = os.path.dirname(filepath)
        name = os.path.basename(filepath)
        return os.path.join(dir, f"lifeboat_{ts}_{name}")

    @ classmethod
    def from_default_config(cls, config: Config, ts: int) -> Lifeboat:
        lifeboat_name = cls.lifeboat_path(config.filepath, ts)
        lifeboat = cls(lifeboat_name, config, ignore_missing=True)
        if 'title' in config:
            lifeboat['title'] += f'@{lifeboat.pretty_date()}'
        try:
            if 'efi' in config:
                lifeboat['efi'] = cls.lifeboat_path(config['efi'], ts)
                copy(config['efi'], lifeboat['efi'])
            lifeboat.write()
        except:
            if lifeboat['efi'] != config['efi']:
                delete_file(lifeboat['efi'])
            delete_file(lifeboat_name)
            raise
        return lifeboat

    def __eq__(self, other) -> bool:
        return self.filepath == other.filepath

    def __lt__(self, other) -> bool:
        return self.timestamp() < other.timestamp()

    def remove(self):
        if 'efi' in self:
            delete_file(self['efi'])
        delete_file(self.filepath)
        self.clear()

    def equivalent(self, other: Config) -> bool:
        ignore_keys = ['title']
        compare_md5_keys = ['efi']

        keys = [x for x in self.keys() if x not in ignore_keys]
        other_keys = [x for x in other.keys() if x not in ignore_keys]

        if len(keys) != len(other_keys):
            return False

        for key in keys:
            if key not in other:
                return False
            elif key in compare_md5_keys:
                try:
                    if md5(self[key]) != md5(other[key]):
                        return False
                except FileNotFoundError:
                    return False
            elif self[key] != other[key]:
                return False
        return True


def get_default_config(esp: str) -> Config:
    loader = Config(os.path.join(esp, 'loader', 'loader.conf'))
    if 'default' not in loader:
        raise ValueError('Missing default key in loader.conf ')

    config_filename = os.path.join(esp, 'loader', 'entries', f"{loader['default']}.conf")
    c = Config(config_filename)
    return c
