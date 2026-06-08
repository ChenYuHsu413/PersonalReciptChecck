// ==============================================================================
// Gmail Invoice Automation - Dashboard Controller (app.js)
// ==============================================================================

// Global State
let invoicesData = [];
let filteredInvoices = [];
let currentPage = 1;
const rowsPerPage = 10;

// Chart Instances (Stored globally to destroy/recreate cleanly)
let spendChartInstance = null;
let statusChartInstance = null;

// Polling interval ID for sync logs
let syncPollInterval = null;

// DOM Elements
const syncBtn = document.getElementById('sync-btn');
const syncIcon = document.getElementById('sync-icon');
const systemStatusDot = document.getElementById('system-status-dot');
const systemStatusText = document.getElementById('system-status-text');
const logTerminal = document.getElementById('log-terminal');

const statTotalCount = document.getElementById('stat-total-count');
const statTotalAmount = document.getElementById('stat-total-amount');
const statAvgAmount = document.getElementById('stat-avg-amount');
const statWinningsCount = document.getElementById('stat-winnings-count');
const statWinningsText = document.getElementById('stat-winnings-text');
const statPendingCount = document.getElementById('stat-pending-count');
const statEncryptedCount = document.getElementById('stat-encrypted-count');

const searchInput = document.getElementById('search-input');
const statusFilter = document.getElementById('status-filter');
const tableBody = document.getElementById('table-body');

const startIdxSpan = document.getElementById('start-idx');
const endIdxSpan = document.getElementById('end-idx');
const totalFilteredSpan = document.getElementById('total-filtered-count');
const pageNumDisplay = document.getElementById('page-num-display');
const prevPageBtn = document.getElementById('prev-page-btn');
const nextPageBtn = document.getElementById('next-page-btn');

// App Initialization
document.addEventListener('DOMContentLoaded', () => {
    initLucide();
    initChartTabs();
    fetchDashboardData();
    checkActiveSyncStatus();
    
    // Add Event Listeners
    syncBtn.addEventListener('click', startSync);
    searchInput.addEventListener('input', handleTableFilter);
    statusFilter.addEventListener('change', handleTableFilter);
    prevPageBtn.addEventListener('click', () => changePage(-1));
    nextPageBtn.addEventListener('click', () => changePage(1));
});

// Helper: Initialize or update Lucide Icons
function initLucide() {
    if (window.lucide) {
        window.lucide.createIcons();
    }
}

// Helper: Chart Tab Switching Logic
function initChartTabs() {
    const tabs = document.querySelectorAll('.tab-btn');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.chart-wrapper').forEach(w => w.classList.remove('active'));
            
            tab.classList.add('active');
            const targetId = tab.getAttribute('data-target');
            document.getElementById(targetId).classList.add('active');
        });
    });
}

// Fetch stats and list from API
async function fetchDashboardData() {
    try {
        const statsRes = await fetch('/api/stats');
        const stats = await statsRes.json();
        updateStatsUI(stats);
        renderCharts(stats);
        
        const listRes = await fetch('/api/invoices');
        invoicesData = await listRes.json();
        
        // Default sorting: Newest invoices first (based on date or processing time)
        invoicesData.sort((a, b) => {
            const dateA = a['發票日期'] || '';
            const dateB = b['發票日期'] || '';
            return dateB.localeCompare(dateA);
        });

        filteredInvoices = [...invoicesData];
        currentPage = 1;
        renderTable();
    } catch (error) {
        console.error("無法加載資料:", error);
        appendTerminalLog(`[錯誤] 讀取 API 資料失敗，請確認伺服器運作正常。`, 'error-msg');
    }
}

// Check if a sync task is currently running when loading the page
async function checkActiveSyncStatus() {
    try {
        const res = await fetch('/api/sync/status');
        const status = await res.json();
        if (status.in_progress) {
            setSyncingState(true);
            updateTerminalLogs(status.logs);
            startPollingStatus();
        }
    } catch (e) {
        console.error("無法取得同步狀態:", e);
    }
}

