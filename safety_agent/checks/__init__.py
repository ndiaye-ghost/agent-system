from ..models import Finding, Level, Project
from .fmea import check_fmea, check_traceability
from .requirements import check_requirements

_ORDER = {Level.ERROR: 0, Level.WARNING: 1, Level.INFO: 2}


def run_all_checks(project: Project) -> list[Finding]:
    findings = check_requirements(project) + check_fmea(project) + check_traceability(project)
    return sorted(findings, key=lambda f: (_ORDER[f.level], f.code, f.target))
