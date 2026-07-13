import click
import supa_cc
from .auth import classify_local_failure, normalize_exit_code
from .strings import CLIStrings as Strings

def _exit_with_local_failure(error):
    result = classify_local_failure(error)
    click.echo(Strings.MSG_ERROR.format(result.message), err=True)
    raise click.exceptions.Exit(normalize_exit_code(result.exit_code) or 1)


def _check_for_updates():
    """Return deterministic update guidance without network or Git access."""
    from .environment import detect_environment
    from .installation import installation_guidance

    update_hint = installation_guidance(detect_environment()).update_hint
    return f"Update: {update_hint}"


def _run_tui():
    from .tui import run

    return run()


@click.group(invoke_without_command=True)
@click.version_option(version=supa_cc.__version__, prog_name="supa.cc")
@click.pass_context
def main(ctx):
    """Supabase account manager."""
    if ctx.invoked_subcommand is None:
        try:
            exit_code = _run_tui()
        except Exception as error:
            _exit_with_local_failure(error)
        if exit_code:
            ctx.exit(normalize_exit_code(exit_code) or 1)


@main.command()
def version():
    """Show the installed version and official update command."""
    click.echo(f"Supa.cc v{supa_cc.__version__}")
    click.echo(_check_for_updates())


@main.command()
@click.argument("name")
def add(name):
    """Add a new account."""
    from .accounts import AccountManager

    token = click.prompt(
        Strings.PROMPT_ACCESS_TOKEN,
        hide_input=True,
        confirmation_prompt=False,
    )
    try:
        manager = AccountManager()
        manager.add(name, token)
        click.echo(Strings.MSG_ACCOUNT_ADDED.format(name))
    except Exception as error:
        _exit_with_local_failure(error)


@main.command("list")
def list_accounts_command():
    """List registered accounts."""
    from .accounts import AccountManager
    try:
        manager = AccountManager()
        accounts = manager.list()
    except Exception as error:
        _exit_with_local_failure(error)
    if not accounts:
        click.echo(Strings.MSG_NO_ACCOUNTS)
        return

    for account in accounts:
        click.echo(f"  {account.name}")


@main.command()
@click.argument("name")
def switch(name):
    """Switch the active account."""
    from .accounts import AccountManager
    try:
        manager = AccountManager()
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
    """Run the Supabase CLI with the active account using the PAT only in the environment."""
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
    """Diagnose executables, the index, the environment, and optional authentication."""
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
@click.confirmation_option(prompt=Strings.MSG_CONFIRM_REMOVE)
def remove(name):
    """Remove a registered account."""
    from .accounts import AccountManager
    try:
        manager = AccountManager()
        manager.remove(name)
    except Exception as error:
        _exit_with_local_failure(error)
    click.echo(Strings.MSG_ACCOUNT_REMOVED.format(name))


if __name__ == "__main__":
    main()
