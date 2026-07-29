// --- UI Helpers ---
function showEl(id) { 
  const el = document.getElementById(id);
  if (el) el.classList.remove('hidden'); 
}
function hideEl(id) { 
  const el = document.getElementById(id);
  if (el) el.classList.add('hidden'); 
}

window.resetUI = function() {
  const container = document.getElementById('results-container');
  if (container) container.innerHTML = '';
  hideEl('progress-card');
  hideEl('success-card');
  hideEl('error-card');
  const ui = document.getElementById('url-input');
  if (ui) ui.value = '';
};

function showError(msg) {
  const errEl = document.getElementById('error-message');
  if (errEl) errEl.textContent = msg;
  hideEl('loading');
  const container = document.getElementById('results-container');
  if (container) container.innerHTML = '';
  hideEl('progress-card');
  showEl('error-card');
}

// --- Platform Tabs ---
let currentPlatform = 'youtube';
const placeholders = {
  youtube: 'Paste YouTube video URL here...',
  facebook: 'Paste Facebook video URL here...',
  instagram: 'Paste Instagram Reel or Video URL here...'
};

window.switchPlatform = function(platform) {
  currentPlatform = platform;
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.platform === platform);
  });
  const input = document.getElementById('url-input');
  if (input) {
    input.placeholder = placeholders[platform];
  }
};

// --- Fetch Info ---
window.fetchInfo = async function() {
  const urlInput = document.getElementById('url-input');
  const fetchBtn = document.getElementById('fetch-btn');
  
  if (!urlInput) return alert("Error: URL input not found in DOM");
  
  const url = urlInput.value.trim();
  if (!url) return;

  if (fetchBtn) fetchBtn.disabled = true;
  document.getElementById('results-container').innerHTML = '';
  hideEl('error-card');
  showEl('loading');

  try {
    const res = await fetch(`/api/info?url=${encodeURIComponent(url)}`);
    const data = await res.json();

    if (data.error) throw new Error(data.error);

    renderResults(data);
    hideEl('loading');
  } catch (e) {
    console.error("Fetch API Error:", e);
    showError(e.message);
  } finally {
    if (fetchBtn) fetchBtn.disabled = false;
  }
};

