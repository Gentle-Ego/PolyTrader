let ws=null,eqChart=null,selBot=null,compareVis=false,configVis=false,hoursVis=false,mktStatsVis=false;
const F=(v,d=2)=>v!=null?Number(v).toFixed(d):'—';
const $=id=>document.getElementById(id);
const U=v=>v!=null?'$'+Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
const P=v=>v!=null?Number(v).toFixed(4)+'%':'—';
const T=s=>{if(s==null)return'—';s=Math.max(0,Math.floor(s));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');};
const TS=t=>t?new Date(t*1000).toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—';
const TD=t=>t?new Date(t*1000).toLocaleDateString('en-US',{month:'short',day:'numeric'})+' '+TS(t):'—';
const DC=v=>v==null?'':v>0?'up':v<0?'down':'';
const E=s=>{const d=document.createElement('div');d.textContent=s;return d.innerHTML;};
const nN=id=>{const v=$(id).value.trim();return v===''?null:parseFloat(v);};
const iN=id=>{const v=$(id).value.trim();return v===''?null:parseInt(v);};

let _allBots = [];

function fmtBytes(b) {
    if (b < 1024) return b + ' B';
    if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
    if (b < 1073741824) return (b / 1048576).toFixed(1) + ' MB';
    return (b / 1073741824).toFixed(2) + ' GB';
}
function fmtUptime(s) {
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (d > 0) return `${d}d ${h}h ${m}m`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}
function updateSystemStats(stats) {
    if (!stats) return;
    $('stat-db-size').textContent = fmtBytes(stats.db_size_bytes || 0);
    $('stat-snapshots').textContent = (stats.total_snapshots || 0).toLocaleString();
    $('stat-results').textContent = (stats.total_results || 0).toLocaleString();
    $('stat-uptime').textContent = fmtUptime(stats.uptime_seconds || 0);
}
let liveChart5m=null, liveChart15m=null;

function initLiveChart(ctxId, titleColor) {
    const ctx = $(ctxId).getContext('2d');
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                { label: 'Delta %', data: [], borderColor: titleColor, yAxisID: 'y', borderWidth: 2, tension: 0.2, pointRadius: 0 },
                { label: 'Ask UP', data: [], borderColor: '#eab308', yAxisID: 'y1', borderWidth: 2, borderDash: [5, 5], tension: 0.2, pointRadius: 0 }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            animation: { duration: 0 },
            plugins: { legend: { display: true, labels: { color: 'rgba(255,255,255,0.7)', font: { size: 10 } } } },
            scales: {
                x: { display: false },
                y: { type: 'linear', display: true, position: 'left', grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b', font: { size: 9 } } },
                y1: { type: 'linear', display: true, position: 'right', grid: { drawOnChartArea: false }, ticks: { color: '#eab308', font: { size: 9 }, callback: v => v.toFixed(2) } }
            }
        }
    });
}

function updateLiveChart(chart, snapshot) {
    if (!chart || !snapshot) return;
    const now = new Date().toLocaleTimeString('en-US', {hour12: false});
    chart.data.labels.push(now);
    chart.data.datasets[0].data.push(snapshot.delta_pct);
    chart.data.datasets[1].data.push(snapshot.ask_up);
    if (chart.data.labels.length > 60) {
        chart.data.labels.shift();
        chart.data.datasets[0].data.shift();
        chart.data.datasets[1].data.shift();
    }
    chart.update();
}

function connectWS(){
    const p=location.protocol==='https:'?'wss':'ws';
    ws=new WebSocket(`${p}://${location.host}/ws`);
    ws.onopen=()=>{
        $('ws-dot').style.background='var(--green)';$('ws-status').textContent='Live';
        if (!liveChart5m) liveChart5m = initLiveChart('live-chart-5m', '#ef4444');
        if (!liveChart15m) liveChart15m = initLiveChart('live-chart-15m', '#a855f7');
        // Seed charts from stored snapshots on connect/reconnect
        seedLiveCharts();
    };
    ws.onclose=()=>{$('ws-dot').style.background='var(--red)';$('ws-status').textContent='Reconnecting…';setTimeout(connectWS,3000);};
    ws.onerror=()=>ws.close();
    ws.onmessage=e=>{
        const d=JSON.parse(e.data);
        uP('5m',d['5m']); updateLiveChart(liveChart5m, d['5m']);
        uP('15m',d['15m']); updateLiveChart(liveChart15m, d['15m']);
        if(d.bots)uBL(d.bots);
        if(d.server_time)$('server-time').textContent=new Date(d.server_time*1000).toLocaleTimeString();
        if(d.system_stats) updateSystemStats(d.system_stats);
    };
}

