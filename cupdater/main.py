import asyncio
import gevent.monkey

gevent.monkey.patch_all()
import gevent
import asyncio_gevent
asyncio.set_event_loop_policy(asyncio_gevent.EventLoopPolicy())

import zipfile_zstd # Hotpatch zipfile for later remotezip usage
import remotezip # Load remotezip so it loads the patched zipfile version

import logging
import traceback
import sys, os
import argparse
import mmap
import json
from pathlib import Path

from .backend import InstallerBackend
from .frontend import TUIFrontend, GUIFrontend
from .backend.filedb import UPDATE_DATA_DB_FILENAME


PROVISIONING_EMBEDDED_HEADER = b"@@@CUPMANIFESTCFG@@@"
def get_embedded_package_manifest():
    '''
    Extract the embedded manifest URL from the executable. None if file is not openable / none found.
    '''
    if not (getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")):
        return None # not a frozen executable build
    with open(sys.executable, "rb") as f, \
            mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as e:
        pos = e.find(PROVISIONING_EMBEDDED_HEADER)
        if pos is None:
            return None # provisioning manifest url not found in executable data
        e.seek(pos + len(PROVISIONING_EMBEDDED_HEADER))
        data = e.read()
        try:
            data = data.decode("utf-8")
            if data.startswith("{"):
                return data.strip()
        except:
            pass
        return None

def get_default_package_manifest():
    '''
    Try getting default manifest information from provisioning.
    '''
    embedded = get_embedded_package_manifest()
    if embedded is not None:
        return embedded
    return None

def get_default_gui():
    return False # TODO
    # return sys.platform == "win32" or "DISPLAY" in os.environ

async def amain():
    # Hello, world!
    parser = argparse.ArgumentParser(
        prog="cupdater",
        description="Updater and launcher"
    )
    manifest_configuration = get_default_package_manifest()
    if manifest_configuration is not None:
        manifest_configuration = json.loads(manifest_configuration)
    parser.add_argument("-m", "--manifest", help="Package manifest URL", default=manifest_configuration["url"] if manifest_configuration is not None else None)
    parser.add_argument("-b", "--branch", help="Use special package branch", default=None)
    parser.add_argument("-i", "--installdir", help="Use custom installation directory", default=None)
    parser.add_argument("--console", help="Use console instead of the GUI", action="store_true", default=not get_default_gui())
    parser.add_argument("-v", "--verbose", help="Enable verbose logging", action="store_true")
    parser.add_argument("-f", "--force", help="Force recheck manifest", action="store_true")
    parser.add_argument("--noselfupdate", help="Skip checking for self-update", action="store_true")
    parser.add_argument("--http-timeout", help="Set HTTP download timeout for content", default=3600)
    parser.add_argument("--nopause", help="Don't wait for user input, just exit the process", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    frontend = TUIFrontend(nopause=args.nopause) if args.console else GUIFrontend(nopause=args.nopause)
    use_manifest_configuration_installdir = manifest_configuration is not None and "installdir" in manifest_configuration
    if args.installdir is not None:
        try:
            os.chdir(args.installdir)
        except FileNotFoundError:
            frontend.fatal("Installation directory " + args.installdir + " was not found. Please check that the folder exists and has correct write permissions set up.")
    elif use_manifest_configuration_installdir:
        try:
            idir = Path(os.curdir) / manifest_configuration["installdir"] # type: ignore
            if idir.exists() or not (Path(os.curdir) / UPDATE_DATA_DB_FILENAME).exists(): # if FileDB database is in our current dir, there is no need to move
                idir.mkdir(parents=True, exist_ok=True)
                os.chdir(idir)
        except (FileNotFoundError, PermissionError):
            frontend.fatal("Installation directory " + args.installdir + " was not found and could not be created. Please check that the folder has correct write permissions set up.")
    backend = InstallerBackend(frontend, timeout=args.http_timeout)
    manifest = args.manifest
    if manifest is None:
        manifest = await frontend.ask("Please enter the manifest URL:")
        if isinstance(manifest, str):
            manifest = manifest.strip()
    if manifest is None or len(manifest) == 0:
        frontend.fatal("Cannot update without manifest URL present. Please enter the correct manifest URL.")
    try:
        await backend.load_manifest_from_url(manifest, force=args.force)
    except Exception as e:
        if args.verbose: traceback.print_exc()
        frontend.fatal("Manifest load error: " + str(e) + ". Please try again later or contact support.")
    backend.set_branch(args.branch if args.branch is not None else "public")
    await backend.update(force=args.force, ignore_self_update=args.noselfupdate)
    frontend.pause()

def main():
    asyncio.run(amain())