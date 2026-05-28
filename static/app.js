function switchPreview(el) {
    document.querySelectorAll('.attachment-item').forEach(e => e.classList.remove('active'));
    el.classList.add('active');

    const area = document.getElementById('preview-area');
    if (!area) return;

    const mime = el.dataset.mime;
    const url  = el.dataset.url;

    if (mime.startsWith('image/')) {
        area.innerHTML = `<img class="preview-img" src="${url}">`;
    } else if (mime === 'application/pdf') {
        area.innerHTML = `<embed class="preview-pdf" src="${url}" type="application/pdf">`;
    } else {
        area.innerHTML = `<span class="preview-empty">No inline preview for this file type</span>`;
    }
}

function showToast(text, type = 'success') {
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = text;
    document.getElementById('toast-container').appendChild(el);
    requestAnimationFrame(() => { requestAnimationFrame(() => el.classList.add('show')); });
    setTimeout(() => {
        el.classList.remove('show');
        setTimeout(() => el.remove(), 250);
    }, 4500);
}

async function doAction(data) {
    const res = await fetch('/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    return res.json();
}

async function downloadAll() {
    const atts = CARD.attachments.map(a => ({ id: a.id, filename: a.filename }));
    const result = await doAction({
        action: 'download',
        msg_id: CARD.msg_id,
        sender: CARD.sender,
        date:   CARD.date,
        attachments: atts,
    });
    if (result.ok) {
        const prefix = result.dry_run ? '[Dry run] Would save to:\n' : 'Saved to:\n';
        showToast(prefix + result.paths.join('\n'));
        setTimeout(() => location.reload(), 2200);
    } else {
        showToast('Error: ' + result.error, 'error');
    }
}

async function downloadAtt(attId, filename) {
    const result = await doAction({
        action: 'download',
        msg_id: CARD.msg_id,
        sender: CARD.sender,
        date:   CARD.date,
        attachments: [{ id: attId, filename }],
    });
    if (result.ok) {
        const prefix = result.dry_run ? '[Dry run] Would save to: ' : 'Saved to: ';
        showToast(prefix + result.paths[0]);
        setTimeout(() => location.reload(), 2200);
    } else {
        showToast('Error: ' + result.error, 'error');
    }
}

async function confirmDelete(type) {
    let msg, data;
    if (type === 'message') {
        msg  = 'Delete this message? This cannot be undone.';
        data = { action: 'delete_message', msg_id: CARD.msg_id };
    } else {
        msg  = `Delete the entire thread (${CARD.thread_count} message${CARD.thread_count === 1 ? '' : 's'})?\n\nThis removes all messages in the conversation and cannot be undone. Other participants will lose the thread too.`;
        data = { action: 'delete_thread', msg_id: CARD.msg_id, thread_id: CARD.thread_id };
    }
    if (!confirm(msg)) return;

    const result = await doAction(data);
    if (result.ok) {
        const prefix = result.dry_run ? '[Dry run] ' : '';
        const label  = type === 'thread'
            ? `Thread deleted (${result.count} message${result.count === 1 ? '' : 's'})`
            : 'Message deleted';
        showToast(prefix + label);
        setTimeout(() => location.reload(), 1500);
    } else {
        showToast('Error: ' + result.error, 'error');
    }
}

async function doSkip() {
    const result = await doAction({ action: 'skip', msg_id: CARD.msg_id });
    if (result.ok) {
        location.reload();
    } else {
        showToast('Error: ' + result.error, 'error');
    }
}
