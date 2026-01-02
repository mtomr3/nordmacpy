#!/bin/bash
#
# Simple script that outputs the exact visudo commands needed
# You can copy-paste these into visudo or add to /etc/sudoers.d/
#
# Usage: ./setup_sudo_permissions_simple.sh

set -euo pipefail

# Get current user
CURRENT_USER="${USER:-$(whoami)}"

# Find openvpn binary
OPENVPN_PATH=$(command -v openvpn 2>/dev/null || echo "/usr/local/bin/openvpn")

echo "=========================================="
echo "Sudo permissions needed for nordmacpy"
echo "User: $CURRENT_USER"
echo "OpenVPN path: $OPENVPN_PATH"
echo "=========================================="
echo ""
echo "Add these lines to /etc/sudoers.d/nordmacpy-$CURRENT_USER:"
echo "(or run: sudo ./setup_sudo_permissions.sh)"
echo ""
echo "---"
cat <<EOF
# Sudo permissions for nordmacpy VPN package
# User: $CURRENT_USER

# OpenVPN - allow all openvpn commands
$CURRENT_USER ALL=(ALL) NOPASSWD: $OPENVPN_PATH

# Route commands for cleanup
$CURRENT_USER ALL=(ALL) NOPASSWD: /sbin/route -n delete -inet 0.0.0.0/1
$CURRENT_USER ALL=(ALL) NOPASSWD: /sbin/route -n delete -inet 128.0.0.0/1

# DNS cache flush
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/dscacheutil -flushcache

# mDNSResponder restart
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/killall -HUP mDNSResponder

# OpenVPN process management
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/pkill -TERM openvpn
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/pkill -KILL openvpn
EOF
echo "---"
echo ""
echo "To apply manually:"
echo "  1. sudo visudo -f /etc/sudoers.d/nordmacpy-$CURRENT_USER"
echo "  2. Paste the above lines"
echo "  3. Save and exit"
echo ""
echo "Or run the automated script:"
echo "  sudo ./setup_sudo_permissions.sh"

