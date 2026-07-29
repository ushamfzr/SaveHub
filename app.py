import os
import sys
import time
import json
import uuid
import threading
import yt_dlp
import urllib.parse
from flask import Flask, render_template, request, jsonify, Response, send_file
import imageio_ffmpeg
import webview

def get_base_path():
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, 
            template_folder=os.path.join(get_base_path(), 'templates'),
            static_folder=os.path.join(get_base_path(), 'static'))
app.config['SECRET_KEY'] = 'super-secret-key-ug'

# Use user's temp directory directly (Safe for macOS .app bundles)
TEMP_DIR = os.path.expanduser('~/Downloads/.savehub_temp')
os.makedirs(TEMP_DIR, exist_ok=True)

ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
jobs = {}

def get_platform_from_url(url):
    url_lower = url.lower()
    if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        return 'youtube'
    if 'facebook.com' in url_lower or 'fb.watch' in url_lower:
        return 'facebook'
    if 'instagram.com' in url_lower:
        return 'instagram'
    return 'unknown'

def get_available_qualities(formats):
    qualities = set()
    if formats:
        for f in formats:
            if f.get('vcodec') not in [None, 'none'] and f.get('height'):
                qualities.add(f['height'])
    
    sorted_q = sorted(list(qualities), reverse=True)
    # Filter for standard sizes and above
    valid_q = [str(q) for q in sorted_q if q >= 360]
    return valid_q if valid_q else ['1080', '720', '480', '360']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/info', methods=['GET'])
def get_info():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    platform = get_platform_from_url(url)
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'ignore_no_formats_error': True,
        'ffmpeg_location': ffmpeg_path,
    }
    
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'

    # We DO NOT use extract_flat so we get full metadata for Instagram carousels to filter videos
    if platform == 'youtube':
        ydl_opts['noplaylist'] = True
        
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            entries = info.get('entries')
            if entries:
                items = []
                for entry in entries:
                    if not entry: continue
                    
                    has_video = False
                    if entry.get('formats'):
                        has_video = any(f.get('vcodec') not in [None, 'none'] for f in entry.get('formats'))
                    
                    if has_video or entry.get('ext') in ['mp4', 'webm', 'mkv']:
                        items.append({
                            'id': entry.get('id'),
                            'title': entry.get('title', 'Video Media'),
                            'thumbnail': entry.get('thumbnail') or info.get('thumbnail'),
                            'url': url, # Use the original URL to keep extractor context
                            'playlist_index': entry.get('playlist_index'),
                            'duration': entry.get('duration'),
                            'view_count': entry.get('view_count'),
                            'uploader': entry.get('uploader'),
                            'available_qualities': get_available_qualities(entry.get('formats'))
                        })
                
                if not items:
                    return jsonify({'error': 'No video formats found in this link. Only videos are supported.'}), 400
                    
                return jsonify({
                    'platform': platform,
                    'type': 'carousel',
                    'title': info.get('title', 'Playlist / Carousel'),
                    'items': items
                })
            else:
                has_video = False
                if info.get('formats'):
                    has_video = any(f.get('vcodec') not in [None, 'none'] for f in info.get('formats'))
                
                if not has_video and info.get('ext') not in ['mp4', 'webm', 'mkv']:
                    return jsonify({'error': 'No video formats found. Only videos are supported.'}), 400

                return jsonify({
                    'platform': platform,
                    'type': 'single',
                    'title': info.get('title', 'Video Media'),
                    'thumbnail': info.get('thumbnail'),
                    'duration': info.get('duration'),
                    'view_count': info.get('view_count'),
                    'uploader': info.get('uploader'),
                    'url': url,
                    'available_qualities': get_available_qualities(info.get('formats'))
                })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

class MyLogger:
    def __init__(self, job_id):
        self.job_id = job_id

    def debug(self, msg):
        print(f"[DEBUG] {msg}")
    def info(self, msg):
        print(f"[INFO] {msg}")
    def warning(self, msg):
        print(f"[WARN] {msg}")
    def error(self, msg):
        print(f"[ERROR] {msg}")
        if self.job_id in jobs:
            jobs[self.job_id]['status'] = 'error'
            jobs[self.job_id]['error'] = msg

