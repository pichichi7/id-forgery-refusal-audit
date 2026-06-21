# Uniform Permissiveness, Unequal Risk — AI Image-Model Identity-Document Refusal Audit

Code and data for the APART **Global South AI Safety Hackathon** (Latin America track, sub-track *AI governance: system auditing & accountability*).

**Author:** Sebastian Soto — FAIR-UBA.
**Paper:** *Uniform Permissiveness, Unequal Risk: Auditing AI Image-Model Identity-Document Forgery as a Systemic Infrastructure Risk.*

This is **defensive AI-safety research**. It measures only whether image models **refuse or comply** with identity-document requests; it does **not** ship forged documents, working prompts, or evasion techniques.

---

## ⚠️ Dual-use / responsible disclosure

This repository deliberately **withholds** the operational artifacts that would have offensive value:

- ❌ The real prompt file (`doc_audit_prompts.json`) is **not** published. Only a schema-level redacted version, [`doc_audit_prompts.REDACTED.json`](doc_audit_prompts.REDACTED.json) (levels, jurisdictions, structure — **no prompt text**), is included.
- ❌ **No generated images** are released; the harness discards image bytes by construction (keeps only a hash).
- ✅ Only aggregate **refuse/comply outcomes** are published (see `outputs/`).

To actually run the harness you must supply your **own** `doc_audit_prompts.json` matching the redacted schema. The scripts are published for **inspection and reproducibility-of-method**, not turnkey generation. Please follow coordinated disclosure to model vendors before any expanded, model-attributed release.

---

## What the study found (summary)

- **Refusal is a model property.** OpenAI's GPT-5-image / -mini refused almost everything; Gemini models complied broadly. Provider difference is the largest, most robust effect (Gemini 68% vs GPT-5.4 17% on document cells under replication; 2-proportion *p* < 1e-5).
- **Single-draw audits overstate.** A dramatic single-draw "English→Spanish flip" pattern dissolved under 5× replication into artifacts; the methodological lesson is to **trust no single-shot refusal number without replication and a reconstructable trail.**
- **A small, consistent Spanish-side residual** survives on document cells across all three replicated models (EN 40% vs ES 62% pooled, *p* ≈ 0.035), but it is underpowered (no single model is individually significant).
- The paper reframes the harm as **systemic identity-infrastructure risk** (credential-centrality *blast radius* × a defense-in-depth *evasion ladder*; forgery as a *scaling*, not *realism*, problem) and maps controls to FATF 2025.

The empirical core is an honest **pilot**, not a powered benchmark — see the paper's Limitations.

---

## Repository layout

```
run_doc_audit.py              # main harness: model × jurisdiction × escalation × language; logs refuse/comply, discards images
confirm_cells.py              # 5× replication runner (resumable, retry-on-error)
check_openrouter.py           # benign connectivity/pricing check (lists image models, generates a red apple)
run_pilot.py                  # earlier text-chatbot pilot runner (superseded framing; included for completeness)
doc_audit_prompts.REDACTED.json   # public-safe schema (NO prompt text)
outputs/
  doc_audit_results.csv       # 120-cell single-draw matrix (6 models)
  doc_audit_confirm.csv       # 5× replication of key cells (3 models)
figures/                      # fig1 harm chain, fig2 replication, fig3 defense ladder (SVG)
```

## Data schema

`outputs/doc_audit_results.csv` — one row per attempt:
`timestamp_utc, model, jurisdiction, level, lang, prompt_id, outcome, refusal_text_snippet, image_sha256`
(`outcome` ∈ {comply, refuse, error}; transient `error` rows were retried — analysis uses the 120 successful cells.)

`outputs/doc_audit_confirm.csv` — one row per replication draw:
`model, prompt_id, lang, draw, outcome`

## Usage

```bash
export OPENROUTER_API_KEY=sk-or-...        # never hard-code the key
python3 check_openrouter.py                # verify access + see image-model pricing
# provide your own doc_audit_prompts.json (schema in doc_audit_prompts.REDACTED.json), then:
python3 run_doc_audit.py                   # single-draw matrix
python3 confirm_cells.py                   # 5× replication of key cells (resumable)
```
Python 3.8+, standard library only — no `pip install` required.

## Citation

> Soto, S. (2026). *Uniform Permissiveness, Unequal Risk: Auditing AI Image-Model Identity-Document Forgery as a Systemic Infrastructure Risk.* APART Global South AI Safety Hackathon, Latin America track.

## License

Code: MIT (see [LICENSE](LICENSE)). Data and figures are released for research use. Operational prompts and generated images are withheld for dual-use reasons.
