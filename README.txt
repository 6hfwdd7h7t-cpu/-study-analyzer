Study Analyzer Web Ver.2 更新ファイル

更新内容:
- 「1つ選べ / 2つ選べ」を問題ごとに選択
- 2つ選べ問題は2項目を選んで回答確定
- 問題画像を写真ライブラリ/ファイルから追加
- 画像は自動縮小してIndexedDBに端末保存
- JSONバックアップに画像も含める
- 旧Ver.1の問題・回答履歴は同じlocalStorageキーを使うためそのまま引き継ぐ
- noindex設定を正常なHTMLに修正
- Service Workerをv2に更新し、更新が反映されやすい方式に変更

GitHubで置き換えるファイル:
1. index.html
2. sw.js

manifest.webmanifest / icon.svg / robots.txt はそのままでOK。
