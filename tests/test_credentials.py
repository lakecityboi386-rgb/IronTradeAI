import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from engine.credentials import CredentialStore, SecureStorageUnavailable
from engine.account_link import AccountLink

# Public test fixtures, not working API credentials.
KEY = "organizations/test/apiKeys/nonfunctional-fixture"
SECRET = "-----BEGIN EC PRIVATE KEY-----\nnot-a-real-key\n-----END EC PRIVATE KEY-----"


class AccountLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Mock()
        self.store.path = Path(self.tmp.name) / "fake-vault"
        self.store.supported.return_value = True
        self.store.validate.side_effect = CredentialStore.validate
        self.client = Mock()
        self.factory = Mock(return_value=self.client)
        self.client.get_api_key_permissions.return_value = {
            "portfolio_uuid": "test-portfolio",
            "can_view": True,
            "can_trade": True,
            "can_transfer": False,
        }
        self.client.get_accounts.return_value = {"accounts": []}
        self.link = AccountLink(self.tmp.name, self.factory, self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_verify_read_only_before_encrypted_save(self):
        status = self.link.connect(KEY, SECRET)
        self.assertTrue(status["connected"])
        self.assertFalse(status["live_enabled"])
        self.store.save.assert_called_once()
        self.client.create_order.assert_not_called()
        self.assertNotIn(KEY, json.dumps(status))
        self.assertNotIn(SECRET, json.dumps(status))

    def test_cloud_storage_failure_makes_no_account_request(self):
        self.store.supported.return_value = False
        with self.assertRaises(SecureStorageUnavailable):
            self.link.connect(KEY, SECRET)
        self.factory.assert_not_called()
        self.store.save.assert_not_called()

    def test_verification_error_is_redacted_and_does_not_save(self):
        self.client.get_accounts.side_effect = RuntimeError(SECRET)
        with self.assertRaises(ValueError) as exc:
            self.link.connect(KEY, SECRET)
        self.assertNotIn(SECRET, str(exc.exception))
        self.store.save.assert_not_called()

    def test_transfer_enabled_key_rejected(self):
        self.client.get_api_key_permissions.return_value["can_transfer"] = True
        with self.assertRaises(ValueError):
            self.link.connect(KEY, SECRET)
        self.store.save.assert_not_called()

    def test_unlink_removes_stored_key_and_in_memory_client(self):
        self.link.connect(KEY, SECRET)
        self.link.disconnect()
        self.assertIsNone(self.link.adapter)
        self.store.remove.assert_called_once()

    def test_restore_failure_fails_closed(self):
        self.store.load.side_effect = RuntimeError(SECRET)
        self.link.restore()
        self.assertIsNone(self.link.adapter)

    def test_invalid_key_rejected(self):
        with self.assertRaises(ValueError):
            self.link.connect("bad", "bad")
        self.factory.assert_not_called()


class NativeCredentialTests(unittest.TestCase):
    @unittest.skipUnless(
        os.name == "nt", "Windows DPAPI verification requires a Windows runner"
    )
    def test_native_dpapi_roundtrip_keeps_plaintext_out_of_file(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CredentialStore(directory)
            store.save({"api_key": KEY, "api_secret": SECRET})
            raw = store.path.read_bytes()
            self.assertNotIn(KEY.encode(), raw)
            self.assertNotIn(SECRET.encode(), raw)
            self.assertEqual(store.load()["api_secret"], SECRET)
            store.remove()
            self.assertFalse(store.path.exists())

    @unittest.skipUnless(
        os.name == "nt", "Windows DPAPI verification requires a Windows runner"
    )
    def test_tampered_ciphertext_does_not_decrypt(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CredentialStore(directory)
            store.path.write_bytes(b"not-valid-ciphertext")
            with self.assertRaises(SecureStorageUnavailable):
                store.load()


class PortfolioBindingTests(unittest.TestCase):
    setUp = AccountLinkTests.setUp
    tearDown = AccountLinkTests.tearDown

    def test_new_key_must_match_existing_portfolio(self):
        with self.assertRaises(ValueError):
            self.link.connect(KEY, SECRET, expected_fingerprint="another-portfolio")
        self.store.save.assert_not_called()
        self.assertIsNone(self.link.adapter)
