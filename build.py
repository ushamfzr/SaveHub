import PyInstaller.__main__
import os
import sys

# Get path to imageio_ffmpeg bundled binary
import imageio_ffmpeg
ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

sep = os.pathsep  # ';' on Windows, ':' on Mac/Linux

args = [
    'app.py',
    '--name=SaveHub by UG',
    '--windowed',
    f'--add-data=templates{sep}templates',
    f'--add-data=static{sep}static',
    # Bundle the ffmpeg binary into the root of _MEIPASS so the cross-platform
    # scanner in app.py (startswith 'ffmpeg') can find it on both Windows & Mac
    f'--add-binary={ffmpeg_exe}{sep}.',
    '--hidden-import=yt_dlp',
    '--hidden-import=imageio_ffmpeg',
    '--hidden-import=webview',
    '--hidden-import=certifi',
    '--clean',
    '--noconfirm',
]

# macOS-specific hidden imports for PyWebView (pyobjc)
# These are also required for create_file_dialog (native folder picker)
if sys.platform == 'darwin':
    args += [
        '--hidden-import=webview.platforms.cocoa',
        '--hidden-import=Foundation',
        '--hidden-import=AppKit',
        '--hidden-import=WebKit',
        '--hidden-import=objc',
    ]
    # Bundle certifi SSL certs so the Mac .app can verify HTTPS connections
    import certifi
    certifi_dir = os.path.dirname(certifi.where())
    args.append(f'--add-data={certifi_dir}{sep}certifi')

PyInstaller.__main__.run(args)
