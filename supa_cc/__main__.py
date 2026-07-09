import subprocess
import click
import supa_cc
from .tui import run as run_tui
from .strings import CLIStrings as Textos

UPGRADE_HINT = "brew upgrade supa-cc ou brew upgrade --fetch-HEAD supa-cc; para pipx: pipx upgrade supa.cc"


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
        run_tui()


@main.command()
def version():
    """Mostra a versão e verifica atualizações."""
    click.echo(f"Supa.cc v{supa_cc.__version__}")
    click.echo(_check_for_updates())


@main.command()
@click.argument("name")
@click.option("--token", prompt=True, hide_input=True)
def add(name, token):
    """Adicionar nova conta."""
    from .accounts import AccountManager
    manager = AccountManager()
    try:
        manager.add(name, token)
        click.echo(Textos.MSG_ACCOUNT_ADDED.format(name))
    except ValueError as e:
        msg = str(e)
        # Sanitiza mensagem para evitar vazamento de token
        if "sbp_" in msg:
            msg = "Erro de validação. Verifique os dados fornecidos."
        click.echo(Textos.MSG_ERROR.format(msg))


@main.command()
def list():
    """Listar contas cadastradas."""
    from .accounts import AccountManager
    manager = AccountManager()
    accounts = manager.list()
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
    if manager.set_active(name):
        click.echo(Textos.MSG_ACCOUNT_ACTIVATED.format(name))
    else:
        click.echo(Textos.MSG_ACTIVATE_FAILED.format(name))


@main.command()
@click.argument("name")
@click.confirmation_option(prompt=Textos.MSG_CONFIRM_REMOVE)
def remove(name):
    """Remover conta cadastrada."""
    from .accounts import AccountManager
    manager = AccountManager()
    manager.remove(name)
    click.echo(Textos.MSG_ACCOUNT_REMOVED.format(name))


if __name__ == "__main__":
    main()