async function seedLiveCharts() {
    try {
        const [data5m, data15m] = await Promise.all([
            fetch('/api/snapshots/recent/5m?limit=60').then(r=>r.json()),
            fetch('/api/snapshots/recent/15m?limit=60').then(r=>r.json()),
        ]);
        if (liveChart5m && data5m.length) {
            for (const s of data5m) {
                const t = new Date(s.ts * 1000).toLocaleTimeString('en-US', {hour12: false});
                liveChart5m.data.labels.push(t);
                liveChart5m.data.datasets[0].data.push(s.delta_pct);
                liveChart5m.data.datasets[1].data.push(s.ask_up);
            }
            liveChart5m.update();
        }
        if (liveChart15m && data15m.length) {
            for (const s of data15m) {
                const t = new Date(s.ts * 1000).toLocaleTimeString('en-US', {hour12: false});
                liveChart15m.data.labels.push(t);
                liveChart15m.data.datasets[0].data.push(s.delta_pct);
                liveChart15m.data.datasets[1].data.push(s.ask_up);
            }
            liveChart15m.update();
        }
    } catch(e) { console.warn('Could not seed live charts:', e); }
}

function uP(t,s){if(!s)return;const set=(id,v)=>{const e=$(id);if(e)e.textContent=v;};const cls=(id,c)=>{const e=$(id);if(e)e.className='value '+c;};
set(`btc-${t}`,U(s.btc_price));set(`target-${t}`,U(s.target_price));
set(`delta-${t}`,P(s.delta_pct));cls(`delta-${t}`,DC(s.delta_pct));
set(`vel-${t}`,s.delta_velocity!=null?s.delta_velocity.toFixed(6)+'/s':'—');cls(`vel-${t}`,DC(s.delta_velocity));
set(`vol-${t}`,s.volatility_20s!=null?s.volatility_20s.toFixed(4):'—');
set(`askup-${t}`,F(s.ask_up));set(`sprup-${t}`,s.spread_up!=null?F(s.spread_up,3):'—');
set(`time-${t}`,T(s.time_remaining_s));
const bar=$(`bar-${t}`);if(bar)bar.style.width=(s.time_remaining_s/(t==='5m'?300:900))*100+'%';}

function uBL(bots){
    // Sort: active first, then paused, then disabled
    bots.sort((a,b) => {
        const sa = a.paused_reason ? 1 : a.enabled ? 0 : 2;
        const sb = b.paused_reason ? 1 : b.enabled ? 0 : 2;
        if (sa !== sb) return sa - sb;
        return (b.net_pnl || 0) - (a.net_pnl || 0);
    });
    _allBots = bots;
    renderBotList();
    if(compareVis)loadCmp();
}

function filterBots() { renderBotList(); }

function renderBotList() {
    const q = ($('bot-search') ? $('bot-search').value : '').toLowerCase();
    const filtered = q ? _allBots.filter(b => b.name.toLowerCase().includes(q)) : _allBots;
    const c=$('bot-list');
    if(!filtered.length){
        c.innerHTML='<div style="color:var(--text-dim);text-align:center;padding:30px">' + (q ? 'No bots match "'+E(q)+'"' : 'No bots — click + New Bot') + '</div>';
        return;
    }
    c.innerHTML=filtered.map(b=>{const tc=b.paused_reason?'paused':b.enabled?'on':'off';const tt=b.paused_reason?'⚠ PAUSED':b.enabled?'ON':'OFF';
    return`<div class="bot-card" onclick="showD('${b.bot_id}')"><div><div class="bot-name">${E(b.name)}</div><div class="bot-sub"><span class="tag ${tc}">${tt}</span>${b.paused_reason?`<span style="font-size:8px;color:var(--orange);margin-left:3px">${E(b.paused_reason)}</span>`:''}</div></div>
    <div class="bot-stat"><div class="num" style="color:${b.net_pnl>=0?'var(--green)':'var(--red)'}">${b.net_pnl>=0?'+':''}${F(b.net_pnl,4)}</div><div class="lbl">PnL</div></div>
    <div class="bot-stat"><div class="num">${U(b.balance)}</div><div class="lbl">Bal</div></div>
    <div class="bot-stat"><div class="num">${b.total_orders}</div><div class="lbl">Ord</div></div>
    <div class="bot-stat"><div class="num">${b.wins}/${b.losses}</div><div class="lbl">W/L</div></div>
    <div class="bot-stat"><div class="num" style="color:${b.win_rate>=50?'var(--green)':'var(--red)'}">${F(b.win_rate,1)}%</div><div class="lbl">WR</div></div>
    <div class="bot-stat"><div class="num">${F(b.sharpe_ratio,2)}</div><div class="lbl">Sharpe</div></div>
    <div class="bot-stat"><div class="num" style="color:${b.current_streak>=0?'var(--green)':'var(--red)'}">${b.current_streak>=0?'+':''}${b.current_streak}</div><div class="lbl">Streak</div></div>
    <div class="bot-actions" onclick="event.stopPropagation()"><button class="btn-sm btn-ghost" onclick="toggleBot('${b.bot_id}')">${b.enabled?'⏸':'▶'}</button><button class="btn-sm btn-danger" onclick="deleteBot('${b.bot_id}')">✕</button></div></div>`;}).join('');
}

