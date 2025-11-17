# copyright (c) 2018- polygoniq xyz s.r.o.

import typing
import collections.abc


class BaseSerializationError(Exception):
    """Base class for all config serialization errors."""

    def __init__(
        self,
        serialized_obj: typing.Any,
        message: str,
        *args,
    ):
        super().__init__(*args)
        self.message = message
        self.serialized_obj = serialized_obj

    def __str__(self):
        return f"{type(self.serialized_obj).__name__}: {self.message}"


class InvalidConfigError(BaseSerializationError):
    """Raised when the loaded config has an invalid format."""

    pass


class UnsupportedVersionError(BaseSerializationError):
    """Raised when the versions of the code and the loaded config are incompatible."""

    def __init__(
        self,
        serialized_obj: typing.Any,
        supported_version: int,
        loaded_version: int,
        *args,
    ):
        super().__init__(
            serialized_obj,
            f"Supported version is {supported_version}, but loaded version is {loaded_version}",
            *args,
        )
        self.expected_version = supported_version
        self.loaded_version = loaded_version


class SerializationError(BaseSerializationError):
    """Raised when the provided class cannot be serialized based on the provided rules.

    Note: this error is caused by wrong use of `serialization_bpy` API.
    """

    pass


class AttributeSerializationError(SerializationError):
    """Raised when the provided attribute cannot be serialized based on the provided rules.

    Note: this error is caused by wrong use of `serialization_bpy` API.
    """

    def __init__(self, serialized_obj: typing.Any, attribute_name: str, message: str, *args):
        super().__init__(serialized_obj, message, *args)
        self.attribute_name = attribute_name

    def __str__(self):
        return f"{type(self.serialized_obj).__name__}.{self.attribute_name}: {self.message}"


class DeserializationError(BaseSerializationError):
    """Raised when the provided class cannot be deserialized based on the provided rules."""

    pass


class AttributeDeserializationError(DeserializationError):
    """Raised when the provided attribute cannot be deserialized based on the provided rules."""

    def __init__(self, serialized_obj: typing.Any, attribute_name: str, message: str, *args):
        super().__init__(serialized_obj, message, *args)
        self.attribute_name = attribute_name

    def __str__(self):
        return f"{type(self.serialized_obj).__name__}.{self.attribute_name}: {self.message}"


class DataDeserializationError(DeserializationError):
    """Raised when the provided data are not valid for deserialization.

    Note: this error is caused by loading data that do not match the expected format or type.
    """

    def __init__(self, serialized_obj: typing.Any, attribute_name: str, message: str, *args):
        super().__init__(serialized_obj, message, *args)
        self.attribute_name = attribute_name

    def __str__(self):
        return f"{type(self.serialized_obj).__name__}.{self.attribute_name}: {self.message}"


class DeserializationErrorGroup(ExceptionGroup, DeserializationError):
    """Raised when one or more errors occur during deserialization of attributes."""

    def __new__(
        cls,
        serialized_obj: typing.Any,
        message: str,
        errors: collections.abc.Sequence[Exception],
    ):
        return ExceptionGroup.__new__(
            cls,
            message,
            errors,
        )

    def __init__(
        self,
        serialized_obj: typing.Any,
        message: str,
        errors: collections.abc.Sequence[Exception],
    ):
        super().__init__(message, errors)
        self.serialized_obj = serialized_obj

    def __str__(self):
        return f"{type(self.serialized_obj).__name__}: {super().__str__()}"

    def derive(self, errors):
        return DeserializationErrorGroup(self.serialized_obj, self.message, errors)
