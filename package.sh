#!/bin/bash
# Package cbc-radio-cli for distribution

set -e

VERSION=${1:-"v0.1.0"}
PLATFORMS=("linux-amd64" "linux-arm64" "darwin-amd64" "darwin-arm64")

echo "Packaging cbc-radio-cli $VERSION"

mkdir -p dist

for platform in "${PLATFORMS[@]}"; do
    echo "Building for $platform..."
    
    platform_dir="dist/cbc-radio-cli-$platform"
    mkdir -p "$platform_dir"
    
    # Copy files
    cp cbc_ideas_audio_dl.py "$platform_dir/"
    cp cbc_radio_web.py "$platform_dir/"
    cp requirements*.txt "$platform_dir/"
    cp README.md "$platform_dir/" 2>/dev/null || true
    cp LICENSE "$platform_dir/" 2>/dev/null || true
    [ -d "web" ] && cp -r web "$platform_dir/" || true
    [ -d "scripts" ] && cp -r scripts "$platform_dir/" || true
    
    # Create install script
    cat > "$platform_dir/install.sh" << 'EOF'
#!/bin/bash
set -e

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
mkdir -p "$INSTALL_DIR"

if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required"
    exit 1
fi

pip3 install -r requirements.txt --user

cp cbc_ideas_audio_dl.py "$INSTALL_DIR/cbc-radio-cli"
chmod +x "$INSTALL_DIR/cbc-radio-cli"

echo "✓ Installed to $INSTALL_DIR/cbc-radio-cli"
echo ""
echo "Make sure $INSTALL_DIR is in your PATH:"
echo "  export PATH=\"\$PATH:$INSTALL_DIR\""
EOF
    chmod +x "$platform_dir/install.sh"
    
    cd dist
    tar -czf "cbc-radio-cli-$VERSION-$platform.tar.gz" "cbc-radio-cli-$platform"
    rm -rf "cbc-radio-cli-$platform"
    cd ..
    
    echo "✓ Created cbc-radio-cli-$VERSION-$platform.tar.gz"
done

echo ""
echo "✓ All packages created in dist/"
