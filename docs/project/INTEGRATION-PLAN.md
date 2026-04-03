# GideonWolfe Feature Integration Plan

Reference: `~/.local/srcs/gitclones/canvas-tui/`

## What They Have That We Want

### 1. Canvas ASCII Logo (dashboard header)
**Their impl**: Base64-encoded PNG decoded at runtime, rendered via `termui.Image` widget.
**Our approach**: ASCII art logo using Rich markup — no image dependency, looks great in any terminal. Hand-craft a sharp Canvas "C" shield logo or full "CANVAS" wordmark using box-drawing / block characters, styled with our cyan/orange Canvas brand colors.
**Location**: New `src/canvas_tui/logo.py` — exports `CANVAS_LOGO` string.
**Where it shows**: Dashboard screen header (left panel, top 1/4).

### 2. Dashboard Screen (landing page with overview)
**Their impl**: `dashboard.go` — 3-row grid:
- Top 1/4: Logo (left 1/3) + Summary bar chart of course scores (right 2/3)
- Mid 2/4: Todo table with urgency-colored borders
- Bottom 1/4: Score line plot across courses

**Our approach**: New `DashboardScreen` that replaces the raw table as the landing view:
- Top row: ASCII logo (left) + course score bar chart (right)
- Middle: "Due soon" summary — next 48h items, urgency-colored
- Bottom: Per-course sparkline grade trends + assignment completion gauges
**Location**: `src/canvas_tui/screens/dashboard.py`
**Keybinding**: `D` from any screen, or make it the default landing screen.

### 3. Course Score Bar Chart
**Their impl**: `createSummaryBarchart()` — horizontal bars per course, color-coded:
- Green >80%, Yellow >70%, Magenta >60%, Red ≤50%
**Our approach**: Rich-rendered horizontal bar chart using `▓░` block characters. Each course gets a labeled bar with percentage and color. No external charting library needed.
**Location**: Built into `DashboardScreen` as a composite widget.

### 4. Score Line Plot (grade trend over time)
**Their impl**: `createCourseScorePlot()` — multi-line braille plot of assignment scores per course.
**Our approach**: We already have sparklines. Upgrade to a full braille-dot scatter/line plot widget using Unicode braille characters (⠁⠂⠃...). Each course gets a trend line. Textual's Rich rendering handles this natively.
**Location**: `src/canvas_tui/widgets/plots.py` — reusable `BraillePlot` widget.

### 5. Assignment Completion Progress Bar (per course)
**Their impl**: `createAssignmentProgressBar()` — gauge widget showing X/Y assignments completed with color thresholds.
**Our approach**: Rich progress bars in the course overview. `[████████░░] 8/12 (67%)` with green/yellow/red coloring.
**Location**: Integrated into `DashboardScreen` and `GradesScreen`.

### 6. Course Breakdown Pie Chart
**Their impl**: `createCoursePieChart()` — assignment group weights as pie chart.
**Our approach**: ASCII pie chart is ugly. Instead: horizontal stacked bar showing assignment group weights with labels. Cleaner in a terminal. `[███ HW 40%][██ Exam 30%][█ Quiz 20%][░ Part 10%]`
**Location**: Add to `GradesScreen` when viewing a course — shows weight breakdown above the grade table.

### 7. Urgency-Colored Table Borders
**Their impl**: Todo table border color changes based on count:
- ≥10 red, ≥7 yellow, ≥4 blue, ≥2 cyan, <2 green
**Our approach**: Dynamic CSS class on the main table container that shifts border/title color based on overdue + due-today count. Textual CSS makes this trivial.
**Location**: `app.py` — `_render_table()` updates a reactive class.

### 8. Course Overview Grid
**Their impl**: `createCourseOverviewGrid()` — per-course view with:
- Overview paragraph (professor, students, term, dates)
- Assignment progress bar
- Todo table + recent scores table
- Announcement window + syllabus
- Score plot + pie chart
**Our approach**: New `CourseDetailScreen` (or enhance existing detail flow):
- Header: course info (instructor, term, enrollment count)
- Left: upcoming assignments for this course
- Right: recent scores with color grading
- Bottom: announcement preview + grade trend
**Location**: `src/canvas_tui/screens/course_overview.py`

---

## Implementation Order (by impact)

| Phase | Feature | Effort | Impact |
|-------|---------|--------|--------|
| **A** | Canvas ASCII logo | Small | High (brand identity, polish) |
| **B** | Dashboard screen with bar charts | Large | Very High (landing experience) |
| **C** | Urgency-colored borders | Small | Medium (visual urgency cues) |
| **D** | Assignment completion gauges | Medium | High (progress visibility) |
| **E** | Braille line plot widget | Medium | High (grade trend visualization) |
| **F** | Assignment group weight bars | Small | Medium (grade context) |
| **G** | Course overview screen | Large | High (per-course deep dive) |

## API Endpoints Needed (already have most)

| Endpoint | Status |
|----------|--------|
| `/api/v1/planner/items` | ✅ Have |
| `/api/v1/courses` | ✅ Have |
| `/api/v1/courses/:id/assignments?include[]=submission` | ✅ Have (`fetch_grades`) |
| `/api/v1/courses/:id` with `?include[]=total_students,teachers,term` | ❌ Need to add params |
| `/api/v1/courses/:id/assignment_groups` | ❌ Need new endpoint |
| `/api/v1/announcements` | ✅ Have |
| `/api/v1/courses/:id?include[]=syllabus_body` | ✅ Have |

## Files to Create/Modify

### New Files
- `src/canvas_tui/logo.py` — ASCII Canvas logo
- `src/canvas_tui/screens/dashboard.py` — Dashboard landing screen
- `src/canvas_tui/screens/course_overview.py` — Per-course deep dive
- `src/canvas_tui/widgets/plots.py` — BraillePlot + BarChart widgets
- `tests/test_dashboard.py`
- `tests/test_plots.py`
- `tests/test_logo.py`

### Modified Files
- `src/canvas_tui/app.py` — Add D keybinding, urgency borders, route to dashboard
- `src/canvas_tui/api.py` — Add `fetch_assignment_groups()`, extend `fetch_current_courses()` with teacher/term
- `src/canvas_tui/screens/grades.py` — Add weight breakdown bars, completion gauges
- `src/canvas_tui/screens/help.py` — Document new keybindings
- `src/canvas_tui/theme.py` — Add bar chart / gauge color definitions
