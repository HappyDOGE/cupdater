import sys, os
import argparse
import mmap
import asyncio

from .backend import InstallerBackend
from .frontend import TUIFrontend, GUIFrontend

PROVISIONING_EMBEDDED_HEADER = b"@@@CUMANIFESTURL@@@"
def get_embedded_package_manifest():
    '''
    Extract the embedded manifest URL from the executable. None if file is not openable / none found.
    '''
    if not getattr(sys, "frozen", False):
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
    return sys.platform == "win32" or "DISPLAY" in os.environ

def main():
    # Hello, world!
    loop = asyncio.new_event_loop()
    parser = argparse.ArgumentParser(
        prog="cupdater",
        description="Updater and launcher"
    )
    parser.add_argument("-m", "--manifest", help="Package manifest URL", default=get_default_package_manifest())
    parser.add_argument("--console", help="Use console instead of the GUI", action="store_true", default=not get_default_gui())
    parser.add_argument("-b", "--branch", help="Use special package branch", default=None)
    args = parser.parse_args()
    frontend = TUIFrontend(loop) if args.console else GUIFrontend(loop)
    backend = InstallerBackend(frontend)
    manifest = args.manifest
    if manifest is None:
        manifest = frontend.ask("Please enter the manifest URL")
    if manifest is None:
        frontend.fatal("Cannot update without manifest URL present")
    try:
        backend.load_manifest_from_url(manifest)
    except Exception as e:
        frontend.fatal("Manifest load error: " + str(e))
    if args.branch is not None:
        backend.set_branch(args.branch)
    backend.update()
    backend.launch()

if __name__ == "__main__":
    main()