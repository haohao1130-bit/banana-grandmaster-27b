# BANANAMV｜Gemma 3 12B Q5｜RTX 5070 獨立片場

本分支改用 **Gemma 3 12B IT Q5_K_M 多模態導演**，沿用 BANANAMV 27B 實驗版既有的 Python 分段、SRT 聲部分配、角色隔離、MiniMax H3 生成與 ComfyUI 交棒流程。不修改原本 9B、FILM 或舊 27B 分支。

## 一鍵安裝（Windows 11、RTX 5070 12GB）

下載倉庫根目錄的 `Install_BANANAMV_12B.cmd` 並執行。安裝器會自動安裝／檢查 Git、FFmpeg、Python 3.12、CUDA 13 PyTorch、獨立 ComfyUI、H3 T8 節點、官方 llama.cpp CUDA13、Gemma 模型與 H3 權重，支援重跑／模型續傳。需要足夠的 F 槽空間；H3 權重遠大於單一 Gemma 模型檔。

- **安裝路徑**：`F:\BANANAMV_12B_STUDIO`
- **原始倉庫**：`haohao1130-bit/banana-grandmaster-27b`
- **分支**：`experiment/rtx5070-gemma3-12b`
- **啟動器**：`F:\BANANAMV_12B_STUDIO\Launch_BANANAMV_12B.cmd`
- **桌面捷徑**：`BANANAMV 12B`
- **網頁**：`http://127.0.0.1:8193`
- **Gemma llama.cpp**：`127.0.0.1:8217`，寫提示詞時才啟動
- **獨立 MiniMax H3 ComfyUI**：`127.0.0.1:8218`

安裝／啟動時，如果 8193 已被其他 Studio 占用，啟動器會拒絕啟動。8218 也會驗證是否為自己的 ComfyUI；不終止舊片場的程序。**請先正常關閉舊 27B 片場，才啟動 12B**。不要刪除舊資料夾。

## 模型

採用同一組 Hugging Face 發行者的互相配對檔案：

- `bartowski/google_gemma-3-12b-it-GGUF` 的 `google_gemma-3-12b-it-Q5_K_M.gguf`（約 8.44 GB，十進位）
- `bartowski/google_gemma-3-12b-it-GGUF` 的 `mmproj-google_gemma-3-12b-it-f16.gguf`（約 854 MB）
- 原本 H3 的六個權重、LoRA 資產及依賴保持不變

注意：854 MB 是視覺投影器檔案大小，**不代表 GPU 專用記憶體必須額外常駐這麼多**。12B 仍會閱讀多張 `@圖片`，但視覺投影器預設在 CPU 做影像編碼，讓 5070 專用顯存優先留給語言模型。

## GPU 初始設定（需實機確認）

```text
-c 16384 -ngl 99 -fit on -fitt 512 -fa auto -ctk q8_0 -ctv q8_0 -np 1 -t 8 --no-mmproj-offload
```

- **16K context** 是起始設定：先避免 32K 額外 KV Cache 壓力；不是永久限制。可經 `Data\config.json` 自訂，啟動器保留自訂值。
- **99 層是全層卸載請求**，但 `-fit on` 在顯存不足時可能減少 GPU 層數；不能保證所有層都在 GPU。
- **Q8 KV Cache** 以較低記憶體需求換取少量精度／速度折衷；實際速度必須測。
- **CPU mmproj** 保留多圖能力，避免多張圖片與語言模型同時搶 VRAM；視覺編碼階段可能更慢。
- 不允許使用 **Windows 共用 GPU RAM** 當作達成目標的必要條件；它經 PCIe 存取通常遠慢於專用 VRAM。
- 不能保證 45 t/s 以上、固定 10GB 專用 VRAM 或 15–25 秒生成完整 1000+ tokens 提示詞；先看實測值與品質。

**檢查記錄：**

```powershell
Get-Content 'F:\BANANAMV_12B_STUDIO\Logs\gemma12b.log' -Tail 120
Get-CimInstance Win32_Process | Where-Object Name -eq 'llama-server.exe' | Select-Object ProcessId,CommandLine
nvidia-smi
```

想確認哪幾層實際在 GPU，請查看 llama-server 的模型載入診斷或增加 log verbosity；不能只用 GPU 使用率 100% 判定。查看 `tg = XX t/s` 測真實生成速度。

## 原有流程保留

Python 仍先處理整首歌曲與分段通告，Gemma 3 12B 只取得當段所需的固定身份、目前事件、SRT 聲部時間與當前連續狀態，不傳送未來劇情。交給 H3 之前會結束 12B llama-server 釋放 GPU 記憶體。原本多圖 S1/S2 身分綁定修正、禁止未登場人物提前入鏡和六欄 H3 提示詞格式保留。

系統預設在 8193/8217/8218，與舊獨立 27B 使用相同埠。舊版停止後才啟動新版；**沒有升級或覆寫舊 27B 工作目錄**。

## 診斷／測試

程式碼靜態回歸測試（不需 GPU）：`python -m unittest tests.test_llama27b tests.test_services tests.test_clip_cast_27b`。在 Windows 本機安裝完成後，先做一段 10 秒、兩張參考圖的測試，確認提示詞、S1/S2 和 H3 交棒，再測四至六張參考圖。當 GPU 專用 VRAM 溢出或速度很慢時，優先檢查模型是否全部卸載、mmproj 是否留 CPU、KV Cache 和圖片數量；不要直接改成 27B 的 `-ngl 999 -fit off`。
