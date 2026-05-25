# LinkedIn post kit — Mister Wiz Report Compiler

Use this document to build a project showcase post. Mix English and Portuguese as you prefer; samples below are English-first with optional PT lines.

---

## Quick facts (for your bio / comments)

| Item | Detail |
|------|--------|
| **Project** | Mister Wiz Report Compiler |
| **What** | Web dashboard + Python engine that turns teacher CSVs into print-ready student & class reports |
| **Client / context** | Mister Wiz English school (internal teacher tool) |
| **Live app** | https://charlesdesouza88-mw-report-copiler-production.up.railway.app |
| **Repo** | https://github.com/charlesdesouza88/MW-report-copiler |
| **Stack** | Python, Flask, Gunicorn, Jinja2, PostgreSQL, Railway, pytest |
| **Outputs** | A4 landscape HTML reports (individual cards + class diagnostics) → Print to PDF |

---

## Recommended post format

**Best on LinkedIn:** Carousel (PDF or 6–8 images) + short caption, **or** 60–90s screen recording as native video.

**Post type:** “Project launch” / “What I built” — good for portfolio and hiring visibility.

---

## Caption option A — Story + impact (recommended)

**Hook (first line — visible before “see more”):**  
I built a tool that turns two CSV files into polished student report cards for an English school — in one click.

**Body:**

Teachers used to spend hours formatting report cards by hand. I designed and shipped **Mister Wiz Report Compiler**: a teacher dashboard where they upload student and lesson data, review scores, and generate **print-ready reports** for every student and every class.

**What it does**
- Upload `students.csv` + `lessons.csv` (with templates and validation)
- Manage students, classes, and scores (1–5) in a simple admin UI
- Generate individual A4 report cards + full class diagnostics
- Preview, print, or download reports — works on **phone, tablet, and desktop**

**Under the hood**
- Python + Flask dashboard, deployed on **Railway** with **PostgreSQL**
- Jinja2 templates with inline SVG charts (radar, pie, bars) — no external chart libraries
- Automated tests + health checks for production reliability
- Responsive UI so teachers can review reports on their phones

This was a full-stack product build: data model, report design, deployment, database connectivity, and mobile UX — not just a script.

**Links**  
🔗 Live demo (login required): https://charlesdesouza88-mw-report-copiler-production.up.railway.app  
💻 Code: https://github.com/charlesdesouza88/MW-report-copiler

If you run a school or training business and still assemble reports manually, happy to share what worked.

**Hashtags (pick 5–8):**  
#Python #Flask #FullStack #EdTech #Railway #PostgreSQL #WebDevelopment #BuildInPublic #SoftwareEngineering #Automation

---

## Caption option B — Technical / developer audience

Shipped: **Mister Wiz Report Compiler** — CSV → validated storage → Jinja2 HTML reports with SVG charts → Flask admin + Railway + Postgres.

Highlights:
- Dual mode: CSV files or PostgreSQL via `DATABASE_URL`
- Report engine: attendance %, participation/development/behavior aggregates, per-student context builders
- Print-first CSS (`@page` A4 landscape) + separate `@media screen` for mobile preview
- Drawer nav, student cards on mobile, pytest suite, `/health` + `/health/db` endpoints

Repo: https://github.com/charlesdesouza88/MW-report-copiler

---

## Caption option C — Short (under 300 characters)

Built a report automation tool for an English school: upload CSVs → manage students → generate print-ready HTML report cards + class diagnostics. Python, Flask, PostgreSQL, Railway. Mobile-friendly teacher dashboard.

🔗 https://github.com/charlesdesouza88/MW-report-copiler

---

## Portuguese caption (optional)

Construí o **Mister Wiz Report Compiler**: professores enviam CSVs de alunos e aulas, revisam notas no painel e geram **relatórios prontos para impressão** (cartão individual + diagnóstico da turma) em um clique.

Stack: Python, Flask, PostgreSQL, Railway — com interface responsiva para celular e tablet.

🔗 App: https://charlesdesouza88-mw-report-copiler-production.up.railway.app  
💻 Código: https://github.com/charlesdesouza88/MW-report-copiler

#Python #Flask #EdTech #DesenvolvimentoWeb

---

## Carousel slides (copy per slide)

Use one idea per slide. Export as 1080×1080 or 1080×1350 images (Canva/Figma) or PDF carousel.

| Slide | Headline | Body text |
|-------|----------|-----------|
| 1 | **Mister Wiz Report Compiler** | From CSV to print-ready student reports in one workflow |
| 2 | **The problem** | Manual report cards = hours of copy-paste, inconsistent layout, errors |
| 3 | **The solution** | Teachers upload data → dashboard validates → one click generates all reports |
| 4 | **Individual reports** | A4 landscape cards: attendance, participation, skills radar, behavior, recommendations |
| 5 | **Class diagnostics** | Profiles, skill charts, development indices, reinforcement scheduling pages |
| 6 | **Teacher dashboard** | Upload CSV templates · manage students · preview · print · download ZIP |
| 7 | **Built for real use** | PostgreSQL on Railway · mobile-responsive · automated tests · health monitoring |
| 8 | **Stack & links** | Python · Flask · Jinja2 · SVG · Railway · GitHub (add QR or URL) |

---

## Photo shot list (what to capture)

Capture these as **screenshots** or **phone photos of your screen** (clean browser, no personal passwords visible).

### Must-have (5–6 images)

