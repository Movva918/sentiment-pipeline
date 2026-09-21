#!/bin/bash
# Packages all ingestion Lambda functions for deployment
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$SCRIPT_DIR/../../src/ingestion"
BUILD_DIR="$SCRIPT_DIR/../../build"

echo "=== Cleaning build directory ==="
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/layer" "$BUILD_DIR/lambdas"

echo "=== Building Lambda layer (requests library) ==="
pip install requests -t "$BUILD_DIR/layer/python" --quiet
cd "$BUILD_DIR/layer"
zip -r "$BUILD_DIR/lambda_layer.zip" python/ -q
echo "Layer packaged: build/lambda_layer.zip"

echo "=== Packaging Lambda functions ==="
LAMBDAS=("finnhub_lambda" "sec_edgar_lambda" "rss_lambda" "alpha_vantage_lambda")

for name in "${LAMBDAS[@]}"; do
    echo "Packaging $name..."
    mkdir -p "$BUILD_DIR/lambdas/$name"
    cp "$SRC_DIR/$name.py" "$BUILD_DIR/lambdas/$name/lambda_function.py"
    cp "$SRC_DIR/utils.py" "$BUILD_DIR/lambdas/$name/utils.py"
    cd "$BUILD_DIR/lambdas/$name"
    zip -r "$BUILD_DIR/$name.zip" . -q
    echo "  -> build/$name.zip"
done

echo ""
echo "=== Build complete ==="
echo "Artifacts:"
ls -lh "$BUILD_DIR"/*.zip
