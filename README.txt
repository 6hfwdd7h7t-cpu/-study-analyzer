Study Analyzer Web Ver.2.3 更新ファイル

修正:
- TXT一括読込でUTF-8 / Shift_JIS(CP932系) / UTF-16 BOMを自動判定
- Shift_JISの日本語TXTをUTF-8固定で読んだ際の文字化けを防止
- JSONバックアップ自体の形式は変更なし

注意:
すでに「�」等に文字化けして保存された問題は元の文字情報が失われているため、自動復元はできません。元TXTから再読み込みしてください。

GitHubで置き換えるファイル:
1. index.html
2. sw.js