async function showD(id){selBot=id;configVis=false;hoursVis=false;$('config-panel').style.display='none';$('hours-panel').style.display='none';$('bot-detail-panel').style.display='block';
const[st,eq,od]=await Promise.all([fetch(`/api/bots/${id}/stats`).then(r=>r.json()),fetch(`/api/bots/${id}/equity`).then(r=>r.json()),fetch(`/api/bots/${id}/orders?limit=200`).then(r=>r.json())]);
$('detail-title').textContent=`📈 ${st.name}`;$('btn-reset').style.display=st.paused_reason?'inline-block':'none';
if(st.config)$('config-panel').textContent=JSON.stringify(st.config,null,2);
$('detail-stats').innerHTML=`
<div class="metric"><div class="label">Started</div><div class="value" style="font-size:10px">${TD(st.started_at)}</div></div>
<div class="metric"><div class="label">Balance</div><div class="value neutral">${U(st.balance)}</div></div>
<div class="metric"><div class="label">Peak</div><div class="value">${U(st.peak_balance)}</div></div>
<div class="metric"><div class="label">PnL</div><div class="value ${st.net_pnl>=0?'up':'down'}">${st.net_pnl>=0?'+':''}${F(st.net_pnl,4)}</div></div>
<div class="metric"><div class="label">ROI</div><div class="value ${st.roi_pct>=0?'up':'down'}">${F(st.roi_pct,2)}%</div></div>
<div class="metric"><div class="label">WR</div><div class="value">${F(st.win_rate,1)}%</div></div>
<div class="metric"><div class="label">PF</div><div class="value">${F(st.profit_factor,2)}</div></div>
<div class="metric"><div class="label">Sharpe</div><div class="value">${F(st.sharpe_ratio,3)}</div></div>
<div class="metric"><div class="label">MaxDD</div><div class="value down">${F(st.max_drawdown_pct,2)}%</div></div>
<div class="metric"><div class="label">Expect.</div><div class="value ${st.expectancy>=0?'up':'down'}">${F(st.expectancy,4)}</div></div>
<div class="metric"><div class="label">AvgW</div><div class="value up">+${F(st.avg_win,4)}</div></div>
<div class="metric"><div class="label">AvgL</div><div class="value down">-${F(st.avg_loss,4)}</div></div>
<div class="metric"><div class="label">Fees</div><div class="value" style="color:var(--red)">${F(st.total_fees,4)}</div></div>
<div class="metric"><div class="label">Best</div><div class="value up">+${st.best_streak}</div></div>
<div class="metric"><div class="label">Worst</div><div class="value down">${st.worst_streak}</div></div>
<div class="metric"><div class="label">Today</div><div class="value">${st.orders_today}ord</div></div>`;
rEq(eq);
$('detail-orders').innerHTML=od.map(o=>{const sc=o.status==='WIN'?'win':o.status==='LOSS'?'loss':o.status==='EARLY_EXIT'?'exit':o.status==='EXPIRED'?'expired':'pending';
return`<tr><td>${TS(o.ts_signal)}</td><td>${o.market_type}</td><td style="color:${o.side==='UP'?'var(--green)':'var(--red)'}">${o.side}</td><td>${F(o.entry_price,4)}</td><td>${o.exit_price?F(o.exit_price,4):'—'}</td><td>${F(o.shares,0)}</td><td>${F(o.cost,4)}</td><td>${F(o.fee+(o.exit_fee||0),4)}</td><td style="color:${o.pnl>=0?'var(--green)':'var(--red)'}">${o.pnl>=0?'+':''}${F(o.pnl,4)}</td><td><span class="result-chip ${sc}">${o.status}</span></td><td style="font-size:9px;color:var(--text-dim)">${F(o.signal_delta,3)}%</td><td style="font-size:9px">${F(o.signal_velocity,5)}</td></tr>`;}).join('');}

