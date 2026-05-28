# Mister Wiz Report Compiler

A Python tool that reads teacher-filled CSV data and generates print-ready HTML reports for every student and class at **Mister Wiz** English school.

---

## What it does

Teachers fill in two CSV files once per reporting period. Running `python compiler.py` produces:

| Output | One file per | Content |
|---|---|---|
| `{TURMA}_{Student}_report.html` | Student | Individual A4 landscape report card |
| `{TURMA}_class_diagnostic.html` | Class | Full class diagnostic (profiles, skill charts, indices, reinforcement pages) |

All outputs are self-contained HTML — open in any browser and **Print → Save as PDF**.

---

## Tech stack

- **Python 3.8+** — CLI report compiler; optional Flask web dashboard
- **Flask + Gunicorn** — teacher dashboard (deployed on Railway)
- **PostgreSQL** (optional) — persistent student/lesson data via SQLAlchemy
- **Jinja2** — HTML templating
- **Inline SVG** — radar/pentagon charts and attendance pie charts (no JS, no external charting libs)
- **CSS `@page`** — A4 landscape print layout
- **pytest** — unit and integration tests

---

## Project structure

```
mister-wiz-report-compiler/
├── compiler.py              # Main script — reads CSVs, renders templates, writes output/
├── app.py                   # Flask web dashboard
├── railway.json             # Railway deploy config (gunicorn)
├── requirements.txt
├── templates/               # Report HTML (Jinja2)
├── web_templates/           # Dashboard HTML (Flask)
├── data/                    # Sample / local CSV data
└── output/                  # Generated HTML files (git-ignored)
```

---

## How to run

CLI report generation:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python compiler.py
# -> output/ now contains all student reports and class diagnostics
```

Web dashboard (easiest local test):

```bash
cp .env.example .env
# Edit .env: SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD

chmod +x scripts/dev.sh
./scripts/dev.sh
# Prints your login email and starts the server (uses 5001 if macOS blocks 5000)
# Open the URL shown in the terminal, e.g. http://127.0.0.1:5001/login
```

Quick automated journey check (no browser):

```bash
.venv/bin/python scripts/smoke_journey.py
```

Manual alternative:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

To run the test battery:

```bash
. .venv/bin/activate
pytest -q
```

## Database mode (optional)

The app can run in two storage modes:

- CSV mode (default): reads/writes `data/students.csv` and `data/lessons.csv`.
- Database mode: enabled when `DATABASE_URL` is set.

When `DATABASE_URL` exists, students and lessons are stored in SQL tables and the
upload flow writes validated CSV data directly to the database.

For Railway PostgreSQL:

1. Create a PostgreSQL service in Railway.
2. Copy `DATABASE_URL` from the PostgreSQL service variables.
3. Set `DATABASE_URL` on your Railway web service (Variables → reference the Postgres service).
4. Redeploy the app.

Notes:

- If your URL starts with `postgres://`, the app auto-normalizes it and adds `sslmode=require` (required on Railway).
- On the **web service**, reference Postgres `DATABASE_URL` (private URL), not the public proxy URL unless you know you need it.
- Tables are created automatically on startup.
- After deploy, open `/health/db` — `connected` should be `true`.

---

## Data model

### `data/students.csv`

One row per student. All score fields are integers 1–5.

| Column | Type | Description |
|---|---|---|
| `teacher` | string | Teacher's first name (e.g. `Chuck`) |
| `turma` | string | Class code used as file prefix (e.g. `MASTER`, `SPARK`) |
| `turma_display` | string | Human-readable class name (e.g. `Masters`) |
| `nivel` | string | Level description (e.g. `Adults Book 4`, `Kids 1`) |
| `horario` | string | Schedule (e.g. `Terça e quinta, 19:00 - 20:00`) |
| `student_name` | string | Full student name |
| `participacao` | 1–5 | Oral contribution in class |
| `comportamento` | 1–5 | Overall behaviour score (used as fallback for sub-scores) |
| `speaking` | 1–5 | Speaking / Fala |
| `listening` | 1–5 | Listening / Audição |
| `foco` | 1–5 | Focus and attention |
| `writing` | 1–5 | Writing / Escrita |
| `reading` | 1–5 | Reading / Leitura |
| `gramatica` | 1–5 | Grammar / Gramática |
| `trabalho_equipe` | 1–5 | Teamwork (falls back to `comportamento`) |
| `organizacao` | 1–5 | Brings materials / desk organised (falls back to `comportamento`) |
| `pontualidade` | 1–5 | Punctuality (falls back to `comportamento`) |
| `respeito_regras` | 1–5 | Respects classroom rules (falls back to `comportamento`) |
| `faltas` | int ≥ 0 | Number of absences |
| `missed_aulas` | string | Comma-separated lesson numbers missed (e.g. `"6,11"`) |
| `aula_extra` | string | `Reforço`, `Reposição`, or blank |
| `feedback_participacao` | string | Teacher's written feedback on oral contribution |
| `feedback_foco` | string | Teacher's written feedback on focus |
| `feedback_trabalho_equipe` | string | Teacher's written feedback on teamwork |
| `recomendacoes` | string | Free-text recommendations printed at bottom of report |
| `observacao` | string | Internal observation (shown in class diagnostic, not student report) |

### `data/lessons.csv`

One row per lesson. Used to calculate attendance % and list what was missed.

| Column | Type | Description |
|---|---|---|
| `turma` | string | Must match `turma` in `students.csv` |
| `aula_num` | string | Lesson number (e.g. `"6"`) — blank rows are ignored |
| `date` | string | Date shown on the report (e.g. `03/09`) |
| `licao_conteudo` | string | Lesson name/topic (e.g. `Lesson 6: Colors`) |
| `atividade_extra` | string | Extra activity description |
| `habilidades` | string | Skills focus (optional) |

