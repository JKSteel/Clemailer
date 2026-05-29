// ── Preview ───────────────────────────────────────────────────────────────────

function switchPreview(el) {
    document.querySelectorAll('.attachment-item').forEach(e => e.classList.remove('active'));
    el.classList.add('active');
    const area = document.getElementById('preview-area');
    if (!area) return;
    const { mime, url } = el.dataset;
    if (mime.startsWith('image/'))
        area.innerHTML = `<img class="preview-img" src="${url}">`;
    else if (mime === 'application/pdf')
        area.innerHTML = `<embed class="preview-pdf" src="${url}" type="application/pdf">`;
    else
        area.innerHTML = `<span class="preview-empty">No inline preview for this file type</span>`;
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function showToast(text, type = 'success') {
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = text;
    document.getElementById('toast-container').appendChild(el);
    requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('show')));
    setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.remove(), 250); }, 4500);
}

// ── Modal (replaceable confirm with "Don't ask again") ────────────────────────

function modal(key, message) {
    return new Promise(resolve => {
        if (key && localStorage.getItem('suppress_' + key) === '1') {
            resolve(true);
            return;
        }

        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';

        const box      = document.createElement('div');    box.className = 'modal-box';
        const msg      = document.createElement('p');      msg.className = 'modal-msg';
        msg.textContent = message;

        const supLabel = document.createElement('label');  supLabel.className = 'modal-suppress';
        const cb       = document.createElement('input');
        cb.type = 'checkbox';
        supLabel.append(cb, " Don't ask again");

        const btns   = document.createElement('div');     btns.className = 'modal-btns';
        const cancel = document.createElement('button');  cancel.className = 'btn btn-ghost';   cancel.textContent = 'Cancel';
        const ok     = document.createElement('button');  ok.className     = 'btn btn-primary'; ok.textContent     = 'OK';
        btns.append(cancel, ok);

        box.append(msg, supLabel, btns);
        overlay.appendChild(box);
        document.body.appendChild(overlay);
        ok.focus();

        const dismiss = (val) => { overlay.remove(); resolve(val); };
        cancel.onclick         = () => dismiss(false);
        ok.onclick             = () => { if (key && cb.checked) localStorage.setItem('suppress_' + key, '1'); dismiss(true); };
        overlay.onclick        = (e) => { if (e.target === overlay) dismiss(false); };
        overlay.onkeydown      = (e) => { if (e.key === 'Escape') dismiss(false); };
    });
}

function resetConfirmations() {
    ['download_strip_delete','strip_keep','strip_trash','delete_message','delete_thread'].forEach(k => localStorage.removeItem('suppress_' + k));
    showToast('Confirmation dialogs reset');
}

// ── Progress indicator ────────────────────────────────────────────────────────

function startProgress(label) {
    document.querySelectorAll('.actions-bar button').forEach(b => b.disabled = true);
    let el = document.getElementById('action-progress');
    if (!el) {
        el = document.createElement('span');
        el.id = 'action-progress';
        el.className = 'action-progress';
        document.querySelector('.actions-bar').appendChild(el);
    }
    el.textContent = label;
}

function updateProgress(label) {
    const el = document.getElementById('action-progress');
    if (el) el.textContent = label;
}

function clearProgress() {
    document.querySelectorAll('.actions-bar button').forEach(b => b.disabled = false);
    document.getElementById('action-progress')?.remove();
}

// ── Core fetch ────────────────────────────────────────────────────────────────

