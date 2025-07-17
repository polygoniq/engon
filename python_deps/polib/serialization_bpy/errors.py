# copyright (c) 2018- polygoniq xyz s.r.o.


class BaseSerializationError(Exception):
    """Base class for all config serialization errors"""

    def __init__(self, message: str, *args):
        super().__init__(*args)
        self.message = message

    def __str__(self):
        return self.message


class SerializationError(BaseSerializationError):
    """Raised when the provided data can't be serialized"""

    pass


class DeserializationError(BaseSerializationError):
    """Raised when the provided data can't be correctly deserialized"""

    pass


class InvalidConfigError(BaseSerializationError):
    """Raised when the loaded config has an invalid format"""

    pass


class UnsupportedVersionError(BaseSerializationError):
    """Raised when the versions of the code and the loaded config are incompatible"""

    pass
