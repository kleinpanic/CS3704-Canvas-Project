"""Analytics screen — full-screen chart visualization.

Multiple panes of graphs: scatter, histogram, heatmap, line trends,
bullet charts, and grade distribution. All rendered via plotext.
"""

from __future__ import annotations

import contextlib
import datetime as dt
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static

if TYPE_CHECKING:
    from ..app import CanvasTUI


class AnalyticsScreen(Screen):
    """Full analytics dashboard with plotext charts."""

    BINDINGS = [
        ("escape", "pop", "Back"),
        ("backspace", "pop", "Back"),
    ]

    def __init__(self, owner_app: CanvasTUI) -> None:
        super().__init__()
        self._owner = owner_app

    def compose(self) -> ComposeResult:
        with Vertical(id="analytics-root"):
            yield Static("[bold]Analytics[/bold]  [dim]Esc = back[/dim]", id="analytics-header")
            with Horizontal(id="analytics-top"):
                yield Static(id="chart-scores", classes="chart-pane")
                yield Static(id="chart-distribution", classes="chart-pane")
            with Horizontal(id="analytics-mid"):
                yield Static(id="chart-trends", classes="chart-pane")
                yield Static(id="chart-scatter", classes="chart-pane")
            with Horizontal(id="analytics-bot"):
                yield Static(id="chart-heatmap", classes="chart-pane")
                yield Static(id="chart-bullet", classes="chart-pane")
            yield Footer()

    def on_mount(self) -> None:
        self._render_all()

    def _render_all(self) -> None:
        from ..widgets.charts import (
            completion_bullet,
            grade_histogram,
            multi_line_chart,
            scatter_scores,
            score_bar_chart,
            submission_heatmap,
        )

        active = {cid: v for cid, v in self._owner.course_cache.items()
                  if cid not in self._owner.state.get_hidden_courses()}

        labels: list[str] = []
        scores: list[float] = []
        course_pcts: dict[str, list[float]] = {}
        all_scores: list[float] = []
        all_x: list[float] = []
        completion: dict[str, float] = {}

        for cid, (code, _name) in sorted(active.items(), key=lambda kv: kv[1][0]):
            grades = self._owner._grade_cache.get(cid, [])
            ts, tp = 0.0, 0.0
            pcts: list[float] = []
            idx = 0
            total_count = len(grades)
            submitted = 0
            for a in grades:
                pts = a.get("points_possible")
                sub = a.get("submission") or {}
                sc = sub.get("score")
                if sc is not None and pts:
                    ts += float(sc)
                    tp += float(pts)
                    pct = 100.0 * float(sc) / float(pts)
                    pcts.append(pct)
                    all_scores.append(pct)
                    idx += 1
                    all_x.append(float(idx))
                    submitted += 1
            avg = (100.0 * ts / tp) if tp > 0 else 0.0
            labels.append(code[:10])
            scores.append(round(avg, 1))
            if pcts:
                course_pcts[code[:10]] = pcts
            if total_count > 0:
                completion[code[:10]] = 100.0 * submitted / total_count

        # 1. Score bar chart
        with contextlib.suppress(Exception):
            chart = score_bar_chart(labels, scores, width=50, height=max(8, len(labels) + 4),
                                    title="Course Scores")
            self.query_one("#chart-scores", Static).update(chart)

        # 2. Grade distribution histogram
        with contextlib.suppress(Exception):
            hist = grade_histogram(all_scores, width=45, height=10,
                                   title="Grade Distribution", bins=12)
            self.query_one("#chart-distribution", Static).update(hist)

        # 3. Multi-line trends
        with contextlib.suppress(Exception):
            if course_pcts:
                trends = multi_line_chart(
                    {k: v[-20:] for k, v in course_pcts.items()},
                    width=50, height=10, title="Score Trends",
                )
                self.query_one("#chart-trends", Static).update(trends)
            else:
                self.query_one("#chart-trends", Static).update("[dim]No trend data[/dim]")

        # 4. Scatter plot
        with contextlib.suppress(Exception):
            if all_x and all_scores:
                sc = scatter_scores(all_x, all_scores, width=45, height=10,
                                    title="All Scores (scatter)")
                self.query_one("#chart-scatter", Static).update(sc)

        # 5. Submission heatmap (day of week x hour)
        with contextlib.suppress(Exception):
            heatmap_data = self._build_submission_heatmap()
            if heatmap_data:
                days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                hmap = submission_heatmap(heatmap_data, days=days, width=50, height=10,
                                          title="Submission Activity")
                self.query_one("#chart-heatmap", Static).update(hmap)
            else:
                self.query_one("#chart-heatmap", Static).update("[dim]No submission data[/dim]")

        # 6. Completion bullet chart
        with contextlib.suppress(Exception):
            if completion:
                c_labels = list(completion.keys())
                c_values = list(completion.values())
                bullet = completion_bullet(c_labels, c_values, width=45, height=10,
                                            title="Completion %")
                self.query_one("#chart-bullet", Static).update(bullet)

    def _build_submission_heatmap(self) -> list[list[int]] | None:
        """Build a 7x24 matrix of submission counts by day-of-week x hour."""
        matrix = [[0] * 24 for _ in range(7)]
        has_data = False
        for it in self._owner.items:
            if "submitted" not in it.status_flags:
                continue
            if not it.due_iso:
                continue
            with contextlib.suppress(Exception):
                d = dt.datetime.fromisoformat(it.due_iso.replace("Z", "+00:00"))
                matrix[d.weekday()][d.hour] += 1
                has_data = True
        return matrix if has_data else None

    def action_pop(self) -> None:
        self.dismiss()
