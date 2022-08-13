#!/usr/bin/env python
from __future__ import annotations
import errno
from functools import total_ordering
from multiprocessing.sharedctypes import Value

import os
import typing
import re
from collections import OrderedDict
import shutil


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

    def write(self):
        with open(self.filepath, 'x', encoding='utf8') as fp:
            lines = [f"{key}\t{value}\n" for [key, value] in self.items()]
            fp.writelines(lines)


def copy(src: str, target: str):
    if os.path.exists(target):
        raise OSError(errno.EEXIST, os.strerror(errno.EEXIST))
    shutil.copy2(src, target)
    st = os.stat(src)
    os.chown(target, st.st_uid, st.st_gid)


def delete_file(filepath: str):
    try:
        os.remove(filepath)
    except OSError:
        pass


@total_ordering
class Lifeboat(Config):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timestamp()  # side effect to ensure the filepath is valid

    def timestamp(self) -> int:
        match = re.search(r'^lifeboat_(\d+)_', os.path.basename(self.filepath))
        if match is None:
            raise ValueError(f"{self.filepath} does not contain a timestamp")
        return int(match.group(1))

    @classmethod
    def get_existing(cls, esp: str) -> list[Lifeboat]:
        config_dir = os.path.join(esp, 'loader', 'entries')
        config_paths = [os.path.join(config_dir, x) for x in os.listdir(config_dir) if x.startswith('lifeboat_')]
        return sorted([cls(x) for x in config_paths])

    @classmethod
    def lifeboat_path(cls, filepath: str, ts: int) -> str:
        dir = os.path.dirname(filepath)
        name = os.path.basename(filepath)
        return os.path.join(dir, f"lifeboat_{ts}_{name}")

    @classmethod
    def from_default_config(cls, config: Config, ts: int) -> Lifeboat:
        lifeboat_name = cls.lifeboat_path(config.filepath, ts)
        lifeboat = cls(lifeboat_name, config, ignore_missing=True)
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


def get_default_config(esp: str) -> typing.Optional[Config]:
    try:
        loader = Config(os.path.join(esp, 'loader', 'loader.conf'))
        if 'default' in loader:
            config_filename = os.path.join(esp, 'loader', 'entries', f"{loader['default']}.conf")
            c = Config(config_filename)
            return c
    except FileNotFoundError:
        return None
