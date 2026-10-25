"""Authorized bilingual BM25F, optional offline semantics, and evidence scope.

Scores measure relevance, not truth or legal confidence. The original hash ranker
is retained as an explicit benchmark baseline. Document vectors are request-local.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import hashlib
import math
import os
import re
import unicodedata
from zoneinfo import ZoneInfo

import numpy as np

from .embeddings import Encoder, EncoderUnavailable, LocalSentenceTransformerEncoder
from .security import CLASSIFICATIONS, Principal, is_injection, redact, validate_text
from .store import Document, Store

STOPWORDS = frozenset("the a an is are was were what which when how of for in and to with on hk hong kong insurance please does do me about under requirement requirements".split())
# Frozen original aliases for reproducing the original feature-hash baseline.
ALIASES = {
    "實施": "commencement", "生效": "commencement", "何時": "commencement",
    "資本": "capital", "風險": "risk", "監管": "regulatory", "支柱": "pillar",
    "披露": "disclosure", "修訂": "amendment", "規則": "rules", "估值": "valuation",
    "自然災害": "catastrophe", "三級": "tier", "資源": "resources",
    "開始": "commencement", "有效": "commencement", "當前": "current",
    "effective": "commencement", "introduced": "commencement", "begin": "commencement",
    "start": "commencement", "implemented": "commencement", "implementation": "commencement",
    "pillars": "pillar", "amendments": "amendment", "tiers": "tier",
}
_WORDS = {
    "commence": "commencement", "commenced": "commencement", "introduced": "commencement",
    "implementation": "commencement", "implemented": "commencement", "start": "commencement",
    "started": "commencement", "begin": "commencement", "began": "commencement",
    "pillars": "pillar", "tiers": "tier", "amendments": "amendment", "changes": "change",
    "insurers": "insurer", "exceptions": "exception", "exclusions": "exception",
    "excluded": "exception", "exemptions": "exception", "exempt": "exception",
    "relaxes": "relaxation", "relaxed": "relaxation", "relax": "relaxation",
    "varies": "variation", "varied": "variation", "vary": "variation",
    "amounts": "amount", "funds": "fund", "rules": "rule", "sections": "section",
    "approved": "approval", "permission": "approval", "authorization": "approval",
    "authorisation": "approval", "reporting": "disclosure", "required": "requirement",
    "requirements": "requirement", "applicability": "scope", "applies": "scope", "applicable": "scope",
}
# Controlled domain vocabulary, not a general translation model.
_PHRASES = {
    "風險為本資本": "rbc", "风险为本资本": "rbc", "資本": "capital", "资本": "capital",
    "風險": "risk", "风险": "risk", "估值": "valuation", "實施": "commencement", "实施": "commencement",
    "開始": "commencement", "开始": "commencement", "何時": "commencement", "何时": "commencement", "生效": "commencement",
    "三大支柱": "pillar", "支柱": "pillar", "量化": "quantitative", "質化": "qualitative", "质化": "qualitative",
    "企業風險管理": "enterprise risk management", "企业风险管理": "enterprise risk management",
    "披露": "disclosure", "公開": "public", "公开": "public",
    "最低資本額": "mca minimum capital amount", "最低资本额": "mca minimum capital amount",
    "訂明資本額": "pca prescribed capital amount", "订明资本额": "pca prescribed capital amount",
    "資本基礎": "capital base", "资本基础": "capital base", "資本基數": "capital base",
    "豁免": "exception", "例外": "exception", "適用": "scope", "适用": "scope", "保險公司": "insurer", "保险公司": "insurer",
    "海事": "marine", "專屬自保": "captive", "专属自保": "captive", "特定目的": "special purpose", "勞合社": "lloyd", "劳合社": "lloyd",
    "更改": "variation", "變更": "variation", "变更": "variation", "放寬": "relaxation", "放宽": "relaxation",
    "法定基金": "statutory fund", "分配": "allocated", "自然災害": "natural catastrophe", "自然灾害": "natural catastrophe",
    "天災": "catastrophe", "天灾": "catastrophe", "自評": "own assessment", "自评": "own assessment",
    "自行評估": "own assessment", "自行评估": "own assessment", "批准": "approval", "默認": "default", "默认": "default", "因子法": "factor based",
    "無限額一級": "unlimited tier 1", "有限額一級": "limited tier 1", "二級": "tier 2", "二级": "tier 2",
    "第一級": "tier 1", "第一级": "tier 1", "第二級": "tier 2", "第二级": "tier 2", "層級": "tier", "层级": "tier",
    "修訂": "amendment", "修订": "amendment", "公告": "announcement", "公佈": "announcement", "公布": "announcement", "新聞稿": "announcement", "新闻稿": "announcement",
    "匹配調整": "matching adjustment", "匹配调整": "matching adjustment", "相關矩陣": "correlation matrix", "相关矩阵": "correlation matrix",
    "相關係數": "correlation", "相关系数": "correlation", "內部": "internal", "内部": "internal", "示意": "illustrative", "管理員": "administrator", "管理员": "administrator",
    "監管": "regulatory", "监管": "regulatory", "規則": "rule", "规则": "rule", "現行": "current", "当前": "current", "當前": "current", "最新": "latest", "合規": "compliance", "合规": "compliance",
    "come into operation": "commencement", "come into force": "commencement", "go live": "commencement",
    "risk based capital": "rbc", "risk-based capital": "rbc", "three pillars": "pillar", "capital resources": "capital base",
    "minimum capital amount": "mca", "prescribed capital amount": "pca", "own-assessment": "own assessment", "factor-based": "factor based", "public reporting": "disclosure",
}
FIELD_WEIGHTS = {"title": 2.0, "section": 2.8, "text": 1.0}
RETRIEVAL_VERSION = "bm25f-bilingual-1.1"


def _normal(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


def rule_identifiers(text: str) -> set[str]:
    """Preserve alphanumeric rules, nested clauses and bounded clause ranges."""
    text = _normal(text)
    text = re.sub(r"\b(and|or|to|through)(?=\d)", r"\1 ", text)
    result: set[str] = set()
    component = r"[a-z0-9]+"
    chain = rf"(?:\s*\(\s*{component}\s*\))*"

    def add(kind: str, rule: str, parts: list[str], remainder: str) -> None:
        prefix = f"{kind}:{rule}"
        suffix = "".join(f"({part})" for part in parts)
        result.add(prefix + suffix)
        if remainder.lstrip().startswith("("):
            result.add(prefix + suffix + "(?)")
        while parts:
            endpoint = re.match(rf"\s*(?P<op>[–—-]|to\b|through\b|and\b|or\b|[至到及和、,&，])\s*(?P<subs>(?:\(\s*{component}\s*\)\s*)+)", remainder)
            if not endpoint:
                break
            following = re.findall(component, endpoint["subs"])
            first, last = parts[-1], following[0]
            stem = prefix + "".join(f"({part})" for part in parts[:-1])
            is_range = endpoint["op"] in {"–", "—", "-", "to", "through", "至", "到"}
            if not is_range:
                result.add(stem + "".join(f"({part})" for part in following))
            elif len(following) == 1 and first.isdigit() and last.isdigit() and 0 <= int(last) - int(first) <= 12:
                result.update(stem + f"({value})" for value in range(int(first), int(last) + 1))
            elif len(following) == 1 and len(first) == len(last) == 1 and first.isalpha() and last.isalpha() and 0 <= ord(last) - ord(first) <= 12:
                result.update(stem + f"({chr(value)})" for value in range(ord(first), ord(last) + 1))
            else:
                result.add(stem + f"({first}).." + "".join(f"({part})" for part in following))
            parts = parts[:-1] + following
            remainder = remainder[endpoint.end():]

    pattern = rf"(?<![a-z])(?P<label>rules?|sections?|§)\s*(?P<rule>\d+[a-z0-9]*)(?P<subs>{chain})"
    labeled_spans = []
    for match in re.finditer(pattern, text):
        labeled_spans.append(match.span())
        kind = "section" if match["label"].startswith("section") else "rule"
        parts = re.findall(component, match["subs"])
        add(kind, match["rule"], parts, text[match.end():])
        if not parts:
            remainder, first = text[match.end():], match["rule"]
            while True:
                endpoint = re.match(rf"\s*(?P<op>[–—-]|to\b|through\b|and\b|or\b|[至到及和、,&，])\s*(?:rules?|sections?)?\s*(?P<rule>\d+[a-z0-9]*)(?P<subs>{chain})", remainder)
                if not endpoint:
                    break
                last = endpoint["rule"]
                if endpoint["op"] in {"and", "or", "及", "和", "、", ",", "，", "&"}:
                    add(kind, last, re.findall(component, endpoint["subs"]), remainder[endpoint.end():])
                elif first.isdigit() and last.isdigit() and 0 <= int(last) - int(first) <= 12 and not endpoint["subs"].strip():
                    result.update(f"{kind}:{number}" for number in range(int(first), int(last) + 1))
                else:
                    result.add(f"{kind}:{first}..{last}")
                remainder, first = remainder[endpoint.end():], last
    bare = rf"(?<![a-z0-9])(?P<rule>\d+[a-z0-9]*)(?P<subs>(?:\s*\(\s*{component}\s*\))+)"
    for match in re.finditer(bare, text):
        if any(start <= match.start() < end for start, end in labeled_spans):
            continue
        add("rule", match["rule"], re.findall(component, match["subs"]), text[match.end():])
    chinese = rf"第\s*(?P<rule>\d+[a-z0-9]*)(?P<subs>{chain})\s*[條条](?:第?\s*(?P<sub>{component})\s*(?:(?P<op>[至到及和、–—-])\s*(?P<end>{component})\s*)?[款項项])?"
    for match in re.finditer(chinese, text):
        parts = re.findall(component, match["subs"]) + ([match["sub"]] if match["sub"] else [])
        remainder = (match["op"] + "(" + match["end"] + ")" if match["op"] else "") + text[match.end():]
        add("rule", match["rule"], parts, remainder)
    return result


def tokens(text: str) -> list[str]:
    text = _normal(text)
    words = re.findall(r"[a-z][a-z0-9]*(?:[_-][a-z0-9]+)*|\d+(?:\.\d+)?", text)
    # Retain identifiers, but also match ordinary hyphenated prose to its words.
    words += [part for word in words if "-" in word for part in word.split("-")]
    result = [_WORDS.get(word, word) for word in words if word not in STOPWORDS]
    for span in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        result.extend("zh:" + span[index:index + 2] for index in range(len(span) - 1))
    for phrase, concepts in _PHRASES.items():
        present = phrase in text if re.search(r"[\u4e00-\u9fff]", phrase) else bool(re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", text))
        if present:
            result.extend(_WORDS.get(word, word) for word in concepts.split() if word not in STOPWORDS)
    result.extend("id:" + identifier for identifier in sorted(rule_identifiers(text)))
    return result


def _legacy_tokens(text: str) -> list[str]:
    text = text.lower()
    expanded = text + " " + " ".join(value for key, value in ALIASES.items() if key in text)
    terms = re.findall(r"[a-z]+|\d{4}|[\u4e00-\u9fff]{2,}", expanded)
    return [ALIASES.get(term, term) for term in terms if term not in STOPWORDS]


def embed(text: str, dimensions: int = 512) -> np.ndarray:
    """Frozen original hash baseline; MMR uses it only to measure redundancy."""
    if type(dimensions) is not int or dimensions < 1:
        raise ValueError("Embedding dimensions must be positive")
    vector = np.zeros(dimensions, dtype=np.float64)
    for term in _legacy_tokens(text):
        index = int.from_bytes(hashlib.blake2b(term.encode(), digest_size=8).digest(), "big") % dimensions
        vector[index] += 1.0
    norm = np.linalg.norm(vector)
    return vector / norm if norm else vector


def section_chunks(document: Document, max_chars: int = 1200) -> list[Document]:
    if max_chars < 100:
        raise ValueError("Chunk size must be at least 100")
    if len(document.text) <= max_chars:
        return [document]
    pieces: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", document.text):
        for sentence in re.split(r"(?<=[.!?。])\s+", paragraph):
            for offset in range(0, len(sentence), max_chars):
                part = sentence[offset:offset + max_chars]
                if current and len(current) + len(part) + 1 > max_chars:
                    pieces.append(current)
                    current = ""
                current = (current + " " + part).strip()
    if current:
        pieces.append(current)
    return [document.model_copy(update={"document_id": f"{document.document_id[:68]}-p{index + 1}", "text": text}) for index, text in enumerate(pieces)]


@dataclass(frozen=True)
class Hit:
    document: Document
    score: float
    retrieval_method: str = "unspecified"

    def to_dict(self) -> dict:
        return {"reference": self.document.reference, "score": round(self.score, 6), "retrieval_method": self.retrieval_method, **self.document.model_dump(mode="json")}


def _primary_rules(document: Document) -> set[str]:
    return rule_identifiers(document.section)


def _rule_match(requested: set[str], document: Document) -> bool:
    primary = _primary_rules(document)
    return not requested or any(wanted in primary or any(value.startswith(wanted + "(") for value in primary) for wanted in requested)


def _bm25_scores(documents: list[Document], query: str) -> list[float]:
    """BM25F field-normalized term frequency, saturation k1=1.2, b=.75."""
    if not documents:
        return []
    fields = [{name: Counter(tokens(getattr(document, name))) for name in FIELD_WEIGHTS} for document in documents]
    averages = {name: sum(sum(item[name].values()) for item in fields) / len(fields) or 1 for name in FIELD_WEIGHTS}
    query_terms = set(tokens(query))
    df = {term: sum(any(term in item[name] for name in FIELD_WEIGHTS) for item in fields) for term in query_terms}
    scores = []
    for document, item in zip(documents, fields):
        score = 0.0
        for term in query_terms:
            tf = sum(weight * item[name][term] / (.25 + .75 * sum(item[name].values()) / averages[name]) for name, weight in FIELD_WEIGHTS.items())
            if tf:
                idf = math.log(1 + (len(documents) - df[term] + .5) / (df[term] + .5))
                score += idf * (2.2 * tf) / (1.2 + tf)
        scores.append(score + 4 * len(rule_identifiers(query) & _primary_rules(document)))
    return scores


class Retriever:
    def __init__(self, store: Store, *, backend: str = "bm25", encoder: Encoder | None = None) -> None:
        if backend not in {"bm25", "hash", "dense", "hybrid"}:
            raise ValueError("Unknown retrieval backend")
        if backend in {"dense", "hybrid"} and encoder is None:
            raise EncoderUnavailable("Semantic retrieval requires an explicitly configured local encoder")
        self.store, self.backend, self.encoder = store, backend, encoder

    @classmethod
    def from_env(cls, store: Store) -> Retriever:
        backend = os.getenv("HKRBC_RETRIEVAL_BACKEND", "bm25").lower()
        if backend not in {"bm25", "hash", "dense", "hybrid"}:
            raise ValueError("Unknown retrieval backend")
        path = os.getenv("HKRBC_EMBEDDING_MODEL_PATH", "")
        encoder = LocalSentenceTransformerEncoder(path) if backend in {"dense", "hybrid"} and path else None
        return cls(store, backend=backend, encoder=encoder)

    def search(self, principal: Principal, query: str, limit: int = 3) -> list[Hit]:
        safe_query, _ = redact(validate_text(query))
        if is_injection(safe_query):
            return []
        if type(limit) is not int:
            raise ValueError("Retrieval limit must be an integer")
        limit = max(1, min(limit, 10))
        # Both SQL authorization and an independent policy check precede all encoding.
        documents = [doc for doc in self.store.visible_documents(principal) if doc.classification in CLASSIFICATIONS[principal.role] and not is_injection(doc.model_dump_json())]
        if not documents or not tokens(safe_query):
            return []
        contents = [doc.title + " " + doc.section + " " + doc.text for doc in documents]
        if self.backend == "hash":
            query_terms = set(_legacy_tokens(safe_query))
            query_vector = embed(safe_query)
            hits = [Hit(doc, float(np.dot(query_vector, embed(content))), "hash-legacy") for doc, content in zip(documents, contents) if query_terms & set(_legacy_tokens(doc.text + " " + doc.section))]
            return sorted((hit for hit in hits if math.isfinite(hit.score) and hit.score >= .12), key=lambda hit: (-hit.score, hit.document.reference))[:limit]
        requested_rules = rule_identifiers(safe_query)
        eligible = [index for index, doc in enumerate(documents) if _rule_match(requested_rules, doc)]
        lexical = _bm25_scores(documents, safe_query)
        if self.backend in {"dense", "hybrid"}:
            vectors = np.asarray(self.encoder.encode([safe_query, *contents]), dtype=np.float64)
            if vectors.ndim != 2 or vectors.shape[0] != len(documents) + 1 or not vectors.shape[1] or not np.isfinite(vectors).all():
                raise ValueError("Encoder returned an invalid vector matrix")
            norms = np.linalg.norm(vectors, axis=1)
            if np.any(norms <= 0):
                raise ValueError("Encoder returned zero-length vectors")
            vectors = vectors / norms[:, None]
            semantic = vectors[1:] @ vectors[0]
            if self.backend == "dense":
                scores = [float(value) for value in semantic]
                eligible = [index for index in eligible if scores[index] >= .20]
            else:
                lex_order = sorted(eligible, key=lambda index: (-lexical[index], documents[index].reference))
                dense_order = sorted(eligible, key=lambda index: (-semantic[index], documents[index].reference))
                scores = [0.0] * len(documents)
                for order in (lex_order, dense_order):
                    for rank, index in enumerate(order, 1):
                        scores[index] += 1 / (60 + rank)
                eligible = [index for index in eligible if lexical[index] > 0 or semantic[index] >= .20]
        else:
            scores = lexical
            eligible = [index for index in eligible if scores[index] > 0]
        if not eligible:
            return []
        # Hash features only estimate redundancy; relevance remains BM25/dense/RRF.
        embed(safe_query)
        redundancy_vectors = {index: embed(contents[index]) for index in eligible}
        peak = max(scores[index] for index in eligible) or 1
        selected: list[int] = []
        seen_text: set[str] = set()
        remaining = set(eligible)
        while remaining and len(selected) < limit:
            def mmr(index: int) -> tuple:
                redundancy = max((float(np.dot(redundancy_vectors[index], redundancy_vectors[other])) for other in selected), default=0)
                return (- (.9 * scores[index] / peak - .1 * redundancy), -scores[index], documents[index].reference)
            index = min(remaining, key=mmr)
            remaining.remove(index)
            fingerprint = hashlib.sha256((documents[index].section + "\n" + documents[index].text).encode()).hexdigest()
            if fingerprint not in seen_text:
                seen_text.add(fingerprint)
                selected.append(index)
        return [Hit(documents[index], float(scores[index]), self.backend + "+mmr") for index in selected if documents[index].classification in CLASSIFICATIONS[principal.role]]


def requested_claims(query: str) -> set[str]:
    """Conservative request scope; curated tags do not prove semantic entailment."""
    text = re.sub(r"(?<=[a-z])[-‐‑–](?=[a-z])", " ", _normal(query))
    claims: set[str] = set()
    illustrative_concept = bool(re.search(r"illustrative|internal|synthetic|內部|内部|示意", text)) and not re.search(r"matrix|coefficient|numbers?|values?|percent|calculat|compute|formula|矩陣|矩阵|係數|系数|數值|数值|數字|数字|百分|計算|计算|公式", text)
    if re.search(r"correlation|(?:pca|capital).{0,35}matrix|matrix.{0,35}(?:pca|capital)|相關矩陣|相关矩阵|相關係數|相关系数", text) and not illustrative_concept:
        claims.add("capital.market_correlation_direction" if re.search(r"(?:interest|equity|market).{0,40}(?:up|down|direction)|利率|股票|升息|降息", text) else "capital.correlation_matrix")
    specific_crypto = bool(re.search(r"crypto|加密", text))
    if (re.search(r"prescribed\s+(?:risk\s+)?factors?|stress\s+(?:factors?|percent|rates?)|壓力因子|压力因子", text) and not specific_crypto) or re.search(r"calibrat|校準|校准|mortality|longevity|lapse\s+stress|死亡率|長壽|长寿", text):
        claims.add("capital.risk_factors")
    if re.search(r"(?:calculate|compute|formula|how.{0,20}calculat).{0,35}(?:pca|prescribed capital)|(?:pca|prescribed capital).{0,35}(?:calculat|formula)|(?:計算|计算).{0,12}[資资]本", text):
        claims.add("capital.pca_calculation")
    if re.search(r"matching adjustment|匹配調整|匹配调整", text):
        # Mentioning an announcement/year must not erase a second, unsupported
        # formula or eligibility request in a compound question.
        formula = bool(re.search(r"formula|calculat|compute|calibrat|numerical|percentage|spread|公式|計算|计算|校準|校准|數值|数值|百分比|息差|利差", text))
        eligibility = bool(re.search(r"eligib|qualif|資格|资格|適用|适用", text))
        announcement = bool(re.search(r"announcement|announce|mention|公告|公佈|公布|提及", text))
        if formula or not (announcement or eligibility):
            claims.add("matching_adjustment.formula")
        if eligibility:
            claims.add("matching_adjustment.eligibility")
    if re.search(r"tier.{0,20}(?:\b(?:caps?|limits?)\b|上限|限額|限额)|\b(?:caps?|limits?)\b.{0,20}tier|[一二兩两][級级].{0,10}上限", text):
        claims.add("capital.tier_limits")
    if re.search(r"tier|instrument|subordinat|debt|bonds?|[一二兩两][級级]|工具|債券|债券|次順位|次顺位", text) and re.search(r"eligib|qualif|inclusion|合格|資格|资格|可計入|可计入", text):
        claims.add("capital.tier_instrument_eligibility")
    if re.search(r"loss.given.default|default probability|\blgd\b|\bpd\b|違約損失|违约损失", text):
        claims.add("capital.counterparty_default_calibration")
    if re.search(r"cyber|網絡風險|网络风险", text):
        claims.add("capital.cyber_calibration")
    if re.search(r"discount curve|risk.free curve|\bufr\b|smith.wilson|折現曲線|折现曲线|終極遠期|终极远期", text):
        claims.add("discount_curve.calibration")
    if re.search(r"\bifrs\s*17\b|\bcsm\b|\bgmm\b", text):
        claims.add("ifrs17.measurement")
    if re.search(r"(?<![a-z0-9])tvog(?![a-z0-9])|保證.{0,5}時間價值|保证.{0,5}时间价值", text):
        claims.add("liability.tvog_methodology")
        if re.search(r"proxy|simplif|代理|簡化|简化", text):
            claims.add("liability.tvog_proxy")
        if re.search(r"calculat|compute|formula|numerical|calibrat|scenario count|number of scenarios|公式|計算|计算|數值|数值|校準|校准|幾多條情景|多少條情景|參數|参数|收斂|收敛", text):
            claims.add("liability.tvog_calculation")
    if re.search(r"crypto|加密", text):
        claims.add("capital.crypto_stress")
    if re.search(r"(?<![a-z0-9])cca(?![a-z0-9])|counter\s*cyclical|逆周期|逆週期", text) and re.search(r"bound|limit|range|cap|floor|上下限|範圍|范围|上限|下限", text):
        claims.add("capital.equity_cca_bounds")
        if re.search(r"gazette|notice|憲報|宪报|公告", text) and re.search(r"numerical|numbers?|values?|exact|數字|数字|數值|数值|幾多|多少", text):
            claims.add("capital.equity_cca_notice_values")
    if re.search(r"currency risk|foreign currenc|(?<![a-z])fx(?![a-z])|匯率|汇率|外幣|外币", text) and re.search(r"stress|charge|factor|calibrat|prescribed|壓力|压力|法定|校準|校准", text):
        claims.add("capital.fx_calibration")
    for country in ("macao", "macau", "singapore", "bermuda"):
        if re.search(r"\b" + country + r"\b", text):
            claims.add("jurisdiction." + ("macao" if country == "macau" else country))
    return claims


def evidence_answer(query: str, hits: list[Hit]) -> dict:
    required = requested_claims(query)
    # "Current estimate" is a technical valuation term, not a request for today's
    # consolidated law. Other current-law words in the same query still apply.
    temporal_query = re.sub(r"\b(?:deterministic\s+)?current\s+estimate\b", "technical estimate", query, flags=re.I)
    current_question = bool(re.search(r"\b(current|currently|today|latest|compliant|compliance)\b|現行|當前|当前|最新|合規|合规", temporal_query, re.I))
    today = datetime.now(ZoneInfo("Asia/Hong_Kong")).date()
    query_years = {int(value) for value in re.findall(r"(?<!\d)20\d{2}(?!\d)", _normal(query))}
    named_amendment = bool(re.search(r"amendment|修訂|修订", query, re.I)) and any(
        hit.document.status == "future" and any(value and value.year in query_years
            for value in (hit.document.effective_from, hit.document.published_at)) for hit in hits)
    future_requested = (bool(re.search(r"\b(future|scheduled|will)\b|未來|未来|將.{0,6}生效|将.{0,6}生效|將於|将于|預定|预定", query, re.I)) or named_amendment) and not current_question
    coverage_sources = [hit.document for hit in hits if hit.document.status not in {"superseded"}
        and (future_requested or (hit.document.status != "future" and (hit.document.effective_from is None or hit.document.effective_from <= today)))]
    covered = {tag for document in coverage_sources for tag in getattr(document, "claim_tags", ())}
    if "capital.tier_eligibility_limits" in covered:
        covered.add("capital.tier_limits")
    def current_eligible(document: Document) -> bool:
        return (document.current_consolidated_verified and document.kind == "regulatory" and document.status not in {"future", "superseded", "demo"}
                and (document.effective_from is None or document.effective_from <= today)
                and (document.effective_to is None or today <= document.effective_to) and document.reviewed_at <= today)
    temporal_ok = bool(hits) and all(current_eligible(hit.document) for hit in hits)
    requested_rules = rule_identifiers(query)
    missing_rules = {rule for rule in requested_rules if not any(_rule_match({rule}, hit.document) for hit in hits)}
    normalized_query = _normal(query)
    requested_class = "restricted" if re.search(r"\brestricted\b|restricted_demo|受限|機密", normalized_query) else ("internal" if re.search(r"\binternal\b|internal_demo|內部|内部", normalized_query) else None)
    class_missing = requested_class is not None and not any(hit.document.classification == requested_class for hit in hits)
    identifiers = re.findall(r"(?<![a-z0-9_])[a-z][a-z0-9]*(?:_[a-z0-9]+){2,}(?![a-z0-9_])", normalized_query)
    missing_named = [value for value in identifiers if not any(value in _normal(hit.document.text + " " + hit.document.document_id) for hit in hits)]
    missing = required - covered
    comparison = bool(re.search(r"compar|difference|比較|比较", normalized_query)) and future_requested
    historical_requested = comparison and bool(re.search(r"original|baseline|historical|2024|原始|原版|原有", normalized_query))
    def relevant_version(document: Document) -> bool:
        return not required or bool(required & set(document.claim_tags))
    missing_versions = ["historical_baseline"] if historical_requested and not any(document.status != "future" and document.kind == "regulatory" and document.published_at and document.published_at.year < max(query_years or {today.year}) and relevant_version(document) for document in coverage_sources) else []
    if historical_requested and not any(document.status == "future" and relevant_version(document) for document in coverage_sources):
        missing_versions.append("scheduled_amendment")
    insufficient = not coverage_sources or bool(missing or missing_rules or missing_named or class_missing or missing_versions) or (current_question and not temporal_ok)
    scope = {"requested_claim_tags": sorted(required), "covered_claim_tags": sorted(covered), "missing_claim_tags": sorted(missing),
             "missing_rule_identifiers": sorted(missing_rules), "current_law_requested": current_question, "all_sources_current_verified": temporal_ok,
             "requested_classification": requested_class, "classification_evidence_missing": class_missing, "missing_named_identifiers": missing_named,
             "future_scope_requested": future_requested,
             "missing_evidence_versions": missing_versions,
             "assessment": "Curated claim tags and explicit dates/identifiers; not semantic entailment verification."}
    if not hits:
        answer = "Insufficient verified evidence in the authorized local corpus. No regulatory conclusion can be made; consult the current official rules and a qualified reviewer."
    else:
        lines = []
        for hit in hits:
            document = hit.document
            label = "Regulatory source paraphrase" if document.kind == "regulatory" else "Internal interpretation / demonstration"
            lines.append(f"{label} [{document.reference}] — {document.status}; section: {document.section}: {document.text}\nSource limitation: {document.limitations or 'See source metadata.'}")
        prefix = "Insufficient verified evidence to establish the requested current requirement, specific rule or claim coverage. The following historical/background sources may assist a reviewer:\n\n" if insufficient else ""
        answer = prefix + "\n\n".join(lines)
    return {"status": "insufficient_evidence" if insufficient else "evidence_found", "answer": answer,
            "citations": [hit.to_dict() for hit in hits], "provider": "local-extractive", "commentary": None,
            "retrieval_method": ",".join(sorted({hit.retrieval_method for hit in hits})) or "none", "evidence_scope": scope,
            "limitations": ["Retrieved evidence is not a completeness determination or legal advice.",
                "Dates, sections and versions shown below apply to each source. Review the latest consolidated law before reliance.",
                "Paraphrases are stored; no generated quotation is presented as law.",
                "Lexical/semantic relevance and curated claim coverage do not prove that a source entails an answer."]}
