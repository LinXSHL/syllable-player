# 音节拆分跟读 · Syllable Player

输入任意英文单词，自动完成：**拼写分段 + IPA 音标分段 + 音频时间轴三方对齐**，
播放发音时逐段同步高亮（当前音标红底、当前拼写浅底），并展示词性、中英文释义、
配图、英文例句（逐词高亮播放）与中文翻译。

示例：`everyone` → eve｜ry｜one ↔ /'ev/｜/ri/｜/wʌn/

## 运行

**双击 `run.bat`**（推荐），或命令行：

```powershell
cd syllable_player
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

> 请务必在自己的桌面会话中启动程序（双击 run.bat），音频输出才可靠。
> 首次查询新单词需联网（约 5-20 秒，界面顶部会显示"正在加载"状态与失败原因）；
> 查过的词缓存到 `data/cache/`，之后离线秒开。

如已有可用的 Python 环境，也可以直接安装依赖：

```bash
pip install -r requirements.txt
```

## 架构

```
main.py                     入口
core/
  phonology.py              音节学引擎：pyphen 拼写切分 + CMUdict 音素切分(maximal onset)
                            + ARPAbet→IPA 映射 + 段数对齐校验（回退链）
  tts.py                    edge-tts 合成音频，boundary="WordBoundary" 采集时间戳
  timing.py                 整词时间窗按音素权重（元音×1.35）切分为音节时间轴
  dictionary.py             Free Dictionary API（免密钥）+ deep-translator 中文翻译
                            （Google→MyMemory 双引擎兜底），内置例句库
  images.py                 配图：Openverse → LoremFlickr → Picsum 三级回退
  cache.py / favorites.py   本地 JSON 缓存（二次查询全离线）与收藏
  pipeline.py               流水线：并行拉取各模块，合并为统一 WordData
ui/
  main_window.py            主窗口；QMediaPlayer.positionChanged → 二分查找当前段 → 高亮
  widgets.py                SegmentRow（音节对）、WordHighlightLabel（例句逐词）
data/
  overrides.json            拼写切分人工修正表（key 为单词，value 为分段数组）
  examples_bank.json        常用词内置例句
  cache/                    每词一份 JSON + mp3 + jpg
```

## 核心设计：三方对齐

`segments[i]` 是同一下标三元组：`spell`（拼写）/ `ipa`（音标）/ `[start_ms, end_ms]`（音频时间）。

1. **音素分段为基准**：CMUdict 音素按 maximal onset 原则切音节（EH1 V｜R IY0｜W AH2 N），
   再逐音素映射为 IPA（'ev｜ri｜wʌn，主重音加 `'`）。
2. **拼写分段对齐**：pyphen 断词结果必须与音素段数一致，否则按回退链处理：
   `overrides.json` → 元音字母组规则 → 等长切分（标注"近似切分"）。
3. **时间轴生成**：edge-tts 只给整词时间窗，按各音节音素权重（元音 1.35 / 辅音 1.0）
   比例切分。如需音素级精度，可接入 aeneas 强制对齐替换 `timing.py`。

## 同步高亮

`QMediaPlayer.positionChanged(ms)` → 对 `segments` 起始时间二分查找当前下标 →
当前音标 QLabel 设红底白字、当前拼写 QLabel 设浅橙底，下标不变不重复刷样式；
`StoppedState` 或超过末段结束时间时全部复位。点击任一音节可单段试听。
例句播放复用同一逻辑（segments 换成 WordBoundary 词数组）。

## 免密钥说明

全部在线服务无需 API key：edge-tts（微软语音）、api.dictionaryapi.dev（词典）、
deep-translator（翻译）、LoremFlickr/Picsum（配图）。首次查询需联网，
之后数据与音频全部缓存在 `data/cache/`，离线可用。

## 常见问题

- **切分不准**：编辑 `data/overrides.json`，如 `"everyone": ["eve", "ry", "one"]`。
- **词典未收录的词**：会提示 OOV；可在 `data/overrides.json` 预置分段后仍需 CMUdict 收录才能出音标。
- **网络抖动**：词典请求自带 3 次重试；配图三级回退保证不空窗。
