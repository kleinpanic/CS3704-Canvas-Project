"""Lazy iterator over paginated Canvas API endpoints — handles all the cursor following for you."""

from __future__ import annotations

import re
from typing import Iterable, Iterator, Type, TypeVar

T = TypeVar("T")


class PaginatedList(Iterable[T]):
    """
    Lazy list-like wrapper around paginated Canvas API endpoints.

    Iterating this object automatically fetches subsequent pages as needed, so you can
    simply ``for item in PaginatedList(...)`` without worrying about cursors or page limits.

    Supports normal list operations: indexing, slicing, ``len()``.

    See `Canvas pagination docs <https://canvas.instructure.com/doc/api/file.pagination.html>`_.
    """

    def __getitem__(self, index):
        assert isinstance(index, (int, slice))
        if isinstance(index, int):
            if index < 0:
                raise IndexError("Cannot negative index a PaginatedList")
            self._get_up_to_index(index)
            return self._elements[index]
        else:
            return self._Slice(self, index)

    def __init__(
        self,
        content_class: type[T],
        requester,
        request_method: str,
        first_url: str,
        extra_attribs: dict = None,
        _root: str = None,
        _url_override: str = None,
        **kwargs,
    ):
        """
        :param content_class: Type of objects this list should return.
        :type content_class: class
        :param requester: Requester instance for API calls.
        :type requester: :class:`canvas_sdk.requester.Requester`
        :param request_method: HTTP method (GET, POST, etc.).
        :type request_method: str
        :param first_url: Canvas API endpoint for the first page.
        :type first_url: str
        :param extra_attribs: Extra key-value pairs merged into every item (e.g. course_id).
        :type extra_attribs: dict
        :param _root: If the response nests data under a key (e.g. ``"courses"``), pass that key here.
        :type _root: str
        :param _url_override: "new_quizzes" or "graphql" to route to non-standard endpoints.
        :type _url_override: str
        :rtype: :class:`canvas_sdk.paginated_list.PaginatedList` of type content_class
        """
        self._elements: list = []

        self._requester = requester
        self._content_class = content_class
        self._first_url = first_url
        self._first_params: dict = kwargs or {}
        self._first_params["per_page"] = kwargs.get("per_page", 100)
        self._next_url = first_url
        self._next_params = self._first_params
        self._extra_attribs = extra_attribs or {}
        self._request_method = request_method
        self._root = _root
        self._url_override = _url_override

    def __iter__(self) -> Iterator[T]:
        for element in self._elements:
            yield element
        while self._has_next():
            new_elements = self._grow()
            for element in new_elements:
                yield element

    def __repr__(self):
        return "<PaginatedList of type {}>".format(self._content_class.__name__)

    def _get_next_page(self) -> list:
        response = self._requester.request(
            self._request_method,
            self._next_url,
            _url=self._url_override,
            **self._next_params,
        )
        data = response.json()
        self._next_url = None
        # Check the response headers first. This is the normal Canvas convention
        # for pagination, but there are endpoints which return a `meta` property
        # for pagination instead.
        # See https://github.com/kleinpanic/CS3704-Canvas-Project/discussions/605
        if response.links:
            next_link = response.links.get("next")
        elif isinstance(data, dict) and "meta" in data:
            # requests parses headers into dicts, this returns the same
            # structure so the regex will still work.
            try:
                next_link = {"url": data["meta"]["pagination"]["next"], "rel": "next"}
            except KeyError:
                next_link = None
        else:
            next_link = None

        regex = r"(?:{}|{})(.*)".format(
            re.escape(self._requester.base_url),
            re.escape(self._requester.new_quizzes_url),
        )

        self._next_url = (
            re.search(regex, next_link["url"]).group(1) if next_link else None
        )

        self._next_params = {}

        content = []

        if self._root:
            try:
                data = data[self._root]
            except KeyError:
                raise ValueError(
                    "The key <{}> does not exist in the response.".format(self._root)
                )

        for element in data:
            if element is not None:
                element.update(self._extra_attribs)
                content.append(self._content_class(self._requester, element))

        return content

    def _get_up_to_index(self, index):
        while len(self._elements) <= index and self._has_next():
            self._grow()

    def _grow(self):
        new_elements = self._get_next_page()
        self._elements += new_elements
        return new_elements

    def _has_next(self) -> bool:
        return self._next_url is not None

    def _is_larger_than(self, index) -> bool:
        return len(self._elements) > index or self._has_next()

    class _Slice:
        def __init__(self, the_list, the_slice):
            self._list = the_list
            self._start = the_slice.start or 0
            self._stop = the_slice.stop
            self._step = the_slice.step or 1

            if self._start < 0 or self._stop < 0:
                raise IndexError("Cannot negative index a PaginatedList slice")

        def __iter__(self):
            index = self._start
            while not self._finished(index):
                if self._list._is_larger_than(index):
                    try:
                        yield self._list[index]
                    except IndexError:
                        return
                    index += self._step
                else:
                    return

        def _finished(self, index) -> bool:
            return self._stop is not None and index >= self._stop
