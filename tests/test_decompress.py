import importlib
import os
import struct
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

import decompress
from binary_reader import ParseError
from decompress import decompress_sav


def build_palsav(raw: bytes, save_type: int) -> bytes:
    if save_type == 0x30:
        body = raw
        compressed_len = len(body)
    elif save_type == 0x31:
        body = zlib.compress(raw)
        compressed_len = len(body)
    elif save_type == 0x32:
        once = zlib.compress(raw)
        body = zlib.compress(once)
        compressed_len = len(once)
    else:
        raise ValueError(save_type)
    header = struct.pack("<II", len(raw), compressed_len) + b"PlZ" + struct.pack("<B", save_type)
    return header + body


class TestDecompressSav(unittest.TestCase):
    def test_uncompressed(self):
        raw = b"GVAS" + b"\x00" * 20
        self.assertEqual(decompress_sav(build_palsav(raw, 0x30)), raw)

    def test_single_zlib(self):
        raw = b"GVAS" + b"hello world" * 10
        self.assertEqual(decompress_sav(build_palsav(raw, 0x31)), raw)

    def test_double_zlib(self):
        raw = b"GVAS" + b"hello world" * 10
        self.assertEqual(decompress_sav(build_palsav(raw, 0x32)), raw)

    def test_cnk_wrapper(self):
        raw = b"GVAS" + b"payload"
        inner = build_palsav(raw, 0x31)
        outer = struct.pack("<II", len(inner), len(inner)) + b"CNK" + struct.pack("<B", 0) + inner
        self.assertEqual(decompress_sav(outer), raw)

    def test_bad_magic_raises(self):
        bad = struct.pack("<II", 4, 4) + b"XXX" + struct.pack("<B", 0x30) + b"data"
        with self.assertRaises(ParseError):
            decompress_sav(bad)

    def test_unknown_save_type_raises(self):
        raw = b"data"
        header = struct.pack("<II", len(raw), len(raw)) + b"PlZ" + struct.pack("<B", 0x99)
        with self.assertRaises(ParseError):
            decompress_sav(header + raw)

    def test_uncompressed_length_mismatch_raises(self):
        raw = b"short"
        header = struct.pack("<II", 999, len(raw)) + b"PlZ" + struct.pack("<B", 0x30)
        with self.assertRaises(ParseError):
            decompress_sav(header + raw)

    def test_oodle_without_library_raises_helpful_error(self):
        body = b"whatever-compressed-bytes"
        header = struct.pack("<II", 100, len(body)) + b"PlM" + struct.pack("<B", 0)
        with self.assertRaises(ParseError) as ctx:
            decompress_sav(header + body)
        self.assertIn("libooz.so", str(ctx.exception))


class TestOozDllPath(unittest.TestCase):
    def tearDown(self):
        # Other test modules (e.g. test_watcher.py, via watcher.py's own
        # `import decompress`) share this same module object -- reload once
        # more with no override so later tests see the default path again.
        importlib.reload(decompress)

    def test_ooz_path_defaults_to_the_repo_copy(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PALSAVE_API_OOZ_LIB_PATH", None)
            importlib.reload(decompress)
        self.assertEqual(decompress.OOZ_DLL_PATH.name, "libooz.so")
        self.assertEqual(decompress.OOZ_DLL_PATH.parent.parent.name, "ooz")

    def test_ooz_path_honours_the_environment(self):
        override = "/var/lib/palsave-api/lib/libooz.so"
        with patch.dict(os.environ, {"PALSAVE_API_OOZ_LIB_PATH": override}):
            importlib.reload(decompress)
        self.assertEqual(decompress.OOZ_DLL_PATH, Path(override))


if __name__ == "__main__":
    unittest.main()
