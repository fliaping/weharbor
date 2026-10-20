"""Current-chat proof rejects stale heap data, ambiguous pages and races."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'root/scripts/workspace'))
import session_identity as identity
import desktop


class SessionIdentityTests(unittest.TestCase):
    def setUp(self):
        self.mem = object.__new__(identity.Memory)
        self.mem.base = 0x100000
        self.mem.fd = 123
        self.mem.maps = [(0x100000, 0x102000, 'r-xp', str(identity.EXE), 0),
                         (0x300000, 0x301000, 'rw-p', '[heap]', 0)]
        self.bytes = {}
        self.layout = {'field': 0x100, 'vtables': [0x200], 'functions': [0x400],
                       'meta': 0x800, 'handler': 0x1000, 'handler_bytes': (b'H' * 200).hex()}
        self.put(0x100200, struct.pack('<Q', 0x100400))
        code = b'X' * 15 + bytes.fromhex('488d05')
        self.put(0x100400, code + struct.pack('<i', 0x800 - 0x400 - 22) + bytes.fromhex('c3'))
        self.put(0x101000, b'H' * 200)
        self.add_page(0x300000, 'wxid_synthetic')
        self.mock = patch.object(identity.os, 'pread', side_effect=self.pread)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def put(self, address, value):
        self.bytes.update((address + i, byte) for i, byte in enumerate(value))

    def pread(self, fd, count, address):
        return bytes(self.bytes.get(address + i, 0) for i in range(count))

    def add_page(self, address, username):
        private = address + 0x200
        self.put(address, struct.pack('<QQ', 0x100200, private))
        self.put(private + 8, struct.pack('<Q', address))
        value = username.encode()
        self.put(address + 0x100, bytes([len(value) * 2]) + value + bytes(23 - len(value)))

    def test_version_policy_uses_two_numeric_components_without_major_ceiling(self):
        self.assertEqual(identity.version_pair('4.1.1'), identity.version_pair('4.1.99.999'))
        self.assertEqual(identity.version_pair('12.30.4-1'), (12, 30))
        self.assertNotEqual(identity.version_pair('4.1'), identity.version_pair('4.2'))
        for value in ['4', '4.1junk', '4.1;command', '4.1.']:
            with self.assertRaises(identity.IdentityError):
                identity.version_pair(value)

    def test_live_typed_page_resolves_exact_session(self):
        self.assertEqual(self.mem.pages(self.layout), 0x300000)
        self.assertEqual(self.mem.page(0x300000, self.layout), 'wxid_synthetic')

    def test_freed_heap_residue_cannot_prove_session(self):
        self.put(0x300208, struct.pack('<Q', 0))
        with self.assertRaisesRegex(identity.IdentityError, 'SESSION_PAGE_UNAVAILABLE'):
            self.mem.pages(self.layout)

    def test_multiple_live_pages_fail_instead_of_selecting_target_match(self):
        self.add_page(0x300500, 'wxid_another')
        with self.assertRaisesRegex(identity.IdentityError, 'SESSION_PAGES_AMBIGUOUS'):
            self.mem.pages(self.layout)

    def test_runtime_handler_change_invalidates_cached_layout(self):
        self.put(0x101000, b'changed')
        with self.assertRaises(identity.IdentityError):
            self.mem.page(0x300000, self.layout)

    def test_long_string_capacity_bounds_and_terminator(self):
        value = b'wxid_synthetic_long_username'
        self.put(0x300100, struct.pack('<QQQ', 65, len(value), 0x300800))
        self.put(0x300800, value + bytes(1))
        self.assertEqual(self.mem.username(0x300100), value.decode())
        self.put(0x300800 + len(value), b'x')
        with self.assertRaises(identity.IdentityError):
            self.mem.username(0x300100)
        self.put(0x300108, struct.pack('<Q', 2**63))
        with self.assertRaises(identity.IdentityError):
            self.mem.username(0x300100)

    def test_empty_session_and_racing_string_fail(self):
        self.put(0x300100, bytes(24))
        with self.assertRaises(identity.IdentityError):
            self.mem.username(0x300100)
        self.add_page(0x300000, 'wxid_synthetic')
        original = self.pread
        reads = 0

        def racing(fd, count, address):
            nonlocal reads
            value = original(fd, count, address)
            if address == 0x300100:
                reads += 1
                if reads > 1:
                    return bytes(count)
            return value

        with patch.object(identity.os, 'pread', side_effect=racing):
            with self.assertRaisesRegex(identity.IdentityError, 'SESSION_MEMORY_CHANGED'):
                self.mem.username(0x300100)

    def test_malformed_or_wrong_arch_elf_fails(self):
        for value in [bytes(64), bytes.fromhex('7f454c460101') + bytes(100)]:
            with self.assertRaises(identity.IdentityError):
                identity.Elf(value)


class DesktopMemoryBindingTests(unittest.TestCase):
    def test_exact_account_and_username_required_without_leaking_helper_output(self):
        driver = object.__new__(desktop.Desktop)
        binding = {'account': 'local', 'username': 'wxid_target'}
        valid = dict(binding, verified=True)
        for evidence in [valid, dict(valid, username='wxid_other'),
                         dict(valid, account='other'), dict(valid, verified=False), {}, None, []]:
            result = subprocess.CompletedProcess([], 0, json.dumps(evidence), '')
            with patch.object(desktop.subprocess, 'run', return_value=result) as run:
                if evidence == valid:
                    driver._identity(binding)
                else:
                    with self.assertRaises(desktop.DesktopError) as failure:
                        driver._identity(binding)
                    self.assertNotIn('wxid_', str(failure.exception))
                self.assertEqual(run.call_args.args[0], ['sudo', '-n', '/usr/local/bin/weharbor-capture-key'])
        with patch.object(desktop.subprocess, 'run', side_effect=subprocess.TimeoutExpired([], 20)):
            with self.assertRaises(desktop.DesktopError):
                driver._identity(binding)
