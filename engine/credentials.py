"""Windows user-bound DPAPI storage. No plaintext or cross-platform fallback."""

import ctypes
import json
import os
import tempfile
from pathlib import Path


class SecureStorageUnavailable(ValueError):
    pass


class CredentialStore:
    def __init__(self, directory):
        self.path = Path(directory) / "coinbase.dpapi"

    @staticmethod
    def supported():
        return os.name == "nt"

    @staticmethod
    def validate(key, secret):
        if not isinstance(key, str) or not isinstance(secret, str):
            raise ValueError("Coinbase key name and private key are required")
        if (
            not key.startswith("organizations/")
            or "/apiKeys/" not in key
            or len(key) > 512
        ):
            raise ValueError("Use a Coinbase CDP API key name")
        if (
            len(secret) > 8192
            or "PRIVATE KEY-----" not in secret
            or "-----END " not in secret
        ):
            raise ValueError("Use the private key from your Coinbase CDP key export")
        return {
            "api_key": key.strip(),
            "api_secret": secret.strip().replace("\\n", "\n"),
        }

    def _crypt(self, raw, decrypt=False):
        if not self.supported():
            raise SecureStorageUnavailable(
                "Secure Coinbase linking requires the Windows desktop app. No credentials were saved on this cloud machine."
            )

        class Blob(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("data", ctypes.POINTER(ctypes.c_ubyte)),
            ]

        buffer = ctypes.create_string_buffer(raw)
        source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        output = Blob()
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
        operation.argtypes = [
            ctypes.POINTER(Blob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(Blob),
        ]
        operation.restype = ctypes.c_int
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        if not operation(
            ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)
        ):
            raise SecureStorageUnavailable(
                "Windows could not access user-bound encrypted storage"
            )
        try:
            return ctypes.string_at(output.data, output.length)
        finally:
            kernel32.LocalFree(output.data)

    def save(self, credentials):
        valid = self.validate(credentials["api_key"], credentials["api_secret"])
        encrypted = self._crypt(json.dumps(valid).encode())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.path.parent, prefix=".coinbase-", delete=False
            ) as f:
                temporary = Path(f.name)
                f.write(encrypted)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def load(self):
        if not self.path.exists():
            return None
        credentials = json.loads(self._crypt(self.path.read_bytes(), decrypt=True))
        return self.validate(credentials["api_key"], credentials["api_secret"])

    def remove(self):
        self.path.unlink(missing_ok=True)
