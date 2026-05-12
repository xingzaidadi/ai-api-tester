import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillInstallSmokeTest(unittest.TestCase):
    def test_copied_skill_runs_detect_independent_of_repo_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            installed_skill = Path(tmpdir) / "ai-api-tester"
            shutil.copytree(ROOT / "skill", installed_skill)

            result = subprocess.run(
                [
                    sys.executable,
                    str(installed_skill / "scripts" / "detect.py"),
                    str(ROOT / "tests" / "fixtures" / "fastapi-basic"),
                ],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            self.assertIn("language: python", result.stdout)
            self.assertIn("framework: fastapi", result.stdout)


if __name__ == "__main__":
    unittest.main()
