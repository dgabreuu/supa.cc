"""Pure rendering helpers for doctor output."""

import json

from .auth import sanitize_sensitive_text


def sanitize_structure(value):
    if isinstance(value, str):
        return sanitize_sensitive_text(value)
    if isinstance(value, dict):
        return {str(key): sanitize_structure(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_structure(item) for item in value]
    return value


def render_json(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def report_to_dict(report):
    live = None
    if report.live_result is not None:
        live = {
            "ok": report.live_result.ok,
            "code": report.live_result.code.value,
            "message": sanitize_sensitive_text(report.live_result.message),
            "exit_code": report.live_result.exit_code,
        }
    return sanitize_structure({
        "ok": report.ok,
        "exit_code": report.exit_code,
        "runtime": report.runtime,
        "supabase_cli": report.supabase_cli,
        "keychain": {
            "service": report.keychain_service,
            "backend": report.keychain_backend,
        },
        "credentials": report.credentials,
        "index": report.index,
        "active_account": report.active_account,
        "environment": report.environment,
        "diagnostic_codes": report.diagnostic_codes,
        "activation": report.activation,
        "live": live,
    })


def render_human(report) -> str:
    def identity_line(label, invoked, realpath, signature):
        status = signature.get("status", "unknown") if isinstance(signature, dict) else "unknown"
        return f"{label}: {invoked or 'not identified'} -> {realpath or 'not identified'} (signature: {status})"

    cli_path = report.supabase_cli.get("realpath") or report.supabase_cli.get("path") or "not found"
    launcher = report.runtime.get("launcher")
    python = report.runtime.get("python")
    launcher = launcher if isinstance(launcher, dict) else {"invoked": launcher, "realpath": launcher}
    python = python if isinstance(python, dict) else {
        "invoked": report.runtime.get("python_executable"),
        "realpath": report.runtime.get("python_realpath"),
    }
    states = {
        "present": "present",
        "absent": "absent",
        "inaccessible": "inaccessible",
        "pending": "pending",
        "not_checked": "not checked",
    }
    diagnostics = ", ".join(code.replace("keychain", "credential_store") for code in report.diagnostic_codes) or "none"
    availability = report.credentials.get("availability")
    credential_state = {
        "available": "available (verified)",
        "unavailable": "unavailable (verified)",
        "unverified": (
            "unavailable (not verified; no probe)"
            if report.credentials.get("status") == "unavailable"
            else "configured (not verified; no probe)"
        ),
    }.get(availability, "unknown")
    index_state = report.index.get("state")
    index_summary = (
        "not checked"
        if index_state == "not_checked"
        else f"{index_state} ({report.index.get('account_count', 0)} accounts)"
    )
    lines = [
        "Supa.cc doctor",
        f"Supa.cc version: {report.runtime.get('supa_cc_version') or 'unknown'}",
        f"Installation channel: {report.runtime.get('installation_channel') or 'unknown'}",
        f"Operating system: {report.runtime.get('operating_system') or 'unknown'}",
        identity_line("Supa.cc launcher", launcher.get("invoked"), launcher.get("realpath"), launcher.get("signature")),
        identity_line("Python", python.get("invoked"), python.get("realpath"), python.get("signature")),
        identity_line("Supabase CLI", report.supabase_cli.get("invoked") or cli_path, report.supabase_cli.get("realpath") or cli_path, report.supabase_cli.get("signature")),
        f"Supabase CLI version: {report.supabase_cli.get('version') or 'unknown'}",
        f"Supabase CLI minimum version: {report.supabase_cli.get('minimum_version') or 'unknown'}",
        f"Supabase CLI compatibility: {report.supabase_cli.get('compatibility') or 'not_checked'}",
        f"Provenance: {report.supabase_cli.get('provenance') or 'unknown'}",
        f"Credential store: {report.credentials.get('backend', report.keychain_backend)} ({credential_state})",
        f"Index: {index_summary}",
        "Active account: "
        + (
            "not checked"
            if report.active_account.get("checked") is False
            else "selected (indexed)"
            if report.active_account.get("selected") and report.active_account.get("indexed")
            else "selected (not indexed)"
            if report.active_account.get("selected")
            else "not selected"
        ),
        "SUPABASE_ACCESS_TOKEN in environment: " + ("present" if report.environment.get("supabase_access_token_present") else "absent"),
        f"Diagnostics: {diagnostics}",
        f"Activation: {report.activation.get('mode', 'unknown')} (native session: {report.activation.get('native_session', 'unknown')}; profile: {report.activation.get('profile', 'unknown')})",
        "Synchronization journal: " + states.get(report.activation.get("journal_state", "absent"), "unknown"),
        "Plaintext fallback: " + states.get(report.activation.get("plaintext_fallback_state", "absent"), "unknown"),
    ]
    if report.runtime.get("linux_distribution"):
        lines.append(f"Linux distribution: {report.runtime['linux_distribution']}")
    if report.credentials.get("remediation"):
        lines.append(f"Remediation: {report.credentials['remediation']}")
    if report.live_result is not None:
        lines.append(f"Live validation: {report.live_result.code.value} - {sanitize_sensitive_text(report.live_result.message)}")
    return sanitize_sensitive_text("\n".join(lines))
