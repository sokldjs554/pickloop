import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
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
check('operator can reach the owner experiment and role evidence before the replay controls', () => {
  const heading = html.slice(0, html.indexOf('class="workspace-grid"'));
  assert.match(heading, /href="https:\/\/github.com\/sokldjs554\/pickloop\/pull\/1"/);
  assert.match(heading, /href="evidence.html"/);
  const trial = version => JSON.parse(readFileSync(resolve(root, `docs/experiments/retry-height/seed-200-${version}.json`)))
    .find(row => row.fault === 'calibration_error' && row.policy === 'recovery');
  const saving = (trial('before').sim_duration_s - trial('after').sim_duration_s).toFixed(3);
  assert.ok(heading.includes(saving) && heading.includes('seed 200'));
});
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
check('failure summary preserves stage and actual reason',()=>{assert.equal(failureSummary({events:[{event:'seal_failed',state:'SEAL',data:{reason:'PRESSURE_NOT_ESTABLISHED'}}]}),'흡착 / 흡착 압력 미성립');assert.equal(failureSummary({events:[]}),'감지된 실패 없음');});
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
check('same-time STATE_OK is hidden beyond the frame log-event boundary',()=>{const events=[{event_id:0,sim_time:0,state:'OBSERVE',event:'STATE_ENTER',attempt:1},{event_id:1,sim_time:0,state:'OBSERVE',event:'STATE_OK',attempt:1},{event_id:2,sim_time:0,state:'PLAN',event:'STATE_ENTER',attempt:1}];assert.equal(helpers.phaseHistory(events,0,0).find(p=>p.key==='OBSERVE').done,false);assert.equal(helpers.phaseHistory(events,0,1).find(p=>p.key==='OBSERVE').done,true);});
check('terminal valve policy is hidden before terminal even at identical simulation time',()=>{assert.equal(typeof helpers.terminalPolicyVisible,'function');const r=normalizeRun({status:'HELD',terminal_policy:{action:'OFF_CONFIRMED'},events:[{event_id:4,sim_time:3,event:'HOLD_POLICY'},{event_id:5,sim_time:3,event:'TERMINAL'}]});assert.equal(helpers.terminalPolicyVisible(r,{sim_time:3,state:'SEAL',log_event_id:3}),false);assert.equal(helpers.terminalPolicyVisible(r,{sim_time:3,state:'HELD',log_event_id:5}),true);});
check('narrative translates known causes and reports the actual placement attempt',()=>{const r=normalizeRun({policy:'recovery',status:'COMPLETED',success:true,events:[{event:'STATE_FAILED',state:'SEAL',attempt:1,sim_time:1,data:{reason:'SEAL_NOT_CONFIRMED'}},{event:'RECOVERY_END',attempt:2,sim_time:2,data:{next_attempt:2}},{event:'STATE_ENTER',state:'OBSERVE',attempt:2,sim_time:2},{event:'PLACEMENT_VERIFIED',state:'VERIFY',attempt:2,sim_time:8}]});const narrative=helpers.runNarrative(r);assert.match(narrative,/1차 시도.*흡착.*흡착 압력·부착 미확인/);assert.match(narrative,/재관측·재계획.*2차 시도/);assert.match(narrative,/2차 시도.*배치 검증 완료/);assert.doesNotMatch(narrative,/SEAL_NOT_CONFIRMED/);});
check('exhausted hold reports all failed attempts and the recorded valve decision', () => {
  const events = [1, 2, 3].map(attempt => ({
    event: 'STATE_FAILED', state: 'SEAL', attempt, data: {reason: 'SEAL_NOT_CONFIRMED'}
  }));
  events.push({event: 'RETRY_EXHAUSTED', attempt: 3, data: {retries: 2}},
    {event: 'HOLD_POLICY', attempt: 3, data: {action: 'OFF_CONFIRMED'}},
    {event: 'TERMINAL', attempt: 3, state: 'HELD'});
  const run = normalizeRun({status: 'HELD', events});
  assert.equal(helpers.runNarrative(run), '총 3회 시도에서 흡착 실패 → 재시도 2회 소진 → 밸브 OFF 확인 후 보류');
  events.at(-2).data.action = 'OFF_UNCONFIRMED';
  assert.match(helpers.runNarrative(run), /OFF 명령 결과 미확인/);
  events[0].state = 'OBSERVE';
  assert.doesNotMatch(helpers.runNarrative(run), /3회 시도에서 흡착 실패/);
});
// Execute the real browser script against a minimal DOM surface and deterministic
// recorded payloads. This checks loading, control bindings and time synchronization;
// it is not a substitute for browser layout/visual QA.
class Node {
  constructor(tag='div'){this.tag=tag;this._value='';this.children=[];this.dataset={};this.style={};this.attributes={};this.listeners={};this.hidden=false;this.disabled=false;this.textContent='';this.innerHTML='';this.naturalWidth=0;this.parentElement=this;this.classList={toggle(){}};}
  get value(){return this._value||this.children[0]?.value||'';}
  set value(v){this._value=String(v);}
  replaceChildren(...children){this.children=children;this._value='';}
  append(...children){this.children.push(...children);}
  prepend(...children){this.children.unshift(...children);}
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
const fixtureRuns=policies.map(policy=>({run_id:`fixture-${policy}`,job_id:`job-${policy}`,seed:7,fault:'suction_once',policy,recording_equivalent:policy!=='naive',evaluation_url:'data/evaluation/original/run.json',condition_id:'c'.repeat(64),sku:'SKU-RED-A',status:policy==='recovery'?'COMPLETED':'HELD',success:policy==='recovery',retries:policy==='baseline'?0:2,run_url:`data/runs/${policy}/run.json`}));
const fixturePayload=entry=>({...entry,provenance:{source_sha256:'a'.repeat(64),model_sha256:'b'.repeat(64)},terminal_policy:entry.success?undefined:{action:'OFF_CONFIRMED',reason:'EMPTY',output_uncertain:false},events:[{event_id:0,sim_time:5,state:'OBSERVE',event:'STATE_OK',attempt:1},{event_id:1,sim_time:6,state:'SEAL',event:'STATE_FAILED',attempt:1,data:{reason:'SEAL_NOT_CONFIRMED'}},{event_id:2,sim_time:7,state:'RECOVERY',event:'RECOVERY_BEGIN',attempt:2},...(entry.success?[{event_id:3,sim_time:15,state:'VERIFY',event:'PLACEMENT_VERIFIED',attempt:3}]:[{event_id:3,sim_time:7,state:'SEAL',event:'RETRY_EXHAUSTED',attempt:3}])],frames:[{frame_id:0,sim_time:5,observation_id:'fixture-obs-0123',state:'OBSERVE',attempt:1,pressure_kpa:0,scene:'frames/0-scene.jpg',camera:'frames/0-camera.jpg',log_event_id:0,detections:[{sku:'UNKNOWN',confidence:.6,distance:.12}]},{frame_id:1,sim_time:6,state:'SEAL',attempt:1,pressure_kpa:-3,scene:'frames/1-scene.jpg',camera:'frames/1-camera.jpg',log_event_id:1},{frame_id:2,sim_time:entry.success?15:7,state:entry.status,attempt:3,pressure_kpa:0,scene:'frames/2-scene.jpg',camera:'frames/2-camera.jpg',log_event_id:3}]});
const requested=[];
const browserContext={URL,console,AbortSignal,performance:{now:()=>0},requestAnimationFrame:()=>1,cancelAnimationFrame(){},setTimeout:()=>1,clearTimeout(){},document:doc,window:{addEventListener(){}},fetch:async url=>{requested.push(String(url));const path=new URL(url,doc.baseURI).pathname;let payload;if(path.endsWith('/data/index.json'))payload={runs:fixtureRuns,source_version:'fixture',metrics_url:'data/metrics.json'};else if(path.endsWith('/data/metrics.json'))payload={aggregate:{naive:{n:1,completed:0},recovery:{n:1,completed:1,completion_rate:1,completion_seed_cluster95:[.6,1]}},contrasts:[{before:'naive',after:'recovery',n_pairs:1,after_only:1,before_only:0,completion_delta:1,seed_cluster_bootstrap95:[.5,1],seed_clusters:1}],conditions:[{fault:'suction_once',policy:'recovery',n:1,completed:1}]};else if(path.endsWith('/data/evidence.json'))payload=[{title:'실행 증거',description:'기록된 연동',links:[{label:'원문',url:'data/evidence/raw.json'}]}];else if(path.endsWith('/evaluation/original/run.json'))payload={status:'HELD',reason:'DEVICE_UNCERTAIN',sim_duration_s:12.465};else if(path==='/api/health')return {ok:false,status:404};else{const entry=fixtureRuns.find(r=>path.endsWith(`/data/runs/${r.policy}/run.json`));if(entry)payload=fixturePayload(entry);}return payload?{ok:true,json:async()=>payload}:{ok:false,status:404};}};
vm.createContext(browserContext);vm.runInContext(js,browserContext);
const settle=async()=>{for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));};
await settle();
check('runtime initializes actual naive/recovery comparison and nested run-relative image URLs',()=>{assert.equal(nodes.get('compare-left-policy').value,'naive');assert.match(nodes.get('compare-left-status').textContent,/원평가와 다른 결과/);assert.equal(nodes.get('observation-id').textContent,'관측 123');assert.equal(nodes.get('observation-id').title,'fixture-obs-0123');assert.equal(nodes.get('compare-right-policy').value,'recovery');assert.match(nodes.get('compare-left-image').src,/nested\/data\/runs\/naive\/frames\/0-scene\.jpg$/);assert.match(nodes.get('run-narrative').textContent,/흡착 압력·부착 미확인.*재시도.*3차 시도.*배치 검증 완료/);assert.equal(nodes.get('jump-failure').disabled,false);assert.match(nodes.get('detection-summary').textContent,/진단점수 0.600/);assert.doesNotMatch(nodes.get('detection-summary').textContent,/%/);assert.match(nodes.get('provenance-detail').textContent,/a{64}/);assert.equal(nodes.get('integration-evidence').hidden,false);});
nodes.get('compare-scrubber').value='6';nodes.get('compare-scrubber').trigger('input');
check('runtime scrubbing shares elapsed clock while short policy freezes final frame',()=>{assert.match(nodes.get('compare-left-image').src,/naive\/frames\/2-scene\.jpg$/);assert.match(nodes.get('compare-right-image').src,/recovery\/frames\/1-scene\.jpg$/);assert.match(nodes.get('compare-left-frame').textContent,/마지막 프레임 유지/);assert.equal(nodes.get('compare-time').textContent,'6.00 s');});
nodes.get('jump-failure').trigger('click');
check('runtime failure jump selects the exact bound frame',()=>{assert.equal(nodes.get('scrubber').value,'1');assert.match(nodes.get('event-detail-summary').textContent,/단계 실패/);assert.match(nodes.get('event-json').textContent,/STATE_FAILED/);assert.match(nodes.get('scene-image').src,/recovery\/frames\/1-scene\.jpg$/);});
nodes.get('run-select').value='fixture-naive';nodes.get('run-select').trigger('change');await settle();check('terminal output policy is not shown on the initial replay frame',()=>{assert.equal(nodes.get('hold-policy').hidden,true);});nodes.get('scrubber').value='2';nodes.get('scrubber').trigger('input');
check('runtime terminal HELD keeps prior STATE_OK and distinguishes exhaustion and output policy',()=>{assert.match(nodes.get('task-steps').innerHTML,/완료 시도 1/);assert.match(nodes.get('phase-outcome').textContent,/단계 실패: 흡착/);assert.match(nodes.get('retry-outcome').textContent,/재시도 소진.*종료: 보류/);assert.match(nodes.get('hold-policy').textContent,/OFF 확인/);assert.equal(nodes.get('jump-placement').disabled,true);});
check('runtime metric intervals use seed clusters and show paired denominators',()=>{assert.match(nodes.get('confidence-values').innerHTML,/60.0–100.0%/);assert.doesNotMatch(nodes.get('evaluation-metrics').innerHTML,/60.0–100.0/);assert.match(nodes.get('metrics-contrasts').innerHTML,/n=1/);assert.match(nodes.get('metrics-contrasts').innerHTML,/100\.00 %p/);assert.doesNotMatch(nodes.get('evaluation-metrics').innerHTML,/Wilson/);});
nodes.get('compare-left-policy').value='baseline';nodes.get('compare-left-policy').trigger('change');
check('comparison policy change clears stale frames and disables playback while loading',()=>{assert.equal(nodes.get('compare-left-image').hidden,true);assert.equal(nodes.get('compare-play').disabled,true);});
await settle();
check('comparison policy change loads the selected real baseline recording',()=>{assert.match(nodes.get('compare-left-image').src,/baseline\/frames\/0-scene\.jpg$/);assert.equal(nodes.get('compare-play').disabled,false);});
check('compact IDs keep full values in titles and raw details',()=>{assert.equal(helpers.shortObservation('fixture-obs-0123'),'관측 123');assert.equal(nodes.get('comparison-condition').textContent.includes('c'.repeat(64)),false);assert.equal(nodes.get('comparison-condition').title,'c'.repeat(64));assert.equal(nodes.get('run-select').children[0].textContent.includes('fixture-'),false);assert.match(nodes.get('run-select').children[0].title,/fixture-/);});
check('interrupted recovery does not claim a subsequent attempt was executed',()=>{const r=normalizeRun({policy:'recovery',status:'HELD',events:[{event:'STATE_FAILED',state:'SEAL',attempt:1,sim_time:1,data:{reason:'SEAL_NOT_CONFIRMED'}},{event:'RECOVERY_BEGIN',state:'RECOVERY',attempt:1,sim_time:1}]});assert.doesNotMatch(helpers.runNarrative(r),/후 재시도/);assert.match(helpers.runNarrative(r),/복구 절차 시작/);});
check('carried-payload recovery describes replanning without claiming reobservation',()=>{const r=normalizeRun({policy:'recovery',status:'COMPLETED',success:true,events:[{event:'STATE_FAILED',state:'TRANSPORT',attempt:1,data:{reason:'PATH_BLOCKED'}},{event:'RECOVERY_BEGIN',state:'RECOVERY',attempt:1},{event:'RECOVERY_END',state:'RECOVERY',attempt:2,data:{holding_payload:true,next_attempt:2}},{event:'STATE_ENTER',state:'OBSERVE',attempt:2},{event:'PLACEMENT_VERIFIED',state:'VERIFY',attempt:2}]});assert.match(helpers.runNarrative(r),/흡착 유지·운반 경로 재계획/);assert.doesNotMatch(helpers.runNarrative(r),/재관측/);});
check('mismatch table contains both source records and resets when compare selection changes', () => {
  const panel = nodes.get('selected-outcomes');
  assert.equal(panel.hidden, false);
  assert.match(panel.innerHTML, /장치 상태 불확실/);
  assert.match(panel.innerHTML, /12\.465초/);
  assert.match(panel.innerHTML, /nested\/data\/evaluation\/original\/run\.json/);
  assert.match(panel.innerHTML, /nested\/data\/runs\/naive\/run\.json/);
  assert.equal(nodes.get('paired-outcomes').hidden, true);
});
check('score help and confidence intervals start in closed native disclosures', () => {
  assert.match(html, /<details class="diagnostic-help"><summary>진단점수 해석/);
  assert.match(html, /<details id="confidence-details" class="confidence-details" hidden>/);
});
check('published photo results match the frozen gallery evaluation', () => {
  const page = readFileSync(resolve(root, 'web/evidence.html'), 'utf8');
  const {partitions} = JSON.parse(readFileSync(resolve(root, 'docs/experiments/carton-panels/summary.json'), 'utf8'));
  const row = page.match(/<tr id="panel-result">([\s\S]*?)<\/tr>/);
  assert.ok(row, 'missing photo recognition result');
  const cells = [...row[1].matchAll(/<td>(.*?)<\/td>/g)].map(match => match[1]);
  const {test_cartons: carton, test_produce: produce} = partitions;
  assert.deepEqual(cells.slice(1), [
    `${carton.known_correct} / ${carton.known_total}`, `${carton.unknown_false_accepts} / ${carton.unknown_total}`,
    `${produce.unknown_false_accepts} / ${produce.unknown_total.toLocaleString('en-US')}`
  ]);
  assert.match(page, /docs\/experiments\/carton-panels\/predictions\.csv/);
});
const evidencePage = readFileSync(resolve(root, 'web/evidence.html'), 'utf8');
const catalogueScript = readFileSync(resolve(root, 'web/grocery-catalogue.js'), 'utf8');
function openCatalogue(data, lookup = null, requests = [], hash = '') {
  const elements = new Map([...evidencePage.matchAll(/\bid="([^"]+)"/g)].map(match => [match[1], new Node()]));
  const document = {getElementById: id => elements.get(id), createElement: tag => new Node(tag)};
  elements.get('photo-filter').value = 'review';
  const fetch = async path => {
    requests.push(path);
    const payloads = {'data/grocery-catalogue.json':data, 'data/grocery-previous-photos.json':lookup};
    assert.ok(Object.hasOwn(payloads, path));
    return {ok: payloads[path] !== null, json: async () => payloads[path]};
  };
  vm.runInNewContext(catalogueScript, {document, fetch, console, location: {hash}});
  return id => elements.get(id);
}
const products = ['Golden-Delicious', 'Granny-Smith', 'Pink-Lady', 'Red-Delicious', 'Royal-Gala',
  'Avocado', 'Banana', 'Kiwi', 'Mango', 'Bravo-Apple-Juice', 'Carrots'];
const catalogueFixture = {
  counts: {registered: 11, test_total: 44, correct: 20, wrong: 11, held: 13, outside_total: 5, outside_false_accepts: 2},
  previous_unknown: {total: 7, correct: 4, wrong: 2, held: 1},
  classes: products.map((name, id) => ({id, name, group: id === 10 ? 'Vegetables' : id === 9 ? 'Packages' : 'Fruit',
    test_total: 4, correct: id === 0 ? 0 : 2, wrong: 1, held: id === 0 ? 3 : 1}))
};
const view = openCatalogue(catalogueFixture);
await settle();
check('review page links to the full catalogue and preserves the earlier two-juice evidence', () => {
  assert.match(html, /href="evidence.html#photos"/);
  assert.ok(evidencePage.indexOf('id="photos"') < evidencePage.indexOf('id="panel-result"'));
  for (const path of ['docs/grocery-catalogue.md', 'docs/experiments/grocery-catalogue/predictions.csv']) {
    assert.ok(evidencePage.includes('https://github.com/sokldjs554/pickloop/blob/main/' + path));
  }
});
check('catalogue reads measured official, prior and external results with separate denominators', () => {
  assert.equal(view('catalogue-results').hidden, false);
  assert.match(view('catalogue-coverage').textContent, /11종.*10종/);
  assert.deepEqual(['test-total','correct','wrong','held'].map(key => view('catalogue-' + key).textContent), ['44','20','11','13']);
  assert.match(view('catalogue-previous').textContent, /7장.*4장.*2장.*1장/);
  assert.match(view('catalogue-outside').textContent, /5장.*2장/);
});
check('catalogue paginates and searches official names, Korean labels and item IDs across all pages', () => {
  const rows = view('catalogue-rows');
  const search = view('catalogue-search');
  const setQuery = query => {search.value = query; search.trigger('input');};
  assert.ok(rows.children.length > 0 && rows.children.length < products.length);
  assert.equal(view('catalogue-prev').disabled, true);
  view('catalogue-next').trigger('click');
  assert.equal(view('catalogue-prev').disabled, false);
  assert.equal(view('catalogue-next').disabled, true);
  setQuery('bravo apple');
  assert.equal(rows.children.length, 1);
  assert.deepEqual(rows.children[0].children.slice(1).map(cell => cell.textContent), ['4','2','1','1']);
  assert.equal(view('catalogue-prev').disabled, true);
  setQuery('당근');
  assert.equal(rows.children.length, 1);
  assert.deepEqual(rows.children[0].children[0].children.map(node => node.textContent), ['당근', '#10 · Carrots']);
  setQuery('6');
  assert.equal(rows.children.length, 1);
  setQuery('카탈로그에 없는 상품');
  assert.equal(rows.children.length, 0);
  assert.match(view('catalogue-position').textContent, /검색 결과가 없습니다/);
  setQuery('');
  view('catalogue-group').value = 'Vegetables';
  view('catalogue-group').trigger('change');
  assert.equal(rows.children.length, 1);
});
const failedView = openCatalogue(null);
await settle();
check('missing catalogue evidence has a visible error and the historical page still renders', () => {
  assert.match(failedView('catalogue-status').textContent, /불러오지 못했습니다/);
  assert.equal(failedView('catalogue-results').hidden, true);
  assert.ok(failedView('panel-result'));
});
const measuredCatalogue = JSON.parse(readFileSync(resolve(root, 'web/data/grocery-catalogue.json'), 'utf8'));
const lookup = JSON.parse(readFileSync(resolve(root, 'web/data/grocery-previous-photos.json'), 'utf8'));
const requests = [];
const measured = openCatalogue(measuredCatalogue, lookup, requests);
await settle();
check('photo lookup matches the pinned audit ledgers and initially loads no photo list', () => {
  execFileSync('python3', ['scripts/export_previous_photos.py', '--check'], {cwd:root});
  assert.equal(lookup.photos.length, 2656);
  assert.equal(new Set(lookup.photos.map(row => row.id)).size, lookup.photos.length);
  assert.match(evidencePage, /<details id="previous-photos"[^>]*>/);
  assert.doesNotMatch(evidencePage, /<details id="previous-photos"[^>]* open/);
  assert.deepEqual(requests, ['data/grocery-catalogue.json']);
  assert.equal(measured('photo-lookup').hidden, true);
});
const linkedPhotos = openCatalogue(measuredCatalogue, lookup, [], '#previous-photos');
await settle();
check('a direct link opens and loads the historical photo lookup', () => {
  assert.equal(linkedPhotos('previous-photos').open, true);
  assert.equal(linkedPhotos('photo-lookup').hidden, false);
});
function expand(el) { el.open = true; el.trigger('toggle'); }
expand(measured('previous-photos'));
await settle();
function filterPhotos(status, query = '') {
  measured('photo-filter').value = status;
  measured('photo-filter').trigger('change');
  measured('photo-search').value = query;
  measured('photo-search').trigger('input');
}
const photoRows = measured('photo-rows');
check('photo review defaults to errors and holds, pages subsets and links to pinned original images', () => {
  assert.equal(measured('photo-lookup').hidden, false);
  assert.deepEqual(requests, ['data/grocery-catalogue.json', 'data/grocery-previous-photos.json']);
  assert.equal(photoRows.children.length, 8);
  const before = photoRows.children[0].children[0].children[0].href;
  measured('photo-next').trigger('click');
  assert.notEqual(photoRows.children[0].children[0].children[0].href, before);
  const wrong = lookup.photos.find(photo => photo.status === 'wrong');
  assert.ok(wrong);
  filterPhotos('wrong', wrong.id);
  assert.equal(photoRows.children.length, 1);
  assert.equal(measured('photo-prev').disabled, true);
  const [file, truth, prediction, status] = photoRows.children[0].children;
  assert.equal(truth.children[1].textContent, wrong.truth);
  assert.equal(prediction.children[1].textContent, wrong.prediction);
  assert.equal(status.textContent, '오답');
  assert.equal(file.children[1].title, wrong.id);
  assert.equal(file.children[0].href, lookup.source_base + wrong.path);
  assert.equal(file.children[0].children[0].src, file.children[0].href);
  assert.equal(file.children[0].children[0].loading, 'lazy');
  assert.match(file.children[0].href, /^https:\/\/raw\.githubusercontent\.com\/marcusklasson\/GroceryStoreDataset\/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc\/dataset\//);
  assert.equal(file.children[0].textContent, wrong.path.split('/').at(-1));
});
check('all photos can be searched by Korean label, path or hash, including held photos and correct calls', () => {
  filterPhotos('all');
  assert.match(measured('photo-position').textContent, /2,656장/);
  filterPhotos('all', '당근');
  assert.ok(photoRows.children.length > 0);
  assert.ok(photoRows.children.every(row => [row.children[1], row.children[2]].some(cell => cell.children[0]?.textContent === '당근')));
  for (const outcome of ['correct', 'held']) {
    const item = lookup.photos.find(photo => photo.status === outcome);
    filterPhotos(outcome, item.path);
    assert.equal(photoRows.children.length, 1);
    const prediction = photoRows.children[0].children[2];
    if (outcome === 'held') assert.equal(prediction.textContent, '판정 보류');
    else assert.equal(prediction.children[1].textContent, item.truth);
  }
  filterPhotos('all', 'no-photo-for-this-query');
  assert.match(measured('photo-position').textContent, /검색 결과가 없습니다/);
});
const stale = openCatalogue(catalogueFixture, lookup);
await settle();
expand(stale('previous-photos'));
await settle();
check('a mismatched photo lookup shows an error while the aggregate evidence stays visible', () => {
  assert.equal(stale('catalogue-results').hidden, false);
  assert.equal(stale('photo-lookup').hidden, true);
  assert.match(stale('photo-load-status').textContent, /불러오지 못했습니다/);
});
check('both entry points show a native video with its real poster, captions and recorded-event jumps', () => {
  const run = JSON.parse(readFileSync(resolve(root,'web/data/runs/suction_once-3000-recovery-aaff86/run.json')));
  const elapsed = event => run.events.find(event).sim_time - run.frames[0].sim_time;
  const marks = [elapsed(e => e.event === 'STATE_FAILED'), elapsed(e => e.state === 'TRANSPORT' && e.event === 'STATE_ENTER'), elapsed(e => e.event === 'PLACEMENT_VERIFIED')];
  for (const markup of [html, evidencePage]) {
    assert.ok(markup.indexOf('id="work-scene"') < markup.indexOf(markup === html ? 'id="notice"' : 'id="personal"'));
    assert.match(markup, /<video controls muted playsinline[^>]+poster="media\/picking-recovery.jpg"/);
    assert.match(markup, /<source src="media\/picking-recovery.mp4" type="video\/mp4">/);
    assert.match(markup, /<track kind="captions"[^>]+src="media\/picking-recovery.ko.vtt"/);
    assert.match(markup, /\?run=suction_once-3000-recovery-aaff86#recorded-view/);
    const jumps = [...markup.matchAll(/data-elapsed="([.\d]+)"/g)].map(m => Number(m[1]));
    assert.equal(jumps.length, marks.length);
    for (let i=0; i<marks.length; i++) assert.ok(Math.abs(jumps[i] - marks[i]) <= .05);
  }
});
check('each featured shop photograph matches the actual outcome in the previous-unknown ledger', () => {
  const examples = [...evidencePage.matchAll(/<figure><a href="(https:[^"]+)"><img[^>]+src="([^"]+)"[^>]*><\/a><figcaption><strong class="(correct|wrong|held)">/g)];
  assert.equal(examples.length, 3);
  for (const [,link,src,status] of examples) {
    assert.equal(src,link);
    assert.equal(lookup.photos.find(photo => lookup.source_base + photo.path === src)?.status,status);
  }
});
check('scene chapters seek after metadata arrives, including under reduced motion', () => {
  const film = new Node('video');
  film.play = async () => {film.paused=false;};
  film.load = () => {};
  film.focus = () => {};
  film.pause = () => {film.paused=true;};
  film.readyState=0; film.paused=true;
  film.querySelector = () => new Node('source');
  const chapter = new Node('a');
  chapter.dataset.elapsed='14.00';
  let onVisibility;
  class Observer {
    constructor(callback) {onVisibility=callback;}
    observe() {}
  }
  vm.runInNewContext(readFileSync(resolve(root,'web/work-scene.js'),'utf8'), {
    window:{matchMedia:()=>({matches:true}),IntersectionObserver:Observer},IntersectionObserver:Observer,
    document:{getElementById:()=>({querySelector:()=>film,querySelectorAll:()=>[chapter]})}
  });
  onVisibility([{isIntersecting:true,intersectionRatio:1}]);
  assert.equal(film.paused,true);
  chapter.trigger('click');
  film.readyState=1;
  film.trigger('loadedmetadata');
  assert.equal(film.currentTime,14);
  assert.equal(film.paused,false);
  onVisibility([{isIntersecting:false,intersectionRatio:0}]);
  assert.equal(film.paused,true);
});
async function exerciseUnavailableVideo(responseOk, reduced) {
  const film=new Node('video'), source=new Node('source'), fallback=new Node('a'), img=new Node('img');
  source.src='media/picking-recovery.mp4'; img.dataset.animation='media/picking-transport.gif'; img.src='poster.jpg';
  fallback.hidden=true; fallback.querySelector=()=>img; film.querySelector=()=>source;
  const window={matchMedia:()=>({matches:reduced}),addEventListener(){}};
  const scene={querySelector:s=>s==='video'?film:fallback,querySelectorAll:()=>[]};
  vm.runInNewContext(readFileSync(resolve(root,'web/work-scene.js'),'utf8'), {
    window, document:{getElementById:()=>scene},
    URL:{createObjectURL:()=>'blob:local-video'},
    fetch:async()=>({ok:responseOk,blob:async()=>({})})
  });
  source.trigger('error');
  await settle();
  return {film,fallback,img};
}
const blobPlayback=await exerciseUnavailableVideo(true,false);
const gifPlayback=await exerciseUnavailableVideo(false,false);
const stillPlayback=await exerciseUnavailableVideo(false,true);
check('unavailable native playback retries from a Blob and provides a real scene when the MP4 is unavailable', () => {
  assert.equal(blobPlayback.film.src,'blob:local-video');
  blobPlayback.film.trigger('error');
  assert.equal(blobPlayback.fallback.hidden,false);
  assert.equal(gifPlayback.film.hidden,true);
  assert.equal(gifPlayback.img.src,'media/picking-transport.gif');
  assert.equal(stillPlayback.fallback.hidden,false);
  assert.equal(stillPlayback.img.src,'poster.jpg');
});
console.log(`\n${checks} UI contract checks passed.`);
