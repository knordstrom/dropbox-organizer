import os
import sys

import click
import dropbox
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .auth import DropboxAuthManager
from .config import DEFAULT_TOKEN_PATH, DEFAULT_STATE_PATH, CLAUDE_MODEL, SUPPORTED_EXTENSIONS, build_label_prompt
from .downloader import PhotoDownloader, FileTooLargeError
from .labeler import PhotoLabeler
from .scanner import DropboxScanner
from .state import StateManager
from . import costs, reporter

load_dotenv()
console = Console()


def _get_app_key(ctx_param_val: str | None) -> str:
    val = ctx_param_val or os.environ.get("DROPBOX_APP_KEY", "")
    if not val:
        console.print("[red]Error: DROPBOX_APP_KEY is required (set in .env or pass --app-key)[/red]")
        sys.exit(1)
    return val


def _get_api_key(ctx_param_val: str | None) -> str:
    val = ctx_param_val or os.environ.get("ANTHROPIC_API_KEY", "")
    if not val:
        console.print("[red]Error: ANTHROPIC_API_KEY is required (set in .env or pass --api-key)[/red]")
        sys.exit(1)
    return val


@click.group()
def main():
    """Dropbox photo labeling tool powered by Claude vision."""


@main.command()
@click.option("--app-key", envvar="DROPBOX_APP_KEY", default=None, help="Dropbox app key")
@click.option("--token-path", default=DEFAULT_TOKEN_PATH, show_default=True)
@click.option("--code", default=None, help="Authorization code from Dropbox (skips interactive prompt)")
def auth(app_key, token_path, code):
    """Authenticate with Dropbox and save credentials.

    Run without --code to get the authorization URL, then re-run with
    --code <value> to complete the flow.
    """
    app_key = _get_app_key(app_key)
    manager = DropboxAuthManager(app_key, token_path)

    if code is None:
        # Step 1: generate URL and save PKCE state
        auth_url = manager.start_pkce_flow()
        console.print("\nDropbox authorization required.")
        console.print(f"1. Visit this URL:\n\n   [cyan]{auth_url}[/cyan]\n")
        console.print("2. Click [bold]Allow[/bold], then copy the authorization code.")
        console.print("3. Re-run: [bold]dbo auth --code <paste-code-here>[/bold]")
        return

    # Step 2: exchange code
    refresh_token = manager.finish_pkce_flow(code)
    manager._save_token(refresh_token)
    dbx = dropbox.Dropbox(oauth2_refresh_token=refresh_token, app_key=app_key)
    account = dbx.users_get_current_account()
    console.print(f"[green]Authenticated as {account.name.display_name} ({account.email})[/green]")
    console.print(f"Token saved to {token_path}")


@main.command()
@click.option("--path", default="/", show_default=True, help="Dropbox folder to scan")
@click.option("--recursive/--no-recursive", default=True, show_default=True)
@click.option("--app-key", envvar="DROPBOX_APP_KEY", default=None)
@click.option("--token-path", default=DEFAULT_TOKEN_PATH, show_default=True)
@click.option("--state-file", default=DEFAULT_STATE_PATH, show_default=True)
def scan(path, recursive, app_key, token_path, state_file):
    """List photos in Dropbox and show which are already labeled."""
    app_key = _get_app_key(app_key)
    dbx = DropboxAuthManager(app_key, token_path).authenticate()
    state = StateManager(state_file)
    scanner = DropboxScanner(dbx)

    total = 0
    cached = 0
    console.print(f"Scanning [cyan]{path or '/'}[/cyan] for {', '.join(sorted(SUPPORTED_EXTENSIONS))} files...")

    for entry in scanner.list_photos(path, recursive):
        total += 1
        is_done = state.is_processed(entry.path_display, entry.content_hash)
        status = "[green]labeled[/green]" if is_done else "[yellow]unlabeled[/yellow]"
        if is_done:
            cached += 1
        console.print(f"  {status}  {entry.path_display}  [dim]({entry.size // 1024} KB)[/dim]")

    console.print(f"\nFound [bold]{total}[/bold] photos: {cached} labeled, {total - cached} unlabeled.")


