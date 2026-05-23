from compiler import (
    build_student_ctx,
    group_by_turma,
    int_score,
    needs_extra,
    pie_path,
    pres_to_score,
    presence_pct,
)


def _student(**overrides):
    base = {
        "teacher": "Chuck",
        "turma": "MASTER",
        "turma_display": "Masters",
        "nivel": "Adults Book 4",
        "horario": "Tue/Thu 19:00",
        "student_name": "Jane Doe",
        "participacao": "4",
        "comportamento": "3",
        "speaking": "4",
        "listening": "5",
        "foco": "4",
        "writing": "3",
        "reading": "4",
        "gramatica": "2",
        "trabalho_equipe": "",
        "organizacao": "",
        "pontualidade": "",
        "respeito_regras": "",
        "faltas": "1",
        "missed_aulas": "2",
        "aula_extra": "Reposicao",
        "feedback_participacao": "",
        "feedback_foco": "",
        "feedback_trabalho_equipe": "",
        "recomendacoes": "",
        "observacao": "",
    }
    base.update(overrides)
    return base


def _lessons():
    return [
        {
            "turma": "MASTER",
            "aula_num": "1",
            "date": "01/01",
            "licao_conteudo": "L1",
            "atividade_extra": "",
            "habilidades": "",
        },
        {
            "turma": "MASTER",
            "aula_num": "2",
            "date": "03/01",
            "licao_conteudo": "L2",
            "atividade_extra": "",
            "habilidades": "",
        },
    ]


def test_presence_score_mapping_boundaries():
    assert pres_to_score(95) == 5
    assert pres_to_score(85) == 4
    assert pres_to_score(75) == 3
    assert pres_to_score(65) == 2
    assert pres_to_score(64) == 1


def test_presence_pct_zero_lessons_defaults_to_100():
    assert presence_pct(0, 0) == 100


def test_int_score_clamps_and_defaults():
    assert int_score("9") == 5
    assert int_score("0") == 1
    assert int_score("not-a-number", default=2) == 2


def test_pie_path_full_circle_flag_when_100_percent():
    path_d, full = pie_path(100)
    assert full is True
    assert "A 48,48" in path_d


def test_build_student_ctx_computes_expected_derived_values():
    ctx = build_student_ctx(_student(), _lessons())
    assert ctx["pct"] == 50
    assert ctx["pres_score"] == 1
    assert ctx["needs_makeup"] is True
    assert ctx["part_scores"] == [4, 4, 3]
    assert ctx["comp_scores"] == [3, 3, 3]
    assert len(ctx["missed"]) == 1


def test_needs_extra_accepts_accented_and_unaccented_values():
    assert needs_extra(_student(aula_extra="Reforco")) is True
    assert needs_extra(_student(aula_extra="Reposicao")) is True
    assert needs_extra(_student(aula_extra="")) is False


def test_group_by_turma_groups_students():
    groups = group_by_turma([
        _student(student_name="A", turma="MASTER"),
        _student(student_name="B", turma="MASTER"),
        _student(student_name="C", turma="SPARK"),
    ])
    assert sorted(groups.keys()) == ["MASTER", "SPARK"]
    assert len(groups["MASTER"]) == 2


def test_individual_report_renders_labeled_overall_scores():
    from pathlib import Path

    from jinja2 import Environment, FileSystemLoader

    from compiler import build_student_ctx

    base = Path(__file__).resolve().parent.parent
    env = Environment(loader=FileSystemLoader(str(base / "templates")), autoescape=False)
    html = env.get_template("individual_report.html").render(
        **build_student_ctx(_student(), _lessons())
    )

    assert "card-header" in html
    assert html.count('class="overall-score-label"') == 4
    assert "bubble-abs" not in html
    assert "Nota" in html
    assert "Critérios" in html
