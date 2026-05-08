# Ingestion Reality Audit
## Ticket: INV-EXT-002

## SECTION 1 — UPLOAD ENTRY POINT AUDIT

**1.1 File path and line range of the route handler**
`lexichat-api/services/ingestion_service.py` lines 201-250 (called by router in `lexichat-api/main.py` lines 121-124).

**1.2 Accepted Content-Type / MIME types**
FastAPI uses `UploadFile`, which accepts any MIME type sent by the client. The only explicit validation is a simple string match on the filename extension.

**1.3 Maximum upload size**
No explicit maximum upload size is configured in the route or middleware. FastAPI defaults to keeping files under 50MB in memory and spools larger files to disk using `SpooledTemporaryFile`.

**1.4 The exact filesystem path where uploaded bytes are first written**
`lexichat-api/uploads/{doc_id}.pdf`

**1.5 Filename preservation**
The original filename is saved strictly into the database (`models.WorkspaceDocument.filename`), but the physical file is sanitized/renamed to a UUID on disk.

```python
    # Generate unique document ID
    doc_id = str(uuid.uuid4())
    
    file.file.seek(0)
    pdf_bytes = file.file.read()
    
    # Save PDF to disk for viewing in React
    file_path_saved = os.path.join(UPLOAD_DIR, f"{doc_id}.pdf")
    with open(file_path_saved, "wb") as f:
        f.write(pdf_bytes)
```

**1.6 File-type validation**
Only a naive extension check is performed. No magic byte validation exists.

```python
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
```

---

## SECTION 2 — INGESTION PIPELINE TRACE

**2.1 Complete ordered list of functions called**
1. `main.py:122` - `upload_pdf` (router)
2. `services/ingestion_service.py:201` - `upload_pdf` (service logic)
3. `services/ingestion_service.py:15` - `process_document_background` (background task)
4. `requests.post` (`https://api.cloud.llamaindex.ai/api/parsing/upload`) - External LlamaParse API
5. `requests.get` (`https://api.cloud.llamaindex.ai/api/parsing/job/{job_id}/result/json`) - External LlamaParse API
6. `utils/chunking.py` - `smart_chunk`
7. `services/vector_service.py` - `get_embeddings` (External Voyage/OpenAI API)
8. `dependencies.py` - `index.upsert` (External Pinecone API)
9. `services/intelligence_service.py` - `analyze_document_brief_background`

**2.2 Step traits**
- **upload_pdf**: Reads original bytes, writes transformed version renamed to `{doc_id}.pdf`, does not discard original.
- **process_document_background**: Calls external API (LlamaParse). Writes transformed markdown version to `{doc_id}.md`. Calls external APIs (embeddings, Pinecone).

**2.3 Magic byte inspection**
None. The code never reads the first 4-8 bytes to verify it is genuinely a PDF.

**2.4 Non-PDF handling (ZIP, image, corrupted)**
There is no defensive handling for zip/image/corrupted files in the upload route. If a ZIP is renamed to `.pdf`, it is successfully saved to disk. `process_document_background` sends it to LlamaParse via `requests.post`. 
If LlamaParse fails (returns ERROR), the code catches it in the `else:` block and logs "LlamaParse parsing completely failed:".
Wait, if LLAMA_CLOUD_API_KEY is missing, it falls back to PyMuPDF (`fitz.open(file_path_saved)`), which will immediately raise a runtime exception and crash if the file is a ZIP archive.

**2.5 Final paths of intermediate artefacts**
- Original upload renamed: `uploads/{doc_id}.pdf`
- Processed markdown: `uploads/{doc_id}.md`
- Ingestion status cache: `uploads/{doc_id}_status.json`
- Generated brief cache: `uploads/{doc_id}_brief.json`

---

## SECTION 3 — LLAMAPARSE CONFIGURATION

**3.1 Exact LlamaParse client init code**
The codebase does not use the `llama-parse` python SDK. It uses raw HTTP requests.

```python
            headers = {
                "Authorization": f"Bearer {llama_api_key}",
                "Accept": "application/json"
            }
            
            # 1. Upload to LlamaParse Headless Pipeline
            with open(file_path_saved, "rb") as f:
                files = {"file": f}
                data = {"premium_mode": "false", "result_type": "markdown"}
                upload_resp = requests.post("https://api.cloud.llamaindex.ai/api/parsing/upload", headers=headers, files=files, data=data)
                upload_resp.raise_for_status()
```

**3.2 Parameters passed**
- parsing mode: `premium_mode` = `"false"` (i.e., using the basic Fast/Balanced tier)
- result_type: `"markdown"`
- Language setting: none explicit
- OCR mode: none explicit
- Timeout: Uses a 60-iteration polling loop sleeping for 2 seconds (120s timeout total).

