# 🍌 Banana Grandmaster 27B

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/haohao1130-bit/banana-grandmaster-27b/blob/main/Banana_Grandmaster_27B.ipynb)

獨立的 27B／9B 導演對照試煉場。**不修改、不啟動正式 Banana MV，不生成影片。**

## 新實驗：同模型的 T8 分鏡 Off／On

[在 Colab 開啟 T8 實驗分支](https://colab.research.google.com/github/haohao1130-bit/banana-grandmaster-27b/blob/experiment/t8-director-ab/Banana_T8_Director_AB.ipynb)。
此筆記本會 clone `experiment/t8-director-ab`；若已有其他分支的 checkout 會停止提示，
避免畫面開實驗筆記本卻跑到 main 的舊程式。

介面上方新增獨立實驗：給故事主軸、可選參考圖與聲部時間，讓同一顆通用
Qwen3.5-27B 拍兩版。Off 使用精簡導演指令，On 只在同樣指令後加入 T8
實驗分鏡方法；故事、圖片、輸出格式、取樣與模型 revision 相同。可選 9B
或反轉 Off／On 順序再跑。兩個實驗共用 GPU 佇列，避免兩個按鈕同時載入模型。

這組實驗不使用下方舊版 Banana planner/writer 的 system；舊對照保留。
預設案例是新寫的 15 秒雙線喜劇，聲部時間是測試用人工設定，**沒有分析原曲**。
上傳圖片時，在主軸明寫 Picture 1、Picture 2 分別代表誰；非演唱角色可以用
動作、插鏡與反應參與畫面。沒有固定鏡數或最低鏡長。

Colab 第一格會下載一份固定 T8 來源到忽略的 `cache/t8/`。本機先執行：

```bash
python tools/fetch_t8.py
```

來源固定為 [T8 storyboard_director.py](https://github.com/T8mars/comfyui-minimax-h3-prompt-enhancer-T8/blob/25a8caafac8d4d77f5d0e11b6c01f1491903d5f5/storyboard_director.py)，
Git blob `4f4bd39499d05649f9befe57b5de1bfeda50913f`。驗證雜湊後，用 AST
只讀取 H3／AUTO 分支的字串，不 import、eval 或 exec 上游程式；不安裝 ComfyUI
或其他 T8 功能，也不把上游原文收入本倉庫。來源缺少／雜湊不符就停止，不偷偷
退回無 T8 的實驗。詳見 [實驗方法與驗收](docs/director-experiment.md)。

每版原始輸出與失敗立即存檔；JSON 包含完整 system、任務、T8／system 雜湊、
模型 revision、取樣、圖片像素雜湊與尺寸、耗時及顯存紀錄。兩版會各自載入及
釋放同一模型，因此一次比較有兩次載入成本；本次不為了省載入而改既有 backend
生命週期。結果與素材不會自動上傳 GitHub。

**目前只是可執行的文字對照工具。** 沒有真實 27B／H3／Seedance 生成結果，
不能稱為接近 Seedance 的品質驗收，也不能當成完整 T8 插件的測試。

## 測什麼

預設比較官方 `Qwen/Qwen3.5-9B` 與 `Qwen/Qwen3.5-27B`，兩邊皆以 Transformers＋bitsandbytes NF4 載入；關閉思考、temperature 0.7、top_p 0.8、top_k 20，逐顆載入及釋放，不同時保留兩顆。

**這不是正式 Banana MV 的 H3 專用量化改寫 9B。** 此處先比較同系列通用模型，不能將結果直接宣稱為「27B 比現有 H3 改寫器好多少」。也沒有自動把模型接入正式版。

保留同一版 Banana 導演／畫面寫手 system，提供：

- 全曲規劃：72 秒、八段、舞台演唱與拳擊雙線，完整作品／中段片段切換。
- 單段畫面：同一個攻防事件，觀察動作、攝影與角色分工。
- 最多四張參考圖；兩邊使用相同 EXIF 校正、768px 縮圖與任務內容。
- 原始輸出並排、完整 JSON 下載；每個模型完成或失敗後即保存。
- 可反轉測試順序，換 Seed 重測；不加第二顆模型當裁判。

## 開始

Colab 依序執行三格：獨立安裝 → 選保存位置 → 啟動內嵌介面。按「請兩位導演各拍一版」才下載／執行模型。預設結果和快取在 `MyDrive/BananaGrandmaster27B`。

兩份筆記本的預設 GPU 偏好皆為 **G4**；請在「執行階段 → 變更執行階段類型」確認。
實際分配依 Colab 資源與帳戶而定；此設定不保證顯存足夠，也不會自動切換既有執行階段。

第一格會在服務已停止、分支正確且沒有本地修改時，以 `git pull --ff-only` 更新。
安裝採 `venv --without-pip --system-site-packages`，再由 notebook 的 pip
將 pip 安裝到獨立環境，避免 Colab 缺少 ensurepip 或失敗留下半成品的問題。
不同 Python 版本或無法執行的舊環境會保留為 `.venv-before-setup-*`，不刪除。
每個安裝步驟都顯示完整輸出，並保存 `setup.log`；失敗時以第一個具體 ERROR
判斷，不自動認定 Python 3.13 不支援。此 log 不會提交到 GitHub。

使用獨立虛擬環境，沿用 Colab 的 GPU PyTorch；不修改 ComfyUI。27B 需要較大的顯存，實際需求取決於圖片與上下文。OOM 會記錄錯誤，不偷偷 CPU offload 或換模型。未做實際 GPU 執行驗收，不能保證每種 Colab 卡都能跑。

**NF4 是載入時量化。** 仍需先下載官方完整原始權重；兩顆合計可能需要數十 GB 以上磁碟。第一次的載入時間含下載與量化，不拿它當純推論速度。

本機已有 CUDA PyTorch 時：

```bash
python -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py --output runs
```

Windows 使用 `.venv\Scripts\python.exe`。介面預設只綁 localhost，不建立公開分享網址；Colab 透過登入中的 notebook 內嵌代理存取。

## 怎麼看結果

| 紀錄 | 意義與限制 |
|---|---|
| generation_seconds | generate 呼叫耗時，含模型 prefill，不含載入和圖片處理 |
| output_tokens_per_second | 該模型 tokenizer 的生成 token／秒，不能當故事品質分數 |
| load_seconds_including_download | 含首次下載、載入及量化；快取狀態不同時不可直接比 |
| peak_torch_allocated / reserved | PyTorch 記憶體統計，不是所有程序的 GPU 總顯存 |
| hit_token_budget | 可能被輸出上限截斷，不能直接判定模型不會結尾 |
| technical_check | 部分 JSON、段數、角色引用和收尾預算檢查；不是完整 Banana MV validator，更不是故事或影片驗證 |

人工比較：角色／場地是否混線、因果與事件是否推進、是否反覆勝利、是否漏掉事件、收尾是否可拍完、畫面是否具體有變化。格式通過仍可能把劇情寫反。沒有 H3 成片，不能據此評估手腳、臉或對嘴。

固定同一 Seed 方便重現測試設定，不代表兩個不同架構有相同抽樣路徑。至少測不同故事、不同 Seed，交換順序；再決定是否值得做「27B 全曲規劃＋9B 分段寫手」。

報告保存模型 commit revision、套件版本、GPU、量化、指令、任務、Seed、圖片像素雜湊與尺寸；不自動複製圖片或上傳任何結果到 GitHub。自己的圖片需另外保存才能重現。`runs/`、快取和 log 預設忽略。

## 離線檢查

```bash
python tools/build_notebook.py
python -m unittest discover -s tests -v
python -m compileall -q bench app.py tools
```

使用模擬 backend 驗證同輸入、順序、錯誤保存和技術檢查；不代表 GPU 速度、顯存或品質已驗證。

參考：[Qwen 27B](https://huggingface.co/Qwen/Qwen3.5-27B)、[Qwen 9B](https://huggingface.co/Qwen/Qwen3.5-9B)、[bitsandbytes](https://huggingface.co/docs/transformers/main/en/quantization/bitsandbytes)。模型與套件授權依各自來源；本倉庫不附權重。
