#!/usr/bin/env python3
"""
╔════════════════════════════════════════════════════════════════╗
║     CS3704 Canvas TUI — Professional Test Suite Runner         ║
║     "Where code meets quality, and quality meets style"        ║
╚════════════════════════════════════════════════════════════════╝
"""

import subprocess
import sys
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import re

try:
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, SpinnerColumn
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text
    from rich.columns import Columns
    from rich import box
    from rich.style import Style
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Installing rich for beautiful output...")
    subprocess.run([sys.executable, "-m", "pip", "install", "rich", "-q"])
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, SpinnerColumn
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text
    from rich.columns import Columns
    from rich import box
    from rich.style import Style
    RICH_AVAILABLE = True


# =============================================================================
# Configuration
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "canvas_tui"
TEST_DIR = PROJECT_ROOT / "tests"

# Custom styles
HEADER_STYLE = Style(color="bright_cyan", bold=True)
SUCCESS_STYLE = Style(color="bright_green", bold=True)
FAIL_STYLE = Style(color="bright_red", bold=True)
WARN_STYLE = Style(color="bright_yellow", bold=True)
DIM_STYLE = Style(color="bright_black")


# =============================================================================
# Test Stages
# =============================================================================

@dataclass
class TestStage:
    name: str
    command: list
    description: str
    icon: str
    critical: bool = True


TEST_STAGES = [
    TestStage(
        "Import Check",
        [sys.executable, "-c", "import canvas_tui"],
        "Verify package imports",
        "📦"
    ),
    TestStage(
        "Lint Check",
        ["ruff", "check", "src", "tests"],
        "Code style validation",
        "🔍",
        critical=False
    ),
    TestStage(
        "Format Check",
        ["ruff", "format", "--check", "src", "tests"],
        "Code formatting",
        "🎨",
        critical=False
    ),
    TestStage(
        "Type Check",
        ["mypy", "src/canvas_tui", "--ignore-missing-imports", "--no-error-summary"],
        "Static type analysis",
        "🔬",
        critical=False
    ),
    TestStage(
        "Unit Tests",
        ["pytest", "tests", "-q", "--tb=no", "-x"],
        "Core functionality tests",
        "🧪"
    ),
    TestStage(
        "Coverage Analysis",
        ["pytest", "--cov=canvas_tui", "--cov-report=term-missing", "-q", "--tb=no"],
        "Code coverage metrics",
        "📊",
        critical=False
    ),
]


# =============================================================================
# Test Runner
# =============================================================================