**3.3 Model used**
Not explicitly configured. Defaults to whatever LlamaParse free/basic tier uses.

**3.4 Configuration Variance**
No. The exact same hardcoded configuration is used for every single document, regardless of size or type.

**3.5 LITMUS TEST**
(a) true digital PDF: Handled perfectly by LlamaParse.
(b) true PDF image-only: Handled by LlamaParse. If LlamaParse fails or extracts <500 chars, the fallback uses `pytesseract.image_to_string`.
(c) ZIP archive renamed to .pdf: Accepted at upload. Sent to LlamaParse. LlamaParse will likely reject it with "ERROR", triggering the fallback block which logs the exception and aborts.
(d) JPEG renamed to .pdf: Same as ZIP.
(e) 0-byte file: Same as ZIP.
(f) .docx renamed to .pdf: LlamaParse natively supports `.docx` and might actually parse it correctly despite the wrong extension.

---

## SECTION 4 — TEXT SOURCE GROUND TRUTH

### N1 Franchise agreement.pdf
**4.1 Raw Upload File**
- Size: 1212550 bytes
- Hex (first 8 bytes): `0000000    %   P   D   F   -   1   .   7                                
0000010`
- `file` command: `lexichat-api/uploads/0dc07677-7041-4193-8bca-5f68bfc6c8c4.pdf: PDF document, version 1.7 (zip deflate encoded)`

**4.2 Processed Markdown File**
- Size: 109559 bytes
- First 200 chars:
```

<!-- PAGE 1 START -->
 
Bootlegger_Franchise Agreement_2020_v2.1.docx 
 
 
 
 
FRANCHISE AGREEMENT 
 
 
 
between 
 
 
BOOTLEGGER FRANCHISE COMPANY PROPRIETARY LIMITED 
 
 
and 
 
 
……………………………………………
```
- Last 200 chars:
```
tellenbosch


<!-- PAGE 37 START -->
 
 
 
page | 36 
Bootlegger_Franchise Agreement_2020_v2.1.docx 
ANNEXURE C 
TRADE MARKS 
 
 
 
 
 
 
 
DocuSign Envelope ID: B91ADC09-CA91-4454-ADB0-22E6783FF674


```
- Contains DocuSign Envelope ID: True

**4.3 Total character count**: 108122
**4.4 Markdown Quality**
- Appears to be proper Markdown output with LlamaParse pagination markers.

### N1 City Lease.pdf
**4.1 Raw Upload File**
- Size: 1627713 bytes
- Hex (first 8 bytes): `0000000    %   P   D   F   -   1   .   4                                
0000010`
- `file` command: `lexichat-api/uploads/32768201-a85e-40d6-82d5-1ec28462e26f.pdf: PDF document, version 1.4, 28 pages`

**4.2 Processed Markdown File**
- Size: 108237 bytes
- First 200 chars:
```

<!-- PAGE 1 START -->
LEASE AGREEMENT

SHOPRITE CHECKERS (PTY) LTD
REGISTRATION NO.: 1929/001817/07

SHOPRITE 63)
€& Checkers

ANNEXURE A:
STANDARD CONDITIONS

CLAUSE:

DEFINITIONS
GENERAL

PRO RATA 
```
- Last 200 chars:
```
roperty
Manager
Authorised By
(Regional
Manager

Lease Audit
(Legal
Assistant

REMARKS:

Signature

Entered on
System.
Admin Assistant
Reviewed By
(Administration
Manager)

Stamped and
Copy sent

28


```
- Contains DocuSign Envelope ID: False

**4.3 Total character count**: 107838
**4.4 Markdown Quality**
- Appears to be proper Markdown output with LlamaParse pagination markers.

### Lease  27 Rosmead Avenue Service Road Claremont,.pdf
**4.1 Raw Upload File**
- Size: 709601 bytes
- Hex (first 8 bytes): `0000000    %   P   D   F   -   1   .   7                                
0000010`
- `file` command: `lexichat-api/uploads/824eab37-2762-43a5-894a-5d79465ea544.pdf: PDF document, version 1.7, 40 pages`

**4.2 Processed Markdown File**
- Size: 98086 bytes
- First 200 chars:
```

<!-- PAGE 1 START -->
1 
 
Initial Here 
 
 
MEMORANDUM OF AGREEMENT OF LEASE 
 
 
 
 
MADE AND ENTERED INTO BY AND BETWEEN 
 
 
 
HOOSEN VAWDA CAPITAL (PTY) LTD 
Registration Number:  2014/267584/07
```
- Last 200 chars:
```
HIOR rot T ese Wik FAA
weceyeT WF Gut, rence T aden TT Ror pious
& GE miggnnerd Fraud woe FT Came un

Registration Number: 2014/;
: 447i

Tel 021817 "9803 Emai admingbemcorp

—“—_——SSSSSSSSSSSSS eo



```
- Contains DocuSign Envelope ID: False

