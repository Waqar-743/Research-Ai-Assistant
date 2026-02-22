/* ═══════════════════════════════════════════
   Multi-Agent Research Assistant — Frontend
   ═══════════════════════════════════════════ */

(() => {
    'use strict';

    // ─── Configuration ───
    const API_BASE = 'http://localhost:8000/api/v1';
    const WS_BASE  = 'ws://localhost:8000/ws';
    const POLL_INTERVAL = 3000;

    // ─── State ───
    let currentSessionId = null;
    let pollTimer = null;
    let ws = null;
    let isResearching = false;

    // ─── DOM Refs ───
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const dom = {
        // Nav
        apiDot:       $('#apiStatusDot'),
        apiText:      $('#apiStatusText'),
        navBtns:      $$('.nav-btn'),
        // Research form
        form:         $('#researchForm'),
        queryInput:   $('#queryInput'),
        btnStart:     $('#btnStart'),
        focusAreas:   $('#focusAreas'),
        sourcePrefs:  $('#sourcePrefs'),
        reportFormat: $('#reportFormat'),
        citationStyle:$('#citationStyle'),
        maxSources:   $('#maxSources'),
        researchMode: $('#researchMode'),
        // Pipeline
        pipelineSection: $('#pipelineSection'),
        overallBarFill:  $('#overallBarFill'),
        overallPercent:  $('#overallPercent'),
        overallPhase:    $('#overallPhase'),
        btnCancel:       $('#btnCancel'),
        logEntries:      $('#logEntries'),
        btnClearLog:     $('#btnClearLog'),
        // Results
        resultsSection: $('#resultsSection'),
        resultsTitle:   $('#resultsTitle'),
        reportContent:  $('#reportContent'),
        findingsList:   $('#findingsList'),
        sourcesList:    $('#sourcesList'),
        metadataContent:$('#metadataContent'),
        btnDownloadMd:  $('#btnDownloadMd'),
        btnDownloadHtml:$('#btnDownloadHtml'),
        btnNewResearch: $('#btnNewResearch'),
        tabs:           $$('.tab'),
        // History
        historyList:    $('#historyList'),
        historySearch:  $('#historySearch'),
        historyFilter:  $('#historyFilter'),
        // Toast
        toastContainer: $('#toastContainer'),
    };

    // ═══════════════════════════════════════
    //  Utility Helpers
    // ═══════════════════════════════════════

    function toast(msg, type = 'info', duration = 4000) {
        const el = document.createElement('div');
        el.className = `toast toast-${type}`;
        el.innerHTML = `
            <span class="toast-icon">${type === 'success' ? '✓' : type === 'error' ? '✕' : type === 'warning' ? '⚠' : 'ℹ'}</span>
            <span class="toast-msg">${escapeHtml(msg)}</span>
        `;
        dom.toastContainer.appendChild(el);
        requestAnimationFrame(() => el.classList.add('show'));
        setTimeout(() => {
            el.classList.remove('show');
            setTimeout(() => el.remove(), 300);
        }, duration);
    }

    function escapeHtml(str) {
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    function timeAgo(dateStr) {
        if (!dateStr) return '—';
        const diff = Date.now() - new Date(dateStr).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'just now';
        if (mins < 60) return `${mins}m ago`;
        const hrs = Math.floor(mins / 60);
        if (hrs < 24) return `${hrs}h ago`;
        const days = Math.floor(hrs / 24);
        return `${days}d ago`;
    }

    function formatDate(dateStr) {
        if (!dateStr) return '—';
        return new Date(dateStr).toLocaleString();
    }

    // ═══════════════════════════════════════
    //  API Layer
    // ═══════════════════════════════════════

    async function apiFetch(path, options = {}) {
        const url = `${API_BASE}${path}`;
        const res = await fetch(url, {
            headers: { 'Content-Type': 'application/json', ...options.headers },
            ...options,
        });
        const data = await res.json().catch(() => null);
        if (!res.ok) {
            const detail = data?.detail || data?.message || res.statusText;
            throw new Error(detail);
        }
        return data;
    }

    // ─── Health check ───
    async function checkHealth() {
        try {
            await apiFetch('/health');
            dom.apiDot.className = 'status-dot online';
            dom.apiText.textContent = 'API Online';
            return true;
        } catch {
            dom.apiDot.className = 'status-dot offline';
            dom.apiText.textContent = 'API Offline';
            return false;
        }
    }

    // ─── Start research ───
    async function startResearch(query, opts = {}) {
        const body = {
            query,
            focus_areas: opts.focusAreas || null,
            source_preferences: opts.sourcePreferences || null,
            max_sources: opts.maxSources || 300,
            report_format: opts.reportFormat || 'markdown',
            citation_style: opts.citationStyle || 'APA',
            research_mode: opts.researchMode || 'auto',
        };
        return apiFetch('/research/start', {
            method: 'POST',
            body: JSON.stringify(body),
        });
    }

    // ─── Get status ───
    async function getStatus(sessionId) {
        return apiFetch(`/research/${sessionId}`);
    }

    // ─── Get results ───
    async function getResults(sessionId) {
        return apiFetch(`/research/${sessionId}/results`);
    }

    // ─── Cancel research ───
    async function cancelResearch(sessionId) {
        return apiFetch(`/research/${sessionId}/cancel`, { method: 'POST' });
    }

    // ─── History ───
    async function getHistory(page = 1, limit = 20, status = '', search = '') {
        let qs = `?page=${page}&limit=${limit}`;
        if (status) qs += `&status=${status}`;
        if (search) qs += `&search=${encodeURIComponent(search)}`;
        return apiFetch(`/history/${qs}`);
    }

    // ═══════════════════════════════════════
    //  WebSocket
    // ═══════════════════════════════════════

    function connectWebSocket(sessionId) {
        if (ws) {
            try { ws.close(); } catch {}
        }
        const url = `${WS_BASE}/${sessionId}`;
        ws = new WebSocket(url);

        ws.onopen = () => {
            addLog('WebSocket connected', 'system');
        };

        ws.onmessage = (evt) => {
            try {
                const msg = JSON.parse(evt.data);
                handleWsMessage(msg);
            } catch (e) {
                console.warn('WS parse error:', e);
            }
        };

        ws.onerror = () => {
            addLog('WebSocket error — falling back to polling', 'warning');
        };

        ws.onclose = () => {
            ws = null;
        };
    }

    function handleWsMessage(msg) {
        switch (msg.type) {
            case 'connection_established':
                addLog(`Connected to session ${msg.session_id?.slice(0, 8)}…`, 'system');
                break;

            case 'agent_status_update':
            case 'agent_update':
                updateAgentUI(msg.agent, msg.status, msg.progress, msg.output);
                break;

            case 'research_progress':
                if (msg.progress != null) setOverallProgress(msg.progress, msg.stage || msg.phase);
                break;

            case 'research_completed':
                addLog('Research completed!', 'success');
                onResearchComplete();
                break;

            case 'research_failed':
                addLog(`Research failed: ${msg.error || 'unknown error'}`, 'error');
                onResearchFailed(msg.error);
                break;

            case 'log':
            case 'info':
                addLog(msg.message || msg.output || JSON.stringify(msg), 'info');
                break;

            default:
                if (msg.agent) {
                    updateAgentUI(msg.agent, msg.status, msg.progress, msg.output);
                }
        }
    }

    // ═══════════════════════════════════════
    //  Pipeline UI
    // ═══════════════════════════════════════

    const AGENTS = ['user_proxy', 'researcher', 'analyst', 'fact_checker', 'report_generator'];

    function resetPipeline() {
        AGENTS.forEach(name => {
            const el = $(`#agent-${name}`);
            if (!el) return;
            el.classList.remove('active', 'completed', 'failed');
            const bar = el.querySelector('.agent-bar-fill');
            const text = el.querySelector('.agent-status-text');
            if (bar) bar.style.width = '0%';
            if (text) text.textContent = 'Waiting';
        });
        setOverallProgress(0, 'Initializing…');
        dom.logEntries.innerHTML = '';
    }

    function updateAgentUI(agentName, status, progress, output) {
        // Normalize agent name (handle variations)
        const normalized = agentName?.toLowerCase().replace(/[\s-]+/g, '_') || '';
        const el = $(`#agent-${normalized}`);
        if (!el) {
            // Still log even if no matching pipeline element
            if (output) addLog(`[${agentName}] ${output}`, 'info');
            return;
        }

        el.classList.remove('active', 'completed', 'failed');

        if (status === 'in_progress' || status === 'running') {
            el.classList.add('active');
        } else if (status === 'completed') {
            el.classList.add('completed');
        } else if (status === 'failed') {
            el.classList.add('failed');
        }

        const bar = el.querySelector('.agent-bar-fill');
        const text = el.querySelector('.agent-status-text');
        if (bar && progress != null) bar.style.width = `${progress}%`;
        if (text) text.textContent = capitalise(status || 'waiting');

        if (output) addLog(`[${capitalise(agentName)}] ${output}`, 'info');
    }

    function setOverallProgress(pct, phase) {
        if (dom.overallBarFill) dom.overallBarFill.style.width = `${pct}%`;
        if (dom.overallPercent) dom.overallPercent.textContent = `${Math.round(pct)}%`;
        if (dom.overallPhase && phase) dom.overallPhase.textContent = phase;
    }

    function addLog(message, level = 'info') {
        const entry = document.createElement('div');
        entry.className = `log-entry log-${level}`;
        const time = new Date().toLocaleTimeString();
        entry.innerHTML = `<span class="log-time">${time}</span> <span class="log-msg">${escapeHtml(message)}</span>`;
        dom.logEntries.appendChild(entry);
        dom.logEntries.scrollTop = dom.logEntries.scrollHeight;
    }

    function capitalise(s) {
        if (!s) return '';
        return s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    }

    // ═══════════════════════════════════════
    //  Polling Fallback
    // ═══════════════════════════════════════

    function startPolling(sessionId) {
        stopPolling();
        pollTimer = setInterval(async () => {
            try {
                const resp = await getStatus(sessionId);
                const d = resp?.data;
                if (!d) return;

                const statusVal = d.status?.toLowerCase();

                // Update progress
                if (d.progress != null) setOverallProgress(d.progress, d.current_stage || '');

                // Update agent statuses from backend
                if (d.agents && typeof d.agents === 'object') {
                    for (const [agentName, agentData] of Object.entries(d.agents)) {
                        if (typeof agentData === 'object') {
                            updateAgentUI(agentName, agentData.status, agentData.progress);
                        } else {
                            updateAgentUI(agentName, agentData);
                        }
                    }
                }

                // Terminal states
                if (statusVal === 'completed') {
                    onResearchComplete();
                } else if (statusVal === 'failed') {
                    onResearchFailed(d.error);
                } else if (statusVal === 'cancelled') {
                    onResearchCancelled();
                }
            } catch (err) {
                console.warn('Poll error:', err);
            }
        }, POLL_INTERVAL);
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    // ═══════════════════════════════════════
    //  Research Lifecycle
    // ═══════════════════════════════════════

    async function handleStartResearch(e) {
        e.preventDefault();
        if (isResearching) return;

        const query = dom.queryInput.value.trim();
        if (query.length < 5) {
            toast('Query must be at least 5 characters', 'warning');
            dom.queryInput.focus();
            return;
        }

        // Collect options
        const focusRaw = dom.focusAreas?.value?.trim();
        const focusAreas = focusRaw ? focusRaw.split(',').map(s => s.trim()).filter(Boolean) : null;

        const sourcePrefs = dom.sourcePrefs
            ? Array.from(dom.sourcePrefs.selectedOptions).map(o => o.value)
            : null;

        const opts = {
            focusAreas: focusAreas?.length ? focusAreas : null,
            sourcePreferences: sourcePrefs?.length ? sourcePrefs : null,
            maxSources: parseInt(dom.maxSources?.value) || 300,
            reportFormat: dom.reportFormat?.value || 'markdown',
            citationStyle: dom.citationStyle?.value || 'APA',
            researchMode: dom.researchMode?.value || 'auto',
        };

        // UI transitions
        isResearching = true;
        dom.btnStart.disabled = true;
        dom.btnStart.innerHTML = `<span class="spinner"></span> Starting…`;
        dom.resultsSection.classList.add('hidden');
        dom.pipelineSection.classList.remove('hidden');
        dom.btnCancel.classList.remove('hidden');
        resetPipeline();

        try {
            const resp = await startResearch(query, opts);
            const sessionId = resp?.data?.session_id;
            if (!sessionId) throw new Error('No session ID returned');

            currentSessionId = sessionId;
            addLog(`Session started: ${sessionId.slice(0, 8)}…`, 'success');
            addLog(`Query: "${query}"`, 'info');
            toast('Research started!', 'success');

            // Connect WebSocket + polling fallback
            connectWebSocket(sessionId);
            startPolling(sessionId);

            dom.btnStart.innerHTML = `<span class="spinner"></span> Researching…`;
        } catch (err) {
            toast(`Failed to start research: ${err.message}`, 'error');
            resetResearchUI();
        }
    }

    async function onResearchComplete() {
        stopPolling();
        isResearching = false;
        setOverallProgress(100, 'Completed');
        dom.btnCancel.classList.add('hidden');
        dom.btnStart.disabled = false;
        dom.btnStart.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Start Research`;

        // Mark all agents completed
        AGENTS.forEach(name => {
            const el = $(`#agent-${name}`);
            if (el) {
                el.classList.remove('active', 'failed');
                el.classList.add('completed');
                const bar = el.querySelector('.agent-bar-fill');
                const text = el.querySelector('.agent-status-text');
                if (bar) bar.style.width = '100%';
                if (text) text.textContent = 'Completed';
            }
        });

        addLog('Research completed — loading results…', 'success');
        toast('Research completed!', 'success');

        // Fetch and display results
        try {
            const resp = await getResults(currentSessionId);
            displayResults(resp?.data);
        } catch (err) {
            toast(`Failed to load results: ${err.message}`, 'error');
            addLog(`Error loading results: ${err.message}`, 'error');
        }
    }

    function onResearchFailed(error) {
        stopPolling();
        isResearching = false;
        dom.btnCancel.classList.add('hidden');
        dom.btnStart.disabled = false;
        dom.btnStart.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Start Research`;
        setOverallProgress(0, 'Failed');
        toast(`Research failed: ${error || 'Unknown error'}`, 'error');
        addLog(`Failed: ${error || 'Unknown error'}`, 'error');
    }

    function onResearchCancelled() {
        stopPolling();
        isResearching = false;
        dom.btnCancel.classList.add('hidden');
        dom.btnStart.disabled = false;
        dom.btnStart.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Start Research`;
        setOverallProgress(0, 'Cancelled');
        toast('Research cancelled', 'warning');
        addLog('Research was cancelled', 'warning');
    }

    function resetResearchUI() {
        isResearching = false;
        dom.btnStart.disabled = false;
        dom.btnStart.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Start Research`;
        dom.btnCancel.classList.add('hidden');
    }

    async function handleCancel() {
        if (!currentSessionId) return;
        try {
            await cancelResearch(currentSessionId);
            onResearchCancelled();
        } catch (err) {
            toast(`Cancel failed: ${err.message}`, 'error');
        }
    }

    // ═══════════════════════════════════════
    //  Results Display
    // ═══════════════════════════════════════

    function displayResults(data) {
        if (!data) {
            addLog('No results data received', 'warning');
            return;
        }

        dom.resultsSection.classList.remove('hidden');

        // Report tab
        const report = data.report;
        if (report) {
            const content = report.content || report.markdown_content || report.html_content || '';
            dom.reportContent.innerHTML = renderMarkdown(content);
            dom.resultsTitle.textContent = report.title || 'Research Results';
        } else {
            dom.reportContent.innerHTML = '<p class="empty-state">No report generated.</p>';
        }

        // Findings tab
        const findings = data.findings || [];
        if (findings.length) {
            dom.findingsList.innerHTML = findings.map((f, i) => `
                <div class="finding-card">
                    <div class="finding-header">
                        <span class="finding-num">#${i + 1}</span>
                        <span class="finding-confidence" style="color: ${confidenceColor(f.confidence)}">
                            ${Math.round((f.confidence || 0) * 100)}% confidence
                        </span>
                    </div>
                    <h4 class="finding-title">${escapeHtml(f.title || f.claim || 'Finding')}</h4>
                    <p class="finding-body">${escapeHtml(f.description || f.evidence || f.content || '')}</p>
                    ${f.source_urls?.length ? `<div class="finding-sources">${f.source_urls.map(u => `<a href="${escapeHtml(u)}" target="_blank" rel="noopener">${shortenUrl(u)}</a>`).join(', ')}</div>` : ''}
                </div>
            `).join('');
        } else {
            dom.findingsList.innerHTML = '<p class="empty-state">No findings available.</p>';
        }

        // Sources tab
        const sources = data.sources || [];
        if (sources.length) {
            dom.sourcesList.innerHTML = sources.map(s => `
                <div class="source-card">
                    <div class="source-type">${escapeHtml(s.source_type || s.type || 'web')}</div>
                    <a class="source-title" href="${escapeHtml(s.url || '#')}" target="_blank" rel="noopener">
                        ${escapeHtml(s.title || s.url || 'Untitled')}
                    </a>
                    <p class="source-snippet">${escapeHtml(truncate(s.snippet || s.description || s.content || '', 200))}</p>
                    ${s.credibility_score != null ? `<span class="source-cred">Credibility: ${Math.round(s.credibility_score * 100)}%</span>` : ''}
                </div>
            `).join('');
        } else {
            dom.sourcesList.innerHTML = '<p class="empty-state">No sources collected.</p>';
        }

        // Metadata tab
        const meta = data.metadata || {};
        dom.metadataContent.innerHTML = `
            <div class="meta-grid">
                <div class="meta-item"><span class="meta-label">Session ID</span><span class="meta-value">${escapeHtml(data.research_id || '')}</span></div>
                <div class="meta-item"><span class="meta-label">Query</span><span class="meta-value">${escapeHtml(data.query || '')}</span></div>
                <div class="meta-item"><span class="meta-label">Status</span><span class="meta-value status-badge status-${data.status}">${capitalise(data.status || '')}</span></div>
                <div class="meta-item"><span class="meta-label">Created</span><span class="meta-value">${formatDate(data.created_at)}</span></div>
                <div class="meta-item"><span class="meta-label">Completed</span><span class="meta-value">${formatDate(data.completed_at)}</span></div>
                <div class="meta-item"><span class="meta-label">Processing Time</span><span class="meta-value">${data.processing_time || '—'}</span></div>
                <div class="meta-item"><span class="meta-label">Quality Score</span><span class="meta-value">${data.quality_score != null ? Math.round(data.quality_score * 100) + '%' : '—'}</span></div>
                <div class="meta-item"><span class="meta-label">Total Sources</span><span class="meta-value">${meta.sources_count?.total ?? sources.length}</span></div>
                <div class="meta-item"><span class="meta-label">Findings</span><span class="meta-value">${meta.findings_count ?? findings.length}</span></div>
            </div>
        `;

        // Scroll to results
        dom.resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    // ─── Markdown renderer (basic) ───
    function renderMarkdown(md) {
        if (!md) return '';
        let html = escapeHtml(md);
        // Headers
        html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
        html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
        // Bold / italic
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
        // Links
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
        // Lists
        html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
        // Line breaks
        html = html.replace(/\n\n/g, '</p><p>');
        html = html.replace(/\n/g, '<br>');
        return `<div class="rendered-md"><p>${html}</p></div>`;
    }

    function confidenceColor(score) {
        if (!score) return 'var(--text-muted)';
        if (score >= 0.8) return 'var(--success)';
        if (score >= 0.5) return 'var(--warning)';
        return 'var(--error)';
    }

    function truncate(str, max) {
        if (!str) return '';
        return str.length > max ? str.slice(0, max) + '…' : str;
    }

    function shortenUrl(url) {
        try {
            const u = new URL(url);
            return u.hostname + (u.pathname.length > 30 ? u.pathname.slice(0, 30) + '…' : u.pathname);
        } catch {
            return url?.slice(0, 50) || '';
        }
    }

    // ─── Downloads ───
    function downloadFile(content, filename, mime) {
        const blob = new Blob([content], { type: mime });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        a.click();
        URL.revokeObjectURL(a.href);
    }

    function handleDownloadMd() {
        const content = dom.reportContent?.innerText || '';
        if (!content) { toast('No report content to download', 'warning'); return; }
        downloadFile(content, `research-report-${currentSessionId?.slice(0, 8) || 'report'}.md`, 'text/markdown');
    }

    function handleDownloadHtml() {
        const content = dom.reportContent?.innerHTML || '';
        if (!content) { toast('No report content to download', 'warning'); return; }
        const fullHtml = `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Research Report</title><style>body{font-family:Inter,sans-serif;max-width:800px;margin:0 auto;padding:40px;line-height:1.7;color:#1a1a2e}h1,h2,h3{margin-top:1.5em}a{color:#6366f1}ul{padding-left:1.5em}</style></head><body>${content}</body></html>`;
        downloadFile(fullHtml, `research-report-${currentSessionId?.slice(0, 8) || 'report'}.html`, 'text/html');
    }

    // ═══════════════════════════════════════
    //  History
    // ═══════════════════════════════════════

    let historyPage = 1;

    async function loadHistory() {
        const search = dom.historySearch?.value?.trim() || '';
        const filter = dom.historyFilter?.value || '';

        try {
            const resp = await getHistory(historyPage, 20, filter, search);
            const data = resp?.data;
            if (!data) throw new Error('No data');

            const sessions = data.sessions || [];
            const pagination = data.pagination || {};

            if (!sessions.length) {
                dom.historyList.innerHTML = '<p class="empty-state">No research sessions found.</p>';
                return;
            }

            dom.historyList.innerHTML = sessions.map(s => `
                <div class="history-card" data-session-id="${escapeHtml(s.session_id)}">
                    <div class="history-card-header">
                        <span class="status-badge status-${s.status}">${capitalise(s.status)}</span>
                        <span class="history-time">${timeAgo(s.created_at)}</span>
                    </div>
                    <p class="history-query">${escapeHtml(s.query || '')}</p>
                    <div class="history-card-footer">
                        <span class="history-mode">${capitalise(s.research_mode || 'auto')}</span>
                        ${s.progress != null ? `<span class="history-progress">${Math.round(s.progress)}%</span>` : ''}
                        <button class="btn-sm btn-view-session">View</button>
                    </div>
                </div>
            `).join('');

            // Pagination
            if (pagination.pages > 1) {
                dom.historyList.innerHTML += `
                    <div class="pagination">
                        <button class="btn-sm" ${historyPage <= 1 ? 'disabled' : ''} id="histPrev">← Prev</button>
                        <span>Page ${pagination.page} of ${pagination.pages}</span>
                        <button class="btn-sm" ${historyPage >= pagination.pages ? 'disabled' : ''} id="histNext">Next →</button>
                    </div>
                `;
                $('#histPrev')?.addEventListener('click', () => { historyPage--; loadHistory(); });
                $('#histNext')?.addEventListener('click', () => { historyPage++; loadHistory(); });
            }

            // View session clicks
            dom.historyList.querySelectorAll('.btn-view-session').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const card = e.target.closest('.history-card');
                    const sid = card?.dataset.sessionId;
                    if (sid) viewSession(sid);
                });
            });

        } catch (err) {
            dom.historyList.innerHTML = `<p class="empty-state">Failed to load history: ${escapeHtml(err.message)}</p>`;
        }
    }

    async function viewSession(sessionId) {
        // Switch to research view
        switchView('research');
        currentSessionId = sessionId;
        dom.pipelineSection.classList.remove('hidden');
        resetPipeline();
        addLog(`Loading session ${sessionId.slice(0, 8)}…`, 'info');

        try {
            const statusResp = await getStatus(sessionId);
            const d = statusResp?.data;
            if (!d) throw new Error('Status not found');

            const statusVal = d.status?.toLowerCase();

            if (statusVal === 'completed') {
                setOverallProgress(100, 'Completed');
                AGENTS.forEach(name => {
                    const el = $(`#agent-${name}`);
                    if (el) {
                        el.classList.add('completed');
                        const bar = el.querySelector('.agent-bar-fill');
                        if (bar) bar.style.width = '100%';
                        const text = el.querySelector('.agent-status-text');
                        if (text) text.textContent = 'Completed';
                    }
                });
                const results = await getResults(sessionId);
                displayResults(results?.data);
            } else if (statusVal === 'running' || statusVal === 'in_progress') {
                isResearching = true;
                dom.btnCancel.classList.remove('hidden');
                dom.btnStart.disabled = true;
                dom.btnStart.innerHTML = `<span class="spinner"></span> Researching…`;
                setOverallProgress(d.progress || 0, d.current_stage || 'Running');
                connectWebSocket(sessionId);
                startPolling(sessionId);
            } else if (statusVal === 'failed') {
                setOverallProgress(0, 'Failed');
                addLog(`Session failed: ${d.error || 'Unknown error'}`, 'error');
            } else {
                setOverallProgress(0, capitalise(statusVal));
            }
        } catch (err) {
            addLog(`Error loading session: ${err.message}`, 'error');
            toast(`Failed to load session: ${err.message}`, 'error');
        }
    }

    // ═══════════════════════════════════════
    //  Navigation / Views
    // ═══════════════════════════════════════

    function switchView(viewName) {
        $$('.view').forEach(v => v.classList.remove('active'));
        dom.navBtns.forEach(b => b.classList.remove('active'));

        const target = $(`#view${capitalise(viewName)}`);
        if (target) target.classList.add('active');

        dom.navBtns.forEach(b => {
            if (b.dataset.view === viewName) b.classList.add('active');
        });

        if (viewName === 'history') {
            historyPage = 1;
            loadHistory();
        }
    }

    // ═══════════════════════════════════════
    //  Tab Switching
    // ═══════════════════════════════════════

    function switchTab(tabName) {
        dom.tabs.forEach(t => t.classList.remove('active'));
        dom.tabs.forEach(t => { if (t.dataset.tab === tabName) t.classList.add('active'); });

        ['Report', 'Findings', 'Sources', 'Metadata'].forEach(name => {
            const el = $(`#tab${name}`);
            if (el) el.classList.toggle('hidden', name.toLowerCase() !== tabName);
        });
    }

    // ═══════════════════════════════════════
    //  Event Binding
    // ═══════════════════════════════════════

    function bindEvents() {
        // Form submit
        dom.form?.addEventListener('submit', handleStartResearch);

        // Cancel
        dom.btnCancel?.addEventListener('click', handleCancel);

        // Clear log
        dom.btnClearLog?.addEventListener('click', () => { dom.logEntries.innerHTML = ''; });

        // Nav buttons
        dom.navBtns.forEach(btn => {
            btn.addEventListener('click', () => switchView(btn.dataset.view));
        });

        // Tabs
        dom.tabs.forEach(tab => {
            tab.addEventListener('click', () => switchTab(tab.dataset.tab));
        });

        // Downloads
        dom.btnDownloadMd?.addEventListener('click', handleDownloadMd);
        dom.btnDownloadHtml?.addEventListener('click', handleDownloadHtml);

        // New research
        dom.btnNewResearch?.addEventListener('click', () => {
            dom.resultsSection.classList.add('hidden');
            dom.pipelineSection.classList.add('hidden');
            dom.queryInput.value = '';
            dom.queryInput.focus();
            currentSessionId = null;
        });

        // History search/filter (debounced)
        let historyTimeout;
        dom.historySearch?.addEventListener('input', () => {
            clearTimeout(historyTimeout);
            historyTimeout = setTimeout(() => { historyPage = 1; loadHistory(); }, 400);
        });
        dom.historyFilter?.addEventListener('change', () => { historyPage = 1; loadHistory(); });
    }

    // ═══════════════════════════════════════
    //  Init
    // ═══════════════════════════════════════

    async function init() {
        bindEvents();
        await checkHealth();
        // Re-check health every 30s
        setInterval(checkHealth, 30000);
    }

    // Start when DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
