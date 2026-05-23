#!/usr/bin/env python3
"""Mister Wiz Report Compiler — generates student and class reports from CSV data."""

import csv
import math
import os
import sys
from pathlib import Path
from jinja2 import Environment, FileSystemLoader


# ── SVG helpers ──────────────────────────────────────────────────────────────

def _pentagon_points(scores, cx, cy, max_r):
    """Return SVG polygon points string for a 5-axis radar chart.
    Axes in order: Audição, Fala, Gramática, Escrita, Leitura (clockwise from top).
    """
    pts = []
    for i, s in enumerate(scores):
        angle = -math.pi / 2 + i * 2 * math.pi / 5
        r = (float(s) / 5.0) * max_r
        x = round(cx + r * math.cos(angle), 2)
        y = round(cy + r * math.sin(angle), 2)
        pts.append(f"{x},{y}")
    return " ".join(pts)


def pentagon_polygon(scores, cx=100, cy=105, max_r=78):
    return _pentagon_points(scores, cx, cy, max_r)


def pentagon_grid(cx=100, cy=105, max_r=78):
    """Return list of SVG polygon point strings for grid rings (levels 1–5)."""
    rings = []
    for level in range(1, 6):
        r = (level / 5.0) * max_r
        pts = []
        for i in range(5):
            angle = -math.pi / 2 + i * 2 * math.pi / 5
            x = round(cx + r * math.cos(angle), 2)
            y = round(cy + r * math.sin(angle), 2)
            pts.append(f"{x},{y}")
        rings.append(" ".join(pts))
    return rings


def axis_endpoints(cx=100, cy=105, max_r=78):
    """Return list of (x, y) axis tip coordinates."""
    eps = []
    for i in range(5):
        angle = -math.pi / 2 + i * 2 * math.pi / 5
        x = round(cx + max_r * math.cos(angle), 2)
        y = round(cy + max_r * math.sin(angle), 2)
        eps.append((x, y))
    return eps


def pie_path(percentage, cx=58, cy=58, r=48):
    """Return (svg_path_d, is_full_circle) for a clockwise attendance pie slice."""
    pct = float(percentage)
    if pct >= 100:
        return f"M {cx},{cy-r} A {r},{r} 0 1,1 {cx - 0.01},{cy-r} Z", True
    angle = (pct / 100) * 2 * math.pi - math.pi / 2
    ex = round(cx + r * math.cos(angle), 2)
    ey = round(cy + r * math.sin(angle), 2)
    large = 1 if pct > 50 else 0
    d = f"M {cx},{cy} L {cx},{cy-r} A {r},{r} 0 {large},1 {ex},{ey} Z"
    return d, False


# ── Data helpers ──────────────────────────────────────────────────────────────

def load_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def int_score(val, default=3):
    try:
        return max(1, min(5, int(float(val))))
    except (TypeError, ValueError):
        return default


def avg_score(scores):
    vals = [float(s) for s in scores if str(s).strip()]
    return round(sum(vals) / len(vals)) if vals else 0


def presence_pct(faltas, total_lessons):
    if total_lessons == 0:
        return 100
    return round(((total_lessons - int(faltas or 0)) / total_lessons) * 100)


def pres_to_score(pct):
    if pct >= 95: return 5
    if pct >= 85: return 4
    if pct >= 75: return 3
    if pct >= 65: return 2
    return 1


def missed_lessons(student, all_lessons):
    raw = student.get("missed_aulas", "").strip()
    if not raw:
        return []
    nums = {n.strip() for n in raw.split(",") if n.strip()}
    turma = student["turma"]
    return [l for l in all_lessons if l["turma"] == turma and l["aula_num"].strip() in nums]


def lessons_for(turma, all_lessons):
    return [l for l in all_lessons if l["turma"] == turma and l["aula_num"].strip()]


def needs_extra(student):
    ae = student.get("aula_extra", "").strip().lower()
    return ae in ("reforço", "reforco", "reposição", "reposicao")


def group_by_turma(students):
    groups = {}
    for s in students:
        groups.setdefault(s["turma"], []).append(s)
    return groups


# ── Report builders ───────────────────────────────────────────────────────────

