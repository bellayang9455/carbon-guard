'use strict';
const $ = s => document.querySelector(s);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
let user, page = 'overview', records = [], total = 0, offset = 0, model = {}, search = '', state = 'all';
const titles = {overview:'碳數據，安心掌握。',records:'每一筆排放，都有依據。',ai:'AI 異常偵測',integrity:'資料完整性驗證',security:'資安防護與稽核'};
async function api(path, options = {}) {
  const headers = {...options.headers};
  if (options.body) headers['Content-Type'] = 'application/json';
  if (user?.csrf) headers['X-CSRF-Token'] = user.csrf;
  const response = await fetch('/api' + path, {...options, headers, credentials:'same-origin'});
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    if (response.status === 401 && path !== '/login') showLogin();
    throw Error(typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail || '操作失敗'));
  }
  if (path === '/export') return response.blob();
  return response.json();
}
function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => $('#toast').hidden = true, 5000); }
function showLogin() {user = null;$('#app').hidden = true;$('#login-view').hidden = false;}
async function enter() {
  $('#login-view').hidden = true;$('#app').hidden = false;
  $('#identity').textContent = `${user.username}｜${user.role === 'admin' ? '管理員' : user.supplier}`;
  document.querySelectorAll('.admin-only').forEach(el => el.hidden = user.role !== 'admin');
  page = 'overview'; offset = 0; await refresh();
}
async function refresh() {
  const [data, info] = await Promise.all([api(`/records?limit=100&offset=${offset}`), api('/model')]);
  records = data.records; total = data.total; model = info; render();
}
function tag(row) {return row.anomaly === null ? '<span class="tag muted">尚未評分</span>' : row.anomaly ? '<span class="tag warn">待人工覆核</span>' : '<span class="tag">正常範圍</span>';}
function table() {
  const filtered = records.filter(row => (!search || row.supplier.includes(search) || String(row.id).includes(search)) && (state === 'all' || (state === 'anomaly' ? row.anomaly === true : row.anomaly === false)));
  return `<div class="card"><div class="toolbar"><input id="search" aria-label="搜尋本頁供應商" placeholder="搜尋本頁供應商或編號" value="${escapeHTML(search)}"><select id="filter" aria-label="篩選狀態"><option value="all">全部狀態</option><option value="anomaly" ${state==='anomaly'?'selected':''}>待覆核</option><option value="normal" ${state==='normal'?'selected':''}>正常範圍</option></select><button id="export" class="secondary">匯出所有可見資料</button><small>篩選適用於目前這一頁</small></div><div class="tablewrap"><table><thead><tr><th>編號 / 供應商</th><th>月份</th><th>範疇</th><th>tCO₂e</th><th>產量</th><th>AI 結果</th><th>分數</th><th>操作</th></tr></thead><tbody>${filtered.map(row => `<tr><td>#${row.id} ${escapeHTML(row.supplier)}</td><td>${escapeHTML(row.month)}</td><td>${row.scope}</td><td>${row.emission.toLocaleString()}</td><td>${row.production.toLocaleString()}</td><td>${tag(row)}</td><td>${row.score?.toFixed(4) ?? '—'}</td><td><button class="secondary detail-button" data-id="${row.id}">詳情${user.role==='admin'?' / 覆核':''}</button></td></tr>`).join('') || '<tr><td colspan="8">沒有符合條件的資料</td></tr>'}</tbody></table></div><div class="pager"><span>第 ${total ? offset+1 : 0}–${offset+records.length} 筆 / 共 ${total} 筆</span><button id="previous" class="secondary" ${offset===0?'disabled':''}>上一頁</button><button id="next" class="secondary" ${offset+records.length>=total?'disabled':''}>下一頁</button></div></div>`;
}
function overview() {
  const sum = records.reduce((s,r) => s+r.emission,0), flags = records.filter(r=>r.anomaly).length;
  const months = [...new Set(records.map(r=>r.month))].sort().slice(-6);
  const values = months.map(m=>records.filter(r=>r.month===m).reduce((s,r)=>s+r.emission,0));
  const max = Math.max(...values,1);
  return `<div class="grid stats">${[['可見紀錄總數',total,'筆'],['本頁排放總量',sum.toLocaleString(undefined,{maximumFractionDigits:2}),'tCO₂e'],['本頁待覆核',flags,'筆'],['本頁供應商',new Set(records.map(r=>r.supplier)).size,'家']].map(([label,v,unit])=>`<div class="card stat"><span>${label}</span><strong>${v}</strong><small>${unit}</small></div>`).join('')}</div><div class="card"><h2>月度排放趨勢</h2><small>僅統計目前載入的 ${records.length} 筆資料，非全部資料總量。</small><div class="bars">${months.map((m,i)=>`<div class="barcol"><span>${values[i].toFixed(1)}</span><div class="bar" data-height="${Math.round(values[i]/max*120)}"></div><small>${escapeHTML(m)}</small></div>`).join('') || '<p>新增資料後即可查看趨勢。</p>'}</div></div>` + table();
}
function render() {
  $('#page-title').textContent = titles[page];
  document.querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===page));
  $('#model-banner').hidden = model.trained;
  $('#model-banner').textContent = model.trained ? '' : '尚未設定模型，資料將暫不評分。';
  let html = '';
  if (page === 'overview') html = overview();
  if (page === 'records') html = table();
  if (page === 'ai') html = `<div class="grid two"><div class="card"><h2>Isolation Forest 模型</h2><p>200 棵隔離樹；特徵包含排放量、產量、排放強度及範疇。分數越高代表越離群，並非錯誤機率。請使用相同產品及可比較單位的參考資料。</p><pre>${escapeHTML(JSON.stringify(model,null,2))}</pre></div><div class="card">${user.role==='admin'?`<h2>訓練模型</h2><p>匯入已確認的參考 CSV（32–10,000 筆，2 MB 以內）。資料格式與排放匯入相同；訓練不會新增排放紀錄。</p><label>預期離群比例<input id="contamination" type="number" value="0.05" min="0.001" max="0.5" step="0.001"></label><label>訓練備註<textarea id="training-note" maxlength="500" placeholder="例如：2026 年已核對的同產品歷史資料"></textarea></label><input id="train-file" type="file" accept=".csv,text/csv" aria-label="訓練資料 CSV"><button id="train-button">上傳並訓練</button><p id="train-status" role="status"></p>`:'<h2>模型管理權限</h2><p>模型訓練由管理員執行。你可以上傳所屬供應商資料並查看模型評分。</p>'}</div></div>` + table();
  if (page === 'integrity') html = `<div class="card"><h2>內容指紋與鏈結驗證</h2><p>每筆排放紀錄及稽核事件建立 SHA-256 鏈，並以伺服器密鑰產生 HMAC。修改內容、插入紀錄或重寫指紋會造成驗證失敗。</p><button id="verify">立即驗證全部紀錄</button><pre id="verification">尚未執行驗證</pre></div><div class="notice">尾端刪除、整庫回滾需要外部可信錨點偵測。請執行 checkpoint 指令，將筆數及鏈頭保存到獨立的不可改寫儲存。</div>`;
  if (page === 'security') html = `<div class="grid two"><div class="card"><h2>已實作的應用層控制</h2><p>PBKDF2 密碼雜湊、HttpOnly / SameSite Cookie、CSRF Token、供應商存取隔離、管理員權限、登入節流、請求大小限制、參數化 SQL 及安全標頭。</p></div><div class="card"><h2>部署環境需配置</h2><p>HTTPS、WAF、集中式限流、SSO / MFA、備份、金鑰管理、外部稽核錨點與監控。本專案採單程序 SQLite，不支援多 Worker 同時共享模型。</p></div></div><div class="card"><div class="heading"><h2>最近 200 筆稽核事件</h2><button id="load-audit" class="secondary">讀取稽核</button></div><div id="audit-output"></div></div>`;
  $('#content').innerHTML = html; document.querySelectorAll('.bar').forEach(el=>el.style.height=el.dataset.height+'px'); bind();
}
function bind() {
  if ($('#search')) $('#search').oninput = e => { search=e.target.value;const p=e.target.selectionStart;render();$('#search').focus();$('#search').setSelectionRange(p,p); };
  if ($('#filter')) $('#filter').onchange = e => { state=e.target.value;render(); };
  for (const [id,delta] of [['previous',-100],['next',100]]) if ($('#'+id)) $('#'+id).onclick=async()=>{offset+=delta;try{await refresh();}catch(e){toast(e.message);}};
  if ($('#export')) $('#export').onclick=async()=>{try{const blob=await api('/export');const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='carbon-records.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){toast(e.message);}};
  document.querySelectorAll('.detail-button').forEach(button=>button.onclick=async()=>{
    const row=records.find(r=>r.id===Number(button.dataset.id));
    if (user.role!=='admin') {alert(JSON.stringify(row,null,2));return;}
    const decision=prompt(`紀錄 #${row.id}\nSHA-256: ${row.hash}\n模型: ${row.model_id ?? '未評分'}\n\n輸入覆核結果：confirmed（確認合理）、rejected（退回）、pending（待查）\n取消可關閉。`);
    if(decision===null)return;
    if(!['confirmed','rejected','pending'].includes(decision)){toast('覆核結果格式不正確');return;}
    const note=prompt('請輸入覆核原因（1–500 字元）');if(!note)return;
    try{await api(`/records/${row.id}/review`,{method:'POST',body:JSON.stringify({decision,note})});toast('已追加覆核事件，可於稽核頁查閱；原始資料保留。');}catch(e){toast(e.message);}
  });
  if ($('#verify')) $('#verify').onclick=async()=>{try{$('#verification').textContent=JSON.stringify(await api('/integrity'),null,2);}catch(e){toast(e.message);}};
  if ($('#load-audit')) $('#load-audit').onclick=async()=>{try{const rows=await api('/audit');$('#audit-output').innerHTML=`<div class="tablewrap"><table><thead><tr><th>時間</th><th>操作者</th><th>事件</th><th>內容</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${escapeHTML(r.time)}</td><td>${escapeHTML(r.user)}</td><td>${escapeHTML(r.action)}</td><td>${escapeHTML(JSON.stringify(r.detail))}</td></tr>`).join('')}</tbody></table></div>`;}catch(e){toast(e.message);}};
  if ($('#train-button')) $('#train-button').onclick=async()=>{
    const button=$('#train-button');button.disabled=true;
    try{const samples=await csvFile($('#train-file').files[0],10000);if(samples.length<32)throw Error('至少需要 32 筆參考資料');const contamination=Number($('#contamination').value),note=$('#training-note').value.trim();if(!note)throw Error('請填寫訓練備註');$('#train-status').textContent='訓練中，請稍候…';await api('/model/train',{method:'POST',body:JSON.stringify({samples,contamination,note})});await refresh();toast('模型已訓練並保存參考資料');}catch(e){toast(e.message);if($('#train-status'))$('#train-status').textContent=e.message;}finally{button.disabled=false;}
  };
}
function parseCSV(text) {
  const rows=[];let row=[],value='',quoted=false;
  for(let i=0;i<text.length;i++){const ch=text[i];if(ch==='"'){if(quoted&&text[i+1]==='"'){value+='"';i++;}else quoted=!quoted;}else if(ch===','&&!quoted){row.push(value);value='';}else if((ch==='\n'||ch==='\r')&&!quoted){if(ch==='\r'&&text[i+1]==='\n')i++;row.push(value);if(row.some(v=>v.trim()))rows.push(row);row=[];value='';}else value+=ch;}
  if(quoted)throw Error('CSV 引號未閉合');row.push(value);if(row.some(v=>v.trim()))rows.push(row);return rows;
}
async function csvFile(file,max) {
  if(!file)throw Error('請先選擇 CSV');if(file.size>2*1024*1024)throw Error('CSV 不可超過 2 MB');
  const rows=parseCSV((await file.text()).replace(/^\uFEFF/,'')),head=rows.shift()?.map(v=>v.trim());
  if(JSON.stringify(head)!==JSON.stringify(['supplier','month','scope','emission','production']))throw Error('CSV 欄位須依序為 supplier,month,scope,emission,production');
  if(!rows.length||rows.length>max)throw Error(`需提供 1–${max} 筆資料`);
  return rows.map((r,i)=>{if(r.length!==5||r.some(v=>!v.trim()))throw Error(`第 ${i+2} 列欄位錯誤`);const result={supplier:r[0].trim(),month:r[1].trim(),scope:Number(r[2]),emission:Number(r[3]),production:Number(r[4])};if(![result.scope,result.emission,result.production].every(Number.isFinite))throw Error(`第 ${i+2} 列數值無效`);return result;});
}
$('#login-form').onsubmit=async event=>{event.preventDefault();const form=new FormData(event.target),button=event.target.querySelector('button');button.disabled=true;$('#login-error').textContent='';try{user=await api('/login',{method:'POST',body:JSON.stringify(Object.fromEntries(form))});event.target.reset();await enter();}catch(e){$('#login-error').textContent=e.message;}finally{button.disabled=false;}};
$('#logout').onclick=async()=>{try{await api('/logout',{method:'POST'});showLogin();}catch(e){toast(e.message);}};
document.querySelectorAll('[data-page]').forEach(button=>button.onclick=async()=>{page=button.dataset.page;search='';state='all';try{await refresh();}catch(e){toast(e.message);}});
$('#open-upload').onclick=()=>{const form=$('#record-form');form.reset();form.elements.supplier.readOnly=user.role!=='admin';form.elements.supplier.value=user.role==='admin'?'':user.supplier;form.elements.month.value=(()=>{const p=new Intl.DateTimeFormat('en',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit'}).formatToParts(new Date());return p.find(x=>x.type==='year').value+'-'+p.find(x=>x.type==='month').value;})();$('#upload-message').textContent='';$('#upload-dialog').showModal();};
$('#close-dialog').onclick=()=>$('#upload-dialog').close();
async function saveRows(rows){await api('/records',{method:'POST',body:JSON.stringify({records:rows})});$('#upload-dialog').close();offset=0;await refresh();toast('已保存資料、雜湊與模型評分');}
$('#record-form').onsubmit=async event=>{event.preventDefault();const button=event.target.querySelector('button:not([type="button"])');button.disabled=true;try{const values=Object.fromEntries(new FormData(event.target));for(const name of ['scope','emission','production'])values[name]=Number(values[name]);await saveRows([values]);}catch(e){$('#upload-message').textContent=e.message;}finally{button.disabled=false;}};
$('#upload-csv').onchange=async event=>{const input=event.target;input.disabled=true;try{await saveRows(await csvFile(input.files[0],1000));}catch(e){$('#upload-message').textContent=e.message;}finally{input.disabled=false;input.value='';}};
(async()=>{try{user=await api('/me');await enter();}catch{showLogin();}})();
