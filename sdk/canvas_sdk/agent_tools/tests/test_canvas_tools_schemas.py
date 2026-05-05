"""Schema validation tests for canvas_tools — no network, no mocks, no canvas_tui calls."""
from canvas_sdk.agent_tools.canvas_tools import (
    ListCourses,
    GetAssignments,
    GetCourse,
    GetSyllabus,
    GetTodo,
    GetGrades,
    ListAnnouncements,
    ListPlannerItems,
)

CANVAS_TOOLS = [
    ListCourses,
    GetAssignments,
    GetCourse,
    GetSyllabus,
    GetTodo,
    GetGrades,
    ListAnnouncements,
    ListPlannerItems,
]


def test_all_canvas_tool_schemas_have_object_parameters():
    for tool in CANVAS_TOOLS:
        params = tool.SCHEMA["parameters"]
        assert params.get("type") == "object", (
            f"{tool.__name__}.SCHEMA['parameters']['type'] != 'object'"
        )


def test_all_canvas_tool_schemas_have_name():
    for tool in CANVAS_TOOLS:
        assert "name" in tool.SCHEMA, f"{tool.__name__}.SCHEMA missing 'name'"
        assert tool.SCHEMA["name"] == tool.NAME


def test_all_canvas_tool_schemas_have_description():
    for tool in CANVAS_TOOLS:
        assert "description" in tool.SCHEMA, f"{tool.__name__}.SCHEMA missing 'description'"
        assert len(tool.SCHEMA["description"]) > 0


def test_all_canvas_tool_schemas_have_parameters():
    for tool in CANVAS_TOOLS:
        assert "parameters" in tool.SCHEMA, f"{tool.__name__}.SCHEMA missing 'parameters'"


def test_get_assignments_course_id_type():
    props = GetAssignments.SCHEMA["parameters"]["properties"]
    assert "course_id" in props
    assert props["course_id"]["type"] == ["integer", "null"]


def test_get_assignments_has_horizon_days():
    props = GetAssignments.SCHEMA["parameters"]["properties"]
    assert "horizon_days" in props
    assert props["horizon_days"]["type"] == "integer"


def test_get_course_requires_course_id():
    schema = GetCourse.SCHEMA
    assert "course_id" in schema["parameters"]["required"]


def test_get_course_course_id_is_integer():
    props = GetCourse.SCHEMA["parameters"]["properties"]
    assert props["course_id"]["type"] == "integer"


def test_get_syllabus_description_mentions_credit_hours():
    desc = GetSyllabus.SCHEMA["description"].lower()
    assert "credit hours" in desc or "credits" in desc, (
        f"GetSyllabus description does not mention credit hours: {desc!r}"
    )


def test_get_grades_description_mentions_score_or_urgency():
    desc = GetGrades.SCHEMA["description"].lower()
    assert "score" in desc or "urgency" in desc, (
        f"GetGrades description does not mention score/urgency: {desc!r}"
    )


def test_list_announcements_has_past_days_property():
    props = ListAnnouncements.SCHEMA["parameters"]["properties"]
    assert "past_days" in props, "ListAnnouncements SCHEMA missing 'past_days' property"


def test_list_announcements_past_days_is_integer():
    props = ListAnnouncements.SCHEMA["parameters"]["properties"]
    assert props["past_days"]["type"] == "integer"


def test_list_announcements_has_course_ids_property():
    props = ListAnnouncements.SCHEMA["parameters"]["properties"]
    assert "course_ids" in props
    assert props["course_ids"]["type"] == "array"


def test_get_todo_has_no_required_params():
    schema = GetTodo.SCHEMA
    assert schema["parameters"]["required"] == []


def test_list_planner_items_has_no_required_params():
    schema = ListPlannerItems.SCHEMA
    assert schema["parameters"]["required"] == []


def test_list_courses_has_active_only_property():
    props = ListCourses.SCHEMA["parameters"]["properties"]
    assert "active_only" in props
    assert props["active_only"]["type"] == "boolean"
