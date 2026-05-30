#!/usr/bin/env python3
"""Mister Wiz Report Compiler — generates student and class reports from CSV data."""

import csv
import math
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from report_names import (class_diagnostic_filename, safe_child_path,
                          student_report_filename)


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


# Display order for class diagnostic skill columns: (label, dev_scores index)
# dev_scores axis order: Audição(0), Fala(1), Gramática(2), Escrita(3), Leitura(4)
SKILL_COLUMN_DEFS = [
    ('Fala', 1),
    ('Audição', 0),
    ('Escrita', 3),
    ('Leitura', 4),
    ('Gramática', 2),
]


def mini_radar_spoke_chart(dev_scores, highlight_axis, cx=34, cy=36, max_r=24):
    """Small pentagon web chart with one axis highlighted (for per-skill columns)."""
    score = int_score(dev_scores[highlight_axis])
    angle = -math.pi / 2 + highlight_axis * 2 * math.pi / 5
    r = (float(score) / 5.0) * max_r
    hx = round(cx + r * math.cos(angle), 2)
    hy = round(cy + r * math.sin(angle), 2)
    return dict(
        grid=pentagon_grid(cx, cy, max_r),
        axes=axis_endpoints(cx, cy, max_r),
        pentagon=pentagon_polygon(dev_scores, cx, cy, max_r),
        center=(cx, cy),
        highlight_tip=(hx, hy),
        highlight_axis=highlight_axis,
    )


def skill_column_charts(dev_scores):
    return [
        dict(
            label=label,
            axis_index=axis_index,
            score=int_score(dev_scores[axis_index]),
            mini=mini_radar_spoke_chart(dev_scores, axis_index),
        )
        for label, axis_index in SKILL_COLUMN_DEFS
    ]


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
    if pct >= 95:
        return 5
    if pct >= 85:
        return 4
    if pct >= 75:
        return 3
    if pct >= 65:
        return 2
    return 1


def missed_lessons(student, all_lessons):
    raw = student.get("missed_aulas", "").strip()
    if not raw:
        return []
    nums = {n.strip() for n in raw.split(",") if n.strip()}
    turma = student["turma"]
    return [
        lesson
        for lesson in all_lessons
        if lesson["turma"] == turma and lesson["aula_num"].strip() in nums
    ]


def lessons_for(turma, all_lessons, report_month=None):
    rows = [
        lesson
        for lesson in all_lessons
        if lesson["turma"] == turma and lesson["aula_num"].strip()
    ]
    if not report_month:
        return rows
    from report_periods import lesson_in_month
    return [lesson for lesson in rows if lesson_in_month(lesson, report_month)]


def needs_extra(student):
    ae = student.get("aula_extra", "").strip().lower()
    return ae in ("reforço", "reforco", "reposição", "reposicao")


def group_by_turma(students):
    groups = {}
    for s in students:
        groups.setdefault(s["turma"], []).append(s)
    return groups


# ── Report builders ───────────────────────────────────────────────────────────

def build_student_ctx(s, all_lessons, report_month=None, trend=None):
    from report_periods import month_label

    turma_lessons = lessons_for(s["turma"], all_lessons, report_month=report_month)
    total = len(turma_lessons)
    missed = missed_lessons(s, all_lessons)
    if report_month:
        from report_periods import lesson_in_month
        missed = [m for m in missed if lesson_in_month(m, report_month)]
        faltas = len(missed)
    else:
        try:
            faltas = max(0, int(float(s.get("faltas") or 0)))
        except (TypeError, ValueError):
            faltas = 0

    pct = presence_pct(faltas, total)
    pie_d, full_circle = pie_path(pct)
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
        report_month=report_month,
        report_month_label=month_label(report_month) if report_month else '',
        trend=trend,
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
        skill_columns=skill_column_charts(dev_scores),
        comp_scores=comp_scores,
        comp_overall=comp_overall,
    )


def build_class_ctx(turma, students, all_lessons, report_month=None, snapshots=None):
    from report_periods import compute_month_trend, month_label, student_composite_score

    turma_lessons = lessons_for(turma, all_lessons, report_month=report_month)
    info = students[0]
    snapshots = snapshots or {}

    student_data = []
    for s in students:
        trend = None
        if report_month:
            ctx_for_score = build_student_ctx(s, all_lessons, report_month=report_month)
            composite = student_composite_score(ctx_for_score)
            trend = compute_month_trend(
                composite, report_month, snapshots,
                s.get('turma', ''), s.get('student_name', ''),
            )
        ctx = build_student_ctx(s, all_lessons, report_month=report_month, trend=trend)
        student_data.append(ctx)

    return dict(
        turma=turma,
        turma_display=info.get("turma_display", turma),
        nivel=info.get("nivel", ""),
        horario=info.get("horario", ""),
        teacher=info.get("teacher", ""),
        report_month=report_month,
        report_month_label=month_label(report_month) if report_month else '',
        lessons=turma_lessons,
        students=student_data,
        grid=pentagon_grid(),
        axes=axis_endpoints(),
    )


# ── Output generators ─────────────────────────────────────────────────────────

def create_report_environment(template_dir):
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(("html", "xml")),
    )


def generate_individual_reports(students, lessons, env, out_dir, report_month=None, snapshots=None):
    from report_periods import compute_month_trend, month_label, student_composite_score
    tpl = env.get_template("individual_report.html")
    snapshots = snapshots or {}
    for s in students:
        turma = (s.get('turma') or '').strip()
        student_name = (s.get('student_name') or '').strip()
        if not turma or not student_name:
            print(f"  ⚠ skipping student row missing turma/name: {s!r}")
            continue
        trend = None
        if report_month:
            base_ctx = build_student_ctx(s, lessons, report_month=report_month)
            composite = student_composite_score(base_ctx)
            trend = compute_month_trend(
                composite, report_month, snapshots,
                turma, student_name,
            )
        ctx = build_student_ctx(s, lessons, report_month=report_month, trend=trend)
        if report_month:
            ctx['report_month_label'] = month_label(report_month)
        html = tpl.render(**ctx)
        fname = student_report_filename(turma, student_name, report_month)
        safe_child_path(out_dir, fname).write_text(html, encoding="utf-8")
        print(f"  ✓ {fname}")


def generate_class_diagnostics(students, lessons, env, out_dir, report_month=None, snapshots=None):
    tpl = env.get_template("class_diagnostic.html")
    snapshots = snapshots or {}
    for turma, group in group_by_turma(students).items():
        ctx = build_class_ctx(turma, group, lessons, report_month=report_month, snapshots=snapshots)
        html = tpl.render(**ctx)
        fname = class_diagnostic_filename(turma, report_month)
        safe_child_path(out_dir, fname).write_text(html, encoding="utf-8")
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

    env = create_report_environment(tmpl_dir)

    print("\nGenerating individual student reports...")
    generate_individual_reports(students, lessons, env, out_dir)

    print("\nGenerating class diagnostics...")
    generate_class_diagnostics(students, lessons, env, out_dir)

    print(f"\nDone! {len(students)} student reports + {len(group_by_turma(students))} class diagnostics → {out_dir}/")


if __name__ == "__main__":
    main()