function closeBotDetail(){$('bot-detail-panel').style.display='none';selBot=null;}
async function resetPause(){if(!selBot)return;await fetch(`/api/bots/${selBot}/reset-pause`,{method:'PATCH'});showD(selBot);}
function toggleConfig(){configVis=!configVis;$('config-panel').style.display=configVis?'block':'none';}

function rEq(data){const ctx=$('equity-chart').getContext('2d');if(eqChart)eqChart.destroy();
// Calculate rolling win rate from actual pnl values
let wins=0, resolved=0;
const rollingWR = data.map((p,i) => {
    if(i === 0) return null; // skip initial balance point
    resolved++;
    if(p.pnl > 0) wins++;
    return (wins / resolved) * 100;
});
eqChart=new Chart(ctx,{
    type:'line',
    data:{
        labels:data.map(p=>TS(p.ts)),
        datasets:[
            {label:'Balance',data:data.map(p=>p.balance),borderColor:'#3b82f6',backgroundColor:c=>{const g=c.chart.ctx.createLinearGradient(0,0,0,200);g.addColorStop(0,'rgba(59,130,246,.2)');g.addColorStop(1,'rgba(59,130,246,0)');return g;},fill:true,tension:0.3,pointRadius:0,borderWidth:2, yAxisID: 'y'},
            {label:'Win Rate %',data:rollingWR,borderColor:'#22c55e',borderDash:[4,4],tension:0.3,pointRadius:0,borderWidth:1.5, yAxisID: 'y1'}
        ]
    },
    options:{
        responsive:true,maintainAspectRatio:false,
        interaction: {mode: 'index', intersect: false},
        plugins:{legend:{display:true, labels: {color: 'rgba(255,255,255,0.7)', font: {size: 10}}}},
        scales:{
            x:{display:false},
            y:{position:'left',ticks:{color:'#64748b',font:{size:9}},grid:{color:'rgba(30,41,59,.5)'}},
            y1:{position:'right',min:0,max:100,ticks:{color:'#22c55e',font:{size:9},stepSize:25},grid:{drawOnChartArea:false}}
        }
    }
});}

// ── Hours analysis ──────────────────────────────────────────────
async function showHours(){if(!selBot)return;hoursVis=!hoursVis;$('hours-panel').style.display=hoursVis?'block':'none';
if(!hoursVis)return;const d=await fetch(`/api/analytics/bot-hours/${selBot}`).then(r=>r.json());
$('hours-grid').innerHTML=Object.entries(d).map(([h,v])=>`<div class="metric"><div class="label">${h}:00</div><div class="value ${v.win_rate>=50?'up':v.trades?'down':''}" style="font-size:12px">${v.trades?F(v.win_rate,0)+'%':'—'}</div><div style="font-size:9px;color:var(--text-dim)">${v.trades}t ${v.pnl>=0?'+':''}${F(v.pnl,3)}</div></div>`).join('');}

// ── Clone / Export ──────────────────────────────────────────────
async function cloneBot(){if(!selBot)return;const n=prompt('Name for clone:');if(!n)return;await fetch(`/api/bots/${selBot}/clone?name=${encodeURIComponent(n)}`,{method:'POST'});}
function exportCSV(){if(!selBot)return;window.open(`/api/export/orders/${selBot}`);}

// ── Leaderboard ─────────────────────────────────────────────────
async function loadCmp(){const d=await fetch('/api/analytics/comparison').then(r=>r.json());
$('compare-body').innerHTML=d.map((b,i)=>`<tr><td class="rank">${i+1}</td><td>${E(b.name)}</td><td style="color:${b.net_pnl>=0?'var(--green)':'var(--red)'}">${b.net_pnl>=0?'+':''}${F(b.net_pnl,4)}</td><td>${F(b.roi_pct,2)}%</td><td>${F(b.win_rate,1)}%</td><td>${F(b.profit_factor,2)}</td><td>${F(b.sharpe_ratio,3)}</td><td style="color:var(--red)">${F(b.max_drawdown_pct,2)}%</td><td>${F(b.expectancy,4)}</td><td>${b.total_orders}</td></tr>`).join('');}
function toggleCompare(){compareVis=!compareVis;$('compare-panel').style.display=compareVis?'block':'none';if(compareVis)loadCmp();}

