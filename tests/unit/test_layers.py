"""Layer rules: inner layers never import outer ones; entry points assemble everything."""

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / 'src'
ALLOWED = {
    'domain': {'domain'},
    'application': {'domain', 'application'},
    'providers': {'domain', 'application', 'providers'},
    'infrastructure': {'domain', 'application', 'providers', 'infrastructure', 'version'},
    'ui': {'domain', 'application', 'ui', 'version'},
}
ENTRY_POINTS = {
    'clipflow.__main__',
    'clipflow.ui.bootstrap',
    'clipflow.ui.self_test',
    'clipflow.infrastructure.auth_process.__main__',
    'clipflow.infrastructure.auth_process.window',
}


def module_name(path):
    parts = list(path.relative_to(SOURCE).with_suffix('').parts)
    if parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def imported_modules(tree):
    """Every clipflow import, including ones inside functions and TYPE_CHECKING blocks."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        yield from (name for name in names if name.split('.')[0] == 'clipflow')


def violations():
    found = []
    for path in sorted((SOURCE / 'clipflow').rglob('*.py')):
        module = module_name(path)
        parts = module.split('.')
        if module in ENTRY_POINTS or len(parts) < 3:
            continue
        allowed = ALLOWED[parts[1]]
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for target in imported_modules(tree):
            if target.split('.')[1] not in allowed:
                found.append(f'{module} -> {target}')
    return found


def test_layer_dependencies():
    assert violations() == []