// Trigger Gmail Synchronization
async function startSync() {
    try {
        setSyncingState(true);
        appendTerminalLog(`[系統] 發起 Gmail 同步請求...`, 'system-msg');
        
        const res = await fetch('/api/sync', { method: 'POST' });
        const data = await res.json();
        
        if (res.ok) {
            appendTerminalLog(`[系統] 同步引擎已啟動: ${data.message}`, 'system-msg');
            startPollingStatus();
        } else {
            appendTerminalLog(`[錯誤] 同步請求被拒絕: ${data.message || '未知錯誤'}`, 'error-msg');
            setSyncingState(false);
        }
    } catch (error) {
        console.error("同步失敗:", error);
        appendTerminalLog(`[錯誤] 發起同步失敗，連線異常。`, 'error-msg');
        setSyncingState(false);
    }
}

// Set UI elements based on syncing state
function setSyncingState(isSyncing) {
    if (isSyncing) {
        syncBtn.disabled = true;
        syncIcon.classList.add('spinning');
        syncBtn.querySelector('span').innerText = '正在同步 Gmail...';
        systemStatusDot.className = 'status-dot-pulse running';
        systemStatusText.innerText = '同步執行中';
    } else {
        syncBtn.disabled = false;
        syncIcon.classList.remove('spinning');
        syncBtn.querySelector('span').innerText = '立即同步 Gmail';
        systemStatusDot.className = 'status-dot-pulse idle';
        systemStatusText.innerText = '系統就緒';
    }
}

// Start polling API for sync logs and progress status
function startPollingStatus() {
    if (syncPollInterval) clearInterval(syncPollInterval);
    
    // Clear terminal screen
    logTerminal.innerHTML = '<div class="log-line system-msg">[系統] 正在拉取 Gmail 發票，請稍候...</div>';
    
    let lastLogCount = 0;
    
    syncPollInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/sync/status');
            const data = await res.json();
            
            // Render logs if there are new ones
            if (data.logs && data.logs.length > lastLogCount) {
                const newLogs = data.logs.slice(lastLogCount);
                updateTerminalLogs(newLogs);
                lastLogCount = data.logs.length;
            }
            
            // Check if finished
            if (!data.in_progress) {
                clearInterval(syncPollInterval);
                syncPollInterval = null;
                setSyncingState(false);
                appendTerminalLog(`[系統] 同步完成！重新整理統計數據與明細...`, 'success-msg');
                // Refresh data
                fetchDashboardData();
            }
        } catch (error) {
            console.error("輪詢狀態失敗:", error);
        }
    }, 1000);
}

// Append a single log message to console terminal
function appendTerminalLog(message, className = '') {
    const line = document.createElement('div');
    line.className = `log-line ${className}`;
    line.innerText = message;
    logTerminal.appendChild(line);
    logTerminal.scrollTop = logTerminal.scrollHeight;
}

// Add batch lines of log and style them
function updateTerminalLogs(logs) {
    logs.forEach(log => {
        let styleClass = 'process-msg';
        if (log.includes('[成功]') || log.includes('成功')) {
            styleClass = 'success-msg';
        } else if (log.includes('[錯誤]') || log.includes('失敗')) {
            styleClass = 'error-msg';
        } else if (log.includes('[警告]') || log.includes('警告')) {
            styleClass = 'error-msg';
        } else if (log.includes('[系統]') || log.includes('系統')) {
            styleClass = 'system-msg';
        } else if (log.includes('[資訊]') || log.includes('[搜尋]')) {
            styleClass = 'info-msg';
        } else if (log.includes('[略過]') || log.includes('略過') || log.includes('過濾')) {
            styleClass = 'tip-msg';
        }
        appendTerminalLog(log, styleClass);
    });
}

