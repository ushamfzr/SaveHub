import PyInstaller.__main__
import os

# Get path to imageio_ffmpeg binaries
import imageio_ffmpeg
ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
ffmpeg_dir = os.path.dirname(ffmpeg_exe)

sep = os.pathsep  # Automatically uses ';' on Windows and ':' on Mac/Linux

PyInstaller.__main__.run([
    'app.py',
    '--name=SaveHub by UG',
    '--windowed',
    f'--add-data=templates{sep}templates',
    f'--add-data=static{sep}static',
    f'--add-binary={ffmpeg_exe}{sep}.',
    '--hidden-import=yt_dlp',
    '--hidden-import=imageio_ffmpeg',
    '--hidden-import=webview',
    '--clean',
    '--noconfirm',
])
