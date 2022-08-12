#!/usr/bin/env python


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
