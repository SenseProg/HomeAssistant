// 2026-08-30: падіння значення джерела після перезапуску HA більше НЕ вважається
// скиданням лічильника. Riemann-інтегратор відновлюється зі стану в recorder і може
// повернутися трохи нижчим за фактичний (5.6321 -> 5.5940 о 20:33:51, бо commit_interval
// 30 с не встиг записати останні прирости). Стара умова ':value' додавала тоді ВЕСЬ
// накопичений інтеграл у поточний стовпчик: 30.08 показало 5148 л замість 618 л,
// а погодинна картка - 4.2 м3 за годину. Скиданням тепер вважається лише падіння
// майже до нуля (<=10% попереднього значення), тобто реальне перестворення лічильника.
(function(){const tag='well-hourly-water-card';if(customElements.get(tag))return;const CAL_LOG='sensor.zhurnal_pokaznykiv_vody';const calib=(hass,cfg)=>hass?.states[cfg.log_entity||CAL_LOG]?.attributes?.calibration||{};class WellHourlyWaterCard extends HTMLElement{
 setConfig(config){this.config=config;if(!config.energy_entity||!config.coefficient_entity)throw new Error('Потрібні energy_entity і coefficient_entity');this._loading();}
 set hass(hass){this._hass=hass;const marker=[hass.states[this.config.energy_entity]?.last_updated||'',hass.states[this.config.coefficient_entity]?.state||''].join('|');if(marker!==this._marker){this._marker=marker;this._load();}}
 connectedCallback(){if(!this._timer)this._timer=setInterval(()=>this._load(),60000);}
 disconnectedCallback(){if(this._timer){clearInterval(this._timer);this._timer=null;}}
 getCardSize(){return 7;}
 _esc(v){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
 _num(v,n=1){return Number(v).toLocaleString('uk-UA',{minimumFractionDigits:n,maximumFractionDigits:n});}
 _loading(){this.innerHTML=`<ha-card><div class="wrap"><h2>${this._esc(this.config.title||'Вода по годинах')}</h2><p>Завантажую історію…</p></div></ha-card><style>.wrap{padding:16px}h2{margin:0;font-size:20px}</style>`;}
 async _load(){
  if(!this._hass)return;
  const now=new Date(),currentHour=new Date(now);currentHour.setMinutes(0,0,0);
  const firstHour=new Date(currentHour.getTime()-23*3600000),queryStart=new Date(firstHour.getTime()-2*3600000);
  const path='history/period/'+encodeURIComponent(queryStart.toISOString())+'?filter_entity_id='+encodeURIComponent(this.config.energy_entity)+'&end_time='+encodeURIComponent(now.toISOString())+'&minimal_response';
  try{
   const data=await this._hass.callApi('GET',path),states=(data&&data[0])||[],buckets=new Map(),keys=[];
   for(let i=0;i<24;i++){const k=firstHour.getTime()+i*3600000;keys.push(k);buckets.set(k,0);}
   let prev=null;
   for(const s of states){const value=Number(s.state),ts=Date.parse(s.last_changed||s.last_updated||'');if(!Number.isFinite(value)||!Number.isFinite(ts))continue;if(prev){const delta=value>=prev.value?value-prev.value:(value<=prev.value*0.1?value:0);if(delta>0){const k=Math.floor(ts/3600000)*3600000;if(buckets.has(k))buckets.set(k,buckets.get(k)+delta);}}prev={value,ts};}
   const offset=Number(calib(this._hass,this.config).energy_offset_kwh??this.config.energy_offset_kwh??0),offsetTs=Date.parse(calib(this._hass,this.config).baseline_iso||this.config.offset_time||'');if(offset>0&&Number.isFinite(offsetTs)){const k=Math.floor(offsetTs/3600000)*3600000;if(buckets.has(k))buckets.set(k,buckets.get(k)+offset);}
   const coef=Math.max(0,Number(this._hass.states[this.config.coefficient_entity]?.state||0)),liters=keys.map(k=>(buckets.get(k)||0)*coef*1000);
   this._render(keys,liters,coef);
  }catch(e){this.innerHTML=`<ha-card><div class="wrap"><h2>${this._esc(this.config.title||'Вода по годинах')}</h2><p class="err">Не вдалося завантажити історію</p></div></ha-card><style>.wrap{padding:16px}.err{color:var(--error-color)}</style>`;}
 }
 _render(keys,liters,coef){
  const total=liters.reduce((a,b)=>a+b,0),peak=Math.max(0,...liters),active=liters.filter(v=>v>0).length,W=1200,H=430,L=64,R=22,T=32,B=66,PW=W-L-R,PH=H-T-B,max=Math.max(1,peak)*1.12,bw=PW/24,color=this.config.color||'#ff9800';
  let svg='';
  for(let i=0;i<=4;i++){const v=max*i/4,y=T+PH-PH*i/4;svg+=`<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" class="grid"/><text x="${L-9}" y="${y+5}" text-anchor="end" class="axis">${this._num(v,0)}</text>`;}
  for(let i=0;i<24;i++){const v=liters[i],h=v/max*PH,x=L+i*bw+bw*.12,y=T+PH-h,label=new Date(keys[i]).toLocaleString('uk-UA',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});svg+=`<rect x="${x}" y="${y}" width="${bw*.76}" height="${Math.max(v>0?3:0,h)}" rx="4" class="bar"><title>${label}: ${this._num(v,1)} л</title></rect>`;if(i%4===0||i===23)svg+=`<text x="${L+i*bw+bw/2}" y="${H-25}" text-anchor="middle" class="axis">${new Date(keys[i]).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'})}</text>`;}
  this.innerHTML=`<ha-card><div class="wrap"><h2>${this._esc(this.config.title||'Розрахункова вода по годинах · 24 години')}</h2><div class="stats"><div><span>За 24 години</span><b>${this._num(total,1)} л</b></div><div><span>Максимум за годину</span><b>${this._num(peak,1)} л</b></div><div><span>Годин зі споживанням</span><b>${active}</b></div></div><div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Розрахункова витрата води по годинах">${svg}<text x="18" y="${T+PH/2}" text-anchor="middle" transform="rotate(-90 18 ${T+PH/2})" class="axis unit">літрів за годину</text></svg></div><div class="legend"><i></i> Розрахунок за енергією · ${Math.round(coef*1000).toLocaleString('uk-UA')} л/кВт·год</div></div></ha-card><style>.wrap{padding:16px}h2{margin:0 0 14px;font-size:20px}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.stats div{padding:11px;border-radius:11px;background:color-mix(in srgb,${color} 11%,transparent)}.stats span{display:block;color:var(--secondary-text-color);font-size:12px}.stats b{display:block;margin-top:4px;font-size:18px}.chart{overflow-x:auto}svg{display:block;width:100%;min-width:720px;height:auto}.grid{stroke:var(--divider-color);stroke-width:1}.axis{fill:var(--secondary-text-color);font:14px sans-serif}.unit{font-size:13px}.bar{fill:${color};opacity:.9}.bar:hover{opacity:1}.legend{color:var(--secondary-text-color);font-size:13px}.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;background:${color};vertical-align:-2px;margin-right:5px}@media(max-width:700px){.stats{grid-template-columns:1fr}.stats b{font-size:17px}}</style>`;
 }
};customElements.define(tag,WellHourlyWaterCard);window.customCards=window.customCards||[];window.customCards.push({type:tag,name:'Погодинна витрата води',description:'24 погодинні стовпчики за енергією насоса'});})();
