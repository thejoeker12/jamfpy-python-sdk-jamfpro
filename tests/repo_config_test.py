"""Repo configuration the code cannot check itself: one Python floor everywhere, ignores, package metadata leftovers.

Like ``contract_test.py``, an exception to one-test-file-per-module: it reads config files, not a source module. Each
test pins a configuration fix, so the mistake can't come back unnoticed.
"""
import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def _pylintrc_py_version() -> str:
    found = re.search(r"^py-version\s*=\s*(\S+)\s*$", (ROOT / ".pylintrc").read_text(encoding="utf-8"), re.MULTILINE)
    assert found, ".pylintrc sets no py-version"
    return found[1]


def _ci_test_matrix() -> list[str]:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    return [str(version) for version in workflow["jobs"]["test"]["strategy"]["matrix"]["python-version"]]


def _makefile_python_versions() -> list[str]:
    found = re.search(r"^PYTHON_VERSIONS\s*\??=\s*(.+)$", (ROOT / "Makefile").read_text(encoding="utf-8"), re.MULTILINE)
    assert found, "the Makefile sets no PYTHON_VERSIONS"
    return found[1].split()


def test_one_python_floor_everywhere():
    """requires-python, pylint, mypy, the CI matrix and check-matrix all start at the same version."""
    requires = PYPROJECT["project"]["requires-python"]
    assert requires.startswith(">="), requires
    floor = _version(requires.removeprefix(">="))
    assert _version(_pylintrc_py_version()) == floor
    assert _version(PYPROJECT["tool"]["mypy"]["python_version"]) == floor
    assert min(_version(version) for version in _ci_test_matrix()) == floor
    assert min(_version(version) for version in _makefile_python_versions()) == floor


def test_gitignore_covers_local_secrets_and_per_version_venvs():
    """.env holds live-tenant credentials; .venv-<version> is what make check-matrix creates."""
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in lines
    assert ".venv-*" in lines


def test_pyproject_has_no_template_leftovers():
    """No placeholder console script or optional-dependency groups: jamfpy installs no scripts and has no extras."""
    assert "scripts" not in PYPROJECT["project"]
    assert "optional-dependencies" not in PYPROJECT["project"]


def test_no_stray_json_file_at_the_root():
    """A file named json at the root was an accidental capture of git output."""
    assert not (ROOT / "json").exists()


def test_py_typed_ships_with_the_package():
    """The PEP 561 marker exists and is package data, so the wheel carries it."""
    assert (ROOT / "jamfpy" / "py.typed").is_file()
    assert "py.typed" in PYPROJECT["tool"]["setuptools"]["package-data"]["jamfpy"]


def test_build_needs_no_setuptools_scm():
    """The version is static in pyproject.toml (release-please edits it), so nothing derives it from git."""
    requires = PYPROJECT["build-system"]["requires"]
    assert not [name for name in requires if re.match(r"setuptools[-_]scm", name, re.IGNORECASE)], requires


def _no_test_gate() -> tuple[list[dict[str, object]], dict[str, object]]:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "integration-test.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["integration"]["steps"]
    gate = next(step for step in steps if step.get("name") == "Fail on a (no-test) PR title")
    return steps, gate


def test_no_test_gate_fails_before_the_live_suite():
    """A (no-test) PR title fails the integration job (a skip would count as passed) before anything touches the tenant."""
    steps, gate = _no_test_gate()
    assert steps.index(gate) == 0
    assert gate["if"] == "github.event_name == 'pull_request'"
    assert "exit 1" in str(gate["run"])


def test_no_test_gate_matches_only_the_no_test_scope():
    """The gate's pattern catches type(no-test): and type(no-test)!:, nothing else."""
    found = re.search(r"grep -Eq '([^']+)'", str(_no_test_gate()[1]["run"]))
    assert found, "the gate has no grep pattern"
    pattern = re.compile(found[1])
    for title in ("docs(no-test): fix a typo", "feat(no-test)!: drop a method"):
        assert pattern.search(title), title
    for title in ("docs: fix a typo", "docs(no-tests): x", "docs(api): x", "chore: (no-test) in the subject"):
        assert not pattern.search(title), title
