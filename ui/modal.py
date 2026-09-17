# ui/modal.py — port asli (dari puppeter), netral terhadap backend
def get_modals_html():
    return """
    <!-- Modal Preview -->
    <div id="modal" class="hidden fixed inset-0 bg-black/95 backdrop-blur-md z-[60] items-center justify-center p-4">
        <div id="modalBox" class="card w-full max-w-5xl overflow-hidden shadow-2xl border border-gray-800 bg-black">
            <div class="flex justify-between items-center p-4 bg-[#1E293B] border-b border-[#334155]">
                <h3 id="mTitle" class="font-bold text-white truncate pr-4 text-sm md:text-base"></h3>
                <button type="button" id="closeModalBtn" class="w-8 h-8 flex items-center justify-center rounded-full bg-[#334155] hover:bg-red-500 hover:text-white text-[#E2E8F0] transition font-bold">&times;</button>
            </div>
            <div id="mContent" class="bg-black min-h-[300px] flex items-center justify-center aspect-video w-full"></div>
        </div>
    </div>

    <!-- Modal Hapus Satuan -->
    <div id="deleteModal" class="hidden fixed inset-0 bg-black/90 backdrop-blur-sm z-[70] items-center justify-center p-4">
        <div class="card bg-[#1E293B] border border-[#334155] w-full max-w-md p-6 rounded-xl shadow-2xl">
            <h3 class="text-xl font-bold text-white mb-2 flex items-center gap-2">
                <svg class="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                Hapus Riwayat
            </h3>
            <p class="text-sm text-[#94A3B8] mb-5">Anda yakin ingin menghapus <span id="delFileName" class="font-semibold text-gray-200 bg-gray-800 px-1 rounded"></span> dari daftar?</p>
            <label class="flex items-start gap-3 p-4 bg-red-950/20 border border-red-900/50 rounded-lg mb-6 cursor-pointer hover:bg-red-900/40 transition">
                <input type="checkbox" id="deleteFromDrive" class="mt-0.5 w-5 h-5 rounded border-gray-600 bg-gray-700 chk-custom cursor-pointer">
                <div class="flex-1">
                    <span class="block text-sm text-red-200 font-bold mb-0.5">Hapus juga file fisik di GDrive</span>
                    <span class="block text-[11px] text-red-400/80 leading-tight">Mencentang ini akan menghapus permanen video .mp4 dan thumbnail dari penyimpanan awan.</span>
                </div>
            </label>
            <div class="flex justify-end gap-3 mt-4">
                <button id="cancelDelBtn" class="px-5 py-2.5 text-sm font-semibold text-[#E2E8F0] bg-[#334155] hover:bg-[#475569] rounded-xl transition">Batal</button>
                <button id="confirmDelBtn" class="px-5 py-2.5 text-sm font-bold text-white bg-red-600 hover:bg-red-700 rounded-xl transition shadow-lg shadow-red-900/40 flex items-center gap-2">
                    <span>Ya, Hapus</span>
                </button>
            </div>
        </div>
    </div>

    <!-- Modal Hapus Semua -->
    <div id="clearAllModal" class="hidden fixed inset-0 bg-black/90 backdrop-blur-sm z-[70] items-center justify-center p-4">
        <div class="card bg-[#1E293B] border border-[#334155] w-full max-w-md p-6 rounded-xl shadow-2xl">
            <h3 class="text-xl font-bold text-white mb-2 flex items-center gap-2">
                <svg class="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                Hapus Semua Riwayat
            </h3>
            <p class="text-sm text-[#94A3B8] mb-6">Anda yakin ingin menghapus <b>seluruh</b> riwayat unduhan secara total? Tindakan ini tidak dapat dibatalkan.</p>
            <div class="flex justify-end gap-3 mt-4">
                <button id="cancelClearBtn" class="px-5 py-2.5 text-sm font-semibold text-[#E2E8F0] bg-[#334155] hover:bg-[#475569] rounded-xl transition">Batal</button>
                <button id="confirmClearBtn" class="px-5 py-2.5 text-sm font-bold text-white bg-red-600 hover:bg-red-700 rounded-xl transition shadow-lg shadow-red-900/40 flex items-center gap-2">
                    <span>Ya, Hapus Semua</span>
                </button>
            </div>
        </div>
    </div>
    """