// ─── INIT ────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function () {
    initializeCircularProgress();
    animateWellnessBars();
    loadAnalytics();
    initModalHandlers();
    initNavHandlers();
    autoDismissAlert();
    initChartFilters();
});

// ─── ANALYTICS LOADER ────────────────────────────────────────────────────────

let analyticsData = null;

function loadAnalytics() {
    fetch('/api/analytics/')
        .then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}: ${r.statusText}`);
            return r.json();
        })
        .then(data => {
            analyticsData = data;
            console.log('✅ Analytics loaded:', data);

            // API keys: score_trend, facial_emotions, feeling_scores,
            //           recommendations, summary, sessions, stats, wellness

            renderScoreTrendChart(data.score_trend);
            renderFacialEmotionChart(data.facial_emotions);
            renderFeelingScoresChart(data.feeling_scores);
            renderSessionList(data.sessions);
            renderStatCards(data.stats);
            renderSummaryCards(data.summary);
            renderWellnessBars(data.wellness);
            renderRecommendations(data.recommendations, data.sessions);
        })
        .catch(err => {
            console.error('❌ Analytics load failed:', err);
            showEmptyState();
        });
}

function showEmptyState() {
    _setText('risk-level-value', 'No data yet');
    _setText('risk-level-note', 'Complete an assessment to see results');
    _setText('current-mood-value', 'No data yet');
    _setText('current-mood-note', 'Complete an assessment to see results');
    _setText('streak-value', '0 days');
    _setText('streak-note', 'Complete your first session to start a streak.');
    _setText('stat-sessions', '0');
    _setText('stat-resources', '0');
    _setText('stat-days', '0');

    const container = document.querySelector('.sessions-list');
    if (container) container.innerHTML = '<p style="color:#9AA5B9;font-size:14px;padding:16px;">No sessions yet. Start your first assessment!</p>';

    const recList = document.getElementById('recommendations-list');
    if (recList) recList.innerHTML = '<p style="color:#9ca3af;font-size:13px;padding:12px 0;">Complete an assessment to see recommendations.</p>';

    const noteEl = document.querySelector('.panel-note span');
    if (noteEl) noteEl.textContent = 'Complete an assessment to see personalised notes.';
}

// ─── CHART 1: Score Trend Line ────────────────────────────────────────────────
// Data source: data.score_trend  (array, ASC by date)

function renderScoreTrendChart(scoreTrend) {
    const ctx = document.getElementById('moodChart');
    if (!ctx) return;

    const existing = Chart.getChart(ctx);
    if (existing) existing.destroy();

    if (!scoreTrend || !scoreTrend.length) {
        ctx.parentElement.innerHTML = '<p style="text-align:center;color:#9ca3af;font-size:13px;padding:40px 0;">No session data yet. Complete an assessment to see your trend.</p>';
        return;
    }

    const labels = scoreTrend.map(s => {
        const d = new Date(s.session_date);
        return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
    });

    new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Depression',
                    data: scoreTrend.map(s => s.depression_score),
                    borderColor: '#E89B9B',
                    backgroundColor: 'rgba(232,155,155,0.08)',
                    borderWidth: 3, tension: 0.4, fill: true,
                    pointRadius: 6, pointBackgroundColor: '#E89B9B',
                    pointBorderColor: '#fff', pointBorderWidth: 3
                },
                {
                    label: 'Anxiety',
                    data: scoreTrend.map(s => s.anxiety_score),
                    borderColor: '#cc8758',
                    backgroundColor: 'rgba(232,168,124,0.08)',
                    borderWidth: 3, tension: 0.4, fill: true,
                    pointRadius: 6, pointBackgroundColor: '#E8A87C',
                    pointBorderColor: '#fff', pointBorderWidth: 3
                },
                {
                    label: 'Stress',
                    data: scoreTrend.map(s => s.stress_score),
                    borderColor: '#5886ae',
                    backgroundColor: 'rgba(107,154,196,0.08)',
                    borderWidth: 3, tension: 0.4, fill: true,
                    pointRadius: 6, pointBackgroundColor: '#6B9AC4',
                    pointBorderColor: '#fff', pointBorderWidth: 3
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true, position: 'top' },
                tooltip: {
                    callbacks: {
                        afterBody: (items) => {
                            const s = scoreTrend[items[0].dataIndex];
                            return [
                                `Dep: ${s.depression_risk_level || '—'}`,
                                `Anx: ${s.anxiety_risk_level || '—'}`,
                                `Str: ${s.stress_risk_level || '—'}`,
                                s.overall_trend ? `Trend: ${s.overall_trend}` : ''
                            ].filter(Boolean);
                        }
                    }
                }
            },
            scales: {
                y: { beginAtZero: true, max: 63,
                     ticks: { font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 }, color: '#9AA5B9' } },
                x: { grid: { display: false },
                     ticks: { font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 }, color: '#9AA5B9' } }
            }
        }
    });
}

// ─── CHART 2: Facial Emotion Donut ───────────────────────────────────────────
// Data source: data.facial_emotions  (array with overall_dominant_emotion)

function renderFacialEmotionChart(facialEmotions) {
    const ctx = document.getElementById('emotionChart');
    if (!ctx) return;

    const existing = Chart.getChart(ctx);
    if (existing) existing.destroy();

    if (!facialEmotions || !facialEmotions.length) {
        ctx.parentElement.innerHTML = '<p style="text-align:center;color:#9ca3af;font-size:13px;padding:40px 0;">No facial emotion data yet.</p>';
        return;
    }

    const emotionCounts = {};
    facialEmotions.forEach(f => {
        const e = (f.overall_dominant_emotion || 'unknown').toLowerCase();
        emotionCounts[e] = (emotionCounts[e] || 0) + 1;
    });

    const EMOTION_COLORS = {
        angry: '#E89B9B', sad: '#6B9AC4', happy: '#7DBAA4',
        neutral: '#A89DD9', fear: '#E8A87C', surprise: '#F5C842',
        disgust: '#8B6F8B', unknown: '#C8CDD6'
    };

    const labels = Object.keys(emotionCounts);
    const values = Object.values(emotionCounts);
    const colors = labels.map(l => EMOTION_COLORS[l] || '#C8CDD6');

    new Chart(ctx, {
        type: 'doughnut',
        data: { labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 2 }] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom',
                    labels: { font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 } } }
            }
        }
    });
}

// ─── CHART 3: Feeling Scores Bar ──────────────────────────────────────────────
// Data source: data.feeling_scores  (single object from latest session)
// questionnaire_project_final_score = {"Sadness": 0.42, "Annoyance": 0.05, ...}

function renderFeelingScoresChart(data) {
    const canvas = document.getElementById('feelingChart');
    if (!canvas || !data.labels) return;

    const ctx = canvas.getContext('2d');
    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Score',
                data: data.values,
                backgroundColor: '#E8A87C', // Peach color from your sample image
                borderRadius: 4,
                barThickness: 12
            }]
        },
        options: {
            indexAxis: 'y', // Makes it a horizontal bar chart
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    beginAtZero: true,
                    max: 1, // Crucial for 0.0 - 1.0 range
                    grid: { display: false },
                    ticks: { color: '#9AA5B9', stepSize: 0.2 }
                },
                y: {
                    grid: { display: false },
                    ticks: {
                        color: '#4B5563',
                        font: { family: "'Plus Jakarta Sans', sans-serif", weight: '600' }
                    }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => `Intensity: ${context.parsed.x.toFixed(2)}`
                    }
                }
            }
        }
    });
}

// ─── SESSION LIST ─────────────────────────────────────────────────────────────
// Data source: data.sessions  (array DESC by date)

let globalSessions = []; // To store data for the modal

function renderSessionList(sessions) {
    globalSessions = sessions; 
    const container = document.querySelector('.sessions-list');
    if (!container) return;

    if (!sessions || !sessions.length) {
        container.innerHTML = '<p style="color:#9AA5B9;font-size:14px;padding:16px;">No sessions yet.</p>';
        return;
    }

    const RISK_CLASS = {
        minimal: 'low', mild: 'low', low: 'low',
        moderate: 'moderate',
        severe: 'high', high: 'high', extreme: 'high'
    };

    container.innerHTML = sessions.slice(0, 5).map((s, i) => {
        const date = new Date(s.finalized_at);
        const dateLabel = i === 0 ? 'Latest' : date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
        const timeLabel = date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
        
        const riskKey = (s.depression_risk_level || 'moderate').toLowerCase();
        const riskClass = RISK_CLASS[riskKey] || 'moderate';
        const trend = s.overall_trend || '—';
        const emotion = s.dominant_emotion ? s.dominant_emotion.charAt(0).toUpperCase() + s.dominant_emotion.slice(1) : '—';

        const trendTagClass = trend === 'improving' ? 'tag-success'
            : trend === 'worsening' ? 'tag-danger'
            : trend === 'no_data' ? 'tag-info'
            : 'tag-warning';

        const trendLabel = trend === 'no_data' ? 'First Session' : trend;

        // RESTORED ORIGINAL HTML STRUCTURE
        return `
        <div class="session-card ${i === 0 ? 'recent' : ''}" 
             onclick="openSessionReport(${i})" 
             style="cursor:pointer">
            <div class="session-date">
                <span class="session-day">${dateLabel}</span>
                <span class="session-time">${timeLabel}</span>
            </div>
            <div class="session-content">
                <h4 class="session-title">Mental Health Assessment</h4>
                <div class="session-tags">
                    <span class="tag tag-info">${emotion}</span>
                    <span class="tag ${trendTagClass}">${trendLabel}</span>
                </div>
                <div class="session-metrics">
                    <div class="session-metric">
                        <span class="metric-label">Depression:</span>
                        <span class="metric-badge ${riskClass}">${s.depression_score ?? '—'}</span>
                    </div>
                    <div class="session-metric">
                        <span class="metric-label">Anxiety:</span>
                        <span class="metric-badge">${s.anxiety_score ?? '—'}</span>
                    </div>
                    <div class="session-metric">
                        <span class="metric-label">Stress:</span>
                        <span class="metric-badge">${s.stress_score ?? '—'}</span>
                    </div>
                </div>
                ${s.emotional_summary ? `<p style="font-size:0.78rem;color:#697386;margin-top:6px;line-height:1.4;">${s.emotional_summary.substring(0, 90)}…</p>` : ''}
            </div>
            <div class="session-arrow">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M7.5 15L12.5 10L7.5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>
        </div>`;
    }).join('');
}

// function openSessionReport(index) {
//     const session = globalSessions[index];
//     const modal = document.getElementById('mseModal');
//     // Ensure this targets your modal's scrollable body
//     const modalBody = modal.querySelector('.modal-body');

//     if (session && session.report_html) {
//         modalBody.innerHTML = session.report_html;
//         modal.style.display = 'flex'; // Use flex if your CSS uses it for centering
//     } else {
//         console.error("Report HTML is missing in the data object:", session);
//         alert("Report content not found.");
//     }
// }
// Ensure you have a close function

// 1. The Core Counting Function
function incrementResourceCount() {
    const counterDisplay = document.getElementById('stat-resources');
    if (counterDisplay) {
        let currentCount = parseInt(counterDisplay.innerText) || 0;
        counterDisplay.innerText = currentCount + 1;
        
        // Visual Feedback
        counterDisplay.style.transition = "transform 0.2s ease";
        counterDisplay.style.transform = "scale(1.4)";
        setTimeout(() => { counterDisplay.style.transform = "scale(1)"; }, 200);
    }
}

// 2. Updated Session Report Opener
function openSessionReport(index) {
    const session = globalSessions[index];

    if (!session || !session.report_html) {
        alert("Report content not found.");
        return;
    }

    const newTab = window.open('', '_blank');
    newTab.document.open();
    newTab.document.write(session.report_html);
    newTab.document.close();
}

// 3. The Footer Download Button
function downloadReport() {
    window.print();
    incrementResourceCount();
}

function closeMSEReport() {
    document.getElementById('mseModal').style.display = 'none';
}


// ─── SUMMARY CARDS (Risk, Mood, Streak) ──────────────────────────────────────
// Data source: data.summary  (single object — latest session snapshot)

function renderSummaryCards(summary) {
    if (!summary || !Object.keys(summary).length) {
        // show empty state for metric cards
        _setText('risk-level-value', 'No data yet');
        _setText('risk-level-note', 'Complete an assessment to see results');
        _setText('current-mood-value', 'No data yet');
        _setText('current-mood-note', 'Complete an assessment to see results');
        return;
    }

    // ── Risk Assessment Card ──
    const risk = (summary.depression_risk_level || 'unknown').toLowerCase();
    const RISK_MAP = {
        minimal:  { label: 'Minimal Risk',  note: 'No immediate intervention needed',         color: '#4CAF50' },
        mild:     { label: 'Mild Risk',      note: 'Monitor and self-care recommended',         color: '#8BC34A' },
        low:      { label: 'Low Risk',       note: 'No immediate intervention needed',          color: '#8BC34A' },
        moderate: { label: 'Moderate Risk',  note: 'Consider seeking professional support',     color: '#FF9800' },
        severe:   { label: 'Severe Risk',    note: 'Immediate professional help recommended',   color: '#F44336' },
        normal:   { label: 'Healthy', note: 'Indicators are in a normal range', color: '#4CAF50' }, // ADD THIS LINE
        minimal:  { label: 'Minimal Risk',  note: 'No immediate intervention needed', color: '#4CAF50' },
        extreme:  { label: 'Extreme Risk',   note: 'Seek immediate professional help',          color: '#B71C1C' },
        high:     { label: 'High Risk',      note: 'Immediate professional help recommended',   color: '#F44336' },
    };
    const riskInfo = RISK_MAP[risk] || { label: 'No Data', note: 'Complete an assessment', color: '#9E9E9E' };

    _setText('risk-level-value', riskInfo.label);
    _setText('risk-level-note', riskInfo.note);

    const riskCard = document.querySelector('.risk-card');
    if (riskCard) {
        riskCard.classList.remove('low-risk', 'moderate-risk', 'high-risk');
        riskCard.classList.add(`${risk}-risk`);
        riskCard.style.borderLeftColor = riskInfo.color;
    }

    // ── Current Mood Card ──
    const emotion = (summary.dominant_emotion || '').toLowerCase();
    const MOOD_MAP = {
        angry:    { label: 'Angry',     note: 'High distress signals detected' },
        sad:      { label: 'Sad',       note: 'Low mood during your assessment' },
        fear:     { label: 'Anxious',   note: 'Signs of anxiety present' },
        disgust:  { label: 'Unsettled', note: 'Negative emotional state observed' },
        surprise: { label: 'Surprised', note: 'Mixed emotional response' },
        neutral:  { label: 'Neutral',   note: 'Calm emotional state during assessment' },
        happy:    { label: 'Positive',  note: 'Good emotional state during assessment' },
    };
    const moodInfo = MOOD_MAP[emotion] || {
        label: emotion ? (emotion.charAt(0).toUpperCase() + emotion.slice(1)) : 'No Data',
        note: 'Complete an assessment to see your mood'
    };

    _setText('current-mood-value', moodInfo.label);
    _setText('current-mood-note', `Last assessed: ${_relativeDate(summary.last_session_date)}`);
}

// ─── STAT CARDS (bottom row) ──────────────────────────────────────────────────
// Data source: data.stats  (object with counts)

function renderStatCards(stats) {
    if (!stats) return;

    // Sessions Completed
    _setText('stat-sessions', stats.total_sessions ?? '0');

    // Resources Downloaded
    _setText('stat-resources', stats.total_downloads ?? '0');

    // Days Active
    _setText('stat-days', stats.days_active ?? '0');

    // Streak card (in metrics-grid)
    const streak = stats.streak_days || 0;
    _setText('streak-value', streak === 1 ? '1 day' : `${streak} days`);
    _setText('streak-note', streak > 0
        ? 'Keep up the consistency!'
        : 'Complete your first session to start a streak.');
}

// ─── WELLNESS BARS ────────────────────────────────────────────────────────────
// Data source: data.wellness
// { depression_wellness: 55.6, anxiety_wellness: 58.7, stress_wellness: 45.0,
//   depression_score: 28, anxiety_score: 26, stress_score: 22 }
// Lower raw score = better wellness (inverted percentages)

// ─── WELLNESS BARS (FIXED) ────────────────────────────────────────────────────────────

function renderWellnessBars(wellness) {
    if (!wellness) return;

    const scales = [
        { key: 'depression_wellness', label: 'Depression',  color: '#E89B9B' },
        { key: 'anxiety_wellness',    label: 'Anxiety',     color: '#E8A87C' },
        { key: 'stress_wellness',     label: 'Stress',      color: '#6B9AC4' },
    ];

    const items = document.querySelectorAll('.wellness-breakdown .wellness-item');

    scales.forEach((s, i) => {
        const item = items[i];
        if (!item) return;

        const pct = wellness[s.key];
        if (pct === null || pct === undefined) {
            item.querySelector('.wellness-value').textContent = '—';
            return;
        }

        // 1. Update text immediately
        const valueEl = item.querySelector('.wellness-value');
        if (valueEl) valueEl.textContent = `${pct}%`;

        // 2. Animate the bar width
        const bar = item.querySelector('.wellness-bar');
        if (bar) {
            bar.style.background = s.color;
            // Force a slight delay so the browser registers the 0% start point for the transition
            bar.style.width = '0%'; 
            setTimeout(() => {
                bar.style.width = `${pct}%`;
            }, 100 + (i * 100)); // Staggered animation
        }

        item.style.display = '';
    });
}

// Remove or empty this function so it doesn't conflict with the new logic
function animateWellnessBars() {
    // Logic moved inside renderWellnessBars to ensure it triggers after Fetch
}

// ─── RECOMMENDATIONS ──────────────────────────────────────────────────────────
// Data source: data.recommendations  (single object with recommendations_json)
//              data.sessions[0]      (for comparison_summary)

// ─── RECOMMENDATIONS (HARDENED v2) ───────────────────────────────────────────
// Replace the entire renderRecommendations function in dashboard.js with this.
// Handles: recommendations_json as object, as JSON string, flat shape, null.

function renderRecommendations(recommendations, sessions) {
    const recContainer = document.getElementById('recommendations-list');
    const noteEl       = document.querySelector('.panel-note');

    // ── DEBUG: remove after confirming it works ───────────────────────────────
    console.log('🔍 renderRecommendations called with:', recommendations);

    // ── 1. Comparison summary → footer note ──────────────────────────────────
    const summary = recommendations?.comparison_summary
        || sessions?.[0]?.comparison_summary
        || null;

    if (noteEl && summary) {
        noteEl.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style="flex-shrink:0;margin-top:2px">
                <circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="2"/>
                <path d="M8 4v4M8 10h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            <span>${summary}</span>`;
    }

    if (!recContainer) return;

    // ── 2. Extract + parse recommendations_json ───────────────────────────────
    let recs = null;

    if (recommendations) {
        // Case A: { recommendations_json: "{...}" }  ← DB stores it as string
        // Case B: { recommendations_json: {...} }    ← already parsed object
        // Case C: { depression: {...}, anxiety: {...}, stress: {...} } ← flat
        // Case D: recommendations IS the recs object directly

        let raw = recommendations.recommendations_json ?? recommendations;

        // If it's a string, parse it
        if (typeof raw === 'string') {
            try { raw = JSON.parse(raw); } catch(e) {
                console.error('❌ Failed to parse recommendations_json string:', e);
                raw = null;
            }
        }

        // Now check if it has at least one of our scale keys
        if (raw && typeof raw === 'object' && (raw.depression || raw.anxiety || raw.stress)) {
            recs = raw;
        }
    }

    console.log('🔍 Parsed recs object:', recs);

    if (!recs) {
        recContainer.innerHTML = '<p class="rec-empty">Complete an assessment to see recommendations.</p>';
        return;
    }

    // ── 3. Config ─────────────────────────────────────────────────────────────
    const SCALES = [
        {
            key: 'depression', label: 'Depression', color: '#E89B9B', bg: 'rgba(232,155,155,0.08)',
            icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                     <circle cx="12" cy="12" r="10"/>
                     <path d="M8 15s1.5-2 4-2 4 2 4 2"/>
                     <circle cx="9" cy="9" r="1" fill="currentColor"/>
                     <circle cx="15" cy="9" r="1" fill="currentColor"/>
                   </svg>`
        },
        {
            key: 'anxiety', label: 'Anxiety', color: '#E8A87C', bg: 'rgba(232,168,124,0.08)',
            icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                     <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                   </svg>`
        },
        {
            key: 'stress', label: 'Stress', color: '#6B9AC4', bg: 'rgba(107,154,196,0.08)',
            icon: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                     <circle cx="12" cy="12" r="10"/>
                     <path d="M12 6v6l4 2"/>
                   </svg>`
        }
    ];

    const LEVEL_BADGE = {
        minimal:  { label: 'Minimal',  cls: 'lvl-low' },
        mild:     { label: 'Mild',     cls: 'lvl-low' },
        low:      { label: 'Low',      cls: 'lvl-low' },
        moderate: { label: 'Moderate', cls: 'lvl-moderate' },
        mixed:    { label: 'Mixed',    cls: 'lvl-moderate' },
        severe:   { label: 'Severe',   cls: 'lvl-high' },
        high:     { label: 'High',     cls: 'lvl-high' },
        extreme:  { label: 'Extreme',  cls: 'lvl-extreme' },
    };

    // ── 4. Build cards ────────────────────────────────────────────────────────
    let html = '';

    SCALES.forEach(scale => {
        const block = recs[scale.key];
        if (!block) return;

        // tips can be: block itself if array, block.tips, block.recommendations, block.suggestions
        let tips = [];
        if (Array.isArray(block))              tips = block;
        else if (Array.isArray(block.tips))          tips = block.tips;
        else if (Array.isArray(block.recommendations)) tips = block.recommendations;
        else if (Array.isArray(block.suggestions))    tips = block.suggestions;

        const level = (block.level || block.severity || block.risk_level || 'moderate').toLowerCase();
        const badge = LEVEL_BADGE[level] || { label: 'Moderate', cls: 'lvl-moderate' };

        if (!tips.length) return;

        html += `
        <div class="rec-scale-block" style="--scale-color:${scale.color}; --scale-bg:${scale.bg};">
            <div class="rec-scale-header">
                <span class="rec-scale-icon" style="color:${scale.color}">${scale.icon}</span>
                <span class="rec-scale-label">${scale.label}</span>
                <span class="rec-level-badge ${badge.cls}">${badge.label}</span>
            </div>
            <ul class="rec-tips-list">
                ${tips.map(tip => `
                <li class="rec-tip-item">
                    <span class="rec-tip-dot" style="background:${scale.color}"></span>
                    <span>${tip}</span>
                </li>`).join('')}
            </ul>
        </div>`;
    });

    recContainer.innerHTML = html || '<p class="rec-empty">No recommendations available yet.</p>';
}

// ─── HELPERS ──────────────────────────────────────────────────────────────────

function _setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function _relativeDate(isoString) {
    if (!isoString) return 'unknown';
    const d = new Date(isoString);
    const diffMs = Date.now() - d.getTime();
    const diffDays = Math.floor(diffMs / 86400000);
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7)  return `${diffDays} days ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

// ─── UI INTERACTIONS ─────────────────────────────────────────────────────────

function initializeCircularProgress() {
    const progressElement = document.querySelector('.circular-progress');
    if (!progressElement) return;
    const progress = parseInt(progressElement.dataset.progress) || 0;
    _reinitCircularProgress(progressElement, progress);
}

function _reinitCircularProgress(el, progress) {
    const circle = el.querySelector('.progress-ring-fill');
    if (!circle) return;
    const radius = 60;
    const circumference = 2 * Math.PI * radius;
    circle.style.strokeDasharray = `${circumference} ${circumference}`;
    circle.style.strokeDashoffset = circumference;
    setTimeout(() => {
        circle.style.strokeDashoffset = circumference - (progress / 100) * circumference;
    }, 150);
}

function animateWellnessBars() {
    const bars = document.querySelectorAll('.wellness-bar');
    bars.forEach((bar, i) => {
        const width = bar.style.width;
        bar.style.width = '0%';
        setTimeout(() => { bar.style.width = width; }, 200 + i * 100);
    });
}

function showMSEReport(sessionId) {
    const modal = document.getElementById('mseModal');
    if (modal) { modal.classList.add('show'); document.body.style.overflow = 'hidden'; }
}

function closeMSEReport() {
    const modal = document.getElementById('mseModal');
    if (modal) {
        modal.style.display = 'none';
        // Optional: clear content so it doesn't "flash" next time
        document.querySelector('#mseModal .modal-body').innerHTML = '';
    }
}

function initModalHandlers() {
    const modal = document.getElementById('mseModal');
    if (modal) modal.addEventListener('click', e => { if (e.target === modal) closeMSEReport(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMSEReport(); });
}

function showEmergencyResources() {
    const modal = document.getElementById('supportModal');
    modal.style.display = 'flex'; // Shows the modal
}

function closeSupportModal() {
    const modal = document.getElementById('supportModal');
    modal.style.display = 'none'; // Hides the modal
}

// Optional: Close modal if user clicks outside of the box
window.onclick = function(event) {
    const modal = document.getElementById('supportModal');
    if (event.target == modal) {
        modal.style.display = "none";
    }
}

function initNavHandlers() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            if (href && href.startsWith('#')) {
                e.preventDefault();
                const target = document.querySelector(href);
                if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
            this.classList.add('active');
        });
    });
}

function autoDismissAlert() {
    setTimeout(() => {
        const alertEl = document.querySelector('.alert-banner');
        if (!alertEl) return;
        alertEl.style.transition = 'opacity 0.3s, transform 0.3s';
        alertEl.style.opacity = '0';
        alertEl.style.transform = 'translateY(-10px)';
        setTimeout(() => alertEl.remove(), 300);
    }, 5000);
}

// Add this to your event listeners or init block
function initChartFilters() {
    const filterSelect = document.getElementById('chartTimeFilter'); // Ensure this ID matches your HTML
    if (!filterSelect) return;

    filterSelect.addEventListener('change', function(e) {
        const days = parseInt(e.target.value);
        if (!analyticsData || !analyticsData.score_trend) return;

        // Filter the global data
        const filteredTrend = filterDataByDays(analyticsData.score_trend, days);
        
        // Re-render only the trend chart
        renderScoreTrendChart(filteredTrend);
    });
}

function filterDataByDays(data, days) {
    if (days === 0) return data; // "All Time" option

    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);

    return data.filter(item => {
        const sessionDate = new Date(item.session_date);
        return sessionDate >= cutoff;
    });
}
