"""Automated architecture guard tests.

Enforces:
1. Strict modularity: No source file in backend/ exceeds 400 lines of code (LOC).
2. Pure Domain: backend/domain/ has ZERO external third-party imports (stdlib only).
3. Zero monkey-patching in backend/.
"""

import ast
import sys
from pathlib import Path


def test_max_file_loc_under_400() -> None:
    """Ensure NO source file in backend/ exceeds 400 lines of code (LOC)."""
    backend_dir = Path(__file__).resolve().parent.parent.parent / "backend"
    violations = []

    for py_file in backend_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        line_count = len(py_file.read_text(encoding="utf-8").splitlines())
        if line_count > 400:
            violations.append(f"{py_file.relative_to(backend_dir)}: {line_count} lines")

    assert not violations, "Files exceeding 400 LOC guardrail:\n" + "\n".join(violations)


def test_domain_zero_external_dependencies() -> None:
    """Ensure backend/domain/ has ZERO external third-party dependencies (stdlib only)."""
    domain_dir = Path(__file__).resolve().parent.parent.parent / "backend" / "domain"
    stdlib_modules = sys.stdlib_module_names if hasattr(sys, "stdlib_module_names") else set()

    # Allowed internal domain imports
    allowed_internal_prefixes = ("backend.domain",)
    external_imports = []

    for py_file in domain_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_pkg = alias.name.split(".")[0]
                    if root_pkg not in stdlib_modules and not alias.name.startswith(allowed_internal_prefixes):
                        external_imports.append(f"{py_file.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_pkg = node.module.split(".")[0]
                    if root_pkg not in stdlib_modules and not node.module.startswith(allowed_internal_prefixes):
                        external_imports.append(f"{py_file.name}: from {node.module} import ...")

    assert not external_imports, (
        "Domain purity violated (ADR-3). Found external imports in domain/:\n"
        + "\n".join(external_imports)
    )


def test_no_socket_monkey_patching() -> None:
    """Ensure no monkey-patching of socket.getaddrinfo or urllib3 exists in backend/."""
    backend_dir = Path(__file__).resolve().parent.parent.parent / "backend"
    forbidden_patterns = [
        "socket.getaddrinfo =",
        "getaddrinfo =",
        "create_connection =",
    ]
    violations = []

    for py_file in backend_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            if pattern in content:
                violations.append(f"{py_file.name}: contains forbidden pattern '{pattern}'")

    assert not violations, "Forbidden monkey-patching detected:\n" + "\n".join(violations)
