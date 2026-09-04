# 英文分段发音学习器（Syllable Player 2）

这不是“把完整单词放慢”的 TTS 播放器。程序只生成一次完整的美式英语单词录音，再把词典/G2P 给出的音素序列对齐到这段真实音频，从中切出自然发音组。

以 `everyone` 为例，默认分析结果是：

```text
eve  ↔ /ˈev/
ry   ↔ /ri/
one  ↔ /wʌn/
```

播放顺序是 `/ˈev/ → /ri/ → /wʌn/ → everyone`。前三段播放时，字母块和 IPA 块同步高亮；播放完整词时恢复中性显示。

## 安装与启动（Windows）

1. 在项目文件夹中右键 `setup.ps1`，选择“使用 PowerShell 运行”。
2. 等待桌面依赖、CPU 版 MFA 和三个 `english_us_arpa` 模型下载完成。首次安装时间较长，不会安装 CUDA/GPU 运行库。
3. 双击 `run.bat`。

若 PowerShell 阻止脚本，可在项目目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

只安装界面依赖、暂不下载 MFA：

```powershell
.\setup.ps1 -SkipMfa
```

这种模式只允许播放完整词。程序会明确提示缺少对齐器，不会按字符比例伪造分段时间。

## 核心数据流

```text
输入单词
  → CMUdict 候选发音（未登录词改用 MFA G2P）
  → Edge TTS 仅生成一次完整 en-US 单词录音
  → PyAV 解码为 16 kHz 单声道 PCM
  → MFA align_one 选择与录音一致的候选发音并输出音素时间戳
  → 元音核 + 最大声母原则形成 pronunciation chunks
  → 加权 grapheme↔phoneme 单调对齐
  → 在组边界附近寻找低能量/过零切点，加入 5 ms 淡入淡出
  → 独立 WAV 片段 + 教学时间线 + 完整词 WAV
  → QAudioSink 的真实播放时钟驱动字母/IPA 高亮
```

更详细的模块职责和旧方案取舍见 [docs/architecture.md](docs/architecture.md)。

## 质量边界

- 绝不逐个字母、连字符或按时长比例切音频。
- 绝不为每个分段单独调用 TTS。
- 音素序列、TextGrid 或拼写映射不能严格覆盖时，停止分段并显示原因。
- 同形异音词由完整录音与候选发音的声学对齐结果决定，不能匹配就拒绝猜测。
- 字典释义是附加信息；即使网络释义服务不可用，也不影响已缓存的核心发音学习功能。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

默认测试完全离线。真实 TTS + MFA 集成测试需要先安装模型，并显式设置 `RUN_LIVE_ALIGNMENT=1`。

## 隐私与缓存

语音合成会把用户输入的单个英文词发送给 Edge 在线语音服务。MFA 对齐、音频切片、收藏和缓存均在本机进行。`.runtime`、`.models`、`.venv` 和 `cache` 已被排除在版本控制之外。
