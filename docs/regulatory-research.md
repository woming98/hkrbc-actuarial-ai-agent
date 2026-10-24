# HK RBC prototype：監管種子資料核對記錄

核對日期：2026-10-24（香港／上海時區）。`regulatory-evidence.json` 包含 10 筆短篇研究者摘要，並非原文摘錄，亦非完整或已確認現行的法規資料庫。每筆附官方來源、章節、日期、版本、核對方式及適用限制；未知日期保留 `null`。沒有聲稱取得官方再發布授權或開放授權。

## 已採用的第一手來源

| 資料 | 官方來源與定位 | 證據範圍 |
| --- | --- | --- |
| 制度框架 | [IA 2024-01-11 諮詢文件](https://www.ia.org.hk/en/infocenter/files/Consultation_Paper_on_the_Draft_RBC_Rules_20240111_Eng.pdf)，第 2 章第 12 段、註 3 | 制度背景說明；不能當作現行具約束力條文 |
| 原始實施時間 | [政府 2024-05-03 公告](https://www.info.gov.hk/gia/general/202405/03/P2024050300187p.htm) | 原始實施公告 |
| Cap. 41R 原始刊憲文本 | [IA 保存的 L.N. 62 of 2024](https://www.ia.org.hk/en/legislative_framework/overview/files/es22024281862.pdf)，B647、B973；[立法會副本](https://www.legco.gov.hk/yr2024/english/subleg/negative/2024ln062-e.pdf)，Explanatory Note 第 5–6 段 | 原始第 5(1)–(3)、87(1)–(3) 條，以及適用範圍解說；不是現行綜合本 |
| 資本披露欄位 | [IA 2025-08-08 通函附件 1](https://www.ia.org.hk/en/legislative_framework/circulars/reg_matters/files/Circular_20250808_Annex_1.pdf)，第 4 節、印刷頁 4–5；[有日期的通函](https://www.ia.org.hk/en/legislative_framework/circulars/reg_matters/files/Circular_20250808_First_Year_Public_Disclosure.pdf) | 首個適用財政年度披露格式；不能推導工具合資格標準或資本上限 |
| 巨災 own assessment | [IA 指引附錄](https://www.ia.org.hk/english/legislative_framework/circulars/reg_matters/files/Cir_dd_12.6.2024_41R_Appendixes.pdf)，Appendix 3 第 1.1 段 | 第 67–68 條相關批准程序；檔名日期未另以官方封面核實 |
| 2026 變動時間 | [政府 2026-05-22 公告](https://www.info.gov.hk/gia/general/202605/22/P2026052200317.htm) | 已刊憲公告；具體修訂條文及後續程序未完整核實 |

## 時效性和擷取限制

2026 公告須區分兩組時間：公眾披露規則於刊憲時實施，而 RBC 檢討修訂的公告實施時間是 2026-12-31。資料記錄分別使用 `public_disclosure_effective_from` 和 `review_amendments_effective_from`，避免把兩者合併為單一生效日。尚未獨立核實負面審議結果、後續通知或全部修訂沿革，不能把原始 2024 文本標成「截至 2026-10-24 全部現行要求」。

[官方現行 Cap. 41R 入口](https://www.elegislation.gov.hk/hk/cap41R) 在本次擷取轉至瀏覽器設定檢查頁，沒有取得綜合條文。IA PDF 的直接擷取回傳 403，立法會 PDF 擷取回傳 502，但官方網域的搜尋索引回傳了上述特定條文文字。因此 metadata 明確記錄 `Official-domain text surfaced by web search index`，沒有聲稱已下載、完整閱讀或逐頁驗證原始 PDF。政府 2026 公告已開啟並與官方索引內容比對。

種子資料沒有抄入第三方法律網站內容。搜尋中出現的顧問文章、保險公司資料、草擬規則或未核實條文不作最終法規依據。特別是第 7 條的數字資本上限，本輪沒有取得正式條文的第一手核實，因此沒有加入種子資料；披露表只支持資本分層欄位。

## 原型必須採用的證據不足行為

- 回答精確條文、現行合規判斷或監管計算時，先檢查版本、估值日、保險人類型和特別批准／寬免。
- 所有本輪記錄的 `current_consolidated_status_verified` 均為 `false`。可回答有來源的歷史或制度概念問題，但必須帶出版本限制，不能說已確認現行完整要求。
- 若問題要求未收入的壓力因子、相關矩陣、matching adjustment 計算、完整 PCA 聚合、資本工具認可、過渡批准或個別公司寬免，應回覆證據不足，指出缺少哪項原始資料；不得由關鍵字命中推算答案。
- 尚未取得生效證據的草案，以及未到生效日的修訂，不得當作已實施的規則。
- 每次法律事實主張必須能回指資料 ID、官方 URL、章節和版本。摘要不能冒充逐字引文。

## 版權與內容交付

交付內容僅為少量原創摘要與官方連結。`exact_quote` 全部為 `null`；沒有重新散布法規 PDF、全文、長段原文或第三方評註。每筆保留來源權利和用途限制，不聲稱這批摘要或來源內容構成完整的公開再發布許可。若正式建立全文 RAG corpus，須另外核對來源使用條款、官方文本完整性及版本更新程序。
