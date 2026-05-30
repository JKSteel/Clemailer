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

// ── Batch processing ──────────────────────────────────────────────────────────

let _batchState = null; // 'running' | 'paused' | 'stopped' | null

async function startBatch() {
    const remaining = CARD.total - CARD.idx;
    if (!await modal('batch_run', `Process all ${remaining} remaining email${remaining === 1 ? '' : 's'} from this point?\n\nEach will be downloaded, stripped, and moved to trash. Errors are skipped and left in your queue for manual review.`)) return;

    _batchState = 'running';
    _showBatchOverlay();

    const errors = [];
    let processed = 0;
    const startIdx = CARD.idx;
    const total    = CARD.total;

    for (let i = startIdx; i < total; i++) {
        if (_batchState === 'stopped') break;
        while (_batchState === 'paused') await new Promise(r => setTimeout(r, 300));
        if (_batchState === 'stopped') break;

        _updateBatchOverlay(i - startIdx, total - startIdx, 'Fetching…', '');

        let result;
        try {
            const res = await fetch('/batch/step', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ idx: i }),
            });
            result = await res.json();
        } catch (e) {
            errors.push({ idx: i + 1, subject: `Email ${i + 1}`, error: 'Network error' });
            continue;
        }

        if (result.done) break;
        if (result.skipped) continue;

        if (result.ok) {
            processed++;
            const label = result.dry_run ? '[Dry run] ' : '';
            _updateBatchOverlay(
                i - startIdx + 1, total - startIdx,
                result.subject,
                `${label}Downloaded ${result.paths.length} file${result.paths.length === 1 ? '' : 's'}, stripped & trashed`,
            );
        } else {
            errors.push({ idx: i + 1, subject: result.subject || `Email ${i + 1}`, error: result.error });
            _updateBatchOverlay(i - startIdx + 1, total - startIdx, result.subject || `Email ${i + 1}`, `Error — skipped`);
        }

        await new Promise(r => setTimeout(r, 300));
    }

    _batchState = 'done';
    _showBatchSummary(processed, errors, total - startIdx);
}

function toggleBatchPause() {
    if (_batchState === 'paused') {
        _batchState = 'running';
        document.getElementById('batch-pause-btn').textContent = 'Pause';
        document.getElementById('batch-title').textContent = 'Processing emails…';
    } else if (_batchState === 'running') {
        _batchState = 'paused';
        document.getElementById('batch-pause-btn').textContent = 'Resume';
        document.getElementById('batch-title').textContent = 'Paused';
    }
}

function stopBatch() {
    _batchState = 'stopped';
}

function closeBatch() {
    document.getElementById('batch-overlay')?.remove();
    _batchState = null;
    location.reload();
}

function _showBatchOverlay() {
    const el = document.createElement('div');
    el.id = 'batch-overlay';
    el.className = 'batch-overlay';

    const modal = document.createElement('div');
    modal.className = 'batch-modal';
    modal.innerHTML = `
        <div class="batch-header">
            <span id="batch-title">Processing emails…</span>
            <span id="batch-count" class="batch-count"></span>
        </div>
        <div class="batch-bar-wrap"><div id="batch-bar" class="batch-bar-fill" style="width:0%"></div></div>
        <div id="batch-subject" class="batch-subject">Starting…</div>
        <div id="batch-action"  class="batch-action"></div>
        <div id="batch-errors-section" style="display:none">
            <p id="batch-errors-title" class="batch-errors-title"></p>
            <ul id="batch-errors-list" class="batch-errors-list"></ul>
        </div>
        <div class="batch-controls">
            <button id="batch-pause-btn" class="btn btn-ghost"           onclick="toggleBatchPause()">Pause</button>
            <button id="batch-stop-btn"  class="btn btn-danger btn-outline" onclick="stopBatch()">Stop</button>
            <button id="batch-done-btn"  class="btn btn-primary"         onclick="closeBatch()" style="display:none">Done</button>
        </div>`;

    el.appendChild(modal);
    document.body.appendChild(el);
}

function _updateBatchOverlay(done, total, subject, action) {
    const pct = total > 0 ? Math.round(done / total * 100) : 0;
    const bar  = document.getElementById('batch-bar');
    const cnt  = document.getElementById('batch-count');
    const sub  = document.getElementById('batch-subject');
    const act  = document.getElementById('batch-action');
    if (bar) bar.style.width = pct + '%';
    if (cnt) cnt.textContent = `${done} / ${total}`;
    if (sub) sub.textContent = subject || '';
    if (act) act.textContent = action  || '';
}

function _showBatchSummary(processed, errors, total) {
    const title = document.getElementById('batch-title');
    const sub   = document.getElementById('batch-subject');
    const act   = document.getElementById('batch-action');
    const pause = document.getElementById('batch-pause-btn');
    const stop  = document.getElementById('batch-stop-btn');
    const done  = document.getElementById('batch-done-btn');
    const bar   = document.getElementById('batch-bar');
    const cnt   = document.getElementById('batch-count');

    if (title) title.textContent = _batchState === 'stopped' ? 'Stopped' : 'Done';
    if (bar)   bar.style.width = '100%';
    if (cnt)   cnt.textContent = `${processed} processed`;
    if (sub)   sub.textContent = `${processed} email${processed === 1 ? '' : 's'} successfully processed.`;
    if (act)   act.textContent = '';
    if (pause) pause.style.display = 'none';
    if (stop)  stop.style.display  = 'none';
    if (done)  done.style.display  = '';

    if (errors.length > 0) {
        const section = document.getElementById('batch-errors-section');
        const errTitle = document.getElementById('batch-errors-title');
        const errList  = document.getElementById('batch-errors-list');
        if (section) section.style.display = '';
        if (errTitle) errTitle.textContent = `${errors.length} email${errors.length === 1 ? '' : 's'} failed and remain in your queue:`;
        if (errList) {
            errors.forEach(e => {
                const li = document.createElement('li');
                li.className = 'batch-error-item';
                const subj = document.createElement('span'); subj.className = 'batch-error-subject'; subj.textContent = e.subject;
                const err  = document.createElement('span'); err.className  = 'batch-error-msg';     err.textContent  = e.error;
                li.append(subj, ' — ', err);
                errList.appendChild(li);
            });
        }
    }
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
