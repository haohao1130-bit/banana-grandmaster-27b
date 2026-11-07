# Banana H3 專用 9B × T8 實驗場

27B 先停用；倉庫沿用原名稱。正式 BananaMV 不受修改，既有權重與結果不刪除。

[開啟 Colab：9B × T8](https://colab.research.google.com/github/haohao1130-bit/banana-grandmaster-27b/blob/experiment/t8-director-ab/Banana_9B_T8_AB.ipynb)

選 G4，依序執行三格，將同一組故事與參考圖送進 Off／On。第一次須下載 H3 專用的 `minimax_h3_rewriter_ref2va_qwen3.5_9b_w4a8.safetensors`；不下載通用 27B 或 H3 影片模型。舊的兩份筆記本也已轉接相同 9B 入口。

- Off：正式版使用的原生 Ref2VA 短系統＋官方指南，經 ComfyUI 原生 TextGenerate 執行。
- On：相同模型、圖片、故事、Seed、取樣，系統提示末端只加一次固定版本 T8 storyboard 指令。這不是完整 T8 enhancer。
- 刻意不帶入正式版其餘攝影／表演規則，以隔離 T8 的影響。因此 Off 是原生基準，不是完整正式管線的重播。

參考圖按順序送入，轉 RGB、最長邊 768、JPEG quality 92，兩組共用同一份實際輸入。沿用 temperature .7、top_p .8、top_k 20、thinking false、MTP auto；配對固定 seed。MTP 的固定 seed 不代表跨硬體、版本能逐字重現。

ComfyUI 固定 `56f179f6c50dad0c4c860ae4da427415c8e86415`，使用本倉庫 `runtime/native9b/ComfyUI`、埠 8189，不使用正式版的 ComfyUI 或自訂節點。模型／指南的實際 revision、SHA256、Comfy commit、GPU 資訊記錄在安裝 manifest，再複製到每份報告。第三格日誌在 `native9b.log` 與 `bench.log`。

Drive 只存 `Banana9BT8Bench/runs` 的結果，HF 快取與模型放 Colab 本機。新執行階段會重新下載；避免沿用 27B 的 Drive blob 連結問題。只停止本筆記本啟動的兩個服務，不刪歷史檔案。

每個實驗保存故事、兩組完整系統提示與雜湊、T8 出處、實際圖片、完整圖表、原始回傳與錯誤。第一組失敗即停止，不繼續提交可能還在排隊的第二組；已完成結果即時保存。

9B 沒有直接聽音訊。歌詞／歌曲情緒來自使用者文字；`<Audio 1>: fully_copy` 只是輸出的音訊意圖，此測試沒有傳送、播放或合成音訊。這裡只測文字，還不能宣稱 H3 成片或 Seedance 等級。

驗證：原生圖表契約、配對唯一系統差異、圖片一致性、輸出保存、失敗停止與筆記本語法有離線測試；沒有 GPU 實機結果。Colab GPU／套件安裝相容性與實際文字品質仍待驗證。舊通用 HF 程式及 `requirements-legacy27b.txt` 保留供追溯，已不由 app 或筆記本呼叫。
