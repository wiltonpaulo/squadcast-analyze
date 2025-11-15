from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional
import requests


@dataclass
class SquadcastClient:
    """
    Minimal HTTP client for Squadcast Export API.
    Handles only one status per request (multi-status logic happens in the CLI).
    """
    base_api: str
    access_token: str
    timeout: int = 120  # seconds

    def _build_export_url(
        self,
        start_iso: str,
        end_iso: str,
        export_type: str,
        owner_id: Optional[str],
        assigned_to: Optional[str],
        tags: Optional[str],
        status: Optional[str],
    ) -> str:
        """
        Build the final Squadcast export URL.
        Only one status value is supported per request.
        """
        url = (
            f"{self.base_api.rstrip('/')}/incidents/export"
            f"?type={export_type}"
            f"&start_time={start_iso}"
            f"&end_time={end_iso}"
        )

        # Optional filters
        if owner_id:
            url += f"&owner_id={owner_id}"
        if assigned_to:
            url += f"&assigned_to={assigned_to}"
        if tags:
            url += f"&tags={tags}"
        if status:
            # This must be a single status string. Multi-status is handled in the CLI.
            url += f"&status={status}"

        return url

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

        NOTE:
        - The Squadcast API accepts ONLY ONE status per request.
        - Multi-status behavior (looping and merging) is implemented in the CLI.
        """

        # Prepare request URL
        url = self._build_export_url(
            start_iso=start_iso,
            end_iso=end_iso,
            export_type=export_type,
            owner_id=owner_id,
            assigned_to=assigned_to,
            tags=tags,
            status=status,
        )

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json" if export_type == "json" else "text/csv",
        }

        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
        except requests.exceptions.RequestException as exc:
            # Network or transport-level error
            raise RuntimeError(f"Request failed: {exc}")

        # Handle HTTP errors
        if response.status_code != 200:
            msg = response.text[:4000]  # avoid huge stack traces
            raise RuntimeError(f"HTTP {response.status_code}: {msg}")

        return response.content
