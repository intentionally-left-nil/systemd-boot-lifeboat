#!/usr/bin/env python
from __future__ import annotations
import errno

import os
import typing
from collections import OrderedDict
import shutil


class Config(OrderedDict[str, str]):
    filepath: str

    def __init__(self, filepath: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filepath = filepath

    def load(self):
        with open(self.filepath, 'r', encoding='utf8') as fp:
            lines = fp.readlines()
            lines = [x.strip() for x in lines]
            lines = [x for x in lines if not x.startswith('#')]
            keyvals = [x.split(maxsplit=1) for x in lines]
            keyvals = [x for x in keyvals if len(x) == 2]
            for [key, val] in keyvals:
                self[key] = val

    def write(self):
        with open(self.filepath, 'x', encoding='utf8') as fp:
            lines = [f"{key}\t{value}\n" for [key, value] in self.items()]
            fp.writelines(lines)

    def create_lifeboat(self, ts: int) -> Config:
        lifeboat_name = lifeboat_path(self.filepath, ts)
        lifeboat = Config(lifeboat_name, self)
        try:
            if 'efi' in self:
                lifeboat['efi'] = lifeboat_path(self['efi'], ts)
                copy(self['efi'], lifeboat['efi'])
            lifeboat.write()
        except:
            if lifeboat['efi'] != self['efi']:
                delete_file(lifeboat['efi'])
            delete_file(lifeboat_name)
            raise

        return lifeboat


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


def lifeboat_path(filepath: str, ts: int) -> str:
    dir = os.path.dirname(filepath)
    name = os.path.basename(filepath)
    return os.path.join(dir, f"lifeboat_{ts}_{name}")


def get_default_config(esp: str) -> typing.Optional[Config]:
    try:
        loader = Config(os.path.join(esp, 'loader', 'loader.conf'))
        loader.load()
        if 'default' in loader:
            config_filename = os.path.join(esp, 'loader', 'entries', f"{loader['default']}.conf")
            c = Config(config_filename)
            c.load()
            return c
    except FileNotFoundError:
        return None
