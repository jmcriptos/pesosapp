# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('instance/productos.db', 'instance'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PesosAppMac',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Asegura que no sea una app de consola
    disable_windowed_traceback=False,
    argv_emulation=True,  # Habilita argv emulation para mejorar la ejecución en macOS
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='iconoapp.icns',  # Asegúrate de que el icono está en la ubicación correcta
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PesosAppMac',
)

app = BUNDLE(
    coll,
    name='PesosAppMac.app',
    icon='iconoapp.icns',  # Asegúrate de que el icono está en la ubicación correcta
    bundle_identifier='com.miapp.pesosappmac',  # Puedes personalizar este bundle identifier
)