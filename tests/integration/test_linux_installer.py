"""Linux installer contracts, including actual execution of QtIFW scripts."""

import importlib.util
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def scripts_on_path(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.mark.parametrize('display', [None, ':1'])
def test_linux_smoke_environment_handles_display(monkeypatch, tmp_path, display):
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.delenv('WAYLAND_DISPLAY', raising=False)
    monkeypatch.delenv('DISPLAY', raising=False)
    if display:
        monkeypatch.setenv('DISPLAY', display)
    env = script('package_smoke').clean_environment(tmp_path)
    assert env.get('QT_QPA_PLATFORM') == (None if display else 'offscreen')
    assert env['CLIPFLOW_DATA_DIR'] == str(tmp_path)


def test_installer_config_has_user_home_target():
    root = ET.parse(ROOT / 'packaging/linux/installer/config/config.xml').getroot()
    assert root.findtext('TargetDir') == '@HomeDir@/.local/opt/ClipFlow'
    assert root.findtext('MaintenanceToolName') == 'maintenancetool'
    assert root.find('AdminTargetDir') is None
    assert root.findtext('ControlScript') == 'controller.qs'
    ET.parse(ROOT / 'packaging/linux/installer/packages/com.clipflow.app/meta/package.xml')


def test_installer_creator_requires_binarycreator(monkeypatch):
    monkeypatch.delenv('QTIFW_BINARYCREATOR', raising=False)
    monkeypatch.setenv('PATH', '')
    with pytest.raises(RuntimeError, match='QTIFW_BINARYCREATOR'):
        script('linux_build').installer_creator()


def test_installscript_targets_xdg_and_quotes_paths():
    node = os.environ.get('CLIPFLOW_NODE_PATH', 'node')
    source = ROOT / 'packaging/linux/installer/packages/com.clipflow.app/meta/installscript.qs'
    code = """
const fs = require('fs'), vm = require('vm');
const operations = [];
const context = {
 Component: undefined,
 installer: {value: key => ({TargetDir:'/home/кирилл a/ClipFlow',HomeDir:'/home/кирилл a'})[key],
             environmentVariable:key => key === 'XDG_DATA_HOME' ? '/tmp/xdg a' : '',
             execute: () => ['', 0]},
 component: {createOperations:()=>{}, addOperation:(...args)=>operations.push(args)},
 qsTr:x=>x,
};
vm.createContext(context); vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const c = new context.Component(); c.createOperations();
const entries = operations.filter(x=>x[0]==='CreateDesktopEntry');
if (entries.length !== 2 ||
    entries[0][1] !== '/tmp/xdg a/applications/clipflow.desktop') process.exit(2);
if (!entries[0][2].includes('Exec="/home/кирилл a/ClipFlow/ClipFlow"')) process.exit(3);
if (!operations.some(x=>x[0]==='Copy' &&
    x[2].endsWith('hicolor/256x256/apps/clipflow.png'))) process.exit(4);
if (operations[operations.length - 1][0] !== 'Execute') process.exit(5);
"""
    result = subprocess.run(
        [node, '-e', code, str(source)], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr


def test_build_refuses_unknown_linux_arch(monkeypatch, capsys):
    build = script('build')
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(build.platform, 'machine', lambda: 'riscv64')
    with pytest.raises(SystemExit) as raised:
        build.main(['--portable-only'])
    assert raised.value.code == 2
    assert 'Unsupported Linux architecture' in capsys.readouterr().err


def test_installer_stage_has_visible_product_marker(tmp_path):
    app = tmp_path / 'app'
    app.mkdir()
    (app / 'ClipFlow').write_bytes(b'synthetic executable')
    stage = script('linux_build').installer_stage(ROOT, tmp_path / 'stage', app)
    data = stage / 'packages/com.clipflow.app/data'
    assert (data / 'clipflow-install.txt').is_file()


def test_linux_tool_pins_are_complete():
    import re

    tools = script('linux_tools')
    for arch in ('x86_64', 'aarch64'):
        names = ('ffmpeg', 'node', 'qtifw') if arch == 'x86_64' else ('ffmpeg', 'node')
        for name in names:
            pin = tools.PINS[arch][name]
            assert pin['url'].startswith('https://')
            assert re.fullmatch('[a-f0-9]{64}', pin['sha256'])


def test_linux_tools_rejects_checksum_mismatch(tmp_path):
    tools = script('linux_tools')
    destination = tmp_path / 'download'

    def download(url, path):
        path.write_bytes(b'corrupt')

    with pytest.raises(RuntimeError, match='checksum'):
        tools.download_checked(
            'https://example.test/tool', destination, '0' * 64, download=download
        )
    assert not destination.exists()


def test_arm64_uses_native_source_built_qtifw(monkeypatch, tmp_path):
    import types

    tools = script('linux_tools')
    creator = tmp_path / 'qtifw/bin/binarycreator'

    def build(destination):
        assert destination == tmp_path
        return creator

    def reject_binary(*args):
        pytest.fail('The vendor ARM64 binary requires obsolete libtiff.so.5')

    monkeypatch.setitem(sys.modules, 'linux_qtifw', types.SimpleNamespace(build_qtifw=build))
    monkeypatch.setattr(tools, 'download_checked', reject_binary)
    assert tools.install_qtifw('aarch64', tmp_path) == creator


def test_qtifw_source_uses_the_actual_vendor_archive_root(monkeypatch, tmp_path):
    import io
    import tarfile
    import types

    archive = tmp_path / 'vendor.tar.xz'
    root = 'installer-framework-everywhere-src-dev'
    with tarfile.open(archive, 'w:xz') as stream:
        payload = b'TEMPLATE = subdirs\n'
        item = tarfile.TarInfo(root + '/installerfw.pro')
        item.size = len(payload)
        stream.addfile(item, io.BytesIO(payload))
    monkeypatch.setitem(
        sys.modules,
        'linux_tools',
        types.SimpleNamespace(download_checked=lambda *args: archive),
    )
    builder = script('linux_qtifw')
    source = builder._source('qtifw', tmp_path)
    assert source == tmp_path / root
    assert (source / 'installerfw.pro').read_bytes() == payload


def test_arm_installer_requires_static_compression_dependencies(tmp_path):
    builder = script('linux_qtifw')
    for name in ('libz.so', 'libbz2.so', 'liblzma.so'):
        (tmp_path / name).touch()
    with pytest.raises(RuntimeError, match='static compression'):
        builder.compression_flags((tmp_path,))


def test_arm_installer_links_static_compression_archives(tmp_path):
    builder = script('linux_qtifw')
    for name in ('libz.a', 'libbz2.a', 'liblzma.a'):
        (tmp_path / name).touch()
    flags = builder.compression_flags((tmp_path,))
    assert flags == [
        f'IFW_ZLIB_LIBRARY={tmp_path / "libz.a"}',
        f'IFW_BZIP2_LIBRARY={tmp_path / "libbz2.a"}',
        f'IFW_LZMA_LIBRARY={tmp_path / "liblzma.a"}',
    ]
