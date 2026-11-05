"""Load a skill script by folder (the folder names have hyphens) and isolate trader/."""

import importlib.util
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")
sys.path.insert(0, os.path.join(ROOT, "trader-common"))


def load(folder, name):
    path = os.path.join(ROOT, folder, name + ".py")
    spec = importlib.util.spec_from_file_location("bt_" + folder.replace("-", "_") + "_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fixture(*parts):
    return os.path.join(FIX, *parts)


def read(*parts, mode="r"):
    with open(fixture(*parts), mode, **({} if "b" in mode else {"encoding": "utf-8"})) as fh:
        return fh.read()


class TraderDir:
    """with TraderDir(now="2026-11-05T11:00") as d: ... -> a fresh TRADER_DIR."""

    def __init__(self, now="2026-11-05T11:00"):
        self.now = now

    def __enter__(self):
        self.tmp = tempfile.mkdtemp()
        self.dir = os.path.join(self.tmp, "trader")
        os.makedirs(self.dir)
        self.old = {k: os.environ.get(k) for k in ("TRADER_DIR", "TRADER_NOW")}
        os.environ["TRADER_DIR"] = self.dir
        os.environ["TRADER_NOW"] = self.now
        return self

    def path(self, name):
        return os.path.join(self.dir, name)

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)
