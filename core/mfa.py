from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .config import MODEL_ROOT, PROJECT_ROOT, RUNTIME_ROOT
from .models import PhoneInterval
from .phonology import normalize_phone, phone_base, phone_to_ipa


class MfaUnavailableError(RuntimeError):
    pass


class ForcedAlignmentError(RuntimeError):
    pass


ProgressCallback = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class MfaRuntime:
    executable: Path
    model_root: Path
    conda_executable: Path | None = None
    conda_prefix: Path | None = None


def find_mfa_runtime() -> MfaRuntime:
    explicit = os.environ.get("SYLLABLE_PLAYER_MFA")
    candidates = [
        Path(explicit) if explicit else None,
        RUNTIME_ROOT / "mfa" / "Scripts" / "mfa.exe",
        RUNTIME_ROOT / "mfa" / "bin" / "mfa",
    ]
    located = shutil.which("mfa")
    if located:
        candidates.append(Path(located))
    for candidate in candidates:
        if candidate and candidate.is_file():
            configured_root = os.environ.get("SYLLABLE_PLAYER_MFA_ROOT")
            model_root = Path(configured_root) if configured_root else MODEL_ROOT
            resolved = candidate.resolve()
            local_prefix = (RUNTIME_ROOT / "mfa").resolve()
            conda = (RUNTIME_ROOT / "miniforge" / "_conda.exe").resolve()
            if local_prefix in resolved.parents and conda.is_file():
                return MfaRuntime(resolved, model_root.resolve(), conda, local_prefix)
            return MfaRuntime(resolved, model_root.resolve())
    raise MfaUnavailableError(
        "尚未安装项目专用的 MFA 对齐器。请先运行 setup.ps1；完整单词仍可合成，"
        "但程序不会伪造分段时间。"
    )


class MfaBackend:
    def __init__(self, runtime: MfaRuntime | None = None) -> None:
        self.runtime = runtime or find_mfa_runtime()

    def _run(self, arguments: list[str], *, timeout: int = 240) -> str:
        env = os.environ.copy()
        env["MFA_ROOT_DIR"] = str(self.runtime.model_root)
        env["PYTHONUTF8"] = "1"
        command = [str(self.runtime.executable), *arguments]
        if self.runtime.conda_executable and self.runtime.conda_prefix:
            command = [
                str(self.runtime.conda_executable), "run", "--prefix",
                str(self.runtime.conda_prefix), "--no-capture-output", "mfa", *arguments,
            ]
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        if completed.returncode:
            last_lines = "\n".join(output.splitlines()[-12:])
            raise ForcedAlignmentError(f"MFA 执行失败：\n{last_lines}")
        return output

    def g2p(self, word: str, workspace: Path, model: str = "english_us_arpa") -> list[tuple[str, ...]]:
        workspace.mkdir(parents=True, exist_ok=True)
        wordlist = workspace / "oov_words.txt"
        output = workspace / "oov_pronunciations.txt"
        wordlist.write_text(word + "\n", encoding="utf-8")
        self._run([
            "g2p", str(wordlist), model, str(output),
            "--num_pronunciations", "3", "--clean", "--quiet",
            "--temporary_directory", str(workspace / "g2p_temp"),
        ])
        if not output.exists():
            raise ForcedAlignmentError("MFA G2P 没有产生发音结果。")
        pronunciations: list[tuple[str, ...]] = []
        for line in output.read_text(encoding="utf-8").splitlines():
            fields = re.split(r"\s+", line.strip())
            if len(fields) < 2 or fields[0].lower() != word.lower():
                continue
            candidate = tuple(normalize_phone(p) for p in fields[1:] if p)
            if candidate and candidate not in pronunciations:
                pronunciations.append(candidate)
        if not pronunciations:
            raise ForcedAlignmentError(f"MFA G2P 无法为 {word!r} 生成可信发音。")
        return pronunciations

    def align_word(
        self,
        wav_path: Path,
        word: str,
        candidates: Sequence[Sequence[str]],
        workspace: Path,
        acoustic_model: str = "english_us_arpa",
        progress: ProgressCallback | None = None,
    ) -> tuple[list[PhoneInterval], tuple[str, ...]]:
        if not candidates:
            raise ForcedAlignmentError("没有可用于声学对齐的候选发音。")
        workspace.mkdir(parents=True, exist_ok=True)
        transcript = workspace / f"{word}.lab"
        dictionary = workspace / "word.dict"
        textgrid_path = workspace / f"{word}.TextGrid"
        transcript.write_text(word + "\n", encoding="utf-8")
        lines = [word + "\t" + " ".join(normalize_phone(p) for p in candidate) for candidate in candidates]
        dictionary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if progress:
            progress("正在把音素精确对齐到完整录音……")
        self._run([
            "align_one", str(wav_path), str(transcript), str(dictionary),
            acoustic_model, str(textgrid_path), "--clean", "--quiet",
            "--temporary_directory", str(workspace / "align_temp"),
        ])
        if not textgrid_path.exists():
            alternatives = list(workspace.glob("*.TextGrid"))
            if alternatives:
                textgrid_path = alternatives[0]
            else:
                raise ForcedAlignmentError("MFA 没有生成 TextGrid 时间标注。")
        raw_intervals = _read_phone_tier(textgrid_path)
        return _validate_and_label_intervals(raw_intervals, candidates)


