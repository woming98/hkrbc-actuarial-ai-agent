# 面試示範 / Interview walkthrough — 約 9 分 30 秒

這個示範展示受控的精算工作流程：可追溯證據、確定性計算、失敗時阻擋完成，以及權限與審計。全部投資組合都是合成資料；資本是內部示意模型，沒有宣稱 HK RBC 合規、監管認可或生產就緒。

**Opening line:** “This prototype makes an actuarial workflow repeatable and inspectable. Evidence retrieval, numerical calculation and validation have separate responsibilities. Every capital figure here is illustrative.”

## 示範前 / Before the interview

從專案根目錄，在已安裝依賴的環境執行：

```bash
python scripts/preflight.py
```

預期 JSON 顯示 `status: ready`。這個檢查只讀檔案、套件資料和設定風險；不建立資料庫、不登入、不啟動伺服器、不呼叫網絡、不載入模型，也不輸出環境變數的值。模型狀態只檢查 manifest、檔案清單和大小；完整權重雜湊仍由實際載入器檢查。退出碼非零表示必要項目缺失或設定不適合這個離線示範。

接著由你明確啟動本機介面：

```bash
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

開啟 `http://127.0.0.1:8501`。本機工作區亦可使用 `/opt/anaconda3/bin/python`；這個路徑不能假設在其他電腦存在。應用程式讀取啟動環境，**不會自動載入 `.env`**。詳見 [deployment.md](deployment.md)。

選用預設 BM25、關閉外部處理，並以登入側欄所列的公開 `analyst` 示範帳戶登入。這些帳戶只是本機示範身份，密碼不是保密或生產安全機制；不要公開伺服器。任何全局已設定的 API 金鑰都不需要交給這個示範。

預先打開 [範例報告](../reports/example-actuarial-report.md)、[因子橋截圖](../reports/factor-bridge-preview.jpg) 和 [檢索評估](retrieval-evaluation.md)，可作介面故障時的備案。初始化及載入已安裝套件不計入下面九分半鐘；不要在面試途中安裝依賴或下載模型。

## 0:00–0:45 — 業務問題 / Business problem

可以咁講：「精算同事需要知道用咗邊個版本嘅法規、數字點計、點解資本改變，以及有咩未能驗證。呢個系統將呢幾件事分開記錄，令 reviewer 可以重做同核對。」

**English:** “A fluent answer alone is insufficient for an actuarial review. I need dated evidence, a reproducible calculation, a reconciled movement and an explicit record of what remains unsupported.”

指出四頁：`Regulatory Assistant`、`Capital Analysis`、`Validation Dashboard`、`Governance & Audit`。預設回答是本地擷取的來源摘要；沒有 LLM 參與估值、DV01、壓力測試或驗證狀態。

## 0:45–2:15 — 證據與不確定性 / Evidence and abstention

在 `Regulatory Assistant` 保留 `Local evidence`：

1. 展開 **Example questions / 示範問題**，在 **Choose an example** 選 **Original tier caps / 原有資本上限**，按 **Use example**，再按 **Search evidence**。`Use example` 只填問題，不會自行執行。
2. 展開來源，展示原有 Rule 7、版本、Gazette 頁碼、核對日期、來源 SHA-256，以及原文連結。新增的直接核對段落是 `cap41r-direct-tier-caps`；其範圍是原有 2024 Gazette，沒有聲稱現在的完整合併法例已核實。離線時保留畫面上的來源資料即可；點擊外部原文連結需要網絡。
3. 選 **Current-law evidence gap / 現行法規證據不足** → **Use example** → **Search evidence**。展示不足證據狀態：歷史矩陣或未來修訂不會自動變成「現行規定」。

如果時間足夠，可用 **Scheduled amendment / 未來修訂** 展示未來生效標記，或用 **Compound evidence gap / 複合問題證據不足** 展示有公告背景仍不足以提供 matching-adjustment 公式。

**English:** “A section match is not legal completeness. The application preserves the source version and checks the requested claim scope. It can return background evidence while refusing an unsupported current-law conclusion.”

