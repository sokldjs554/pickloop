import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname,resolve} from 'node:path';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const html=readFileSync(resolve(root,'web/index.html'),'utf8');
const js=readFileSync(resolve(root,'web/app.js'),'utf8');
const css=readFileSync(resolve(root,'web/styles.css'),'utf8');
new vm.Script(js,{filename:'app.js'});
const context={URL};vm.createContext(context);vm.runInContext(js,context);
const {normalizeRun,resolveFrameUrl,frameAtTime,retries,statusLabel,failureSummary,isTerminal}=context.PickLoopContract;
let checks=0;
function check(name,fn){fn();checks++;console.log(`ok ${checks} - ${name}`);}
check('HTML is Korean and references actual local assets',()=>{assert.match(html,/<html lang="ko">/);assert.match(html,/href="styles.css"/);assert.match(html,/defer src="app.js"/);});
check('every script ID reference has a unique HTML element',()=>{const ids=[...(html+js).matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);const staticIds=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);assert.equal(new Set(staticIds).size,staticIds.length);for(const [,id] of js.matchAll(/\$\('([^']+)'\)/g))assert.ok(ids.includes(id),`missing #${id}`);});
check('static view cannot start or cancel live compute',()=>{assert.match(html,/<button id="mode-live" disabled/);assert.match(html,/<button id="start-job"[^>]*hidden/);assert.match(html,/<button id="cancel-job"[^>]*hidden/);assert.match(js,/health\.mode!=='live'/);assert.match(js,/state\.mode!=='live'\|\|!state\.liveAvailable\|\|state\.jobId/);});
check('all visible controls have handlers or native behavior',()=>{for(const id of ['mode-replay','mode-live','play-toggle','scrubber','speed','event-detail-toggle','close-dialog','cancel-job'])assert.ok(js.includes(`$('${id}').addEventListener`),`missing handler for ${id}`);assert.match(js,/\$\('run-form'\)\.addEventListener\('submit'/);assert.match(html,/id="download-log"[^>]*download/);assert.doesNotMatch(html,/href="#"/);});
check('missing run payload fields normalize to honest empty arrays',()=>{const r=normalizeRun(null);assert.equal(r.frames.length,0);assert.equal(r.events.length,0);assert.equal(statusLabel(r),'—');assert.equal(retries(r),null);});
check('frames are sorted and invalid timestamps rejected',()=>{const r=normalizeRun({frames:[{sim_time:2},{sim_time:0},null,{sim_time:'3'},{}],events:[{sim_time:4},{sim_time:1}]});assert.equal(r.frames.map(f=>f.sim_time).join(','),'0,2');assert.equal(r.events[0].sim_time,1);});
check('frame paths resolve against run manifest, including nested hosting',()=>{assert.equal(resolveFrameUrl('frames/00001-camera.jpg','data/runs/r1/run.json','https://demo.test/project/'),'https://demo.test/project/data/runs/r1/frames/00001-camera.jpg');assert.equal(resolveFrameUrl('/runs/r1/frames/1.jpg','/api/jobs/1','http://localhost:8000/'),'http://localhost:8000/runs/r1/frames/1.jpg');assert.equal(resolveFrameUrl('javascript:alert(1)','data/run.json','https://demo.test/'),null);assert.equal(resolveFrameUrl(undefined,'data/run.json','https://demo.test/'),null);});
check('playback floors timestamps and clamps outside recording',()=>{const f=[{sim_time:1},{sim_time:2},{sim_time:4}];assert.equal(frameAtTime(f,0),0);assert.equal(frameAtTime(f,2.5),1);assert.equal(frameAtTime(f,99),2);assert.equal(frameAtTime([],2),-1);});
check('event seek prioritizes exact log binding over shared observation',()=>{const f=[{sim_time:1,log_event_id:'e1',observation_id:'o1'},{sim_time:2,log_event_id:'e2',observation_id:'o1'},{sim_time:3,log_event_id:'e3'}];assert.equal(frameAtTime(f,2,{event_id:'e2',observation_id:'o1'}),1);assert.equal(frameAtTime(f,2.8,{event_id:'missing'}),2);});
check('terminal and retry outcomes derive from data',()=>{assert.equal(statusLabel({status:'COMPLETED',success:true,retries:1}),'복구 완료');assert.equal(statusLabel({status:'HOLD_SUCTION_FAILED',success:false}),'보류');assert.equal(retries({events:[{attempt:1},{attempt:3}]}),2);assert.equal(isTerminal({status:'RUNNING'}),false);assert.equal(isTerminal({status:'HOLD_RECOVERY_REQUIRED'}),true);assert.equal(statusLabel({status:'HELD'}),'보류');assert.equal(isTerminal({status:'HELD'}),true);});
check('failure summary preserves stage and actual reason',()=>{assert.equal(failureSummary({events:[{event:'seal_failed',state:'SEAL',data:{reason:'PRESSURE_NOT_ESTABLISHED'}}]}),'흡착 / PRESSURE_NOT_ESTABLISHED');assert.equal(failureSummary({events:[]}),'감지된 실패 없음');});
check('image failure and empty frames have explicit UI states',()=>{assert.match(js,/img\.onerror/);assert.match(js,/저장된 프레임 없음/);assert.match(js,/프레임 파일을 불러오지 못했습니다/);assert.match(js,/프레임 경로 없음/);});
check('layout supports desktop and narrow screens without simulated robot graphics',()=>{assert.match(css,/@media\(max-width:700px\)/);assert.match(css,/grid-template-columns:220px minmax\(440px,1fr\) 284px/);assert.doesNotMatch(html,/<canvas/);assert.match(html,/<img id="scene-image"/);assert.match(html,/<img id="camera-image"/);});

const helpers=context.PickLoopContract;
check('HELD retains successful STATE_OK phase history and separates failure from retry exhaustion',()=>{assert.equal(typeof helpers.phaseHistory,'function');const events=[{sim_time:1,state:'OBSERVE',event:'STATE_OK',attempt:1},{sim_time:2,state:'PLAN',event:'STATE_OK',attempt:1},{sim_time:3,state:'SEAL',event:'STATE_FAILED',attempt:1},{sim_time:4,state:'RECOVERY',event:'RETRY_EXHAUSTED',attempt:3}];const history=helpers.phaseHistory(events,10);assert.equal(history.find(v=>v.key==='OBSERVE').done,true);assert.equal(history.find(v=>v.key==='SEAL').failed,true);assert.equal(history.find(v=>v.key==='VERIFY').done,false);});
check('comparison uses shared elapsed simulation time and freezes a shorter completed recording',()=>{assert.equal(typeof helpers.comparisonFrame,'function');const r=normalizeRun({frames:[{sim_time:5,frame_id:0},{sim_time:7,frame_id:1},{sim_time:9,frame_id:2}]});assert.equal(helpers.comparisonFrame(r,1).frame_id,0);assert.equal(helpers.comparisonFrame(r,3).frame_id,1);assert.equal(helpers.comparisonFrame(r,100).frame_id,2);});
check('pairing excludes different seeds and distinct catalog condition IDs',()=>{assert.equal(typeof helpers.sameCondition,'function');assert.equal(helpers.sameCondition({seed:7,fault:'normal',condition_id:'a'},{seed:7,fault:'normal',condition_id:'a'}),true);assert.equal(helpers.sameCondition({seed:7,fault:'normal',condition_id:'a'},{seed:7,fault:'normal',condition_id:'b'}),false);assert.equal(helpers.sameCondition({seed:7,fault:'normal'},{seed:8,fault:'normal'}),false);});
check('milestone jumps only exist for actual failure, retry start, or verified placement events',()=>{assert.equal(typeof helpers.milestones,'function');const r=normalizeRun({events:[{event:'STATE_FAILED',state:'SEAL',sim_time:3},{event:'RECOVERY_BEGIN',sim_time:4},{event:'PLACEMENT_VERIFIED',sim_time:8}]});assert.equal(helpers.milestones(r).failure.sim_time,3);assert.equal(helpers.milestones(r).retry.sim_time,4);assert.equal(helpers.milestones(r).placement.sim_time,8);assert.equal(helpers.milestones(normalizeRun({})).placement,null);});
check('diagnostic score is not probability and UNKNOWN explains registration rejection',()=>{assert.equal(typeof helpers.detectionLabel,'function');const v=helpers.detectionLabel({sku:'UNKNOWN',confidence:.7,distance:.12});assert.match(v,/미등록 품목·등록 기준 미충족/);assert.match(v,/진단점수 0.700/);assert.match(v,/embedding distance 0.120/);assert.doesNotMatch(v,/%/);});
check('pressure domain always includes real seal threshold -35 kPa',()=>{assert.equal(typeof helpers.pressureDomain,'function');const domain=helpers.pressureDomain([{pressure_kpa:0},{pressure_kpa:-2}]);assert.ok(domain.lo<=-35);assert.ok(domain.hi>=0);});
check('review controls expose synchronized comparison, provenance details and real jump handlers',()=>{for(const id of ['compare-left-policy','compare-right-policy','compare-play','compare-scrubber','jump-failure','jump-retry','jump-placement','provenance-detail','condition-runs','integration-evidence'])assert.ok(html.includes(`id="${id}"`),id);assert.match(js,/data\/evidence\.json/);assert.match(js,/naive:'단순 재시도 \(최대 3회\)'/);});
// Execute the real browser script against a minimal DOM surface and deterministic
// recorded payloads. This checks loading, control bindings and time synchronization;
// it is not a substitute for browser layout/visual QA.
class Node {
  constructor(tag='div'){this.tag=tag;this._value='';this.children=[];this.dataset={};this.style={};this.attributes={};this.listeners={};this.hidden=false;this.disabled=false;this.textContent='';this.innerHTML='';this.naturalWidth=0;this.parentElement=this;this.classList={toggle(){}};}
  get value(){return this._value||this.children[0]?.value||'';}
  set value(v){this._value=String(v);}
  replaceChildren(...children){this.children=children;this._value='';}
  append(child){this.children.push(child);}
  setAttribute(k,v){this.attributes[k]=String(v);}
  getAttribute(k){return this.attributes[k]??(k==='src'?this.src:null)??null;}
  removeAttribute(k){delete this.attributes[k];if(k==='src')delete this.src;}
  addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
  querySelectorAll(){return [];}
  scrollIntoView(){}
  showModal(){this.open=true;}
  close(){this.open=false;}
  trigger(name){for(const fn of this.listeners[name]||[])fn({target:this,preventDefault(){}});}
}
const nodes=new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],new Node()]));
nodes.set('chart-cursor',new Node());
const doc={baseURI:'https://console.test/nested/',getElementById:id=>{assert.ok(nodes.has(id),`runtime ID missing: ${id}`);return nodes.get(id);},createElement:tag=>new Node(tag)};
const policies=['baseline','naive','reobserve','recovery'];
const fixtureRuns=policies.map(policy=>({run_id:`fixture-${policy}`,job_id:`job-${policy}`,seed:7,fault:'suction_once',policy,sku:'SKU-RED-A',status:policy==='recovery'?'COMPLETED':'HELD',success:policy==='recovery',retries:policy==='baseline'?0:2,run_url:`data/runs/${policy}/run.json`}));
const fixturePayload=entry=>({...entry,provenance:{source_sha256:'a'.repeat(64),model_sha256:'b'.repeat(64)},terminal_policy:entry.success?undefined:{action:'OFF_CONFIRMED',reason:'EMPTY',output_uncertain:false},events:[{event_id:0,sim_time:5,state:'OBSERVE',event:'STATE_OK',attempt:1},{event_id:1,sim_time:6,state:'SEAL',event:'STATE_FAILED',attempt:1,data:{reason:'SEAL_NOT_CONFIRMED'}},{event_id:2,sim_time:7,state:'RECOVERY',event:'RECOVERY_BEGIN',attempt:2},...(entry.success?[{event_id:3,sim_time:15,state:'VERIFY',event:'PLACEMENT_VERIFIED',attempt:3}]:[{event_id:3,sim_time:7,state:'SEAL',event:'RETRY_EXHAUSTED',attempt:3}])],frames:[{frame_id:0,sim_time:5,state:'OBSERVE',attempt:1,pressure_kpa:0,scene:'frames/0-scene.jpg',camera:'frames/0-camera.jpg',log_event_id:0,detections:[{sku:'UNKNOWN',confidence:.6,distance:.12}]},{frame_id:1,sim_time:6,state:'SEAL',attempt:1,pressure_kpa:-3,scene:'frames/1-scene.jpg',camera:'frames/1-camera.jpg',log_event_id:1},{frame_id:2,sim_time:entry.success?15:7,state:entry.status,attempt:3,pressure_kpa:0,scene:'frames/2-scene.jpg',camera:'frames/2-camera.jpg',log_event_id:3}]});
const requested=[];
const browserContext={URL,console,AbortSignal,performance:{now:()=>0},requestAnimationFrame:()=>1,cancelAnimationFrame(){},setTimeout:()=>1,clearTimeout(){},document:doc,window:{addEventListener(){}},fetch:async url=>{requested.push(String(url));const path=new URL(url,doc.baseURI).pathname;let payload;if(path.endsWith('/data/index.json'))payload={runs:fixtureRuns,source_version:'fixture',metrics_url:'data/metrics.json'};else if(path.endsWith('/data/metrics.json'))payload={aggregate:{naive:{n:1,completed:0},recovery:{n:1,completed:1,completion_rate:1,completion_seed_cluster95:[.6,1]}},contrasts:[{before:'naive',after:'recovery',n_pairs:1,after_only:1,before_only:0,completion_delta:1,seed_cluster_bootstrap95:[.5,1],seed_clusters:1}],conditions:[{fault:'suction_once',policy:'recovery',n:1,completed:1}]};else if(path.endsWith('/data/evidence.json'))payload=[{title:'실행 증거',description:'기록된 연동',links:[{label:'원문',url:'data/evidence/raw.json'}]}];else if(path==='/api/health')return {ok:false,status:404};else{const entry=fixtureRuns.find(r=>path.endsWith(`/data/runs/${r.policy}/run.json`));if(entry)payload=fixturePayload(entry);}return payload?{ok:true,json:async()=>payload}:{ok:false,status:404};}};
vm.createContext(browserContext);vm.runInContext(js,browserContext);
const settle=async()=>{for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));};
await settle();
check('runtime initializes actual naive/recovery comparison and nested run-relative image URLs',()=>{assert.equal(nodes.get('compare-left-policy').value,'naive');assert.equal(nodes.get('compare-right-policy').value,'recovery');assert.match(nodes.get('compare-left-image').src,/nested\/data\/runs\/naive\/frames\/0-scene\.jpg$/);assert.match(nodes.get('run-narrative').textContent,/SEAL_NOT_CONFIRMED.*재시도.*배치 검증 완료/);assert.equal(nodes.get('jump-failure').disabled,false);assert.match(nodes.get('detection-summary').textContent,/진단점수 0.600/);assert.doesNotMatch(nodes.get('detection-summary').textContent,/%/);assert.match(nodes.get('provenance-detail').textContent,/a{64}/);assert.equal(nodes.get('integration-evidence').hidden,false);});
nodes.get('compare-scrubber').value='6';nodes.get('compare-scrubber').trigger('input');
check('runtime scrubbing shares elapsed clock while short policy freezes final frame',()=>{assert.match(nodes.get('compare-left-image').src,/naive\/frames\/2-scene\.jpg$/);assert.match(nodes.get('compare-right-image').src,/recovery\/frames\/1-scene\.jpg$/);assert.match(nodes.get('compare-left-frame').textContent,/마지막 프레임 유지/);assert.equal(nodes.get('compare-time').textContent,'6.00 s');});
nodes.get('jump-failure').trigger('click');
check('runtime failure jump selects the exact bound frame',()=>{assert.equal(nodes.get('scrubber').value,'1');assert.match(nodes.get('event-detail-summary').textContent,/STATE_FAILED/);assert.match(nodes.get('scene-image').src,/recovery\/frames\/1-scene\.jpg$/);});
nodes.get('run-select').value='fixture-naive';nodes.get('run-select').trigger('change');await settle();nodes.get('scrubber').value='2';nodes.get('scrubber').trigger('input');
check('runtime terminal HELD keeps prior STATE_OK and distinguishes exhaustion and output policy',()=>{assert.match(nodes.get('task-steps').innerHTML,/완료 시도 1/);assert.match(nodes.get('phase-outcome').textContent,/단계 실패: 흡착/);assert.match(nodes.get('retry-outcome').textContent,/재시도 소진.*종료: 보류/);assert.match(nodes.get('hold-policy').textContent,/OFF 확인/);assert.equal(nodes.get('jump-placement').disabled,true);});
check('runtime metric intervals use seed clusters and show paired denominators',()=>{assert.match(nodes.get('evaluation-metrics').innerHTML,/seed-cluster 95%.*60.0.*100.0/);assert.match(nodes.get('metrics-contrasts').innerHTML,/n=1/);assert.match(nodes.get('metrics-contrasts').innerHTML,/100.0 %p/);assert.doesNotMatch(nodes.get('evaluation-metrics').innerHTML,/Wilson/);});
nodes.get('compare-left-policy').value='baseline';nodes.get('compare-left-policy').trigger('change');
check('comparison policy change clears stale frames and disables playback while loading',()=>{assert.equal(nodes.get('compare-left-image').hidden,true);assert.equal(nodes.get('compare-play').disabled,true);});
await settle();
check('comparison policy change loads the selected real baseline recording',()=>{assert.match(nodes.get('compare-left-image').src,/baseline\/frames\/0-scene\.jpg$/);assert.equal(nodes.get('compare-play').disabled,false);});
console.log(`\n${checks} UI contract checks passed.`);
