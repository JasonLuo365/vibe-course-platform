import argparse
from importlib.metadata import version


def main():
    p = argparse.ArgumentParser(prog="vibe-submit")
    p.add_argument("--version", action="store_true")
    p.parse_args()
    print(f"vibe-submit {version('vibe-submit')}")
