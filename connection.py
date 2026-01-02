from __future__ import annotations

import os
import re
import time
import signal
import shutil
import random
import socket
import subprocess
import threading
from dataclasses import dataclass
from typing import Optional, Sequence

# ----------------------------
# Models
# ----------------------------


@dataclass
class OpenVpnResult:
    ok: bool
    proc: Optional[subprocess.Popen[str]]
    reason: str


# ----------------------------
# Stream watcher
# ----------------------------


class StreamWatcher(threading.Thread):
    """
    Reads a text stream line-by-line, optionally prints it, and sets events on:
      - `needle` seen (init completed)
      - process exit
    Also retains recent lines for debugging.
    """

    def __init__(
        self,
        stream,
        needle: str,
        *,
        init_event: threading.Event,
        exit_event: threading.Event,
        verbose: bool = False,
        keep_last_n: int = 300,
    ):
        super().__init__(daemon=True)
        self.stream = stream
        self.needle = needle
        self.init_event = init_event
        self.exit_event = exit_event
        self.verbose = verbose
        self.keep_last_n = keep_last_n
        self.lines: list[str] = []
        self._lock = threading.Lock()

    def tail(self) -> str:
        with self._lock:
            return "".join(self.lines[-self.keep_last_n :])

    def run(self) -> None:
        try:
            for line in iter(self.stream.readline, ""):
                with self._lock:
                    self.lines.append(line)
                    if len(self.lines) > self.keep_last_n * 2:
                        self.lines = self.lines[-self.keep_last_n :]

                if self.verbose:
                    print(line, end="")

                if self.needle in line:
                    self.init_event.set()
        finally:
            self.exit_event.set()
            try:
                self.stream.close()
            except Exception:
                pass


# ----------------------------
# Logging + command runner
# ----------------------------


def _cmd_str(cmd: Sequence[str]) -> str:
    return " ".join(shlex_quote(x) for x in cmd)


def shlex_quote(s: str) -> str:
    # minimal quote helper (avoid importing shlex just to print)
    if not s:
        return "''"
    if re.search(r"[^\w@%+=:,./-]", s):
        return "'" + s.replace("'", "'\"'\"'") + "'"
    return s


def _looks_like_sudo_tty_problem(out: str) -> bool:
    t = out.lower()
    return (
        "a terminal is required to read the password" in t
        or "a password is required" in t
        or "sudo:" in t
        and "password" in t
        or "sorry, you must have a tty" in t
    )


