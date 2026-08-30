// 2026-08-30: падіння значення джерела після перезапуску HA більше НЕ вважається
// скиданням лічильника. Riemann-інтегратор відновлюється зі стану в recorder і може
// повернутися трохи нижчим за фактичний (5.6321 -> 5.5940 о 20:33:51, бо commit_interval
// 30 с не встиг записати останні прирости). Стара умова ':value' додавала тоді ВЕСЬ
// накопичений інтеграл у поточний стовпчик: 30.08 показало 5148 л замість 618 л,
// а погодинна картка - 4.2 м3 за годину. Скиданням тепер вважається лише падіння
// майже до нуля (<=10% попереднього значення), тобто реальне перестворення лічильника.
(function(){const tag='well-water-overview-card';if(customElements.get(tag))return;const CAL_LOG='sensor.zhurnal_pokaznykiv_vody';const calib=(hass,cfg)=>hass?.states[cfg.log_entity||CAL_LOG]?.attributes?.calibration||{};class WellWaterOverviewCard extends HTMLElement{
 setConfig(config){this.config=config;if(!config.energy_entity||!config.coefficient_entity)throw new Error('Потрібні energy_entity і coefficient_entity');this._renderLoading();}
 set hass(hass){this._hass=hass;const marker=[hass.states[this.config.energy_entity]?.last_updated||'',hass.states[this.config.coefficient_entity]?.state||''].join('|');if(marker!==this._marker){this._marker=marker;this._load();}}
 getCardSize(){return 3;}
 _esc(v){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
 _num(v){return Number(v).toLocaleString('uk-UA',{minimumFractionDigits:1,maximumFractionDigits:1});}
 _key(d){return new Intl.DateTimeFormat('en-CA',{timeZone:this.config.time_zone||'Europe/Kyiv',year:'numeric',month:'2-digit',day:'2-digit'}).format(d);}
 _renderLoading(){this.innerHTML=`<ha-card><div class="wrap"><b>${this._esc(this.config.title||'Вода')}</b><span>Завантажую…</span></div></ha-card><style>.wrap{padding:16px;display:flex;justify-content:space-between}</style>`;}
 async _load(){
  if(!this._hass)return;
  const now=new Date(),monthStart=new Date(now.getFullYear(),now.getMonth(),1,0,0,0),queryStart=new Date(monthStart.getTime()-2*86400000);
  const path='history/period/'+encodeURIComponent(queryStart.toISOString())+'?filter_entity_id='+encodeURIComponent(this.config.energy_entity)+'&end_time='+encodeURIComponent(now.toISOString())+'&minimal_response';
  try{
   const data=await this._hass.callApi('GET',path),states=(data&&data[0])||[],todayKey=this._key(now),monthPrefix=todayKey.slice(0,7),buckets=new Map();
   let prev=null;
   for(const s of states){const value=Number(s.state),ts=Date.parse(s.last_changed||s.last_updated||'');if(!Number.isFinite(value)||!Number.isFinite(ts))continue;if(prev){const delta=value>=prev.value?value-prev.value:(value<=prev.value*0.1?value:0);if(delta>0){const key=this._key(new Date(ts));if(key.startsWith(monthPrefix))buckets.set(key,(buckets.get(key)||0)+delta);}}prev={value,ts};}
   const offset=Number(calib(this._hass,this.config).energy_offset_kwh??this.config.energy_offset_kwh??0),offsetDate=(calib(this._hass,this.config).baseline_iso||'').slice(0,10)||this.config.offset_date;if(offset>0&&offsetDate?.startsWith(monthPrefix))buckets.set(offsetDate,(buckets.get(offsetDate)||0)+offset);
   const coef=Math.max(0,Number(this._hass.states[this.config.coefficient_entity]?.state||0)),today=(buckets.get(todayKey)||0)*coef*1000,month=[...buckets.values()].reduce((a,b)=>a+b,0)*coef*1000;
   this._render(today,month,coef);
  }catch(e){this.innerHTML=`<ha-card><div class="wrap err">Не вдалося порахувати воду</div></ha-card><style>.wrap{padding:16px}.err{color:var(--error-color)}</style>`;}
 }
 _render(today,month,coef){
  const href=this.config.navigation_path||'/sverdlovina-dashboard/well';
  this.innerHTML=`<ha-card><a class="wrap" href="${this._esc(href)}"><div class="head"><ha-icon icon="mdi:water"></ha-icon><b>${this._esc(this.config.title||'Вода свердловини')}</b><ha-icon class="go" icon="mdi:chevron-right"></ha-icon></div><div class="stats"><div><span>Сьогодні</span><strong>${this._num(today)} л</strong></div><div><span>Цього місяця</span><strong>${this._num(month)} л</strong></div></div><small>Розрахунок · ${Math.round(coef*1000).toLocaleString('uk-UA')} л/кВт·год</small></a></ha-card><style>.wrap{display:block;padding:16px;color:var(--primary-text-color);text-decoration:none}.head{display:flex;align-items:center;gap:8px;margin-bottom:14px}.head ha-icon{color:var(--primary-color)}.head .go{margin-left:auto;color:var(--secondary-text-color)}.stats{display:grid;grid-template-columns:1fr 1fr;gap:10px}.stats div{padding:11px;border-radius:11px;background:color-mix(in srgb,var(--primary-color) 10%,transparent)}span,small{display:block;color:var(--secondary-text-color);font-size:12px}strong{display:block;font-size:19px;margin-top:4px;font-variant-numeric:tabular-nums}small{margin-top:10px}</style>`;
 }
};customElements.define(tag,WellWaterOverviewCard);window.customCards=window.customCards||[];window.customCards.push({type:tag,name:'Вода свердловини для огляду',description:'Розрахункова вода сьогодні та за поточний місяць'});})();

(function(){
 if(window.__wellOverviewOverlayInstalled)return;
 window.__wellOverviewOverlayInstalled=true;
 const ID='well-overview-live-overlay',pumpEntity='switch.mini_switch_k601_2_switch_1_2';
 const getHass=()=>document.querySelector('home-assistant')?.hass;
 const page=()=>location.pathname.startsWith('/ohliad-dashboard')?'overview':location.pathname.startsWith('/pristroi-dashboard/poliv')?'poliv':'';
 const remove=()=>document.getElementById(ID)?.remove();
 async function nativeExists(kind,hass){
  try{const url_path=kind==='overview'?'ohliad-dashboard':'pristroi-dashboard',cfg=await hass.callWS({type:'lovelace/config',url_path}),raw=JSON.stringify(cfg);return kind==='overview'?raw.includes('well-water-overview-card')&&raw.includes('Насос поливу · ручне керування'):raw.includes('Насос поливу · ручне керування');}catch(e){return false;}
 }
 async function mount(){
  const kind=page(),hass=getHass();if(!kind||!hass){remove();return;}
  if(await nativeExists(kind,hass)){remove();return;}
  let root=document.getElementById(ID);
  if(!root){
   root=document.createElement('div');root.id=ID;
   root.innerHTML='<button class="pump"><ha-icon icon="mdi:water-pump"></ha-icon><span><b>Насос поливу</b><small></small></span><ha-icon class="toggle" icon="mdi:toggle-switch-off-outline"></ha-icon></button><div class="water"></div><style>#'+ID+'{position:fixed;right:18px;top:74px;z-index:8;width:min(390px,calc(100vw - 34px));filter:drop-shadow(0 8px 20px rgba(0,0,0,.28))}#'+ID+' .pump{box-sizing:border-box;width:100%;display:flex;align-items:center;gap:12px;padding:14px 16px;border:2px solid var(--primary-color);border-radius:14px;background:var(--card-background-color);color:var(--primary-text-color);font:inherit;text-align:left;cursor:pointer}#'+ID+' .pump>ha-icon{color:var(--primary-color);width:30px;height:30px}#'+ID+' .pump span{flex:1}#'+ID+' .pump b{display:block;font-size:17px}#'+ID+' .pump small{display:block;color:var(--secondary-text-color);margin-top:3px}#'+ID+' .pump.on{background:color-mix(in srgb,var(--primary-color) 18%,var(--card-background-color));border-color:var(--primary-color)}#'+ID+' .pump.on .toggle{color:var(--primary-color)}#'+ID+'[data-kind="overview"]{top:auto;bottom:18px}#'+ID+' .water{margin-top:10px}#'+ID+' .water:empty{display:none}@media(max-width:700px){#'+ID+'{top:auto;bottom:18px;right:12px;width:calc(100vw - 24px)}#'+ID+' .water{max-height:185px;overflow:auto}}</style>';
   document.body.appendChild(root);
   root.querySelector('.pump').addEventListener('click',()=>{const h=getHass();if(h)h.callService('switch','toggle',{entity_id:pumpEntity});});
  }
  root.dataset.kind=kind;
  const waterHost=root.querySelector('.water');
  if(kind==='overview'&&!waterHost.firstElementChild&&customElements.get('well-water-overview-card')){
   const card=document.createElement('well-water-overview-card');
   card.setConfig({title:'Вода свердловини · розрахунок',energy_entity:'sensor.t34_smart_plug_nasos_sverdlovini_spozhito',coefficient_entity:'input_number.sverdlovina_koefitsiient_vodi',time_zone:'Europe/Kyiv',navigation_path:'/sverdlovina-dashboard/well'});
   waterHost.appendChild(card);
  }else if(kind==='poliv')waterHost.innerHTML='';
  update();
 }
 function update(){
  const root=document.getElementById(ID),hass=getHass();if(!root||!hass)return;
  const on=hass.states[pumpEntity]?.state==='on',available=!['unavailable','unknown'].includes(hass.states[pumpEntity]?.state);
  const btn=root.querySelector('.pump');btn.classList.toggle('on',on);btn.disabled=!available;
  btn.querySelector('small').textContent=available?(on?'Увімкнений · натисніть, щоб вимкнути':'Вимкнений · натисніть, щоб увімкнути'):'Недоступний';
  btn.querySelector('.toggle').setAttribute('icon',on?'mdi:toggle-switch':'mdi:toggle-switch-off-outline');
  const card=root.querySelector('well-water-overview-card');if(card)card.hass=hass;
 }
 let last='';
 setInterval(()=>{const p=location.pathname;if(p!==last){last=p;mount();}else update();},1000);
 window.addEventListener('location-changed',()=>{last='';mount();});
 mount();
})();
