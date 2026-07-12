import hashlib
import inspect

from click.testing import CliRunner


class FakeCredentialStore:
    def __init__(self):
        self.tokens = {}
        self.operations = []
        self.get_error = None
        self.set_error = None
        self.delete_error = None

    def get(self, name):
        self.operations.append(f"get:{name}")
        if self.get_error is not None:
            raise self.get_error
        return self.tokens.get(name)

    def set(self, account):
        self.operations.append(f"set:{account.name}")
        if self.set_error is not None:
            raise self.set_error
        self.tokens[account.name] = account.token

    def delete(self, name):
        self.operations.append(f"delete:{name}")
        if self.delete_error is not None:
            raise self.delete_error
        self.tokens.pop(name, None)


class MemoryActiveAccountStore:
    def __init__(self, name=None):
        self.name = name
        self.operations = []

    def read(self):
        self.operations.append("read")
        return self.name

    def write(self, name):
        self.operations.append(f"write:{name}")
        self.name = name

    def clear(self):
        self.operations.append("clear")
        self.name = None


class FaultInjectingJournal:
    def __init__(self, journal, failure_method=None, failure_call=1):
        self.journal = journal
        self.path = journal.path
        self.failure_method = failure_method
        self.failure_call = failure_call
        self.calls = {"read": 0, "write": 0, "clear": 0}

    def _invoke(self, method, *args):
        self.calls[method] += 1
        if method == self.failure_method and self.calls[method] == self.failure_call:
            raise OSError("private journal path")
        return getattr(self.journal, method)(*args)

    def read(self):
        return self._invoke("read")

    def write(self, operation, target_account, previous_account, phase):
        return self._invoke(
            "write", operation, target_account, previous_account, phase
        )

    def clear(self):
        return self._invoke("clear")


def fake_pat(value: str = "valid_token") -> str:
    body = hashlib.sha256(value.encode("utf-8")).hexdigest()[:40]
    return "sbp" + "_" + body


def fake_oauth_pat(value: str = "valid_token") -> str:
    body = hashlib.sha256(value.encode("utf-8")).hexdigest()[:40]
    return "sbp" + "_oauth_" + body


def click_runner() -> CliRunner:
    parameters = inspect.signature(CliRunner).parameters
    return CliRunner(mix_stderr=False) if "mix_stderr" in parameters else CliRunner()