def _run_cmd(
    cmd: Sequence[str],
    *,
    timeout_s: float = 10.0,
    check: bool = False,
    label: str = "cmd",
    print_cmd: bool = True,
    verbose: bool = False,
) -> tuple[int, str]:
    """
    Run a command and return (rc, combined_output).
    If check=True, raises RuntimeError on non-zero with rich context.
    """
    if print_cmd and verbose:
        print(f"[{label}] $ {_cmd_str(cmd)}")
    try:
        p = subprocess.run(
            list(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_s,
        )
        out = p.stdout or ""
        if verbose:
            if out.strip():
                print(f"[{label}] rc={p.returncode}\n{out.rstrip()}\n")
            else:
                print(f"[{label}] rc={p.returncode}\n")
        if check and p.returncode != 0:
            extra = ""
            if _looks_like_sudo_tty_problem(out):
                extra = (
                    "\nLikely cause: sudo is prompting but Python has no TTY.\n"
                    "Fix: use sudo -n and add the exact command to visudo NOPASSWD.\n"
                )
            raise RuntimeError(f"{label} failed rc={p.returncode}{extra}\n{out}")
        return p.returncode, out
    except subprocess.TimeoutExpired as e:
        out = ""
        if getattr(e, "stdout", None):
            out += e.stdout
        if getattr(e, "stderr", None):
            out += e.stderr
        out += "\n[TIMEOUT]\n"
        if verbose:
            print(f"[{label}] rc=124\n{out.rstrip()}\n")
        if check:
            raise RuntimeError(f"{label} timed out\n{out}")
        return 124, out
    except Exception as e:
        out = f"[EXCEPTION] {e}\n"
        if verbose:
            print(f"[{label}] rc=127\n{out.rstrip()}\n")
        if check:
            raise
        return 127, out


def _sudo_cmd(
    cmd: Sequence[str],
    *,
    timeout_s: float = 10.0,
    check: bool = False,
    label: str = "sudo",
    verbose: bool = False,
) -> tuple[int, str]:
    """
    Run sudo in *non-interactive* mode so failures are explicit.
    """
    sudo = shutil.which("sudo") or "sudo"
    # -n: non-interactive; fail immediately if it would prompt.
    return _run_cmd([sudo, "-n", *cmd], timeout_s=timeout_s, check=check, label=label, verbose=verbose)


# ----------------------------
# Network probes / snapshots
# ----------------------------


def _tcp_connect_ok(host: str, port: int, *, timeout_s: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except Exception:
        return False


def _route_uses_utun(ip: str, *, verbose: bool = False) -> bool:
    rc, out = _run_cmd(
        ["route", "-n", "get", ip], timeout_s=3.0, label="route-get", print_cmd=False, verbose=verbose
    )
    if rc != 0:
        return False
    return bool(re.search(r"interface:\s+utun\d+", out))


def _internet_probe_ok(
    *,
    timeout_s: float = 5.0,
    require_vpn_route: bool = True,
    verbose: bool = False,
) -> tuple[bool, str]:
    if require_vpn_route:
        if not _route_uses_utun("1.1.1.1", verbose=verbose):
            return False, "route-to-1.1.1.1-not-utun"

    tests = [
        ("api.ipify.org", 443),
        ("1.1.1.1", 443),
    ]
    start = time.monotonic()
    for host, port in tests:
        ok = _tcp_connect_ok(host, port, timeout_s=min(3.0, timeout_s))
        if not ok:
            elapsed = time.monotonic() - start
            return False, f"tcp-connect-failed {host}:{port} after {elapsed:.2f}s"
    return True, "probe-ok"


def _snapshot(*, label: str, verbose: bool = False) -> None:
    if verbose:
        print(f"\n===== SNAPSHOT ({label}) =====")
    _run_cmd(
        ["netstat", "-rn", "-f", "inet"],
        timeout_s=3.0,
        label="netstat",
        print_cmd=verbose,
        verbose=verbose,
    )
    _run_cmd(
        ["scutil", "--proxy"], timeout_s=3.0, label="scutil-proxy", print_cmd=verbose, verbose=verbose
    )
    _run_cmd(["scutil", "--dns"], timeout_s=3.0, label="scutil-dns", print_cmd=verbose, verbose=verbose)
    if verbose:
        print("===== END SNAPSHOT =====\n")


def _get_public_ip(*, verbose: bool = False) -> str:
    # avoid requests dependency inside this module
    # curl is fine on macOS
    rc, out = _run_cmd(
        ["curl", "-sS", "--noproxy", "*", "https://api.ipify.org?format=json"],
        timeout_s=8.0,
        label="ipify",
        print_cmd=False,
        verbose=verbose,
    )
    m = re.search(r'"ip"\s*:\s*"([^"]+)"', out)
    return m.group(1) if m else out.strip()


# ----------------------------
# Process controls
# ----------------------------


def _send_signal_to_process_group(proc: subprocess.Popen, sig: int) -> None:
    if os.name == "nt":
        proc.send_signal(sig)
        return
    os.killpg(proc.pid, sig)


def stop_process(
    proc: subprocess.Popen,
    *,
    sigint_grace_s: float = 5.0,
    sigterm_grace_s: float = 3.0,
) -> int:
    rc = proc.poll()
    if rc is not None:
        return rc

    try:
        _send_signal_to_process_group(proc, signal.SIGINT)
    except Exception:
        try:
            proc.send_signal(signal.SIGINT)
        except Exception:
            pass

    try:
        return proc.wait(timeout=sigint_grace_s)
    except subprocess.TimeoutExpired:
        pass

    try:
        _send_signal_to_process_group(proc, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass

    try:
        return proc.wait(timeout=sigterm_grace_s)
    except subprocess.TimeoutExpired:
        pass

    try:
        _send_signal_to_process_group(proc, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    return proc.wait()


# ----------------------------
# Cleanup (IMPORTANT)
# ----------------------------


def _delete_def1_routes(*, verbose: bool = False) -> None:
    # remove def1 split default routes if present
    # NOTE: these require sudo
    _sudo_cmd(
        ["route", "-n", "delete", "-inet", "0.0.0.0/1"],
        timeout_s=3.0,
        label="cleanup-route-0/1",
        verbose=verbose,
    )
    _sudo_cmd(
        ["route", "-n", "delete", "-inet", "128.0.0.0/1"],
        timeout_s=3.0,
        label="cleanup-route-128/1",
        verbose=verbose,
    )


def _flush_dns(*, verbose: bool = False) -> None:
    _sudo_cmd(["dscacheutil", "-flushcache"], timeout_s=5.0, label="cleanup-dnsflush", verbose=verbose)
    _sudo_cmd(["killall", "-HUP", "mDNSResponder"], timeout_s=5.0, label="cleanup-mdns", verbose=verbose)


def _kill_openvpn(*, verbose: bool = False) -> None:
    # best-effort
    _sudo_cmd(["pkill", "-TERM", "openvpn"], timeout_s=3.0, label="cleanup-pkill-term", verbose=verbose)
    time.sleep(0.2)
    _sudo_cmd(["pkill", "-KILL", "openvpn"], timeout_s=3.0, label="cleanup-pkill-kill", verbose=verbose)


def _best_effort_cleanup(*, verbose: bool = False) -> tuple[bool, str]:
    """
    Returns (ok, reason). If ok=False, reason will be very specific.
    """
    try:
        _kill_openvpn(verbose=verbose)
        _flush_dns(verbose=verbose)
        _delete_def1_routes(verbose=verbose)
        time.sleep(0.3)
        if verbose:
            _snapshot(label="post-cleanup", verbose=verbose)
        return True, "cleanup-ok"
    except RuntimeError as e:
        # this is where sudo -n failures will surface
        return False, f"cleanup-failed: {e}"


# ----------------------------
# OpenVPN runner
# ----------------------------


def open_vpn(
    *,
    ovpn_path: str,
    auth_path: str,
    timeout_s: float = 25.0,
    needle: str = "Initialization Sequence Completed",
    extra_openvpn_args: Optional[list[str]] = None,
    verbose: bool = False,
    pre_cleanup: bool = True,
    post_init_probe: bool = True,
    probe_timeout_s: float = 8.0,
) -> OpenVpnResult:
    extra_openvpn_args = extra_openvpn_args or []

    # Baseline IP so you can tell if anything changed at all
    baseline_ip = _get_public_ip(verbose=verbose)
    if verbose:
        print(f"[baseline] exit ip: {baseline_ip}")

    if pre_cleanup:
        ok, reason = _best_effort_cleanup(verbose=verbose)
        if not ok:
            if verbose:
                _snapshot(label="cleanup-failed", verbose=verbose)
            return OpenVpnResult(ok=False, proc=None, reason=reason)

    # IMPORTANT: always run openvpn via sudo -n as well,
    # otherwise it may prompt and hang/fail weirdly.
    argv = [
        "sudo",
        "-n",
        "openvpn",
        "--config",
        ovpn_path,
        "--auth-user-pass",
        auth_path,
        "--auth-nocache",
        "--verb",
        "3",
        "--ping",
        "10",
        "--ping-restart",
        "30",
        *extra_openvpn_args,
    ]
    if verbose:
        print("[openvpn] argv:", argv)

    proc: subprocess.Popen[str] = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )

    assert proc.stdout is not None
    init_event = threading.Event()
    exit_event = threading.Event()

    watcher = StreamWatcher(
        proc.stdout,
        needle,
        init_event=init_event,
        exit_event=exit_event,
        verbose=verbose,
    )
    watcher.start()

    deadline = time.monotonic() + timeout_s

    while True:
        if init_event.is_set():
            break

        rc = proc.poll()
        if rc is not None:
            tail = watcher.tail()
            _best_effort_cleanup(verbose=False)
            return OpenVpnResult(
                ok=False,
                proc=None,
                reason=f"openvpn-exited-early rc={rc}\nTAIL:\n{tail}",
            )

        if time.monotonic() >= deadline:
            tail = watcher.tail()
            final_rc = stop_process(proc)
            _best_effort_cleanup(verbose=False)
            return OpenVpnResult(
                ok=False,
                proc=None,
                reason=f"timeout-waiting-init final_rc={final_rc}\nTAIL:\n{tail}",
            )

        time.sleep(0.05)

    # init seen; verify still alive
    rc = proc.poll()
    if rc is not None:
        tail = watcher.tail()
        _best_effort_cleanup(verbose=False)
        return OpenVpnResult(
            ok=False, proc=None, reason=f"exited-after-init rc={rc}\nTAIL:\n{tail}"
        )

    if post_init_probe:
        probe_deadline = time.monotonic() + probe_timeout_s
        last_reason = "probe-not-run"
        while time.monotonic() < probe_deadline:
            rc = proc.poll()
            if rc is not None:
                tail = watcher.tail()
                _best_effort_cleanup(verbose=False)
                return OpenVpnResult(
                    ok=False,
                    proc=None,
                    reason=f"died-during-probe rc={rc}\nTAIL:\n{tail}",
                )

            ok, reason = _internet_probe_ok(
                timeout_s=min(5.0, probe_deadline - time.monotonic()),
                require_vpn_route=True,
                verbose=verbose,
            )
            if ok:
                # log the VPN exit IP for sanity
                vpn_ip = _get_public_ip(verbose=verbose)
                if verbose:
                    print(f"[vpn] exit ip: {vpn_ip}")
                return OpenVpnResult(ok=True, proc=proc, reason="initialized+probe-ok")

            last_reason = reason
            time.sleep(0.25)

        tail = watcher.tail()
        final_rc = stop_process(proc)
        _best_effort_cleanup(verbose=False)
        if verbose:
            _snapshot(label="probe-failed", verbose=verbose)
        return OpenVpnResult(
            ok=False,
            proc=None,
            reason=f"init-seen-but-probe-failed: {last_reason}; stopped rc={final_rc}\nTAIL:\n{tail}",
        )

    return OpenVpnResult(ok=True, proc=proc, reason="initialized")


def close_vpn(proc: subprocess.Popen[str], *, verbose: bool = False) -> int:
    rc = stop_process(proc)
    _best_effort_cleanup(verbose=verbose)
    return rc


# ----------------------------
# Config helpers
# ----------------------------


def get_vpn_configs(only_tcp: bool = False, only_udp: bool = False) -> list[str]:
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


def get_vpn_configs_per_country(
    only_tcp: bool = False,
    only_udp: bool = False,
) -> dict[str, list[str]]:
    configs = get_vpn_configs(only_tcp=only_tcp, only_udp=only_udp)
    out: dict[str, list[str]] = {}
    for config in configs:
        country = re.split(r"\d+", config)[0]
        out.setdefault(country, []).append(config)
    return out


def get_random_vpn_config(only_tcp: bool = False, only_udp: bool = False) -> str:
    if only_tcp and only_udp:
        raise ValueError("only_tcp and only_udp cannot be True at the same time")

    dir_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs")
    tcp_dir = os.path.join(dir_path, "ovpn_tcp")
    udp_dir = os.path.join(dir_path, "ovpn_udp")

    tcp_configs = os.listdir(tcp_dir)
    udp_configs = os.listdir(udp_dir)

    use_tcp = True if only_tcp else False if only_udp else random.choice([True, False])
    folder = tcp_dir if use_tcp else udp_dir
    cfg = random.choice(tcp_configs if use_tcp else udp_configs)
    return os.path.join(folder, cfg)


# ----------------------------
# Demo
# ----------------------------

if __name__ == "__main__":
    cfg = get_random_vpn_config(only_tcp=True)
    print("cfg:", cfg)
    res = open_vpn(ovpn_path=cfg, auth_path="vpn/pass.txt", verbose=True)
    print("ok:", res.ok, "reason:", res.reason)
    if res.ok and res.proc:
        time.sleep(3)
        close_vpn(res.proc)
