#!/usr/bin/env python3
"""
Canvas TUI Test Runner - "Sexy Edition"
Runs all tests with beautiful output, coverage, and timing.
"""

import subprocess
import sys
from pathlib import Path

# Rich for beautiful output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, BarColumn, TextColumn
    from rich.live import Live
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

console = Console() if RICH_AVAILABLE else None


def run_command(cmd: list, description: str) -> tuple[bool, str]:
    """Run a command and return success + output."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def main():
    """Run the test suite with beautiful output."""
    if RICH_AVAILABLE and console:
        # Print header
        console.print(Panel.fit(
            "[bold cyan]CS3704 Canvas TUI Test Suite[/bold cyan]\n"
            "[dim]Running comprehensive test coverage with style[/dim]",
            border_style="cyan"
        ))

        # Test stages
        stages = [
            ("🔍 Lint Check", ["ruff", "check", "src", "tests"]),
            ("🎨 Format Check", ["ruff", "format", "--check", "src", "tests"]),
            ("🔬 Type Check", ["mypy", "src/canvas_tui", "--ignore-missing-imports"]),
            ("🧪 Unit Tests", ["pytest", "-q", "--tb=short"]),
            ("📊 Coverage", ["pytest", "--cov=canvas_tui", "--cov-report=term-missing", "-q"]),
        ]

        results = []

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Running tests...", total=len(stages))

            for name, cmd in stages:
                progress.update(task, description=f"[yellow]{name}[/yellow]")
                success, output = run_command(cmd, name)
                results.append((name, success, output))
                progress.advance(task)

        # Print results table
        table = Table(title="\n📊 Test Results", show_header=True, header_style="bold cyan")
        table.add_column("Stage", style="dim")
        table.add_column("Status", justify="center")

        all_passed = True
        for name, success, _ in results:
            status = "[green]✓ PASS[/green]" if success else "[red]✗ FAIL[/red]"
            table.add_row(name, status)
            if not success:
                all_passed = False

        console.print(table)

        # Print failures if any
        if not all_passed:
            console.print("\n[bold red]Failures:[/bold red]")
            for name, success, output in results:
                if not success:
                    console.print(Panel(output, title=f"[red]{name}[/red]", border_style="red"))

        # Final status
        if all_passed:
            console.print(Panel.fit(
                "[bold green]✓ All tests passed![/bold green]\n"
                "[dim]Ready to commit[/dim]",
                border_style="green"
            ))
        else:
            console.print(Panel.fit(
                "[bold red]✗ Some tests failed[/bold red]\n"
                "[dim]Fix issues before committing[/dim]",
                border_style="red"
            ))
            sys.exit(1)

    else:
        # Fallback without Rich
        print("CS3704 Canvas TUI Test Suite")
        print("=" * 50)

        stages = [
            ("Lint Check", ["ruff", "check", "src", "tests"]),
            ("Format Check", ["ruff", "format", "--check", "src", "tests"]),
            ("Type Check", ["mypy", "src/canvas_tui", "--ignore-missing-imports"]),
            ("Unit Tests", ["pytest", "-q"]),
            ("Coverage", ["pytest", "--cov=canvas_tui", "-q"]),
        ]

        all_passed = True
        for name, cmd in stages:
            print(f"\n{name}...", end=" ")
            success, output = run_command(cmd, name)
            if success:
                print("✓ PASS")
            else:
                print("✗ FAIL")
                print(output)
                all_passed = False

        print("\n" + "=" * 50)
        if all_passed:
            print("✓ All tests passed!")
        else:
            print("✗ Some tests failed")
            sys.exit(1)


if __name__ == "__main__":
    main()
