from __future__ import annotations

import json
import os
import tempfile
import shutil
from pathlib import Path

import pandas as pd
import streamlit as st

from analyzer import AnalysisConfig, analyze_audio, build_analysis_pack, format_seconds

st.set_page_config(page_title="Conversation Audio Analyzer", layout="wide")
st.title("Conversation Audio Analyzer v1")
st.caption(
    "会話音声を、発話内容だけでなく話者・間・被せ・応答潜時・話速・音量・F0まで時間軸で解析します。"
)

with st.sidebar:
    st.header("解析設定")
    whisper_model = st.selectbox("Whisperモデル", ["large-v3", "medium", "small"], index=0)
    language = st.selectbox("言語", ["ja", "auto"], index=0)
    expected_speakers = st.number_input("想定話者数", min_value=1, max_value=8, value=2, step=1)
    hf_token = st.text_input(
        "Hugging Face token（話者分離用）",
        value=os.environ.get("HF_TOKEN", ""),
        type="password",
    )
    fast_response_ms = st.slider("高速応答しきい値 (ms)", 100, 1000, 500, 50)
    st.caption("短い応答潜時＝先読み、と断定はしません。観察候補として抽出します。")

uploaded = st.file_uploader(
    "WAV / MP3 / M4A / MP4 を選択",
    type=["wav", "mp3", "m4a", "mp4", "mov", "aac", "flac"],
)

if uploaded is None:
    st.info("音声または動画ファイルを選んでください。")
    st.stop()

st.audio(uploaded)

if st.button("解析開始", type="primary"):
    tmp_dir = Path(tempfile.mkdtemp(prefix="conv_audio_"))
    input_path = tmp_dir / uploaded.name
    cfg = AnalysisConfig(
        whisper_model=whisper_model,
        language=None if language == "auto" else language,
        expected_speakers=int(expected_speakers),
        hf_token=hf_token.strip() or None,
        fast_response_sec=fast_response_ms / 1000.0,
    )
    with st.status("解析中…", expanded=True) as status:
        try:
            input_path.write_bytes(uploaded.getbuffer())
            def progress(msg: str):
                st.write(msg)
            result = analyze_audio(input_path, cfg, progress=progress)
            st.session_state["analysis_result"] = result
            status.update(label="解析完了", state="complete")
        except Exception as e:
            status.update(label="解析に失敗", state="error")
            st.exception(e)
        finally:
            # 選択した音声の作業用コピーを解析終了後すぐ削除
            shutil.rmtree(tmp_dir, ignore_errors=True)

result = st.session_state.get("analysis_result")
if not result:
    st.stop()

st.divider()
st.header("概要")
s = result["summary"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("録音時間", format_seconds(s["duration_sec"]))
c2.metric("発話ターン", s["turn_count"])
c3.metric("無音時間", format_seconds(s["silence_sec"]))
c4.metric("被せ候補", s["overlap_count"])

if s.get("diarization_enabled"):
    st.success("話者分離あり")
else:
    st.warning("話者分離なし。HF tokenを設定すると『誰が話したか』『被せ』の精度が上がります。")

speaker_df = pd.DataFrame(result["speaker_metrics"])
st.subheader("話者別指標")
if not speaker_df.empty:
    st.dataframe(speaker_df, use_container_width=True, hide_index=True)

turn_df = pd.DataFrame(result["turns"])
st.subheader("会話タイムライン")
if not turn_df.empty:
    cols = [
        "start_fmt", "end_fmt", "speaker", "duration", "response_latency_sec",
        "overlaps_previous_sec", "fast_response", "text"
    ]
    cols = [c for c in cols if c in turn_df.columns]
    st.dataframe(turn_df[cols], use_container_width=True, hide_index=True)

st.subheader("観察ポイント")
for item in result.get("observations", []):
    st.write("• " + item)

st.caption(
    "このソフトは、声の高さや被せだけから感情・性格・診断を推定しません。"
    "測定値で気になる箇所を絞り、発言内容と原音を合わせて解釈するためのツールです。"
)

st.divider()
st.header("話者名を対応させる")
mapping = {}
for spk in sorted(speaker_df["speaker"].tolist()) if not speaker_df.empty else []:
    mapping[spk] = st.text_input(f"{spk} の表示名", value=spk, key=f"map_{spk}")

pack = build_analysis_pack(result, mapping)
st.download_button(
    "ChatGPT分析パック (TXT) を保存",
    data=pack.encode("utf-8"),
    file_name="conversation_analysis_pack.txt",
    mime="text/plain",
)
st.download_button(
    "解析結果 (JSON) を保存",
    data=json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"),
    file_name="conversation_analysis.json",
    mime="application/json",
)
