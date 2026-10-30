# Cynbit Technologies: AI opportunity report

## Scope and evidence

The assessment brief says Cynbit Technologies is based in Jaipur and runs
BitElevate with 16 training tracks. These company/program details are treated
as **claimed by Cynbit**; they were not independently verified because the
brief supplied no public-page URL. The report uses no private company data.
Opportunity descriptions and scores below are assessment hypotheses, not
claims about existing Cynbit operations.

## Scoring

Each dimension is scored 1–5. Value, feasibility, data access, and speed to
pilot are better when higher. **Risk is exposure** (1 = lower risk, 5 = higher
risk), so the total rewards lower risk:

`Total = value + feasibility + data access + (6 - risk) + speed to pilot`

Maximum total: 25. Scores are comparative judgement for choosing a small
pilot, not measured business outcomes.

| Opportunity | Value | Feasibility | Data access | Risk | Speed to pilot | Total |
|---|---:|---:|---:|---:|---:|---:|
| BitElevate Path Finder | 5 | 4 | 4 | 2 | 5 | **22** |
| “Ask Cynbit” public-site assistant | 4 | 4 | 3 | 3 | 4 | 18 |
| Enquiry triage and routing | 4 | 4 | 3 | 3 | 4 | 18 |
| Cynbit Studio code evaluator | 4 | 3 | 2 | 4 | 3 | 14 |
| Internal proposal drafting | 3 | 5 | 4 | 2 | 5 | 21 |

## Opportunities

### 1. BitElevate Path Finder — selected

Recommend a training track from a student’s stated background, interests,
availability, and goal; return a short, explainable roadmap and first task.
The prototype can run from a small, hand-curated catalogue and synthetic test
profiles, so it does not depend on access to student records. The main risks
are poor recommendations, prompt injection, and accidental collection of
personal information; the proof of concept therefore uses a deterministic
fallback, consent controls, output allowlists, and no free-text persistence.

### 2. “Ask Cynbit” public-site assistant

Answer common questions using only approved public pages and link each answer
to its source. It could reduce navigation friction, but no public-site URL or
approved content set was provided for this assessment. A pilot would need a
curated corpus, explicit “not found” behavior, and a review process for
changes to public claims.

### 3. Enquiry triage and routing

Classify incoming enquiries into categories such as course information,
admissions, or technical support and suggest a destination for staff review.
This may shorten response time, but it requires access to historical enquiries
and a clear privacy/retention basis. The model should not send replies or make
admissions decisions automatically in an initial pilot.

### 4. Cynbit Studio code evaluator

Give learners rubric-based feedback on submitted code, tests, and explanations.
This could support practice at scale but needs a verified rubric, sandboxed
execution, careful handling of unsafe submissions, and safeguards against
grading bias. No Cynbit Studio dataset or rubric was supplied, so this is not
appropriate as the first pilot.

### 5. Internal proposal drafting

Draft structured proposal outlines from staff-approved templates and project
facts. Feasibility and speed are high because a template-based assistant can
start without model training, but business value is less direct to the student
program. It also requires access controls and review to prevent confidential
or inaccurate claims from entering proposals.

## Pick and rationale

**Pilot BitElevate Path Finder first.** It leads the comparative score (22/25),
can be demonstrated from public/synthetic catalogue content without internal
records, and has a measurable offline evaluation. It also tests the useful
end-to-end pattern—retrieval, bounded generation, schema validation, and
fallback—without granting an assistant access to systems or letting it make
high-impact decisions. Internal proposal drafting is a close second (21/25),
but has less direct student value. The Path Finder should remain advisory and
human-reviewed until real-world quality and privacy are separately validated.
