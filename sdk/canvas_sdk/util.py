"""Helpers for request building, parameter normalization, and file handling."""

import os


def is_multivalued(value):
    """
    Returns True if ``value`` should be treated as multiple separate values in a request param.

    Most iterables count (list, tuple, generator, etc.), but ``str`` and ``bytes`` are treated
    as single values to avoid splitting them into individual characters.
    """
    # special cases: iterable, but not multivalued
    if isinstance(value, (str, bytes)):
        return False

    # general rule: multivalued if iterable
    try:
        iter(value)
        return True
    except TypeError:
        return False


def combine_kwargs(**kwargs):
    """
    Flatten a nested dict/list structure into a flat list of ``(key, value)`` tuples suitable
    for passing to the Requester. Nested dicts become bracket-notation keys (e.g. ``course[id]``),
    and lists become repeated keys (e.g. ``enrollment[1]``, ``enrollment[2]``).

    :param kwargs: Nested keyword arguments to flatten.
    :type kwargs: dict
    :returns: Flat list of ``(key, value)`` tuples.
    :rtype: list of tuple
    """
    combined_kwargs = []

    # Loop through all kwargs provided
    for kw, arg in kwargs.items():
        if isinstance(arg, dict):
            for k, v in arg.items():
                for tup in flatten_kwarg(k, v):
                    combined_kwargs.append(("{}{}".format(kw, tup[0]), tup[1]))
        elif is_multivalued(arg):
            for i in arg:
                for tup in flatten_kwarg("", i):
                    combined_kwargs.append(("{}{}".format(kw, tup[0]), tup[1]))
        else:
            combined_kwargs.append((str(kw), arg))

    return combined_kwargs


def flatten_kwarg(key, obj):
    """
    Recursively flatten a kwarg node — dicts get ``[key]`` suffixes, lists get empty ``[]``
    brackets appended repeatedly. Returns a list of ``(key_fragment, value)`` tuples.

    :param key: The key prefix to prepend to each generated param name.
    :type key: str
    :param obj: The value to flatten — dict, list, or scalar.
    :returns: List of ``(key, value)`` tuples.
    :rtype: list of tuple
    """
    if isinstance(obj, dict):
        # Add the word (e.g. "[key]")
        new_list = []
        for k, v in obj.items():
            for tup in flatten_kwarg(k, v):
                new_list.append(("[{}]{}".format(key, tup[0]), tup[1]))
        return new_list

    elif is_multivalued(obj):
        # Add empty brackets (i.e. "[]")
        new_list = []
        for i in obj:
            for tup in flatten_kwarg(key + "][", i):
                new_list.append((tup[0], tup[1]))
        return new_list
    else:
        # Base case. Return list with tuple containing the value
        return [("[{}]".format(str(key)), obj)]


def obj_or_id(parameter, param_name, object_types):
    """
    Accepts either an int (or long or str representation of an integer)
    or an object. If it is an int, return it. If it is an object and
    the object is of correct type, return the object's id. Otherwise,
    throw an exception.

    :param parameter: int, str, long, or object
    :param param_name: str
    :param object_types: tuple
    :rtype: int
    """
    from canvas_sdk.user import User

    try:
        return int(parameter)
    except (ValueError, TypeError):
        # Special case where 'self' is a valid ID of a User object
        if User in object_types and parameter == "self":
            return parameter

        for obj_type in object_types:
            if isinstance(parameter, obj_type):
                try:
                    return int(parameter.id)
                except Exception:
                    break

        obj_type_list = ",".join([obj_type.__name__ for obj_type in object_types])
        message = "Parameter {} must be of type {} or int.".format(
            param_name, obj_type_list
        )
        raise TypeError(message)


def obj_or_str(parameter, param_name, object_types):
    """
    Accepts either an object or a string. If it is a string, return it directly.
    If it is an object and the object is of correct type, return the object's
    corresponding string. Otherwise, throw an exception.

    :param parameter: object from which to retrieve attribute
    :type parameter: str or object
    :param param_name: name of the attribute to retrieve
    :type param_name: str
    :param object_types: tuple containing the types of the object being passed in
    :type object_types: tuple
    :rtype: str
    """
    if isinstance(parameter, str):
        return parameter

    for obj_type in object_types:
        if isinstance(parameter, obj_type):
            try:
                return str(getattr(parameter, param_name))
            except AttributeError:
                raise AttributeError("{} object does not have {} attribute").format(
                    parameter, param_name
                )

    obj_type_list = ",".join([obj_type.__name__ for obj_type in object_types])
    raise TypeError("Parameter {} must be of type {}.".format(parameter, obj_type_list))


def get_institution_url(base_url):
    """
    Clean up a given base URL.

    :param base_url: The base URL of the API.
    :type base_url: str
    :rtype: str
    """
    base_url = base_url.strip()
    return base_url.rstrip("/")


def file_or_path(file):
    """
    Accept a file path or an already-open file handle. If given a path, open it in binary mode.
    Returns ``(file_handle, was_path)`` so callers know whether to close the handle.

    :param file: A file path (str) or an open file-like object.
    :returns: ``(open_file, is_path)`` — the file object and whether we opened it.
    :rtype: (file, bool)
    """

    is_path = False
    if isinstance(file, str):
        if not os.path.exists(file):
            raise IOError("File at path " + file + " does not exist.")
        file = open(file, "rb")
        is_path = True

    return file, is_path


def normalize_bool(val, param_name):
    """
    Normalize boolean-like strings to their corresponding boolean values.

    :param val: Value to normalize. Acceptable values:
        True, "True", "true", False, "False", "false"
    :type val: str or bool
    :param param_name: Name of the parameter being checked
    :type param_name: str

    :rtype: bool
    """
    if isinstance(val, bool):
        return val
    elif val in ("True", "true"):
        return True
    elif val in ("False", "false"):
        return False
    else:
        raise ValueError(
            'Parameter `{}` must be True, "True", "true", False, "False", or "false".'.format(
                param_name
            )
        )


def clean_headers(headers):
    """
    Return a copy of the headers dict with the Authorization header masked,
    showing only the last 4 characters (for safe logging).

    :param headers: Raw headers dict.
    :type headers: dict
    :returns: Sanitized copy of headers.
    :rtype: dict
    """
    cleaned_headers = headers.copy()

    authorization_header = headers.get("Authorization")
    if authorization_header:
        sanitized = "****" + authorization_header[-4:]
        cleaned_headers["Authorization"] = sanitized

    return cleaned_headers
