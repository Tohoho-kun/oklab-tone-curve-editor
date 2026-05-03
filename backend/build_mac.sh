#!/bin/bash

# 必要なライブラリのインストール (scipy を除外して軽量化)
pip install pyinstaller tifffile numpy fastapi uvicorn pydantic starlette pillow

echo "Building Lightweight Standalone App for Mac..."

# PyInstallerを実行
# --exclude-module scipy: 巨大な scipy を強制的に除外
# --noconsole: 黒い画面を出さない
# --onefile: 1つのファイルにまとめる
pyinstaller --noconsole --onefile \
    --name "OkhslToneCurve" \
    --add-data "../frontend:frontend" \
    --exclude-module scipy \
    --exclude-module matplotlib \
    --exclude-module pandas \
    --exclude-module IPython \
    launcher.py

echo "Build complete! Check the 'dist' folder."
echo "The file size should be significantly smaller now."
