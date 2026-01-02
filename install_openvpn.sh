#!/bin/bash
#
# Install OpenVPN on macOS
# Supports Homebrew (Intel and Apple Silicon) and MacPorts
#
# Usage: ./install_openvpn.sh

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}OpenVPN Installation Script for macOS${NC}"
echo "=========================================="
echo ""

# Check if openvpn is already installed
if command -v openvpn &> /dev/null; then
    OPENVPN_PATH=$(command -v openvpn)
    OPENVPN_VERSION=$(openvpn --version 2>/dev/null | head -n 1 || echo "unknown version")
    echo -e "${GREEN}✓ OpenVPN is already installed${NC}"
    echo -e "  Location: $OPENVPN_PATH"
    echo -e "  Version: $OPENVPN_VERSION"
    echo ""
    read -p "Reinstall anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}Installation skipped.${NC}"
        exit 0
    fi
fi

# Detect package manager
if command -v brew &> /dev/null; then
    PACKAGE_MANAGER="brew"
    echo -e "${GREEN}Detected: Homebrew${NC}"
elif command -v port &> /dev/null; then
    PACKAGE_MANAGER="port"
    echo -e "${GREEN}Detected: MacPorts${NC}"
else
    echo -e "${RED}Error: No package manager found!${NC}"
    echo ""
    echo "Please install one of the following:"
    echo "  - Homebrew: https://brew.sh"
    echo "  - MacPorts: https://www.macports.org"
    exit 1
fi

# Install OpenVPN
echo ""
echo -e "${BLUE}Installing OpenVPN...${NC}"

if [[ "$PACKAGE_MANAGER" == "brew" ]]; then
    # Check if we need sudo for brew (usually not needed)
    if brew list openvpn &> /dev/null; then
        echo -e "${YELLOW}OpenVPN is already installed via Homebrew. Upgrading...${NC}"
        brew upgrade openvpn
    else
        echo -e "${BLUE}Installing OpenVPN via Homebrew...${NC}"
        brew install openvpn
    fi
    
    # Verify installation
    OPENVPN_PATH=$(brew --prefix openvpn)/sbin/openvpn
    if [[ ! -f "$OPENVPN_PATH" ]]; then
        # Try bin instead of sbin
        OPENVPN_PATH=$(brew --prefix openvpn)/bin/openvpn
    fi
    
elif [[ "$PACKAGE_MANAGER" == "port" ]]; then
    echo -e "${BLUE}Installing OpenVPN via MacPorts...${NC}"
    echo -e "${YELLOW}Note: MacPorts may require sudo${NC}"
    
    if port installed openvpn &> /dev/null; then
        echo -e "${YELLOW}OpenVPN is already installed via MacPorts. Upgrading...${NC}"
        sudo port upgrade openvpn
    else
        sudo port install openvpn
    fi
    
    OPENVPN_PATH=$(port contents openvpn | grep -E '/openvpn$' | head -n 1 || echo "/opt/local/bin/openvpn")
fi

# Verify installation
echo ""
if command -v openvpn &> /dev/null; then
    OPENVPN_PATH=$(command -v openvpn)
    OPENVPN_VERSION=$(openvpn --version 2>/dev/null | head -n 1 || echo "unknown version")
    echo -e "${GREEN}✓ OpenVPN installed successfully!${NC}"
    echo -e "  Location: $OPENVPN_PATH"
    echo -e "  Version: $OPENVPN_VERSION"
    echo ""
    echo -e "${BLUE}Next steps:${NC}"
    echo "  1. Run: sudo ./setup_sudo_permissions.sh"
    echo "  2. Or manually configure sudo permissions"
else
    echo -e "${RED}✗ Installation completed but openvpn command not found in PATH${NC}"
    echo -e "${YELLOW}You may need to add OpenVPN to your PATH${NC}"
    if [[ "$PACKAGE_MANAGER" == "brew" ]]; then
        BREW_PREFIX=$(brew --prefix)
        echo -e "${YELLOW}Try adding to ~/.zshrc or ~/.bash_profile:${NC}"
        echo -e "  export PATH=\"\$PATH:$BREW_PREFIX/sbin\""
    fi
    exit 1
fi

