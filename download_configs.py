from __future__ import annotations

import os
import pathlib
import zipfile
import urllib.request

OVPN_ZIP_URL = "https://downloads.nordcdn.com/configs/archives/servers/ovpn.zip"


def download_and_extract_nordvpn_ovpn_zip(
    out_dir: str | os.PathLike,
    zip_path: str | os.PathLike | None = None,
    overwrite_zip: bool = True,
) -> tuple[pathlib.Path, pathlib.Path]:
    """
    Downloads NordVPN's official OpenVPN config archive and extracts it.

    Returns: (zip_file_path, extracted_root_dir)
    """
    out_dir = pathlib.Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if zip_path is None:
        zip_path = out_dir / "ovpn.zip"
    else:
        zip_path = pathlib.Path(zip_path).expanduser().resolve()

    if zip_path.exists() and not overwrite_zip:
        raise FileExistsError(f"Zip already exists: {zip_path}")

    # Download
    # print(f"Downloading: {OVPN_ZIP_URL}")
    # print(f"To:         {zip_path}")
    urllib.request.urlretrieve(OVPN_ZIP_URL, zip_path)

    # Extract
    extracted_root = out_dir
    extracted_root.mkdir(parents=True, exist_ok=True)

    # print(f"Extracting to: {extracted_root}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extracted_root)

    # Delete zip file after extraction
    try:
        zip_path.unlink()
        # print(f"Deleted zip file: {zip_path}")
    except OSError as e:
        print(f"Warning: Could not delete zip file {zip_path}: {e}")

    # Quick sanity info
    # tcp_dir = extracted_root / "ovpn_tcp"
    # udp_dir = extracted_root / "ovpn_udp"
    # print("Done.")
    # print(
    #     f"Found ovpn_tcp: {tcp_dir.exists()} ({sum(1 for _ in tcp_dir.glob('*.ovpn')) if tcp_dir.exists() else 0} files)"
    # )
    # print(
    #     f"Found ovpn_udp: {udp_dir.exists()} ({sum(1 for _ in udp_dir.glob('*.ovpn')) if udp_dir.exists() else 0} files)"
    # )

    return zip_path, extracted_root


def download_configs():
    folder = pathlib.Path(__file__).parent / "configs"
    download_and_extract_nordvpn_ovpn_zip(folder)


if __name__ == "__main__":
    download_configs()