def _read_phone_tier(path: Path) -> list[tuple[float, float, str]]:
    try:
        from praatio import textgrid
    except ImportError as exc:  # pragma: no cover - setup catches this
        raise MfaUnavailableError("缺少 praatio，无法读取 MFA 时间标注。") from exc
    grid = textgrid.openTextgrid(str(path), includeEmptyIntervals=True)
    names = list(grid.tierNames)
    phone_names = [name for name in names if "phone" in name.lower()]
    if not phone_names:
        raise ForcedAlignmentError(f"TextGrid 中没有 phone 层（实际层：{', '.join(names)}）。")
    tier = grid.getTier(phone_names[0])
    result: list[tuple[float, float, str]] = []
    for entry in tier.entries:
        try:
            start, end, label_value = entry.start, entry.end, entry.label
        except AttributeError:
            start, end, label_value = entry[0], entry[1], entry[2]
        start = float(start)
        end = float(end)
        label = str(label_value).strip()
        if not label or label.lower() in {"sil", "sp", "spn", "<eps>"}:
            continue
        result.append((start * 1000.0, end * 1000.0, normalize_phone(label)))
    if not result:
        raise ForcedAlignmentError("MFA 时间标注中没有可用音素。")
    return result


def _validate_and_label_intervals(
    intervals: Sequence[tuple[float, float, str]],
    candidates: Sequence[Sequence[str]],
) -> tuple[list[PhoneInterval], tuple[str, ...]]:
    observed = tuple(phone_base(label) for _, _, label in intervals)
    selected: tuple[str, ...] | None = None
    for candidate in candidates:
        normalized = tuple(normalize_phone(p) for p in candidate)
        if tuple(phone_base(p) for p in normalized) == observed:
            selected = normalized
            break
    if selected is None:
        heard = " ".join(observed)
        expected = " | ".join(" ".join(phone_base(p) for p in x) for x in candidates)
        raise ForcedAlignmentError(
            f"实际音频的音素序列与候选发音不一致（音频：{heard}；词典：{expected}）。"
        )
    result: list[PhoneInterval] = []
    previous_end = -1.0
    for (start, end, _), phone in zip(intervals, selected):
        if start < previous_end - 0.5 or end <= start or end - start < 8.0:
            raise ForcedAlignmentError("音素时间戳不连续或持续时间异常，已拒绝切片。")
        result.append(PhoneInterval(phone, phone_to_ipa(phone), start, end))
        previous_end = end
    return result, selected
