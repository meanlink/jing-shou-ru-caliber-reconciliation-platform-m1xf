import {datasets,contracts} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {esc,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {parseCSV} from '../utils/csv.js';
import {DatasetStatus} from '../constants/enums.js';
function columnsOf(version){const c=(workspace.contracts?.versions||[]).find(v=>v.version===version);return c?c.columns:workspace.meta.columns;}
function labelOf(version){const c=(workspace.contracts?.versions||[]).find(v=>v.version===version);return c?c.label:version;}
function preview(d){
 if(!d)return '<div class="empty">尚无批次。接入数据后在此预览。</div>';
 const note=d.status==='quarantined'?'<p class="warning">整批隔离：'+esc(d.quarantine_reason)+'。该批次不参与分析，请修复后换名重新接入。</p>':'';
 return note+table(columnsOf(d.contract_version),d.records.slice(0,30));
}
function contractPanel(){
 const c=workspace.contracts;if(!c)return '';
 return '<section class="panel"><div class="section-title"><h2>列契约版本</h2><span>默认 '+esc(c.default_version)+'</span></div><p class="hint">默认依据：'+esc(c.default_basis)+'</p><div class="contract-list">'+c.versions.map(v=>'<article class="contract-card'+(v.default?' default':'')+'"><div><strong>'+esc(v.version)+' · '+esc(v.label)+'</strong>'+(v.default?'<span class="tag">当前默认</span>':'')+'</div><p>'+esc(v.introduced)+'</p><div class="field-chips">'+v.columns.map(col=>'<span>'+esc(col.key)+'<small>'+esc(col.label)+'</small></span>').join('')+'</div>'+(v.diff_from_previous?'<p class="diff-line">较上一版本：'+(v.diff_from_previous.added.length?'新增 '+v.diff_from_previous.added.map(a=>esc(a.label)+'（'+esc(a.key)+'）').join('、'):'')+(v.diff_from_previous.removed.length?'；移除 '+v.diff_from_previous.removed.map(a=>esc(a.label)).join('、'):'')+(v.diff_from_previous.type_changed.length?'；类型变化 '+v.diff_from_previous.type_changed.map(a=>esc(a.label)+' '+esc(a.from)+'→'+esc(a.to)).join('、'):'')+(!v.diff_from_previous.added.length&&!v.diff_from_previous.removed.length&&!v.diff_from_previous.type_changed.length?'无结构变化':'')+'</p>':'<p class="diff-line">初始注册版本</p>')+'</article>').join('')+'</div></section>';
}
function previewMeta(d){
 if(!d)return '';
 return d.status==='quarantined'?'已隔离 · 契约未判定 · 预览前 30 条':'采用契约 '+esc(d.contract_version)+' · '+esc(labelOf(d.contract_version))+' · 预览前 30 条';
}
export async function dataPage(){
 [workspace.datasets,workspace.contracts]=await Promise.all([datasets.list(),contracts.list()]);
 let first=workspace.datasets.find(d=>d.status!=='quarantined')||workspace.datasets[0];
 let selected=first?await datasets.get(first.id):null,m=workspace.meta;
 return heading('02 / DATA INTAKE','数据接入与批次追溯','保留原始业务字段、来源和内容指纹。每批记录整体判定一个列契约版本，分析任务始终绑定不可变批次与固定契约。')+'<div class="dataset-grid"><section class="panel"><div class="section-title"><h2>业务批次</h2><span>'+workspace.datasets.length+' 批</span></div><div class="batch-list">'+workspace.datasets.map(d=>'<button class="batch-item" data-dataset="'+d.id+'"><strong>'+esc(d.name)+'</strong><span><span class="tag'+(d.status==='quarantined'?' danger':'')+'">'+esc(d.contract_version||'—')+(d.status==='quarantined'?' · '+esc(DatasetStatus[d.status]||d.status):'')+'</span> '+d.rows+' 条 · '+esc(d.source)+'</span><small>SHA256 '+esc(d.checksum.slice(0,18))+'…</small></button>').join('')+'</div><div class="section-title"><h2>接入新数据</h2></div><form id="dataset-form"><label>批次名称<input name="name" required minlength="2" placeholder="例如：11 月复测批次"></label><label>上传 CSV 或 JSON<input type="file" id="file-input" accept=".json,.csv"></label><label>记录 JSON<textarea name="records" rows="6" placeholder="粘贴 JSON 数组，或先选择上方文件" required></textarea></label><p class="hint">默认契约 '+esc(m.default_contract)+' 字段：'+m.columns.map(c=>esc(c.key)+' / '+esc(c.label)).join('，')+'。5–5,000 条记录。字段新增按版本兼容，旧版批次继续有效；缺必需字段、类型变化、未知字段或同批混用契约将整批隔离。</p><button type="submit" class="primary" '+(session.user.role==='viewer'?'disabled':'')+'>校验并接入批次</button></form></section><section class="panel"><div class="section-title"><h2 id="preview-name">'+esc(selected?.name||'尚无批次')+'</h2><span id="preview-meta">'+previewMeta(selected)+'</span></div><div id="data-preview">'+preview(selected)+'</div></section></div>'+contractPanel();
}
export function bindData(refresh){
 let source='manual.json';
 document.querySelector('#file-input').addEventListener('change',async e=>{try{const file=e.target.files[0];if(!file)return;source=file.name;const text=await file.text(),records=file.name.endsWith('.csv')?parseCSV(text):JSON.parse(text);document.querySelector('[name=records]').value=JSON.stringify(records,null,2);}catch(error){notify(error.message,true);}});
 document.querySelectorAll('[data-dataset]').forEach(button=>button.onclick=async()=>{try{const d=await datasets.get(button.dataset.dataset);document.querySelector('#preview-name').textContent=d.name;document.querySelector('#preview-meta').textContent=previewMeta(d);document.querySelector('#data-preview').innerHTML=preview(d);}catch(error){notify(error.message,true);}});
 submit(document.querySelector('#dataset-form'),async f=>{const d=await datasets.create({name:f.get('name'),source,records:JSON.parse(f.get('records'))});if(d.status==='quarantined')notify('批次已整批隔离：'+d.quarantine_reason,true);else notify('数据已接入（采用契约 '+d.contract_version+'），可前往工作台执行分析');await refresh();});
}
