#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "== Conversation Audio Analyzer setup =="

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python3 が見つかりません。Python 3.11 を先にインストールしてください。"
  read -n 1 -s -r -p "何かキーを押すと閉じます..."
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "ffmpegをインストールします..."
    brew install ffmpeg
  else
    echo "ffmpeg がありません。Homebrewを入れた後 brew install ffmpeg を実行してください。"
    read -n 1 -s -r -p "何かキーを押すと閉じます..."
    exit 1
  fi
fi

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "セットアップ完了。run_mac.command を実行してください。"
read -n 1 -s -r -p "何かキーを押すと閉じます..."
