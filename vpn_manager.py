"""
mgr = VpnManager(username="username", password="password")
mgr.connect_to_vpn("ad1", connection_type="tcp")

mgr.disconnect()

mgr.connect_to_random_vpn(
    country_blacklist=None,
    country_whitelist=None,
    host_blacklist=None,
    host_whitelist=None,
    only_tcp=False,
    only_udp=False,
)

mgr.get_available_servers(only_tcp=False, only_udp=False)

mgr.get_available_servers_by_country(only_tcp=False, only_udp=False)

mgr.get_my_ip()

"""

from __future__ import annotations

from typing import Optional
import subprocess
import os
import random
from typing import Set


from list_configs import VpnConfig, ConnectionType
from ip_info import IPInfo

from dataclasses import dataclass


@dataclass
class VpnConnectionResult:
    """Result of a VPN connection."""

    ok: bool
    ip_info: IPInfo
    config: VpnConfig


class VpnManagerUtilities:
    @staticmethod
    def get_ovpn_path(server_id: str, connection_type: ConnectionType) -> str:
        folder = {
            ConnectionType.TCP: "ovpn_tcp",
            ConnectionType.UDP: "ovpn_udp",
        }[connection_type]

        dir_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs")
        fname = f"{server_id}.nordvpn.com.{connection_type.value}.ovpn"

        return os.path.join(dir_path, folder, fname)

    @staticmethod
    def create_pass_file(username: str, password: str, verbose: bool = False) -> str:
        from pass_file import create_nord_pass_file

        pass_file_path = create_nord_pass_file(username, password, verbose=verbose)
        return pass_file_path

    @staticmethod
    def delete_pass_file(pass_file_path: str) -> None:
        try:
            os.remove(pass_file_path)
        except FileNotFoundError:
            pass

    @staticmethod
    def config_files_are_present() -> bool:
        dir_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs")
        try:
            tcp_files = os.listdir(os.path.join(dir_path, "ovpn_tcp"))
            udp_files = os.listdir(os.path.join(dir_path, "ovpn_udp"))
            return len(tcp_files) > 0 and len(udp_files) > 0
        except (FileNotFoundError, OSError):
            return False

    @staticmethod
    def download_config_files() -> None:
        from download_configs import download_configs

        download_configs()

    @staticmethod
    def get_my_ip_info() -> IPInfo:
        from ip_info import get_ip_info

        return get_ip_info()


class VpnConnectionsHistory:
    def __init__(self):
        from collections import deque

        self.history = deque(maxlen=100)

    def add(self, config: VpnConfig) -> None:
        self.history.append(config)

    def get_history(self, last_n: int = 100) -> Set[VpnConfig]:
        if last_n <= 0:
            raise ValueError("last_n cannot be less than or equal to 0")
        if last_n > self.history.maxlen:
            raise ValueError(f"last_n cannot be greater than {self.history.maxlen}")
        # Convert deque to list to support slicing
        return set(list(self.history)[-last_n:])