def progress_hook(d, job_id):
    if job_id not in jobs:
        return

    if d['status'] == 'downloading':
        jobs[job_id].update({
            'status': 'downloading',
            'progress': float(d.get('downloaded_bytes', 0)) / float(d.get('total_bytes') or d.get('total_bytes_estimate') or 1) * 100,
            'speed': d.get('_speed_str', 'N/A'),
            'eta': d.get('_eta_str', 'N/A'),
            'downloaded': d.get('_downloaded_bytes_str', 'N/A'),
            'total': d.get('_total_bytes_str', 'N/A')
        })
    elif d['status'] == 'finished':
        jobs[job_id]['status'] = 'processing'
        jobs[job_id]['file_path'] = d.get('info_dict', {}).get('_filename') or d.get('filename')

def download_worker(job_id, url, format_type, resolution, playlist_index):
    job = jobs[job_id]
    job_dir = os.path.join(TEMP_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    
    ydl_opts = {
        'outtmpl': os.path.join(job_dir, '%(title)s.%(ext)s'),
        'logger': MyLogger(job_id),
        'progress_hooks': [lambda d: progress_hook(d, job_id)],
        'quiet': True,
        'no_warnings': True,
        'restrictfilenames': True,
        'ignore_no_formats_error': True,
        'ffmpeg_location': ffmpeg_path,
        'fragment_retries': 30,
        'retries': 30,
        'file_access_retries': 30,
        'socket_timeout': 120,
        'source_address': '0.0.0.0', # Force IPv4 (fixes Mac IPv6 timeout hangs)
        'nocheckcertificate': True,  # Bypasses Mac python SSL certificate issues
    }

    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'

    if playlist_index:
        ydl_opts['playlist_items'] = str(playlist_index)
    else:
        ydl_opts['noplaylist'] = True

    if format_type == 'mp3':
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else:
        res = resolution if resolution else '1080'
        ext = format_type if format_type in ['mp4', 'webm', 'mkv'] else 'mp4'
        
        ydl_opts.update({
            'format': f'bestvideo[height<={res}][ext={ext}]+bestaudio[ext=m4a]/best[height<={res}][ext={ext}]/best',
            'merge_output_format': ext,
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            downloaded_files = os.listdir(job_dir)
            if downloaded_files:
                final_file = os.path.join(job_dir, downloaded_files[0])
                job['file_path'] = final_file
                job['filename'] = downloaded_files[0]
            else:
                raise Exception("No file found after download")

            job['status'] = 'complete'
    except Exception as e:
        job['status'] = 'error'
        job['error'] = str(e)


@app.route('/api/download', methods=['POST'])
def start_download():
    data = request.json or {}
    url = data.get('url')
    format_type = data.get('format', 'mp4') 
    resolution = data.get('resolution', '1080')
    playlist_index = data.get('playlist_index')

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {'status': 'starting', 'progress': 0}

    thread = threading.Thread(target=download_worker, args=(job_id, url, format_type, resolution, playlist_index))
    thread.start()

    return jsonify({'job_id': job_id})

@app.route('/api/progress/<job_id>')
def progress(job_id):
    def generate():
        last_state = None
        while True:
            job = jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'status': 'error', 'error': 'Job not found'})}\n\n"
                break
            
            current_state = json.dumps(job)
            if current_state != last_state:
                yield f"data: {current_state}\n\n"
                last_state = current_state

            if job['status'] in ['complete', 'error']:
                time.sleep(1) # Grace period
                break
            time.sleep(0.5)

    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/get-file/<job_id>')
def get_file(job_id):
    job = jobs.get(job_id)
    if not job or 'file_path' not in job:
        return jsonify({'error': 'File not found'}), 404

    file_path = job['file_path']
    filename = job.get('filename', 'downloaded_file')
    file_size = os.path.getsize(file_path)

    def generate():
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk: break
                yield chunk
        try:
            os.remove(file_path)
            os.rmdir(os.path.dirname(file_path))
        except:
            pass

    quoted_filename = urllib.parse.quote(filename)

    return Response(
        generate(),
        mimetype='application/octet-stream',
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{quoted_filename}",
            'Content-Length': str(file_size),
        }
    )

def start_server():
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)

if __name__ == '__main__':
    print("=" * 50)
    print("  SaveHub by UG")
    print("=" * 50)
    
    t = threading.Thread(target=start_server)
    t.daemon = True
    t.start()
    
    webview.create_window('SaveHub by UG', 'http://127.0.0.1:5000', width=1024, height=768)
    webview.start()
