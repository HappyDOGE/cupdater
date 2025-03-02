import asyncio
import logging
import sys
from tqdm import tqdm
from .frontend import Frontend, ProgressReportInterface


logger = logging.getLogger(__name__)

async def ainput(string: str) -> str:
    def writenflush(string: str):
        sys.stdout.write(string)
        sys.stdout.flush()
    await asyncio.to_thread(writenflush, f'{string} ')
    return (await asyncio.to_thread(sys.stdin.readline)).rstrip("\n")

class TUIProgressReport(ProgressReportInterface):
    _tqdm: tqdm
    def __init__(self, title, total=None, unit=None, leave=True) -> None:
        self._tqdm = tqdm(desc=title, total=total, unit=unit if unit else "it", leave=leave, position=tqdm._get_free_pos()) # type: ignore
    def __enter__(self):
        self._tqdm.reset()
        self._tqdm.refresh()
        return self
    def __exit__(self, exception_type, exception_value, exception_traceback):
        self._tqdm.close()
    def update(self, count=1):
        self._tqdm.update(count)
    def set(self, value):
        self._tqdm.update(value - self._tqdm.n)
    def status(self, status):
        self._tqdm.write(status)

class TUIFrontend(Frontend):
    def __init__(self) -> None:
        super().__init__()
    def notify(self, notice):
        logger.info(notice)
    async def ask(self, question):
        return await ainput(question)
    def fatal(self, error):
        logger.fatal(error)
        input("Press ENTER to continue...")
        sys.exit(1)
    def progress(self, title, total=None, unit=None, leave=True):
        return TUIProgressReport(title, total=total, unit=unit, leave=leave)
    def set_branding(self, branding):
        pass