// Animate values of counters with high-performance requestAnimationFrame
function animateCounter(element, targetValue, duration = 800, prefix = '', suffix = '') {
    const startValue = 0;
    const endValue = parseInt(targetValue) || 0;
    if (endValue === 0) {
        element.innerText = prefix + '0' + suffix;
        return;
    }
    
    const startTime = performance.now();
    
    function update(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        
        // easeOutQuad easing formula
        const easeProgress = progress * (2 - progress);
        
        const currentValue = Math.floor(startValue + easeProgress * (endValue - startValue));
        element.innerText = prefix + currentValue.toLocaleString('zh-TW') + suffix;
        
        if (progress < 1) {
            requestAnimationFrame(update);
        } else {
            element.innerText = prefix + endValue.toLocaleString('zh-TW') + suffix;
        }
    }
    
    requestAnimationFrame(update);
}

// Update Top Stats Cards
function updateStatsUI(stats) {
    // 1. Total Invoices
    animateCounter(statTotalCount, stats.total_count);
    
    // 2. Total Spend & Average
    animateCounter(statTotalAmount, stats.total_amount, 1000, 'NT$ ');
    const avg = stats.total_count > 0 ? Math.round(stats.total_amount / stats.total_count) : 0;
    statAvgAmount.innerText = `平均每張 NT$ ${avg.toLocaleString('zh-TW')}`;
    
    // 3. Winnings
    let winCount = 0;
    for (const [key, val] of Object.entries(stats.status_dist)) {
        if (key.includes("中獎") || key.includes("中")) {
            winCount += val;
        }
    }
    animateCounter(statWinningsCount, winCount);
    if (winCount > 0) {
        statWinningsText.innerText = `恭喜中獎！共中 ${winCount} 張發票！`;
        statWinningsText.className = "stat-desc text-gold font-weight-bold";
        document.querySelector('.key-highlight').style.boxShadow = "0 8px 32px 0 rgba(251, 191, 36, 0.25)";
    } else {
        statWinningsText.innerText = "期待幸運之神降臨";
        statWinningsText.className = "stat-desc text-gold-dim";
        document.querySelector('.key-highlight').style.boxShadow = "0 8px 32px 0 rgba(251, 191, 36, 0.08)";
    }
    
    // 4. Pending / Encrypted
    const pendingCount = stats.status_dist["未開獎"] || 0;
    const encryptedCount = stats.status_dist["無法對獎(加密)"] || 0;
    animateCounter(statPendingCount, pendingCount + encryptedCount);
    statEncryptedCount.innerText = `加密 PDF: ${encryptedCount} 張 | 未開獎: ${pendingCount} 張`;
}

