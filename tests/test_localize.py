import contextlib
import importlib.util
import io
import json
from pathlib import Path
import ssl
import sys
import tempfile
from types import SimpleNamespace
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPO_ROOT / "renpy-localization" / "scripts"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


localize = load_script("localize")
scan_dynamic_strings = load_script("scan_dynamic_strings")


class ProjectStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_default_state_is_scoped_to_game(self):
        game = self.root / "game-a"
        localize.configure_paths(str(game))

        self.assertEqual(Path(localize.GAME_DIR), game)
        self.assertEqual(Path(localize.PROJECT_DIR), game / ".renpy-localization")
        self.assertEqual(Path(localize.WORK), game / ".renpy-localization" / "work")
        self.assertEqual(
            Path(localize.glossary_path()),
            game / ".renpy-localization" / "glossary.json",
        )

    def test_explicit_project_dir_is_honored(self):
        game = self.root / "game"
        state = self.root / "state"
        localize.configure_paths(str(game), str(state))

        self.assertEqual(Path(localize.PROJECT_DIR), state)
        self.assertEqual(Path(localize.WORK), state / "work")

    def test_translation_memory_does_not_cross_games(self):
        game_a = self.root / "game-a"
        game_b = self.root / "game-b"

        localize.configure_paths(str(game_a))
        localize.save_memory("chinese", {"Hello": "你好"})
        self.assertEqual(localize.load_memory("chinese")["Hello"], "你好")

        localize.configure_paths(str(game_b))
        self.assertEqual(localize.load_memory("chinese"), {})


class TlsTests(unittest.TestCase):
    def test_certificate_verification_is_enabled_by_default(self):
        context = localize.build_ssl_context()

        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_insecure_tls_requires_explicit_opt_in(self):
        context = localize.build_ssl_context(insecure=True)

        self.assertEqual(context.verify_mode, ssl.CERT_NONE)
        self.assertFalse(context.check_hostname)

    def test_insecure_tls_cannot_be_combined_with_ca_file(self):
        with self.assertRaises(ValueError):
            localize.build_ssl_context(insecure=True, ca_file="corp-ca.pem")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.game = Path(self.temp.name) / "sample-game"
        self.tl = self.game / "game" / "tl" / "chinese"
        self.tl.mkdir(parents=True)
        localize.configure_paths(str(self.game))

    def tearDown(self):
        self.temp.cleanup()

    def test_extract_and_apply_round_trip(self):
        skeleton = """translate chinese start_abcd:

    # e \"Hello [name]\"
    e \"Hello [name]\"

translate chinese strings:

    # game/screens.rpy:1
    old \"Back\"
    new \"Back\"
"""
        (self.tl / "script.rpy").write_text(skeleton, encoding="utf-8-sig")

        with contextlib.redirect_stdout(io.StringIO()):
            localize.cmd_extract(SimpleNamespace(lang="chinese"))

        records = json.loads(Path(localize.records_path("chinese")).read_text(encoding="utf-8"))
        self.assertEqual(records["dialogue"][0]["en"], "Hello [name]")
        self.assertEqual(records["strings"][0]["en"], "Back")

        localize.save_memory(
            "chinese",
            {"Hello [name]": "你好，[name]", "Back": "返回"},
        )
        with contextlib.redirect_stdout(io.StringIO()) as output:
            localize.cmd_apply(SimpleNamespace(lang="chinese"))

        rebuilt = (self.tl / "script.rpy").read_text(encoding="utf-8-sig")
        self.assertIn('e "你好，[name]"', rebuilt)
        self.assertIn('new "返回"', rebuilt)
        self.assertIn("MISSING translations: 0", output.getvalue())

    def test_json_tag_interpolation_and_escape_helpers(self):
        payload = localize.extract_json('prefix [{"id":"1","zh":"你好 [mc]"}] suffix')
        self.assertEqual(payload[0]["zh"], "你好 [mc]")
        self.assertEqual(localize.fix_tags("{i}Hi{/i}", "你好"), "{i}你好{/i}")
        self.assertEqual(localize.fix_interp("Hi [mc]", "你好 [ mc ]", {"[mc]"}), "你好 [mc]")
        self.assertEqual(localize.escape_rpy('A "quote"\nnext'), 'A \\"quote\\"\\nnext')


class DynamicScannerTests(unittest.TestCase):
    def test_persistent_translatable_assignment_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "script.rpy").write_text(
                'default persistent.lore = _("Old text")\n'
                '$ persistent.title = _p("Cached title")\n'
                'default ordinary = _("Safe")\n',
                encoding="utf-8",
            )

            risks = scan_dynamic_strings.scan_persistent_i18n(root)

        self.assertEqual(len(risks), 2)
        self.assertTrue(all("persistent" in risk.text for risk in risks))


if __name__ == "__main__":
    unittest.main()