---

## Score mappings

### Presença (Attendance)

Attendance % is calculated as `(total_lessons - faltas) / total_lessons × 100`.

| % | Score |
|---|---|
| ≥ 95% | 5 |
| ≥ 85% | 4 |
| ≥ 75% | 3 |
| ≥ 65% | 2 |
| < 65% | 1 |

### Participação

Average of `participacao` (Contribuição oral), `foco` (Foco e atenção), `trabalho_equipe` (Trabalho em equipe).

### Desenvolvimento

Average of `listening`, `speaking`, `gramatica`, `writing`, `reading`. Rendered as both a bar chart (5 skills) and a pentagon radar chart.

### Comportamento

Average of `organizacao`, `pontualidade`, `respeito_regras`.

---

## Report anatomy

### Individual student report (`individual_report.html`)

A4 landscape, 4-quadrant layout:

```
┌────────────────────┬────────────────────┐
│  Presença          │  Participação      │
│  pie chart + score │  3 bubbles + text  │
├────────────────────┼────────────────────┤
│  Desenvolvimento   │  Comportamento     │
│  bars + radar      │  3 bubbles         │
└────────────────────┴────────────────────┘
  Recomendações (full width)
```

### Class diagnostic (`class_diagnostic.html`)

Multi-page:
- **Page 1** — Member profiles table + individual skill score cards with mini radar charts
- **Page 2** — Development indices table (Presença / Desenvolvimento / Engajamento per student) + Reinforcement direction notes
- **Page 3+** — One page per student flagged as `Reforço` or `Reposição`: Comunicação / Expressão escrita / Domínio Estrutural scores + date grids for scheduling makeup/extra classes

---

## Adding a new teacher or class

1. Add rows to `data/students.csv` with the teacher's name and a new `turma` code.
2. Add the lesson log rows to `data/lessons.csv` with the same `turma` code.
3. Run `python compiler.py` — new reports appear in `output/`.

No code changes needed.

---

## Key functions in `compiler.py`

| Function | Purpose |
|---|---|
| `build_student_ctx(s, lessons)` | Computes all derived values for one student (pct, scores, SVG data) |
| `build_class_ctx(turma, students, lessons)` | Builds context dict for one class diagnostic |
| `generate_individual_reports(...)` | Renders and writes all student HTML files |
| `generate_class_diagnostics(...)` | Renders and writes all class diagnostic HTML files |
| `pentagon_polygon(scores)` | Returns SVG polygon points for a 5-axis radar chart |
| `pie_path(percentage)` | Returns SVG path `d` string for the attendance pie slice |
| `pres_to_score(pct)` | Maps attendance % to 1–5 score |
| `needs_extra(student)` | Returns `True` if student has `Reforço` or `Reposição` flag |
| `group_by_turma(students)` | Groups student list into `{turma: [students]}` dict |

---

## Go live on Railway

Production hosting uses **Railway** (`railway.json` runs `gunicorn` on the Flask app).

### 1. Create the project

1. Push this repo to GitHub.
2. In [Railway](https://railway.app), **New Project → Deploy from GitHub repo** and select this repository.
3. Railway uses `railway.json` for the start command and health check (`/health`).

### 2. Environment variables

On the **web service**, set:

| Variable | Required | Notes |
|---|---|---|
| `SUPERADMIN_EMAIL` | Yes | Bootstrap superadmin login email |
| `SUPERADMIN_PASSWORD` | Yes | Bootstrap superadmin login password |
| `SECRET_KEY` | Yes | Long random string for Flask sessions |
| `DATABASE_URL` | Recommended | From a Railway PostgreSQL service |
| `DATA_DIR` | Optional | Path on a mounted volume for CSV files |
| `OUT_DIR` | Optional | Path on a mounted volume for generated reports |

Copy `.env.example` for local development.

### 3. PostgreSQL (recommended)

1. In the same Railway project, add **PostgreSQL**.
2. On the web service, add a variable reference: `DATABASE_URL` → Postgres `DATABASE_URL`.
3. Redeploy. Tables are created automatically on startup.

With `DATABASE_URL` set, uploads and student edits persist in the database.

### 4. Persistent files (optional)

For CSV-on-disk mode or keeping generated HTML between deploys:

1. Add a **Volume** to the web service (e.g. mount at `/data`).
2. Set `DATA_DIR=/data/mw/data` and `OUT_DIR=/data/mw/output`.
3. Redeploy.

Without a volume, the app still works locally and on Railway using `data/` and `output/` inside the container (data resets on redeploy unless you use the database).

### MCP in Cursor (optional)

This repo includes `.cursor/mcp.json` for the [Railway remote MCP](https://docs.railway.com/ai/remote-mcp-server) (`https://mcp.railway.com`).

1. Reload Cursor MCP servers (or restart Cursor).
2. Approve Railway access in the browser when prompted.
3. You can then ask the agent to list projects, services, variables, and logs.

CLI alternative: `npx -y @railway/cli login` then `railway link` in this directory.

### 5. Post-deploy checks

1. Open the Railway public URL → `/login` with `SUPERADMIN_EMAIL` and `SUPERADMIN_PASSWORD`.
2. Upload `students.csv` and `lessons.csv` (or use DB mode after Postgres is linked).
3. **Generate** reports and confirm preview/download work.

## Planned extensions

- **Google Sheets sync** — read `students.csv` / `lessons.csv` directly from a shared Google Sheet via the Sheets API
- **PDF export** — add WeasyPrint or Puppeteer to generate PDFs server-side (no browser printing needed)
- **Multi-language support** — English/Portuguese toggle on report templates
- **Period comparison** — track score deltas between reporting periods per student
