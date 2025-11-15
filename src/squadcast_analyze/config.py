from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    refresh_token: str
    auth_url: str
    base_api: str
    team_id: Optional[str] = None
    assignee_id: Optional[str] = None
    status: Optional[List[str]] = None
    default_start: Optional[str] = None
    default_end: Optional[str] = None


def load_settings(env_path: str | None = ".env") -> Settings:
    """
    Load configuration from .env file or environment variables.
    """
    if env_path and Path(env_path).exists():
        load_dotenv(env_path)

    refresh = os.getenv("SQUADCAST_REFRESH_TOKEN")
    auth = os.getenv("SQUADCAST_AUTH_URL", "https://auth.squadcast.com/oauth/access-token")
    base = os.getenv("SQUADCAST_BASE_API", "https://api.squadcast.com/v3")

    # Parse STATUS=a,b,c into a normalized list
    raw_status = os.getenv("STATUS", "")
    status_list: List[str] = []
    if raw_status:
        for item in raw_status.split(","):
            cleaned = item.strip().lower()
            if cleaned:
                status_list.append(cleaned)

    if not refresh:
        raise RuntimeError("SQUADCAST_REFRESH_TOKEN is required (set it in .env)")

    return Settings(
        refresh_token=refresh,
        auth_url=auth,
        base_api=base,
        team_id=os.getenv("SQUADCAST_TEAM_ID"),
        assignee_id=os.getenv("SQUADCAST_ASSIGNEE_ID"),
        status=status_list or None,
        default_start=os.getenv("START_TIME"),
        default_end=os.getenv("END_TIME"),
    )
