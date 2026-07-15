import click
import supa_cc
from .auth import classify_local_failure, normalize_exit_code
from .strings import CLIStrings as Strings

def _exit_with_local_failure(error):
    result = classify_local_failure(error)
    click.echo(Strings.MSG_ERROR.format(result.message), err=True)
    raise click.exceptions.Exit(normalize_exit_code(result.exit_code) or 1)


def _exit_with_result(result):
    click.echo(result.message, err=True)
    raise click.exceptions.Exit(normalize_exit_code(result.exit_code) or 1)


def _check_for_updates():
    """Return deterministic update guidance without network or Git access."""
    from .environment import detect_environment
    from .installation import detect_installation_channel, installation_guidance

    update_hint = installation_guidance(
        detect_environment(), channel=detect_installation_channel()
    ).update_hint
    return f"Update: {update_hint}"


def _installation_channel():
    from .installation import detect_installation_channel

    return detect_installation_channel().value


def _show_version(ctx, _param, value):
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"supa.cc, version {supa_cc.__version__}")
    click.echo(f"Installation channel: {_installation_channel()}")
    ctx.exit()


def _run_tui():
    from .tui import run

    return run()


@click.group(invoke_without_command=True)
@click.option(
    "--version",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_show_version,
    help="Show the installed version and installation channel.",
)
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
    click.echo(f"Installation channel: {_installation_channel()}")
    click.echo(_check_for_updates())


@main.command()
@click.argument("name")
def add(name):
    """Add a new account."""
    from .accounts import AccountService

    token = click.prompt(
        Strings.PROMPT_ACCESS_TOKEN,
        hide_input=True,
        confirmation_prompt=False,
    )
    try:
        manager = AccountService()
        result = manager.add(name, token)
        if not result.ok:
            _exit_with_result(result)
        click.echo(Strings.MSG_ACCOUNT_ADDED.format(name))
    except Exception as error:
        _exit_with_local_failure(error)


@main.command("list")
def list_accounts_command():
    """List registered accounts."""
    from .accounts import AccountService
    try:
        manager = AccountService()
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
    from .accounts import AccountService
    try:
        manager = AccountService()
        result = manager.set_active(
            name,
            token_provider=lambda _name: click.prompt(
                Strings.PROMPT_ACCESS_TOKEN,
                hide_input=True,
                confirmation_prompt=False,
            ),
        )
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
    from .accounts import AccountService

    stdout = click.get_text_stream("stdout")
    stderr = click.get_text_stream("stderr")

    def stdout_sink(text):
        stdout.write(text)
        stdout.flush()

    def stderr_sink(text):
        stderr.write(text)
        stderr.flush()

    try:
        result = AccountService().run_active(
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
@click.option("--installation-check", is_flag=True, default=False)
@click.option("--json", "as_json", is_flag=True, default=False)
def doctor(account, live, installation_check, as_json):
    """Diagnose executables, the index, the environment, and optional authentication."""
    from .diagnostics import DiagnosticService

    if installation_check and (live or account is not None):
        raise click.UsageError(
            "--installation-check cannot be combined with --live or --account."
        )
    try:
        report = DiagnosticService().run(
            account=account,
            live=live,
            installation_check=installation_check,
        )
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
    from .accounts import AccountService
    try:
        manager = AccountService()
        result = manager.remove(name)
        if not result.ok:
            _exit_with_result(result)
    except Exception as error:
        _exit_with_local_failure(error)
    click.echo(Strings.MSG_ACCOUNT_REMOVED.format(name))


@main.command()
@click.option("--all", "reset_all", is_flag=True, required=True)
@click.option("--yes", is_flag=True, help="Skip the interactive confirmation.")
def reset(reset_all, yes):
    """Remove all Supa.cc accounts, credentials, and local session intent."""
    from .accounts import AccountService

    if not reset_all:
        raise click.UsageError("Use --all to confirm the reset scope.")
    if not yes and not click.confirm(Strings.MSG_CONFIRM_RESET, default=False):
        click.echo("Reset cancelled.")
        return
    try:
        result = AccountService().reset_all()
    except Exception as error:
        _exit_with_local_failure(error)
    if not result.ok:
        _exit_with_result(result)
    click.echo(result.message)


if __name__ == "__main__":
    main()
