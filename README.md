# PDF → table extraction with local open-source LLMs

Learning project: ingest PDFs, extract fields into a fixed table schema with an LLM running on a local RTX 3090, and score the results against ground truth.

## Setup

```powershell
py -3.11 -m venv .venv          # any Python 3.11 works (e.g. Anaconda's python.exe)
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Data

| Set | Files | Ground truth | Difficulty |
|---|---|---|---|
| Synthetic digital invoices | `data/synthetic/digital/` (200) | `data/synthetic/ground_truth/invoices.csv`, `line_items.csv`, `json/` | Text layer present; varied layouts, labels, date and number formats |
| Synthetic scanned invoices | `data/synthetic/scanned/` (50, same invoices as digital) | same as above | Image only: needs OCR or a vision model |
| SROIE receipts | `data/sroie/pdf/` (626) | `data/sroie/ground_truth/receipts.csv` | Real scanned receipts; 4 fields: company, address, date, total |

Regenerate:

```powershell
.\.venv\Scripts\python.exe src\generate_invoices.py --n 200 --n-scanned 50 --seed 42
.\.venv\Scripts\python.exe -I src\prepare_sroie.py
```

SROIE source: <https://github.com/zzzDavid/ICDAR-2019-SROIE> (the ICDAR 2019 training set with corrected labels), sparse-cloned into `data/raw/sroie_repo`.
Known gap: `sroie_033` has no total in the original labels.

## Extraction

Runtime: [Ollama](https://ollama.com) (installed with `winget install Ollama.Ollama`), model `qwen2.5:7b` (`ollama pull qwen2.5:7b`).
The schemas live in `src/schemas.py`. Each run writes `runs/<name>/json/*.json` (one per PDF) plus flattened CSV tables. Rerunning skips documents that are already done.

```powershell
.\.venv\Scripts\python.exe src\extract.py --input data\synthetic\digital --schema invoice --run digital_qwen7b
.\.venv\Scripts\python.exe src\evaluate.py --run runs\digital_qwen7b --schema invoice
```

Defaults: prompt `v2`, `--text-mode blocks`, `--retries 1`. Reproduce the original baseline with `--prompt v1 --text-mode lines --retries 0`.

| Run (200 digital invoices, qwen2.5:7b) | Fully right | Header fields all right | Line items all right |
|---|---|---|---|
| `digital_qwen7b`: v1 prompt, line text, no checks | 65.0% | 65.0% | 100% |
| `digital_qwen7b_v2`: v2 prompt, block text, arithmetic checks + 1 retry | 92.0% | 93.0% | 99.0% |

In v2, invoices that still fail an arithmetic check after the retry are marked `needs_review` (2 of 200).

`evaluate.py` prints per-field accuracy and writes `runs/<name>/errors.csv` listing every mismatch.

## Scanned PDFs

Scanned PDFs have no text layer. There are two ways to read them:

- `--text-mode ocr` reads the page image with RapidOCR (`pip install rapidocr_onnxruntime`, CPU), puts the text boxes back into lines, and sends that text to the same text model. The OCR text is saved in each document's JSON (`ocr_text`).
- `--text-mode image` sends the page images to a vision model (`ollama pull qwen2.5vl:7b`).

```powershell
.\.venv\Scripts\python.exe src\extract.py --input data\synthetic\scanned --schema invoice --text-mode ocr --run scanned_ocr_qwen7b
.\.venv\Scripts\python.exe src\extract.py --input data\synthetic\scanned --schema invoice --model qwen2.5vl:7b --text-mode image --num-ctx 16384 --run scanned_vision_qwen7bvl
.\.venv\Scripts\python.exe src\evaluate.py --run runs\digital_qwen7b_v2 --schema invoice --subset data\synthetic\scanned
```

`--subset` scores only the documents that also exist in another folder, so different runs are compared on exactly the same invoices. It writes `errors_<folder>.csv`.

| Same 50 invoices, prompt v2 | Fully right | Header fields all right | Line items all right | Flagged for review | Time per invoice |
|---|---|---|---|---|---|
| Digital PDF text (`digital_qwen7b_v2`) | 90% | 90% | 100% | 0 | ~5 s |
| Scanned → OCR → qwen2.5:7b (`scanned_ocr_qwen7b`) | 32% | 36% | 74% | 10 | ~7 s |
| Scanned → qwen2.5vl:7b vision (`scanned_vision_qwen7bvl`) | 84% | 86% | 98% | 1 | ~7 s |
| Same, with date conversion (`scanned_vision_qwen7bvl_datefix`) | 90% | 92% | 98% | 1 | ~6 s |

### Date conversion

Models sometimes copy a date as printed (`28/05/2024`) instead of writing ISO. `extract.py` now converts any non-ISO date in code after the model answers (`to_iso_date`). All-number dates are read month-first for USD invoices and day-first otherwise, unless one part is over 12. Each record lists what was converted under `date_fixes`. Use `--no-date-fix` to turn this off and reproduce earlier runs.

## SROIE receipts (real scans)

```powershell
.\.venv\Scripts\python.exe src\extract.py --input data\sroie\pdf --schema receipt --model qwen2.5vl:7b --text-mode image --num-ctx 16384 --run sroie_vision_qwen7bvl
.\.venv\Scripts\python.exe src\evaluate.py --run runs\sroie_vision_qwen7bvl --schema receipt
```

| 626 receipts, qwen2.5vl:7b, prompt v2 | company | address | date | total | All 4 right | Time per receipt |
|---|---|---|---|---|---|---|
| Exact | 94.2% | 90.9% | 90.9% | 97.6% | | |
| Fuzzy | 95.8% | 97.6% | 90.9% | 97.6% | 83.1% | ~1.9 s |

46 of the 57 date errors are the right date in the wrong format (e.g. `19/10/2018` instead of `2018-10-19`).

With date conversion (`sroie_vision_qwen7bvl_datefix`): date accuracy is 98.2% (was 90.9%) and **89.8%** of receipts have all 4 fields right (was 83.1%). The 11 remaining date errors are digits misread from faded receipts.

### Company-name rule (prompt v3): no real gain

`--prompt v3` adds a receipt rule: use the registered company name (SDN BHD, S/B, ...) rather than the brand, and leave out registration numbers. For invoices v3 is identical to v2.

| 626 receipts, with date conversion | company wrong | All 4 right |
|---|---|---|
| v2 (`sroie_vision_qwen7bvl_datefix`) | 26 | 89.8% |
| v3 (`sroie_vision_qwen7bvl_v3`) | 26 (3 fixed, 3 newly wrong) | 90.1% |

The +0.3 points is 2 receipts. That's within run-to-run noise from changing the prompt, and the rule was written after looking at these same receipts. Two reasons it didn't help:
- The 7B model mostly ignored the rule (sroie_173 still "DOMINO'S PIZZA", sroie_321 still "FamilyMart").
- The labels are inconsistent: sroie_321 is labeled with the legal company but sroie_322 (same FamilyMart chain) with the brand, and sroie_318 vs sroie_610 label the same company differently. No single rule can match both.

Default stays v2.

## Results database (SQL Server)

Local setup: SQL Server 2025 Developer, ODBC Driver 18 for SQL Server, and `sqlcmd`, all installed with winget. Python connects through SQLAlchemy + pyodbc. The connection comes from one environment variable, so pointing at a network server later only means changing it (`src/config.py`):

```powershell
$env:OCR_DB_URL = "mssql+pyodbc://@localhost/ocr_pipeline?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes"
```

To make it permanent for your Windows user: `[Environment]::SetEnvironmentVariable('OCR_DB_URL', '<url>', 'User')`, then open a new terminal.

When `OCR_DB_URL` is set, `extract.py` writes every document to the database as well as to JSON (`--no-db` turns this off). The database is created automatically. Tables (`src/db.py`):

| Table | One row per |
|---|---|
| `runs` | extraction run (model, model digest, prompt, settings) |
| `documents` | document per run: status, timings, `needs_review`, file fingerprint, input-quality measurements |
| `invoice_headers`, `invoice_line_items`, `receipts` | the extracted tables |
| `document_flags` | reason a document was flagged (`review` = send to a person, `info` = recorded only) |
| `reviews` | field checked by a person |
| `evaluations` | field compared with a correct answer (labelled test data or a review) |
| `baselines` | metric: what "normal" looks like, for outliers and drift |

```powershell
.\.venv\Scripts\python.exe src\load_runs.py                                   # copy existing runs/ into the database
.\.venv\Scripts\python.exe src\evaluate.py --run runs\digital_qwen7b_v2 --schema invoice --db   # store scores
```

## Monitoring without ground truth

New documents have no correct answers, so four layers are combined:

1. **Label-free checks on every document** (`src/monitor.py`):
   - *rules*: required fields, total > 0, valid and plausible dates, due date not before issue date, known currency, arithmetic checks, duplicate file or invoice number
   - *guardrails*: blank page, resolution under 90 dpi, tilt over 5°, blur, more than 3 pages
   - *cross-check*: in image mode the page is also read by OCR. The extracted total must appear on the page, and later pages must not start a new document. This catches answers the model made up, which pass every internal check.
2. **Outliers and drift** against baselines built from validated runs. Robust z-scores per document; PSI per batch (< 0.1 stable, 0.1–0.25 watch, > 0.25 drift). Input-statistic outliers are `info` only: on SROIE, documents with unusual brightness were no more often wrong (8%) than the rest (10%).
3. **Human review** (`src/review.py`): every flagged document plus a random audit sample (5%) of unflagged ones. The audit sample gives an unbiased estimate of live accuracy.
4. **Golden set**: rerun labelled test data after any model or prompt change and compare with the stored scores.

```powershell
.\.venv\Scripts\python.exe src\monitor.py build-baseline --runs digital_qwen7b_v2 scanned_vision_qwen7bvl_datefix scanned_ocr_qwen7b sroie_vision_qwen7bvl_datefix
.\.venv\Scripts\python.exe src\monitor.py drift --run <run>
.\.venv\Scripts\python.exe src\review.py export --run <run>          # -> reviews\queue_<run>_<date>.csv
.\.venv\Scripts\python.exe src\review.py import reviews\queue_<run>_<date>.csv
```

Reviewers change `corrected_value` where a value is wrong and put their name in `reviewer` on every row they checked. Rows without a reviewer are ignored.

### Unusual-scan test

`src/make_anomalies.py generate` makes 20 normal scans and 36 unusual ones (3 each of blank, upside-down, heavy tilt, extreme blur, very dark, very faded, heavy noise, cropped, ~45 dpi, not an invoice, two invoices merged, exact duplicate). These are new invoices that aren't in any baseline.

| `anomaly_test_vision` (qwen2.5vl:7b) | Result |
|---|---|
| Unusual documents handled (flagged, or extracted fully correctly anyway) | **35 of 36 (97%)** |
| Normal documents falsely flagged | **0 of 20** |
| Missed | 1 noisy invoice with a minor error (it carried 3 `info` outlier flags) |

Before the OCR cross-check and the blur guardrail, 28 of 36 were handled: cropped and merged files passed every internal check.

## Dashboard

```powershell
.\.venv\Scripts\python.exe src\report.py        # -> reports\dashboard_<date>.html
```

One self-contained HTML file (works offline; regenerate to refresh). It covers:
- overview numbers
- runs, with flag rates
- flags by reason
- accuracy by field (heatmap) and by document
- the review loop: audit vs flagged, with 95% confidence intervals
- drift per metric, outliers, and the unusual-scan test

Tables sort on click, and a run selector filters them.

## Moving to a separate GPU server

- `OLLAMA_URL` (e.g. `http://gpu-server:11434/api/chat`) and `OCR_DB_URL` are the only settings that change.
- Each run records the model's digest. `requirements.txt` pins package versions.
- `extract.py` exits with an error code if every document fails (e.g. Ollama unreachable), so a scheduler notices.

## Target schema (synthetic invoices)

- **invoices**: invoice_id, invoice_number, invoice_date (ISO), due_date (ISO), vendor_name, vendor_address, customer_name, customer_address, currency (ISO 4217), subtotal, tax_rate, tax_amount, shipping, total
- **line_items**: invoice_id, line_no, description, quantity, unit_price, amount

## License

Code: MIT (see LICENSE). The SROIE receipt dataset is not included here; it has its own terms of use (ICDAR 2019 SROIE).
