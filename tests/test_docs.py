import re
from pathlib import Path

README_PATH = Path("README.md")


def test_readme_uses_current_project_name():
    readme = README_PATH.read_text(encoding="utf-8")

    assert "# legal-ops-agent" in readme
    assert "LegalAgent" not in readme


def test_readme_local_markdown_links_exist():
    readme = README_PATH.read_text(encoding="utf-8")
    markdown_links = re.findall(r"\[[^\]]+\]\(([^)]+\.md)\)", readme)

    for link in markdown_links:
        assert Path(link).exists(), f"README link target does not exist: {link}"
