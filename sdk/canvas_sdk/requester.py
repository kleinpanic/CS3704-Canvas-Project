"""Low-level HTTP client for the Canvas API — handles auth headers, request dispatch, and response parsing."""

import logging
from datetime import datetime
from pprint import pformat

import requests

from canvas_sdk.exceptions import (
    BadRequest,
    CanvasException,
    Conflict,
    Forbidden,
    InvalidAccessToken,
    RateLimitExceeded,
    ResourceDoesNotExist,
    Unauthorized,
    UnprocessableEntity,
)
from canvas_sdk.util import clean_headers

logger = logging.getLogger(__name__)

__version__ = "1.0.0"


class Requester:
    """Builds and sends HTTP requests to Canvas, with auth and error handling baked in."""

    def __init__(self, base_url: str, access_token: str):
        """
        :param base_url: Root URL for the Canvas instance (e.g. "https://vt.instructure.com").
        :type base_url: str
        :param access_token: API key used to authenticate requests.
        :type access_token: str
        """
        # Preserve the original base url and add "/api/v1" to it
        self.original_url = base_url
        self.base_url = base_url + "/api/v1/"
        self.new_quizzes_url = base_url + "/api/quiz/v1/"
        self.graphql = base_url + "/api/graphql"
        self.access_token = access_token
        self._session = requests.Session()
        self._cache: list = []

    def _delete_request(self, url, headers, data=None, **kwargs):
        """Send a DELETE to the Canvas API and return the raw response."""
        return self._session.delete(url, headers=headers, data=data)

    def _get_request(self, url, headers, params=None, **kwargs):
        """Send a GET to the Canvas API and return the raw response."""
        return self._session.get(url, headers=headers, params=params)

    def _patch_request(self, url, headers, data=None, **kwargs):
        """Send a PATCH to the Canvas API and return the raw response."""
        return self._session.patch(url, headers=headers, data=data)

    def _post_request(self, url, headers, data=None, json=None):
        """Send a POST to the Canvas API and return the raw response. Handles file uploads."""
        if json:
            return self._session.post(url, headers=headers, params=data, json=json)

        # Grab file from data.
        files = None
        for field, value in data:
            if field == "file":
                if isinstance(value, dict) or value is None:
                    files = value
                else:
                    files = {"file": value}
                break

        # Remove file entry from data.
        data[:] = [tup for tup in data if tup[0] != "file"]

        return self._session.post(url, headers=headers, data=data, files=files)

    def _put_request(self, url, headers, data=None, **kwargs):
        """Send a PUT to the Canvas API and return the raw response."""
        return self._session.put(url, headers=headers, data=data)

    def request(
        self,
        method: str,
        endpoint: str = None,
        headers: dict = None,
        use_auth: bool = True,
        _url: str = None,
        _kwargs: list = None,
        json: bool = False,
        **kwargs,
    ):
        """
        Make a request to the Canvas API and return the response.

        :param method: HTTP method (GET, POST, DELETE, PUT, PATCH).
        :type method: str
        :param endpoint: Canvas API endpoint path.
        :type endpoint: str
        :param headers: Optional HTTP headers.
        :type headers: dict
        :param use_auth: If False, omit the Bearer token (used for public endpoints).
        :type use_auth: bool
        :param _url: Override the URL routing:
            - "new_quizzes" → new quiz endpoint
            - "graphql" → GraphQL endpoint
            - any other string → used as the full URL, ignoring endpoint
            If omitted, uses the standard REST API base URL.
        :type _url: str
        :param _kwargs: Pre-processed ``(key, value)`` tuples for query/body params.
        :type _kwargs: list
        :param json: When True, send body as JSON instead of form data (GraphQL uses this).
        :type json: bool
        :rtype: :class:`requests.Response`
        """
        # Check for specific URL endpoints available from Canvas. If not
        # specified, pass the given URL and move on.
        if not _url:
            full_url = "{}{}".format(self.base_url, endpoint)
        elif _url == "new_quizzes":
            full_url = "{}{}".format(self.new_quizzes_url, endpoint)
        elif _url == "graphql":
            full_url = self.graphql
        else:
            full_url = _url

        if not headers:
            headers = {}

        if use_auth:
            auth_header = {"Authorization": "Bearer {}".format(self.access_token)}
            headers.update(auth_header)

        if "User-Agent" not in headers:
            headers["User-Agent"] = f"python-canvas-sdk/{__version__}"

        # Convert kwargs into list of 2-tuples and combine with _kwargs.
        _kwargs = _kwargs or []
        _kwargs.extend(kwargs.items())

        # Do any final argument processing before sending to request method.
        for i, kwarg in enumerate(_kwargs):
            kw, arg = kwarg

            # Convert boolean objects to a lowercase string.
            if isinstance(arg, bool):
                _kwargs[i] = (kw, str(arg).lower())

            # Convert any datetime objects into ISO 8601 formatted strings.
            elif isinstance(arg, datetime):
                _kwargs[i] = (kw, arg.isoformat())

        # Determine the appropriate request method.
        if method == "GET":
            req_method = self._get_request
        elif method == "POST":
            req_method = self._post_request
        elif method == "DELETE":
            req_method = self._delete_request
        elif method == "PUT":
            req_method = self._put_request
        elif method == "PATCH":
            req_method = self._patch_request

        # Call the request method
        logger.info("Request: {method} {url}".format(method=method, url=full_url))
        logger.debug(
            "Headers: {headers}".format(headers=pformat(clean_headers(headers)))
        )

        if _kwargs:
            logger.debug("Data: {data}".format(data=pformat(_kwargs)))

        if json:
            logger.debug("JSON: {json}".format(json=pformat(json)))

        response = req_method(full_url, headers, _kwargs, json=json)
        logger.info(
            "Response: {method} {url} {status}".format(
                method=method, url=full_url, status=response.status_code
            )
        )
        logger.debug(
            "Headers: {headers}".format(
                headers=pformat(clean_headers(response.headers))
            )
        )

        try:
            logger.debug(
                "Data: {data}".format(data=pformat(response.content.decode("utf-8")))
            )
        except UnicodeDecodeError:
            logger.debug("Data: {data}".format(data=pformat(response.content)))
        except AttributeError:
            # response.content is None
            logger.debug("No data")

        # Add response to internal cache
        if len(self._cache) > 4:
            self._cache.pop()

        self._cache.insert(0, response)

        # Raise for status codes
        if response.status_code == 400:
            raise BadRequest(response.text)
        elif response.status_code == 401:
            if "WWW-Authenticate" in response.headers:
                raise InvalidAccessToken(response.json())
            else:
                raise Unauthorized(response.json())
        elif response.status_code == 403:
            raise Forbidden(response.text)
        elif response.status_code == 404:
            raise ResourceDoesNotExist("Not Found")
        elif response.status_code == 409:
            raise Conflict(response.text)
        elif response.status_code == 422:
            raise UnprocessableEntity(response.text)
        elif response.status_code == 429:
            raise RateLimitExceeded(
                "Rate Limit Exceeded. X-Rate-Limit-Remaining: {}".format(
                    response.headers.get("X-Rate-Limit-Remaining", "Unknown")
                )
            )
        elif response.status_code > 400:
            # generic catch-all for error codes
            raise CanvasException(
                "Encountered an error: status code {}".format(response.status_code)
            )

        return response
