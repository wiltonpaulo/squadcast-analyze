from __future__ import annotations
from pathlib import Path
from typing import Optional, List
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
    # shows only the first line in case of a long payload
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
    status: List[str] = typer.Option(
        None,
        "--status",
        "-s",
        help=(
            "Filter by one or more statuses, e.g. "
            "--status acknowledged --status triggered or --status acknowledged,triggered"
        ),
    ),

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
    Supports multiple --status values by looping over the API when type is json or csv.
    """
    try:
        ensure_dirs()
        settings = load_settings(env_path)

        if export_type not in ("json", "csv"):
            raise typer.BadParameter("type must be 'json' or 'csv'")

        start_iso = start or settings.default_start
        end_iso = end or settings.default_end
        owner_id = team or settings.team_id  # can be None
        assigned_to = assignee or settings.assignee_id

        # ------------------------------------------------------------------
        # Normalize statuses (CLI overrides ENV)
        # ------------------------------------------------------------------
        status_list: list[str] = []

        # From CLI: e.g. --status acknowledged --status triggered, or --status ack,trig
        for item in status or []:
            for part in item.split(","):
                part = part.strip()
                if part:
                    status_list.append(part)

        # If no CLI, fallback to env settings.status (single or comma-separated string)
        if not status_list and settings.status:
            if isinstance(settings.status, str):
                for part in settings.status.split(","):
                    p = part.strip()
                    if p:
                        status_list.append(p)
            else:
                # in case someday Settings.status becomes a list
                status_list.extend(settings.status)

        # Remove duplicates keeping order
        seen = set()
        normalized_status_list: list[str] = []
        for s in status_list:
            if s not in seen:
                seen.add(s)
                normalized_status_list.append(s)
        status_list = normalized_status_list

        if not start_iso or not end_iso:
            raise typer.BadParameter("Provide --start/--end or set START_TIME/END_TIME in .env")

        token = get_access_token(settings.refresh_token, settings.auth_url)
        client = SquadcastClient(settings.base_api, token)

        # ------------------------------------------------------------------
        # Build base URL for debug (without status)
        # ------------------------------------------------------------------
        base_url = (
            f"{settings.base_api.rstrip('/')}/incidents/export?type={export_type}"
            f"&start_time={start_iso}&end_time={end_iso}"
        )
        if owner_id:
            base_url += f"&owner_id={owner_id}"
        if assigned_to:
            base_url += f"&assigned_to={assigned_to}"
        if tags:
            base_url += f"&tags={tags}"

        content: bytes

        # ------------------------------------------------------------------
        # Case 1: zero or one status => single API call
        # ------------------------------------------------------------------
        if len(status_list) <= 1:
            single_status = status_list[0] if status_list else None

            if debug:
                dbg_url = base_url
                if single_status:
                    dbg_url += f"&status={single_status}"
                typer.secho(f"DEBUG URL: {dbg_url}", fg=typer.colors.YELLOW)

            content = client.export_incidents(
                start_iso,
                end_iso,
                owner_id=owner_id,
                assigned_to=assigned_to,
                tags=tags,
                status=single_status,
                export_type=export_type,
            )

        # ------------------------------------------------------------------
        # Case 2: multiple statuses
        #   -> supported for both JSON and CSV via multiple calls
        # ------------------------------------------------------------------
        else:
            if debug:
                typer.secho(
                    f"DEBUG base URL (status will vary per request): {base_url}",
                    fg=typer.colors.YELLOW,
                )
                typer.secho(
                    f"DEBUG statuses (looping): {', '.join(status_list)}",
                    fg=typer.colors.YELLOW,
                )

            # JSON mode: merge records in a single {"data": [...]} payload
            if export_type == "json":
                all_records = []

                for s in status_list:
                    if debug:
                        typer.secho(f"DEBUG requesting status={s}", fg=typer.colors.BLUE)

                    part_content = client.export_incidents(
                        start_iso,
                        end_iso,
                        owner_id=owner_id,
                        assigned_to=assigned_to,
                        tags=tags,
                        status=s,
                        export_type="json",
                    )

                    try:
                        data = json.loads(part_content)
                    except Exception as e:
                        raise RuntimeError(f"Failed to parse JSON for status '{s}': {e}")

                    if isinstance(data, list):
                        all_records.extend(data)
                    elif isinstance(data, dict):
                        records = None
                        if "data" in data and isinstance(data["data"], list):
                            records = data["data"]
                        else:
                            if len(data) == 1:
                                only_val = next(iter(data.values()))
                                if isinstance(only_val, list):
                                    records = only_val
                        if records is not None:
                            all_records.extend(records)
                        else:
                            all_records.append(data)
                    else:
                        all_records.append(data)

                merged = {"data": all_records}
                content = json.dumps(merged).encode("utf-8")

            # CSV mode: keep a single header and merge all rows
            else:  # export_type == "csv"
                header: Optional[str] = None
                rows: list[str] = []

                for s in status_list:
                    if debug:
                        typer.secho(f"DEBUG requesting status={s}", fg=typer.colors.BLUE)

                    part_content = client.export_incidents(
                        start_iso,
                        end_iso,
                        owner_id=owner_id,
                        assigned_to=assigned_to,
                        tags=tags,
                        status=s,
                        export_type="csv",
                    )

                    # assume UTF-8 CSV
                    text = part_content.decode("utf-8").strip()
                    if not text:
                        continue

                    lines = text.splitlines()
                    if not lines:
                        continue

                    if header is None:
                        # first response: take header + data
                        header = lines[0]
                        rows.extend(lines[1:])
                    else:
                        # subsequent responses: skip header if it matches
                        if lines[0] == header:
                            rows.extend(lines[1:])
                        else:
                            # header differs (unexpected) -> be conservative and keep everything
                            rows.extend(lines)

                if header is None:
                    # no data at all
                    content = "".encode("utf-8")
                else:
                    merged_csv = "\n".join([header] + rows) + "\n"
                    content = merged_csv.encode("utf-8")


        # ------------------------------------------------------------------
        # Save output
        # ------------------------------------------------------------------
        out = Path("data/raw") / (
            f"incidents_{utc_stamp()}.json" if export_type == "json" else f"incidents_{utc_stamp()}.csv"
        )
        save_bytes(content, out)
        typer.secho(f"Saved: {out}", fg=typer.colors.GREEN)

        # If JSON, count records and show preview
        if export_type == "json":
            try:
                data = json.loads(content)
                records = data.get("data") if isinstance(data, dict) else data
                n = len(records) if isinstance(records, list) else (1 if records else 0)
                if debug:
                    preview = str(data)[:400]
                    typer.secho(f"DEBUG preview: {preview}", fg=typer.colors.YELLOW)
                if n == 0:
                    typer.secho("No records in response.", fg=typer.colors.BRIGHT_RED)
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