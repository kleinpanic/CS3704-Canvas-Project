"""
Custom exceptions raised by the Canvas API.
"""

from typing import Any


class CanvasException(Exception):
    """
    Base class for all errors returned by the Canvas API.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BadRequest(CanvasException):
    """
    Raised when the API returns a 400 error.
    """

    pass


class Unauthorized(CanvasException):
    """
    Raised when the API returns a 401 error.
    """

    pass


class Forbidden(CanvasException):
    """
    Raised when the API returns a 403 error.
    """

    pass


class RateLimitExceeded(CanvasException):
    """
    Raised when the API returns a 429 error.
    """

    pass


class ResourceDoesNotExist(CanvasException):
    """
    Raised when the API returns a 404 error.
    """

    pass


class Conflict(CanvasException):
    """
    Raised when the API returns a 409 error.
    """

    pass


class UnprocessableEntity(CanvasException):
    """
    Raised when the API returns a 422 error.
    """

    pass


class InvalidAccessToken(CanvasException):
    """
    Raised when the API returns an invalid access token error.
    """

    pass


class RequiredFieldMissing(CanvasException):
    """
    Raised when a required parameter is missing from the request.
    """

    pass
