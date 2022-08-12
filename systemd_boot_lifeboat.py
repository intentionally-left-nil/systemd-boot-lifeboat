#!/usr/bin/env python

import os
import typing
from collections import OrderedDict


class Config(OrderedDict[str, str]):
    filename: str

    def __init__(self, filename: str):
        super().__init__()
        self.filename = filename
        with open(self.filename, 'r', encoding='utf8') as fp:
            lines = fp.readlines()
            lines = [x.strip() for x in lines]
            lines = [x for x in lines if not x.startswith('#')]
            keyvals = [x.split() for x in lines]
            keyvals = [x for x in keyvals if len(x) == 2]
            for [key, val] in keyvals:
                self[key] = val

    def write(self):
        with open(self.filename, 'w', encoding='utf8') as fp:
            lines = [f"{key}\t{value}\n" for [key, value] in self.items()]
            fp.writelines(lines)


def get_default_config(esp: str) -> typing.Optional[Config]:
    try:
        loader = Config(os.path.join(esp, 'loader', 'loader.conf'))
        if 'default' in loader:
            config_filename = os.path.join(esp, 'loader', 'entries', f"{loader['default']}.conf")
            return Config(config_filename)
    except FileNotFoundError:
        return None
