from __future__ import annotations

import csv
import json

from rich.console import Console
from rich.table import Table

from .labeler import LabelResult

console = Console()


def export_csv(results: list[LabelResult], output_path: str):
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["path", "labels", "description", "people_count", "dominant_colors", "analyzed_at", "model"])
        for r in results:
            writer.writerow([
                r.path,
                ", ".join(r.labels),
                r.description,
                r.people_count if r.people_count is not None else "",
                ", ".join(r.dominant_colors),
                r.analyzed_at,
                r.model,
            ])
    console.print(f"[green]Exported {len(results)} records to {output_path}[/green]")


def print_table(results: list[LabelResult]):
    table = Table(title=f"Photo Labels ({len(results)} photos)")
    table.add_column("Path", style="cyan", no_wrap=False, max_width=50)
    table.add_column("Labels", style="green")
    table.add_column("People", justify="right")
    table.add_column("Colors", style="yellow")

    for r in sorted(results, key=lambda x: x.path):
        table.add_row(
            r.path,
            ", ".join(r.labels[:6]),
            str(r.people_count) if r.people_count is not None else "—",
            ", ".join(r.dominant_colors[:3]),
        )
    console.print(table)


def print_json(results: list[LabelResult]):
    data = [
        {
            "path": r.path,
            "labels": r.labels,
            "description": r.description,
            "people_count": r.people_count,
            "dominant_colors": r.dominant_colors,
            "analyzed_at": r.analyzed_at,
            "model": r.model,
        }
        for r in results
    ]
    console.print_json(json.dumps(data))


def print_result(result: LabelResult, con: Console | None = None):
    c = con or console
    c.print(f"\n[bold cyan]{result.path}[/bold cyan]")
    c.print(f"  [dim]Labels:[/dim]  {', '.join(result.labels) or '(none)'}")
    c.print(f"  [dim]Desc:[/dim]    {result.description}")
    if result.people_count is not None:
        c.print(f"  [dim]People:[/dim]  {result.people_count}")
    c.print(f"  [dim]Colors:[/dim]  {', '.join(result.dominant_colors)}")


def print_summary(results: list[LabelResult]):
    console.print(f"\n[bold green]Done.[/bold green] Labeled {len(results)} photos total.")
