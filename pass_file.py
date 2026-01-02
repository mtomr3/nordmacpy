import tempfile


def create_nord_pass_file(username, password, verbose: bool = False):
    """
    Creates a temporary file for NordVPN OpenVPN authentication.
    The file is automatically deleted when the script finishes.
    """
    # Create a named temporary file (delete=False allows other processes to read it)
    # Using 'w' for text mode
    tmp_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")

    # Standard OpenVPN format: username on line 1, password on line 2
    tmp_file.write(f"{username}\n{password}")
    tmp_file.close()  # Close to ensure data is written to disk

    if verbose:
        print(f"Temporary credentials file created at: {tmp_file.name}")
    return tmp_file.name


if __name__ == "__main__":
    # Usage example:
    # Replace with your actual Nord Service Credentials from your dashboard
    svc_user = "your_service_username"
    svc_pass = "your_service_password"

    pass_file_path = create_nord_pass_file(svc_user, svc_pass)

    if pass_file_path:
        print(
            f"You can now run: openvpn --config YOUR_CONFIG.ovpn --auth-user-pass {pass_file_path}"
        )

        # Optional: Manually delete when done, or let it persist until your script exits
        # os.remove(pass_file_path)