來源範圍：原始 13 筆種子包含十筆公開來源摘要及三筆合成治理例子；介面另加入 12 筆直接核對的補充段落，來自兩份實際下載並核對的官方 PDF。分發的是研究者自行撰寫的摘要、來源定位與雜湊；完整 PDF、頁面圖片和全文快取不隨專案分發。沒有推定公開文件可無限制轉載。詳見 [source-verification-2026-10-25.md](source-verification-2026-10-25.md) 與 [regulatory-research.md](regulatory-research.md)。

## 2:15–4:15 — 資本移動與兩種歸因 / Capital movement and two allocations

到 `Capital Analysis`：按 **Load synthetic demo portfolios**，確認 synthetic-data 聲明，按 **Run capital analysis**。

| 畫面數字 / Measure | HKD |
|---|---:|
| Opening illustrative capital | 20,224,927.84 |
| Closing illustrative capital | 22,615,906.43 |
| Capital movement | 2,390,978.59 |
| Unexplained residual | 0.00 |

先指向 rate/credit/equity 的 **risk-module Shapley**：個別模組的未分散變動不能直接相加當成總資本變動，因為聚合有 diversification。這個分配精確考慮模型的非線性聚合。

再展示 **Date and input-factor bridge**：

| 因子 / Factor | HKD |
|---|---:|
| Date ageing at opening quotes | −924,090.62 |
| Holdings and equity value | +3,165,983.67 |
| Risk-free yield | +277,386.92 |
| Credit spread | −128,301.37 |

這裡先做日期 ageing，再於同一收市日期列出八個混合狀態、平均六種因子替換順序。未四捨五入的總和與實際移動完全對帳；每行顯示至仙可以產生一仙顯示差異，沒有硬塞 residual。展開 **Factor-bridge definitions, hybrid states and checks**，快速指出輸入、版本、狀態及所有順序。

**English:** “The module allocation explains which risk buckets changed. The second bridge explains defined input replacements: ageing first, then holdings/value, risk-free yield and spread. Equity units and trades are absent, so I do not claim to separate equity price returns from cash flows.”

模型僅使用 HKD 固定票息債券、股票與現金；沒有負債、matching adjustment、評級專屬壓力或官方相關矩陣。示意資本因子是利率 ±100bp、利差 +100bp、股票 −30%。詳見 [actuarial-methodology.md](actuarial-methodology.md) 和 [movement-attribution.md](movement-attribution.md)。

## 4:15–5:30 — 數學對帳通過仍然可以阻擋 / A reconciled result can remain blocked

仍在 `Capital Analysis`，展開 **Validation example / 驗證示範**，按 **Load missing-settlement example**，再按 **Run capital analysis**。

這對合成檔案由 2025-12-31 至 2026-03-31 跨越 2026-01-01 的債券票息，預定款額 HKD400,000，但沒有結算紀錄。模組數字可以對帳，因子橋仍會阻擋：系統不知道款項有沒有收到、轉出或再投資。**Create review report** 在介面停用。不要將未解釋的因子 residual 顯示成零。

到 `Validation Dashboard` 指出 `factor_bridge_validation` 及 `cashflow_bridge_supported` 的失敗，再展開計算紀錄查看事件日期與輸入。另一個 [malformed.csv](../data/portfolios/malformed.csv) 會在輸入階段因重複 asset ID 被拒絕。

**English:** “Arithmetic reconciliation does not establish an economic explanation. Without settlement information, the default workflow blocks completion. An explicit hypothetical no-interest cash path exists only as an advanced library option; the demo does not silently assume it.”

使用的檔案是 [coupon_crossing_opening.csv](../data/portfolios/coupon_crossing_opening.csv) 和 [coupon_crossing_closing.csv](../data/portfolios/coupon_crossing_closing.csv)。

## 5:30–6:45 — 權限、版本與審計 / Governance

到 `Governance & Audit`：

- 用 analyst 身份展示來源登記及自己的審計事件；指出來源版本、工具版本、驗證狀態與 provider，沒有儲存原始問題或投資組合到審計欄位。
- 解釋 SQL 在檢索前過濾權限，回傳／編碼前再次檢查。不是只把 UI 按鈕隱藏。
- 如需展示角色差異，登出後以側欄公開的 reviewer 示範身份登入；登記可見 internal 合成例子。Administrator 才能攝入及退休來源版本。角色切換會清除前一身份的畫面結果。

可展示管理表單但不用即場退休來源；退休是保留原始內容與雜湊的不可改寫決策，會改變之後的檢索。固定測試涵蓋未授權退休、替代來源權限，以及 A→B→C 後重試舊決策的冪等性。

