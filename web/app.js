(() => {
    'use strict';

    const $ = (id) => document.getElementById(id);

    // ---------- Tien ich ----------

    const FORM_KEY = 'novel-translator.form.v1';

    function storageGet(key) {
        try { return window.localStorage.getItem(key); } catch (e) { return null; }
    }

    function storageSet(key, value) {
        try { window.localStorage.setItem(key, value); } catch (e) { /* bo qua */ }
    }

    let noticeTimer = null;
    function notify(message, kind, ms) {
        const box = $('notice');
        box.textContent = message;
        box.className = 'notice' + (kind ? ' ' + kind : '');
        box.hidden = false;
        if (noticeTimer) clearTimeout(noticeTimer);
        noticeTimer = setTimeout(() => { box.hidden = true; }, ms || 5000);
    }

    async function copyText(text) {
        if (navigator.clipboard && window.isSecureContext) {
            try {
                await navigator.clipboard.writeText(text);
                return true;
            } catch (e) { /* thu cach du phong */ }
        }
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        let ok = false;
        try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        document.body.removeChild(ta);
        return ok;
    }

    async function copyWithFeedback(btn, text) {
        const ok = await copyText(text);
        const original = btn.dataset.label || btn.textContent;
        btn.dataset.label = original;
        btn.textContent = ok ? 'Đã copy' : 'Không copy được';
        setTimeout(() => { btn.textContent = original; }, 1500);
    }

    async function postForm(path, fields) {
        const params = new URLSearchParams();
        Object.keys(fields || {}).forEach((k) => params.append(k, fields[k]));
        return fetch(path, { method: 'POST', body: params });
    }

    // ---------- API Key ----------

    const apiKeyInput = $('api_key_input');
    const btnSaveKey = $('btn-save-key');
    const btnTestKey = $('btn-test-key');
    const keyStatus = $('key-status');
    const keyWarning = $('key-warning');
    const btnCopyKeyError = $('btn-copy-key-error');
    let lastKeyError = '';
    let hasKey = false;

    function setKeyStatus(kind, message) {
        keyStatus.textContent = message;
        keyStatus.className = 'key-status' + (kind ? ' ' + kind : '');
        lastKeyError = kind === 'bad' ? message : '';
        btnCopyKeyError.hidden = kind !== 'bad';
    }

    $('btn-toggle-key').onclick = (e) => {
        const show = apiKeyInput.type === 'password';
        apiKeyInput.type = show ? 'text' : 'password';
        e.currentTarget.textContent = show ? 'Ẩn' : 'Hiện';
        e.currentTarget.setAttribute('aria-pressed', String(show));
    };

    btnCopyKeyError.onclick = () => copyWithFeedback(btnCopyKeyError, lastKeyError);

    btnTestKey.onclick = async () => {
        const key = apiKeyInput.value.trim();
        if (!key) {
            notify('Vui lòng nhập API Key trước khi test.', 'warn');
            apiKeyInput.focus();
            return;
        }
        btnTestKey.disabled = true;
        btnTestKey.textContent = 'Đang test...';
        setKeyStatus('', 'Đang kết nối tới DeepSeek API để kiểm tra...');
        try {
            const r = await postForm('/test_key', { key: key });
            const data = await r.json();
            setKeyStatus(data.success ? 'ok' : 'bad', data.message);
            if (data.success) {
                await refreshKeyBalance(key);
            }
        } catch (err) {
            setKeyStatus('bad', 'Lỗi kết nối khi kiểm tra Key: ' + err.message);
        } finally {
            btnTestKey.disabled = false;
            btnTestKey.textContent = 'Kiểm tra key';
        }
    };

    btnSaveKey.onclick = async () => {
        const key = apiKeyInput.value.trim();
        if (!key) {
            notify('Vui lòng nhập API Key.', 'warn');
            apiKeyInput.focus();
            return;
        }
        btnSaveKey.disabled = true;
        btnSaveKey.textContent = 'Đang lưu...';
        try {
            const r = await postForm('/save_key', { key: key });
            if (r.ok) {
                hasKey = true;
                setKeyStatus('ok', 'Đã lưu API Key thành công.');
                keyWarning.hidden = true;
                await refreshKeyBalance(key);
            } else {
                setKeyStatus('bad', 'Không thể lưu API Key.');
            }
        } catch (err) {
            setKeyStatus('bad', 'Lỗi kết nối khi lưu: ' + err.message);
        } finally {
            btnSaveKey.disabled = false;
            btnSaveKey.textContent = 'Lưu Key';
        }
    };

    async function checkKey() {
        try {
            const r = await fetch('/get_key');
            const data = await r.json();
            if (data.key) {
                hasKey = true;
                apiKeyInput.value = data.key;
                setKeyStatus('ok', 'Đã nạp API Key từ hệ thống.');
                keyWarning.hidden = true;
                await refreshKeyBalance(data.key);
            } else {
                hasKey = false;
                setKeyStatus('bad', 'Chưa cấu hình API Key (chưa có trong .env).');
                keyWarning.hidden = false;
                renderKeyBalance({ available: false, reason: 'Chưa có API Key.' });
            }
        } catch (err) {
            setKeyStatus('bad', 'Không kiểm tra được API Key: ' + err.message);
            renderKeyBalance({ available: false, reason: 'Không kiểm tra được API Key: ' + err.message });
        }
    }

    apiKeyInput.addEventListener('change', () => {
        const key = apiKeyInput.value.trim();
        if (key) {
            refreshKeyBalance(key);
        } else {
            refreshKeyBalance('');
        }
    });

    apiKeyInput.addEventListener('input', () => {
        if (balanceRequest) balanceRequest.abort();
        balanceRequest = null;
        balanceSequence += 1;
        renderKeyBalance({ available: false, reason: apiKeyInput.value.trim()
            ? 'Key đã thay đổi; xác nhận key để cập nhật số dư.' : 'Chưa có API Key.' });
    });

    // ---------- Chon file tho ----------

    const rawFileInput = $('raw_file_input');
    $('btn-upload-raw').onclick = () => rawFileInput.click();
    const rawFileStatus = $('raw_file_status');
    const inputSource = $('input_source');

    function setFileStatus(kind, text) {
        rawFileStatus.hidden = false;
        rawFileStatus.className = 'file-status' + (kind ? ' ' + kind : '');
        rawFileStatus.textContent = text;
    }

    rawFileInput.onchange = async () => {
        const files = Array.from(rawFileInput.files || []);
        if (!files.length) return;
        setFileStatus('', '\u0110ang x\u1eed l\u00fd file...');
        try {
            const htmlFiles = files.filter(file => /\.(?:html?|mht|mhtml)$/i.test(file.name));
            htmlFiles.sort((a, b) => a.name.localeCompare(
                b.name, undefined, { numeric: true, sensitivity: 'base' }));
            let r;
            if (htmlFiles.length) {
                if (htmlFiles.length !== files.length) {
                    throw new Error('H\u00e3y ch\u1ecdn c\u00e1c file HTML ho\u1eb7c m\u1ed9t file TXT, kh\u00f4ng ch\u1ecdn l\u1eabn.');
                }
                const payload = {
                    files: await Promise.all(htmlFiles.map(async file => ({
                        name: file.name,
                        html: await file.text()
                    })))
                };
                r = await fetch('/import_html', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
            } else {
                if (files.length !== 1) throw new Error('M\u1ed7i l\u1ea7n ch\u1ec9 ch\u1ecdn m\u1ed9t file TXT.');
                const file = files[0];
                r = await fetch('/upload_raw?name=' + encodeURIComponent(file.name), {
                    method: 'POST', body: await file.text()
                });
            }
            const data = await r.json();
            if (r.ok && data.success) {
                inputSource.value = data.path;
                const detail = data.chapters ? `\u0110\u00e3 nh\u1eadp ${data.chapters} ch\u01b0\u01a1ng t\u1eeb HTML. ` : '';
                setFileStatus('ok', detail + 'File d\u1eef li\u1ec7u: ' + data.path);
                scheduleEstimate();
                scheduleBookMetadata();
            } else {
                setFileStatus('bad', data.message || 'L\u1ed7i t\u1ea3i file.');
            }
        } catch (err) {
            setFileStatus('bad', 'L\u1ed7i nh\u1eadp file: ' + err.message);
        }
    };

    // ---------- Nho cau hinh lan chay truoc ----------

    const form = $('f');
    const costEstimate = $('cost-estimate');
    const estimateCrawled = $('estimate-crawled');
    const estimateChapters = $('estimate-chapters');
    const estimateChars = $('estimate-chars');
    const estimateTotal = $('estimate-total');
    const estimateBalanceRow = $('estimate-balance-row');
    const estimateBalance = $('estimate-balance');
    const estimateBalanceDetail = $('estimate-balance-detail');
    const estimateRemaining = $('estimate-remaining');
    const estimateWarnings = $('estimate-warnings');
    let estimateTimer = null;
    let estimateRequest = null;
    let estimateSequence = 0;
    let lastKeyBalance = null;
    let balanceRequest = null;
    let balanceRequestedKey = '';
    let balanceSequence = 0;

    function formatUsd(value) {
        const amount = Number(value || 0);
        return amount > 0 && amount < 0.01 ? '< $0.01' : '$' + amount.toFixed(2);
    }

    function hideEstimate() {
        costEstimate.hidden = true;
        costEstimate.setAttribute('aria-busy', 'false');
    }

    function formatBalance(value, currency) {
        const number = Number(value);
        return Number.isFinite(number) ? number.toFixed(2) + ' ' + currency : String(value || '-') + ' ' + currency;
    }

    function updateBalanceUi(data) {
        const button = typeof $ === 'function' ? $('btn-refresh-balance') : null;
        const updated = typeof $ === 'function' ? $('balance-updated') : null;
        if (button) button.disabled = Boolean(balanceRequest) || !apiKeyInput.value.trim();
        if (updated) updated.textContent = data && data.available && data.received_at
            ? 'Cập nhật lúc ' + new Date(data.received_at).toLocaleTimeString('vi-VN') + ' · Tự cập nhật mỗi 30 giây.'
            : 'Tự cập nhật mỗi 30 giây khi trang đang mở.';
    }

    function renderKeyBalance(data) {
        lastKeyBalance = data || null;
        updateBalanceUi(data);
        if (!data) {
            estimateBalanceRow.hidden = true;
            return;
        }
        estimateBalanceRow.hidden = false;
        if (!data.available) {
            estimateBalance.textContent = 'Chưa lấy được';
            estimateBalanceDetail.textContent = data.reason || 'Chưa kiểm tra số dư.';
            return;
        }
        const infos = Array.isArray(data.balance_infos) ? data.balance_infos : [];
        if (!infos.length) {
            estimateBalance.textContent = data.is_available ? 'Không có dữ liệu' : 'Hết số dư';
            estimateBalanceDetail.textContent = data.is_available ? '' : 'Tài khoản hiện không đủ số dư để gọi API.';
            return;
        }
        estimateBalance.textContent = infos.map((info) => formatBalance(info.total_balance, info.currency || '')).join(' / ');
        estimateBalanceDetail.textContent = infos.map((info) =>
            'Tặng ' + formatBalance(info.granted_balance, info.currency || '') +
            ', còn từ tiền nạp ' + formatBalance(info.topped_up_balance, info.currency || '')
        ).join(' | ');
    }

    function renderEstimate(data) {
        if (!data || !data.available) {
            hideEstimate();
            return;
        }
        costEstimate.hidden = false;
        costEstimate.setAttribute('aria-busy', 'false');
        estimateCrawled.textContent = String(data.crawled_chapters ?? data.chapters ?? 0);
        estimateChapters.textContent = String(data.chapters);
        estimateChars.textContent = Number(data.total_chars || 0).toLocaleString('en-US');
        const total = data.cost_total || {};
        estimateTotal.textContent = formatUsd(total.average) +
            ' (' + formatUsd(total.low) + ' - ' + formatUsd(total.high) + ')';

        const translated = Number(data.translated_chapters || 0);
        if (translated > 0) {
            const remaining = data.cost_remaining || {};
            estimateRemaining.hidden = false;
            estimateRemaining.textContent = 'Còn lại ' + data.remaining_chapters + ' chương, ' +
                Number(data.remaining_chars || 0).toLocaleString('en-US') +
                ' ký tự: khoảng ' + formatUsd(remaining.average) +
                ' (' + formatUsd(remaining.low) + ' - ' + formatUsd(remaining.high) + ').';
        } else {
            estimateRemaining.hidden = true;
            estimateRemaining.textContent = '';
        }

        estimateWarnings.textContent = '';
        (data.warnings || []).forEach((warning) => {
            const item = document.createElement('li');
            item.textContent = warning;
            estimateWarnings.appendChild(item);
        });
        renderKeyBalance(lastKeyBalance);
    }

    async function refreshKeyBalance(key) {
        const requestedKey = String(key ?? apiKeyInput.value).trim();
        if (balanceRequest && balanceRequestedKey === requestedKey) return;
        if (balanceRequest) balanceRequest.abort();
        const sequence = ++balanceSequence;
        balanceRequest = null;
        if (!requestedKey) {
            renderKeyBalance({ available: false, reason: 'Chưa có API Key.' });
            return;
        }
        balanceRequestedKey = requestedKey;
        balanceRequest = new AbortController();
        renderKeyBalance({ available: false, reason: 'Đang cập nhật số dư...' });
        try {
            const r = await fetch('/key_balance', {
                method: 'POST',
                body: new URLSearchParams({ key: requestedKey }),
                signal: balanceRequest.signal
            });
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const data = await r.json();
            if (sequence === balanceSequence && apiKeyInput.value.trim() === requestedKey) {
                renderKeyBalance({ ...data, received_at: Date.now() });
            }
        } catch (error) {
            if (error.name !== 'AbortError' && sequence === balanceSequence &&
                apiKeyInput.value.trim() === requestedKey) {
                renderKeyBalance({ available: false, reason: 'Lỗi kết nối khi lấy số dư: ' + error.message });
            }
        } finally {
            if (sequence === balanceSequence) {
                balanceRequest = null;
                updateBalanceUi(lastKeyBalance);
            }
        }
    }

    function refreshVisibleBalance() {
        if (!document.hidden && apiKeyInput.value.trim()) refreshKeyBalance();
    }

    const balanceRefreshButton = typeof $ === 'function' ? $('btn-refresh-balance') : null;
    if (balanceRefreshButton) balanceRefreshButton.onclick = () => refreshKeyBalance();

    setInterval(refreshVisibleBalance, 30000);
    document.addEventListener('visibilitychange', refreshVisibleBalance);
    window.addEventListener('focus', refreshVisibleBalance);

    async function refreshEstimate() {
        const input = inputSource.value.trim();
        if (!input) {
            hideEstimate();
            return;
        }
        if (estimateRequest) estimateRequest.abort();
        estimateRequest = new AbortController();
        const sequence = ++estimateSequence;
        costEstimate.setAttribute('aria-busy', 'true');
        const params = new URLSearchParams({
            input: input,
            title: form.elements.title.value,
            output_dir: form.elements.output_dir ? form.elements.output_dir.value.trim() : '',
            model: form.elements.model.value,
            reasoning_effort: form.elements.reasoning_effort.value,
            no_thinking: form.elements.no_thinking.checked ? '1' : '0',
            allow_peak: form.elements.allow_peak.checked ? '1' : '0'
        });
        try {
            const response = await fetch('/estimate?' + params.toString(), { signal: estimateRequest.signal });
            const data = await response.json();
            if (sequence === estimateSequence) renderEstimate(data);
        } catch (error) {
            if (error.name !== 'AbortError' && sequence === estimateSequence) hideEstimate();
        }
    }

    function scheduleEstimate() {
        if (estimateTimer) clearTimeout(estimateTimer);
        estimateTimer = setTimeout(refreshEstimate, 250);
    }

    inputSource.addEventListener('input', scheduleEstimate);
    const bookMetadataStatus = $('book-metadata-status');
    let bookMetadataTimer = null;
    let bookMetadataRequest = null;
    let bookMetadataSequence = 0;
    let bookMetadataInput = '';
    let autoBookFields = {};

    function renderBookProfile(data) {
        const panel = $('book-profile');
        if (!panel) return;
        panel.hidden = !data.available;
        function date(value, fallback, withTime = true) {
            if (!value) return fallback;
            const parsed = new Date(value);
            if (Number.isNaN(parsed.getTime())) return fallback;
            const day = parsed.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
            return withTime ? day + ' · ' + parsed.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }) : day;
        }
        let source = data.source_url || '';
        try { source = new URL(source).hostname; } catch (_) { /* local file */ }
        const fields = {
            'book-original-title': data.original_title || 'Chưa có',
            'book-original-author': data.original_author || 'Chưa có',
            'book-source': source || 'File trên máy',
            'book-publication-date': date(data.publication_date, 'Nguồn chưa cung cấp', false),
            'book-export-created': date(data.export_created_at, 'Chưa tạo bản xuất'),
            'book-export-updated': date(data.export_updated_at, 'Chưa tạo bản xuất'),
            'book-exported-chapters': data.exported_chapters !== '' && data.exported_chapters != null
                ? Number(data.exported_chapters).toLocaleString('vi-VN') + ' chương' : 'Chưa tạo bản xuất',
            'book-model': data.translation_model || 'Chưa có dữ liệu',
            'book-identifier': data.book_id || 'Được tạo khi bắt đầu chạy'
        };
        Object.entries(fields).forEach(([id, value]) => { const node = $(id); if (node) node.textContent = value; });
    }

    async function refreshBookMetadata() {
        const input = inputSource.value.trim();
        if (bookMetadataRequest) bookMetadataRequest.abort();
        const sequence = ++bookMetadataSequence;
        if (input !== bookMetadataInput) {
            ['title', 'author'].forEach((name) => {
                if (autoBookFields[name] && form.elements[name].value === autoBookFields[name]) {
                    form.elements[name].value = '';
                }
            });
            autoBookFields = {};
            bookMetadataInput = input;
        }
        if (!input) {
            bookMetadataStatus.textContent = '';
            renderBookProfile({ available: false });
            saveForm();
            return;
        }
        bookMetadataRequest = new AbortController();
        const before = { title: form.elements.title.value, author: form.elements.author.value };
        bookMetadataStatus.textContent = 'Đang lấy thông tin truyện...';
        const query = new URLSearchParams({ input, title: before.title,
            output_dir: form.elements.output_dir.value.trim() });
        try {
            const response = await fetch('/book_metadata?' + query, { signal: bookMetadataRequest.signal });
            if (!response.ok) throw new Error('HTTP ' + response.status);
            const data = await response.json();
            if (sequence !== bookMetadataSequence || inputSource.value.trim() !== input) return;
            renderBookProfile(data);
            ['title', 'author'].forEach((name) => {
                const field = form.elements[name];
                if (!before[name] && !field.value && data[name]) {
                    field.value = data[name];
                    autoBookFields[name] = data[name];
                }
            });
            bookMetadataStatus.textContent = data.available
                ? [data.original_title ? 'Tên gốc: ' + data.original_title : '',
                    data.original_author ? 'Tác giả gốc: ' + data.original_author : '',
                    'Anh có thể sửa tên truyện và tác giả trước khi chạy.'].filter(Boolean).join(' | ')
                : (data.reason || 'Chưa có thông tin sách; có thể nhập thủ công.');
            saveForm();
            scheduleEstimate();
        } catch (error) {
            if (error.name !== 'AbortError' && sequence === bookMetadataSequence) {
                bookMetadataStatus.textContent = 'Không lấy được thông tin sách; có thể nhập thủ công.';
                renderBookProfile({ available: false });
            }
        }
    }

    function scheduleBookMetadata() {
        if (bookMetadataTimer) clearTimeout(bookMetadataTimer);
        // Invalidate an in-flight response immediately when the source changes.
        bookMetadataSequence += 1;
        if (bookMetadataRequest) bookMetadataRequest.abort();
        renderBookProfile({ available: false });
        bookMetadataTimer = setTimeout(refreshBookMetadata, 600);
    }

    inputSource.addEventListener('input', scheduleBookMetadata);
    form.elements.output_dir.addEventListener('change', scheduleBookMetadata);
    ['title', 'author'].forEach((name) => {
        form.elements[name].addEventListener('input', () => {
            delete autoBookFields[name];
            saveForm();
        });
    });
    ['title', 'output_dir', 'model', 'reasoning_effort', 'no_thinking', 'allow_peak'].forEach((name) => {
        const field = form.elements[name];
        if (!field) return;
        field.addEventListener('change', scheduleEstimate);
        if (field.tagName === 'INPUT' && field.type !== 'checkbox') field.addEventListener('input', scheduleEstimate);
    });

    const TEXT_FIELDS = ['input', 'title', 'output_dir', 'author', 'model', 'reasoning_effort', 'workers', 'temperature', 'chapters'];
    const CHECK_FIELDS = ['stream_mode', 'allow_peak', 'no_style_detect', 'no_thinking'];

    function saveForm() {
        const data = {};
        data.metadataAuto = autoBookFields;
        TEXT_FIELDS.forEach((n) => { data[n] = form.elements[n].value; });
        CHECK_FIELDS.forEach((n) => { data[n] = form.elements[n].checked; });
        storageSet(FORM_KEY, JSON.stringify(data));
    }

    function loadForm() {
        const raw = storageGet(FORM_KEY);
        if (!raw) return;
        let data;
        try { data = JSON.parse(raw); } catch (e) { return; }
        if (!data || typeof data !== 'object') return;
        autoBookFields = data.metadataAuto && typeof data.metadataAuto === 'object' ? data.metadataAuto : {};
        bookMetadataInput = typeof data.input === 'string' ? data.input.trim() : '';
        TEXT_FIELDS.forEach((n) => {
            const field = form.elements[n];
            if (typeof data[n] !== 'string' || data[n] === '') return;
            if (field.tagName === 'SELECT') {
                const exists = Array.prototype.some.call(field.options, (o) => o.value === data[n]);
                if (!exists) return;
            }
            field.value = data[n];
        });
        CHECK_FIELDS.forEach((n) => {
            if (typeof data[n] === 'boolean') form.elements[n].checked = data[n];
        });
        syncStreamRow();
        scheduleEstimate();
    }

    const streamModeCheck = $('stream_mode');
    const streamChaptersRow = $('stream-chapters-row');

    function syncStreamRow() {
        streamChaptersRow.hidden = !streamModeCheck.checked;
    }

    streamModeCheck.onchange = syncStreamRow;

    function syncThinkingControls() {
        const enabled = form.elements.no_thinking.checked;
        form.elements.temperature.disabled = !enabled;
        form.elements.reasoning_effort.disabled = enabled;
        $('temperature-hint').textContent = enabled
            ? 'Áp dụng cho chế độ không suy luận.' : 'Không áp dụng khi đang bật suy luận.';
    }
    form.elements.no_thinking.addEventListener('change', syncThinkingControls);

    // ---------- Chay / dung ----------

    const btnStart = $('btn-start');
    const btnCrawlOnly = $('btn-crawl-only');
    const btnStop = $('btn-stop');
    const logEl = $('log');
    const resultEl = $('result');
    const progressArea = $('progress-area');
    const progressBar = $('progress-bar');
    const progressText = $('progress-text');
    const progressPercent = $('progress-percent');
    const fileInfo = $('file-info');
    const costSpent = $('cost-spent');
    const errorReport = $('error-report');
    const errorDetailText = $('error-detail-text');
    const btnCopyError = $('btn-copy-error');
    const btnScroll = $('btn-scroll');
    const btnCopy = $('btn-copy');

    let lastStatus = {};
    let autoScroll = true;
    let pollTimeout = null;
    let wasRunning = false;

    function setResult(kind, text) {
        if (!kind) {
            resultEl.hidden = true;
            resultEl.className = 'result-box';
            resultEl.textContent = '';
            return;
        }
        resultEl.hidden = false;
        resultEl.className = 'result-box ' + kind;
        resultEl.textContent = text;
    }

    btnCopyError.onclick = () => {
        const report = [
            'Bước lỗi: ' + (lastStatus.step || '(không rõ)'),
            'Lỗi: ' + (lastStatus.error || '(không rõ)'),
            'File thô: ' + (lastStatus.raw_file || '(không có)'),
            '',
            'Chi tiết (log/traceback):',
            lastStatus.error_detail || '(không có)'
        ].join('\n');
        copyWithFeedback(btnCopyError, report);
    };

    btnScroll.onclick = () => {
        autoScroll = !autoScroll;
        btnScroll.textContent = 'Tự cuộn: ' + (autoScroll ? 'BẬT' : 'TẮT');
        btnScroll.classList.toggle('active', autoScroll);
        btnScroll.setAttribute('aria-pressed', String(autoScroll));
    };

    btnCopy.onclick = () => copyWithFeedback(btnCopy, logEl.textContent);

    form.onsubmit = async (e) => {
        e.preventDefault();
        const crawlOnly = e.submitter && e.submitter.dataset.mode === 'crawl_only';
        if (!crawlOnly && !hasKey) {
            notify('Chưa có API Key. Hãy nhập và bấm Lưu Key trước khi dịch.', 'warn', 6000);
            apiKeyInput.focus();
            return;
        }
        saveForm();
        setResult(null);
        const params = new URLSearchParams();
        new FormData(form).forEach((value, key) => params.append(key, value));
        if (crawlOnly) params.set('mode', 'crawl_only');
        // Chi dung 1 lan: de lai thi lan chay sau cao trung tu chuong nay.
        form.elements.from_chapter.value = '';
        try {
            const r = await fetch('/', { method: 'POST', body: params });
            if (!r.ok) throw new Error('Máy chủ trả về mã ' + r.status);
        } catch (err) {
            notify('Không gửi được yêu cầu: ' + err.message, 'error', 7000);
            return;
        }
        if (pollTimeout) clearTimeout(pollTimeout);
        poll();
    };

    // Tham so nguon dung chung cho cac thao tac tren truyen (sua chuong, nap chuong, tai file).
    function sourceParams() {
        return new URLSearchParams({
            input: form.elements.input.value.trim(),
            title: form.elements.title.value.trim(),
            author: form.elements.author.value.trim(),
            output_dir: form.elements.output_dir.value.trim(),
        });
    }

    function requireSource(actionLabel) {
        if (form.elements.input.value.trim()) return true;
        notify('Nhập nguồn truyện trước khi ' + actionLabel + '.', 'warn', 5000);
        form.elements.input.focus();
        return false;
    }

    $('btn-heal').onclick = async () => {
        if (!requireSource('sửa chương')) return;
        try {
            const r = await fetch('/heal', { method: 'POST', body: sourceParams() });
            const d = await r.json();
            if (!d.ok) throw new Error(d.message || ('mã ' + r.status));
            notify(d.fixed ? 'Đã sửa chương. Xem nhật ký.' : 'Không có chương trùng hay lệch.', 'info', 5000);
        } catch (err) {
            notify('Tự sửa chương lỗi: ' + err.message, 'error', 7000);
        }
        if (pollTimeout) clearTimeout(pollTimeout);
        poll();
    };

    // Nap file chuong sua: moi file gui rieng, server thay chuong cung so trong file tho.
    const fixFileInput = $('fix_file_input');
    $('btn-fix-upload').onclick = () => {
        if (requireSource('nạp file chương sửa')) fixFileInput.click();
    };

    fixFileInput.onchange = async () => {
        const files = Array.from(fixFileInput.files || []);
        fixFileInput.value = '';
        for (const file of files) {
            const params = sourceParams();
            params.set('name', file.name);
            try {
                const r = await fetch('/replace_chapters?' + params.toString(), { method: 'POST', body: file });
                const d = await r.json();
                if (!d.ok) throw new Error(d.message || ('mã ' + r.status));
                notify(file.name + ': thay ' + d.replaced + ' chương, thêm ' + d.appended + ' chương mới.' +
                    (d.healed ? ' Đã sắp lại.' : ''), 'info', 6000);
            } catch (err) {
                notify('Nạp ' + file.name + ' lỗi: ' + err.message, 'error', 7000);
                break;
            }
        }
        if (pollTimeout) clearTimeout(pollTimeout);
        poll();
    };

    btnStop.onclick = async () => {
        btnStop.disabled = true;
        try {
            await fetch('/stop', { method: 'POST' });
        } catch (err) {
            notify('Không gửi được lệnh dừng: ' + err.message, 'error');
            btnStop.disabled = false;
        }
    };

    // ---------- Cac buoc ----------

    const STEP_IDS = ['step-crawl', 'step-translate', 'step-validate', 'step-done'];

    function setStepLabels(isStream) {
        $('step-crawl').querySelector('.step-label').textContent = isStream ? 'Cào + Dịch' : 'Cào truyện';
        $('step-translate').querySelector('.step-label').textContent = isStream ? 'Từng chương' : 'Dịch thuật';
    }

    function updateSteps(currentStep, isStream, crawlOnly) {
        setStepLabels(isStream);
        $('step-done').querySelector('.step-label').textContent = currentStep === 'done' ? 'Hoàn tất' : 'Đóng gói';
        if (crawlOnly) {
            $('step-crawl').querySelector('.step-label').textContent = 'C\u00e0o ch\u01b0\u01a1ng';
            $('step-translate').querySelector('.step-label').textContent = 'B\u1ecf qua d\u1ecbch';
        }
        STEP_IDS.forEach((id) => { $(id).className = 'step'; });
        if (currentStep === 'idle') return;
        if (crawlOnly && currentStep === 'done') {
            $('step-crawl').className = 'step completed';
            return;
        }

        const stateToIdx = isStream
            ? { streaming: 0, validating: 2, packaging: 3, done: 3 }
            : { crawling: 0, translating: 1, validating: 2, packaging: 3, done: 3 };
        const activeIdx = stateToIdx[currentStep];
        if (activeIdx === undefined) return;

        STEP_IDS.forEach((id, idx) => {
            if (idx < activeIdx) $(id).className = 'step completed';
            else if (idx === activeIdx) $(id).className = 'step active';
        });
        if (currentStep === 'done') $('step-done').className = 'step completed';
    }

    function showProgress(text, percentLabel, percent) {
        progressArea.hidden = false;
        progressText.textContent = text;
        progressPercent.textContent = percentLabel;
        if (percent === null) {
            progressBar.classList.add('indeterminate');
            progressBar.style.width = '';
        } else {
            progressBar.classList.remove('indeterminate');
            progressBar.style.width = percent + '%';
        }
    }

    function renderProgress(s) {
        if (!s.running) {
            progressArea.hidden = true;
            return;
        }
        const cur = s.current_chapter;
        const total = s.total_chapters;
        const pct = total > 0 ? Math.min(100, Math.round(cur / total * 100)) : null;

        if (s.step === 'crawling') {
            if (total > 0) {
                showProgress('Đang cào chương: ' + cur + '/' + total, pct + '%', pct);
            } else {
                showProgress('Đang cào chương: ' + cur, 'Đang tải...', null);
            }
        } else if (s.step === 'streaming') {
            showProgress('Đã dịch thêm ' + cur + ' chương' + (total > 0 ? '/' + total : ''),
                pct === null ? 'Đang dịch...' : pct + '%', pct);
        } else if (s.step === 'translating') {
            if (total > 0) {
                showProgress('Đang dịch: ' + cur + '/' + total + ' chương', pct + '%', pct);
            } else {
                showProgress('Đang dịch: ' + cur + ' chương', 'Đang dịch...', null);
            }
        } else if (s.step === 'validating') {
            showProgress('Đang kiểm tra chất lượng bản dịch...', '', null);
        } else if (s.step === 'packaging') {
            showProgress('Đang đóng gói file EPUB/PDF...', '', null);
        } else {
            progressArea.hidden = true;
        }
    }

    // Mot cho duy nhat quyet dinh nut nao bi khoa khi pipeline dang chay.
    function setBusy(running) {
        [btnStart, btnCrawlOnly, $('btn-heal'), $('btn-fix-upload'), $('btn-export-epub'), $('btn-export-pdf')]
            .forEach((btn) => { btn.disabled = running; });
        btnStop.hidden = !running;
    }

    function renderResult(s) {
        if (s.crawl_only && s.step === 'done') {
            setResult('success', 'Da cao ' + s.crawled_chapters + ' chuong. File tho luu tai: ' + s.raw_file);
        } else if (s.epub) {
            setResult('success', 'Thành công. File EPUB lưu tại: ' + s.epub);
            if (s.pdf) resultEl.textContent += ' | PDF: ' + s.pdf;
        } else if (s.stop_requested && !s.running) {
            setResult('warn', 'Đã dừng theo yêu cầu. Bấm "Bắt đầu dịch" để chạy tiếp, các chương đã xong được giữ nguyên.');
        } else if (s.error) {
            setResult('error', 'Lỗi: ' + s.error);
        } else {
            setResult(null);
        }
    }

    async function poll() {
        try {
            const r = await fetch('/status');
            const s = await r.json();

            setBusy(s.running);
            if (s.running) btnStop.disabled = !!s.stop_requested;

            logEl.textContent = s.log;
            if (autoScroll) logEl.scrollTop = logEl.scrollHeight;

            lastStatus = s;
            updateSteps(s.step, s.stream_mode, s.crawl_only);
            renderProgress(s);
            costSpent.hidden = !(Number(s.cost_spent) > 0);
            if (!costSpent.hidden) costSpent.textContent = 'Đã tiêu khoảng ' + formatUsd(s.cost_spent);
            fileInfo.textContent = s.raw_file
                ? (s.crawl_only ? 'File tho: ' + s.raw_file : 'File thô: ' + s.raw_file + '  |  File dịch: ' + s.translated_file + (s.epub_path ? '  |  EPUB: ' + s.epub_path : ''))
                : '';
            if (!s.crawl_only && s.raw_file && s.pdf_path) fileInfo.textContent += '  |  PDF: ' + s.pdf_path;
            renderResult(s);

            if (s.error_detail) {
                errorReport.hidden = false;
                errorDetailText.textContent = s.error_detail;
            } else {
                errorReport.hidden = true;
            }

            if (wasRunning && !s.running) {
                refreshVisibleBalance();
                scheduleBookMetadata();
            }
            wasRunning = s.running;

            if (s.running) pollTimeout = setTimeout(poll, 1000);
        } catch (err) {
            console.error('Polling error:', err);
            pollTimeout = setTimeout(poll, 2000);
        }
    }

    // ---------- Tai ban dich (EPUB/PDF dong goi theo yeu cau) ----------

    function exportFileName(r, fallback) {
        const cd = r.headers.get('Content-Disposition') || '';
        const m = cd.match(/filename\*=UTF-8''([^;]+)/i);
        if (m) {
            try { return decodeURIComponent(m[1]); } catch (_) { /* roi xuong ten du phong */ }
        }
        return fallback;
    }

    async function exportPackage(fmt, btn) {
        if (!requireSource('tải file')) return;
        const params = sourceParams();
        params.set('format', fmt);
        const label = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Đang đóng gói...';
        try {
            const r = await fetch('/export?' + params.toString());
            if (!r.ok) {
                let msg = 'mã ' + r.status;
                try { msg = (await r.json()).message || msg; } catch (_) { /* giu ma loi */ }
                throw new Error(msg);
            }
            const blob = await r.blob();
            const name = exportFileName(r, 'truyen.' + fmt);
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = name;
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 10000);
            notify('Đã tải ' + name, 'info', 4000);
        } catch (err) {
            notify('Không tải được ' + fmt.toUpperCase() + ': ' + err.message, 'error', 7000);
        } finally {
            btn.textContent = label;
            btn.disabled = false;
        }
    }

    $('btn-export-epub').onclick = (e) => exportPackage('epub', e.currentTarget);
    $('btn-export-pdf').onclick = (e) => exportPackage('pdf', e.currentTarget);

    // ---------- Thong tin app, mo thu muc, thoat ----------

    const btnQuit = $('btn-quit');
    const btnOpenDir = $('btn-open-dir');
    const btnPickDir = $('btn-pick-dir');
    let quitArmed = false;
    let quitTimer = null;

    async function loadInfo() {
        try {
            const r = await fetch('/info');
            const info = await r.json();
            $('footer-version').textContent = 'Trình dịch truyện DeepSeek ' + info.version;
            const dir = $('footer-dir');
            dir.hidden = false;
            dir.textContent = 'Dữ liệu: ' + info.data_dir;

            $('help-termux').hidden = info.platform !== 'termux';
            $('help-termux-files').hidden = info.platform !== 'termux';
            $('help-desktop').hidden = info.platform === 'termux';
            $('help-data-dir').textContent = info.data_dir;

            btnOpenDir.hidden = !info.can_open_dir;
            btnQuit.hidden = !info.can_quit;

            if (btnPickDir) {
                btnPickDir.hidden = !info.can_pick_dir;
                btnPickDir.onclick = async () => {
                    btnPickDir.disabled = true;
                    try {
                        const r = await fetch('/pick_directory', { method: 'POST' });
                        const res = await r.json();
                        if (res.success && res.path) {
                            const outputInput = $('output_dir_input');
                            if (outputInput) outputInput.value = res.path;
                            saveForm();
                            scheduleEstimate();
                            scheduleBookMetadata();
                        }
                    } catch (err) {
                        notify('Không chọn được thư mục: ' + err.message, 'error');
                    } finally {
                        btnPickDir.disabled = false;
                    }
                };
            }
        } catch (err) {
            console.error('Info error:', err);
        }
    }

    btnOpenDir.onclick = async () => {
        try {
            const r = await fetch('/open_data_dir', { method: 'POST' });
            if (!r.ok) throw new Error('mã ' + r.status);
        } catch (err) {
            notify('Không mở được thư mục: ' + err.message, 'error');
        }
    };

    btnQuit.onclick = async () => {
        if (!quitArmed) {
            quitArmed = true;
            btnQuit.textContent = 'Bấm lại để thoát';
            const running = lastStatus.running;
            notify(running
                ? 'Đang dịch dở. Thoát lúc này sẽ dừng việc đang chạy, lần sau chạy lại sẽ tự tiếp tục.'
                : 'Bấm "Bấm lại để thoát" trong 4 giây để xác nhận.', 'warn', 4000);
            quitTimer = setTimeout(() => {
                quitArmed = false;
                btnQuit.textContent = 'Thoát ứng dụng';
            }, 4000);
            return;
        }
        clearTimeout(quitTimer);
        try {
            await fetch('/shutdown', { method: 'POST' });
        } catch (err) { /* may chu tat nen ket noi co the bi ngat */ }
        if (pollTimeout) clearTimeout(pollTimeout);
        const bye = document.createElement('div');
        bye.className = 'goodbye';
        const byeTitle = document.createElement('h1');
        byeTitle.textContent = 'Ứng dụng đã tắt';
        const byeText = document.createElement('p');
        byeText.textContent = 'Có thể đóng tab này. Mở lại file chạy để dùng tiếp.';
        bye.appendChild(byeTitle);
        bye.appendChild(byeText);
        $('app').replaceChildren(bye);
    };

    // ---------- Dich thu ----------

    const testModal = $('test-modal');
    const btnRunTest = $('btn-run-test');
    const testText = $('test-text');
    const testResult = $('test-result');
    const btnCopyTestError = $('btn-copy-test-error');
    let lastTestError = '';

    function openTestModal() {
        testModal.classList.add('active');
        testResult.hidden = true;
        btnCopyTestError.hidden = true;
        testText.focus();
    }

    function closeTestModal() {
        testModal.classList.remove('active');
        $('btn-test-translate').focus();
    }

    $('btn-test-translate').onclick = openTestModal;
    $('btn-close-modal').onclick = closeTestModal;
    testModal.onclick = (e) => { if (e.target === testModal) closeTestModal(); };
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && testModal.classList.contains('active')) closeTestModal();
    });
    btnCopyTestError.onclick = () => copyWithFeedback(btnCopyTestError, lastTestError);

    function showTestSuccess(text) {
        testResult.textContent = '';
        const head = document.createElement('strong');
        head.textContent = 'Dịch thành công.';
        const quote = document.createElement('em');
        quote.textContent = text.length > 300 ? text.substring(0, 300) + '...' : text;
        const link = document.createElement('a');
        link.href = '/download_test';
        link.setAttribute('download', 'test_dung_thu.epub');
        link.textContent = 'Tải file EPUB';
        testResult.appendChild(head);
        testResult.appendChild(quote);
        testResult.appendChild(link);
        const pdfLink = document.createElement('a');
        pdfLink.href = '/download_test_pdf';
        pdfLink.setAttribute('download', 'test_dung_thu.pdf');
        pdfLink.textContent = 'Tải file PDF';
        testResult.appendChild(pdfLink);
        testResult.className = 'modal-result success';
        testResult.hidden = false;
        btnCopyTestError.hidden = true;
    }

    function showTestError(message, detail) {
        testResult.textContent = message;
        testResult.className = 'modal-result error';
        testResult.hidden = false;
        lastTestError = message + (detail ? '\n\n' + detail : '');
        btnCopyTestError.hidden = false;
    }

    btnRunTest.onclick = async () => {
        const text = testText.value.trim();
        if (!text) {
            showTestError('Vui lòng nhập đoạn văn bản tiếng Trung.');
            return;
        }
        btnRunTest.disabled = true;
        btnRunTest.textContent = 'Đang dịch...';
        testResult.hidden = true;
        try {
            const r = await postForm('/test_translate', { text: text });
            const data = await r.json();
            if (data.success) showTestSuccess(data.translated_text);
            else showTestError(data.message, data.detail);
        } catch (err) {
            showTestError('Lỗi kết nối: ' + err.message);
        } finally {
            btnRunTest.disabled = false;
            btnRunTest.textContent = 'Dịch và tạo EPUB/PDF';
            refreshVisibleBalance();
        }
    };

    // ---------- Khoi dong ----------

    loadForm();
    syncThinkingControls();
    scheduleEstimate();
    scheduleBookMetadata();
    checkKey();
    loadInfo();
    poll();
})();
