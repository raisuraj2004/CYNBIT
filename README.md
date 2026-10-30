# BitElevate Path Finder

A secure proof of concept for adaptive student-track recommendations. Students
describe their education, known tools, interests, availability, goal, and
background; the app ranks all 16 catalogue tracks, proposes a short roadmap, and
suggests a first task.

The assessment brief says BitElevate is a student training program run by
Cynbit Technologies in Jaipur and lists 16 tracks. Those company/program
statements are treated here as **claimed by Cynbit** and were not independently
verified because no public-page URL was supplied. No private Cynbit material or
real student data is used. The track descriptions and skills are a small,
synthetic catalogue for this proof of concept, not official Cynbit curriculum.

## Features

- Streamlit form with Pydantic v2 validation, control-character cleanup, size
  limits, and a character allowlist for tool/language names.
- TF-IDF text similarity blended with transparent skill, interest, goal,
  education, and weekly-time weights.
- Optional Gemini 2.5 Flash recommendation adapter; Gemini receives only the
  sanitized profile and top five catalogue candidates, and must return strict
  schema-valid JSON with an allowlisted track ID.
- A deterministic local fallback works without an API key and is used on
  provider failures or invalid output after one retry.
- SQLite persistence, consent controls, hashed session/IP rate limits,
  recommendation deletion by UUID, and consent-based optional feedback.
- No names, emails, phone numbers, or free-text profile content are written to
  the recommendations table. Operational rate-limit hashes remain stored for
  up to 24 hours.

## Setup (Python 3.11)

The project targets Python 3.11 (`.python-version`). In PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python seed.py
streamlit run app.py
```

To use Gemini, set the key in the process environment; leaving it unset keeps
the app in fallback mode:

```powershell
$env:GOOGLE_API_KEY = "your-key"
# Optional:
$env:GEMINI_MODEL = "gemini-2.5-flash"
# Optional SQLite path:
$env:BIT_ELEVATE_DB_PATH = "data/pathfinder.sqlite3"
streamlit run app.py
```

Do not put real keys in source files or commit `.env`; `.env.example` contains
only variable names. The UI asks for separate consent before sending a profile
to Gemini and before storing a recommendation. When “Don't store my
recommendation or profile” is enabled (the default), the recommendation and
profile are not persisted; hashed operational rate-limit counters are still
written to SQLite and are disclosed in the UI.

For production, deploy only behind HTTPS (for example Streamlit Community
Cloud); this local-development server does not itself terminate TLS. Debug
details are disabled in `.streamlit/config.toml`.

## Tests and evaluation

```powershell
python -m pytest -q
python eval\run_eval.py
```

The evaluation runner uses 20 synthetic profiles and manually assigned labels.
To explicitly compare against Gemini, configure `GOOGLE_API_KEY` and run:

```powershell
python eval\run_eval.py --llm
```

That option sends only the synthetic evaluation profiles to Gemini and
consumes the same persisted daily LLM-attempt budget as the app.

Security/dependency checks:

```powershell
pip-audit -r requirements.txt
detect-secrets scan
git --no-pager log --all --oneline
```

The local history was checked before any push; no push was performed. Review
any scanner findings before publishing.
The pinned dependency audit reported no known vulnerabilities after updating
Streamlit, Pillow, and pytest to compatible patched releases.

## Evaluation snapshot

Measured with `python eval\run_eval.py` on the local Windows/Python 3.11.13
environment:

| Metric | Result |
| --- | ---: |
| Synthetic profiles | 20 |
| Fallback top-1 accuracy | 100.0% |
| Fallback top-3 accuracy | 100.0% |
| Fallback JSON validity | 100.0% |
| Average local fallback latency | 21.18 ms |
| Prompt-injection cases passed | 6/6 (100.0%) |
| Live Gemini comparison | Not run; no API key configured |

These are measurements on the included synthetic fixtures only. The live LLM
accuracy, JSON validity, and latency are **not measured**.

## Limitations

- Only 20 synthetic profiles are included; they are not representative of
  students or validated against outcomes.
- The correct-track labels were assigned by one person and are subjective.
- There is no real student data, official Cynbit curriculum, or verified
  Cynbit program data in this repository.
- Retrieval is a small lexical TF-IDF/rule-based baseline, not a learned
  personalization model; confidence is heuristic and uncalibrated.
- No live Gemini comparison was run. Provider/model pricing, data handling,
  latency, and availability must be checked before a pilot.
- Latency is local and synthetic; it is not a cloud/provider performance
  measurement.

See [docs/opportunity_report.md](docs/opportunity_report.md) and
[docs/technical_approach.md](docs/technical_approach.md) for the assessment
and implementation details.
