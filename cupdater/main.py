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
from .backend import InstallerBackend
from .frontend import TUIFrontend, GUIFrontend


PROVISIONING_EMBEDDED_HEADER = b"@@@CUPMANIFESTURL@@@"
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
            link = data.decode("utf-8")
            if link.startswith("http"):
                return link.strip()
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
    parser.add_argument("-m", "--manifest", help="Package manifest URL", default=get_default_package_manifest())
    parser.add_argument("-b", "--branch", help="Use special package branch", default=None)
    parser.add_argument("-i", "--installdir", help="Use custom installation directory", default=None)
    parser.add_argument("--console", help="Use console instead of the GUI", action="store_true", default=not get_default_gui())
    parser.add_argument("-v", "--verbose", help="Enable verbose logging", action="store_true")
    parser.add_argument("-f", "--force", help="Force recheck manifest", action="store_true")
    parser.add_argument("--noselfupdate", help="Skip checking for self-update", action="store_true")
    parser.add_argument("--http-timeout", help="Set HTTP download timeout for content", default=1800)
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    frontend = TUIFrontend() if args.console else GUIFrontend()
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
    if args.installdir is None:
        backend.use_default_install_dir()
    else:
        try:
            os.chdir(args.installdir)
        except FileNotFoundError:
            frontend.fatal("Installation directory " + args.installdir + " was not found. Please check that the folder exists and has correct write permissions set up.")
    backend.set_branch(args.branch if args.branch is not None else "public")
    await backend.update(force=args.force, ignore_self_update=args.noselfupdate)
    if args.console:
        input("Press ENTER to continue...")

def main():
    asyncio.run(amain())