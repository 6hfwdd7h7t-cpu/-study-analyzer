from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import librosa
import numpy as np


@dataclass
class AnalysisConfig:
    whisper_model: str = "large-v3"
    language: Optional[str] = "ja"
    expected_speakers: int = 2
    hf_token: Optional[str] = None
    fast_response_sec: float = 0.5


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr[-4000:]}")


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg が見つかりません。README_JA.md の手順でインストールしてください。")


def convert_to_wav(input_path: Path, out_dir: Path) -> Path:
    require_ffmpeg()
    wav = out_dir / "analysis_16k_mono.wav"
    _run([
        "ffmpeg", "-y", "-i", str(input_path), "-vn",
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)
    ])
    return wav


def probe_duration(path: Path) -> float:
    p = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(p.stdout.strip())
    except Exception:
        y, sr = librosa.load(str(path), sr=None, mono=True)
        return len(y) / sr


def transcribe(wav_path: Path, cfg: AnalysisConfig):
    from faster_whisper import WhisperModel

    model = WhisperModel(cfg.whisper_model, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(wav_path),
        language=cfg.language,
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=True,
    )
    out = []
    for s in segments:
        words = []
        for w in (s.words or []):
            words.append({
                "start": float(w.start),
                "end": float(w.end),
                "word": w.word,
                "probability": float(getattr(w, "probability", 0.0) or 0.0),
            })
        out.append({
            "start": float(s.start),
            "end": float(s.end),
            "text": s.text.strip(),
            "words": words,
        })
    return out, {
        "language": getattr(info, "language", None),
        "language_probability": float(getattr(info, "language_probability", 0.0) or 0.0),
    }


def diarize(wav_path: Path, cfg: AnalysisConfig):
    if not cfg.hf_token:
        return []

    from pyannote.audio import Pipeline

    # 現行communityモデルを優先し、環境差に備えて3.1へフォールバック。
    model_ids = [
        "pyannote/speaker-diarization-community-1",
        "pyannote/speaker-diarization-3.1",
    ]
    pipeline = None
    last_err = None
    for model_id in model_ids:
        try:
            try:
                pipeline = Pipeline.from_pretrained(model_id, token=cfg.hf_token)
            except TypeError:
                pipeline = Pipeline.from_pretrained(model_id, use_auth_token=cfg.hf_token)
            if pipeline is not None:
                break
        except Exception as e:
            last_err = e

    if pipeline is None:
        raise RuntimeError(
            "話者分離モデルを読み込めません。HF tokenとモデル利用条件を確認してください。\n"
            f"最後のエラー: {last_err}"
        )

    output = pipeline(str(wav_path), num_speakers=cfg.expected_speakers)
    annotation = getattr(output, "speaker_diarization", output)

    diar = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        diar.append({"start": float(turn.start), "end": float(turn.end), "speaker": str(speaker)})
    diar.sort(key=lambda x: (x["start"], x["end"]))
    return diar


def overlap(a0, a1, b0, b1) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def assign_speakers(transcript_segments, diar_segments):
    if not diar_segments:
        return [{**s, "speaker": "SPEAKER_UNKNOWN"} for s in transcript_segments]

    assigned = []
    for s in transcript_segments:
        scores = {}
        for d in diar_segments:
            ov = overlap(s["start"], s["end"], d["start"], d["end"])
            if ov > 0:
                scores[d["speaker"]] = scores.get(d["speaker"], 0.0) + ov
        speaker = max(scores, key=scores.get) if scores else "SPEAKER_UNKNOWN"
        assigned.append({**s, "speaker": speaker})
    return assigned


def merge_turns(segments, max_gap=0.8):
    turns = []
    for s in sorted(segments, key=lambda x: x["start"]):
        if not turns:
            turns.append({
                "start": s["start"], "end": s["end"], "speaker": s["speaker"],
                "text": s["text"], "words": list(s.get("words", []))
            })
            continue
        p = turns[-1]
        if s["speaker"] == p["speaker"] and s["start"] - p["end"] <= max_gap:
            p["end"] = max(p["end"], s["end"])
            p["text"] = (p["text"] + " " + s["text"]).strip()
            p["words"].extend(s.get("words", []))
        else:
            turns.append({
                "start": s["start"], "end": s["end"], "speaker": s["speaker"],
                "text": s["text"], "words": list(s.get("words", []))
            })
    return turns


def diarization_overlap_stats(diar_segments):
    count, total, events = 0, 0.0, []
    for i, a in enumerate(diar_segments):
        for b in diar_segments[i + 1:]:
            if b["start"] >= a["end"]:
                break
            if a["speaker"] == b["speaker"]:
                continue
            ov = overlap(a["start"], a["end"], b["start"], b["end"])
            if ov > 0:
                count += 1
                total += ov
                events.append({
                    "start": max(a["start"], b["start"]),
                    "end": min(a["end"], b["end"]),
                    "speaker_a": a["speaker"],
                    "speaker_b": b["speaker"],
                    "duration": ov,
                })
    return count, total, events


