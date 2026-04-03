# Canvas TUI v2.0 — Architecture Plan

## Architecture: Daemon + Session Model

```
canvas-tuid (daemon)          canvas-tui (session/TUI)
┌────────────────────┐        ┌─────────────────────────┐
│ Background process │        │ Textual TUI             │
│ - Periodic refresh │  IPC   │ - Connects to daemon    │
│ - Data cache (SQLite│◄─────►│ - Renders panes/graphs  │
│   or JSON)         │ (Unix  │ - Keyboard navigation   │
│ - Notification     │ socket │ - Multiple windows      │
│   scheduler        │  or    │                         │
│ - Rate limiting    │ file)  │ Window = screen context  │
│ - Grade history    │        │ Pane = visual component  │
│   tracking         │        │                         │
└────────────────────┘        └─────────────────────────┘
```

**Fallback**: If no daemon, TUI fetches directly (current behavior).

## Pane Layout System (tmux-style)

Each "window" (screen) is divided into panes. Users can:
- Resize panes with mouse or keys
- Cycle through pane layouts (horizontal, vertical, grid)
- Each pane is a self-contained widget

### Main Window Panes:
```
┌──────────────────────┬──────────────────────┐
│ [Logo + Info]        │ [Score Bar Chart]    │
│                      │ (plotext)            │
├──────────────────────┴──────────────────────┤
│ [Assignment Table]                          │
│ (scrollable, full data)                     │
├─────────────┬──────────────┬────────────────┤
│ [Line Graph]│ [Pie Chart]  │ [Heatmap]      │
│ Score trend │ Grade weights│ Activity/week  │
│ (plotext)   │ (plotext)    │ (plotext)      │
└─────────────┴──────────────┴────────────────┘
```

### Analytics Window Panes:
```
┌──────────────────────┬──────────────────────┐
│ [Scatter Plot]       │ [Grade Distribution] │
│ Scores over time     │ Histogram            │
├──────────────────────┼──────────────────────┤
│ [Heatmap]            │ [Radial Chart]       │
│ Submission patterns  │ Course completion    │
│ per day/hour         │                      │
├──────────────────────┴──────────────────────┤
│ [Multi-Year Analysis Table]                 │
│ Semester-over-semester comparison            │
└─────────────────────────────────────────────┘
```

## Graph Types (via plotext)

| Chart | Data Source | Location |
|-------|-----------|----------|
| Bar chart | Course scores | Main banner, dashboard |
| Line/scatter | Score trend per assignment | Bottom pane, analytics |
| Histogram | Grade distribution across all courses | Analytics |
| Heatmap | Submission times (day x hour) | Analytics |
| Stacked bar | Assignment group weights | Course overview |
| Pie (simulated) | Grade weight breakdown | Course overview |
| Bullet chart | Progress vs target per course | Dashboard |
| Matrix | Course x week submission grid | Analytics |

## Plotext Integration

`plotext` renders to ANSI strings. We capture the output and display
in Textual Static widgets:

```python
import plotext as plt

def render_score_chart(courses, scores, width, height):
    plt.clf()
    plt.theme('dark')
    plt.bar(courses, scores)
    plt.title('Course Scores')
    plt.plotsize(width, height)
    return plt.build()
```

## Implementation Phases

### Phase 1: plotext graphs + pane layout (HIGH IMPACT)
- Replace custom bar/sparkline rendering with plotext
- Add line chart, histogram, heatmap to bottom panes
- Proper 3-pane bottom section with real charts
- Add plotext to dependencies

### Phase 2: Pomodoro controls + footer fix
- Scrollable/paginated footer bar
- Proper start/pause/stop/reset pomodoro controls
- Timer display in header

### Phase 3: Analytics window
- New 'V' key for analytics/visualization screen
- Scatter plots, histograms, heatmaps
- Submission pattern analysis
- Grade distribution charts

### Phase 4: Daemon architecture
- canvas-tuid background service
- Unix socket IPC or shared JSON/SQLite cache
- systemd user service unit
- Grade history tracking for multi-semester analysis
- Auto-refresh without TUI running

### Phase 5: Advanced visualizations
- Sunburst (simulated with nested bars)
- Radial histogram (clock-style submission pattern)
- Multi-year heatmap
- Bullet charts for progress tracking
