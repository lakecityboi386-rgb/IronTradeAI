"""Local-only Coinbase linking; no execution and no raw broker errors in responses."""

from threading import RLock
from .credentials import CredentialStore, SecureStorageUnavailable
from .coinbase_preview import CoinbasePreview


def official_client(credentials):
    try:
        from coinbase.rest import RESTClient
    except ImportError:
        raise ValueError(
            "Coinbase SDK is not installed. Install requirements-coinbase.txt in the engine Python environment."
        ) from None
    return RESTClient(
        api_key=credentials["api_key"],
        api_secret=credentials["api_secret"],
        timeout=10,
        verbose=False,
    )


class AccountLink:
    def __init__(self, directory, client_factory=official_client, store=None):
        self.store = store or CredentialStore(directory)
        self.client_factory = client_factory
        self.adapter = None
        self.lock = RLock()

    def status(self):
        with self.lock:
            return {
                "connected": self.adapter is not None,
                "secure_storage_available": self.store.supported(),
                "saved": self.store.path.exists(),
                "live_enabled": False,
                "storage": "Windows user-bound DPAPI; no browser or source-code storage",
                "scope": "Account connection only; execution requires separate activation and individual human approval",
            }

    def connect(self, key, secret, expected_fingerprint=None):
        with self.lock:
            # Reject unsupported systems before creating a client or making any account request.
            if not self.store.supported():
                raise SecureStorageUnavailable(
                    "Link your account in the Windows desktop app. Secure storage is unavailable on this cloud machine; no credentials were saved."
                )
            credentials = self.store.validate(key, secret)
            try:
                candidate = CoinbasePreview(self.client_factory(credentials))
                inspection = (
                    candidate.inspect()
                )  # Read-only permission and balance validation; never submits orders.
            except Exception:
                raise ValueError(
                    "Coinbase account verification failed. Check the key permissions, network access and SDK installation. Credentials were not saved."
                ) from None
            if (
                expected_fingerprint
                and inspection["portfolio_fingerprint"] != expected_fingerprint
            ):
                raise ValueError(
                    "This app ledger is bound to another portfolio. Reconnect the original account to preserve reconciliation."
                )
            try:
                self.store.save(credentials)
            except Exception:
                raise SecureStorageUnavailable(
                    "Windows encrypted storage failed; account was not linked."
                ) from None
            self.adapter = candidate
            return self.status()

    def restore(self):
        with self.lock:
            if not self.store.supported():
                return
            try:
                credentials = self.store.load()
                if credentials:
                    candidate = CoinbasePreview(self.client_factory(credentials))
                    candidate.inspect()
                    self.adapter = candidate
            except Exception:
                self.adapter = None  # Fail closed; never log exception text or credential material.

    def disconnect(self):
        with self.lock:
            self.adapter = None
            self.store.remove()
            return self.status()
