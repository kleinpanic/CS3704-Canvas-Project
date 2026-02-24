# Canvas TUI — Issues

## Critical

### Issue #1: plotext ANSI→Rich rendering is lossy
`charts.py` uses plotext to generate ANSI escape codes, then converts via `Text.from_ansi()`. Not all plotext escape sequences map cleanly to Textual's Rich compositor — causes axis label misalignment, poor color fidelity, and rendering artifacts.

### Issue #2: Scatter plot invisible data points
"All Scores (scatter)" pane renders axes but zero visible data points. `scatter_scores()` uses `marker="braille"` which produces invisible dots at low data density. Needs larger markers or fallback rendering.

### Issue #3: Grade Distribution negative x-axis
`grade_histogram()` shows `-3.6` as a bin edge — meaningless for grade percentages. Bin ranges are not clamped to `[0, 100]`.

### Issue #4: Score Trends massive empty space
`multi_line_chart()` renders at a fixed character grid. plotext's internal layout wastes ~70% of pane width when data is sparse. Legend overlaps chart area.

## Major

### Issue #5: Dual charting systems, no coherence
`charts.py` uses plotext (ANSI pipeline), `plots.py` uses Rich markup (braille/blocks). Dashboard uses `plots.py`, Analytics uses `charts.py`. Different rendering → inconsistent look across screens.

### Issue #6: No dynamic chart sizing
Analytics calculates `tw//3` for panel width but plotext charts don't resize to fill containers. Fixed character grid → charts float top-left with dead space on wide terminals.

### Issue #7: Uncoordinated color palette
Hard-coded color lists (`["cyan", "green", "yellow", "magenta", "blue", "red"]`) in 4+ places. `theme.py` defines a full token system but **charts don't use it** — they bypass themes entirely.

### Issue #8: Competing border systems
CSS uses `#30363d` borders consistently, but plotext's own `dark` theme adds orange frame borders. Two border systems fighting each other.

## Minor

### Issue #9: Submission heatmap always empty
`_build_submission_heatmap()` checks `"submitted" not in it.status_flags` (inverted logic) and uses `it.due_iso` instead of actual submission timestamps. Nearly always returns `None`.

### Issue #10: Completion % chart — targets never passed
`completion_bullet()` renders actual vs target, but target values are never provided by callers. It's just a regular bar chart pretending to be a bullet chart.

### Issue #11: Course code label truncation inconsistency
Labels like `NEUR_2464_`, `CS_3724_13` have trailing underscores. Analytics truncates at `[:10]`, app.py at `[:12]`. No consistent normalization.

### Issue #12: Braille plots don't overlay series
`plots.py` renders each series in separate rows rather than overlaying on a shared Y-axis grid. Multiple series produce stacked charts, not overlaid lines.