def _print_cost_estimate(estimates: list[costs.CostEstimate], model: str, skipped: int):
    from rich.table import Table

    table = Table(title=f"Dry-run cost estimate  |  model: {model}")
    table.add_column("Photo", style="cyan", no_wrap=False, max_width=60)
    table.add_column("Size", justify="right", style="dim")
    table.add_column("Input tokens", justify="right")
    table.add_column("Output tokens", justify="right")
    table.add_column("Est. cost", justify="right", style="green")

    for e in estimates:
        table.add_row(
            e.path,
            f"{e.file_size_kb:.0f} KB",
            f"{e.input_tokens:,}",
            f"{e.output_tokens:,}",
            costs.format_cost(e.cost_usd),
        )

    console.print(table)

    total_cost = sum(e.cost_usd for e in estimates)
    total_input = sum(e.input_tokens for e in estimates)
    total_output = sum(e.output_tokens for e in estimates)
    console.print(
        f"\n[bold]Totals:[/bold] {len(estimates)} photos to process, {skipped} skipped (already labeled)"
        f"\n  Input tokens : {total_input:,}"
        f"\n  Output tokens: {total_output:,}"
        f"\n  [bold green]Estimated cost: {costs.format_cost(total_cost)}[/bold green]"
        f"\n  [dim](Estimates assume typical image dimensions from file size; actual cost may differ.)[/dim]"
    )

    pricing = costs.MODEL_PRICING.get(model)
    if pricing is None:
        console.print(f"  [yellow]Note: pricing for '{model}' is unknown; used fallback rates.[/yellow]")


@main.command()
@click.option("--path", default="/", show_default=True)
@click.option("--recursive/--no-recursive", default=True, show_default=True)
@click.option("--force", is_flag=True, help="Re-process already-labeled files")
@click.option("--model", default=CLAUDE_MODEL, show_default=True)
@click.option("--state-file", default=DEFAULT_STATE_PATH, show_default=True)
@click.option("--dry-run", is_flag=True, help="Show what would be processed without calling APIs")
@click.option("--limit", default=0, help="Process at most N photos (0 = unlimited)")
@click.option("--app-key", envvar="DROPBOX_APP_KEY", default=None)
@click.option("--api-key", envvar="ANTHROPIC_API_KEY", default=None)
@click.option("--token-path", default=DEFAULT_TOKEN_PATH, show_default=True)
@click.option(
    "--labels", "allowed_labels", multiple=True, metavar="LABEL",
    help="Allowed label(s). Repeat to specify multiple, e.g. --labels dog --labels cat",
)
@click.option(
    "--strict", is_flag=True,
    help="Only use labels from --labels; discard any others the model suggests",
)
def label(path, recursive, force, model, state_file, dry_run, limit, app_key, api_key, token_path, allowed_labels, strict):
    """Download and label photos using Claude vision."""
    app_key = _get_app_key(app_key)
    if not dry_run:
        api_key = _get_api_key(api_key)

    if strict and not allowed_labels:
        console.print("[red]Error: --strict requires at least one --labels value[/red]")
        sys.exit(1)

    label_list: list[str] | None = list(allowed_labels) if allowed_labels else None
    if label_list:
        mode = "strict" if strict else "preferred"
        console.print(f"Label set ({mode}): {', '.join(label_list)}")

    dbx = DropboxAuthManager(app_key, token_path).authenticate()
    state = StateManager(state_file)
    scanner = DropboxScanner(dbx)
    downloader = PhotoDownloader(dbx)
    labeler = PhotoLabeler(api_key, model)

    from .properties import DropboxPropertyWriter
    prop_writer = DropboxPropertyWriter(dbx) if not dry_run else None

    # Phase 1: scan to determine total work
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as scan_progress:
        scan_task = scan_progress.add_task(f"Scanning {path or '/'}...", total=None)
        all_entries = []
        for entry in scanner.list_photos(path, recursive):
            all_entries.append(entry)
            scan_progress.advance(scan_task)

    console.print(f"Found [bold]{len(all_entries)}[/bold] photos in {path or '/'}.")

    # Phase 2: split into to-process vs already-cached
    to_process = []
    skipped = 0
    for entry in all_entries:
        if not force and state.is_processed(entry.id, entry.content_hash):
            skipped += 1
        else:
            to_process.append(entry)

    if limit:
        to_process = to_process[:limit]

    console.print(f"[bold]{len(to_process)}[/bold] to process, {skipped} already labeled.")

    processed = 0
    errors = 0
    dry_run_estimates: list[costs.CostEstimate] = []

    # Phase 3: process with known total
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=False,
    ) as progress:
        task_id = progress.add_task("Labeling photos...", total=len(to_process))

        for entry in to_process:
            p = entry.path_display
            h = entry.content_hash
            fid = entry.id

            if dry_run:
                progress.update(task_id, description=f"Estimating: {p}")
                prompt_text = build_label_prompt(label_list, strict)
                est = costs.estimate(p, entry.size, prompt_text, model)
                dry_run_estimates.append(est)
                processed += 1
                progress.advance(task_id)
                continue

            progress.update(task_id, description=f"[{processed + 1}/{len(to_process)}] {p}")

            try:
                image_bytes, media_type = downloader.download_to_bytes(p)
                result = labeler.analyze(image_bytes, media_type, p, h, file_id=fid, allowed_labels=label_list, strict=strict)

                if prop_writer:
                    prop_writer.write_labels(p, result)

                state.update(result)
                reporter.print_result(result, console)
                processed += 1
                progress.advance(task_id)

            except FileTooLargeError as e:
                console.print(f"[yellow]Skipped (too large):[/yellow] {e}")
                skipped += 1
            except Exception as e:
                console.print(f"[red]Error processing {p}:[/red] {e}")
                errors += 1

    if dry_run_estimates:
        _print_cost_estimate(dry_run_estimates, model, skipped)
    else:
        console.print(f"\n[bold]Summary:[/bold] {processed} labeled, {skipped} skipped, {errors} errors.")


