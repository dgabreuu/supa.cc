from pathlib import Path
import re

import tomllib


CURRENT_DOCUMENTS = (
    Path("README.md"),
    Path("AGENTS.md"),
    Path("CONTRIBUTING.md"),
    Path("SECURITY.md"),
    Path("CHANGELOG.md"),
    Path(".agents/skills/supa-cc/SKILL.md"),
    Path(".agents/skills/supa-cc/references/commands.md"),
    Path(".agents/skills/supa-cc/references/safety-and-errors.md"),
    Path("docs/agent-skill.md"),
    Path("docs/installation.md"),
    Path("docs/release.md"),
    Path("docs/usage.md"),
    Path("docs/security.md"),
    Path("docs/troubleshooting.md"),
)

PORTUGUESE_MARKERS = (
    "não",
    "conta",
    "contas",
    "sessão",
    "segurança",
    "instalação",
    "instalar",
    "desinstalar",
    "diagnóstico",
    "solução",
    "problemas",
    "nenhuma",
    "adicionar",
    "alternar",
    "remover",
    "selecionar",
    "credencial",
    "armazenamento",
    "índice",
    "pendente",
    "verificação",
    "versão",
    "operação",
    "disponível",
    "informe",
    "nome",
    "falha",
    "voltar",
    "adicionada",
    "ativada",
    "removida",
    "remova",
    "somente",
    "tentou",
)


def _product_source_files():
    return sorted(Path("supa_cc").rglob("*.py"))


def _current_operational_text_files():
    return sorted(
        {
            *Path(".github/ISSUE_TEMPLATE").glob("*.yml"),
            *Path(".github/workflows").glob("*.yml"),
            *Path("scripts").glob("*.py"),
            Path("Formula/supa-cc.rb"),
            Path("assets/terminal.svg"),
            Path("pyproject.toml"),
        }
    )


def test_project_declares_english_as_its_only_natural_language():
    with Path("pyproject.toml").open("rb") as pyproject_file:
        project = tomllib.load(pyproject_file)["project"]

    natural_languages = [
        classifier
        for classifier in project["classifiers"]
        if classifier.startswith("Natural Language ::")
    ]

    assert natural_languages == ["Natural Language :: English"]


def test_current_text_surfaces_contain_no_portuguese_text():
    files = (
        *_product_source_files(),
        *_current_operational_text_files(),
        *CURRENT_DOCUMENTS,
    )
    violations = []

    for path in files:
        text = path.read_text(encoding="utf-8").casefold()
        if re.search(r"[à-öø-ÿ]", text):
            violations.append(f"{path}: accented Latin text")
        for marker in PORTUGUESE_MARKERS:
            if re.search(rf"(?<![a-z]){re.escape(marker)}(?![a-z])", text):
                violations.append(f"{path}: {marker}")

    assert not violations, "Portuguese text remains:\n" + "\n".join(violations)


def test_product_has_no_language_switch_or_portuguese_alias():
    product_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (*_product_source_files(), *CURRENT_DOCUMENTS)
    ).casefold()

    assert "--language" not in product_text
    assert "português" not in product_text
    assert "portuguese" not in product_text
