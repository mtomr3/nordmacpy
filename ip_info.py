"""
IP information utilities using ipinfo.io API.

Example:
    info = get_ip_info()
    print(f"IP: {info.ip}")
    print(f"Location: {info.city}, {info.region}, {info.country}")
"""

from __future__ import annotations

import json
import subprocess
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class IPInfo(BaseModel):
    """IP information from ipinfo.io API."""

    ip: str = Field(..., description="IP address")
    city: Optional[str] = Field(None, description="City name")
    region: Optional[str] = Field(None, description="Region/state name")
    country: Optional[str] = Field(None, description="Country code")
    loc: Optional[str] = Field(
        None, description="Latitude and longitude (comma-separated)"
    )
    org: Optional[str] = Field(None, description="Organization/ISP")
    postal: Optional[str] = Field(None, description="Postal/ZIP code")
    timezone: Optional[str] = Field(None, description="Timezone")
    readme: Optional[HttpUrl] = Field(None, description="API documentation URL")

    @property
    def latitude(self) -> Optional[float]:
        """Extract latitude from loc field."""
        if not self.loc:
            return None
        try:
            parts = self.loc.split(",")
            if len(parts) >= 1:
                return float(parts[0].strip())
        except (ValueError, AttributeError):
            pass
        return None

    @property
    def longitude(self) -> Optional[float]:
        """Extract longitude from loc field."""
        if not self.loc:
            return None
        try:
            parts = self.loc.split(",")
            if len(parts) >= 2:
                return float(parts[1].strip())
        except (ValueError, AttributeError):
            pass
        return None


def get_ip_info(*, verbose: bool = False) -> IPInfo:
    """
    Fetch IP information from ipinfo.io API.

    Args:
        verbose: If True, print debug information.

    Returns:
        IPInfo object containing IP address and location information.

    Raises:
        RuntimeError: If the API request fails or returns invalid data.
    """
    # Use curl to match the codebase style (avoiding requests dependency)
    # curl is fine on macOS
    cmd = ["curl", "-s", "https://ipinfo.io/json"]
    if verbose:
        print(f"[ipinfo] $ {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10.0,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("ipinfo.io API request timed out")
    except Exception as e:
        raise RuntimeError(f"Failed to execute curl: {e}")

    if result.returncode != 0:
        error_msg = result.stderr or "Unknown error"
        raise RuntimeError(
            f"curl failed with return code {result.returncode}: {error_msg}"
        )

    response_text = result.stdout.strip()
    if not response_text:
        raise RuntimeError("ipinfo.io API returned empty response")

    if verbose:
        print(f"[ipinfo] response: {response_text}")

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Failed to parse JSON response: {e}\nResponse: {response_text}"
        )

    try:
        return IPInfo(**data)
    except Exception as e:
        raise RuntimeError(f"Failed to create IPInfo model: {e}\nData: {data}")


if __name__ == "__main__":
    # Demo
    info = get_ip_info(verbose=True)
    print(f"\nIP: {info.ip}")
    print(f"Location: {info.city}, {info.region}, {info.country}")
    print(f"Coordinates: {info.loc}")
    if info.latitude and info.longitude:
        print(f"Latitude: {info.latitude}, Longitude: {info.longitude}")
    print(f"Organization: {info.org}")
    print(f"Postal: {info.postal}")
    print(f"Timezone: {info.timezone}")