def compute_acoustics(wav_path: Path, diar_segments):
    y, sr = librosa.load(str(wav_path), sr=16000, mono=True)
    eps = 1e-9

    def feature(start, end):
        a, b = max(0, int(start * sr)), min(len(y), int(end * sr))
        yy = y[a:b]
        if len(yy) < int(0.15 * sr):
            return {"rms_db": None, "f0_hz": None}
        rms = float(np.sqrt(np.mean(np.square(yy)) + eps))
        rms_db = 20 * math.log10(rms + eps)
        f0_val = None
        try:
            f0, _, _ = librosa.pyin(yy, fmin=70, fmax=400, sr=sr, frame_length=1024, hop_length=256)
            good = f0[np.isfinite(f0)]
            if len(good):
                f0_val = float(np.median(good))
        except Exception:
            pass
        return {"rms_db": rms_db, "f0_hz": f0_val}

    source = diar_segments or [{"start": 0, "end": len(y) / sr, "speaker": "SPEAKER_UNKNOWN"}]
    out = []
    for d in source:
        if d["end"] - d["start"] < 0.15:
            continue
        out.append({**d, **feature(d["start"], d["end"])})
    return out


def nonspace_chars(text: str) -> int:
    return len("".join(text.split()))


def format_seconds(sec):
    sec = float(sec or 0)
    m, s = divmod(int(round(sec)), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def add_turn_context(turns, fast_response_sec):
    for i, t in enumerate(turns):
        t["duration"] = round(max(0.0, t["end"] - t["start"]), 3)
        t["response_latency_sec"] = None
        t["overlaps_previous_sec"] = 0.0
        t["fast_response"] = False
        if i > 0 and t["speaker"] != turns[i - 1]["speaker"]:
            latency = t["start"] - turns[i - 1]["end"]
            t["response_latency_sec"] = round(latency, 3)
            if latency < 0:
                t["overlaps_previous_sec"] = round(-latency, 3)
            t["fast_response"] = latency <= fast_response_sec
        t["start_fmt"] = format_seconds(t["start"])
        t["end_fmt"] = format_seconds(t["end"])
    return turns


def union_duration(intervals):
    xs = sorted((float(a), float(b)) for a, b in intervals if b > a)
    if not xs:
        return 0.0
    total = 0.0
    ca, cb = xs[0]
    for a, b in xs[1:]:
        if a <= cb:
            cb = max(cb, b)
        else:
            total += cb - ca
            ca, cb = a, b
    return total + (cb - ca)


def build_metrics(duration, turns, acoustic_segments, fast_response_sec):
    metrics = []
    for spk in sorted(set(t["speaker"] for t in turns)):
        ts = [t for t in turns if t["speaker"] == spk]
        speech = sum(t["duration"] for t in ts)
        latencies = [t["response_latency_sec"] for t in ts if t["response_latency_sec"] is not None]
        fast = [x for x in latencies if x <= fast_response_sec]
        chars = sum(nonspace_chars(t["text"]) for t in ts)
        cpm = chars / (speech / 60) if speech > 0 else None
        ac = [a for a in acoustic_segments if a["speaker"] == spk]
        f0s = [a["f0_hz"] for a in ac if a.get("f0_hz") is not None]
        rms = [a["rms_db"] for a in ac if a.get("rms_db") is not None]
        metrics.append({
            "speaker": spk,
            "speech_sec": round(speech, 2),
            "speech_share_pct": round(100 * speech / duration, 1) if duration else None,
            "turns": len(ts),
            "mean_turn_sec": round(float(np.mean([t["duration"] for t in ts])), 2) if ts else None,
            "median_response_sec": round(float(np.median(latencies)), 3) if latencies else None,
            "fast_response_rate_pct": round(100 * len(fast) / len(latencies), 1) if latencies else None,
            "interruptions_started": sum(1 for t in ts if t.get("overlaps_previous_sec", 0) > 0),
            "chars_per_min": round(cpm, 1) if cpm else None,
            "median_f0_hz": round(float(np.median(f0s)), 1) if f0s else None,
            "median_rms_db": round(float(np.median(rms)), 1) if rms else None,
        })
    return metrics


def generate_observations(metrics, overlap_count, fast_response_sec):
    obs = []
    if len(metrics) >= 2:
        ordered = sorted(metrics, key=lambda x: x.get("speech_sec", 0), reverse=True)
        obs.append(
            f"発話量最多は {ordered[0]['speaker']}（{ordered[0]['speech_sec']}秒）。"
            f"次が {ordered[1]['speaker']}（{ordered[1]['speech_sec']}秒）。"
        )
    for m in metrics:
        if m.get("fast_response_rate_pct") is not None:
            obs.append(
                f"{m['speaker']}：相手への応答ターンの {m['fast_response_rate_pct']}% が "
                f"{fast_response_sec:.2f}秒以内に開始。"
            )
        if m.get("interruptions_started"):
            obs.append(f"{m['speaker']}：前話者と重なって開始したターン {m['interruptions_started']}回。")
    if overlap_count:
        obs.append(f"話者分離上の重なり区間 {overlap_count}件。原音確認候補。")
    return obs


def analyze_audio(input_path: Path, cfg: AnalysisConfig, progress: Callable[[str], None] = print):
    # 解析用WAVは一時ディレクトリにだけ置き、解析終了時に確実に削除する
    with tempfile.TemporaryDirectory(prefix="conversation_audio_analysis_") as work_dir:
        work = Path(work_dir)

        progress("1/6 解析用WAVへ変換")
        wav = convert_to_wav(Path(input_path), work)
        duration = probe_duration(wav)

        progress("2/6 ローカルWhisperで文字起こし＋単語時刻")
        transcript, lang_info = transcribe(wav, cfg)

        progress("3/6 話者分離")
        diar = diarize(wav, cfg)
        if not diar:
            progress("  HF token未設定のため話者分離はスキップ")

        progress("4/6 発言と話者を統合")
        assigned = assign_speakers(transcript, diar)
        turns = add_turn_context(merge_turns(assigned), cfg.fast_response_sec)

        progress("5/6 音量・F0を計算")
        acoustics = compute_acoustics(wav, diar)

        progress("6/6 会話指標を集計")
        ov_count, ov_sec, ov_events = diarization_overlap_stats(diar)
        metrics = build_metrics(duration, turns, acoustics, cfg.fast_response_sec)
        speech_union = union_duration([(t["start"], t["end"]) for t in turns])
        silence = max(0.0, duration - speech_union)

        return {
            "meta": {
                "source_name": Path(input_path).name,
                "language": lang_info,
                "whisper_model": cfg.whisper_model,
                "expected_speakers": cfg.expected_speakers,
                "fast_response_sec": cfg.fast_response_sec,
            },
            "summary": {
                "duration_sec": round(duration, 2),
                "turn_count": len(turns),
                "silence_sec": round(silence, 2),
                "overlap_count": ov_count,
                "overlap_sec": round(ov_sec, 2),
                "diarization_enabled": bool(diar),
            },
            "speaker_metrics": metrics,
            "turns": turns,
            "diarization_segments": diar,
            "overlap_events": ov_events,
            "acoustic_segments": acoustics,
            "observations": generate_observations(metrics, ov_count, cfg.fast_response_sec),
        }


def build_analysis_pack(result, speaker_name_map=None):
    speaker_name_map = speaker_name_map or {}
    def spk(name):
        return speaker_name_map.get(name, name)

    lines = [
        "# Conversation Audio Analyzer — ChatGPT analysis pack",
        "",
        "## 解析前提",
        "- 数値は観察指標。感情・性格・診断を直接示すものではない。",
        "- 短い応答潜時や被せは『先読み』候補だが、それ単独では断定しない。",
        "",
        "## 概要",
    ]
    for k, v in result["summary"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 話者別指標"]
    for m in result["speaker_metrics"]:
        mm = dict(m)
        mm["speaker"] = spk(mm["speaker"])
        lines.append("- " + json.dumps(mm, ensure_ascii=False))
    lines += ["", "## 会話タイムライン"]
    for t in result["turns"]:
        meta = []
        if t.get("response_latency_sec") is not None:
            meta.append(f"応答潜時={t['response_latency_sec']:.3f}s")
        if t.get("overlaps_previous_sec", 0):
            meta.append(f"重なり={t['overlaps_previous_sec']:.3f}s")
        suffix = f" [{' / '.join(meta)}]" if meta else ""
        lines.append(
            f"{format_seconds(t['start'])}-{format_seconds(t['end'])} "
            f"{spk(t['speaker'])}{suffix}: {t['text']}"
        )
    lines += [
        "",
        "## ChatGPTへの分析依頼",
        "事実として測定されたこと／会話機能としての解釈／心理的意味の仮説を分けて分析する。",
        "特に、応答潜時、被せ、相手に発話余地を残す場面、質問、主導権、仮説提示→相手の修正の循環、先読みしすぎの可能性を見る。",
        "短い潜時や声の特徴だけから心理を断定しない。",
    ]
    return "\n".join(lines)
