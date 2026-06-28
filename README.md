# story-harness

一個練習 harness 的小工具。

它用 Markdown 大綱當輸入，跑一個簡單的 writer/reviewer 迴圈，最後把生成結果寫到 `stories/`。這不是正式產品，也不是通用框架；主要是用來練習怎麼把 CLI、設定檔、prompt、agent provider、測試和輸出流程串起來。

## 快速開始

如果 Python、訂閱型 CLI 或 Ollama 都已經準備好，可以先照這組最短流程跑一次；失敗時再看後面的設定說明。

```bash
python3 scripts/generate_presets.py
python3 story_harness.py --list-presets
```

從 `--list-presets` 的輸出挑一個 writer 和 reviewer preset。接著把你自己準備好的標準大綱放到 `outlines/`，檔名自取，例如 `outlines/example.md`。

把選好的 preset 寫進 `config.json`：

```json
{
  "agents": {
    "writer": "你的 writer preset",
    "reviewer": "你的 reviewer preset"
  },
  "runtime": {
    "rounds": 3,
    "ollama_url": "http://localhost:11434",
    "num_ctx": 2048,
    "num_predict": 2500,
    "writer_temperature": 0.8,
    "reviewer_temperature": 0.3,
    "keep_alive": "0s"
  }
}
```

有大綱後直接執行：

```bash
python3 story_harness.py
```

輸出會在：

```text
stories/YYYYMMDD-故事標題/book.md
```

## 基本限制

- Python 3.10+
- 不需要安裝 Python 套件
- 不直接用模型 API key
- AI 來源只用兩種：
  - 已登入的訂閱型 CLI：Agy、Codex CLI、Claude Code
  - 本機 Ollama：需要 Ollama app 或 `ollama serve`
- `outlines/` 放輸入大綱，只保留 `.keep` 進 Git
- `stories/` 放生成結果，只保留 `.keep` 進 Git

## 執行方式

確認 Python：

```bash
python3 --version
```

偵測本機可用的 AI 來源，產生 `presets.generated.json`：

```bash
python3 scripts/generate_presets.py
```

這一步會檢查：

- `PATH` 裡有沒有 `agy`
- `PATH` 裡有沒有 `codex`
- `PATH` 裡有沒有 `claude`
- 本機 Ollama 是否有回應，以及已下載哪些模型

其他訂閱型 CLI 目前沒有偵測；要支援的話改 `scripts/generate_presets.py`。

列出產生出來的 preset：

```bash
python3 story_harness.py --list-presets
```

`--list-presets` 只讀 `presets.generated.json`，不會重新偵測。

跑測試：

```bash
python3 -m unittest
```

整理大綱：

```bash
python3 scripts/prepare_outline.py outlines/example.md \
  --preset <list-presets 裡的 preset>
```

這會用 `prompts/outline.md` 當整理格式，直接整理並覆寫 `outlines/example.md`。如果想另存新檔，加 `--new-file`，會寫到 `outlines/<故事名>.md`；同名檔案已存在時會加上 `-1`、`-2`。

整理後的大綱要長這樣：

```markdown
# 雨季前的井

**風格**：奇幻、懸疑、偏文學。
**核心**：一座村莊每年雨季前都會聽見井底有人敲門。

## 第一章：井聲

主角第一次聽見井底傳來敲門聲，村人卻假裝沒聽見。

## 第二章：雨前祭

主角發現村裡每年雨季前都會少一個人。
```

執行全部待處理的大綱：

```bash
python3 story_harness.py
```

輸出會在：

```text
stories/YYYYMMDD-故事標題/book.md
```

## 常用指令

跑 `outlines/` 裡所有尚未完成的大綱：

```bash
python3 story_harness.py
```

只跑指定大綱：

```bash
python3 story_harness.py \
  --outline outlines/example.md
```

只跑單章：

```bash
python3 story_harness.py \
  --outline outlines/example.md \
  --chapter 1
```

臨時指定 writer/reviewer：

```bash
python3 story_harness.py \
  --writer <list-presets 裡的 writer preset> \
  --reviewer <list-presets 裡的 reviewer preset>
```

## 設定

- `config.json`：設定預設 writer/reviewer、rounds 和模型參數；`outlines/` 是固定輸入資料夾，`stories/` 是固定輸出資料夾。
- `presets.generated.json`：由偵測腳本產生的 preset 清單，不要手改，也不進 Git。
- `scripts/generate_presets.py`：偵測本機 CLI / Ollama，產生 preset。
- `prompts/outline.md`：整理故事素材成標準大綱的 prompt。

重新產生 preset：

```bash
python3 scripts/generate_presets.py
```

## 大綱格式

大綱需要：

- 一個 H1：故事標題
- 多個 H2：章節

程式只看 H2 出現順序，不解析「第一章」「第二章」這些字。

如果 `outlines/` 裡的大綱還不是這個格式，可以用 `scripts/prepare_outline.py` 直接整理那個檔案。

## 程式結構

- `story_harness.py`：CLI 入口
- `scripts/runner.py`：整本書與 queue 流程
- `scripts/conversation.py`：writer/reviewer 迴圈
- `scripts/outline.py`：讀取與解析大綱
- `scripts/agent.py`：Ollama / command provider client
- `scripts/config.py`：設定檔
- `scripts/generate_presets.py`：偵測本機可用 preset
- `scripts/prepare_outline.py`：把素材整理成可解析大綱
- `prompts/`：writer、reviewer、outline prompt
- `tests/`：測試


## TODO

- 尚未處理額度用完的情況。
- 尚未處理圖片功能。
- 尚未處理打包功能。
