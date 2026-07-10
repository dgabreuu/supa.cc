import subprocess
import click
import supa_cc
from .auth import classify_local_failure, normalize_exit_code
from .tui import run as run_tui
from .strings import CLIStrings as Textos

UPGRADE_HINT = "brew upgrade supa-cc ou brew upgrade --fetch-HEAD supa-cc; para pipx: pipx upgrade supa.cc"


def _exit_with_local_failure(error):
    result = classify_local_failure(error)
    click.echo(Textos.MSG_ERROR.format(result.message), err=True)
    raise click.exceptions.Exit(normalize_exit_code(result.exit_code) or 1)


def _check_for_updates():
    """Verifica se há uma versão mais recente disponível."""
    import os

    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    git_dir = os.path.join(pkg_dir, ".git")

    if not os.path.isdir(git_dir):
        return f"Para verificar atualizações, clone o repositório ou execute: {UPGRADE_HINT}"

    try:
        local = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True, timeout=5, cwd=pkg_dir,
        )
        remote = subprocess.run(
            ["git", "ls-remote", "origin", "HEAD"],
            capture_output=True, text=True, check=True, timeout=5, cwd=pkg_dir,
        )
        local_hash = local.stdout.strip()
        remote_hash = remote.stdout.split()[0][:7] if remote.stdout else local_hash
        if remote_hash != local_hash:
            return f"Nova versão disponível! (local: {local_hash} → remoto: {remote_hash})"
        return "Você está na versão mais recente."
    except subprocess.CalledProcessError:
        return f"Não foi possível verificar atualizações. Verifique sua conexão ou execute: {UPGRADE_HINT}"
    except FileNotFoundError:
        return f"Git não encontrado. Para atualizar, execute: {UPGRADE_HINT}"


@click.group(invoke_without_command=True)
@click.version_option(version=supa_cc.__version__, prog_name="supa.cc")
@click.pass_context
def main(ctx):
    """Gerenciador de Contas Supabase"""
    if ctx.invoked_subcommand is None:
        exit_code = run_tui()
        if exit_code:
            ctx.exit(normalize_exit_code(exit_code) or 1)


@main.command()
def version():
    """Mostra a versão e verifica atualizações."""
    click.echo(f"Supa.cc v{supa_cc.__version__}")
    click.echo(_check_for_updates())


@main.command()
@click.argument("name")
def add(name):
    """Adicionar nova conta."""
    from .accounts import AccountManager

    token = click.prompt(
        Textos.PROMPT_ACCESS_TOKEN,
        hide_input=True,
        confirmation_prompt=False,
    )
    manager = AccountManager()
    try:
        manager.add(name, token)
        click.echo(Textos.MSG_ACCOUNT_ADDED.format(name))
    except Exception as error:
        _exit_with_local_failure(error)


@main.command("list")
def list_accounts_command():
    """Listar contas cadastradas."""
    from .accounts import AccountManager
    manager = AccountManager()
    try:
        accounts = manager.list()
    except Exception as error:
        _exit_with_local_failure(error)
    if not accounts:
        click.echo(Textos.MSG_NO_ACCOUNTS)
        return

    for account in accounts:
        click.echo(f"  {account.name}")


@main.command()
@click.argument("name")
def switch(name):
    """Alternar conta ativa."""
    from .accounts import AccountManager
    manager = AccountManager()
    try:
        result = manager.set_active(name)
    except Exception as error:
        _exit_with_local_failure(error)
    if result.ok:
        click.echo(result.message)
        return
    click.echo(result.message, err=True)
    raise click.exceptions.Exit(normalize_exit_code(result.exit_code) or 1)


@main.command(
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    }
)
@click.argument("arguments", nargs=-1, required=True, type=click.UNPROCESSED)
def run(arguments):
    """Executar a Supabase CLI com a conta ativa, usando PAT somente no ambiente."""
    from .accounts import AccountManager

    stdout = click.get_text_stream("stdout")
    stderr = click.get_text_stream("stderr")

    def stdout_sink(text):
        stdout.write(text)
        stdout.flush()

    def stderr_sink(text):
        stderr.write(text)
        stderr.flush()

    try:
        result = AccountManager().run_active(
            [argument for argument in arguments],
            stdout_sink=stdout_sink,
            stderr_sink=stderr_sink,
        )
    except Exception as error:
        _exit_with_local_failure(error)
    if not result.ok:
        click.echo(result.message, err=True)
        raise click.exceptions.Exit(normalize_exit_code(result.exit_code) or 1)


@main.command()
@click.option("--account", type=str, default=None)
@click.option("--live", is_flag=True, default=False)
@click.option("--json", "as_json", is_flag=True, default=False)
def doctor(account, live, as_json):
    """Diagnosticar executáveis, índice, ambiente e autenticação opcional."""
    from .diagnostics import DiagnosticService

    try:
        report = DiagnosticService().run(account=account, live=live)
    except Exception as error:
        _exit_with_local_failure(error)
    click.echo(report.to_json() if as_json else report.to_human())
    if not report.ok:
        raise click.exceptions.Exit(normalize_exit_code(report.exit_code) or 1)


@main.command()
@click.argument("name")
@click.confirmation_option(prompt=Textos.MSG_CONFIRM_REMOVE)
def remove(name):
    """Remover conta cadastrada."""
    from .accounts import AccountManager
    manager = AccountManager()
    try:
        manager.remove(name)
    except Exception as error:
        _exit_with_local_failure(error)
    click.echo(Textos.MSG_ACCOUNT_REMOVED.format(name))


if __name__ == "__main__":
    main()
