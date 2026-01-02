from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import StrEnum


class ConnectionType(StrEnum):
    TCP = "tcp"
    UDP = "udp"


@dataclass
class VpnConfig:
    server_id: str
    connection_type: ConnectionType

    def __post_init__(self) -> None:
        self.name = f"{self.server_id}.nordvpn.com.{self.connection_type.value}"

    @property
    def file_path(self) -> str:
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "configs",
            "ovpn_" + self.connection_type.value,
            self.name + ".ovpn",
        )

    @property
    def country(self) -> str:
        return re.split(r"\d+", self.name)[0]

    @classmethod
    def from_name(cls, name: str) -> VpnConfig:
        """Create a VpnConfig from a name.
        Example:
        >>> VpnConfig.from_name("ad1.nordvpn.com.tcp")
        VpnConfig(server_id="ad1", connection_type=ConnectionType.TCP)
        """
        if not name.endswith(".nordvpn.com.tcp") and not name.endswith(
            ".nordvpn.com.udp"
        ):
            raise ValueError(
                f"Invalid name: {name}. Must look like: ad1.nordvpn.com.tcp, us1013.nordvpn.com.udp, etc."
            )
        server_id = name.split(".")[0]
        connection_type = ConnectionType.TCP if "tcp" in name else ConnectionType.UDP
        return cls(server_id=server_id, connection_type=connection_type)

    @classmethod
    def from_file_name(cls, file_name: str) -> VpnConfig:
        server_id = file_name.split(".")[0]
        connection_type = (
            ConnectionType.TCP if "tcp" in file_name else ConnectionType.UDP
        )
        return cls(server_id=server_id, connection_type=connection_type)

    def __hash__(self) -> int:
        return hash((self.server_id, self.connection_type.value))


def _get_vpn_config_paths(only_tcp: bool = False, only_udp: bool = False) -> list[str]:
    if only_tcp and only_udp:
        raise ValueError("only_tcp and only_udp cannot be True at the same time")

    dir_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs")
    tcp_files = os.listdir(os.path.join(dir_path, "ovpn_tcp"))
    udp_files = os.listdir(os.path.join(dir_path, "ovpn_udp"))

    if only_tcp:
        return tcp_files
    if only_udp:
        return udp_files
    return tcp_files + udp_files


def get_vpn_configs(only_tcp: bool = False, only_udp: bool = False) -> list[VpnConfig]:
    paths = _get_vpn_config_paths(only_tcp=only_tcp, only_udp=only_udp)
    return [VpnConfig.from_file_name(os.path.basename(path)) for path in paths]


def get_vpn_configs_per_country(
    only_tcp: bool = False, only_udp: bool = False
) -> dict[str, list[VpnConfig]]:
    configs = get_vpn_configs(only_tcp=only_tcp, only_udp=only_udp)
    out: dict[str, list[VpnConfig]] = {}
    for config in configs:
        out.setdefault(config.country, []).append(config)
    return out