async function doAction(data) {
    const res = await fetch('/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    return res.json();
}

// ── Download ──────────────────────────────────────────────────────────────────

async function downloadSingle(idx) {
    const att = CARD.attachments[idx];
    startProgress(`Downloading ${att.filename}…`);
    const result = await doAction({
        action: 'download', msg_id: CARD.msg_id, sender: CARD.sender, date: CARD.date, subject: CARD.subject,
        attachments: [{ id: att.id, filename: att.filename }], advance: false,
    });
    clearProgress();
    if (result.ok) showToast((result.dry_run ? '[Dry run] Would save to: ' : 'Saved to: ') + result.paths[0]);
    else           showToast('Error: ' + result.error, 'error');
}

async function downloadAll() {
    startProgress('Downloading…');
    const result = await doAction({
        action: 'download', msg_id: CARD.msg_id, sender: CARD.sender, date: CARD.date, subject: CARD.subject,
        attachments: CARD.attachments.map(a => ({ id: a.id, filename: a.filename, mime_type: a.mime_type })), advance: false,
    });
    clearProgress();
    if (result.ok) showToast((result.dry_run ? '[Dry run] Would save to:\n' : 'Saved to:\n') + result.paths.join('\n'));
    else           showToast('Error: ' + result.error, 'error');
}

async function downloadAllNext() {
    startProgress('Downloading…');
    const result = await doAction({
        action: 'download', msg_id: CARD.msg_id, sender: CARD.sender, date: CARD.date, subject: CARD.subject,
        attachments: CARD.attachments.map(a => ({ id: a.id, filename: a.filename, mime_type: a.mime_type })), advance: true,
    });
    if (result.ok) { showToast((result.dry_run ? '[Dry run] Would save to:\n' : 'Saved to:\n') + result.paths.join('\n')); setTimeout(() => location.reload(), 2200); }
    else           { clearProgress(); showToast('Error: ' + result.error, 'error'); }
}

// ── Complete action (no confirmation) ─────────────────────────────────────────

async function downloadStripDelete() {
    const count = CARD.attachments.length;
    if (!await modal('download_strip_delete', `Download ${count} attachment${count === 1 ? '' : 's'}, strip from email, and move original to trash?`)) return;
    startProgress('Step 1/2 — Downloading…');
    const dlResult = await doAction({
        action: 'download', msg_id: CARD.msg_id, sender: CARD.sender, date: CARD.date, subject: CARD.subject,
        attachments: CARD.attachments.map(a => ({ id: a.id, filename: a.filename, mime_type: a.mime_type })), advance: false,
    });
    if (!dlResult.ok) { clearProgress(); showToast('Download failed: ' + dlResult.error, 'error'); return; }
    showToast((dlResult.dry_run ? '[Dry run] Would save to:\n' : 'Saved to:\n') + dlResult.paths.join('\n'));

    updateProgress('Step 2/2 — Stripping & trashing…');
    const stripResult = await doAction({ action: 'detach', msg_id: CARD.msg_id, keep_original: false });
    if (!stripResult.ok) { clearProgress(); showToast('Strip failed: ' + stripResult.error, 'error'); return; }

    updateProgress('Done — moving on…');
    setTimeout(() => location.reload(), 1500);
}

// ── Strip ─────────────────────────────────────────────────────────────────────

async function confirmDetach(keepOriginal) {
    const count = CARD.attachments.length;
    const consequence = keepOriginal
        ? 'A stripped copy will be added to your inbox alongside the original.'
        : 'A stripped copy will replace the original (original moved to trash).\n\nDownload first if you want to keep the files.';
    const key = keepOriginal ? 'strip_keep' : 'strip_trash';
    if (!await modal(key, `Strip ${count} attachment${count === 1 ? '' : 's'} from this email?\n\n${consequence}`)) return;

    startProgress(keepOriginal ? 'Stripping attachments…' : 'Stripping & trashing original…');
    const result = await doAction({ action: 'detach', msg_id: CARD.msg_id, keep_original: keepOriginal });
    if (result.ok) {
        const label = result.removed === 0 ? 'No attachments found' : `Stripped ${result.removed} attachment${result.removed === 1 ? '' : 's'}`;
        showToast((result.dry_run ? '[Dry run] ' : '') + label);
        setTimeout(() => location.reload(), 1500);
    } else { clearProgress(); showToast('Error: ' + result.error, 'error'); }
}

// ── Delete ────────────────────────────────────────────────────────────────────

async function confirmDelete(type) {
    const isThread = type === 'thread';
    const key = isThread ? 'delete_thread' : 'delete_message';
    const message = isThread
        ? `Move the entire thread (${CARD.thread_count} message${CARD.thread_count === 1 ? '' : 's'}) to trash?\n\nNote: other participants will still have their copies.`
        : 'Move this message to trash?';
    if (!await modal(key, message)) return;

    startProgress(isThread ? 'Trashing thread…' : 'Trashing message…');
    const result = await doAction(isThread
        ? { action: 'delete_thread',  msg_id: CARD.msg_id, thread_id: CARD.thread_id }
        : { action: 'delete_message', msg_id: CARD.msg_id });
    if (result.ok) {
        const label = isThread ? `Thread moved to trash (${result.count} message${result.count === 1 ? '' : 's'})` : 'Message moved to trash';
        showToast((result.dry_run ? '[Dry run] ' : '') + label);
        setTimeout(() => location.reload(), 1500);
    } else { clearProgress(); showToast('Error: ' + result.error, 'error'); }
}

// ── Skip ──────────────────────────────────────────────────────────────────────

async function doSkip() {
    startProgress('Skipping…');
    const result = await doAction({ action: 'skip', msg_id: CARD.msg_id });
    if (result.ok) location.reload();
    else { clearProgress(); showToast('Error: ' + result.error, 'error'); }
}

// ── Settings ──────────────────────────────────────────────────────────────────

async function browseFolder() {
    try {
        const res = await fetch('/browse-folder');
        const data = await res.json();
        if (data.path)        document.getElementById('download_path').value = data.path;
        else if (data.error)  showToast('Could not open folder browser: ' + data.error, 'error');
    } catch { showToast('Could not open folder browser', 'error'); }
}
