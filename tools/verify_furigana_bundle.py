"""Verify that the furigana reading dictionary is really in the build.

pykakasi is the fallback reading provider, and the ONLY one present in a fresh
install: fugashi/UniDic arrives later, if the user installs the Japanese pack in
Settings. It is also consulted on every annotation for compound readings. So if
`kanwadict4.db` is missing from the EXE, furigana silently disappears for most
users - `KakasiProvider._get_kks()` catches the FileNotFoundError, logs it, and
renders plain text. Nothing crashes, nothing is visibly wrong, and the build
looks fine. That is exactly the failure a build guard has to catch.

Two checks, because they fail for different reasons:

  --source  before building: is the data file present in the environment
            PyInstaller will collect from? Catches a broken/partial pykakasi
            install, or a wheel that stopped shipping the dictionary.

  --exe P   after building: did the data file actually reach the archive?
            Catches a spec that lost the `collect_data_files('pykakasi')` entry
            and any bundling failure PyInstaller only warned about.

The post-build check reads PyInstaller's own archive TOC rather than searching
the binary for a filename, so it cannot be fooled by the name appearing in some
other blob.

Usage:
    python tools/verify_furigana_bundle.py --source
    python tools/verify_furigana_bundle.py --exe dist/CrossTrans_v1.9.19.exe
"""
import argparse
import os
import sys

# The reading dictionary itself. The other pykakasi .db files map kana between
# romanization systems; this is the one that maps kanji to readings.
DATA_FILE = 'kanwadict4.db'

# Where it lands inside the archive. PyInstaller writes TOC names with the host
# separator, so compare on a normalized form.
BUNDLED_PATH = 'pykakasi/data/kanwadict4.db'


def _normalize(path: str) -> str:
    """Compare archive names without caring about the path separator."""
    return path.replace('\\', '/').lower()


def source_data_files():
    """Names PyInstaller would collect for pykakasi from this environment."""
    from PyInstaller.utils.hooks import collect_data_files
    return [source for source, _dest in collect_data_files('pykakasi')]


def check_source():
    """Check the build environment can supply the reading dictionary.

    Returns:
        (ok, message) - message is written to stdout by main() either way.
    """
    try:
        files = source_data_files()
    except Exception as e:
        return False, f"could not inspect pykakasi data files: {e}"

    for path in files:
        if _normalize(path).endswith(DATA_FILE):
            return True, f"{DATA_FILE} found in the build environment: {path}"
    return False, (f"{DATA_FILE} is NOT among pykakasi's data files "
                   f"({len(files)} collected). Reinstall pykakasi: "
                   f"pip install --force-reinstall pykakasi")


def archive_names(exe_path):
    """Names in the EXE's PyInstaller archive.

    Raises:
        Exception: if the file is missing or is not a PyInstaller archive.
    """
    from PyInstaller.archive.readers import CArchiveReader
    toc = CArchiveReader(exe_path).toc
    # dict in PyInstaller 6.x, list of entry tuples in older releases.
    return list(toc) if isinstance(toc, dict) else [entry[-1] for entry in toc]


def check_exe(exe_path):
    """Check a built EXE actually carries the reading dictionary.

    Returns:
        (ok, message)
    """
    if not os.path.isfile(exe_path):
        return False, f"no such file: {exe_path}"
    try:
        names = archive_names(exe_path)
    except Exception as e:
        return False, f"could not read the PyInstaller archive in {exe_path}: {e}"

    wanted = _normalize(BUNDLED_PATH)
    for name in names:
        if _normalize(str(name)) == wanted:
            return True, f"{BUNDLED_PATH} is bundled ({len(names)} archive entries)"
    return False, (f"{BUNDLED_PATH} is MISSING from {exe_path}. Furigana would "
                   f"fall back to plain text for every user without the Japanese "
                   f"NLP pack. Check collect_data_files('pykakasi') in "
                   f"CrossTrans.spec")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--source', action='store_true',
                        help='check the build environment (run before building)')
    parser.add_argument('--exe', metavar='PATH',
                        help='check a built EXE (run after building)')
    args = parser.parse_args(argv)

    if not args.source and not args.exe:
        parser.error('nothing to check: pass --source and/or --exe')

    ok = True
    if args.source:
        passed, message = check_source()
        print(f"[furigana bundle] source: {'OK' if passed else 'FAILED'} - {message}")
        ok = ok and passed
    if args.exe:
        passed, message = check_exe(args.exe)
        print(f"[furigana bundle] exe:    {'OK' if passed else 'FAILED'} - {message}")
        ok = ok and passed
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