// Render monthly spending line chart and doughnut status chart
function renderCharts(stats) {
    const monthlyData = stats.monthly_spending || {};
    const statusData = stats.status_dist || {};
    
    // -- 1. Monthly Spending Trend Line Chart --
    const lineCtx = document.getElementById('spendChart').getContext('2d');
    if (spendChartInstance) {
        spendChartInstance.destroy();
    }
    
    const months = Object.keys(monthlyData);
    const spentAmounts = Object.values(monthlyData);
    
    // Dynamic Gradient for area filling
    const blueGradient = lineCtx.createLinearGradient(0, 0, 0, 300);
    blueGradient.addColorStop(0, 'rgba(59, 130, 246, 0.4)');
    blueGradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)');
    
    spendChartInstance = new Chart(lineCtx, {
        type: 'line',
        data: {
            labels: months,
            datasets: [{
                label: '月度消費總額',
                data: spentAmounts,
                borderColor: '#3b82f6',
                borderWidth: 3,
                backgroundColor: blueGradient,
                fill: true,
                tension: 0.4,
                pointBackgroundColor: '#3b82f6',
                pointBorderColor: '#ffffff',
                pointHoverRadius: 7,
                pointRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    padding: 12,
                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    titleColor: '#fff',
                    bodyColor: '#94a3b8',
                    titleFont: { family: 'Outfit', weight: 'bold' },
                    bodyFont: { family: 'Inter' }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8', font: { family: 'Outfit' } }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: {
                        color: '#94a3b8',
                        font: { family: 'Outfit' },
                        callback: function(value) { return 'NT$ ' + value.toLocaleString(); }
                    }
                }
            }
        }
    });
    
    // -- 2. Invoice Status Doughnut Chart --
    const donutCtx = document.getElementById('statusChart').getContext('2d');
    if (statusChartInstance) {
        statusChartInstance.destroy();
    }
    
    // Classify statuses into standard categories
    const categories = {
        '中獎': 0,
        '未中獎': 0,
        '未開獎': 0,
        '加密 / 無法對獎': 0
    };
    
    Object.entries(statusData).forEach(([key, val]) => {
        if (key.includes('中')) {
            categories['中獎'] += val;
        } else if (key.includes('未開獎')) {
            categories['未開獎'] += val;
        } else if (key.includes('加密') || key.includes('密碼') || key.includes('無法對獎')) {
            categories['加密 / 無法對獎'] += val;
        } else {
            categories['未中獎'] += val;
        }
    });
    
    // Filter out categories with 0 values to keep the doughnut chart clean
    const activeLabels = [];
    const activeValues = [];
    const baseColors = {
        '中獎': '#fbbf24',
        '未中獎': '#64748b',
        '未開獎': '#3b82f6',
        '加密 / 無法對獎': '#8b5cf6'
    };
    const activeColors = [];
    
    Object.entries(categories).forEach(([label, val]) => {
        if (val > 0) {
            activeLabels.push(label);
            activeValues.push(val);
            activeColors.push(baseColors[label]);
        }
    });
    
    statusChartInstance = new Chart(donutCtx, {
        type: 'doughnut',
        data: {
            labels: activeLabels,
            datasets: [{
                data: activeValues,
                backgroundColor: activeColors,
                borderWidth: 1,
                borderColor: '#0f1322',
                hoverOffset: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#94a3b8',
                        padding: 15,
                        font: { family: 'Inter', size: 11 }
                    }
                },
                tooltip: {
                    padding: 12,
                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    titleColor: '#fff',
                    bodyColor: '#94a3b8',
                    titleFont: { family: 'Outfit', weight: 'bold' },
                    bodyFont: { family: 'Inter' }
                }
            },
            cutout: '65%'
        }
    });
}

