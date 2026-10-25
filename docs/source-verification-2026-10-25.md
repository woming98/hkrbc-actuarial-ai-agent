# Primary-source verification, 25 October 2026

This supplement upgrades selected evidence from search-index visibility to inspected official document bytes. It adds **12 short researcher paraphrases**: eight original-law baselines and four future amendment records. It does not certify the present consolidated law. The existing 13-record seed was not edited.

The distributed outputs are [the supplementary records](../data/documents/verified_supplement.json) and [the source register](../data/documents/source_register.json). The register holds access outcomes, rights notes, checksums and page checks. Raw source material remains in the ignored `runtime/source-cache/` directory and must be excluded from release archives, even when the archive tool does not honor `.gitignore`.

## Independently downloaded documents

| Source | Actual response | SHA256 of downloaded file bytes |
| --- | --- | --- |
| [Original L.N. 62 of 2024, official LegCo PDF](https://www.legco.gov.hk/yr2024/english/subleg/negative/2024ln062-e.pdf) | HTTP 200, application/pdf; 2,346,958 bytes; 270 PDF pages | `ecca2bbe8b256ca821836b18343e7e6ae977da1ad6bc448d2e6e31df979180d3` |
| [L.N. 58 of 2026, official LegCo PDF](https://www.legco.gov.hk/yr2026/english/hc/sub_leg/sc04/papers/2026ln058-e.pdf) | HTTP 200, application/pdf; 2,208,297 bytes; 59 PDF pages | `e8999c31776b8af3389a9b9107cec1c8c2a30c8c7bcab3e0cca2616d37f31b06` |

Both files were retrieved on 2026-10-25 using macOS `/usr/bin/curl` with its normal certificate verification. Certificate validation was never disabled. The 2026 PDF URL came from the actual L.N. 58 anchor in the downloaded [LegCo subcommittee agenda](https://www.legco.gov.hk/yr2026/english/hc/sub_leg/sc04/agenda/sc0420260618.htm).

Relevant English operative pages were extracted and visually inspected, including headings and printed Gazette locators. Poppler rendering reported a missing Adobe-CNS1 language pack for the Chinese half of the spreads; MuPDF English crop-box rendering was therefore used for the checks. No Chinese-text verification is claimed. The PDF byte hashes cover the complete downloaded files; the register's separate page-text hashes cover only extracted relevant English text.

## Supplement coverage and boundaries

The original-law records cover rules 3, 4, 6, 7 and 19, plus Schedule 7 Table 2. Each record's `source_page` is a **one-based PDF page integer**. Its `section` provides the precise provision and printed Gazette locator; multi-page ranges appear in the provenance and register.

Tags distinguish numeric tier limits from instrument eligibility. TVOG evidence describes the specified method and conditional proxy, without supplying an implementation or calibration. The correlation record covers Table 2's four-module matrix; it supplies no sub-risk capital amounts or complete PCA calculation. Inspected market sub-risk pages were not turned into a complete market-matrix record.

The 2026 records concern actual operative amendment text, rather than the consultation draft or a summary announcement. Rule 1 specifies **31 December 2026**. The other records pinpoint rule 14(1), rule 22(2) and added rule 85A(1)(a). All four carry `status: future` and the scheduled effective date; they must not be applied as operative on 25 October 2026. The actual amendment text supplies the matrix, countercyclical-bound and crypto-stress changes described in those narrowly scoped records. It does not establish a verified subsequent Gazette value for the future countercyclical bounds. [Source: L.N. 58 of 2026](https://www.legco.gov.hk/yr2026/english/hc/sub_leg/sc04/papers/2026ln058-e.pdf).

Every record has `current_consolidated_verified: false`. Later instruments, the full amendment history, negative-vetting outcomes and insurer-specific approvals or relaxations were not exhaustively checked. The original commencement provision is conditional; the new baseline records leave `effective_from` unset instead of pretending their inspected sections independently establish a calendar commencement date.

## Access failures and misleading success responses

- Direct requests to the [IA original PDF](https://www.ia.org.hk/en/legislative_framework/overview/files/es22024281862.pdf), IA Gazette index and IA legal-information page returned HTTP 403. They were not treated as actual downloaded source text.
- Python HTTPS requests to LegCo failed issuer-chain validation with both the default and certifi CA bundles. The same official sources downloaded successfully with macOS curl's standard trust. The register preserves these as client/method-specific failures alongside successful attempts.
- The [legacy Gazette PDF URL](https://www.gld.gov.hk/egazette/pdf/20242818/es22024281862.pdf) returned HTTP 200 after redirecting to the new Gazette homepage. Its cached HTML checksum is explicitly **not a legislation checksum**.
- The [current e-Legislation Cap. 41R entry](https://www.elegislation.gov.hk/hk/cap41R) returned configuration-check HTML. HTTP 200 did not provide the current consolidated rules.
- The new Gazette search route returned an Important Notices acceptance screen. This was not recorded as a successful notice search.
- Initial sandbox DNS failure is recorded separately from remote HTTP refusal. No search-index snippet is described as a downloaded PDF.

## Rights and distribution

The actual downloaded [LegCo copyright policy](https://www.legco.gov.hk/en/general/disclaimer.html), paragraphs 1-3, describes conditional personal/internal non-commercial copying, accuracy and attribution requirements, and separate third-party permissions. It is not a public open licence; the presence of a government Gazette PDF on LegCo does not establish that LegCo owns all underlying rights.

The actual downloaded [Gazette Important Notices](https://egazette.gld.gov.hk/en/important-notices), Copyright Notice, requires prior written government authorization for public reproduction, adaptation, distribution or dissemination. The [IA legal-information page](https://www.ia.org.hk/en/legal_information.html) could only be reviewed through official-domain indexed text, which similarly reserves public-reproduction rights; its direct access failed and no page-byte checksum is asserted.

The cache is retained locally for this research verification, with attribution and provenance. No public-redistribution permission for source PDFs, screenshots, full text or snapshots is asserted. Distributed content comprises small original paraphrases, exact source links, locators and metadata. Rights-policy observations are not a legal opinion or permission grant; a full-text commercial corpus would need a separate rights assessment.

## Verification performed

- Validated all 12 supplementary records against the project's `Document` schema.
- Recomputed all eight stored cache-file hashes and matched them to the register.
- Passed 42 anchor-presence assertions against actual extracted source pages, alongside visual checks. These are provenance checks, not proof that every legal nuance is encoded in the paraphrases.
- Ingested all 12 records into a separate local validation database; all were visible to the authorized administrator.
- Confirmed the original seed still hashes to `b84c377c10c371a5419a94451f8f650b318bf3b3c1116aca9079dc32a293b3ce`.

Reproduce byte hashes from the downloaded files before relying on the register. A hash identifies the retrieved bytes; it does not prove legal currency, provenance by itself, completeness or permission to redistribute.