let historyChart=null;
// ── Market stats ────────────────────────────────────────────────
async function toggleMktStats(){mktStatsVis=!mktStatsVis;$('mkt-stats-panel').style.display=mktStatsVis?'block':'none';
if(!mktStatsVis)return;
const[ms,corr]=await Promise.all([fetch('/api/analytics/market-stats').then(r=>r.json()),fetch('/api/analytics/correlations?market_type=5m').then(r=>r.json())]);
$('mkt-stats-grid').innerHTML=`
<div class="metric"><div class="label">Total Resolved</div><div class="value">${ms.total}</div></div>
<div class="metric"><div class="label">UP %</div><div class="value up">${ms.up_pct}%</div></div>
<div class="metric"><div class="label">DOWN %</div><div class="value down">${ms.down_pct}%</div></div>
<div class="metric"><div class="label">Avg Δ</div><div class="value">${F(ms.avg_delta,4)}%</div></div>
<div class="metric"><div class="label">Std Δ</div><div class="value">${F(ms.std_delta,4)}%</div></div>`;

const corrHTML = Object.entries(corr).map(([k,v])=>`<div class="metric"><div class="label" style="font-size:8px">${k.replace(/_/g,' ')}</div><div class="value ${v.up_win_pct>=55?'up':v.up_win_pct<=45?'down':''}" style="font-size:13px">${v.total?v.up_win_pct+'%':'—'}</div><div style="font-size:9px;color:var(--text-dim)">n=${v.total}</div></div>`).join('');
$('corr-grid').innerHTML=corrHTML;

const ctxH = $('history-chart').getContext('2d');
if(historyChart) historyChart.destroy();
const labels = Object.keys(corr).map(k=>k.replace(/_/g,' '));
const data = Object.values(corr).map(v=>v.total?v.up_win_pct:0);
const colors = data.map(v=>v>=55?'#22c55e':v<=45?'#ef4444':'#3b82f6');
historyChart = new Chart(ctxH, {
    type: 'bar',
    data: {
        labels: labels,
        datasets: [{ label: 'UP Win Rate %', data: data, backgroundColor: colors, borderRadius: 4 }]
    },
    options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
            x: { ticks: { color: '#64748b', font: { size: 9 }, maxRotation: 45, minRotation: 45 }, grid: { display: false } },
            y: { min: 0, max: 100, ticks: { color: '#64748b', font: { size: 9 }, stepSize: 20 }, grid: { color: 'rgba(30,41,59,.5)' } }
        }
    }
});
}

