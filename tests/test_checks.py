from pathlib import Path

import pytest

from safety_agent.checks import run_all_checks
from safety_agent.checks.action_priority import action_priority
from safety_agent.loaders import load_project
from safety_agent.models import Asil, FmeaRow, Project, Requirement

EX = Path(__file__).parent.parent / "examples"


def codes(findings, target=None):
    return {f.code for f in findings if target is None or f.target == target}


@pytest.mark.parametrize("s,o,d,expected", [
    (10, 10, 10, "H"), (9, 4, 1, "M"), (9, 2, 5, "M"), (9, 2, 2, "L"), (9, 1, 10, "L"),
    (8, 6, 1, "M"), (7, 4, 7, "H"), (7, 2, 7, "M"), (5, 8, 7, "H"), (5, 8, 4, "M"),
    (4, 6, 1, "L"), (3, 9, 6, "M"), (3, 9, 4, "L"), (1, 10, 10, "L"),
])
def test_action_priority(s, o, d, expected):
    assert action_priority(s, o, d) == expected


def test_action_priority_rejects_out_of_scale():
    with pytest.raises(ValueError):
        action_priority(11, 1, 1)


@pytest.mark.parametrize("raw,level,origin", [
    ("C", "C", None), ("ASIL B(D)", "B", "D"), ("qm(b)", "QM", "B"), ("ASIL A (ASIL C)", "A", "C"),
])
def test_asil_parse(raw, level, origin):
    a = Asil.parse(raw)
    assert (a.level, a.decomposed_from) == (level, origin)


def _project(*reqs, fmea=()):
    return Project({r.id: r for r in reqs}, {f.id: f for f in fmea})


SG = Requirement("SG", "Le système doit éviter X.", "SG", "ASIL D")


def test_valid_decomposition():
    p = _project(SG,
                 Requirement("A", "Le capteur doit détecter X.", "FSR", "C(D)", ["SG"], "Test"),
                 Requirement("B", "Le moniteur doit détecter X.", "FSR", "A(D)", ["SG"], "Test"))
    c = codes(run_all_checks(p))
    assert "REQ-034" in c and "REQ-033" not in c and "REQ-031" not in c


def test_invalid_decomposition():
    p = _project(SG,
                 Requirement("A", "Le capteur doit détecter X.", "FSR", "B(D)", ["SG"], "Test"),
                 Requirement("B", "Le moniteur doit détecter X.", "FSR", "A(D)", ["SG"], "Test"))
    assert "REQ-033" in codes(run_all_checks(p))


def test_decomposition_from_wrong_asil():
    p = _project(SG, Requirement("A", "Le capteur doit détecter X.", "FSR", "B(C)", ["SG"], "Test"))
    assert "REQ-030" in codes(run_all_checks(p), "A")


def test_cycle_detected():
    p = _project(SG,
                 Requirement("A", "Le BMS doit faire X.", "FSR", "D", ["B"], "Test"),
                 Requirement("B", "Le BMS doit faire Y.", "FSR", "D", ["A"], "Test"))
    assert "REQ-014" in codes(run_all_checks(p), "A")


def test_wording_checks():
    p = _project(SG, Requirement("A", "Le BMS doit réagir rapidement et doit alerter le conducteur.", "FSR", "D", ["SG"], "Test"))
    c = codes(run_all_checks(p), "A")
    assert {"REQ-021", "REQ-023", "REQ-024"} <= c


def test_quantified_timing_is_ok():
    p = _project(SG, Requirement("A", "Le BMS doit ouvrir les contacteurs dans un délai de 100 ms.", "FSR", "D", ["SG"], "Test"))
    assert "REQ-024" not in codes(run_all_checks(p), "A")


def test_critical_fmea_without_requirement():
    p = _project(SG, fmea=[FmeaRow("F1", failure_mode="Perte", effect="E", cause="C", severity=10,
                                   occurrence=5, detection=5, actions="Ajouter un diagnostic")])
    assert "FMEA-021" in codes(run_all_checks(p), "F1")


def test_example_files_load_and_find_seeded_issues():
    project, load_findings = load_project(EX / "bms_exigences.csv", EX / "bms_amdec.csv")
    assert len(project.requirements) == 11 and len(project.fmea) == 6
    assert project.fmea["FM-01"].requirement_ids == ["FSR-01", "FSR-03"]
    f = load_findings + run_all_checks(project)
    assert "REQ-031" in codes(f, "FSR-05")
    assert "REQ-013" in codes(f, "TSR-02")
    assert "REQ-012" in codes(f, "SW-01")
    assert "FMEA-010" in codes(f, "FM-01")
    assert "FMEA-020" in codes(f, "FM-04")
    assert "FMEA-001" in codes(f, "FM-06")
    assert "TRA-001" in codes(f, "SG-02")


def test_comma_csv_and_english_headers(tmp_path):
    path = tmp_path / "reqs.csv"
    path.write_text("Requirement ID,Description,Type,ASIL,Derived from,Verification method\n"
                    "SG-1,The system shall avoid X.,SG,D,,\n", encoding="utf-8")
    project, _ = load_project(path, None)
    assert project.requirements["SG-1"].asil.level == "D"


def test_xlsx_loading(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    wb.active.append(["ID", "Mode de défaillance", "Gravité", "Occurrence", "Détection"])
    wb.active.append(["F1", "Perte", 9, 4, 3])
    wb.save(tmp_path / "a.xlsx")
    project, _ = load_project(None, tmp_path / "a.xlsx")
    assert project.fmea["F1"].severity == 9
