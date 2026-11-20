import {datasets,jobs,contracts} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {esc,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
function supported(version){const c=(workspace.contracts?.versions||[]).find(v=>v.version===version);return new Set([...(c?c.columns:[]).map(x=>x.key),'channel','week']);}
export async function workbench(){
 [workspace.datasets,workspace.contracts]=await Promise.all([datasets.list(),contracts.list()]);const m=workspace.meta;
 const active=workspace.datasets.filter(d=>d.status!=='quarantined');
 return heading('03 / ANALYSIS LAB',m.workbench_title,'选择业务批次和分析口径。参数、输入指纹、固定契约版本与计算结论随任务保存，便于复核和复现。')+'<div class="workbench-grid"><section class="panel"><form id="job-form"><label>分析任务名称<input name="name" required minlength="2" value="'+esc(m.name)+' · 复核试算"></label><label>数据批次<select name="dataset_id" required>'+workspace.datasets.map(d=>'<option value="'+d.id+'" '+(d.status==='quarantined'?'disabled':'')+'>'+esc(d.name)+' · '+esc(d.contract_version||'—')+' · '+d.rows+' 条'+(d.status==='quarantined'?'（已隔离）':'')+'</option>').join('')+'</select></label><div class="parameter-grid">'+m.parameters.map(p=>'<label>'+esc(p.label)+(p.type==='select'?'<select name="param-'+esc(p.key)+'">'+p.options.map(o=>'<option value="'+esc(o.value)+'" '+(o.value==p.default?'selected':'')+'>'+esc(o.label)+'</option>').join('')+'</select>':'<input type="number" step="any" name="param-'+esc(p.key)+'" value="'+esc(p.default)+'" min="'+esc(p.min??'')+'" max="'+esc(p.max??'')+'" required>')+'</label>').join('')+'</div><button type="submit" class="primary" '+(session.user.role==='viewer'||!active.length?'disabled':'')+'>'+esc(m.action_label||'执行分析')+' ↗</button><p class="hint">提交后由后台任务计算，分析全程固定该批次的契约版本；按结算标签分组需要契约 v2 及以上批次。观察员可查看参数和结果，无法提交。</p></form></section><section class="method-sheet"><p class="eyebrow">METHOD / BUSINESS RULE</p><h2>'+esc(m.method)+'</h2><p>'+esc(m.tagline)+'</p><h3>业务判读边界</h3><ul>'+m.limitations.map(v=>'<li>'+esc(v)+'</li>').join('')+'</ul><div class="method-trace"><span>输入</span><strong>'+esc(m.dataset_name)+'</strong><span>输出</span><strong>可复核结果 / 参数版本 / 分发归档</strong></div></section></div>';
}
export function bindWorkbench(){
 const datasetSelect=document.querySelector('[name=dataset_id]'),groupSelect=document.querySelector('[name=param-group_by]');
 const gate=()=>{const d=workspace.datasets.find(x=>String(x.id)===datasetSelect.value);if(!d||!groupSelect)return;const ok=supported(d.contract_version);let reset=false;for(const o of groupSelect.options){const allowed=ok.has(o.value);o.disabled=!allowed;if(!allowed&&o.selected)reset=true;}if(reset)groupSelect.value='channel';};
 datasetSelect?.addEventListener('change',gate);gate();
 submit(document.querySelector('#job-form'),async f=>{const params={};for(const p of workspace.meta.parameters){const value=f.get('param-'+p.key);params[p.key]=p.type==='number'?Number(value):value;}const j=await jobs.create({name:f.get('name'),dataset_id:Number(f.get('dataset_id')),params});workspace.selectedJob=j.id;notify('分析任务已提交');location.hash='#/results/'+j.id;});
}
