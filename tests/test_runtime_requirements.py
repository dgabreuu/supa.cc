from scripts.runtime_requirements import runtime_requirements


def test_runtime_audit_input_contains_only_declared_runtime_dependencies():
    assert runtime_requirements() == [
        "questionary>=2.0.0",
        "keyring>=24.0.0",
        "click>=8.0.0",
        "rich>=13.0.0",
    ]
