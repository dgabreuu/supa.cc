"""Native-session mutation primitives used by cross-feature transactions."""

from .native import NativeSessionSynchronizer


class SessionMutationService:
    def __init__(self, transaction):
        self.transaction = transaction

    def activate_after_preflight(self, account):
        native_session = self.transaction.native_session
        if isinstance(native_session, NativeSessionSynchronizer):
            return native_session._activate_preflighted(account)
        return native_session.activate(account)

    def logout_after_preflight(self):
        native_session = self.transaction.native_session
        if isinstance(native_session, NativeSessionSynchronizer):
            return native_session._logout_preflighted()
        return native_session.logout()