// ── Create bot ───────────────────────────────────────────────────
function openCreateModal(){$('create-modal').classList.add('active');}
function closeCreateModal(){$('create-modal').classList.remove('active');}
async function submitBot(){const b={name:$('f-name').value,side:$('f-side').value,market_type:$('f-market').value,
min_entry_time_s:nN('f-min-entry')||0,max_entry_time_s:nN('f-max-entry')||120,
delta_pct_min:nN('f-dmin'),delta_pct_max:nN('f-dmax'),delta_velocity_min:nN('f-vmin'),delta_velocity_max:nN('f-vmax'),
volatility_min:nN('f-volmin'),volatility_max:nN('f-volmax'),
ask_up_min:nN('f-aum'),ask_up_max:nN('f-aux'),ask_down_min:nN('f-adm'),ask_down_max:nN('f-adx'),
spread_max:nN('f-sprmax'),session_start_utc:iN('f-sess-s'),session_end_utc:iN('f-sess-e'),
fill_delay_s:nN('f-fd'),taker_fee_pct:nN('f-fee')||2,slippage_pct:nN('f-slip')||0,
shares_per_order:nN('f-sh')||1,multiple_orders:$('f-multi').value==='true',cooldown_s:nN('f-cd')||30,
max_orders_per_round:iN('f-mr')||1,max_open_orders:iN('f-mo')||5,
streak_scaling:$('f-ss').value==='true',streak_win_bonus:nN('f-swb')||0,streak_loss_reduce:nN('f-slr')||0,max_shares:nN('f-maxsh')||10,
balance:nN('f-bal')||100,max_daily_loss:nN('f-mdl'),max_drawdown_pct:nN('f-mdd'),
max_consecutive_losses:iN('f-mcl'),daily_order_limit:iN('f-dl'),max_exposure:nN('f-mex'),
auto_disable_after:iN('f-ada'),auto_disable_if_roi_below:nN('f-adr'),
enable_early_exit:$('f-ee').value==='true',take_profit_bid:nN('f-tp'),stop_loss_bid:nN('f-sl')};
const r=await fetch('/api/bots',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
const d=await r.json();if(d.ok)closeCreateModal();else alert(JSON.stringify(d));}

async function toggleBot(id){await fetch(`/api/bots/${id}/toggle`,{method:'PATCH'});}
async function deleteBot(id){if(!confirm('Delete?'))return;await fetch(`/api/bots/${id}`,{method:'DELETE'});if(selBot===id)closeBotDetail();}

// ── Optimizer ────────────────────────────────────────────────────
function openOptimizer(){$('opt-modal').classList.add('active');$('opt-results').style.display='none';}
function closeOptimizer(){$('opt-modal').classList.remove('active');}

function parseRange(id){const v=$(id).value.trim();if(!v)return null;
const parts=v.split(',').map(s=>parseFloat(s.trim()));
if(parts.length===3)return{min_val:parts[0],max_val:parts[1],step:parts[2]};
return{values:parts};}

async function runOptimizer(){
    const ranges=[];
    const add=(field,id,isInt=false)=>{const r=parseRange(id);if(r){r.field=field;r.is_int=isInt;ranges.push(r);}};
    add('delta_pct_min','o-dmin');add('ask_up_min','o-aumin');add('ask_up_max','o-aumax');
    add('max_entry_time_s','o-met');add('min_entry_time_s','o-miet');add('spread_max','o-spr');

    const body={
        base_config:{side:$('o-side').value,market_type:$('o-mkt').value,balance:100,fill_delay_s:1,taker_fee_pct:2},
        ranges,method:$('o-method').value,max_combinations:iN('o-max')||100,rank_by:$('o-rank').value,min_orders:iN('o-minord')||5};
    $('opt-summary').textContent='Running…';$('opt-results').style.display='block';$('opt-body').innerHTML='';
    const r=await fetch('/api/optimizer/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    if(d.error){$('opt-summary').textContent=d.error;return;}
    $('opt-summary').textContent=`Tested ${d.total_tested} configs → ${d.total_passed} passed (${d.duration_ms}ms)`;
    $('opt-body').innerHTML=(d.results||[]).map((r,i)=>{
        const kp=Object.entries(r.config).filter(([k])=>['delta_pct_min','ask_up_min','ask_up_max','max_entry_time_s','min_entry_time_s','spread_max'].includes(k)).map(([k,v])=>`${k.replace(/_/g,'').slice(0,8)}=${v}`).join(' ');
        return`<tr><td>${i+1}</td><td style="color:${r.net_pnl>=0?'var(--green)':'var(--red)'}">${r.net_pnl>=0?'+':''}${F(r.net_pnl,4)}</td><td>${F(r.roi_pct,2)}%</td><td>${F(r.win_rate,1)}%</td><td>${F(r.profit_factor,2)}</td><td>${F(r.sharpe_ratio,3)}</td><td>${F(r.max_drawdown_pct,1)}%</td><td>${F(r.expectancy,4)}</td><td>${r.total_orders}</td><td style="font-size:9px;color:var(--text-dim)">${kp}</td><td><button class="btn-sm btn-primary" onclick='promoteOpt(${JSON.stringify(r.config).replace(/'/g,"&#39;")})'>Deploy</button></td></tr>`;}).join('');}

async function promoteOpt(config){const n=prompt('Bot name:','Optimized');if(!n)return;
await fetch(`/api/optimizer/promote?name=${encodeURIComponent(n)}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});
closeOptimizer();}

// ── Results ──────────────────────────────────────────────────────
async function loadRes(){const r=await fetch('/api/results').then(r=>r.json());
$('results-body').innerHTML=r.map(x=>{const d=x.close_price&&x.target_price?((x.close_price-x.target_price)/x.target_price*100):0;
return`<tr><td>${TS(x.resolved_at)}</td><td>${x.market_type}</td><td>${U(x.target_price)}</td><td>${U(x.close_price)}</td><td style="color:${d>=0?'var(--green)':'var(--red)'}">${P(d)}</td><td><span class="result-chip ${x.outcome==='UP'?'win':'loss'}">${x.outcome}</span></td></tr>`;}).join('');}

connectWS();loadRes();setInterval(loadRes,30000);setInterval(()=>{if(selBot)showD(selBot);},15000);
