from .frontend import Frontend

class GUIFrontend(Frontend):
    def __init__(self, nopause=False) -> None:
        super().__init__()