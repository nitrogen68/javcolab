def get_full_ui(app_version, modals_html, is_dev=False):
    """Mengembalikan HTML lengkap untuk aplikasi."""
    template = r"""
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>javColab ke GDrive</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            body{font-family:'Inter',sans-serif;background:#0F172A;color:#E2E8F0}
            .card{border-radius:16px;box-shadow:0 4px 12px rgba(0,0,0,0.4);background:#1E293B;border:1px solid #334155}
            .tab-btn{border-bottom:2px solid transparent;color:#94A3B8}
            .tab-btn.active{border-color:#14B8A6;color:#14B8A6}
            .progress-bar{transition: width 300ms ease-out}
            input{ background:#0F172A; border-color:#334155; color:#E2E8F0 }
            input::placeholder{ color:#64748B }
            input:focus{ border-color:#2563EB; box-shadow:0 0 0 2px rgba(37,99,235,0.3) }
            button{transition: all 200ms}
            ::-webkit-scrollbar{width:8px}
            ::-webkit-scrollbar-track{background:#0F172A}
            ::-webkit-scrollbar-thumb{background:#334155;border-radius:4px}
            .chk-custom { accent-color: #ef4444; }
            .scrollbar-thin::-webkit-scrollbar { height: 4px; }
            .scrollbar-thin::-webkit-scrollbar-thumb { background: #4B5563; border-radius: 4px; }
            #driveIconSvg:hover { color: #4285F4; }
            .gh-line { color: #22D3EE; font-weight: 600; }
            .gh-line a { text-decoration: underline; }
            .gh-step { color: #67E8F9; opacity: 0.85; }
            .gh-status { color: #FBBF24; text-transform: capitalize; }

            .progress-bar.uploading {
                background: linear-gradient(90deg, #f59e0b, #fbbf24);
                animation: pulse 1.5s infinite;
            }
            @keyframes pulse {
                0% { opacity: 1; }
                50% { opacity: 0.5; }
                100% { opacity: 1; }
            }
        </style>
    </head>
    <body>
        <div class="max-w-7xl mx-auto p-4 md:p-8">
            <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-2 gap-3">
                <div>
                    <h1 class="text-2xl font-bold text-white tracking-tight">javColab</h1>
                    <p class="text-xs font-mono text-[#14B8A6] mt-1">__APP_VERSION__</p>
                </div>
                <button onclick="location.reload()" class="text-xs font-semibold bg-[#334155] hover:bg-[#475569] text-white px-4 py-2 rounded-lg border border-[#475569] shadow-lg">🔄 Muat Ulang UI</button>
            </div>
            <p class="text-sm text-[#94A3B8] mb-6">Penyimpanan: <b class="text-gray-300">Google Drive » javColab</b> &nbsp;·&nbsp; <span class="text-[#64748B]">Vercel UI + GitHub Actions Worker</span></p>
            
            <div class="flex gap-6 border-b border-[#334155] mb-6">
                <button data-tab="upload" class="tab-btn active pb-3 font-semibold text-sm tracking-wide">Upload Baru</button>
                <button data-tab="history" class="tab-btn pb-3 font-semibold text-sm tracking-wide">Riwayat Unduhan</button>
            </div>
            
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div id="uploadPanel" class="card p-5 sm:p-6">
                    <form id="uploadForm" class="space-y-5">
                        <div>
                            <label class="block text-sm font-semibold mb-2 text-[#CBD5E1]">Masukkan Kode Video</label>
                            <div class="flex gap-2 w-full relative">
                                <input type="text" id="urlInput" required placeholder="Contoh: vema 263" autocomplete="off" class="flex-1 min-w-0 h-12 px-4 rounded-xl outline-none text-sm border focus:border-blue-500 transition-all bg-[#0A0F1C]">
                                <button type="button" data-paste="urlInput" class="shrink-0 px-4 sm:px-5 h-12 bg-[#334155] hover:bg-[#475569] border border-[#334155] rounded-xl text-sm font-semibold text-[#E2E8F0]">Paste</button>
                            </div>
                            <div id="autoSuggestContainer" class="mt-2 hidden">
                                <p class="text-[10px] font-bold text-[#14B8A6] uppercase tracking-widest mb-1.5 flex items-center gap-1.5"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 1.1.9 2 2 2h12a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H6a2 2 0 00-2 2z"/></svg> Dari database Automation</p>
                                <div id="autoSuggestList" class="flex flex-col gap-1.5 max-h-56 overflow-y-auto pr-1"></div>
                            </div>
                        </div>
                        <div id="errorMsg" class="hidden text-xs text-red-400 bg-red-950/40 p-3 rounded-lg border border-red-900">❌ Error: Masukan kode pencarian, bukan URL!</div>
                        <button type="submit" id="submitBtn" class="w-full h-12 mt-2 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-700 hover:to-blue-600 text-white font-bold rounded-xl shadow-lg shadow-blue-900/30">Mulai Pencarian & Unduh</button>
                        <p id="loginWarning" class="hidden text-xs text-red-400 text-center mt-3 font-semibold transition-all">⚠️ Maaf, Anda harus login untuk menggunakan fitur ini.</p>
                    </form>
                    <div id="progressPanel" class="mt-6 hidden bg-[#1E293B] border border-[#334155] rounded-xl overflow-hidden shadow-xl">
                        <div class="p-5 border-b border-[#334155]">
                            <div class="flex justify-between items-center mb-4">
                                <div class="flex items-center gap-3 overflow-hidden pr-4">
                                    <div id="pSpinner" class="animate-spin rounded-full h-4 w-4 border-2 border-b-transparent border-[#14B8A6] shrink-0"></div>
                                    <span id="pFile" class="text-sm font-bold truncate text-white">Memproses...</span>
                                </div>
                                <span id="pPercent" class="text-lg font-black text-[#14B8A6] shrink-0">0%</span>
                            </div>
                            <div class="w-full bg-[#0F172A] rounded-full h-2.5 mb-4 overflow-hidden shadow-inner border border-[#334155]">
                                <div id="pBar" class="progress-bar bg-gradient-to-r from-[#0D9488] to-[#14B8A6] h-full rounded-full relative" style="width:0%"></div>
                            </div>
                            <div class="flex flex-col sm:flex-row justify-between text-[11px] gap-2">
                                <span id="pStatus" class="font-medium bg-[#0F172A] text-[#94A3B8] px-3 py-1.5 rounded-lg border border-[#334155] inline-block truncate">Menyiapkan...</span>
                                <span id="pMeta" class="font-mono font-medium bg-[#0F172A] text-[#94A3B8] px-3 py-1.5 rounded-lg border border-[#334155] inline-block whitespace-nowrap">Size: 0 B • Speed: 0 KB/s</span>
                            </div>
                        </div>
                        <div class="bg-[#0A0F1C]">
                            <div class="flex justify-between items-center px-4 py-2 border-b border-[#1E293B]">
                                <p class="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Terminal Log</p>
                                <button type="button" id="copyLogBtn" class="text-[9px] font-bold bg-[#1E293B] hover:bg-[#334155] text-[#94A3B8] hover:text-white px-2 py-1 rounded transition border border-[#334155] uppercase">Copy Log</button>
                            </div>
                            <div id="logBox" class="p-4 h-36 overflow-y-auto text-[11px] font-mono text-emerald-400 space-y-2 scroll-smooth">
                                <div class="text-gray-500">> System initialized...</div>
                            </div>
                        </div>
                    </div>
                    <div id="previewPanel" class="card p-4 sm:p-5 mt-4 hidden">
                        <div class="flex items-start gap-4 flex-col sm:flex-row">
                            <div id="previewThumbWrap" class="w-full sm:w-48 h-32 sm:h-32 rounded-xl bg-[#0A0F1C] border border-[#334155] overflow-hidden shrink-0">
                                <img id="previewThumb" class="w-full h-full object-cover hidden" alt="Thumbnail">
                                <div id="previewThumbPlaceholder" class="w-full h-full flex items-center justify-center text-3xl">🎬</div>
                            </div>
                            <div class="flex-1 min-w-0 w-full">
                                <p class="text-[10px] font-bold text-[#14B8A6] uppercase tracking-widest mb-1">Preview siap — konfirmasi untuk unduh penuh</p>
                                <h3 id="previewTitle" class="text-sm sm:text-base font-bold text-white mb-2 leading-snug">-</h3>
                                <div class="flex flex-wrap gap-2 text-[11px]">
                                    <span id="previewSize" class="px-2 py-1 bg-[#0F172A] text-[#94A3B8] rounded-lg border border-[#334155] font-mono">Ukuran: -</span>
                                    <span id="previewDur" class="px-2 py-1 bg-[#0F172A] text-[#94A3B8] rounded-lg border border-[#334155] font-mono">Durasi: -</span>
                                    <span id="previewFname" class="px-2 py-1 bg-[#0F172A] text-[#94A3B8] rounded-lg border border-[#334155] font-mono truncate max-w-full">File: -</span>
                                </div>
                                <button id="confirmDownloadBtn" class="mt-4 w-full sm:w-auto px-6 h-12 bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-700 hover:to-emerald-600 text-white font-bold rounded-xl shadow-lg shadow-emerald-900/30">⬇️ Unduh ke Google Drive</button>
                                <button id="resetBtn" class="mt-2 w-full sm:w-auto px-6 h-11 bg-gradient-to-r from-red-600 to-orange-500 hover:from-red-700 hover:to-orange-600 text-white font-bold rounded-xl shadow-lg shadow-red-900/30">🔄 Reset & Mulai Tugas Baru</button>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div id="historyPanel" class="card p-5 sm:p-6 hidden flex flex-col h-full max-h-[800px]">
                    <div class="flex justify-between items-center mb-6">
                        <h2 class="font-bold text-white text-lg tracking-tight">Riwayat Unduhan</h2>
                        <button onclick="showClearHistoryModal()" class="text-xs font-semibold bg-red-950/30 hover:bg-red-900/60 text-red-400 px-3 py-1.5 rounded-lg border border-red-900/50 transition">🗑️ Hapus Semua</button>
                    </div>
                    <div id="historyList" class="flex-1 space-y-3 overflow-y-auto pr-2 pb-2 relative">
                        <div class="flex flex-col items-center justify-center h-40 text-center">
                            <span class="text-4xl mb-2 opacity-50">📭</span>
                            <p class="text-[#64748B] text-sm">Belum ada riwayat unduhan</p>
                        </div>
                    </div>
                </div>
            </div>
            
            <div id="driveStatusContainer" class="mt-6 flex flex-col md:flex-row items-center justify-center bg-[#1E293B] border border-[#334155] rounded-xl p-5 gap-4 md:gap-8 relative overflow-visible">
                <div class="flex flex-col items-center justify-center min-w-0 text-center">
                    <svg id="driveIconSvg" class="w-10 h-10 text-gray-400 cursor-pointer transition hover:scale-110 mb-2 drop-shadow-md" fill="currentColor" viewBox="0 0 24 24" onclick="toggleDriveStatus()">
                        <path d="M12 14.5l-5.5-3.5 2-3.5h7l2 3.5-5.5 3.5zM12 9.5H5l-2.5 4.3L5 18h7l2.5-4.3L12 9.5zm0 0h7l2.5 4.3L19 18h-7l-2.5-4.3L12 9.5z"/>
                    </svg>
                    <p class="text-[11px] text-gray-400 font-bold uppercase tracking-wider mb-0.5">Connected to:</p>
                    <p id="driveEmail" class="text-sm font-semibold text-white truncate max-w-[280px] sm:max-w-xs px-2">-</p>
                </div>
                <div class="hidden md:block w-px h-16 bg-[#334155]"></div>
                <div class="flex flex-col sm:flex-row items-center justify-center gap-3 shrink-0 relative w-full md:w-auto">
                    <span id="driveStatusBadge" class="text-xs font-bold px-3 py-1.5 rounded-md bg-gray-700 text-gray-300 uppercase tracking-widest shadow-inner">Disconnect</span>
                    <button id="driveActionBtn" class="text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white px-6 py-2.5 rounded-lg transition shadow-lg shadow-blue-900/30 whitespace-nowrap">Hubungkan Drive</button>
                    
                    <div id="authPopover" class="hidden fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[92vw] sm:w-[320px] max-w-sm bg-[#1E293B] border border-[#334155] rounded-2xl shadow-[0_20px_60px_rgba(0,0,0,0.9)] z-[80] p-5 text-center transition-all">
                        <div class="flex justify-between items-center mb-3">
                            <p class="text-[#E2E8F0] font-bold text-xs sm:text-sm">Masukkan Kode Otorisasi:</p>
                            <button onclick="document.getElementById('authPopover').classList.add('hidden')" class="text-gray-400 hover:text-white text-xs px-1.5 py-0.5 rounded bg-[#334155]">✕</button>
                        </div>
                        <div class="bg-[#0F172A] p-3 rounded-xl border border-[#334155] text-center font-mono text-xl sm:text-2xl text-[#14B8A6] font-bold tracking-[0.2em] mb-4 select-all shadow-inner" id="popoverCode">------</div>
                        <div class="flex gap-3">
                            <button id="popoverCopyCodeBtn" class="flex-1 py-2 sm:py-2.5 bg-[#334155] hover:bg-[#475569] rounded-lg text-white font-bold transition text-[11px] sm:text-xs">Salin Kode</button>
                            <button id="popoverConnectBtn" class="flex-1 py-2 sm:py-2.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-white font-bold transition text-[11px] sm:text-xs shadow-md shadow-blue-900/30">Lanjutkan</button>
                        </div>
                    </div>
                </div>
            </div>

            __MODALS_INJECTION__

            <div id="successModal" class="hidden fixed inset-0 z-[60] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 transition-opacity">
                <div class="bg-[#1E293B] border border-[#334155] rounded-2xl w-full max-w-sm p-6 shadow-2xl relative flex flex-col text-center">
                    <div class="text-5xl mb-3 text-[#14B8A6]">✅</div>
                    <h3 class="text-lg font-bold text-white mb-2">Sukses Terhubung!</h3>
                    <p class="text-sm text-[#94A3B8] leading-relaxed mb-6">Semua unduhan akan tersimpan pada folder:<br><b class="text-white font-mono text-xs">Google Drive/javColab</b></p>
                    <button id="closeSuccessBtn" class="w-full py-2.5 bg-[#334155] hover:bg-[#475569] text-white font-semibold rounded-lg transition">Tutup</button>
                </div>
            </div>

            <div id="logoutModal" class="hidden fixed inset-0 z-[60] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 transition-opacity">
                <div class="bg-[#1E293B] border border-[#334155] rounded-2xl w-full max-w-sm p-6 shadow-2xl relative flex flex-col">
                    <h3 class="text-lg font-bold text-white mb-2 text-center">⚠️ Yakin ingin logout?</h3>
                    <p class="text-sm text-[#94A3B8] text-center mb-6">Anda harus melakukan otorisasi ulang jika ingin mengunggah file ke Drive lagi.</p>
                    <div class="flex gap-3">
                        <button id="logoutNoBtn" class="flex-1 py-2.5 bg-[#334155] hover:bg-[#475569] text-white font-semibold rounded-lg transition">No</button>
                        <button id="logoutYesBtn" class="flex-1 py-2.5 bg-red-600 hover:bg-red-700 text-white font-semibold rounded-lg transition">Ya</button>
                    </div>
                </div>
            </div>

            <div id="authModal" class="hidden fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-md p-4 transition-opacity duration-300 opacity-0">
                <div id="authModalBox" class="bg-[#1E293B] border border-[#334155] rounded-2xl w-full max-w-md p-6 shadow-[0_30px_60px_-15px_rgba(0,0,0,1)] relative flex flex-col transform scale-90 transition-all duration-300">
                    <button onclick="closeAuthModal()" class="absolute top-4 right-4 text-gray-400 hover:text-white hover:bg-[#334155] p-1.5 rounded-lg transition">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                    </button>
                    <h3 class="text-lg font-bold text-white mb-1">Otorisasi Google Drive</h3>
                    <p class="text-sm text-[#94A3B8] mb-5">Buka tautan berikut dan masukkan kode untuk mengizinkan akses ke Drive Anda.</p>
                    
                    <div class="bg-[#0F172A] rounded-xl p-4 border border-[#334155] mb-5 shadow-inner">
                        <div class="flex flex-col gap-4">
                            <div>
                                <span class="block text-[10px] text-gray-500 font-bold uppercase tracking-widest mb-1.5">Langkah 1: Buka Tautan</span>
                                <a id="authLinkUrl" href="#" target="_blank" class="inline-flex items-center gap-1.5 text-sm font-semibold text-blue-400 hover:text-blue-300 bg-blue-500/10 hover:bg-blue-500/20 px-3 py-2 rounded-lg transition">
                                    Buka Halaman Otorisasi
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                                </a>
                            </div>
                            <div class="border-t border-[#334155]"></div>
                            <div>
                                <span class="block text-[10px] text-gray-500 font-bold uppercase tracking-widest mb-1.5">Langkah 2: Masukkan Kode</span>
                                <div class="flex items-center justify-between gap-3 bg-[#1E293B] border border-[#334155] p-1.5 rounded-lg shadow-sm">
                                    <span id="authCodeTxt" class="text-lg font-mono font-bold text-[#14B8A6] pl-2 tracking-widest"></span>
                                    <button id="copyAuthCodeBtn" class="bg-[#334155] hover:bg-[#475569] text-white px-4 py-2 rounded-md text-xs font-bold transition flex items-center gap-2">
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
                                        Copy
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="flex items-center justify-center gap-3 py-2 bg-blue-950/30 rounded-lg border border-blue-900/50">
                        <div class="animate-spin rounded-full h-4 w-4 border-2 border-b-transparent border-blue-400"></div>
                        <span class="text-xs font-semibold text-blue-300">Menunggu Anda login...</span>
                    </div>
                </div>
            </div>

        <script>
            const IS_DEV = __IS_DEV__;
            let sessionToken = localStorage.getItem('driveSessionToken') || '';
            let pollTimer = null;
            let fileToDelete = null;
            let isDownloading = false;
            let currentTaskId = '';
            const PTASK_KEY = 'ptask';

            const driveIconSvg = document.getElementById('driveIconSvg');
            const driveEmail = document.getElementById('driveEmail');
            const driveStatusBadge = document.getElementById('driveStatusBadge');
            const driveActionBtn = document.getElementById('driveActionBtn');

            window.addEventListener('beforeunload', function (e) {
                if (isDownloading) {
                    e.preventDefault();
                    e.returnValue = 'Proses download sedang berjalan. Yakin ingin meninggalkan halaman?';
                }
            });

            function escapeHtml(str) { return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
            async function pasteInto(id) { try { document.getElementById(id).value = await navigator.clipboard.readText(); } catch { alert('Gagal mengakses clipboard.'); } }
            
            document.getElementById('copyLogBtn').addEventListener('click', async () => {
                const logBox = document.getElementById('logBox');
                try {
                    await navigator.clipboard.writeText(logBox.innerText);
                    const btn = document.getElementById('copyLogBtn');
                    const orig = btn.innerHTML;
                    btn.innerHTML = '✅ COPIED!';
                    setTimeout(() => { btn.innerHTML = orig; }, 2000);
                } catch (err) { alert('Gagal menyalin log'); }
            });

            document.querySelectorAll('[data-paste]').forEach(btn => { btn.addEventListener('click', () => pasteInto(btn.dataset.paste)); });
            document.querySelectorAll('[data-tab]').forEach(btn => { btn.addEventListener('click', () => setTab(btn.dataset.tab)); });
            
            function setTab(t) {
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === t));
                document.getElementById('uploadPanel').classList.toggle('hidden', t !== 'upload');
                document.getElementById('historyPanel').classList.toggle('hidden', t !== 'history');
                
                const driveContainer = document.getElementById('driveStatusContainer');
                if (driveContainer) {
                    driveContainer.classList.toggle('hidden', t !== 'upload');
                }

                if (t === 'history') loadHistory();
            }

            function formatBytes(b) {
                if (!b) return "0 B";
                const u = ['B', 'KB', 'MB', 'GB']; let i = 0;
                while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
                return b.toFixed(2) + ' ' + u[i];
            }

            const urlInput = document.getElementById('urlInput');

            // ===== AUTOMATION DATABASE AUTOCOMPLETE =====
            const autoContainer = document.getElementById('autoSuggestContainer');
            const autoList = document.getElementById('autoSuggestList');
            let autoTimer = null;
            urlInput.addEventListener('input', () => {
                const q = urlInput.value.trim();
                clearTimeout(autoTimer);
                if (q.length < 2) { autoContainer.classList.add('hidden'); autoList.innerHTML = ''; return; }
                autoTimer = setTimeout(async () => {
                    try {
                        const res = await fetch('/api/automation/search?q=' + encodeURIComponent(q));
                        if (!res.ok) throw new Error(`HTTP ${res.status}`);
                        const data = await res.json();
                        const results = data.results || [];
                        if (results.length > 0) {
                            autoList.innerHTML = results.map(r => {
                                const code = (r.code || r.id || r.name || '').trim();
                                const title = r.title || '';
                                const thumb = r.thumb || '';
                                const safeCode = escapeHtml(code);
                                const safeTitle = escapeHtml(title);
                                const thumbHtml = thumb ? `<img src="${escapeHtml(thumb)}" class="w-9 h-9 rounded-md object-cover border border-[#334155] shrink-0" onerror="this.style.display='none'">` : `<div class="w-9 h-9 rounded-md bg-[#334155] flex items-center justify-center text-sm shrink-0">🎬</div>`;
                                return `<button type="button" data-auto-code="${safeCode}" class="text-left w-full px-3 py-2 rounded-lg bg-[#0F172A] border border-[#334155] hover:border-[#14B8A6] hover:bg-[#1a2742] text-sm text-[#E2E8F0] transition flex items-center gap-3">${thumbHtml}<span class="min-w-0"><span class="block font-mono font-bold text-[#14B8A6]">${safeCode}</span>${safeTitle ? `<span class="block text-xs text-[#94A3B8] truncate">${safeTitle}</span>` : ''}</span></button>`;
                            }).join('');
                            autoContainer.classList.remove('hidden');
                        } else { autoContainer.classList.add('hidden'); autoList.innerHTML = ''; }
                    } catch (e) { console.error('[API Error] Gagal memuat saran automation:', e); autoContainer.classList.add('hidden'); }
                }, 350);
            });
            autoList.addEventListener('click', (e) => {
                const rnd = e.target.closest('[data-random-code]');
                if (rnd) {
                    urlInput.value = rnd.dataset.randomCode;
                    autoContainer.classList.add('hidden');
                    const form = document.getElementById('uploadForm');
                    if (form && typeof form.requestSubmit === 'function') { form.requestSubmit(); }
                    else { form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true })); }
                    return;
                }
                const btn = e.target.closest('[data-auto-code]');
                if (btn) { urlInput.value = btn.dataset.autoCode; autoContainer.classList.add('hidden'); urlInput.focus(); }
            });

            // ===== RANDOM SUGGESTION ON HOVER (HANYA VERSI DEV) =====
            let hoverSuggestionTimer = null;
            function loadRandomSuggestions() {
                if (!IS_DEV) return;
                if (urlInput.value.trim()) return;
                const n = 10 + Math.floor(Math.random() * 11); // 10-20
                fetch('/api/automation/random?n=' + n)
                    .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
                    .then(data => {
                        if (urlInput.value.trim()) return;
                        const results = data.results || [];
                        if (!results.length) { autoContainer.classList.add('hidden'); return; }
                        autoList.innerHTML = results.map(r => {
                            const code = (r.code || r.id || r.name || '').trim();
                            const title = r.title || '';
                            const thumb = r.thumb || '';
                            const safeCode = escapeHtml(code);
                            const safeTitle = escapeHtml(title);
                            const thumbHtml = thumb ? `<img src="${escapeHtml(thumb)}" class="w-9 h-9 rounded-md object-cover border border-[#334155] shrink-0" onerror="this.style.display='none'">` : `<div class="w-9 h-9 rounded-md bg-[#334155] flex items-center justify-center text-sm shrink-0">🎬</div>`;
                            return `<button type="button" data-random-code="${safeCode}" class="text-left w-full px-3 py-2 rounded-lg bg-[#0F172A] border border-[#334155] hover:border-[#14B8A6] hover:bg-[#1a2742] text-sm text-[#E2E8F0] transition flex items-center gap-3">${thumbHtml}<span class="min-w-0"><span class="block font-mono font-bold text-[#14B8A6]">${safeCode}</span>${safeTitle ? `<span class="block text-xs text-[#94A3B8] truncate">${safeTitle}</span>` : ''}<span class="block text-[10px] font-bold text-amber-400/90 mt-0.5">⚡ Saran acak (dev) — klik untuk cari langsung</span></span></button>`;
                        }).join('');
                        autoContainer.classList.remove('hidden');
                        autoList.scrollTop = 0;
                    })
                    .catch(e => console.error('[API Error] Gagal memuat saran acak:', e));
            }
            urlInput.addEventListener('mouseenter', () => {
                if (!IS_DEV) return;
                clearTimeout(hoverSuggestionTimer);
                hoverSuggestionTimer = setTimeout(loadRandomSuggestions, 450);
            });
            urlInput.addEventListener('mouseleave', () => {
                clearTimeout(hoverSuggestionTimer);
                setTimeout(() => { if (!autoContainer.matches(':hover')) { autoContainer.classList.add('hidden'); } }, 250);
            });
            autoContainer.addEventListener('mouseenter', () => clearTimeout(hoverSuggestionTimer));
            autoContainer.addEventListener('mouseleave', () => autoContainer.classList.add('hidden'));

            // ===== FLOW PREVIEW → KONFIRMASI → DOWNLOAD =====
            function showPreview(d) {
                const preview = d.preview || {};
                const panel = document.getElementById('previewPanel');
                document.getElementById('previewTitle').innerText = preview.title || d.clean_title || 'Judul tidak diketahui';
                document.getElementById('previewSize').innerText = 'Ukuran: ' + (preview.size || '—');
                document.getElementById('previewDur').innerText = 'Durasi: ' + (preview.duration || '—');
                document.getElementById('previewFname').innerText = 'File: ' + (preview.filename || '—');
                const img = document.getElementById('previewThumb');
                const ph = document.getElementById('previewThumbPlaceholder');
                img.classList.add('hidden'); ph.classList.remove('hidden');
                if (preview.thumb) {
                    img.onload = () => { ph.classList.add('hidden'); img.classList.remove('hidden'); };
                    img.onerror = () => { img.classList.add('hidden'); ph.classList.remove('hidden'); };
                    img.src = preview.thumb;
                }
                panel.classList.remove('hidden');
            }

            function renderLogs(d) {
                const logBox = document.getElementById('logBox');
                let html = '';
                const gh = d.github || {};
                const run = d.run || {};
                const runNo = gh.run_number || gh.run_id || '';
                if (gh.html_url || runNo) {
                    if (gh.html_url) {
                        html += `<div class="gh-line">> ▶️ GitHub Action: <a href="${escapeHtml(gh.html_url)}" target="_blank" rel="noopener" class="underline text-[#22D3EE]">run #${escapeHtml(String(runNo))}</a>${run.status ? ` · <span class="gh-status">${escapeHtml(run.status)}</span>` : ''}</div>`;
                    } else {
                        html += `<div class="gh-line">> ▶️ GitHub Action: run #${escapeHtml(String(runNo))}${run.status ? ` · ${escapeHtml(run.status)}` : ''}</div>`;
                    }
                    (run.steps || []).forEach(s => {
                        const mark = s.status === 'completed' ? (s.conclusion === 'success' ? '✅' : '❌') : (s.status === 'in_progress' ? '🔄' : '⏳');
                        html += `<div class="gh-step">>   ${mark} ${escapeHtml(s.name || '')}${s.status === 'in_progress' ? ' — sedang berjalan...' : ''}</div>`;
                    });
                }
                if (d.logs && d.logs.length) html += d.logs.map(l => `<div>> ${escapeHtml(l)}</div>`).join('');
                if (html) { logBox.innerHTML = html; logBox.scrollTop = logBox.scrollHeight; }
            }

            function startPolling(taskId) {
                clearInterval(pollTimer);
                const progressPanel = document.getElementById('progressPanel');
                pollTimer = setInterval(async () => {
                    try {
                        const res = await fetch('/api/progress/' + encodeURIComponent(taskId));
                        if (!res.ok) throw new Error(`HTTP ${res.status}`);
                        const d = await res.json();
                        
                        if (d.clean_title) { document.getElementById('pFile').innerText = d.clean_title; }
                        let pct = d.percent && d.percent > 0 ? Math.floor(d.percent) : 0;
                        if (pct <= 0 && d.logs && d.logs.length > 0) {
                            const lastLog = d.logs[d.logs.length - 1];
                            const match = lastLog.match(/Progres sedang berlangsung: (\d+)%/);
                            if (match) { pct = parseInt(match[1]); }
                        }
                        const speedStr = d.speed > (1024 * 1024) ? (d.speed / 1024 / 1024).toFixed(2) + ' MB/s' : (d.speed / 1024).toFixed(0) + ' KB/s';
                        const displaySize = d.downloaded > 0 ? formatBytes(d.downloaded) : "0 B";
                        document.getElementById('pBar').style.width = pct + '%';
                        document.getElementById('pPercent').innerText = pct + '%';
                        document.getElementById('pStatus').innerText = d.status || 'Memproses...';
                        document.getElementById('pMeta').innerText = `Size: ${displaySize} • Speed: ${speedStr}`;

                        renderLogs(d);

                        const pBar = document.getElementById('pBar');
                        const statusText = d.status || '';
                        if (statusText.includes('Mengunggah')) { pBar.classList.add('uploading'); } 
                        else { pBar.classList.remove('uploading'); }

                        const btn = document.getElementById('submitBtn');

                        if (d.status === 'preview_ready') {
                            clearInterval(pollTimer);
                            isDownloading = false;
                            document.getElementById('pBar').style.width = '100%';
                            document.getElementById('pPercent').innerText = '100%';
                            document.getElementById('pStatus').innerText = '✅ Preview ditemukan — klik "Unduh ke Google Drive" untuk kirim ke GDrive';
                            document.getElementById('pStatus').className = "font-bold bg-[#052e16] text-emerald-300 px-3 py-1.5 rounded-lg border border-[#166534] inline-block truncate";
                            document.getElementById('pSpinner').classList.add('hidden');
                            document.getElementById('pMeta').innerText = 'Preview menunggu konfirmasi';
                            showPreview(d);
                            localStorage.setItem(PTASK_KEY, JSON.stringify({ task_id: taskId, clean_title: d.clean_title, preview: d.preview }));
                            btn.disabled = false; btn.innerText = 'Cari & Tampilkan Preview'; btn.classList.remove('opacity-75');
                            return;
                        }

                        if (d.status === 'Selesai') {
                            clearInterval(pollTimer);
                            isDownloading = false;
                            localStorage.removeItem(PTASK_KEY);
                            progressPanel.className = "mt-6 bg-[#052e16] border border-[#166534] rounded-xl overflow-hidden shadow-xl shadow-green-900/20 transition-opacity duration-500";
                            document.getElementById('pStatus').className = "font-bold bg-[#14532d] text-green-300 px-3 py-1.5 rounded-lg border border-[#166534] inline-block truncate";
                            document.getElementById('pStatus').innerText = "✅ Berhasil Disimpan ke GDrive!";
                            document.getElementById('pBar').className = "progress-bar bg-green-500 h-full rounded-full relative";
                            document.getElementById('pSpinner').classList.add('hidden');
                            document.getElementById('previewPanel').classList.add('hidden');
                            btn.disabled = false; btn.innerText = 'Cari & Tampilkan Preview'; btn.classList.remove('opacity-75');
                            loadHistory();
                            setTimeout(() => {
                                progressPanel.classList.add('opacity-0');
                                setTimeout(() => {
                                    progressPanel.classList.add('hidden');
                                    progressPanel.classList.remove('opacity-0');
                                }, 500); 
                            }, 6000); 
                        }

                        if (d.status && d.status.startsWith('Gagal')) {
                            clearInterval(pollTimer);
                            isDownloading = false;
                            localStorage.removeItem(PTASK_KEY);
                            progressPanel.className = "mt-6 bg-[#450a0a] border border-[#991b1b] rounded-xl overflow-hidden shadow-xl shadow-red-900/20";
                            document.getElementById('pStatus').className = "font-bold bg-[#7f1d1d] text-red-300 px-3 py-1.5 rounded-lg border border-[#991b1b] inline-block truncate";
                            document.getElementById('pStatus').innerText = "❌ " + d.status;
                            document.getElementById('pBar').className = "progress-bar bg-red-600 h-full rounded-full relative";
                            document.getElementById('pSpinner').classList.add('hidden');
                            btn.disabled = false; btn.innerText = 'Cari & Tampilkan Preview'; btn.classList.remove('opacity-75');
                        }
                    } catch (pollErr) {
                        console.error('[API Error] Gagal membaca progress:', pollErr);
                    }
                }, 2000);
            }

            document.getElementById('uploadForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                if (!sessionToken) {
                    const warningText = document.getElementById('loginWarning');
                    warningText.classList.remove('hidden');
                    warningText.classList.add('animate-pulse');
                    setTimeout(() => {
                        warningText.classList.add('hidden');
                        warningText.classList.remove('animate-pulse');
                    }, 4000);
                    return; 
                }

                autoContainer.classList.add('hidden');
                localStorage.removeItem(PTASK_KEY);
                const btn = document.getElementById('submitBtn');
                const errorMsg = document.getElementById('errorMsg');
                const val = urlInput.value.trim();
                if (val.startsWith('http://') || val.startsWith('https://')) { errorMsg.classList.remove('hidden'); return; }
                else { errorMsg.classList.add('hidden'); }
                urlInput.value = '';
                
                const btnC = document.getElementById('confirmDownloadBtn');
                btnC.disabled = false; btnC.innerText = '⬇️ Unduh ke Google Drive'; btnC.classList.remove('opacity-50', 'cursor-not-allowed');
                document.getElementById('previewPanel').classList.add('hidden');
                const progressPanel = document.getElementById('progressPanel');
                progressPanel.className = "mt-6 bg-[#1E293B] border border-[#334155] rounded-xl overflow-hidden shadow-xl";
                document.getElementById('pBar').className = "progress-bar bg-gradient-to-r from-[#0D9488] to-[#14B8A6] h-full rounded-full relative";
                document.getElementById('pStatus').className = "font-medium bg-[#0F172A] text-[#94A3B8] px-3 py-1.5 rounded-lg border border-[#334155] inline-block truncate";
                document.getElementById('pSpinner').classList.remove('hidden');
                document.getElementById('pBar').style.width = '0%';
                document.getElementById('pPercent').innerText = '0%';
                document.getElementById('logBox').innerHTML = '<div class="text-gray-500">> Memulai sistem pencarian...</div>';
                btn.disabled = true; btn.innerText = 'Mencari & Menyiapkan Preview...'; btn.classList.add('opacity-75');
                progressPanel.classList.remove('hidden');
                document.getElementById('pFile').innerText = val;
                document.getElementById('pStatus').innerText = "Menghubungi Server...";
                isDownloading = true;
                
                try {
                    const dlRes = await fetch('/api/download', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url: val, filename: '', session_token: sessionToken })
                    });
                    
                    if (!dlRes.ok) throw new Error(`Server membalas dengan status: ${dlRes.status} - ${await dlRes.text()}`);
                    const dlData = await dlRes.json();
                    currentTaskId = dlData.task_id || val;
                    startPolling(currentTaskId);
                } catch (dlErr) {
                    console.error('[API Error] Gagal mengirim perintah unduh:', dlErr);
                    isDownloading = false;
                    progressPanel.className = "mt-6 bg-[#450a0a] border border-[#991b1b] rounded-xl overflow-hidden shadow-xl shadow-red-900/20";
                    document.getElementById('pStatus').className = "font-bold bg-[#7f1d1d] text-red-300 px-3 py-1.5 rounded-lg border border-[#991b1b] inline-block truncate";
                    document.getElementById('pStatus').innerText = "❌ Gagal: " + dlErr.message;
                    document.getElementById('pBar').className = "progress-bar bg-red-600 h-full rounded-full relative";
                    document.getElementById('pSpinner').classList.add('hidden');
                    btn.disabled = false; btn.innerText = 'Cari & Tampilkan Preview'; btn.classList.remove('opacity-75');
                    return; 
                }
            });

            // ===== KONFIRMASI: worker yang SAMA melanjutkan unduh (tanpa reset/restart) =====
            document.getElementById('confirmDownloadBtn').addEventListener('click', async () => {
                if (!currentTaskId || !sessionToken) return;
                const btnC = document.getElementById('confirmDownloadBtn');
                btnC.disabled = true; btnC.innerText = '⏳ Menyiapkan unduhan...';

                const progressPanel = document.getElementById('progressPanel');
                progressPanel.classList.remove('hidden');
                document.getElementById('pSpinner').classList.remove('hidden');
                document.getElementById('pStatus').className = "font-medium bg-[#0F172A] text-[#94A3B8] px-3 py-1.5 rounded-lg border border-[#334155] inline-block truncate";
                document.getElementById('pStatus').innerText = 'Melanjutkan unduhan penuh — progres tidak di-reset...';
                document.getElementById('logBox').innerHTML = '<div class="text-gray-500">> Konfirmasi diterima — worker yang sama melanjutkan unduhan penuh...</div>';
                document.getElementById('previewPanel').classList.remove('hidden');
                isDownloading = true;

                try {
                    const res = await fetch('/api/download/confirm', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ task_id: currentTaskId, session_token: sessionToken })
                    });
                    if (!res.ok) throw new Error(`Status ${res.status}: ${await res.text()}`);
                    btnC.disabled = true; btnC.innerText = '🔒 Unduhan diproses — tombol dinonaktifkan'; btnC.classList.add('opacity-50', 'cursor-not-allowed');
                    startPolling(currentTaskId);
                } catch (err) {
                    console.error('[API Error] Gagal konfirmasi unduhan:', err);
                    isDownloading = false;
                    progressPanel.className = "mt-6 bg-[#450a0a] border border-[#991b1b] rounded-xl overflow-hidden shadow-xl shadow-red-900/20";
                    document.getElementById('pStatus').className = "font-bold bg-[#7f1d1d] text-red-300 px-3 py-1.5 rounded-lg border border-[#991b1b] inline-block truncate";
                    document.getElementById('pStatus').innerText = "❌ Gagal konfirmasi: " + err.message;
                    document.getElementById('pBar').className = "progress-bar bg-red-600 h-full rounded-full relative";
                    document.getElementById('pSpinner').classList.add('hidden');
                    btnC.disabled = false; btnC.innerText = '⬇️ Unduh ke Google Drive';
                    document.getElementById('previewPanel').classList.remove('hidden');
                }
            });
            
            // ===== RESET: dialog konfirmasi → HARD RESET murni =====
            function openResetModal() {
                const m = document.getElementById('resetModal');
                if (m) { m.classList.remove('hidden'); m.classList.add('flex'); }
            }
            function closeResetModal() {
                const m = document.getElementById('resetModal');
                if (m) { m.classList.add('hidden'); m.classList.remove('flex'); }
            }

            function resetTask() {
                openResetModal();
            }

            async function performHardReset() {
                clearInterval(pollTimer);
                pollTimer = null;
                isDownloading = false;

                // Hapus task/log/result lama di server (TANPA dispatch / memproses).
                try {
                    await fetch('/api/reset', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ task_id: currentTaskId, session_token: sessionToken })
                    });
                } catch (err) { console.error('[API Error] Gagal reset state server:', err); }

                currentTaskId = '';
                // Hapus SEMUA state frontend: localStorage + sessionStorage.
                try { localStorage.clear(); } catch (e) {}
                try { sessionStorage.clear(); } catch (e) {}
                sessionToken = '';
                updateDriveUI(false);
                document.getElementById('authPopover').classList.add('hidden');

                const progressPanel = document.getElementById('progressPanel');
                progressPanel.className = "mt-6 bg-[#1E293B] border border-[#334155] rounded-xl overflow-hidden shadow-xl";
                progressPanel.classList.remove('hidden', 'opacity-0');
                document.getElementById('previewPanel').classList.add('hidden');

                document.getElementById('pBar').className = "progress-bar bg-gradient-to-r from-[#0D9488] to-[#14B8A6] h-full rounded-full relative";
                document.getElementById('pBar').style.width = '0%';
                document.getElementById('pPercent').innerText = '0%';
                document.getElementById('pStatus').className = "font-medium bg-[#0F172A] text-[#94A3B8] px-3 py-1.5 rounded-lg border border-[#334155] inline-block truncate";
                document.getElementById('pStatus').innerText = 'Menyiapkan...';
                document.getElementById('pSpinner').classList.remove('hidden');
                document.getElementById('pMeta').innerText = 'Size: 0 B • Speed: 0 KB/s';
                document.getElementById('pFile').innerText = 'Memproses...';
                document.getElementById('logBox').innerHTML = '<div class="text-gray-500">> System initialized...</div>';

                const submitBtn = document.getElementById('submitBtn');
                submitBtn.disabled = false; submitBtn.innerText = 'Mulai Pencarian & Unduh'; submitBtn.classList.remove('opacity-75');

                const confirmBtn = document.getElementById('confirmDownloadBtn');
                confirmBtn.disabled = false; confirmBtn.innerText = '⬇️ Unduh ke Google Drive'; confirmBtn.classList.remove('opacity-50', 'cursor-not-allowed');

                const input = document.getElementById('urlInput');
                if (input) { input.value = ''; input.focus(); }
                const errorMsg = document.getElementById('errorMsg');
                if (errorMsg) errorMsg.classList.add('hidden');
                const autoContainer = document.getElementById('autoSuggestContainer');
                if (autoContainer) autoContainer.classList.add('hidden');

                closeResetModal();
            }

            document.getElementById('resetBtn').addEventListener('click', resetTask);
            document.getElementById('confirmResetBtn').addEventListener('click', performHardReset);
            document.getElementById('cancelResetBtn').addEventListener('click', closeResetModal);
            document.getElementById('resetModal').addEventListener('click', (e) => { if (e.target.id === 'resetModal') closeResetModal(); });
            
            // 🟢 LOAD HISTORY DENGAN TOMBOL VIEW (STREAMING MANUAL KE DRIVE) DI BAWAH TOMBOL DELETE
            async function loadHistory() {
                try {
                    const token = sessionToken;
                    const res = await fetch(`/api/history?session_token=${encodeURIComponent(token)}`);
                    if (!res.ok) throw new Error(`HTTP Error ${res.status}: ${await res.text()}`);
                    const data = await res.json();
                    
                    const historyList = document.getElementById('historyList');
                    if (!data.length) { 
                        historyList.innerHTML = '<div class="flex flex-col items-center justify-center h-40 text-center"><span class="text-4xl mb-2 opacity-50">📭</span><p class="text-[#64748B] text-sm">Belum ada riwayat unduhan</p></div>'; 
                        return; 
                    }
                    
                    historyList.innerHTML = data.map(item => {
                        const safeName = escapeHtml(item.name);
                        const ext = (item.name.split('.').pop() || '').toLowerCase();
                        const isSuccess = item.status === 'success';
                        const driveId = item.drive_file_id || '';
                        
                        let thumbSrc = isSuccess && ['mp4', 'webm', 'mkv', 'avi'].includes(ext) 
                            ? `/api/thumbnail/${encodeURIComponent(item.name)}?session_token=${encodeURIComponent(token)}` 
                            : '';
                        let thumbHtml = thumbSrc ? `<img src="${thumbSrc}" class="w-full h-full object-cover group-hover:scale-110 transition duration-500">` : '<div class="text-2xl h-full w-full flex items-center justify-center">📄</div>';
                        
                        return `<div class="history-item group relative flex items-center gap-4 p-3.5 bg-[#1E293B] hover:bg-[#283548] border border-[#334155] hover:border-[#475569] rounded-xl transition-all shadow-sm" data-name="${safeName}" data-status="${item.status}">
                            <div class="w-16 h-14 rounded-lg bg-black border border-[#475569] overflow-hidden shrink-0 relative">${thumbHtml}</div>
                            <div class="flex-1 min-w-0 pr-14">
                                <h4 class="font-semibold text-sm text-gray-100 truncate mb-1.5 leading-tight">${safeName}</h4>
                                <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                                    <span class="px-2 py-0.5 ${isSuccess ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'} border rounded text-[10px] font-bold tracking-wide uppercase">${isSuccess ? 'Berhasil' : 'Gagal'}</span>
                                    <span class="text-[11px] font-mono text-[#94A3B8]">${escapeHtml(item.size)}</span>
                                    <span class="text-[10px] text-gray-600">•</span>
                                    <span class="text-[11px] text-[#94A3B8] font-medium">${escapeHtml(item.time)}</span>
                                </div>
                            </div>
                            
                            <!-- Kumpulan Tombol Aksi (Delete & View tersusun vertikal di kanan) -->
                            <div class="absolute right-4 top-1/2 -translate-y-1/2 flex flex-col gap-2 md:opacity-0 md:group-hover:opacity-100 transition-all">
                                <button class="delete-btn w-9 h-9 flex items-center justify-center rounded-full bg-red-950/40 text-red-400 hover:bg-red-600 hover:text-white transition-all shadow border border-transparent hover:border-red-500" data-name="${safeName}" title="Hapus Data">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                                </button>
                                
                                ${isSuccess && driveId && driveId !== 'None' && driveId !== 'null' ? `
                                
                               <a href="https://drive.google.com/file/d/${driveId}/preview" target="_blank"  class="w-9 h-9 flex items-center justify-center rounded-full bg-blue-950/40 text-blue-400 hover:bg-blue-600 hover:text-white transition-all shadow border border-transparent hover:border-blue-500" title="View / Streaming Manual di Google Drive">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path></svg>
                                </a>
                                ` : ''}
                            </div>
                        </div>`;
                    }).join('');
                } catch (err) {
                    console.error('[API Error] Gagal memuat daftar riwayat:', err);
                    document.getElementById('historyList').innerHTML = `<div class="text-center text-red-400 mt-4 p-4 bg-red-950/30 rounded-xl border border-red-900/50">❌ Gagal memuat riwayat.<br><span class="text-xs text-red-500/80">${err.message}</span></div>`;
                }
            }
            
            function showClearHistoryModal() {
                const m = document.getElementById('clearAllModal');
                if (m) { m.classList.remove('hidden'); m.classList.add('flex'); }
            }
            
            // 🟢 ERROR HANDLING API 5: /api/history/delete
            document.getElementById('confirmDelBtn').addEventListener('click', async () => {
                if (!fileToDelete) return;
                const deleteFromDrive = document.getElementById('deleteFromDrive').checked;
                const btn = document.getElementById('confirmDelBtn');
                const orig = btn.innerHTML;
                
                btn.innerHTML = '<span class="animate-pulse">Menghapus...</span>';
                btn.disabled = true;
                
                try {
                    const res = await fetch('/api/history/delete', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            filename: fileToDelete,
                            delete_file: deleteFromDrive,
                            session_token: sessionToken
                        })
                    });
                    
                    if (!res.ok) throw new Error(`Status ${res.status}: ${await res.text()}`);
                    
                } catch (err) { 
                    console.error('[API Error] Gagal menghapus file dari server:', err);
                    alert('❌ Gagal menghapus file! Pesan Server: ' + err.message); 
                } finally {
                    btn.innerHTML = orig;
                    btn.disabled = false;
                    closeDeleteModal();
                    loadHistory();
                }
            });

            // 🟢 ERROR HANDLING API 6: /api/history/clear
            async function clearHistory() {
                const btn = document.getElementById('confirmClearBtn');
                if (!btn) return;
                const orig = btn.innerHTML;
                const token = sessionToken; 
                
                btn.innerHTML = '<span class="animate-pulse">Mereset...</span>';
                btn.disabled = true;
                
                try {
                    const res = await fetch(`/api/history/clear?session_token=${encodeURIComponent(token)}`, { method: 'DELETE' });
                    
                    if (!res.ok) throw new Error(`Status ${res.status}: ${await res.text()}`);
                    
                    const m = document.getElementById('clearAllModal');
                    if (m) { m.classList.add('hidden'); m.classList.remove('flex'); }
                } catch (err) {
                    console.error("[API Error] Gagal mereset semua history:", err);
                    alert("❌ Gagal mereset history! Pesan Server: " + err.message);
                } finally {
                    btn.innerHTML = orig;
                    btn.disabled = false;
                    loadHistory();
                }
            }
            
            const cancelClearBtn = document.getElementById('cancelClearBtn');
            if (cancelClearBtn) {
                cancelClearBtn.addEventListener('click', () => {
                    const m = document.getElementById('clearAllModal');
                    if (m) { m.classList.add('hidden'); m.classList.remove('flex'); }
                });
            }

            const confirmClearBtn = document.getElementById('confirmClearBtn');
            if (confirmClearBtn) { confirmClearBtn.addEventListener('click', clearHistory); }

            // 🟢 HANYA MENANGANI AKSI TOMBOL DELETE (LOGIKA MODAL PEMUTAR VIDEO DIHAPUS)
            document.getElementById('historyList').addEventListener('click', (e) => {
                const delBtn = e.target.closest('.delete-btn');
                if (delBtn) { 
                    e.stopPropagation(); 
                    showDeleteModal(delBtn.dataset.name); 
                    return; 
                }
            });
            
            function showDeleteModal(filename) {
                fileToDelete = filename;
                document.getElementById('delFileName').innerText = filename;
                document.getElementById('deleteFromDrive').checked = false;
                document.getElementById('deleteModal').classList.remove('hidden');
                document.getElementById('deleteModal').classList.add('flex');
            }
            
            function closeDeleteModal() {
                fileToDelete = null;
                document.getElementById('deleteModal').classList.add('hidden');
                document.getElementById('deleteModal').classList.remove('flex');
            }
            
            document.getElementById('deleteModal').addEventListener('click', (e) => { if (e.target.id === 'deleteModal') closeDeleteModal(); });
            
            // ===== FUNGSI MODAL SUKSES & LOGOUT =====
            function openSuccessModal() {
                document.getElementById('successModal').classList.remove('hidden');
                document.getElementById('successModal').classList.add('flex');
            }
            function closeSuccessModal() {
                document.getElementById('successModal').classList.add('hidden');
                document.getElementById('successModal').classList.remove('flex');
            }
            function openLogoutModal() {
                document.getElementById('logoutModal').classList.remove('hidden');
                document.getElementById('logoutModal').classList.add('flex');
            }
            function closeLogoutModal() {
                document.getElementById('logoutModal').classList.add('hidden');
                document.getElementById('logoutModal').classList.remove('flex');
            }

            document.getElementById('closeSuccessBtn').addEventListener('click', closeSuccessModal);
            document.getElementById('logoutNoBtn').addEventListener('click', closeLogoutModal);
            document.getElementById('logoutYesBtn').addEventListener('click', () => {
                closeLogoutModal();
                disconnectDrive();
            });
            
            // ===== GOOGLE DRIVE AUTH =====
            function updateDriveUI(connected, email = '') {
                if (connected) {
                    driveIconSvg.classList.add('text-blue-500');
                    driveIconSvg.classList.remove('text-gray-400');
                    driveEmail.innerText = email;
                    driveStatusBadge.innerText = 'Connected';
                    driveStatusBadge.classList.remove('bg-gray-700', 'text-gray-300', 'bg-red-900', 'text-red-400');
                    driveStatusBadge.classList.add('bg-blue-900', 'text-blue-400');
                    driveActionBtn.innerText = 'Putuskan';
                    driveActionBtn.classList.remove('bg-blue-600', 'hover:bg-blue-700');
                    driveActionBtn.classList.add('bg-red-600', 'hover:bg-red-700');
                } else {
                    driveIconSvg.classList.add('text-gray-400');
                    driveIconSvg.classList.remove('text-blue-500');
                    driveEmail.innerText = '-';
                    driveStatusBadge.innerText = 'Disconnect';
                    driveStatusBadge.classList.remove('bg-blue-900', 'text-blue-400', 'bg-red-900', 'text-red-400');
                    driveStatusBadge.classList.add('bg-gray-700', 'text-gray-300');
                    driveActionBtn.innerText = 'Hubungkan Drive';
                    driveActionBtn.classList.remove('bg-red-600', 'hover:bg-red-700');
                    driveActionBtn.classList.add('bg-blue-600', 'hover:bg-blue-700');
                }
            }

            async function checkDriveStatus() {
                if (!sessionToken) { updateDriveUI(false); return; }
                try {
                    const res = await fetch(`/api/auth/status?session_token=${encodeURIComponent(sessionToken)}`);
                    if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
                    const data = await res.json();
                    
                    if (data.connected) { updateDriveUI(true, data.email || ''); } 
                    else {
                        console.warn('Token tidak dikenali, menghapus sesi.');
                        localStorage.removeItem('driveSessionToken');
                        sessionToken = '';
                        updateDriveUI(false);
                    }
                } catch (e) {
                    console.error('[API Error] Gagal cek status Drive:', e);
                }
            }
            
            function showAuthModal(url, code) {
                document.getElementById('authLinkUrl').href = url;
                document.getElementById('authCodeTxt').innerText = code;
                const modal = document.getElementById('authModal');
                const modalBox = document.getElementById('authModalBox');
                modal.classList.remove('hidden');
                setTimeout(() => {
                    modal.classList.remove('opacity-0');
                    modal.classList.add('opacity-100');
                    modalBox.classList.remove('scale-90');
                    modalBox.classList.add('scale-100');
                }, 10);
            }
            
            function closeAuthModal() {
                const modal = document.getElementById('authModal');
                const modalBox = document.getElementById('authModalBox');
                modal.classList.remove('opacity-100');
                modal.classList.add('opacity-0');
                modalBox.classList.remove('scale-100');
                modalBox.classList.add('scale-90');
                setTimeout(() => { modal.classList.add('hidden'); }, 300);
            }

            document.getElementById('copyAuthCodeBtn').addEventListener('click', async () => {
                const code = document.getElementById('authCodeTxt').innerText;
                try {
                    await navigator.clipboard.writeText(code);
                    const btn = document.getElementById('copyAuthCodeBtn');
                    const orig = btn.innerHTML;
                    btn.innerHTML = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Copied!';
                    setTimeout(() => { btn.innerHTML = orig; }, 2000);
                } catch (err) { alert('Gagal menyalin kode'); }
            });

            let authWindow = null;

            async function startAuthFlow() {
                try {
                    const res = await fetch('/api/auth/device', { method: 'POST' });
                    if (!res.ok) throw new Error(`HTTP Error ${res.status}: ${await res.text()}`);
                    const data = await res.json();
                    
                    if (!data.user_code) throw new Error(data.detail || 'Respons JSON tidak valid dari server');
                    
                    const userCode = data.user_code;
                    const url = data.verification_url;
                    const deviceCode = data.device_code;
                    window._auth_data = { userCode, url, deviceCode };
                    
                    const popover = document.getElementById('authPopover');
                    document.getElementById('popoverCode').innerText = userCode;
                    popover.classList.remove('hidden');
                    
                } catch (e) {
                    console.error('[API Error] Gagal memulai device flow:', e);
                    alert('❌ Gagal menghubungi server otorisasi: ' + e.message);
                }
            }

            document.getElementById('popoverConnectBtn').addEventListener('click', () => {
                const { url, deviceCode } = window._auth_data || {};
                if (!url) return;
                authWindow = window.open(url, '_blank');
                if (!authWindow || authWindow.closed) {
                    alert('⚠️ Popup diblokir! Izinkan popup (pop-up blocker) untuk melanjutkan.');
                    return;
                }
                document.getElementById('authPopover').classList.add('hidden');
                
                const pollInterval = setInterval(async () => {
                    try {
                        const pollRes = await fetch('/api/auth/poll', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ device_code: deviceCode })
                        });
                        
                        if (!pollRes.ok) throw new Error(`HTTP Error ${pollRes.status}: ${await pollRes.text()}`);
                        const pollData = await pollRes.json();
                        
                        if (pollData.status === 'success') {
                            clearInterval(pollInterval);
                            sessionToken = pollData.session_token;
                            localStorage.setItem('driveSessionToken', sessionToken);
                            updateDriveUI(true, pollData.email);
                            
                            try { if (authWindow) authWindow.close(); } catch(err) { console.warn('COOP Memblokir window.close'); }
                            openSuccessModal();
                            
                        } else if (pollData.status !== 'pending') {
                            clearInterval(pollInterval);
                            try { if (authWindow) authWindow.close(); } catch(err) { console.warn('COOP Memblokir window.close'); }
                            alert('⚠️ Gagal menghubungkan Drive atau batas waktu otorisasi telah habis.');
                        }
                    } catch (pollErr) {
                        console.error('[API Error] Polling error:', pollErr);
                        clearInterval(pollInterval);
                        try { if (authWindow) authWindow.close(); } catch(err) { console.warn('COOP Memblokir window.close'); }
                        alert('❌ Terjadi kesalahan fatal saat berkomunikasi dengan server: ' + pollErr.message);
                    }
                }, 3000);
            });

            document.getElementById('popoverCopyCodeBtn').addEventListener('click', async () => {
                const code = document.getElementById('popoverCode').innerText;
                try {
                    await navigator.clipboard.writeText(code);
                    const btn = document.getElementById('popoverCopyCodeBtn');
                    const orig = btn.innerHTML;
                    btn.innerHTML = '✅ Tersalin!';
                    setTimeout(() => { btn.innerHTML = orig; }, 2000);
                } catch (err) { alert('Gagal menyalin kode'); }
            });

            function disconnectDrive() {
                localStorage.removeItem('driveSessionToken');
                sessionToken = '';
                updateDriveUI(false);
                document.getElementById('authPopover').classList.add('hidden');
                try { if (authWindow) authWindow.close(); } catch(err) { console.warn('COOP Memblokir window.close'); }
            }

            function toggleDriveStatus() {
                if (sessionToken) { openLogoutModal(); } 
                else { startAuthFlow(); }
            }

            driveActionBtn.addEventListener('click', () => {
                if (sessionToken) { openLogoutModal(); } 
                else { startAuthFlow(); }
            });

            // ===== RESUME PREVIEW SAAT HALAMAN DI-RELOAD (state via localStorage task_id) =====
            (function restorePreviewState() {
                try {
                    const raw = localStorage.getItem(PTASK_KEY);
                    if (!raw) return;
                    const saved = JSON.parse(raw);
                    if (!saved || !saved.task_id) { localStorage.removeItem(PTASK_KEY); return; }
                    const progressPanel = document.getElementById('progressPanel');
                    currentTaskId = saved.task_id;
                    showPreview({ preview: saved.preview || {}, clean_title: saved.clean_title || '' });
                    progressPanel.classList.remove('hidden');
                    document.getElementById('pFile').innerText = saved.clean_title || (saved.preview && saved.preview.filename) || currentTaskId;
                    document.getElementById('pBar').className = "progress-bar bg-gradient-to-r from-[#0D9488] to-[#14B8A6] h-full rounded-full relative";
                    document.getElementById('pBar').style.width = '100%';
                    document.getElementById('pPercent').innerText = '100%';
                    document.getElementById('pStatus').className = "font-bold bg-[#052e16] text-emerald-300 px-3 py-1.5 rounded-lg border border-[#166534] inline-block truncate";
                    document.getElementById('pStatus').innerText = '✅ Preview ditemukan — klik "Unduh ke Google Drive" untuk kirim ke GDrive';
                    document.getElementById('pSpinner').classList.add('hidden');
                    document.getElementById('pMeta').innerText = 'Preview menunggu konfirmasi';
                    document.getElementById('logBox').innerHTML = '<div class="text-gray-500">> Memulihkan sesi terakhir — polling berlanjut tiap 2 detik...</div>';
                    startPolling(currentTaskId);
                } catch (err) {
                    console.error('[API Error] Gagal memulihkan preview terakhir:', err);
                    try { localStorage.removeItem(PTASK_KEY); } catch (e2) {}
                }
            })();

            checkDriveStatus();
        </script>
    </body>
    </html>
    """
    template = template.replace("__APP_VERSION__", app_version)
    template = template.replace("__MODALS_INJECTION__", modals_html)
    template = template.replace("__IS_DEV__", "true" if is_dev else "false")
    return template
