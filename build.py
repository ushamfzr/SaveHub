import PyInstaller.__main__
import os
import sys

# Get path to imageio_ffmpeg binaries
import imageio_ffmpeg
ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
ffmpeg_dir = os.path.dirname(ffmpeg_exe)

sep = os.pathsep  # Automatically uses ';' on Windows and ':' on Mac/Linux

args = [
    'app.py',
    '--name=SaveHub by UG',
    '--windowed',
    f'--add-data=templates{sep}templates',
    f'--add-data=static{sep}static',
    f'--add-binary={ffmpeg_exe}{sep}.',
    '--hidden-import=yt_dlp',
    '--hidden-import=imageio_ffmpeg',
    '--hidden-import=webview',
    '--hidden-import=certifi',
    '--clean',
    '--noconfirm',
]

# Add macOS-specific hidden imports for PyWebView (pyobjc)
if sys.platform == 'darwin':
    args += [
        '--hidden-import=webview.platforms.cocoa',
        '--hidden-import=Foundation',
        '--hidden-import=AppKit',
        '--hidden-import=WebKit',
        '--hidden-import=objc',
    ]
    # Bundle the certifi SSL certs so Mac app can verify HTTPS connections
    import certifi
    certifi_dir = os.path.dirname(certifi.where())
    args.append(f'--add-data={certifi_dir}{sep}certifi')

PyInstaller.__main__.run(args)
