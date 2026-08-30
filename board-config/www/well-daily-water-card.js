// 2026-08-30: падіння значення джерела після перезапуску HA більше НЕ вважається
// скиданням лічильника. Riemann-інтегратор відновлюється зі стану в recorder і може
// повернутися трохи нижчим за фактичний (5.6321 -> 5.5940 о 20:33:51, бо commit_interval
// 30 с не встиг записати останні прирости). Стара умова ':value' додавала тоді ВЕСЬ
// накопичений інтеграл у поточний стовпчик: 30.08 показало 5148 л замість 618 л,
// а погодинна картка - 4.2 м3 за годину. Скиданням тепер вважається лише падіння
// майже до нуля (<=10% попереднього значення), тобто реальне перестворення лічильника.
(function(){const tag='well-daily-water-card';if(customElements.get(tag))return;const CAL_LOG='sensor.zhurnal_pokaznykiv_vody';const calib=(hass,cfg)=>hass?.states[cfg.log_entity||CAL_LOG]?.attributes?.calibration||{};class WellDailyWaterCard extends HTMLElement{
 setConfig(config){this.config=config;if(!config.energy_entity||!config.coefficient_entity)throw new Error('Потрібні energy_entity і coefficient_entity');this._renderLoading();}
 set hass(hass){this._hass=hass;const marker=[hass.states[this.config.energy_entity]?.last_updated||'',hass.states[this.config.coefficient_entity]?.state||''].join('|');if(marker!==this._marker){this._marker=marker;this._load();}}
 getCardSize(){return 8;}
 _esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
 _num(v,n=1){return Number(v).toLocaleString('uk-UA',{minimumFractionDigits:n,maximumFractionDigits:n});}
 _dayKey(d){return new Intl.DateTimeFormat('en-CA',{timeZone:this.config.time_zone||'Europe/Kyiv',year:'numeric',month:'2-digit',day:'2-digit'}).format(d);}
 _label(key,full=false){const d=new Date(key+'T12:00:00');return d.toLocaleDateString('uk-UA',full?{day:'2-digit',month:'2-digit',year:'numeric'}:{day:'2-digit',month:'2-digit'});}
 _renderLoading(){this.innerHTML=`<ha-card><div class="wrap"><h2>${this._esc(this.config.title||'Розрахункова вода за днями')}</h2><p>Завантажую історію енергії…</p></div></ha-card><style>.wrap{padding:16px}h2{font-size:20px;margin:0 0 12px}p{color:var(--secondary-text-color)}</style>`;}
 async _load(){
  if(!this._hass)return;
  const days=this.config.days||30,end=new Date(),start=new Date(end.getTime()-(days+2)*86400000);
  const path='history/period/'+encodeURIComponent(start.toISOString())+'?filter_entity_id='+encodeURIComponent(this.config.energy_entity)+'&end_time='+encodeURIComponent(end.toISOString())+'&minimal_response';
  try{
   const data=await this._hass.callApi('GET',path),states=(data&&data[0])||[];
   const buckets=new Map(),keys=[];
   const noon=new Date();noon.setHours(12,0,0,0);
   for(let i=days-1;i>=0;i--){const d=new Date(noon);d.setDate(d.getDate()-i);const k=this._dayKey(d);keys.push(k);buckets.set(k,0);}
   let prev=null;
   for(const s of states){const value=Number(s.state),ts=Date.parse(s.last_changed||s.last_updated||'');if(!Number.isFinite(value)||!Number.isFinite(ts))continue;if(prev){const delta=value>=prev.value?value-prev.value:(value<=prev.value*0.1?value:0);if(delta>0){const k=this._dayKey(new Date(ts));if(buckets.has(k))buckets.set(k,buckets.get(k)+delta);}}prev={value,ts};}
   const offset=Number(calib(this._hass,this.config).energy_offset_kwh??this.config.energy_offset_kwh??0),offsetDate=(calib(this._hass,this.config).baseline_iso||'').slice(0,10)||this.config.offset_date;if(offset>0&&offsetDate&&buckets.has(offsetDate))buckets.set(offsetDate,buckets.get(offsetDate)+offset);
   const coef=Number(this._hass.states[this.config.coefficient_entity]?.state||0);
   const liters=keys.map(k=>Math.max(0,buckets.get(k)||0)*Math.max(0,coef)*1000);
   this._render(keys,liters,coef);
  }catch(e){this.innerHTML=`<ha-card><div class="wrap"><h2>${this._esc(this.config.title||'Розрахункова вода за днями')}</h2><p class="err">Не вдалося завантажити історію: ${this._esc(e?.message||e)}</p></div></ha-card><style>.wrap{padding:16px}.err{color:var(--error-color)}</style>`;}
 }
 _render(keys,liters,coef){
  const total=liters.reduce((a,b)=>a+b,0),today=liters[liters.length-1]||0,avg=total/Math.max(1,keys.length);
  const W=1200,H=430,L=62,R=22,T=35,B=72,PW=W-L-R,PH=H-T-B,max=Math.max(1,...liters)*1.12,bw=PW/keys.length;
  let svg='';
  for(let i=0;i<=4;i++){const val=max*i/4,y=T+PH-(PH*i/4);svg+=`<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" class="grid"/><text x="${L-8}" y="${y+5}" text-anchor="end" class="axis">${this._num(val,0)}</text>`;}
  for(let i=0;i<keys.length;i++){const v=liters[i],h=v/max*PH,x=L+i*bw+bw*.14,y=T+PH-h;svg+=`<rect x="${x}" y="${y}" width="${Math.max(2,bw*.72)}" height="${Math.max(v>0?2:0,h)}" rx="3" class="bar"><title>${this._label(keys[i],true)}: ${this._num(v,1)} л</title></rect>`;if(i%5===0||i===keys.length-1)svg+=`<text x="${L+i*bw+bw/2}" y="${H-42}" text-anchor="middle" class="axis date">${this._label(keys[i])}</text>`;}
  const note=coef>0?`Чинний коефіцієнт: ${this._num(coef*1000,0)} л/кВт·год. Після нового механічного показника весь графік автоматично перераховується.`:'Очікується коефіцієнт калібрування.';
  this.innerHTML=`<ha-card><div class="wrap"><h2>${this._esc(this.config.title||'Розрахункова вода за днями')}</h2><div class="stats"><div><span>Сьогодні</span><b>${this._num(today,1)} л</b></div><div><span>За 30 днів</span><b>${this._num(total,1)} л</b></div><div><span>Розрахункова середня</span><b>${this._num(avg,1)} л/день</b></div></div><div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Розрахункова витрата води по днях за останні 30 днів">${svg}<text x="18" y="${T+PH/2}" text-anchor="middle" transform="rotate(-90 18 ${T+PH/2})" class="axis unit">літрів на день</text></svg></div><div class="legend"><i></i> Розрахунок за енергією насоса</div><p>${this._esc(note)}</p></div></ha-card><style>.wrap{padding:16px}h2{font-size:20px;margin:0 0 14px}.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:12px}.stats div{padding:12px;border-radius:12px;background:color-mix(in srgb,var(--primary-color) 9%,transparent)}.stats span{display:block;color:var(--secondary-text-color);font-size:12px;margin-bottom:5px}.stats b{font-size:18px;font-variant-numeric:tabular-nums}.chart{overflow-x:auto}svg{display:block;width:100%;min-width:720px;height:auto}.grid{stroke:var(--divider-color);stroke-width:1}.axis{fill:var(--secondary-text-color);font:14px sans-serif}.date{font-size:13px}.unit{font-size:13px}.bar{fill:var(--primary-color);opacity:.86}.bar:hover{opacity:1}.legend{font-size:13px;color:var(--secondary-text-color);margin-top:2px}.legend i{display:inline-block;width:11px;height:11px;border-radius:3px;background:var(--primary-color);vertical-align:-1px;margin-right:5px}p{margin:10px 0 0;color:var(--secondary-text-color);font-size:13px}@media(max-width:700px){.stats{grid-template-columns:1fr}.stats b{font-size:17px}}</style>`;
 }
};customElements.define(tag,WellDailyWaterCard);window.customCards=window.customCards||[];window.customCards.push({type:tag,name:'Розрахункова вода за 30 днів',description:'Добова витрата води з історії енергії насоса'});})();
