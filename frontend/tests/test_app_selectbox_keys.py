import ast
import unittest
from pathlib import Path


class SelectboxKeyTests(unittest.TestCase):
    def test_selectbox_calls_include_key_argument(self):
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        source = app_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        missing_keys = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "selectbox":
                has_key = any(keyword.arg == "key" for keyword in node.keywords)
                if not has_key:
                    snippet = ast.get_source_segment(source, node) or "st.selectbox(...)"
                    missing_keys.append(snippet)

        self.assertEqual([], missing_keys, "Selectbox widgets must declare a unique key to avoid duplicate element IDs.\n" + "\n".join(missing_keys))


if __name__ == "__main__":
    unittest.main()
