# BANANAMV｜Gemma 3 12B Q5｜RTX 5070 精簡版

這是原本 **27B 實驗倉庫的新 12B 分支**。導演模型改為 Gemma 3 12B IT Q5_K_M，保留既有 Python MV 分段、SRT 多聲部、圖片參考、MINIMAX H3 提示詞、H3 交棒等功能。

## 實際共用架構

**不會重新安裝 CUDA13、PyTorch、ComfyUI、H3、音樂分析、FFmpeg，也不會複製 H3 幾十 GB 的權重。**

- 原版 5070 CUDA13 Python：`F:\AI\Banana9B-cu130\Scripts\python.exe`
- 原版音樂分析 Python：`F:\AI\BananaMusicVenv\Scripts\python.exe`
- 原版 MV/FILM 共用 ComfyUI 主程式：`F:\AI\ComfyUI\App\main.py`
- 原版共用權重優先：`F:\AI\Models`，如缺少六個指定 H3 檔案，才引用已存在的 `F:\AI\BANANAMV_27B_STUDIO\Models\H3`，**不下載 H3**
- 已驗證的 CUDA13 llama.cpp：`F:\AI\BANANAMV_27B_STUDIO\Runtime\llama.cpp\llama-server.exe`，**只借用這顆執行檔，完全不載入 27B 模型、不啟動舊 27B 程序**。暫時不能刪除舊 27B 的該 runtime 資料夾；未來可獨立移轉，不必重新下載
- 新 12B 的 GitHub 程式、設定、獨立影片／圖片輸出和兩個新模型：`F:\BANANAMV_12B_STUDIO`

## 唯二下載的模型

`bartowski/google_gemma-3-12b-it-GGUF`：

1. `google_gemma-3-12b-it-Q5_K_M.gguf`
2. `mmproj-google_gemma-3-12b-it-f16.gguf`

兩個檔案放在 `F:\BANANAMV_12B_STUDIO\Models\12B`。重新執行安裝器會檢查檔案大小並跳過已下載完整的檔案。

## 一鍵安裝／恢復已 Clone 的環境

首次從 repo `experiment/rtx5070-gemma3-12b` 分支下載 `Install_BANANAMV_12B.cmd`，執行即可。

已經 Clone 過 `F:\BANANAMV_12B_STUDIO\App` 的使用者直接在 PowerShell 執行：

```powershell
$root = 'F:\BANANAMV_12B_STUDIO'
git -C "$root\App" pull --ff-only origin experiment/rtx5070-gemma3-12b
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$root\App\tools\install_12b.ps1" -Root $root
```

安裝器只讀取原版 `F:\AI` 的共享軟體和模型；**不會對它們執行 pip install、git checkout、下載、刪除或覆寫**。在新 12B 資料夾內存放兩顆 GGUF、ComfyUI 額外模型路徑索引、FFmpeg 路徑索引及啟動配置。

如果找不到原本某個 H3 或 FFmpeg 檔案，安裝器會明確報出缺少項目，而不是默默再安裝一套。

## 連接埠與安全

- 12B MV 前端：8193
- 12B llama.cpp 導演：8217，按需啟動、生成後釋放
- **12B 使用原版 ComfyUI 程式碼**，另開 **8218** 的獨立服務和自己的 Input/Output/Temp，與原版 MV／FILM 不共用服務進程

**先正常關閉原 9B／FILM／27B 片場再啟動 12B**，避免 12GB VRAM 同時跑兩個模型。若 8193 或 8218 被別的片場占用，12B 會拒絕啟動，不會關閉其他程式。

## 初始 GPU 實驗值

```text
-c 16384 -ngl 99 -fit on -fitt 512 -fa auto -ctk q8_0 -ctv q8_0 -np 1 -t 8 --no-mmproj-offload
```

這是 **Gemma Q5 + 16K + Q8 KV + CPU mmproj 的起始設定**，不是 100% 全 GPU 或 45–60 t/s 的保證；以 5070 實機生成日誌為準。

```powershell
Get-Content 'F:\BANANAMV_12B_STUDIO\Logs\gemma12b.log' -Tail 100
```

先試兩張參考圖、10 秒短段落，核對 `tg = XX t/s`、S1/S2 身份和 H3 交棒，再試多張圖片。
