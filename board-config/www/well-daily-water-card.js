// 2026-09-03: добові стовпчики беруться з довгострокової статистики (LTS) інтегратора,
// а не з сирої історії. recorder тримає 7 діб (purge_keep_days), тому «за 30 днів»
// раніше означало «за 7», а «середня» ділилась на 30 - занижена вчетверо. LTS
// (recorder/statistics_during_period, period day, change) живе роками, ріже доби
// за часовою зоною сервера (Europe/Kyiv) і сама обробляє скидання лічильника.
// Сьогоднішній стовпчик - з сирої історії від опівночі, бо LTS відстає до години.
// Перезавантаження - лише коли насос зупинився, змінився коефіцієнт або минуло
// 5 хвилин: раніше картка тягнула ~1 МБ історії щосекунди протягом пуску.
//
// 2026-08-30: падіння значення джерела після перезапуску HA не вважається
// скиданням (Riemann-інтегратор відновлюється з restore_state трохи нижчим);
// скидання - лише падіння до <=10 % попереднього значення.
(function(){const tag='well-daily-water-card';if(customElements.get(tag))return;const CAL_LOG='sensor.zhurnal_pokaznykiv_vody';const RUN='input_boolean.nasos_sverdlovini_pratsiuie';class WellDailyWaterCard extends HTMLElement{
 setConfig(config){this.config=config;if(!config.energy_entity||!config.coefficient_entity)throw new Error('Потрібні energy_entity і coefficient_entity');this._renderLoading();}
 set hass(hass){this._hass=hass;const coef=hass.states[this.config.coefficient_entity]?.state||'',run=hass.states[this.config.running_entity||RUN]?.state||'',marker=coef+'|'+run,now=Date.now();
  if(marker!==this._marker){this._marker=marker;if(run!=='on'||!this._lastLoad)this._load();}
  else if(now-(this._lastLoad||0)>300000)this._load();}
 connectedCallback(){if(!this._timer)this._timer=setInterval(()=>{if(Date.now()-(this._lastLoad||0)>300000)this._load();},60000);}
 disconnectedCallback(){if(this._timer){clearInterval(this._timer);this._timer=null;}}
 getCardSize(){return 8;}
 _esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
 _num(v,n=1){return Number(v).toLocaleString('uk-UA',{minimumFractionDigits:n,maximumFractionDigits:n});}
 _dayKey(d){return new Intl.DateTimeFormat('en-CA',{timeZone:this.config.time_zone||'Europe/Kyiv',year:'numeric',month:'2-digit',day:'2-digit'}).format(d);}
 _label(key,full=false){const d=new Date(key+'T12:00:00');return d.toLocaleDateString('uk-UA',full?{day:'2-digit',month:'2-digit',year:'numeric'}:{day:'2-digit',month:'2-digit'});}
 _renderLoading(){this.innerHTML=`<ha-card><div class="wrap"><h2>${this._esc(this.config.title||'Розрахункова вода за днями')}</h2><p>Завантажую статистику…</p></div></ha-card><style>.wrap{padding:16px}h2{font-size:20px;margin:0 0 12px}p{color:var(--secondary-text-color)}</style>`;}
 async _rawSince(startDate){
  const path='history/period/'+encodeURIComponent(startDate.toISOString())+'?filter_entity_id='+encodeURIComponent(this.config.energy_entity)+'&end_time='+encodeURIComponent(new Date().toISOString())+'&minimal_response&no_attributes';
  const data=await this._hass.callApi('GET',path),states=(data&&data[0])||[];let prev=null,sum=0;
  for(const s of states){const value=Number(s.state);if(!Number.isFinite(value))continue;if(prev!==null){const delta=value>=prev?value-prev:(value<=prev*0.1?value:0);if(delta>0)sum+=delta;}prev=value;}
  return sum;
 }
 async _load(){
  if(!this._hass)return;this._lastLoad=Date.now();
  const days=this.config.days||30,keys=[],noon=new Date();noon.setHours(12,0,0,0);
  for(let i=days-1;i>=0;i--){const d=new Date(noon);d.setDate(d.getDate()-i);keys.push(this._dayKey(d));}
  const todayKey=keys[keys.length-1],buckets=new Map(keys.map(k=>[k,null]));
  try{
   const lts=await this._hass.callWS({type:'recorder/statistics_during_period',start_time:new Date(Date.now()-(days+1)*86400000).toISOString(),statistic_ids:[this.config.energy_entity],period:'day',types:['change']});
   for(const row of (lts?.[this.config.energy_entity]||[])){if(row.change==null)continue;const k=this._dayKey(new Date(row.start));if(buckets.has(k)&&k!==todayKey)buckets.set(k,Math.max(0,row.change));}
   try{buckets.set(todayKey,await this._rawSince(new Date(todayKey+'T00:00:00')));}
   catch(e){const t=(lts?.[this.config.energy_entity]||[]).find(r=>this._dayKey(new Date(r.start))===todayKey);buckets.set(todayKey,t&&t.change!=null?Math.max(0,t.change):null);}
   const coef=Math.max(0,Number(this._hass.states[this.config.coefficient_entity]?.state||0));
   const liters=keys.map(k=>{const v=buckets.get(k);return v==null?null:v*coef*1000;});
   this._render(keys,liters,coef);
  }catch(e){this.innerHTML=`<ha-card><div class="wrap"><h2>${this._esc(this.config.title||'Розрахункова вода за днями')}</h2><p class="err">Не вдалося завантажити статистику: ${this._esc(e?.message||e)}</p></div></ha-card><style>.wrap{padding:16px}.err{color:var(--error-color)}</style>`;}
 }
 _render(keys,liters,coef){
  const known=liters.filter(v=>v!=null),n=known.length,total=known.reduce((a,b)=>a+b,0),today=liters[liters.length-1]??0,avg=n?total/n:0;
  const W=1200,H=430,L=62,R=22,T=35,B=72,PW=W-L-R,PH=H-T-B,max=Math.max(1,...known)*1.12,bw=PW/keys.length;
  let svg='';
  for(let i=0;i<=4;i++){const val=max*i/4,y=T+PH-(PH*i/4);svg+=`<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" class="grid"/><text x="${L-8}" y="${y+5}" text-anchor="end" class="axis">${this._num(val,0)}</text>`;}
  for(let i=0;i<keys.length;i++){const v=liters[i],x=L+i*bw+bw*.14;if(v==null){svg+=`<rect x="${x}" y="${T+PH-2}" width="${Math.max(2,bw*.72)}" height="2" class="nodata"><title>${this._label(keys[i],true)}: немає статистики</title></rect>`;}else{const h=v/max*PH,y=T+PH-h;svg+=`<rect x="${x}" y="${y}" width="${Math.max(2,bw*.72)}" height="${Math.max(v>0?2:0,h)}" rx="3" class="bar${i===keys.length-1?' today':''}"><title>${this._label(keys[i],true)}: ${this._num(v,1)} л${i===keys.length-1?' (сьогодні, ще триває)':''}</title></rect>`;}if(i%5===0||i===keys.length-1)svg+=`<text x="${L+i*bw+bw/2}" y="${H-42}" text-anchor="middle" class="axis date">${this._label(keys[i])}</text>`;}
  const note=coef>0?`Чинний коефіцієнт: ${this._num(coef*1000,0)} л/кВт·год. Дні - з довгострокової статистики (живе роками), сьогодні - з сирої історії. Після нового механічного показника весь графік перераховується.`:'Очікується коефіцієнт калібрування.';
  this.innerHTML=`<ha-card><div class="wrap"><h2>${this._esc(this.config.title||'Розрахункова вода за днями')}</h2><div class="stats"><div><span>Сьогодні</span><b>${this._num(today,1)} л</b></div><div><span>За ${n} ${n===1?'день':(n>=2&&n<=4?'дні':'днів')} з даними</span><b>${this._num(total,1)} л</b></div><div><span>Середня за ці дні</span><b>${this._num(avg,1)} л/день</b></div></div><div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Розрахункова витрата води по днях">${svg}<text x="18" y="${T+PH/2}" text-anchor="middle" transform="rotate(-90 18 ${T+PH/2})" class="axis unit">літрів на день</text></svg></div><div class="legend"><i></i> Розрахунок за енергією насоса · <i class="nd"></i> статистики ще немає</div><p>${this._esc(note)}</p></div></ha-card><style>.wrap{padding:16px}h2{font-size:20px;margin:0 0 14px}.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:12px}.stats div{padding:12px;border-radius:12px;background:color-mix(in srgb,var(--primary-color) 9%,transparent)}.stats span{display:block;color:var(--secondary-text-color);font-size:12px;margin-bottom:5px}.stats b{font-size:18px;font-variant-numeric:tabular-nums}.chart{overflow-x:auto}svg{display:block;width:100%;min-width:720px;height:auto}.grid{stroke:var(--divider-color);stroke-width:1}.axis{fill:var(--secondary-text-color);font:14px sans-serif}.date{font-size:13px}.unit{font-size:13px}.bar{fill:var(--primary-color);opacity:.86}.bar.today{opacity:.55}.bar:hover{opacity:1}.nodata{fill:var(--secondary-text-color);opacity:.35}.legend{font-size:13px;color:var(--secondary-text-color);margin-top:2px}.legend i{display:inline-block;width:11px;height:11px;border-radius:3px;background:var(--primary-color);vertical-align:-1px;margin-right:5px}.legend i.nd{background:var(--secondary-text-color);opacity:.35;margin-left:8px}p{margin:10px 0 0;color:var(--secondary-text-color);font-size:13px}@media(max-width:700px){.stats{grid-template-columns:1fr}.stats b{font-size:17px}}</style>`;
 }
};customElements.define(tag,WellDailyWaterCard);window.customCards=window.customCards||[];window.customCards.push({type:tag,name:'Розрахункова вода за 30 днів',description:'Добова витрата води зі статистики енергії насоса'});})();
