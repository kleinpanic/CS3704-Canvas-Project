import json
import pytest

from canvas_sdk.agent_tools import REGISTRY, get_schemas, get_schema_json, dispatch

EXPECTED_NAMES = {
    "canvas.list_courses",
    "canvas.get_assignments",
    "canvas.get_course",
    "canvas.get_syllabus",
    "canvas.get_todo",
    "canvas.get_grades",
    "canvas.list_announcements",
    "canvas.list_planner_items",
    "calendar.list_events",
    "calendar.find_free_blocks",
    "calendar.create_event",
    "calendar.modify_event",
    "calendar.delete_event",
    "study.spaced_schedule",
    "study.semester_schedule",
    "study.recommend_block_size",
    "study.exam_bracket",
    "reranker.priority_hint",
}


def test_registry_has_all_18_tools():
    assert len(REGISTRY) == 18


def test_registry_has_all_expected_names():
    assert set(REGISTRY.keys()) == EXPECTED_NAMES


def test_tool_name_matches_registry_key():
    for key, tool_class in REGISTRY.items():
        assert tool_class.NAME == key, f"{tool_class.__name__}.NAME={tool_class.NAME!r} != registry key {key!r}"


def test_get_schemas_returns_18():
    schemas = get_schemas()
    assert len(schemas) == 18


def test_get_schemas_each_has_type_and_function():
    for schema in get_schemas():
        assert "type" in schema
        assert "function" in schema
        assert schema["type"] == "function"


def test_get_schemas_function_has_required_keys():
    for schema in get_schemas():
        fn = schema["function"]
        assert "name" in fn, f"Missing 'name' in schema: {fn}"
        assert "description" in fn, f"Missing 'description' in schema: {fn}"
        assert "parameters" in fn, f"Missing 'parameters' in schema: {fn}"


def test_get_schema_json_is_valid_json():
    raw = get_schema_json()
    parsed = json.loads(raw)
    assert isinstance(parsed, list)
    assert len(parsed) == 18


def test_get_schema_json_entries_have_required_keys():
    parsed = json.loads(get_schema_json())
    for entry in parsed:
        assert entry["type"] == "function"
        fn = entry["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn


def test_dispatch_raises_keyerror_for_unknown_tool():
    with pytest.raises(KeyError):
        dispatch("does.not_exist", {})


def test_dispatch_raises_keyerror_for_empty_name():
    with pytest.raises(KeyError):
        dispatch("", {})