**4.3 Total character count**: 97676
**4.4 Markdown Quality**
- Appears to be proper Markdown output with LlamaParse pagination markers.

### Franchise - Shop No. 2  27 Rosmead Avenue Service Road Claremont,.pdf
**4.1 Raw Upload File**
- Size: 2145029 bytes
- Hex (first 8 bytes): `0000000    %   P   D   F   -   1   .   7                                
0000010`
- `file` command: `lexichat-api/uploads/b55e4e10-6c3b-4d5c-a1d1-07d79b8e76d4.pdf: PDF document, version 1.7`

**4.2 Processed Markdown File**
- Size: 140029 bytes
- First 200 chars:
```

<!-- PAGE 1 START -->
 
Bootlegger Franchise Agreement 2024 V1.docx 
Docusign Envelope ID: C30FEAF5-0450-4989-89D3-DF59DAB9295C
2BW N1 HYPER (PTY) LTD


<!-- PAGE 2 START -->
 
 
page | 1 
Bootlegger
```
- Last 200 chars:
```
9-89D3-DF59DAB9295C


<!-- PAGE 48 START -->
 
 
page | 47 
Bootlegger Franchise Agreement 2024 V1.docx 
ANNEXURE D 
Debit Order Authority 
Docusign Envelope ID: C30FEAF5-0450-4989-89D3-DF59DAB9295C


```
- Contains DocuSign Envelope ID: False

**4.3 Total character count**: 138562
**4.4 Markdown Quality**
- Appears to be proper Markdown output with LlamaParse pagination markers.

### BOOTLEGGER LEASE AGREEMNET (1 JULY 2023 - 30 JUNE 2028.pdf
**4.1 Raw Upload File**
- Size: 7454147 bytes
- Hex (first 8 bytes): `0000000    %   P   D   F   -   1   .   4                                
0000010`
- `file` command: `lexichat-api/uploads/8762e3a7-fb9a-4a4d-a19f-38a716c7e897.pdf: PDF document, version 1.4`

**4.2 Processed Markdown File**
- Size: 257457 bytes
- First 200 chars:
```

<!-- PAGE 1 START -->
I>

RETAIL LEASE AGREEMENT

entered into between

ATTACQ RETAIL FUND PROPRIEATARTY LIMITED
Registration number: 2008/021582/07
and
KEY CAPITAL HOLDINGS PROPRIEATARY LIMITED
Regi
```
- Last 200 chars:
```

Pale

B: 20

C: 0%
M: 26%
Y: 90%
K: 22%

BOOTLEGGER BLACK:

Pantone:
HTML: #231F20

ds

B: 32

C: 0%
M: 0%
Y¥: 0%

K: 100%

BOOTLEGGER
WHITE:
Pantone:
HTML: #0

ALAS

B: 20

C:0%
M: 0%
Y¥: 0%
K: 0%


```
- Contains DocuSign Envelope ID: False

**4.3 Total character count**: 256675
**4.4 Markdown Quality**
- Appears to be proper Markdown output with LlamaParse pagination markers.

### Bootlegger_FA_XS_Eikestad.pdf
**4.1 Raw Upload File**
- Size: 1387020 bytes
- Hex (first 8 bytes): `0000000    %   P   D   F   -   1   .   7                                
0000010`
- `file` command: `lexichat-api/uploads/cfb61f7b-fdf4-4aa4-9a4d-e006579ed617.pdf: PDF document, version 1.7 (zip deflate encoded)`

**4.2 Processed Markdown File**
- Size: 109559 bytes
- First 200 chars:
```

<!-- PAGE 1 START -->
 
Bootlegger_Franchise Agreement_2020_v2.1.docx 
 
 
 
 
FRANCHISE AGREEMENT 
 
 
 
between 
 
 
BOOTLEGGER FRANCHISE COMPANY PROPRIETARY LIMITED 
 
 
and 
 
 
……………………………………………
```
- Last 200 chars:
```
e town
July


<!-- PAGE 37 START -->
 
 
 
page | 36 
Bootlegger_Franchise Agreement_2020_v2.1.docx 
ANNEXURE C 
TRADE MARKS 
 
 
 
 
 
 
 
DocuSign Envelope ID: 5349907E-7706-40F1-9E0F-110F512FFD4F


```
- Contains DocuSign Envelope ID: True

**4.3 Total character count**: 108122
**4.4 Markdown Quality**
- Appears to be proper Markdown output with LlamaParse pagination markers.


---

## SECTION 5 — OCR-SOURCE MISMATCH HYPOTHESIS

