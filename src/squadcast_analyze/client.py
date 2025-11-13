from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional
import requests


@dataclass
class SquadcastClient:
    base_api: str
    access_token: str
    timeout: int = 120

    def export_incidents(
        self,
        start_iso: str,
        end_iso: str,
        owner_id: Optional[str] = None,
        assigned_to: Optional[str] = None,
        tags: Optional[str] = None,
        status: Optional[str] = None,
        export_type: Literal["json", "csv"] = "json",
    ) -> bytes:
        """
        Export incidents from Squadcast within a time window.
        """
        url = (
            f"{self.base_api.rstrip('/')}/incidents/export"
            f"?type={export_type}&start_time={start_iso}&end_time={end_iso}"
        )
        if owner_id:
            url += f"&owner_id={owner_id}"

        if assigned_to:
            url += f"&assigned_to={assigned_to}"
        if tags:
            url += f"&tags={tags}"
        if status:
            status += f"&status={status}"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json" if export_type == "json" else "text/csv",
        }

        resp = requests.get(url, headers=headers, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"Error {resp.status_code}: {resp.text[:4000]}")

        return resp.content
