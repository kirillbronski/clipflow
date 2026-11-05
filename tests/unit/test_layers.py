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


def imported_modules(tree, module, package=False):
    """Every clipflow import, absolute or relative, including ones inside functions and
    TYPE_CHECKING blocks; ``from clipflow import ui`` counts as importing ``clipflow.ui``."""
    base = module.split('.') if package else module.split('.')[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (
                alias.name for alias in node.names if alias.name.split('.')[0] == 'clipflow'
            )
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            anchor = base[: len(base) - (node.level - 1)]
            target = '.'.join(anchor + ([node.module] if node.module else []))
        else:
            target = node.module or ''
        if target.split('.')[0] != 'clipflow':
            continue
        if target.count('.') < 1:
            yield from (target + '.' + alias.name for alias in node.names)
        else:
            yield target


def module_violations(module, text, package=False):
    allowed = ALLOWED[module.split('.')[1]]
    found = []
    for target in imported_modules(ast.parse(text), module, package):
        parts = target.split('.')
        if len(parts) < 2 or parts[1] not in allowed:
            found.append(f'{module} -> {target}')
    return found


def violations():
    found = []
    for path in sorted((SOURCE / 'clipflow').rglob('*.py')):
        module = module_name(path)
        parts = module.split('.')
        if module in ENTRY_POINTS or len(parts) < 2 or parts[1] not in ALLOWED:
            continue
        text = path.read_text(encoding='utf-8')
        found += module_violations(module, text, package=path.name == '__init__.py')
    return found


def test_layer_dependencies():
    assert violations() == []


def test_no_pending_markers():
    marked = [
        f'{path.relative_to(SOURCE)}:{number}'
        for path in sorted((SOURCE / 'clipflow').rglob('*.py'))
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1)
        if '# подпроект 3' in line
    ]
    assert marked == []


def test_checker_sees_relative_and_package_imports():
    sneaky = 'from ..providers.base import MediaItem\nfrom . import urls\n'
    assert module_violations('clipflow.domain.paths', sneaky) == [
        'clipflow.domain.paths -> clipflow.providers.base'
    ]
    package = 'from .. import ui\nimport clipflow\n'
    assert module_violations('clipflow.domain', package, package=True) == [
        'clipflow.domain -> clipflow.ui',
        'clipflow.domain -> clipflow',
    ]


TESTS = Path(__file__).resolve().parents[1]


def test_test_modules_do_not_import_each_other():
    """Shared fixtures live in conftest.py and helpers in tests/support, never in test files."""
    found = []
    for path in sorted(TESTS.rglob('test_*.py')):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            found += [
                f'{path.relative_to(TESTS)} -> {name}'
                for name in names
                if name.startswith('tests.') and name.split('.')[-1].startswith('test_')
            ]
    assert found == []
