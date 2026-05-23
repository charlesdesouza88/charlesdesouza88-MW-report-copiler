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

- **Python 3.8+** — no web server, no database
- **Jinja2** — HTML templating
- **Inline SVG** — radar/pentagon charts and attendance pie charts (no JS, no external charting libs)
- **CSS `@page`** — A4 landscape print layout
- **pytest** — unit and integration tests

---

## Project structure

```
mister-wiz-report-compiler/
├── compiler.py              # Main script — reads CSVs, renders templates, writes output/
├── requirements.txt         # jinja2, pytest
├── templates/
│   ├── individual_report.html   # Jinja2 template: per-student report card
│   └── class_diagnostic.html   # Jinja2 template: per-class diagnostic
├── data/
│   ├── students.csv         # One row per student (scores, feedback, attendance)
│   └── lessons.csv          # One row per lesson (date, content, activities)
└── output/                  # Generated HTML files (git-ignored)
```

---

## How to run

```bash
pip install -r requirements.txt
python compiler.py
# → output/ now contains all student reports and class diagnostics
```

To run tests:

```bash
pytest test_compiler.py -v
```

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

## Planned extensions

- **Google Sheets sync** — read `students.csv` / `lessons.csv` directly from a shared Google Sheet via the Sheets API
- **PDF export** — add WeasyPrint or Puppeteer to generate PDFs server-side (no browser printing needed)
- **Web UI** — simple Flask/FastAPI form where teachers fill in scores and download reports instantly
- **Multi-language support** — English/Portuguese toggle on report templates
- **Period comparison** — track score deltas between reporting periods per student
