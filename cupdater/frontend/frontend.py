class ProgressReportInterface:
    def __init__(self, title, total=None) -> None:
        pass
    def __enter__(self):
        raise NotImplementedError()
    def __exit__(self, exception_type, exception_value, exception_traceback):
        raise NotImplementedError()
    def update(self, count=1):
        raise NotImplementedError()
    def set(self, value):
        raise NotImplementedError()
    def status(self, status):
        raise NotImplementedError()

class Frontend:
    def notify(self, notice):
        raise NotImplementedError()
    async def ask(self, question):
        raise NotImplementedError()
    def fatal(self, error):
        raise NotImplementedError()
    def progress(self, title, total=None, unit=None, leave=True) -> ProgressReportInterface:
        raise NotImplementedError()