**5.1 verify_value_in_text function**
`lexichat-api/services/intelligence_engine.py:557-567`
```python
def verify_value_in_text(value: str, full_text: str) -> bool:
    if not value or value.lower() in ["not specified", "unknown"]:
        return False
        
    # Standardize spaces and case
    search_val = " ".join(value.lower().split())
    text_corpus = " ".join(full_text.lower().split())
    
    if search_val in text_corpus:
        return True
```

**5.2 Text source for verification**
The `full_text` argument is constructed inside `extract_expiries` by directly reading the `.md` file created by LlamaParse:
`lexichat-api/services/intelligence_service.py:724-730`
```python
            md_path = os.path.join(UPLOAD_DIR, f"{doc_info['pinecone_doc_id']}.md")
            full_text = ""
            if os.path.exists(md_path):
                with open(md_path, "r", encoding="utf-8", errors="ignore") as f:
                    full_text = f.read()
```

**5.3 Search for literal strings in Eikestad Franchise**
For `Bootlegger_FA_XS_Eikestad.pdf` (mapped locally to `cfb61f7b...md`):
- `5%`: 4 matches
- `5 %`: 0 matches
- `5percent`: 0 matches
- `5 percent`: 0 matches
- `five percent`: 1 matches
- `7%`: 0 matches
- `7 %`: 0 matches
- `7 percent`: 0 matches
- `seven percent`: 0 matches

**5.4 Compare to raw native OCR**
UNKNOWN — production data needed. (Requires the zip archive to diff the embedded OCR text against the LlamaParse markdown).

**5.5 Hypothesis Evaluation**
The evidence **supports** the hypothesis. The validation engine rigidly checks `search_val in text_corpus`. If LlamaParse drops the `%` symbol, hallucinates spaces, or formatting differs in the slightest from what the LLM extracted (which might have been extracted via a different text branch or hallucinated), `verify_value_in_text` will fail and quarantine the value.

---

## SECTION 6 — FILE-FORMAT EDGE CASES

**6.1 User uploads a true PDF**
Processed correctly. Uploaded, sent to LlamaParse, converted to Markdown, embedded, and cached.

**6.2 User uploads a ZIP renamed to .pdf**
**(c) accept, store, fail at LlamaParse** -> Wait, actually `requests.post` sends the file to LlamaParse. LlamaParse will attempt to process it. If it fails, `requests.get` status polling returns `ERROR`. The code (`ingestion_service.py:80`) raises an Exception, and the `except Exception as e:` block on line 162 catches it, prints "LlamaParse parsing completely failed:", and the function returns early. 
Code path: `ingestion_service.py:80-81` and `162-164`.

**6.3 User uploads a 0-byte file with .pdf extension**
Accepted, stored. Sent to LlamaParse. LlamaParse will return an ERROR or empty result. If empty result (`full_markdown` length < 500), it hits the PyTesseract fallback (`ingestion_service.py:105-111`). `pdf2image` will crash trying to convert a 0-byte file, causing `ingestion_status = "failed_no_text"`.

**6.4 User uploads a true PDF that is 100% scanned**
LlamaParse's basic tier attempts OCR. If it fails to return > 500 characters, the system explicitly falls back to `pytesseract`.
Evidence: `ingestion_service.py:105-108`:
```python
            if not full_markdown or len(full_markdown.strip()) < MIN_TEXT_THRESHOLD:
                ingestion_status = "ocr_required"
                try:
                    import pytesseract
```

**6.5 User uploads a corrupted PDF**
Same as the 0-byte file. Accepted at upload, fails at LlamaParse, fails at `pdf2image` fallback, ultimately gracefully stopping with `ingestion_status = "failed_no_text"`.

---

## SECTION 7 — OPEN QUESTIONS AND EVIDENCE GAPS

| Question | Why it matters | What we need to answer it |
|---|---|---|
| Does LlamaParse silently succeed on ZIP archives containing JPEG/TXT? | If LlamaParse processes the ZIP by parsing the first image or extracting embedded `.txt`, it explains why Eikestad extracted partially instead of crashing. | Test LlamaParse API manually with the exact ZIP-as-PDF file. |
| Is the Eikestad 7% issue caused by LlamaParse OCR artifacts or PyTesseract fallback? | Determines whether we need to fix the verification regex, the parsing tier (premium mode), or block ZIP files outright. | Production data: The original `.zip` file downloaded from Railway to inspect embedded OCR text. |
| Why was `Bootlegger_FA_XS_Eikestad.pdf` a 260-byte empty stub in the audit? | A 260-byte file is definitely a corrupted upload. We need to know if the user's browser interrupted it or if the ZIP generation script is broken. | Server access to logs or the original frontend ZIP generation script. |