def build_student_ctx(s, all_lessons):
    turma_lessons = lessons_for(s["turma"], all_lessons)
    total = len(turma_lessons)
    faltas = int_score(s.get("faltas", 0), default=0)

    pct = presence_pct(faltas, total)
    pie_d, full_circle = pie_path(pct)
    missed = missed_lessons(s, all_lessons)
    pres_score = pres_to_score(pct)
    needs_makeup = (s.get("aula_extra", "").strip().lower() in ("reposição", "reposicao"))

    # Participação: Contribuição oral, Foco e atenção, Trabalho em equipe
    part_scores = [
        int_score(s.get("participacao", 3)),
        int_score(s.get("foco", 3)),
        int_score(s.get("trabalho_equipe") or s.get("comportamento", 3)),
    ]
    part_overall = avg_score(part_scores)

    # Desenvolvimento: Audição, Fala, Gramática, Escrita, Leitura
    dev_scores = [
        int_score(s.get("listening", 3)),
        int_score(s.get("speaking", 3)),
        int_score(s.get("gramatica", 3)),
        int_score(s.get("writing", 3)),
        int_score(s.get("reading", 3)),
    ]
    dev_overall = avg_score(dev_scores)
    dev_labels = ["Audição", "Fala", "Gramática", "Escrita", "Leitura"]

    # Comportamento: Organização, Pontualidade, Respeito
    comp_scores = [
        int_score(s.get("organizacao") or s.get("comportamento", 3)),
        int_score(s.get("pontualidade") or s.get("comportamento", 3)),
        int_score(s.get("respeito_regras") or s.get("comportamento", 3)),
    ]
    comp_overall = avg_score(comp_scores)

    return dict(
        student=s,
        pct=pct,
        pie_d=pie_d,
        full_circle=full_circle,
        missed=missed,
        pres_score=pres_score,
        needs_makeup=needs_makeup,
        part_scores=part_scores,
        part_overall=part_overall,
        dev_scores=dev_scores,
        dev_overall=dev_overall,
        dev_labels=dev_labels,
        pentagon=pentagon_polygon(dev_scores),
        grid=pentagon_grid(),
        axes=axis_endpoints(),
        comp_scores=comp_scores,
        comp_overall=comp_overall,
    )


def build_class_ctx(turma, students, all_lessons):
    turma_lessons = lessons_for(turma, all_lessons)
    info = students[0]

    student_data = []
    for s in students:
        ctx = build_student_ctx(s, all_lessons)
        student_data.append(ctx)

    return dict(
        turma=turma,
        turma_display=info.get("turma_display", turma),
        nivel=info.get("nivel", ""),
        horario=info.get("horario", ""),
        teacher=info.get("teacher", ""),
        lessons=turma_lessons,
        students=student_data,
        grid=pentagon_grid(),
        axes=axis_endpoints(),
    )


# ── Output generators ─────────────────────────────────────────────────────────

def generate_individual_reports(students, lessons, env, out_dir):
    tpl = env.get_template("individual_report.html")
    for s in students:
        ctx = build_student_ctx(s, lessons)
        html = tpl.render(**ctx)
        safe_name = s["student_name"].replace(" ", "_")
        fname = f"{s['turma']}_{safe_name}_report.html"
        (out_dir / fname).write_text(html, encoding="utf-8")
        print(f"  ✓ {fname}")


def generate_class_diagnostics(students, lessons, env, out_dir):
    tpl = env.get_template("class_diagnostic.html")
    for turma, group in group_by_turma(students).items():
        ctx = build_class_ctx(turma, group, lessons)
        html = tpl.render(**ctx)
        fname = f"{turma}_class_diagnostic.html"
        (out_dir / fname).write_text(html, encoding="utf-8")
        print(f"  ✓ {fname}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    base = Path(__file__).parent
    data_dir = base / "data"
    tmpl_dir = base / "templates"
    out_dir = base / "output"
    out_dir.mkdir(exist_ok=True)

    students_file = data_dir / "students.csv"
    lessons_file = data_dir / "lessons.csv"

    if not students_file.exists():
        print(f"ERROR: {students_file} not found.", file=sys.stderr)
        sys.exit(1)
    if not lessons_file.exists():
        print(f"ERROR: {lessons_file} not found.", file=sys.stderr)
        sys.exit(1)

    students = load_csv(students_file)
    lessons = load_csv(lessons_file)

    env = Environment(loader=FileSystemLoader(str(tmpl_dir)), autoescape=False)

    print("\nGenerating individual student reports...")
    generate_individual_reports(students, lessons, env, out_dir)

    print("\nGenerating class diagnostics...")
    generate_class_diagnostics(students, lessons, env, out_dir)

    print(f"\nDone! {len(students)} student reports + {len(group_by_turma(students))} class diagnostics → {out_dir}/")


if __name__ == "__main__":
    main()
