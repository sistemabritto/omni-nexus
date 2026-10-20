"""Static adapter failure codes; never forward upstream bodies or exception text."""


class AdapterError(ValueError):
    def __init__(self, code, status=400):
        self.code = code
        self.status = status
        super().__init__(code)
