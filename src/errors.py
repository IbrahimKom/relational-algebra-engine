"""All error categories the engine can report. Every one of these is caught
at the top level (see cli.py) and printed as a clean message -- never a
Python traceback -- per assignment Section 6.3.
"""


class RAError(Exception):
    """Base class for every error the engine reports to the user."""

    category = "Error"

    def __init__(self, message, line=None, col=None):
        self.message = message
        self.line = line
        self.col = col
        super().__init__(message)

    def format(self):
        if self.line is not None:
            return f"{self.category} at line {self.line}, col {self.col}: {self.message}"
        return f"{self.category}: {self.message}"


class LexError(RAError):
    category = "Lexical error"


class ParseError(RAError):
    category = "Syntax error"


class NameResolutionError(RAError):
    category = "Name error"


class SchemaError(RAError):
    category = "Schema error"


class TypeCheckError(RAError):
    category = "Type error"