1. **Dashboard home** — stat cards (students, classes, lessons, reports) + “Gerar Relatórios” (desktop, 1280px width).
2. **Upload page** — hero + both CSV panels (shows product polish).
3. **Sample individual report** — full A4 preview in browser (student name visible; use sample/fake name if needed).
4. **Class diagnostic** — page 1 with profiles table + skill cards.
5. **Mobile dashboard** — phone width: top bar with ☰ menu + stacked stats (proves responsive work).
6. **Reports list** — generated files with Preview / Print / Download actions.

### Nice-to-have

7. **Student edit** — score pickers (1–5 bubbles) — shows UX care.
8. **Students page** — table on desktop OR cards on phone.
9. **Before/after** — split: messy spreadsheet vs clean report (mock in Canva if needed).
10. **Architecture diagram** — simple boxes: CSV/DB → Flask → Templates → HTML/PDF.

### How to capture quickly

```bash
# Local (safe for screenshots — use test data)
cd "/path/to/MW-report-copiler"  # your local clone
ADMIN_PASSWORD=testpass SECRET_KEY=dev python3 -m flask --app app run -p 5000
# Open http://127.0.0.1:5000 — login with testpass
# Generate reports first if output/ is empty: upload data/ CSVs → Gerar Relatórios
```

Chrome DevTools → Toggle device toolbar → iPhone 14 (390px) for mobile shots.

**Do not screenshot:** Railway env vars, `.env`, real student PII without permission, admin password fields filled in.

---

## Video scripts

### Video 1 — 45–60 seconds (ideal for LinkedIn native video)

| Time | Visual | Voiceover / text overlay |
|------|--------|-------------------------|
| 0–5s | Dashboard logo / title card | “I built a report compiler for an English school.” |
| 5–12s | Upload page scroll | “Teachers upload two CSV files — students and lessons.” |
| 12–18s | Click Generate | “One click generates every report.” |
| 18–30s | Scroll individual report (Presença, Participação, radar) | “Individual cards: attendance, participation, skills, behavior — print-ready.” |
| 30–40s | Class diagnostic table + charts | “Plus a full class diagnostic with profiles and indices.” |
| 40–50s | Phone: mobile dashboard | “Works on phone too — teachers can preview on the go.” |
| 50–60s | End card: GitHub + Railway URL | “Python, Flask, PostgreSQL, Railway. Link in comments.” |

**Recording tip:** QuickTime or OBS, 1920×1080, cursor highlights, 1.25× speed in edit if needed. Add subtle background music (royalty-free).

### Video 2 — 15 seconds (teaser / reel style)

Fast cuts: Upload → Generate button → Report scroll → Mobile menu open → Logo end card.  
On-screen text only: “CSV in. Reports out.” / “Built with Python + Flask”

---

## Report content to highlight (talking points)

Use these if someone asks “what’s on the report?”

**Individual student report (4 quadrants):**
- **Presença** — attendance % + pie chart + score 1–5  
- **Participação** — oral contribution, focus, teamwork + teacher feedback  
- **Desenvolvimento** — listening, speaking, grammar, writing, reading + bar chart + pentagon radar  
- **Comportamento** — organization, punctuality, classroom rules  
- **Recomendações** — teacher recommendations footer  

**Class diagnostic:**
- Member profiles + per-student skill mini-charts  
- Development indices (attendance / development / engagement)  
- Extra pages for students needing **Reforço** or **Reposição** with scheduling grids  

---

## Skills to tag on LinkedIn (project section)

Python · Flask · Jinja2 · PostgreSQL · SQLAlchemy · HTML/CSS · SVG · REST APIs · Gunicorn · Railway · pytest · Git · Responsive Web Design · Technical Documentation · EdTech · Process Automation

---

## Project description (LinkedIn “Featured” or Experience bullet)

**Mister Wiz Report Compiler** — Full-stack reporting tool for an English language school. Designed CSV data models and validation, built a Flask teacher dashboard with PostgreSQL persistence on Railway, and implemented Jinja2 report templates with inline SVG visualizations for print-ready A4 student and class reports. Delivered responsive mobile UI, automated testing, and production health monitoring.

---

## Comment to pin (after posting)

Thanks for the interest!  
🔗 **Code:** https://github.com/charlesdesouza88/MW-report-copiler  
🔗 **Live app:** https://charlesdesouza88-mw-report-copiler-production.up.railway.app (private login — demo on request)  

Stack: Python · Flask · PostgreSQL · Railway · Jinja2 · pytest  

Happy to connect with others building tools for education or ops automation.

---

## Engagement prompts (optional last line)

Pick one:
- “What’s the most painful manual report process you’ve seen?”
- “Would you generate PDFs server-side next, or keep print-from-browser?”
- “Teachers: would you trust CSV upload or prefer Google Sheets sync?”

---

## Checklist before you post

- [ ] Generate fresh sample reports (no real student names unless you have consent)
- [ ] Capture 6 carousel images or one 60s video
- [ ] Blur/crop any sensitive data
- [ ] Add GitHub link (and live URL if you want inquiries)
- [ ] Post Tuesday–Thursday morning (your timezone) for best reach
- [ ] Reply to first comments within 1 hour

---

## Sample report names for demos (from repo data)

Use generic or first-name-only in visuals if posting publicly: e.g. “Jane Doe”, “MASTER class”, teacher “Chuck” — or anonymize to “Student A”, “Class B”.
