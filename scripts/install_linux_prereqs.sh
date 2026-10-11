#!/bin/bash
set -e  # Exit on error

# Quality checks need the runtime/toolchain, but do not publish an AppImage.
SKIP_APPIMAGE=false
if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--skip-appimage" ]; }; then
    echo "Usage: $0 [--skip-appimage]" >&2
    exit 2
fi
if [ "$#" -eq 1 ]; then
    SKIP_APPIMAGE=true
fi

# Function to print status messages
print_status() {
    echo "==> $1"
}

# Install system dependencies
print_status "Updating package lists"
sudo env DEBIAN_FRONTEND=noninteractive apt-get update

print_status "Installing system dependencies"
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git \
    python3 \
    python3-dev \
    python3-pip \
    build-essential \
    squashfs-tools \
    gettext \
    autoconf \
    automake \
    libtool \
    pkg-config \
    mtdev-tools \
    libhidapi-hidraw0


if [ "$SKIP_APPIMAGE" = true ]; then
    print_status "Linux development dependencies installed; AppImage tooling skipped"
    exit 0
fi

print_status "Installing linuxdeploy (AppImage)"
ARCH=$(uname -m)
LINUXDEPLOY_URL="https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-${ARCH}.AppImage"
LINUXDEPLOY_BIN="linuxdeploy"
echo "Detected architecture: $ARCH. Attempting to download linuxdeploy-${ARCH}.AppImage."
TMP_LINUXDEPLOY="/tmp/${LINUXDEPLOY_BIN}.AppImage"
if ! curl --fail --location --connect-timeout 10 --max-time 120 --retry 2 "$LINUXDEPLOY_URL" -o "$TMP_LINUXDEPLOY"; then
    echo "Warning: Failed to download $LINUXDEPLOY_URL. This architecture may not be supported by linuxdeploy."
    exit 1
fi
chmod +x "$TMP_LINUXDEPLOY"
if [ "$(id -u)" -eq 0 ]; then
    mv "$TMP_LINUXDEPLOY" "/usr/local/bin/$LINUXDEPLOY_BIN"
else
    mkdir -p "$HOME/.local/bin"
    mv "$TMP_LINUXDEPLOY" "$HOME/.local/bin/$LINUXDEPLOY_BIN"
fi

print_status "Linux development dependencies installed successfully"
