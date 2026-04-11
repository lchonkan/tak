# -*- mode: python ; coding: utf-8 -*-
import os, sys
from PyInstaller.utils.hooks import collect_all

# Resolve site-packages from the active Python environment
_sp = os.path.join(os.path.dirname(sys.executable), '..', 'lib',
                   f'python{sys.version_info.major}.{sys.version_info.minor}', 'site-packages')
_sp = os.path.normpath(_sp)
_mlx_lib = os.path.join(_sp, 'mlx', 'lib')
_sd_data = os.path.join(_sp, '_sounddevice_data')

datas = [
    (os.path.join(_mlx_lib, 'mlx.metallib'), 'mlx/lib'),
]
if os.path.isdir(_sd_data):
    datas.append((_sd_data, '_sounddevice_data'))

binaries = [(os.path.join(_mlx_lib, 'libmlx.dylib'), 'mlx/lib')]
hiddenimports = ['AppKit', 'Foundation', 'objc', 'sounddevice', 'numpy']
tmp_ret = collect_all('mlx')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('mlx_whisper')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pynput')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['tak/gui_main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchaudio', 'torchvision', 'faster_whisper', 'ctranslate2', 'onnxruntime', 'PIL', 'tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TAK',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['resources/tak.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TAK',
)
app = BUNDLE(
    coll,
    name='TAK.app',
    icon='resources/tak.icns',
    bundle_identifier='com.tak.app',
)
