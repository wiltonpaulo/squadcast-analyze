from __future__ import annotations
from pathlib import Path
from typing import Optional
import json
import typer
from tabulate import tabulate

from .config import load_settings
from .auth import get_access_token
from .client import SquadcastClient
from .io_utils import ensure_dirs, utc_stamp, save_bytes, load_json_records
from .analyzer import to_dataframe, top_counts

app = typer.Typer(help="Squadcast Analyze CLI - fetch & analyze incidents")


# ---------- helpers ----------
def _err(msg: str, exit_code: int = 1) -> None:
    """Print a clean error (no traceback) and exit."""
    # mostra só a primeira linha caso venha um payload longo
    short = msg.splitlines()[0].strip()
    typer.secho(f"❌ {short}", fg=typer.colors.RED)
    raise typer.Exit(exit_code)


# ---------- commands ----------
@app.command()
def auth(env_path: Optional[str] = typer.Option(".env", help="Path to .env")):
    """
    Prints an access token (uses X-Refresh-Token flow).
    """
    try:
        settings = load_settings(env_path)
        token = get_access_token(settings.refresh_token, settings.auth_url)
        typer.echo(token)
    except Exception as e:
        _err(f"Auth failed: {e}")


@app.command()
def fetch(
    # Main filters
    start: Optional[str] = typer.Option(None, help="ISO start time (UTC)"),
    end: Optional[str] = typer.Option(None, help="ISO end time (UTC)"),
    tags: Optional[str] = typer.Option(None, help="Single Tag as key=value"),
    status: Optional[str] = typer.Option(None, help="Status=acknowledged"),

    # Assignee filters
    team: Optional[str] = typer.Option(None, help="Owner/team id (owner_id)"),
    assignee: Optional[str] = typer.Option(None, help="Assignee Id (assigned_to)"),

    # Extras
    export_type: str = typer.Option("json", "--type", help="json or csv"),
    env_path: Optional[str] = typer.Option(".env", help="Path to .env"),
    debug: bool = typer.Option(False, help="Print debug info (URL, sample of payload)"),
):
    """
    Fetch incidents (export) and save to data/raw.
    """
    try:
        ensure_dirs()
        settings = load_settings(env_path)

        if export_type not in ("json", "csv"):
            raise typer.BadParameter("type must be 'json' or 'csv'")

        start_iso = start or settings.default_start
        end_iso = end or settings.default_end
        owner_id = team or settings.team_id  # pode ser None
        assigned_to = assignee or settings.assignee_id
        status = status or settings.status

        if not start_iso or not end_iso:
            raise typer.BadParameter("Provide --start/--end or set START_TIME/END_TIME in .env")

        token = get_access_token(settings.refresh_token, settings.auth_url)
        client = SquadcastClient(settings.base_api, token)

        # URL para debug (log amigável, sem realizar chamada extra)
        dbg_url = (
            f"{settings.base_api.rstrip('/')}/incidents/export?type={export_type}"
            f"&start_time={start_iso}&end_time={end_iso}"
        )
        if owner_id:
            dbg_url += f"&owner_id={owner_id}"
        if assigned_to:
            dbg_url += f"&assigned_to={assigned_to}"
        if tags:
            dbg_url += f"&tags={tags}"
        if status:
            dbg_url += f"&status={status}"
        if debug:
            typer.secho(f"DEBUG URL: {dbg_url}", fg=typer.colors.YELLOW)

        content = client.export_incidents(
            start_iso, end_iso, owner_id=owner_id, assigned_to=assigned_to, tags=tags, status=status, export_type=export_type
        )
        out = Path("data/raw") / (
            f"incidents_{utc_stamp()}.json" if export_type == "json" else f"incidents_{utc_stamp()}.csv"
        )
        save_bytes(content, out)
        typer.secho(f"Saved: {out}", fg=typer.colors.GREEN)

        # Se JSON, conta registros e avisa
        if export_type == "json":
            try:
                data = json.loads(content)
                records = data.get("data") if isinstance(data, dict) else data
                n = len(records) if isinstance(records, list) else (1 if records else 0)
                if debug:
                    preview = str(data)[:400]
                    typer.secho(f"DEBUG preview: {preview}", fg=typer.colors.YELLOW)
                if n == 0:
                   ...
                else:
                    typer.secho(f"Records: {n}", fg=typer.colors.CYAN)
            except Exception:
                if debug:
                    typer.secho("DEBUG: failed to parse JSON preview", fg=typer.colors.RED)

    except typer.BadParameter as e:
        _err(str(e))
    except Exception as e:
        _err(f"Fetch failed: {e}")

@app.command()
def analyze(
    input: str = typer.Option(..., help="Path to JSON exported file"),
    group_by: str = typer.Option(
        "service", help="Field to group by (e.g., service, environment, priority)"
    ),
    top: int = typer.Option(10, help="Top N"),
    csv_out: Optional[str] = typer.Option(None, help="Optional CSV output"),
):
    """
    Analyze Top-N counts grouped by any field (smart matching on nested columns).
    """
    try:
        path = Path(input)
        if not path.exists():
            raise typer.BadParameter(f"Input not found: {path}")

        records = load_json_records(path)
        if not records:
            _err("No records to analyze.", exit_code=2)

        df = to_dataframe(records)
        table = top_counts(df, group_by, top)

        typer.echo(tabulate(table, headers="keys", tablefmt="github", showindex=False))

        if csv_out:
            out_path = Path(csv_out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            table.to_csv(out_path, index=False)
            typer.secho(f"CSV saved: {out_path}", fg=typer.colors.GREEN)

    except typer.BadParameter as e:
        _err(str(e))
    except Exception as e:
        _err(f"Analyze failed: {e}")


@app.command()
def list_fields(input: str = typer.Option(..., help="Path to JSON exported file")):
    """
    Show available fields/columns in the JSON (after normalization to DataFrame).
    Useful to know what to group by in 'analyze'.
    """
    try:
        path = Path(input)
        if not path.exists():
            raise typer.BadParameter(f"Input not found: {path}")

        records = load_json_records(path)
        if not records:
            typer.secho("No records found in file.", fg=typer.colors.BRIGHT_RED)
            raise typer.Exit(2)

        df = to_dataframe(records)
        cols = list(df.columns)

        typer.secho("Available fields:\n", fg=typer.colors.CYAN)
        for c in cols:
            typer.echo(f"- {c}")
        typer.secho(f"\nTotal fields: {len(cols)}", fg=typer.colors.GREEN)

    except Exception as e:
        msg = str(e).splitlines()[0].strip()
        typer.secho(f"❌ {msg}", fg=typer.colors.RED)
        raise typer.Exit(1)
