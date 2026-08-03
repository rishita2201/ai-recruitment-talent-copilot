import ast
import unittest
from pathlib import Path


class AudioInputFallbackTests(unittest.TestCase):
    def test_streamlit_audio_input_is_guarded_for_old_versions(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        source = app_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        has_audio_input_call = False
        has_guard = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "audio_input":
                has_audio_input_call = True
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "hasattr":
                if len(node.args) >= 2 and isinstance(node.args[0], ast.Name) and node.args[0].id == "st" and isinstance(node.args[1], ast.Constant) and node.args[1].value == "audio_input":
                    has_guard = True

        self.assertTrue(has_audio_input_call)
        self.assertTrue(has_guard, "audio_input should be accessed through a compatibility guard when the installed Streamlit version may not support it.")


if __name__ == "__main__":
    unittest.main()
