import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillStructureTest(unittest.TestCase):
    def test_skill_frontmatter_has_required_fields(self):
        skill_md = ROOT / "skill" / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8")

        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---", 2)[1]
        self.assertIn("name: ai-api-tester", frontmatter)
        self.assertIn("description:", frontmatter)

    def test_required_skill_resources_exist(self):
        required_paths = [
            "skill/agents/openai.yaml",
            "skill/references/yaml_format.md",
            "skill/references/assertions.md",
            "skill/references/dimensions.md",
            "skill/references/context_format.md",
            "skill/references/failure_analysis.md",
            "skill/scripts/detect.py",
            "skill/scripts/locate.py",
            "skill/scripts/gen_context.py",
            "skill/scripts/validate_cases.py",
            "skill/scripts/run_tests.py",
            "skill/scripts/analyze_failures.py",
        ]

        for path in required_paths:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).exists())


if __name__ == "__main__":
    unittest.main()