class VpnManager:
    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password

        self.proc: Optional[subprocess.Popen[str]] = None
        self.history = VpnConnectionsHistory()

        if not VpnManagerUtilities.config_files_are_present():
            print("Downloading config files...")
            VpnManagerUtilities.download_config_files()
            print("Config files downloaded successfully")

    def connect_to_vpn(
        self, server_id: str, connection_type: ConnectionType, verbose: bool = False
    ) -> VpnConnectionResult:
        from connection import open_vpn

        self.disconnect()

        ovpn_path = VpnManagerUtilities.get_ovpn_path(server_id, connection_type)
        pass_path = VpnManagerUtilities.create_pass_file(
            self.username, self.password, verbose=verbose
        )

        result = open_vpn(
            ovpn_path=ovpn_path,
            auth_path=pass_path,
            verbose=verbose,
        )

        VpnManagerUtilities.delete_pass_file(pass_path)

        self.proc = result.proc

        config = VpnConfig(
            server_id=server_id,
            connection_type=connection_type,
        )
        if result.ok:
            self.history.add(config)

        return VpnConnectionResult(
            ok=result.ok,
            ip_info=VpnManagerUtilities.get_my_ip_info(),
            config=config,
        )

    def disconnect(self) -> None:
        from connection import close_vpn

        if self.proc is not None:
            close_vpn(self.proc)
            self.proc = None

    def _connect_to_random_vpn(
        self,
        country_blacklist: Optional[list[str]] = None,
        country_whitelist: Optional[list[str]] = None,
        host_blacklist: Optional[list[str]] = None,
        host_whitelist: Optional[list[str]] = None,
        only_tcp: bool = False,
        only_udp: bool = False,
        avoid_last_n_servers: int = 0,
        verbose: bool = False,
    ) -> VpnConnectionResult:
        configs = self.get_available_servers(only_tcp=only_tcp, only_udp=only_udp)

        if country_blacklist is not None:
            len_before = len(configs)
            configs = [
                config for config in configs if config.country not in country_blacklist
            ]
            print(
                f"Filtered out {len_before - len(configs)} servers due to country blacklist"
            )
        if country_whitelist is not None:
            len_before = len(configs)
            configs = [
                config for config in configs if config.country in country_whitelist
            ]
            print(
                f"Filtered out {len_before - len(configs)} servers due to country whitelist"
            )
        if host_blacklist is not None:
            host_blacklist = [
                VpnConfig.from_name(name) if isinstance(name, str) else name
                for name in host_blacklist
            ]
            len_before = len(configs)
            host_blacklist = set(host_blacklist)
            configs = [config for config in configs if config not in host_blacklist]
            print(
                f"Filtered out {len_before - len(configs)} servers due to host blacklist"
            )
        if host_whitelist is not None:
            host_whitelist = [
                VpnConfig.from_name(name) if isinstance(name, str) else name
                for name in host_whitelist
            ]
            len_before = len(configs)
            host_whitelist = set(host_whitelist)
            configs = [config for config in configs if config in host_whitelist]
            print(
                f"Filtered out {len_before - len(configs)} servers due to host whitelist"
            )

        if avoid_last_n_servers > 0:
            len_before = len(configs)
            history = self.history.get_history(last_n=avoid_last_n_servers)
            configs = [config for config in configs if config not in history]
            print(
                f"Filtered out {len_before - len(configs)} servers due to avoid last {avoid_last_n_servers} servers"
            )

        if len(configs) == 0:
            raise ValueError("No available servers found")

        vpn_config = random.choice(configs)
        result = self.connect_to_vpn(
            vpn_config.server_id, vpn_config.connection_type, verbose=verbose
        )
        if result.ok:
            ip_info = VpnManagerUtilities.get_my_ip_info()
            print(
                f"Connected to VPN in {ip_info.city}, {ip_info.region}, {ip_info.country}"
            )
        return VpnConnectionResult(
            ok=result.ok,
            ip_info=result.ip_info,
            config=vpn_config,
        )

    def connect_to_random_vpn(
        self,
        country_blacklist: Optional[list[str]] = None,
        country_whitelist: Optional[list[str]] = None,
        host_blacklist: Optional[list[str]] = None,
        host_whitelist: Optional[list[str]] = None,
        only_tcp: bool = False,
        only_udp: bool = False,
        avoid_last_n_servers: int = 0,
        max_attempts: int = 5,
        verbose: bool = False,
    ) -> VpnConnectionResult:
        for attempt in range(max_attempts):
            if attempt > 0:
                print(f"Failed to connect to VPN {attempt} times, trying again...")
            result = self._connect_to_random_vpn(
                country_blacklist=country_blacklist,
                country_whitelist=country_whitelist,
                host_blacklist=host_blacklist,
                host_whitelist=host_whitelist,
                only_tcp=only_tcp,
                only_udp=only_udp,
                avoid_last_n_servers=avoid_last_n_servers,
                verbose=verbose,
            )
            if result.ok:
                return result
        raise ValueError(f"Failed to connect to VPN after {max_attempts} attempts")

    def get_available_servers(
        self, only_tcp: bool = False, only_udp: bool = False
    ) -> list[VpnConfig]:
        from list_configs import get_vpn_configs

        return get_vpn_configs(only_tcp=only_tcp, only_udp=only_udp)

    def get_available_servers_by_country(
        self, only_tcp: bool = False, only_udp: bool = False
    ) -> dict[str, list[VpnConfig]]:
        from list_configs import get_vpn_configs_per_country

        return get_vpn_configs_per_country(only_tcp=only_tcp, only_udp=only_udp)

    def __del__(self) -> None:
        print(
            "Disconnecting from VPN on deconstruction of the VpnManager object class so we don't leak threads..."
        )
        print(
            " (If you want to have this VPN connection remain open you must keep the instance of the VpnManager object alive)"
        )
        self.disconnect()
        print("Disconnected from VPN")
