'use strict';
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let user,model,facilities=[],rows=[],accounts=[],selectedRecord=null,offset=0,total=0;
function tell(s){$('#toast').textContent=s;$('#toast').hidden=false;clearTimeout(tell.t);tell.t=setTimeout(()=>$('#toast').hidden=true,6000);}
async function api(path,body){const r=await fetch('/api'+path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-CSRF-Token':user.csrf}:{},body:body?JSON.stringify(body):undefined});if(r.status===401){location.href='/';throw Error('請先登入');}const value=await r.json();if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail));return value;}
async function action(fn,button){if(button)button.disabled=true;try{await fn();}catch(e){tell(e.message);}finally{if(button)button.disabled=false;}}
function aiTag(r){return `<span class="tag ${r.anomaly?'warn':''}">${r.anomaly?'待人工覆核':'正常範圍'}</span>`;}
function reviewTag(r){const labels={confirmed:'確認合理',rejected:'已退回',pending:'待查證'};return r.review?`<span class="tag ${r.review.decision==='confirmed'?'':'warn'}">${labels[r.review.decision]}</span>`:(r.anomaly?'尚未覆核':'—');}
async function refresh(){
 model=await api('/semiconductor/model');$('#status').hidden=model.loaded;$('#status').textContent=model.loaded?'':(user.role==='admin'?'尚未載入年度模型，請先載入模型。':'目前暫無可用模型，請聯絡管理員。');populateFacilities();
 const data=await api('/semiconductor/records?offset='+offset);rows=data.records;total=data.total;
 $('#count').textContent=total?`目前 ${offset+1}–${offset+rows.length} 筆，共 ${total} 筆`:'尚無年度紀錄';
 $('#rows').innerHTML=rows.map(r=>`<tr><td>#${r.id} ${esc(r.supplier)}</td><td>${r.year}</td><td>${r.direct}</td><td>${r.indirect}</td><td>${aiTag(r)}</td><td>${reviewTag(r)}</td><td><button data-id="${r.id}">${user.role==='admin'?'檢視／覆核':'檢視'}</button></td></tr>`).join('');
 $('#prev').disabled=offset===0;$('#next').disabled=offset+rows.length>=total;
 document.querySelectorAll('[data-id]').forEach(b=>b.onclick=()=>openDetails(rows.find(r=>r.id===+b.dataset.id)));
}
function openDetails(row){
 selectedRecord=row;
 const fields=[['供應商',row.supplier],['廠別管制編號',row.controlno],['行業',row.industry],['年度',row.year],['直接排放',row.direct+' tCO₂e'],['間接排放',row.indirect+' tCO₂e'],['總排放',row.total+' tCO₂e']];
 $('#detail-content').innerHTML=`<dl class="record-fields">${fields.map(([label,value])=>`<div><dt>${label}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl><p>AI 偵測結果：${aiTag(row)}</p><p>人工覆核：${reviewTag(row)}</p>${row.review?`<p>覆核說明：${esc(row.review.note)}</p><small>${esc(row.review.reviewed_by)} · ${esc(row.review.reviewed_at)}</small>`:''}<details><summary>驗證資訊</summary><pre>資料指紋：${esc(row.hash)}
模型識別：${esc(row.model_id)}</pre></details>`;
 $('#review-form').hidden=user.role!=='admin';$('#review-decision').value=row.review?.decision||'pending';$('#review-note').value=row.review?.note||'';$('#review-message').textContent='';
 if(!$('#record-dialog').open)$('#record-dialog').showModal();
}
$('#detail-close').onclick=()=>$('#record-dialog').close();
$('#review-form').onsubmit=e=>{e.preventDefault();action(async()=>{
 const note=$('#review-note').value.trim();if(!note)throw Error('請填寫覆核說明');const id=selectedRecord.id;
 await api('/semiconductor/records/'+id+'/review',{decision:$('#review-decision').value,note});await refresh();
 const row=rows.find(r=>r.id===id);if(row)openDetails(row);$('#review-message').textContent='覆核已儲存';tell('覆核已儲存');
},e.target.querySelector('button'));};
async function loadBindings(){
 if(user.role!=='admin')return;
 accounts=await api('/semiconductor/supplier-accounts');
 $('#binding-panel').hidden=false;
 const prev=$('#binding-user').value;
 $('#binding-user').innerHTML='<option value="">請選擇帳號</option>'+accounts.map(a=>`<option value="${esc(a.username)}">${esc(a.username)}</option>`).join('');
 if(accounts.some(a=>a.username===prev))$('#binding-user').value=prev;
 $('#binding-facility').innerHTML='<option value="">請選擇廠別</option>'+facilities.map(f=>`<option value="${esc(f.controlno)}">${esc(f.controlno)} — ${esc(f.supplier)}</option>`).join('');
 $('#binding-user').onchange=()=>{const account=accounts.find(a=>a.username===$('#binding-user').value);$('#binding-current').textContent=account?'目前綁定：'+account.supplier:'';$('#binding-facility').value=facilities.find(f=>f.supplier===account?.supplier)?.controlno||'';};
 $('#binding-user').onchange();$('#binding-save').disabled=!accounts.length;
}
$('#binding-form').onsubmit=e=>{e.preventDefault();action(async()=>{
 const username=$('#binding-user').value,controlno=$('#binding-facility').value;
 if(!username||!controlno)throw Error('請選擇帳號與廠別');
 if(!confirm('這會變更此帳號可存取的供應商資料，並讓該帳號登出。確定儲存？'))return;
 await api('/semiconductor/supplier-binding',{username,controlno});await loadBindings();tell('已儲存廠別設定，請供應商重新登入');
},$('#binding-save'));};

function populateFacilities(){
 const form=$('#annual-form'), select=form.elements.controlno, previous=select.value;
 const allowed=facilities.filter(f=>!model.loaded||f.industry===model.industry);
 select.innerHTML='<option value="">請選擇廠別</option>'+allowed.map(f=>`<option value="${esc(f.controlno)}">${esc(f.controlno)} — ${esc(f.supplier)}</option>`).join('');
 if(allowed.some(f=>f.controlno===previous))select.value=previous;
 const update=()=>{const facility=allowed.find(f=>f.controlno===select.value);form.elements.supplier.value=facility?.supplier||'';if(facility)form.elements.industry.value=facility.industry;};
 select.onchange=update;update();select.disabled=!allowed.length;form.querySelector('button').disabled=!allowed.length||!model.loaded;
 $('#facility-hint').textContent=allowed.length?'':(user.role==='admin'?'目前沒有符合模型行業的廠別。':'沒有可選廠別，請聯絡管理員確認帳號的供應商名稱與廠別資料一致。');
}

function csv(text){let rows=[],row=[],v='',quoted=false;for(let i=0;i<text.length;i++){let c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){v+='"';i++;}else quoted=!quoted;}else if(c===','&&!quoted){row.push(v);v='';}else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(v);if(row.some(x=>x.trim()))rows.push(row);row=[];v='';}else v+=c;}if(quoted)throw Error('CSV 引號未閉合');row.push(v);if(row.some(x=>x.trim()))rows.push(row);const header=rows.shift()?.map(x=>x.trim());const fields=['app_year','companyname','controlno','ccksicco1','sicname1','tot1_value','tot2_value','tot_value','check_yn'];if(!header||fields.some(k=>!header.includes(k)))throw Error('請選擇原始格式的 semiconductor-clean-annual.csv，不是 scores.csv');return rows.map((r,i)=>{if(r.length!==header.length)throw Error('CSV 第'+(i+2)+'列欄位數錯誤');return Object.fromEntries(header.map((k,j)=>[k,r[j]]));});}
async function save(records){await api('/semiconductor/records',{records});offset=0;await refresh();tell('已保存年度評分、雜湊及稽核事件');}
$('#import').onclick=e=>action(async()=>{const f=$('#model-file').files[0];if(!f||f.size>2*1024*1024)throw Error('請選擇 2 MB 以內模型 JSON');await api('/semiconductor/model/import',JSON.parse(await f.text()));await refresh();tell('年度模型已載入');},e.target);
$('#annual-form').onsubmit=e=>{e.preventDefault();action(async()=>{const r=Object.fromEntries(new FormData(e.target));r.industry=$('#annual-form').elements.industry.value;for(const k of ['year','direct','indirect'])r[k]=Number(r[k]);await save([r]);},e.target.querySelector('button'));};
$('#csv-save').onclick=e=>action(async()=>{if(!model.loaded)throw Error('請先載入模型');const f=$('#csv').files[0];if(!f||f.size>2*1024*1024)throw Error('請選擇 2 MB 以內 CSV');const year=Number($('#csv-year').value);const all=csv((await f.text()).replace(/^\uFEFF/,''));const selected=all.filter(r=>{const y=Number(r.app_year);return (y<1911?y+1911:y)===year&&r.ccksicco1===model.industry;});if(!selected.length||selected.length>1000)throw Error('指定行業／年度需有1–1000筆');const records=selected.map(r=>{if(r.check_yn!=='是'||!r.tot1_value.trim()||!r.tot2_value.trim()||!r.tot_value.trim())throw Error('請先清理缺值與未查證資料');const direct=Number(r.tot1_value),indirect=Number(r.tot2_value),total=Number(r.tot_value);if(![direct,indirect,total].every(Number.isFinite)||Math.abs(direct+indirect-total)>.002)throw Error('數值或合計檢查失敗');return {supplier:r.companyname,controlno:r.controlno,industry:r.ccksicco1,year,direct,indirect};});if(!confirm(`將新增 ${records.length} 筆 ${year} 年資料，是否繼續？`))return;await save(records);},e.target);
$('#verify').onclick=()=>action(async()=>{const result=await api('/semiconductor/integrity');$('#verification').hidden=false;$('#verification').textContent=JSON.stringify(result,null,2);});$('#refresh').onclick=()=>action(refresh);$('#prev').onclick=()=>action(async()=>{offset-=100;await refresh();});$('#next').onclick=()=>action(async()=>{offset+=100;await refresh();});
$('#export').onclick=()=>{const fields=['id','supplier','controlno','industry','year','direct','indirect','total','score','anomaly','model_id','hash'];const cell=v=>{let s=String(v??'');if(/^[=+@\-\t\r\n]/.test(s.trimStart()))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';};const text=fields.join(',')+'\n'+rows.map(r=>fields.map(k=>cell(r[k])).join(',')).join('\n');const url=URL.createObjectURL(new Blob(['\uFEFF',text],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='semiconductor-page.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
(async()=>{try{user=await api('/me');const isAdmin=user.role==='admin';$('#annual-management').hidden=!isAdmin;$('#verify').hidden=!isAdmin;$('#import').disabled=!isAdmin;$('#csv-save').disabled=!isAdmin;facilities=await api('/semiconductor/facilities');await loadBindings();await refresh();}catch(e){tell(e.message);}})();
