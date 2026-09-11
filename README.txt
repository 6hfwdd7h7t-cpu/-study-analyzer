Study Analyzer Web Ver.2.9 + 会話分析

元: Web Ver.2.8

追加内容
- 下部ナビに「会話」を追加
- Conversation Audio Analyzerが出力したJSONを読み込み
- 会話分析JSONはIndexedDBに保存
- 会話ごとの録音時間・発話ターン・無音・被せを表示
- 話者名（例：鳥越 / 明見）を端末内で対応づけ可能
- 話者別に発話時間、発話割合、平均ターン、応答潜時、高速応答率、被せ開始、話速、F0を表示
- 全会話タイムラインを表示
- 「高速応答だけ」「被せ・重なりだけ」のフィルタ
- ChatGPTへ渡す分析パックTXTを書き出し
- 完全バックアップJSONに会話分析も含める
- 全データ初期化に会話分析も含める

重要
- このGitHub Pages版は音声ファイル自体を解析しません。
- 音声解析（Whisper / 話者分離 / F0等）はMac/PC側のConversation Audio Analyzerで実行し、
  そのJSONをこのWeb版へ読み込む構成です。
- 音声そのものはWeb版には保存しません。
- 短い応答潜時や被せだけで「先読み」と断定しません。原音・発言内容と組み合わせて確認してください。

GitHub Pages更新
1. index.html を上書き
2. sw.js を上書き
3. manifest.webmanifest を上書き
4. icon類は既存のままでも可（このZIPにも同梱）

Service Workerのキャッシュ名は study-analyzer-v2-9 に更新済みです。
