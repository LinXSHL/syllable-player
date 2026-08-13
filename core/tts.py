# -*- coding: utf-8 -*-
"""
TTS 模块：edge-tts 合成单词/例句音频，并采集 WordBoundary 时间戳。
所有函数均为同步封装（内部跑 asyncio），供 QThread worker 直接调用。
"""
import asyncio
import os

import edge_tts

DEFAULT_VOICE = "en-US-JennyNeural"
WORD_RATE = "-25%"      # 单词读慢一点，便于跟读与分段感知
SENT_RATE = "-5%"       # 例句接近自然语速


async def _synth(text, out_path, voice, rate):
    """合成 text -> out_path(mp3)，返回 [(word, start_ms, end_ms), ...]"""
    communicate = edge_tts.Communicate(text, voice, rate=rate,
                                       boundary="WordBoundary",
                                       connect_timeout=10, receive_timeout=20)
    boundaries = []
    sentence_window = None
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start_ms = chunk["offset"] / 10_000  # 100ns -> ms
                dur_ms = chunk["duration"] / 10_000
                boundaries.append((chunk["text"], start_ms, start_ms + dur_ms))
            elif chunk["type"] == "SentenceBoundary":
                start_ms = chunk["offset"] / 10_000
                dur_ms = chunk["duration"] / 10_000
                sentence_window = (chunk.get("text", text), start_ms,
                                   start_ms + dur_ms)
    # 单词合成时服务端可能只回 SentenceBoundary，用它兜底
    if not boundaries and sentence_window is not None:
        boundaries.append(sentence_window)
    return boundaries


def synth_word(word, out_path, voice=DEFAULT_VOICE):
    """合成单词读音，返回整词时间窗 (start_ms, end_ms)；失败抛异常"""
    bounds = asyncio.run(_synth(word, out_path, voice, WORD_RATE))
    if bounds:
        return bounds[0][1], bounds[0][2]
    # 极少数情况没有 WordBoundary：用音频总长兜底
    return 0.0, _audio_duration_ms(out_path)


def synth_sentence(sentence, out_path, voice=DEFAULT_VOICE):
    """合成例句，返回词级时间戳 [(word, start_ms, end_ms), ...]"""
    return asyncio.run(_synth(sentence, out_path, voice, SENT_RATE))


def _audio_duration_ms(path):
    try:
        import wave
        with wave.open(path, "rb") as wf:
            return wf.getnframes() / wf.getframerate() * 1000
    except Exception:
        return 1500.0


if __name__ == "__main__":
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "everyone.mp3")
    print(synth_word("everyone", tmp))