**English:** “The privacy controls are enforced at the service boundary. Local processing is the default; external commentary requires server enablement, an eligible role, explicit approval and public non-sensitive context. This is still a prototype, with pattern-based DLP and public demo identities.”

## 6:45–8:00 — 點解 BM25 係預設？ / Why BM25 by default?

打開 [retrieval-evaluation.md](retrieval-evaluation.md)。這是 44 條開發者撰寫的診斷問題、13 筆固定種子來源；34 條有非空 relevance labels，12 條中文。補充來源未混入這次比較。

| 實際紀錄 / Method | Recall@3 | 中文 Recall@3 |
|---|---:|---:|
| BM25F + MMR | 0.956 | 0.955 |
| English dense + MMR | 0.691 | 0.318 |
| Multilingual dense + MMR | 0.868 | 0.864 |
| Multilingual hybrid + MMR | 0.926 | 0.864 |

BM25 在這份小型、含精確條文定位與中英詞彙的開發集較好，而且預設不需要模型。英文 encoder 的中文表現較差；多語 encoder 改善中文，但仍低於此處的 BM25。這不是 lexical search 普遍勝過 embeddings 的證明，也不是獨立 held-out 評估。Recall、claim-scope 與權限分開記錄；合法引用 ID 和 relevant section 均不能證明逐句法律 entailment。

如被問速度：兩次紀錄的 BM25 median 約 9ms；英文 dense 約 123ms，多語 dense 約 367ms。這是同一工作機上的非受控量測，且刻意不跨身份快取私有文件向量；不能包裝成普遍性能提升。

**English:** “I measured both real local encoders. BM25 remains the default because it performed best on this inspectable bilingual diagnostic set. I would freeze an independently authored held-out set before making a broader claim.”

原始端到端八案例工具是 [evaluation/run.py](../evaluation/run.py)：C 的離線固定案例有實測；A 與 B 都保留 `not_run`，除非提供真實外部結果。沒有做過的同一 LLM A/B/C 比較不會捏造分數。兩個本地 encoder 是檢索模型，不是資本計算器或生成式回答 LLM。

## 8:00–9:30 — 可重做的交付與取捨 / Reviewable artifacts and trade-offs

回到 `Capital Analysis`，按 **Load synthetic demo portfolios** → **Run capital analysis** → **Create review report**，展示 Markdown/JSON 下載。指出 JSON 有完整合成輸入、函數／版本、檢查、假設與局限；Markdown 供 reviewer 掃讀。若時間不夠，直接展示預先打開的 [範例報告](../reports/example-actuarial-report.md)。

準備以下精簡回答：

| 問題 / Question | 可答重點 / Answer |
|---|---|
| 為甚麼不交給 LLM 計數？ | Python 是數值權威；LLM 如有啟用只補充未驗證文字，不能決定 validation。獨立 Decimal／有限差分／Shapley identity 測試可重做。 |
| 是否重用了原有四個 repo？ | 已在 pinned commit 進行只讀審查，借鑑輸入／計算／reconciliation 的介面思路。沒有複製來源碼；三個沒有清楚授權聲明，另一個 README 的 MIT 連結指向缺失檔案，故先獨立實作。原 repo 沒有修改。詳見 repository review。 |
| 這是否真正的 HK RBC PCA？ | 不是。它是 asset-only 教學模型；官方來源只作帶版本的上下文，不校準這個內部壓力與矩陣。 |
| 下一步最重要是甚麼？ | 真正 IAM、確認適用日期的完整法規版本、加入負債與正式模型校準、獨立 actuarial review、代表性 held-out 問題與更廣泛攻防測試。 |

**Closing line:** “The engineering contribution is a controlled, auditable workflow with honest failure states. The next step is stronger evidence and validation for the intended business use, rather than claiming compliance from a successful demo.”

原 repo 與授權證據見 [repository-review.md](repository-review.md)；測試與比較界限見 [evaluation/README.md](../evaluation/README.md)。本機兩個模型檔案合計約 576MB；檢查時有八個邏輯 CPU、8GiB 實體記憶體。權重大小不等於推論峰值記憶體，預設示範毋須載入模型；不要在有限資源下同時跑兩個 encoder benchmark。