// Live Invoices Table Rendering & Pagination
function renderTable() {
    tableBody.innerHTML = '';
    
    if (filteredInvoices.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center text-muted py-5">
                    找不到符合條件的發票。
                </td>
            </tr>
        `;
        startIdxSpan.innerText = '0';
        endIdxSpan.innerText = '0';
        totalFilteredSpan.innerText = '0';
        pageNumDisplay.innerText = '頁碼 1 / 1';
        prevPageBtn.disabled = true;
        nextPageBtn.disabled = true;
        return;
    }
    
    const startIndex = (currentPage - 1) * rowsPerPage;
    const endIndex = Math.min(startIndex + rowsPerPage, filteredInvoices.length);
    const paginatedItems = filteredInvoices.slice(startIndex, endIndex);
    
    paginatedItems.forEach(invoice => {
        const tr = document.createElement('tr');
        
        // Formulate result badge class
        const result = invoice['對獎結果'] || '未中獎';
        let badgeClass = 'badge-loser';
        if (result.includes('中獎') || result.includes('中')) {
            badgeClass = 'badge-winner';
        } else if (result.includes('未開獎')) {
            badgeClass = 'badge-pending';
        } else if (result.includes('已逾期')) {
            badgeClass = 'badge-expired';
        } else if (result.includes('無法對獎') || result.includes('加密') || result.includes('密碼')) {
            badgeClass = 'badge-encrypted';
        }
        
        // Safe values fallback
        const invNum = invoice['發票號碼'] || '無';
        const invDate = invoice['發票日期'] || '無';
        const invAmt = invoice['總金額'] || '0';
        const mailSub = invoice['來源郵件主旨'] || '無';
        const mailTime = invoice['收信時間'] || '無';
        const pdfName = invoice['PDF 檔名'] || '內文解析';
        const importTime = invoice['處理時間'] || '無';
        
        tr.innerHTML = `
            <td class="font-mono font-weight-semibold">${invNum}</td>
            <td>${invDate}</td>
            <td class="text-right font-weight-bold">NT$ ${parseInt(invAmt).toLocaleString()}</td>
            <td title="${mailSub}">${mailSub.length > 28 ? mailSub.substring(0, 28) + '...' : mailSub}</td>
            <td title="${mailTime}" class="text-muted text-xs">${formatEmailTime(mailTime)}</td>
            <td title="${pdfName}">${pdfName.length > 20 ? pdfName.substring(0, 20) + '...' : pdfName}</td>
            <td><span class="badge ${badgeClass}">${result}</span></td>
            <td class="text-muted text-xs">${importTime}</td>
        `;
        tableBody.appendChild(tr);
    });
    
    // Update Pagination UI
    startIdxSpan.innerText = (startIndex + 1).toString();
    endIdxSpan.innerText = endIndex.toString();
    totalFilteredSpan.innerText = filteredInvoices.length.toString();
    
    const totalPages = Math.ceil(filteredInvoices.length / rowsPerPage);
    pageNumDisplay.innerText = `頁碼 ${currentPage} / ${totalPages}`;
    
    prevPageBtn.disabled = currentPage === 1;
    nextPageBtn.disabled = currentPage === totalPages;
    
    initLucide();
}

// Convert standard Gmail raw date string to a shorter presentation
function formatEmailTime(rawTime) {
    if (!rawTime) return '';
    try {
        // Handle standard formats: Mon, 1 Jun 2026 10:00:00 +0800
        const d = new Date(rawTime);
        if (!isNaN(d.getTime())) {
            const y = d.getFullYear();
            const m = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            const h = String(d.getHours()).padStart(2, '0');
            const min = String(d.getMinutes()).padStart(2, '0');
            return `${y}-${m}-${day} ${h}:${min}`;
        }
    } catch (e) {
        // Fallback to raw string
    }
    return rawTime;
}

// Pagination Controls Trigger
function changePage(direction) {
    const totalPages = Math.ceil(filteredInvoices.length / rowsPerPage);
    const newPage = currentPage + direction;
    if (newPage >= 1 && newPage <= totalPages) {
        currentPage = newPage;
        renderTable();
    }
}

// Search and Filter Trigger
function handleTableFilter() {
    const query = searchInput.value.toLowerCase().trim();
    const statusVal = statusFilter.value;
    
    filteredInvoices = invoicesData.filter(invoice => {
        // 1. Check Search Query
        const num = (invoice['發票號碼'] || '').toLowerCase();
        const amt = (invoice['總金額'] || '').toString();
        const sub = (invoice['來源郵件主旨'] || '').toLowerCase();
        const file = (invoice['PDF 檔名'] || '').toLowerCase();
        
        const matchesQuery = !query || 
                             num.includes(query) || 
                             amt.includes(query) || 
                             sub.includes(query) || 
                             file.includes(query);
                             
        // 2. Check Status Selector
        const res = invoice['對獎結果'] || '未中獎';
        let matchesStatus = true;
        if (statusVal === '中獎') {
            matchesStatus = res.includes('中獎') || res.includes('中');
        } else if (statusVal === '未中獎') {
            matchesStatus = res.includes('未中獎');
        } else if (statusVal === '未開獎') {
            matchesStatus = res.includes('未開獎');
        } else if (statusVal === '無法對獎') {
            matchesStatus = res.includes('無法對獎') || res.includes('加密') || res.includes('密碼');
        }
        
        return matchesQuery && matchesStatus;
    });
    
    currentPage = 1;
    renderTable();
}
