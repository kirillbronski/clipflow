"""Release configuration is executable policy, not a legacy app renamed 2.0."""

import importlib.util
import os
import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    assert path.is_file(), f'Missing release component: {path.name}'
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def configuration():
    return module('package_config', ROOT / 'scripts/package_config.py')


def test_both_specs_use_same_qt_entry_version_and_resources(monkeypatch, tmp_path):
    cfg = configuration()
    tools = {name: tmp_path / name for name in ('ffmpeg', 'ffprobe', 'node')}
    for path in tools.values():
        path.write_bytes(b'synthetic config fixture, not executable')
    monkeypatch.setattr(cfg, 'resolve_tool', lambda name: tools[name])
    versions = []
    for system in ('windows', 'macos'):
        spec = ROOT / f'packaging/{system}/ClipFlow.spec'
        assert spec.is_file()
        recorded = []
        executable_options = []

        def analysis(scripts, **kwargs):
            # runpy calls these fakes synchronously within this loop iteration.
            recorded.append((scripts, kwargs))  # noqa: B023 — called within this iteration
            return type(
                'AnalysisResult', (), {'pure': [], 'scripts': [], 'binaries': [], 'datas': []}
            )()

        runpy.run_path(
            str(spec),
            init_globals={
                'SPECPATH': str(spec.parent),
                'Analysis': analysis,
                'PYZ': lambda *a, **k: None,
                'EXE': lambda *a, **k: executable_options.append(k),  # noqa: B023 — same iteration
                'COLLECT': lambda *a, **k: None,
                'BUNDLE': lambda *a, **k: None,
            },
        )
        scripts, args = recorded[0]
        assert [Path(p).resolve() for p in scripts] == [ROOT / 'src/clipflow/__main__.py']
        assert str(ROOT / 'source') not in args['pathex']
        assert {Path(p).stem for p, dest in args['binaries']} >= {'ffmpeg', 'ffprobe', 'node'}
        assert any(dest == 'licenses' for p, dest in args['datas'])
        assert 'PySide6.QtWebEngineWidgets' in args['hiddenimports']
        if system == 'windows':
            assert Path(executable_options[0]['version']).name == 'windows-version.txt'
        versions.append(cfg.APP_VERSION)
    assert versions == [runpy.run_path(str(ROOT / 'src/clipflow/version.py'))['APP_VERSION']] * 2


def test_no_tk_or_legacy_app_in_release(monkeypatch, tmp_path):
    cfg = configuration()
    monkeypatch.setattr(cfg, 'resolve_tool', lambda name: tmp_path / name)
    inputs = cfg.spec_inputs(ROOT, 'windows')
    assert {'tkinter', '_tkinter', 'customtkinter'} <= set(inputs['excludes'])
    assert not any('source' in Path(p).relative_to(ROOT).parts for p in inputs['pathex'])
    assert not any('customtkinter' in str(pair) for pair in inputs['datas'])


def test_coverage_threshold_gate_fails_below_each_limit():
    gate = module('check_coverage', ROOT / 'scripts/check_coverage.py')

    def report(core_lines=100, core_branches=100, runtime_lines=100):
        return {
            'files': {
                'src/clipflow/domain/models.py': {
                    'summary': {
                        'covered_lines': core_lines,
                        'num_statements': 100,
                        'covered_branches': core_branches,
                        'num_branches': 100,
                    }
                },
                'src/clipflow/ui/window.py': {
                    'summary': {
                        'covered_lines': runtime_lines,
                        'num_statements': 100,
                        'covered_branches': 0,
                        'num_branches': 0,
                    }
                },
            }
        }

    assert gate.evaluate(report())['passed']
    for data in (report(core_lines=94), report(core_branches=89), report(runtime_lines=79)):
        assert not gate.evaluate(data)['passed']
    assert not gate.evaluate({'files': {}})['passed']


def test_coverage_combines_child_process_data(tmp_path):
    from coverage import CoverageData

    gate = module('check_coverage', ROOT / 'scripts/check_coverage.py')
    source = str(tmp_path / 'work.py')
    for suffix, lines in (('a', [1, 2]), ('b', [5])):
        data = CoverageData(basename=str(tmp_path / '.coverage'), suffix=suffix)
        data.add_lines({source: lines})
        data.write()

    gate.combine_data(tmp_path)

    combined = CoverageData(basename=str(tmp_path / '.coverage'))
    combined.read()
    assert sorted(combined.lines(source)) == [1, 2, 5]
    assert not list(tmp_path.glob('.coverage.*'))


@pytest.mark.parametrize(('system', 'measured'), [('darwin', False), ('win32', True)])
def test_coverage_leaves_out_code_only_the_other_os_runs(tmp_path, monkeypatch, system, measured):
    from coverage import Coverage

    gate = module('check_coverage', ROOT / 'scripts/check_coverage.py')
    monkeypatch.setenv('CLIPFLOW_FOREIGN_OS', gate.foreign_system(system))
    source = tmp_path / 'native.py'
    source.write_text('def seal():  # pragma: only windows\n    return 1\n', encoding='utf-8')
    coverage = Coverage(config_file=str(ROOT / 'pyproject.toml'), data_file=str(tmp_path / 'data'))
    statements = coverage.analysis2(str(source))[1]
    assert bool(statements) is measured