@main.command("remove-labels")
@click.option(
    "--labels", "labels_to_remove", multiple=True, required=True, metavar="LABEL",
    help="Label(s) to remove. Repeat for multiple, e.g. --labels dog --labels cat",
)
@click.option("--path", default="/", show_default=True, help="Only affect photos under this Dropbox path")
@click.option("--state-file", default=DEFAULT_STATE_PATH, show_default=True)
@click.option("--dry-run", is_flag=True, help="Show what would change without modifying the state file")
def remove_labels(labels_to_remove, path, state_file, dry_run):
    """Remove specific labels from all labeled photos under a path."""
    remove_set = set(labels_to_remove)
    state = StateManager(state_file)

    prefix = "" if path in ("/", "") else path

    # Preview what would change without committing
    if dry_run:
        state.load()
        p_lower = prefix.rstrip("/").lower()
        any_found = False
        for photo_path, entry in state._data.get("photos", {}).items():
            if p_lower and not photo_path.lower().startswith(p_lower):
                continue
            hits = [l for l in entry.get("labels", []) if l in remove_set]
            if hits:
                any_found = True
                console.print(f"  [cyan]{photo_path}[/cyan]  would remove: {', '.join(hits)}")
        if not any_found:
            console.print("[yellow]No matching labels found under that path.[/yellow]")
        return

    changed = state.remove_labels(remove_set, prefix)

    if not changed:
        console.print("[yellow]No matching labels found under that path.[/yellow]")
        return

    for photo_path, removed in sorted(changed):
        console.print(f"  [cyan]{photo_path}[/cyan]  removed: {', '.join(removed)}")

    console.print(f"\n[green]Removed label(s) {sorted(remove_set)} from {len(changed)} photo(s).[/green]")


@main.command()
@click.option("--state-file", default=DEFAULT_STATE_PATH, show_default=True)
@click.option("--output", default=None, help="Write CSV to this path")
@click.option("--format", "fmt", type=click.Choice(["table", "csv", "json"]), default="table", show_default=True)
def report(state_file, output, fmt):
    """Show a summary report of all labeled photos."""
    state = StateManager(state_file)
    results = state.get_all()

    if not results:
        console.print("[yellow]No labeled photos found. Run 'label' first.[/yellow]")
        return

    if output:
        reporter.export_csv(results, output)
    elif fmt == "csv":
        reporter.export_csv(results, "/dev/stdout")
    elif fmt == "json":
        reporter.print_json(results)
    else:
        reporter.print_table(results)

    reporter.print_summary(results)


@main.command("backfill-ids")
@click.option("--path", default="/", show_default=True, help="Dropbox folder to scan for IDs")
@click.option("--app-key", envvar="DROPBOX_APP_KEY", default=None)
@click.option("--token-path", default=DEFAULT_TOKEN_PATH, show_default=True)
@click.option("--state-file", default=DEFAULT_STATE_PATH, show_default=True)
def backfill_ids(path, app_key, token_path, state_file):
    """Fetch Dropbox file IDs for existing records and promote file_id to primary key."""
    app_key = _get_app_key(app_key)
    dbx = DropboxAuthManager(app_key, token_path).authenticate()
    state = StateManager(state_file)
    scanner = DropboxScanner(dbx)

    missing = set(state.paths_missing_file_id())
    if not missing:
        console.print("[green]All records already have a file_id.[/green]")
        return

    console.print(f"Backfilling file IDs for {len(missing)} records...")
    updated = 0
    not_found = 0

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  BarColumn(), TaskProgressColumn(), console=console) as progress:
        task_id = progress.add_task("Scanning Dropbox...", total=len(missing))

        for entry in scanner.list_photos(path, recursive=True):
            if entry.path_display in missing:
                state.set_file_id(entry.path_display, entry.id)
                missing.discard(entry.path_display)
                updated += 1
                progress.advance(task_id)
                if not missing:
                    break

    not_found = len(missing)
    console.print(f"\nUpdated: {updated}, not found in scan: {not_found}")

    remaining = state.paths_missing_file_id()
    if not remaining:
        console.print("[green]All records have file_id — promoting to primary key...[/green]")
        state._promote_file_id_to_pk()
        console.print("[green]Done. file_id is now the primary key.[/green]")
    else:
        console.print(f"[yellow]{len(remaining)} records still missing file_id. Re-run with a broader --path to cover them.[/yellow]")
