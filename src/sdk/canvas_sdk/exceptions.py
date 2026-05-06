from __future__ import annotations


class CanvasException(Exception):
    """Base class for all Canvas SDK exceptions."""


class InvalidAccessToken(CanvasException):
    """The provided access token is invalid or expired (HTTP 401)."""


class Forbidden(CanvasException):
    """The user lacks permission to access the resource (HTTP 403)."""


class ResourceNotFound(CanvasException):
    """The requested resource does not exist (HTTP 404)."""


class Conflict(CanvasException):
    """The request conflicts with current resource state (HTTP 409)."""


class UnprocessableEntity(CanvasException):
    """The request is well-formed but cannot be processed due to semantic errors (HTTP 422)."""


class RateLimitExceeded(CanvasException):
    """The request was throttled; raised after retries are exhausted (HTTP 429)."""


class CanvasServerError(CanvasException):
    """The Canvas API returned a server-side error (HTTP 5xx)."""