class TestRunner:
    """Professional test runner with beautiful Rich output."""
    
    def __init__(self):
        self.console = Console()
        self.results: list[tuple[TestStage, bool, str, float]] = []
        
    def run_stage(self, stage: TestStage, progress, task) -> tuple[bool, str, float]:
        """Run a single test stage and return results."""
        start_time = time.time()
        
        progress.update(task, description=f"[yellow]{stage.icon} {stage.name}[/yellow]")
        
        try:
            result = subprocess.run(
                stage.command,
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
                timeout=120
            )
            elapsed = time.time() - start_time
            success = result.returncode == 0
            output = result.stdout + result.stderr
            return success, output, elapsed
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            return False, "Stage timed out after 120s", elapsed
        except FileNotFoundError as e:
            elapsed = time.time() - start_time
            return False, f"Command not found: {e}", elapsed
    
    def print_header(self):
        """Print beautiful header."""
        header = Text()
        header.append("\n")
        header.append("╔════════════════════════════════════════════════════════════════╗\n", style="cyan")
        header.append("║     ", style="cyan")
        header.append("CS3704 Canvas TUI — Test Suite", style="cyan bold")
        header.append("                              ║\n", style="cyan")
        header.append("║     ", style="cyan")
        header.append('"Where code meets quality, and quality meets style"', style="cyan italic")
        header.append("        ║\n", style="cyan")
        header.append("╚════════════════════════════════════════════════════════════════╝\n", style="cyan")
        
        self.console.print(header)
        
        # Project info
        info_table = Table.grid(padding=(0, 2))
        info_table.add_column(style="dim")
        info_table.add_column()
        info_table.add_row("📁 Project Root:", str(PROJECT_ROOT))
        info_table.add_row("🐍 Python:", sys.version.split()[0])
        info_table.add_row("📍 Working Dir:", str(Path.cwd()))
        
        self.console.print(Panel(info_table, title="[bold]Environment[/bold]", border_style="dim"))
        self.console.print()
    
    def run_all_stages(self):
        """Run all test stages with progress tracking."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40, complete_style="green", finished_style="green"),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task("[cyan]Initializing...", total=len(TEST_STAGES))
            
            for stage in TEST_STAGES:
                success, output, elapsed = self.run_stage(stage, progress, task)
                self.results.append((stage, success, output, elapsed))
                progress.advance(task)
        
    def print_results(self):
        """Print results in a beautiful table."""
        # Results table
        table = Table(
            title="\n📊 Test Results Summary",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
            border_style="cyan",
        )
        
        table.add_column("Stage", style="dim", width=20)
        table.add_column("Status", justify="center", width=12)
        table.add_column("Time", justify="right", width=10)
        table.add_column("Critical", justify="center", width=10)
        
        passed = 0
        failed = 0
        total_time = 0.0
        
        for stage, success, output, elapsed in self.results:
            total_time += elapsed
            status = "[green]✓ PASS[/green]" if success else "[red]✗ FAIL[/red]"
            critical = "[yellow]Yes[/yellow]" if stage.critical else "[dim]No[/dim]"
            time_str = f"{elapsed:.2f}s"
            
            table.add_row(
                f"{stage.icon} {stage.name}",
                status,
                time_str,
                critical
            )
            
            if success:
                passed += 1
            else:
                failed += 1
        
        self.console.print(table)
        
        # Statistics panel
        stats = Table.grid(padding=(0, 3))
        stats.add_column(justify="right")
        stats.add_column()
        stats.add_row("[green]Passed:[/green]", f"[green bold]{passed}[/green bold]")
        stats.add_row("[red]Failed:[/red]", f"[red bold]{failed}[/red bold]")
        stats.add_row("[cyan]Total:[/cyan]", f"[cyan bold]{passed + failed}[/cyan bold]")
        stats.add_row("[dim]Duration:[/dim]", f"[dim]{total_time:.2f}s[/dim]")
        
        self.console.print()
        self.console.print(Panel(
            stats,
            title="[bold]Statistics[/bold]",
            border_style="dim"
        ))
        
        # Print failures
        failures = [(s, o, e) for s, success, o, e in self.results if not success]
        if failures:
            self.console.print("\n[bold red]━━━ Failed Stage Details ━━━[/bold red]\n")
            
            for stage, output, elapsed in failures:
                # Truncate long output
                output_lines = output.strip().split("\n")
                if len(output_lines) > 30:
                    output = "\n".join(output_lines[:15] + ["...", f"({len(output_lines) - 30} more lines)"] + output_lines[-15:])
                
                self.console.print(Panel(
                    output or "[dim]No output[/dim]",
                    title=f"[red]{stage.icon} {stage.name}[/red]",
                    subtitle=f"[dim]{elapsed:.2f}s[/dim]",
                    border_style="red",
                    expand=False
                ))
        
        # Final status
        self.console.print()
        all_critical_passed = all(
            success or not stage.critical 
            for stage, success, _, _ in self.results
        )
        
        if all_critical_passed:
            success_panel = Panel(
                "[bold green]✓ All critical tests passed![/bold green]\n\n"
                "[dim]Ready to commit. Your code is beautiful. ✨[/dim]",
                title="[bold]Success[/bold]",
                border_style="green",
                box=box.DOUBLE
            )
            self.console.print(success_panel)
        else:
            fail_panel = Panel(
                "[bold red]✗ Some tests failed[/bold red]\n\n"
                "[dim]Fix the issues above before committing.[/dim]",
                title="[bold]Failure[/bold]",
                border_style="red",
                box=box.DOUBLE
            )
            self.console.print(fail_panel)
            sys.exit(1)
    
    def run(self):
        """Main entry point."""
        self.print_header()
        self.run_all_stages()
        self.print_results()


# =============================================================================
# Entry Point
# =============================================================================

def main():
    """Run the professional test suite."""
    runner = TestRunner()
    runner.run()


if __name__ == "__main__":
    main()
