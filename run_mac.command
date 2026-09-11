#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo ".venv がありません。先に setup_mac.command を実行してください。"
  read -n 1 -s -r -p "何かキーを押すと閉じます..."
  exit 1
fi

source .venv/bin/activate
streamlit run app.py
