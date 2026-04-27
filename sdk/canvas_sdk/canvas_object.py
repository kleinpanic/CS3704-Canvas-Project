"""Base class for all Canvas API entity objects. Provides attribute hydration and datetime parsing."""

import arrow
import pytz


class CanvasObject:
    """
    Base class for every Canvas API entity. Pass in a JSON dict from the API and this class
    will hydrate its attributes, including parsing ISO8601 timestamps into aware datetime objects.
    """

    def __getattribute__(self, name):
        return super().__getattribute__(name)

    def __init__(self, requester, attributes: dict):
        """
        :param requester: Requester instance for making follow-up API calls.
        :type requester: :class:`canvas_sdk.requester.Requester`
        :param attributes: Raw JSON dict from the Canvas API.
        :type attributes: dict
        """
        self._requester = requester
        self.set_attributes(attributes)

    def __repr__(self):  # pragma: no cover
        classname = self.__class__.__name__
        attrs = ", ".join(
            [
                "{}={}".format(attr, val)
                for attr, val in self.__dict__.items()
                if attr != "attributes"
            ]
        )
        return "{}({})".format(classname, attrs)

    def set_attributes(self, attributes: dict):
        """
        Hydrate this object from a JSON dict. Also detects ISO8601 date strings and creates
        a corresponding ``_date`` attribute with a timezone-aware datetime.

        For example, a response containing ``start_at: "2012-05-05T00:00:00Z"`` will also
        get a ``start_at_date`` attribute parsed into a proper UTC datetime.

        :param attributes: Raw JSON dict from the Canvas API.
        :type attributes: dict
        """
        for attribute, value in attributes.items():
            self.__setattr__(attribute, value)

            try:
                naive = arrow.get(str(value)).datetime
                aware = naive.replace(tzinfo=pytz.utc) - naive.utcoffset()
                self.__setattr__(attribute + "_date", aware)
            except arrow.ParserError:
                pass
            except ValueError:
                pass