function renderResults(data) {
  const container = document.getElementById('results-container');
  container.innerHTML = '';
  
  let items = [];
  if (data.type === 'carousel' || data.items) {
    items = data.items;
  } else {
    items = [data];
  }

  const template = document.getElementById('video-card-template');
  
  items.forEach(item => {
    // Only render items that have a video title or look valid
    if (!item.title && !item.thumbnail) return;

    const clone = template.content.cloneNode(true);
    
    // Populate Metadata
    clone.querySelector('.video-thumbnail').src = item.thumbnail || 'https://via.placeholder.com/600x400?text=No+Thumbnail';
    clone.querySelector('.video-title').textContent = item.title || 'Video Media';
    clone.querySelector('.video-uploader').textContent = item.uploader ? `By ${item.uploader}` : '';
    
    if (item.duration) {
      const m = Math.floor(item.duration / 60);
      const s = item.duration % 60;
      clone.querySelector('.video-duration').textContent = `${m}:${s.toString().padStart(2, '0')}`;
    } else {
      clone.querySelector('.video-duration').style.display = 'none';
    }
    
    if (item.view_count) {
      clone.querySelector('.video-views').textContent = `${item.view_count.toLocaleString()} views`;
    } else {
      clone.querySelector('.video-views').style.display = 'none';
    }

    // Bind Quality Selection
    let selectedQuality = item.available_qualities ? item.available_qualities[0] : '1080';
    const qualityGrid = clone.querySelector('.quality-grid');
    qualityGrid.style.display = 'flex';
    qualityGrid.style.gap = '0.5rem';
    qualityGrid.style.flexWrap = 'wrap';

    const qualities = item.available_qualities || ['1080', '720', '480', '360'];
    qualities.forEach((q, idx) => {
      const btn = document.createElement('button');
      btn.className = `format-btn ${idx === 0 ? 'active' : ''}`;
      btn.style.padding = '0.5rem 1rem';
      btn.style.flex = '1';
      btn.innerHTML = `<span class="format-name" style="font-size:0.9rem">${q}p</span>`;
      btn.onclick = () => {
        qualityGrid.querySelectorAll('.format-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        selectedQuality = q;
      };
      qualityGrid.appendChild(btn);
    });

    // Bind Format Selection
    let selectedFormat = 'mp4';
    const formatBtns = clone.querySelectorAll('.format-grid .format-btn');
    formatBtns.forEach(btn => {
      btn.onclick = () => {
        formatBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        selectedFormat = btn.dataset.format;
      };
    });

    // Bind Download
    const downloadBtn = clone.querySelector('.start-download-btn');
    downloadBtn.onclick = () => {
      startDownload(item.url, selectedFormat, selectedQuality, item.title, item.playlist_index, downloadBtn);
    };

    container.appendChild(clone);
  });
}

// --- Download Flow ---
let currentJobId = null;
let progressSource = null;

async function startDownload(url, formatType, quality, title, playlistIndex, btn) {
  title = (title || 'Download').trim().replace(/[<>:"/\\|?*\n\r]/g, '').slice(0, 120);
  const ext = (formatType === 'mp3') ? 'mp3' : formatType;

  // --- Step 1: Ask user where to save BEFORE starting download ---
  let chosenFolder = null;

  if (window.pywebview) {
    // Desktop app: use native folder-picker via pywebview API
    try {
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="btn-loader" style="display:inline-block; border-color:white; border-top-color:transparent; margin-right:8px;"></span> Choosing folder...`;
      }
      chosenFolder = await window.pywebview.api.pick_save_folder();
      if (!chosenFolder) {
        // User cancelled the dialog
        if (btn) { btn.disabled = false; btn.innerHTML = 'Download'; }
        return;
      }
    } catch (e) {
      console.warn('Folder picker failed, will save to Downloads:', e);
    }
  } else if (typeof window.showSaveFilePicker === 'function') {
    // Standard browser: use File System Access API save picker
    try {
      const fileHandle = await window.showSaveFilePicker({
        suggestedName: `${title}.${ext}`,
        startIn: 'downloads',
      });
      // We'll use this handle after download completes
      window._pendingFileHandle = fileHandle;
    } catch (e) {
      if (e.name === 'AbortError') return;
    }
  }

  // --- Step 2: Start the backend download ---
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="btn-loader" style="display:inline-block; border-color:white; border-top-color:transparent; margin-right:8px;"></span> Starting...`;
  }

  try {
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, format: formatType, resolution: quality, playlist_index: playlistIndex })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    currentJobId = data.job_id;

    // --- Step 3: Track progress ---
    await new Promise((resolve, reject) => {
      let isDone = false;
      progressSource = new EventSource(`/api/progress/${currentJobId}`);
      progressSource.onmessage = (e) => {
        const job = JSON.parse(e.data);
        if (job.status === 'downloading') {
          if (btn) btn.innerHTML = `Downloading ${Math.round(job.progress)}%`;
        } else if (job.status === 'processing') {
          if (btn) btn.innerHTML = 'Processing media...';
        } else if (job.status === 'complete') {
          isDone = true; progressSource.close(); resolve();
        } else if (job.status === 'error') {
          isDone = true; progressSource.close(); reject(new Error(job.error));
        }
      };
      progressSource.onerror = () => {
        if (!isDone) { progressSource.close(); reject(new Error('Connection lost')); }
      };
    });

    // --- Step 4: Save file to chosen location ---
    if (btn) btn.innerHTML = 'Saving file...';

    if (chosenFolder) {
      // Desktop: copy directly to chosen folder via backend
      const saveRes = await fetch(`/api/save-file/${currentJobId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder: chosenFolder })
      });
      const saveData = await saveRes.json();
      if (!saveData.success) throw new Error(saveData.error || 'Failed to save file');

    } else if (window._pendingFileHandle) {
      // Browser with File System Access API
      const fileHandle = window._pendingFileHandle;
      window._pendingFileHandle = null;
      const fileRes = await fetch(`/api/get-file/${currentJobId}`);
      if (!fileRes.ok) throw new Error('Could not retrieve file');
      const writable = await fileHandle.createWritable();
      await fileRes.body.pipeTo(writable);

    } else {
      // Fallback: anchor download to default Downloads folder
      const a = document.createElement('a');
      a.href = `/api/get-file/${currentJobId}`;
      a.download = `${title}.${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      await new Promise(r => setTimeout(r, 2000));
    }

    // --- Step 5: Success state ---
    if (btn) {
      btn.innerHTML = '✔ Download Complete!';
      btn.style.background = '#22c55e';
      btn.style.borderColor = '#22c55e';
      setTimeout(() => {
        btn.innerHTML = 'Download Another';
        btn.style.background = '';
        btn.style.borderColor = '';
        btn.disabled = false;
        btn.onclick = () => {
          const urlInput = document.getElementById('url-input');
          urlInput.value = '';
          document.getElementById('results-container').innerHTML = '';
          urlInput.focus();
          window.scrollTo({ top: 0, behavior: 'smooth' });
        };
      }, 2500);
    }

  } catch (err) {
    if (btn) {
      btn.innerHTML = 'Error';
      btn.disabled = false;
      btn.style.background = '#FF3B3B';
    }
    showError(err.message);
  }
}