def test_windows_build_path_excludes_foreign_dlls(tmp_path):
    cfg = configuration()
    foreign = tmp_path / 'poppler/bin'
    system = tmp_path / 'Windows'
    python = tmp_path / 'Python/python.exe'
    env = cfg.windows_build_environment(
        {'PATH': str(foreign), 'SYSTEMROOT': str(system)}, python, python.parent
    )
    assert str(foreign) not in env['PATH']
    assert str(system / 'System32') in env['PATH']
    assert str(python.parent) in env['PATH']


def test_auth_flags_work_when_frozen(monkeypatch, tmp_path):
    cfg = configuration()
    monkeypatch.setattr(cfg, 'resolve_tool', lambda name: tmp_path / name)
    inputs = cfg.spec_inputs(ROOT, 'windows')
    assert 'clipflow.infrastructure.auth_process.__main__' in inputs['hiddenimports']
    import sys

    import clipflow.infrastructure.auth as auth
    from clipflow.domain.models import Service
    from clipflow.infrastructure.auth import NativeAuthGateway

    commands = []

    class Child:
        def poll(self):
            return None

    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(
        auth.subprocess, 'Popen', lambda command, **kw: commands.append(command) or Child()
    )
    gateway = NativeAuthGateway(tmp_path)
    gateway.sign_in(Service.YOUTUBE, 'ru')
    gateway.sign_in(Service.INSTAGRAM, 'ru')
    assert commands[0][0] == sys.executable
    assert '--youtube-login' in commands[0]
    assert '-m' not in commands[0]
    assert '--instagram-login' in commands[1]


def test_installer_language_only_seeds_first_profile(monkeypatch, tmp_path):
    import clipflow.ui.bootstrap as bootstrap
    from clipflow.version import APP_VERSION

    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'ClipFlow.exe'))
    marker = tmp_path / 'language.txt'
    marker.write_text(APP_VERSION + ':en')
    profile = tmp_path / 'profile'
    profile.mkdir()
    assert bootstrap.installer_language(profile) == 'en'
    (profile / 'settings-v2.json').write_text('{}')
    assert bootstrap.installer_language(profile) is None
    (profile / 'settings-v2.json').unlink()
    marker.write_text('old-version:en')
    assert bootstrap.installer_language(profile) is None


def test_explicit_tool_survives_sanitized_path(monkeypatch, tmp_path):
    cfg = configuration()
    tool = tmp_path / 'ffmpeg.exe'
    tool.write_bytes(b'fixture')
    monkeypatch.setenv('PATH', '')
    monkeypatch.setenv('CLIPFLOW_FFMPEG_PATH', str(tool))
    monkeypatch.delenv('CLIPFLOW_BIN_DIR', raising=False)
    assert cfg.resolve_tool('ffmpeg') == tool


def offline_check(monkeypatch, codes):
    """Load scripts/check.py with fake ruff results and a fake coverage run."""
    import types

    # check.main may set QT_QPA_PLATFORM: record the caller's value so monkeypatch restores it.
    current = os.environ.get('QT_QPA_PLATFORM')
    monkeypatch.setenv('QT_QPA_PLATFORM', current or 'unset')
    if current is None:
        monkeypatch.delenv('QT_QPA_PLATFORM')
    check = module('clipflow_check_script', ROOT / 'scripts/check.py')
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs.get('cwd')))
        return types.SimpleNamespace(returncode=codes.pop(0))

    tests = types.SimpleNamespace(calls=0)

    def run_tests():
        tests.calls += 1
        return 0

    monkeypatch.setitem(sys.modules, 'check_coverage', types.SimpleNamespace(run=run_tests))
    return (lambda: check.main([], run=fake_run)), calls, tests


def test_offline_check_stops_before_tests_when_style_fails(monkeypatch):
    main, calls, tests = offline_check(monkeypatch, [1, 0])
    assert main() == 1
    assert tests.calls == 0
    assert calls[0] == ([sys.executable, '-m', 'ruff', 'format', '--check', '.'], ROOT)


def test_offline_check_runs_lint_then_tests(monkeypatch):
    main, calls, tests = offline_check(monkeypatch, [0, 0])
    assert main() == 0
    assert [command for command, _ in calls] == [
        [sys.executable, '-m', 'ruff', 'format', '--check', '.'],
        [sys.executable, '-m', 'ruff', 'check', '.'],
    ]
    assert tests.calls == 1


def test_offline_check_runs_tests_from_repository_root(monkeypatch, tmp_path):
    main, _, _ = offline_check(monkeypatch, [0, 0])
    seen = []
    monkeypatch.setattr(sys.modules['check_coverage'], 'run', lambda: seen.append(Path.cwd()) or 0)
    monkeypatch.chdir(tmp_path)
    assert main() == 0
    assert seen == [ROOT]


def test_check_runs_qt_offscreen_by_default(monkeypatch):
    """The local check runs Qt like the CI offline job, so a locked screen cannot fail it."""
    monkeypatch.delenv('QT_QPA_PLATFORM', raising=False)
    main, _, _ = offline_check(monkeypatch, [0, 0])
    assert main() == 0
    assert os.environ['QT_QPA_PLATFORM'] == 'offscreen'


def test_check_keeps_an_explicit_qt_platform(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'cocoa')
    main, _, _ = offline_check(monkeypatch, [0, 0])
    assert main() == 0
    assert os.environ['QT_QPA_PLATFORM'] == 'cocoa'
