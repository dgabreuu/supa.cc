from pathlib import Path
import re

import tomllib


PRODUCT_DOCUMENTS = (
    Path("README.md"),
    Path("SECURITY.md"),
    Path("CHANGELOG.md"),
    Path("SKILL.md"),
    Path("docs/installation.md"),
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
)


def _product_source_files():
    return sorted(Path("supa_cc").rglob("*.py"))


def test_project_declares_english_as_its_only_natural_language():
    with Path("pyproject.toml").open("rb") as pyproject_file:
        project = tomllib.load(pyproject_file)["project"]

    natural_languages = [
        classifier
        for classifier in project["classifiers"]
        if classifier.startswith("Natural Language ::")
    ]

    assert natural_languages == ["Natural Language :: English"]


def test_product_source_and_documents_contain_no_portuguese_text():
    files = (*_product_source_files(), *PRODUCT_DOCUMENTS)
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
        for path in (*_product_source_files(), *PRODUCT_DOCUMENTS)
    ).casefold()

    assert "--language" not in product_text
    assert "português" not in product_text
    assert "portuguese" not in product_text
