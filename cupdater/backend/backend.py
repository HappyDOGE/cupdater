import json
import logging
import os, sys
import traceback
from zipfile import ZipFile
import jsonschema
import asyncio
import aiohttp
import hashlib
import pathlib

from ..frontend import Frontend
from .filedb import FileDB
from .remotezip import RemoteZip

from .manifest import MANIFEST_SCHEMA


logger = logging.getLogger(__name__)

def sha256sum(filename):
    with open(filename, 'rb', buffering=0) as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

OLD_UPDATER_FILENAME = ".cupd.old"

class InstallerBackend:
    _tcp_connections: int
    _session: aiohttp.ClientSession

    _frontend: Frontend
    _db: FileDB
    _manifest: dict | None
    _unchanged: bool

    _selected_branch: str
    _selected_branch_data: dict
    
    _deletable_files: list[str]

    def __init__(self, frontend, tcp_connections=50, timeout=None) -> None:
        self._frontend = frontend
        self._tcp_connections = tcp_connections
        self._session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=self._tcp_connections), timeout=aiohttp.ClientTimeout(total=timeout))
        self._selected_branch = ""
        self._selected_branch_data = {}
        self._db = FileDB()
        self._manifest = None
        self._unchanged = False
        self._deletable_files = []
        if os.path.exists(OLD_UPDATER_FILENAME): os.unlink(OLD_UPDATER_FILENAME)

    def __del__(self):
        try:
            loop = asyncio.get_event_loop()
            asyncio.create_task(self._close_session())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._close_session())

    async def _close_session(self):
        if not self._session.closed:
            await self._session.close()

    def _unzip(self, filename):
        logger.info("Extracting %s", filename)
        with ZipFile(filename) as zf:
            zf.extractall()
            for f in zf.filelist:
                if not f.is_dir():
                    self._db.track_file(f.filename, f.CRC, os.path.getmtime(f.filename))
        logger.debug("Removing source archive %s", filename)
        os.unlink(filename)

    async def _download_file(self, url, filename, title=None):
        async with self._session.get(url) as response:
            size = int(response.headers.get("content-length", 0)) or None
            with self._frontend.progress(title if title else f"Downloading {filename}", \
                                         total=((size // 1024) if size else None), unit="KiB", leave=False) as p:
                with open(filename, mode="wb") as f, p:
                    async for chunk in response.content.iter_chunked(65536):
                        f.write(chunk)
                        p.update(len(chunk) // 1024)

    async def _download_file_with_retries(self, url, filename, title=None, retries=5):
        ee = None
        for r in range(retries, 0, -1):
            try:
                return await self._download_file(url, filename, title)
            except Exception as e:
                ee = e
                if logger.level == logging.DEBUG: traceback.print_exc()
                logger.warning("Failed to download URL %s: %s. %i retries left.", url, str(e), r-1)
                os.unlink(filename)
        await self._frontend.fatal(("Failed to download file %s after %i retries. Last error was: %s. " \
                                    "Please try again later or contact support." % 
                                   url, retries, str(ee)))

    async def _download_and_unzip(self, url):
        logger.debug("Downloading layer content archive %s fully since this is a clean install", url)
        filename = url.rpartition("/")[-1]
        logger.info("Downloading %s", filename)
        await self._download_file_with_retries(url, filename)
        await asyncio.to_thread(self._unzip, filename)

    async def _selective_download(self, url):
        logger.debug("Downloading layer content archive %s selectively", url)
        filename = url.rpartition("/")[-1]
        logger.debug("Loading archive %s", filename)
        with RemoteZip(url, proxies={"http": "", "https": ""}, support_suffix_range=False) as zf:
            new = []
            overwrite = []
            for f in zf.filelist:
                if not f.is_dir():
                    file_info = self._db.get_file(f.filename)
                    if not file_info:
                        # new file, add to tracking list
                        new.append(f)
                        continue
                    self._deletable_files.remove(f.filename)
                    _, dcrc, _ = file_info
                    if f.CRC != dcrc:
                        # overwrite updated file
                        overwrite.append(f)
                        continue
            to_download = (new + overwrite)
            with self._frontend.progress(f"Downloading {filename}", total=len(to_download), unit="file", leave=False) as p:
                for f in to_download:
                    p.update()
                    zf.extract(f)
            for f in new:
                self._db.track_file(f.filename, f.CRC, os.path.getmtime(f.filename))
            for f in overwrite:
                self._db.update_tracked_file(f.filename, f.CRC, os.path.getmtime(f.filename))

    async def load_manifest_from_url(self, url, force=False):
        MANIFEST_ETAG_CACHED_KEY = "manifest:cached"
        MANIFEST_ETAG_META_KEY = "manifest:cached:etag"
        etag = self._db.get_meta(MANIFEST_ETAG_META_KEY)
        use_etag = etag is not None and not force
        if use_etag:
            logger.debug("Found Etag for previous manifest download, will skip update if it hasn't changed")
        logger.info("Loading update manifest")
        async with await self._session.get(url, headers={
            "If-None-Match": etag if use_etag else ""
        }) as data: # type: ignore
            data.raise_for_status()
            if data.status == 304 and not force:
                logger.debug("Manifest is unchanged from a known state, nothing changed")
                self._unchanged = True
                self._manifest = json.loads(self._db.get_meta(MANIFEST_ETAG_CACHED_KEY, "{}")) # type: ignore
            else:
                if "Etag" in data.headers:
                    logger.debug("Saving manifest with Etag %s for later comparison", data.headers["Etag"])
                    self._db.set_meta(MANIFEST_ETAG_META_KEY, data.headers["Etag"])
                self._manifest = await data.json(content_type=None)
                self._db.set_meta(MANIFEST_ETAG_CACHED_KEY, json.dumps(self._manifest))
        assert self._manifest is not None
        jsonschema.validate(self._manifest, MANIFEST_SCHEMA)
        self._frontend.set_branding(self._manifest["brand"])
        logger.info("Updating %s", self._manifest["brand"]["name"])

    def set_branch(self, branch):
        if self._manifest is None:
            raise ValueError("Please load manifest first")
        if branch not in self._manifest["branches"].keys():
            raise ValueError("Branch " + branch + " does not exist in manifest")
        logger.info("Using branch %s", branch)
        self._selected_branch = branch
        self._selected_branch_data = self._manifest["branches"][branch]

    async def update(self, force=False, ignore_self_update=False):
        CLEAN_INSTALL_COMPLETE = "clean-install:complete"
        if self._manifest is None:
            self._frontend.fatal("Manifest is not loaded.")
            return
        if not ignore_self_update and getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            platform = "windows" if sys.platform == "win32" else ("linux" if sys.platform.startswith("linux") else "unknown")
            uhash = sha256sum(sys.executable)
            if platform in self._manifest["self"]:
                selfupdate_info = self._manifest["self"][platform]
                if uhash != selfupdate_info["sha256"]:
                    # need to update
                    self._frontend.fatal("An update is available, please download it from " + selfupdate_info["url"])
                    return
        logger.info("Indexing existing files")
        total, modified, removed = self._db.index_files()
        logger.debug("Total %i tracked files: %i modified, %i removed", len(total), len(modified), len(removed))
        layers = self._selected_branch_data["layers"]
        clean_install = (len(total) == 0 or not int(self._db.get_meta(CLEAN_INSTALL_COMPLETE, "0"))) # type: ignore
        if not clean_install:
            # populate deletable files list for later deletion
            self._deletable_files = [f[0] for f in total.copy()] # add all files, they will be removed during file download later
            if self._unchanged:
                logger.info("No update required")
                return
        else: self._db.clear_tracked_files()
        with self._frontend.progress("Loading layers", total=len(layers), leave=False) as p:
            for layer in layers:
                p.update()
                if layer not in self._manifest["layers"]:
                    self._frontend.fatal("Layer " + layer + " was not found in the manifest.")
                    break
                meta_key = f"manifest:layer:{layer}:updated"
                layer_data = self._manifest["layers"][layer]
                recorded_updated_value = int(self._db.get_meta(meta_key, "0")) # type: ignore
                if recorded_updated_value >= layer_data["updated"] and not force and not clean_install:
                    logger.debug("Layer " + layer + " was not changed since last update check")
                    continue
                if len(layer_data["url"]) == 0:
                    self._frontend.fatal("Layer " + layer + " does not have any content URLs")
                    break
                with self._frontend.progress("Loading layer " + layer, total=len(layer_data["url"]), leave=False) as lp:
                    tasks = []
                    for url in layer_data["url"]:
                        lp.update(1)
                        if clean_install:
                            # no point in selective download, just download and unzip all at once
                            tasks.append(asyncio.ensure_future(self._download_and_unzip(url)))
                        else:
                            tasks.append(asyncio.ensure_future(self._selective_download(url)))
                    await asyncio.gather(*tasks)
                self._db.set_meta(meta_key, str(layer_data["updated"]))
        for f in self._deletable_files: os.unlink(f)
        if clean_install: self._db.set_meta(CLEAN_INSTALL_COMPLETE, "1")
        self._frontend.notify("Update complete.")