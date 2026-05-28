"""Tests for compiler.py — Mister Wiz Report Compiler."""

import csv
import io
import math
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from compiler import (
    _pentagon_points,
    pentagon_polygon,
    pentagon_grid,
    axis_endpoints,
    pie_path,
    load_csv,
    int_score,
    avg_score,
    presence_pct,
    pres_to_score,
    missed_lessons,
    lessons_for,
    needs_extra,
    group_by_turma,
    build_student_ctx,
    build_class_ctx,
    generate_individual_reports,
    generate_class_diagnostics,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_LESSONS = [
    {"turma": "MASTER", "aula_num": "1", "date": "10/02/2026", "licao_conteudo": "Introduction", "atividade_extra": "Syllabus", "habilidades": ""},
    {"turma": "MASTER", "aula_num": "2", "date": "12/02/2026", "licao_conteudo": "Lesson 1", "atividade_extra": "Connection words", "habilidades": ""},
    {"turma": "MASTER", "aula_num": "3", "date": "19/02/2026", "licao_conteudo": "Lesson 2", "atividade_extra": "Abbreviations", "habilidades": ""},
    {"turma": "INSPIRE", "aula_num": "1", "date": "10/02/2026", "licao_conteudo": "Introduction", "atividade_extra": "Syllabus", "habilidades": ""},
    {"turma": "INSPIRE", "aula_num": "2", "date": "12/02/2026", "licao_conteudo": "Lesson 1", "atividade_extra": "Worksheet", "habilidades": ""},
    {"turma": "SPARK", "aula_num": "", "date": "01/01/2026", "licao_conteudo": "Empty aula_num", "atividade_extra": "", "habilidades": ""},
]

SAMPLE_STUDENT = {
    "teacher": "Chuck",
    "turma": "MASTER",
    "turma_display": "Masters",
    "nivel": "Adults Book 4",
    "horario": "Terça e quinta, 19:00 - 20:00",
    "student_name": "Ana Silva",
    "participacao": "4",
    "comportamento": "3",
    "speaking": "5",
    "listening": "3",
    "foco": "4",
    "writing": "4",
    "reading": "4",
    "gramatica": "4",
    "trabalho_equipe": "4",
    "organizacao": "4",
    "pontualidade": "4",
    "respeito_regras": "4",
    "faltas": "1",
    "missed_aulas": "2",
    "aula_extra": "",
    "feedback_participacao": "Boa contribuição",
    "feedback_foco": "Muito focada",
    "feedback_trabalho_equipe": "Ótima em equipe",
    "recomendacoes": "",
    "observacao": "",
}


# ── _pentagon_points / pentagon_polygon ───────────────────────────────────────

class TestPentagonPoints:
    def test_returns_string(self):
        result = _pentagon_points([3, 3, 3, 3, 3], cx=100, cy=105, max_r=78)
        assert isinstance(result, str)

    def test_returns_five_point_pairs(self):
        result = _pentagon_points([3, 3, 3, 3, 3], cx=100, cy=105, max_r=78)
        pairs = result.strip().split()
        assert len(pairs) == 5
        for p in pairs:
            x, y = p.split(",")
            float(x)  # should not raise
            float(y)

    def test_all_zeros_gives_center(self):
        # Score 0 maps to r=0, all points should be at (cx, cy)
        result = _pentagon_points([0, 0, 0, 0, 0], cx=100, cy=105, max_r=78)
        for pair in result.strip().split():
            x, y = pair.split(",")
            assert float(x) == pytest.approx(100.0, abs=0.05)
            assert float(y) == pytest.approx(105.0, abs=0.05)

    def test_all_fives_gives_max_radius(self):
        # Score 5 maps to r=max_r; first axis is at angle -pi/2 (pointing up)
        result = _pentagon_points([5, 5, 5, 5, 5], cx=100, cy=105, max_r=78)
        pairs = result.strip().split()
        x0, y0 = (float(v) for v in pairs[0].split(","))
        # First point: angle=-pi/2 → x=cx, y=cy-max_r
        assert x0 == pytest.approx(100.0, abs=0.05)
        assert y0 == pytest.approx(105.0 - 78.0, abs=0.05)

    def test_mixed_scores(self):
        result = _pentagon_points([1, 3, 5, 2, 4], cx=100, cy=105, max_r=78)
        pairs = result.strip().split()
        assert len(pairs) == 5

    def test_pentagon_polygon_uses_defaults(self):
        scores = [3, 3, 3, 3, 3]
        assert pentagon_polygon(scores) == _pentagon_points(scores, cx=100, cy=105, max_r=78)

    def test_pentagon_polygon_custom_params(self):
        scores = [2, 4, 1, 5, 3]
        assert pentagon_polygon(scores, cx=50, cy=50, max_r=40) == _pentagon_points(scores, 50, 50, 40)

    def test_float_scores_accepted(self):
        result = _pentagon_points([1.5, 2.5, 3.5, 4.5, 5.0], cx=100, cy=105, max_r=78)
        assert len(result.strip().split()) == 5


# ── pentagon_grid ─────────────────────────────────────────────────────────────

class TestPentagonGrid:
    def test_returns_five_rings(self):
        rings = pentagon_grid()
        assert len(rings) == 5

    def test_each_ring_has_five_points(self):
        rings = pentagon_grid()
        for ring in rings:
            pairs = ring.strip().split()
            assert len(pairs) == 5

    def test_rings_are_ordered_increasing(self):
        # Each ring's points should be farther from center than the previous
        rings = pentagon_grid(cx=100, cy=105, max_r=78)
        def dist_from_center(ring, cx=100, cy=105):
            x, y = ring.strip().split()[0].split(",")
            return math.hypot(float(x) - cx, float(y) - cy)
        dists = [dist_from_center(r) for r in rings]
        assert dists == sorted(dists)

    def test_outermost_ring_at_max_r(self):
        rings = pentagon_grid(cx=100, cy=105, max_r=78)
        outer = rings[-1]
        x, y = outer.strip().split()[0].split(",")
        d = math.hypot(float(x) - 100, float(y) - 105)
        assert d == pytest.approx(78.0, abs=0.05)

    def test_custom_params(self):
        rings = pentagon_grid(cx=50, cy=50, max_r=40)
        assert len(rings) == 5


# ── axis_endpoints ────────────────────────────────────────────────────────────

class TestAxisEndpoints:
    def test_returns_five_endpoints(self):
        eps = axis_endpoints()
        assert len(eps) == 5

    def test_each_endpoint_is_tuple_of_two_floats(self):
        eps = axis_endpoints()
        for ep in eps:
            assert len(ep) == 2
            float(ep[0])
            float(ep[1])

    def test_first_axis_points_up(self):
        # First axis angle = -pi/2 → x=cx, y=cy-max_r
        eps = axis_endpoints(cx=100, cy=105, max_r=78)
        assert eps[0][0] == pytest.approx(100.0, abs=0.05)
        assert eps[0][1] == pytest.approx(27.0, abs=0.05)  # 105 - 78

    def test_all_endpoints_at_max_r_distance(self):
        eps = axis_endpoints(cx=100, cy=105, max_r=78)
        for x, y in eps:
            d = math.hypot(x - 100, y - 105)
            assert d == pytest.approx(78.0, abs=0.05)

    def test_custom_params(self):
        eps = axis_endpoints(cx=50, cy=60, max_r=30)
        assert len(eps) == 5
        for x, y in eps:
            d = math.hypot(x - 50, y - 60)
            assert d == pytest.approx(30.0, abs=0.05)


# ── pie_path ──────────────────────────────────────────────────────────────────

class TestPiePath:
    def test_full_circle_at_100(self):
        d, is_full = pie_path(100)
        assert is_full is True
        assert "A" in d

    def test_full_circle_above_100(self):
        d, is_full = pie_path(120)
        assert is_full is True

    def test_partial_circle_returns_false(self):
        d, is_full = pie_path(50)
        assert is_full is False

    def test_partial_circle_has_path_data(self):
        d, _ = pie_path(75)
        assert d.startswith("M ")
        assert "L" in d
        assert "A" in d
        assert "Z" in d

    def test_large_arc_flag_when_over_50(self):
        d, _ = pie_path(75)
        # large-arc-flag should be 1
        assert " 1,1 " in d

    def test_small_arc_flag_when_under_50(self):
        d, _ = pie_path(25)
        # large-arc-flag should be 0
        assert " 0,1 " in d

    def test_exactly_50_percent_small_arc(self):
        d, _ = pie_path(50)
        assert " 0,1 " in d

    def test_zero_percent(self):
        d, is_full = pie_path(0)
        assert is_full is False

    def test_custom_params(self):
        d, is_full = pie_path(100, cx=58, cy=58, r=48)
        assert is_full is True

    def test_percentage_as_string(self):
        d, is_full = pie_path("100")
        assert is_full is True


# ── load_csv ──────────────────────────────────────────────────────────────────

class TestLoadCsv:
    def test_loads_csv_as_list_of_dicts(self, tmp_path):
        f = tmp_path / "test.csv"
        f.write_text("name,age\nAlice,30\nBob,25\n", encoding="utf-8")
        rows = load_csv(f)
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"
        assert rows[1]["age"] == "25"

    def test_empty_csv_returns_empty_list(self, tmp_path):
        f = tmp_path / "empty.csv"
        f.write_text("name,age\n", encoding="utf-8")
        rows = load_csv(f)
        assert rows == []

    def test_preserves_column_order_as_keys(self, tmp_path):
        f = tmp_path / "cols.csv"
        f.write_text("turma,aula_num,date\nMASTER,1,10/02/2026\n", encoding="utf-8")
        rows = load_csv(f)
        assert list(rows[0].keys()) == ["turma", "aula_num", "date"]

    def test_utf8_encoding(self, tmp_path):
        f = tmp_path / "utf8.csv"
        f.write_text("nome\nAudiçãó\n", encoding="utf-8")
        rows = load_csv(f)
        assert rows[0]["nome"] == "Audiçãó"

    def test_raises_for_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_csv(tmp_path / "nonexistent.csv")


# ── int_score ─────────────────────────────────────────────────────────────────

class TestIntScore:
    def test_normal_value(self):
        assert int_score("3") == 3

    def test_clamps_above_5(self):
        assert int_score("10") == 5

    def test_clamps_below_1(self):
        assert int_score("0") == 1

    def test_negative_clamps_to_1(self):
        assert int_score("-3") == 1

    def test_float_string_rounds(self):
        assert int_score("3.7") == 3  # int(float("3.7")) = 3

    def test_none_returns_default(self):
        assert int_score(None) == 3

    def test_empty_string_returns_default(self):
        assert int_score("") == 3

    def test_invalid_string_returns_default(self):
        assert int_score("abc") == 3

    def test_custom_default(self):
        assert int_score(None, default=0) == 0

    def test_integer_input(self):
        assert int_score(4) == 4

    def test_boundary_value_1(self):
        assert int_score("1") == 1

    def test_boundary_value_5(self):
        assert int_score("5") == 5

    def test_value_exactly_at_ceiling(self):
        assert int_score("5.0") == 5


# ── avg_score ─────────────────────────────────────────────────────────────────

class TestAvgScore:
    def test_empty_list_returns_zero(self):
        assert avg_score([]) == 0

    def test_single_value(self):
        assert avg_score([4]) == 4

    def test_average_rounds(self):
        # (3 + 4) / 2 = 3.5 → rounds to 4 in Python (banker's rounding may vary)
        result = avg_score([3, 4])
        assert result in (3, 4)  # allow both banker's rounding behaviors

    def test_all_same(self):
        assert avg_score([3, 3, 3]) == 3

    def test_mixed_values(self):
        # (1+2+3+4+5)/5 = 3.0
        assert avg_score([1, 2, 3, 4, 5]) == 3

    def test_string_values_are_accepted(self):
        assert avg_score(["3", "3", "3"]) == 3

    def test_empty_string_excluded(self):
        # Empty strings are filtered by str(s).strip() check
        assert avg_score(["3", "", "3"]) == 3

    def test_whitespace_string_excluded(self):
        assert avg_score(["4", "  ", "4"]) == 4

    def test_returns_int_type(self):
        result = avg_score([3, 3, 3])
        assert isinstance(result, int)


# ── presence_pct ──────────────────────────────────────────────────────────────

class TestPresencePct:
    def test_zero_total_returns_100(self):
        assert presence_pct(0, 0) == 100

    def test_no_absences(self):
        assert presence_pct(0, 10) == 100

    def test_one_absence(self):
        assert presence_pct(1, 10) == 90

    def test_all_absent(self):
        assert presence_pct(10, 10) == 0

    def test_none_faltas_treated_as_zero(self):
        assert presence_pct(None, 10) == 100

    def test_rounding(self):
        # (10 - 3) / 10 = 0.7 → 70
        assert presence_pct(3, 10) == 70

    def test_fractional_result_rounds(self):
        # (11 - 1) / 11 = 0.909... → 91
        assert presence_pct(1, 11) == 91

    def test_string_faltas(self):
        # int("2") = 2; (10 - 2) / 10 = 0.8 → 80
        assert presence_pct("2", 10) == 80


# ── pres_to_score ─────────────────────────────────────────────────────────────

class TestPresToScore:
    def test_100_pct_gives_5(self):
        assert pres_to_score(100) == 5

    def test_95_pct_gives_5(self):
        assert pres_to_score(95) == 5

    def test_94_pct_gives_4(self):
        assert pres_to_score(94) == 4

    def test_85_pct_gives_4(self):
        assert pres_to_score(85) == 4

    def test_84_pct_gives_3(self):
        assert pres_to_score(84) == 3

    def test_75_pct_gives_3(self):
        assert pres_to_score(75) == 3

    def test_74_pct_gives_2(self):
        assert pres_to_score(74) == 2

    def test_65_pct_gives_2(self):
        assert pres_to_score(65) == 2

    def test_64_pct_gives_1(self):
        assert pres_to_score(64) == 1

    def test_0_pct_gives_1(self):
        assert pres_to_score(0) == 1


# ── missed_lessons ────────────────────────────────────────────────────────────

class TestMissedLessons:
    def test_empty_missed_aulas_returns_empty(self):
        student = {"turma": "MASTER", "missed_aulas": ""}
        assert missed_lessons(student, SAMPLE_LESSONS) == []

    def test_no_missed_aulas_key_returns_empty(self):
        student = {"turma": "MASTER"}
        assert missed_lessons(student, SAMPLE_LESSONS) == []

    def test_single_missed_lesson(self):
        student = {"turma": "MASTER", "missed_aulas": "2"}
        result = missed_lessons(student, SAMPLE_LESSONS)
        assert len(result) == 1
        assert result[0]["aula_num"] == "2"
        assert result[0]["turma"] == "MASTER"

    def test_multiple_missed_lessons(self):
        student = {"turma": "MASTER", "missed_aulas": "1,3"}
        result = missed_lessons(student, SAMPLE_LESSONS)
        assert len(result) == 2
        aula_nums = {r["aula_num"] for r in result}
        assert aula_nums == {"1", "3"}

    def test_only_returns_lessons_for_student_turma(self):
        student = {"turma": "INSPIRE", "missed_aulas": "1"}
        result = missed_lessons(student, SAMPLE_LESSONS)
        assert all(r["turma"] == "INSPIRE" for r in result)

    def test_nonexistent_lesson_number_ignored(self):
        student = {"turma": "MASTER", "missed_aulas": "99"}
        result = missed_lessons(student, SAMPLE_LESSONS)
        assert result == []

    def test_whitespace_in_missed_aulas_handled(self):
        student = {"turma": "MASTER", "missed_aulas": " 1 , 2 "}
        result = missed_lessons(student, SAMPLE_LESSONS)
        assert len(result) == 2

    def test_empty_aula_num_in_lessons_excluded(self):
        # SPARK lesson has empty aula_num — should not appear in missed lessons
        student = {"turma": "SPARK", "missed_aulas": ""}
        result = missed_lessons(student, SAMPLE_LESSONS)
        assert result == []


# ── lessons_for ───────────────────────────────────────────────────────────────

class TestLessonsFor:
    def test_returns_only_matching_turma(self):
        result = lessons_for("MASTER", SAMPLE_LESSONS)
        assert all(r["turma"] == "MASTER" for r in result)

    def test_returns_correct_count(self):
        result = lessons_for("MASTER", SAMPLE_LESSONS)
        assert len(result) == 3

    def test_excludes_empty_aula_num(self):
        # SPARK has a lesson with empty aula_num
        result = lessons_for("SPARK", SAMPLE_LESSONS)
        assert all(r["aula_num"].strip() for r in result)

    def test_unknown_turma_returns_empty(self):
        result = lessons_for("UNKNOWN", SAMPLE_LESSONS)
        assert result == []

    def test_empty_lessons_list(self):
        result = lessons_for("MASTER", [])
        assert result == []


# ── needs_extra ───────────────────────────────────────────────────────────────

class TestNeedsExtra:
    def test_reforco_ascii_returns_true(self):
        assert needs_extra({"aula_extra": "reforco"}) is True

    def test_reforco_accented_returns_true(self):
        assert needs_extra({"aula_extra": "reforço"}) is True

    def test_reposicao_ascii_returns_true(self):
        assert needs_extra({"aula_extra": "reposicao"}) is True

    def test_reposicao_accented_returns_true(self):
        assert needs_extra({"aula_extra": "reposição"}) is True

    def test_case_insensitive_upper(self):
        assert needs_extra({"aula_extra": "Reforço"}) is True

    def test_case_insensitive_all_caps(self):
        assert needs_extra({"aula_extra": "REFORÇO"}) is True

    def test_empty_string_returns_false(self):
        assert needs_extra({"aula_extra": ""}) is False

    def test_missing_key_returns_false(self):
        assert needs_extra({}) is False

    def test_other_value_returns_false(self):
        assert needs_extra({"aula_extra": "outro"}) is False

    def test_whitespace_stripped(self):
        assert needs_extra({"aula_extra": "  reforço  "}) is True


# ── group_by_turma ────────────────────────────────────────────────────────────

class TestGroupByTurma:
    def test_single_turma(self):
        students = [
            {"turma": "MASTER", "student_name": "Alice"},
            {"turma": "MASTER", "student_name": "Bob"},
        ]
        groups = group_by_turma(students)
        assert "MASTER" in groups
        assert len(groups["MASTER"]) == 2

    def test_multiple_turmas(self):
        students = [
            {"turma": "MASTER", "student_name": "Alice"},
            {"turma": "INSPIRE", "student_name": "Bob"},
            {"turma": "MASTER", "student_name": "Carol"},
        ]
        groups = group_by_turma(students)
        assert set(groups.keys()) == {"MASTER", "INSPIRE"}
        assert len(groups["MASTER"]) == 2
        assert len(groups["INSPIRE"]) == 1

    def test_empty_list_returns_empty_dict(self):
        assert group_by_turma([]) == {}

    def test_preserves_student_order_within_turma(self):
        students = [
            {"turma": "MASTER", "student_name": "Alice"},
            {"turma": "MASTER", "student_name": "Bob"},
        ]
        groups = group_by_turma(students)
        assert groups["MASTER"][0]["student_name"] == "Alice"
        assert groups["MASTER"][1]["student_name"] == "Bob"


# ── build_student_ctx ─────────────────────────────────────────────────────────

class TestBuildStudentCtx:
    def test_returns_required_keys(self):
        ctx = build_student_ctx(SAMPLE_STUDENT, SAMPLE_LESSONS)
        required = [
            "student", "pct", "pie_d", "full_circle", "missed",
            "pres_score", "needs_makeup", "part_scores", "part_overall",
            "dev_scores", "dev_overall", "dev_labels",
            "pentagon", "grid", "axes",
            "comp_scores", "comp_overall",
        ]
        for key in required:
            assert key in ctx, f"Missing key: {key}"

    def test_student_reference(self):
        ctx = build_student_ctx(SAMPLE_STUDENT, SAMPLE_LESSONS)
        assert ctx["student"] is SAMPLE_STUDENT

    def test_pct_is_integer(self):
        ctx = build_student_ctx(SAMPLE_STUDENT, SAMPLE_LESSONS)
        assert isinstance(ctx["pct"], int)

    def test_dev_labels_correct(self):
        ctx = build_student_ctx(SAMPLE_STUDENT, SAMPLE_LESSONS)
        assert ctx["dev_labels"] == ["Audição", "Fala", "Gramática", "Escrita", "Leitura"]

    def test_dev_scores_length(self):
        ctx = build_student_ctx(SAMPLE_STUDENT, SAMPLE_LESSONS)
        assert len(ctx["dev_scores"]) == 5

    def test_part_scores_length(self):
        ctx = build_student_ctx(SAMPLE_STUDENT, SAMPLE_LESSONS)
        assert len(ctx["part_scores"]) == 3

    def test_comp_scores_length(self):
        ctx = build_student_ctx(SAMPLE_STUDENT, SAMPLE_LESSONS)
        assert len(ctx["comp_scores"]) == 3

    def test_grid_has_five_rings(self):
        ctx = build_student_ctx(SAMPLE_STUDENT, SAMPLE_LESSONS)
        assert len(ctx["grid"]) == 5

    def test_axes_has_five_endpoints(self):
        ctx = build_student_ctx(SAMPLE_STUDENT, SAMPLE_LESSONS)
        assert len(ctx["axes"]) == 5

    def test_missed_lessons_populated(self):
        ctx = build_student_ctx(SAMPLE_STUDENT, SAMPLE_LESSONS)
        # SAMPLE_STUDENT has missed_aulas="2", turma="MASTER", which exists in SAMPLE_LESSONS
        assert len(ctx["missed"]) == 1
        assert ctx["missed"][0]["aula_num"] == "2"

    def test_needs_makeup_false_when_no_reposicao(self):
        ctx = build_student_ctx(SAMPLE_STUDENT, SAMPLE_LESSONS)
        assert ctx["needs_makeup"] is False

    def test_needs_makeup_true_for_reposicao(self):
        s = {**SAMPLE_STUDENT, "aula_extra": "reposição"}
        ctx = build_student_ctx(s, SAMPLE_LESSONS)
        assert ctx["needs_makeup"] is True

    def test_needs_makeup_false_for_reforco(self):
        s = {**SAMPLE_STUDENT, "aula_extra": "reforço"}
        ctx = build_student_ctx(s, SAMPLE_LESSONS)
        assert ctx["needs_makeup"] is False

    def test_full_circle_when_no_lessons(self):
        # When there are no lessons for the turma, presence_pct returns 100 → full circle
        s = {**SAMPLE_STUDENT, "faltas": "0", "missed_aulas": ""}
        ctx = build_student_ctx(s, [])  # no lessons → total=0 → pct=100
        assert ctx["full_circle"] is True
        assert ctx["pct"] == 100

    def test_faltas_zero_is_clamped_to_one_by_int_score(self):
        # int_score always returns 1-5, so faltas="0" is treated as 1 absence
        # With 3 MASTER lessons and effective faltas=1: pct = (3-1)/3*100 = 67
        s = {**SAMPLE_STUDENT, "faltas": "0", "missed_aulas": ""}
        ctx = build_student_ctx(s, SAMPLE_LESSONS)
        assert ctx["pct"] == 67
        assert ctx["full_circle"] is False

    def test_dev_scores_clamped(self):
        s = {**SAMPLE_STUDENT, "speaking": "10", "listening": "-1"}
        ctx = build_student_ctx(s, SAMPLE_LESSONS)
        assert ctx["dev_scores"][1] == 5  # speaking clamped to 5
        assert ctx["dev_scores"][0] == 1  # listening clamped to 1

    def test_comportamento_fallback_for_missing_fields(self):
        # If organizacao is missing, should fall back to comportamento
        s = {**SAMPLE_STUDENT}
        s_copy = {k: v for k, v in s.items() if k not in ("organizacao", "pontualidade", "respeito_regras")}
        s_copy["comportamento"] = "4"
        ctx = build_student_ctx(s_copy, SAMPLE_LESSONS)
        # All comp_scores should equal 4 (from comportamento)
        assert ctx["comp_scores"] == [4, 4, 4]

    def test_pentagon_is_string(self):
        ctx = build_student_ctx(SAMPLE_STUDENT, SAMPLE_LESSONS)
        assert isinstance(ctx["pentagon"], str)

    def test_empty_lessons_gives_100_pct(self):
        ctx = build_student_ctx(SAMPLE_STUDENT, [])
        assert ctx["pct"] == 100


# ── build_class_ctx ───────────────────────────────────────────────────────────

class TestBuildClassCtx:
    def setup_method(self):
        self.student_a = {**SAMPLE_STUDENT, "student_name": "Alice"}
        self.student_b = {**SAMPLE_STUDENT, "student_name": "Bob"}

    def test_returns_required_keys(self):
        ctx = build_class_ctx("MASTER", [self.student_a], SAMPLE_LESSONS)
        required = ["turma", "turma_display", "nivel", "horario", "teacher", "lessons", "students", "grid", "axes"]
        for key in required:
            assert key in ctx, f"Missing key: {key}"

    def test_turma_matches(self):
        ctx = build_class_ctx("MASTER", [self.student_a], SAMPLE_LESSONS)
        assert ctx["turma"] == "MASTER"

    def test_turma_display_from_first_student(self):
        ctx = build_class_ctx("MASTER", [self.student_a], SAMPLE_LESSONS)
        assert ctx["turma_display"] == "Masters"

    def test_students_list_length(self):
        ctx = build_class_ctx("MASTER", [self.student_a, self.student_b], SAMPLE_LESSONS)
        assert len(ctx["students"]) == 2

    def test_each_student_is_full_ctx(self):
        ctx = build_class_ctx("MASTER", [self.student_a], SAMPLE_LESSONS)
        student_ctx = ctx["students"][0]
        assert "dev_scores" in student_ctx
        assert "pct" in student_ctx

    def test_lessons_filtered_by_turma(self):
        ctx = build_class_ctx("MASTER", [self.student_a], SAMPLE_LESSONS)
        assert all(l["turma"] == "MASTER" for l in ctx["lessons"])

    def test_grid_has_five_rings(self):
        ctx = build_class_ctx("MASTER", [self.student_a], SAMPLE_LESSONS)
        assert len(ctx["grid"]) == 5

    def test_axes_has_five_endpoints(self):
        ctx = build_class_ctx("MASTER", [self.student_a], SAMPLE_LESSONS)
        assert len(ctx["axes"]) == 5

    def test_nivel_and_horario_from_first_student(self):
        ctx = build_class_ctx("MASTER", [self.student_a], SAMPLE_LESSONS)
        assert ctx["nivel"] == SAMPLE_STUDENT["nivel"]
        assert ctx["horario"] == SAMPLE_STUDENT["horario"]

    def test_turma_display_defaults_to_turma_if_missing(self):
        s = {k: v for k, v in self.student_a.items() if k != "turma_display"}
        ctx = build_class_ctx("MASTER", [s], SAMPLE_LESSONS)
        assert ctx["turma_display"] == "MASTER"


# ── generate_individual_reports ───────────────────────────────────────────────

class TestGenerateIndividualReports:
    def test_creates_html_files(self, tmp_path):
        from jinja2 import Environment, FileSystemLoader
        templates_dir = Path(__file__).parent / "templates"
        if not templates_dir.exists():
            pytest.skip("templates directory not found")
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
        student = {**SAMPLE_STUDENT, "missed_aulas": ""}
        generate_individual_reports([student], SAMPLE_LESSONS, env, tmp_path)
        files = list(tmp_path.glob("*.html"))
        assert len(files) == 1

    def test_filename_format(self, tmp_path):
        from jinja2 import Environment, FileSystemLoader
        templates_dir = Path(__file__).parent / "templates"
        if not templates_dir.exists():
            pytest.skip("templates directory not found")
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
        student = {**SAMPLE_STUDENT, "student_name": "John Doe", "missed_aulas": ""}
        generate_individual_reports([student], SAMPLE_LESSONS, env, tmp_path)
        expected_file = tmp_path / "MASTER_John_Doe_report.html"
        assert expected_file.exists()

    def test_html_content_contains_student_name(self, tmp_path):
        from jinja2 import Environment, FileSystemLoader
        templates_dir = Path(__file__).parent / "templates"
        if not templates_dir.exists():
            pytest.skip("templates directory not found")
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
        student = {**SAMPLE_STUDENT, "student_name": "Maria Test", "missed_aulas": ""}
        generate_individual_reports([student], SAMPLE_LESSONS, env, tmp_path)
        html_file = tmp_path / "MASTER_Maria_Test_report.html"
        content = html_file.read_text(encoding="utf-8")
        assert "Maria Test" in content

    def test_generates_multiple_files(self, tmp_path):
        from jinja2 import Environment, FileSystemLoader
        templates_dir = Path(__file__).parent / "templates"
        if not templates_dir.exists():
            pytest.skip("templates directory not found")
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
        s1 = {**SAMPLE_STUDENT, "student_name": "Alice One", "missed_aulas": ""}
        s2 = {**SAMPLE_STUDENT, "student_name": "Bob Two", "missed_aulas": ""}
        generate_individual_reports([s1, s2], SAMPLE_LESSONS, env, tmp_path)
        files = list(tmp_path.glob("*.html"))
        assert len(files) == 2


# ── generate_class_diagnostics ────────────────────────────────────────────────

class TestGenerateClassDiagnostics:
    def test_creates_html_file(self, tmp_path):
        from jinja2 import Environment, FileSystemLoader
        templates_dir = Path(__file__).parent / "templates"
        if not templates_dir.exists():
            pytest.skip("templates directory not found")
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
        student = {**SAMPLE_STUDENT, "missed_aulas": ""}
        generate_class_diagnostics([student], SAMPLE_LESSONS, env, tmp_path)
        expected_file = tmp_path / "MASTER_class_diagnostic.html"
        assert expected_file.exists()

    def test_filename_format(self, tmp_path):
        from jinja2 import Environment, FileSystemLoader
        templates_dir = Path(__file__).parent / "templates"
        if not templates_dir.exists():
            pytest.skip("templates directory not found")
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
        student = {**SAMPLE_STUDENT, "turma": "TESTCLASS", "missed_aulas": ""}
        generate_class_diagnostics([student], SAMPLE_LESSONS, env, tmp_path)
        expected_file = tmp_path / "TESTCLASS_class_diagnostic.html"
        assert expected_file.exists()

    def test_html_contains_turma_display(self, tmp_path):
        from jinja2 import Environment, FileSystemLoader
        templates_dir = Path(__file__).parent / "templates"
        if not templates_dir.exists():
            pytest.skip("templates directory not found")
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
        student = {**SAMPLE_STUDENT, "missed_aulas": ""}
        generate_class_diagnostics([student], SAMPLE_LESSONS, env, tmp_path)
        content = (tmp_path / "MASTER_class_diagnostic.html").read_text(encoding="utf-8")
        assert "Masters" in content

    def test_generates_one_file_per_turma(self, tmp_path):
        from jinja2 import Environment, FileSystemLoader
        templates_dir = Path(__file__).parent / "templates"
        if not templates_dir.exists():
            pytest.skip("templates directory not found")
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
        s1 = {**SAMPLE_STUDENT, "turma": "MASTER", "missed_aulas": ""}
        s2 = {**SAMPLE_STUDENT, "turma": "INSPIRE", "missed_aulas": ""}
        generate_class_diagnostics([s1, s2], SAMPLE_LESSONS, env, tmp_path)
        files = list(tmp_path.glob("*_class_diagnostic.html"))
        assert len(files) == 2


# ── Integration: load real CSVs and build contexts ────────────────────────────

class TestIntegrationWithRealData:
    """Smoke tests using the actual data files shipped with the project."""

    @pytest.fixture
    def real_data(self):
        base = Path(__file__).parent
        students_file = base / "data" / "students.csv"
        lessons_file = base / "data" / "lessons.csv"
        if not students_file.exists() or not lessons_file.exists():
            pytest.skip("Real data files not found")
        students = load_csv(students_file)
        lessons = load_csv(lessons_file)
        return students, lessons

    def test_loads_expected_student_count(self, real_data):
        students, _ = real_data
        assert len(students) == 25

    def test_loads_expected_lesson_count(self, real_data):
        _, lessons = real_data
        assert len(lessons) == 59

    def test_all_students_have_student_name(self, real_data):
        students, _ = real_data
        for s in students:
            assert s.get("student_name", "").strip() != ""

    def test_group_by_turma_gives_expected_turmas(self, real_data):
        students, _ = real_data
        groups = group_by_turma(students)
        assert set(groups.keys()) == {"MASTER", "INSPIRE", "POWER", "SPARK", "BEYOND"}

    def test_build_student_ctx_for_each_real_student(self, real_data):
        students, lessons = real_data
        for s in students:
            ctx = build_student_ctx(s, lessons)
            assert 0 <= ctx["pct"] <= 100
            assert all(1 <= score <= 5 for score in ctx["dev_scores"])

    def test_build_class_ctx_for_each_turma(self, real_data):
        students, lessons = real_data
        groups = group_by_turma(students)
        for turma, group in groups.items():
            ctx = build_class_ctx(turma, group, lessons)
            assert ctx["turma"] == turma
            assert len(ctx["students"]) == len(group)

    def test_mellissa_has_reforco_flag(self, real_data):
        students, _ = real_data
        mellissa = next(s for s in students if "Mellissa" in s["student_name"])
        assert needs_extra(mellissa) is True

    def test_student_without_extra_not_flagged(self, real_data):
        students, _ = real_data
        bruna = next(s for s in students if "Bruna" in s["student_name"])
        assert needs_extra(bruna) is False
