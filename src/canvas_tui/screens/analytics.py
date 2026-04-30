"""Analytics screen — full-screen chart visualization.

Multiple panes of graphs: scatter, histogram, heatmap, line trends,
bullet charts, and grade distribution. Rich-native rendering.
"""

from __future__ import annotations

import contextlib
import datetime as dt
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.screen import Screen
from textual.widgets import Footer, Static

from ..theme import get_theme
from ..utils import course_label

if TYPE_CHECKING:
    from ..app import CanvasTUI


class AnalyticsScreen(Screen):
    """Full analytics dashboard with Rich-native charts."""

    BINDINGS = [
        ("escape", "pop", "Back"),
        ("backspace", "pop", "Back"),
    ]

    def __init__(self, owner_app: CanvasTUI) -> None:
        super().__init__()
        self._owner = owner_app

    def compose(self) -> ComposeResult:
        t = get_theme()
        with Vertical(id="analytics-root"):
            yield Static(f"[bold {t.text}]Analytics[/bold {t.text}]  [dim]Esc = back[/dim]", id="analytics-header")
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
        self.call_after_refresh(self._render_all)

    def on_resize(self, event: Resize) -> None:
        """Re-render charts after layout settles with new terminal dimensions."""
        self.call_after_refresh(self._render_all)

    def _get_pane_size(self, pane_id: str) -> tuple[int, int]:
        """Get the actual rendered size of a chart pane."""
        try:
            pane = self.query_one(f"#{pane_id}", Static)
            w, h = pane.size
            return max(20, w - 2), max(6, h - 2)
        except Exception:
            try:
                tw, th = self.app.size
                return max(40, tw // 2 - 4), max(10, th // 3 - 2)
            except Exception:
                return 50, 12

    def _render_all(self) -> None:
        from ..widgets.charts import (
            completion_bullet,
            grade_histogram,
            multi_line_chart,
            scatter_scores,
            score_bar_chart,
            submission_heatmap,
        )

        t = get_theme()
        active = {
            cid: v for cid, v in self._owner.course_cache.items() if cid not in self._owner.state.get_hidden_courses()
        }

        labels: list[str] = []
        scores: list[float] = []
        course_pcts: dict[str, list[float]] = {}
        all_scores: list[float] = []
        all_x: list[float] = []
        completion: dict[str, float] = {}
        label_counts: dict[str, int] = {}

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
            manual_avg = (100.0 * ts / tp) if tp > 0 else 0.0
            avg = self._owner._course_score_cache.get(cid, manual_avg)
            base = course_label(code)
            n = label_counts.get(base, 0) + 1
            label_counts[base] = n
            lbl = base if n == 1 else f"{course_label(code, 9)}#{n}"

            labels.append(lbl)
            scores.append(round(avg, 1))
            if pcts:
                course_pcts[lbl] = pcts
            if total_count > 0:
                completion[lbl] = 100.0 * submitted / total_count

        # 1. Score bar chart — responsive to pane size
        with contextlib.suppress(Exception):
            pw, ph = self._get_pane_size("chart-scores")
            chart = score_bar_chart(labels, scores, width=pw, height=max(ph, len(labels) + 4), title="Course Scores")
            self.query_one("#chart-scores", Static).update(chart)

        # 2. Grade distribution histogram
        with contextlib.suppress(Exception):
            pw, ph = self._get_pane_size("chart-distribution")
            hist = grade_histogram(
                all_scores, width=pw, height=ph, title="Grade Distribution", bins=min(12, max(5, pw // 4))
            )
            self.query_one("#chart-distribution", Static).update(hist)

        # 3. Multi-line trends
        with contextlib.suppress(Exception):
            pw, ph = self._get_pane_size("chart-trends")
            if course_pcts:
                trends = multi_line_chart(
                    {k: v[-20:] for k, v in course_pcts.items()},
                    width=pw,
                    height=ph,
                    title="Score Trends",
                )
                self.query_one("#chart-trends", Static).update(trends)
            else:
                self.query_one("#chart-trends", Static).update(
                    f"[{t.text_muted}]No trend data available[/{t.text_muted}]"
                )

        # 4. Scatter plot
        with contextlib.suppress(Exception):
            pw, ph = self._get_pane_size("chart-scatter")
            if all_x and all_scores:
                sc = scatter_scores(all_x, all_scores, width=pw, height=ph, title="All Scores (scatter)")
                self.query_one("#chart-scatter", Static).update(sc)
            else:
                self.query_one("#chart-scatter", Static).update(
                    f"[{t.text_muted}]No score data for scatter[/{t.text_muted}]"
                )

        # 5. Submission heatmap
        with contextlib.suppress(Exception):
            pw, ph = self._get_pane_size("chart-heatmap")
            heatmap_data = self._build_submission_heatmap()
            if heatmap_data:
                days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                hmap = submission_heatmap(heatmap_data, days=days, width=pw, height=ph, title="Submission Activity")
                self.query_one("#chart-heatmap", Static).update(hmap)
            else:
                self.query_one("#chart-heatmap", Static).update(
                    f"[{t.text_muted}]No submission data — submit assignments to see activity patterns[/{t.text_muted}]"
                )

        # 6. Completion bullet chart — with 100% targets
        with contextlib.suppress(Exception):
            pw, ph = self._get_pane_size("chart-bullet")
            if completion:
                c_labels = list(completion.keys())
                c_values = list(completion.values())
                c_targets = [100.0] * len(c_labels)
                bullet = completion_bullet(
                    c_labels, c_values, targets=c_targets, width=pw, height=ph, title="Completion %"
                )
                self.query_one("#chart-bullet", Static).update(bullet)
            else:
                self.query_one("#chart-bullet", Static).update(f"[{t.text_muted}]No completion data[/{t.text_muted}]")

    def _build_submission_heatmap(self) -> list[list[int]] | None:
        """Build a 7x24 matrix of submission counts by day-of-week x hour."""
        matrix = [[0] * 24 for _ in range(7)]
        has_data = False
        for it in self._owner.items:
            if "submitted" not in it.status_flags:
                continue
            # Try submission timestamp from raw_plannable, fall back to due_iso
            raw = it.raw_plannable or {}
            sub = raw.get("submissions", {}) if isinstance(raw.get("submissions"), dict) else {}
            ts = sub.get("submitted_at") or raw.get("submitted_at") or it.due_iso
            if not ts:
                continue
            with contextlib.suppress(Exception):
                d = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                matrix[d.weekday()][d.hour] += 1
                has_data = True
        return matrix if has_data else None

    def action_pop(self) -> None:
        self.dismiss()
