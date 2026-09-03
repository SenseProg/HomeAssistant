// 2026-09-03: «цього місяця» береться з довгострокової статистики інтегратора
// (recorder/statistics_during_period, period day), а не з сирої історії: recorder
// тримає 7 діб, і після 8-го числа місячна цифра мовчки ставала тижневою.
// «Сьогодні» - з сирої історії від опівночі, бо LTS відстає до години.
// Перезавантаження - лише коли насос зупинився, змінився коефіцієнт або минуло
// 5 хвилин: картка живе на завжди відкритому «Огляді» і раніше тягнула історію
// щосекунди під час кожного пуску.
//
// 2026-08-30: падіння значення джерела після перезапуску HA не вважається
// скиданням (Riemann відновлюється з restore_state трохи нижчим); скидання -
// лише падіння до <=10 % попереднього значення.
(function(){const tag='well-water-overview-card';if(customElements.get(tag))return;const RUN='input_boolean.nasos_sverdlovini_pratsiuie';class WellWaterOverviewCard extends HTMLElement{
 setConfig(config){this.config=config;if(!config.energy_entity||!config.coefficient_entity)throw new Error('Потрібні energy_entity і coefficient_entity');this._renderLoading();}
 set hass(hass){this._hass=hass;const coef=hass.states[this.config.coefficient_entity]?.state||'',run=hass.states[this.config.running_entity||RUN]?.state||'',marker=coef+'|'+run,now=Date.now();
  if(marker!==this._marker){this._marker=marker;if(run!=='on'||!this._lastLoad)this._load();}
  else if(now-(this._lastLoad||0)>300000)this._load();}
 getCardSize(){return 3;}
 _esc(v){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
 _num(v){return Number(v).toLocaleString('uk-UA',{minimumFractionDigits:1,maximumFractionDigits:1});}
 _key(d){return new Intl.DateTimeFormat('en-CA',{timeZone:this.config.time_zone||'Europe/Kyiv',year:'numeric',month:'2-digit',day:'2-digit'}).format(d);}
 _renderLoading(){this.innerHTML=`<ha-card><div class="wrap"><b>${this._esc(this.config.title||'Вода')}</b><span>Завантажую…</span></div></ha-card><style>.wrap{padding:16px;display:flex;justify-content:space-between}</style>`;}
 async _rawSince(startDate){
  const path='history/period/'+encodeURIComponent(startDate.toISOString())+'?filter_entity_id='+encodeURIComponent(this.config.energy_entity)+'&end_time='+encodeURIComponent(new Date().toISOString())+'&minimal_response&no_attributes';
  const data=await this._hass.callApi('GET',path),states=(data&&data[0])||[];let prev=null,sum=0;
  for(const s of states){const value=Number(s.state);if(!Number.isFinite(value))continue;if(prev!==null){const delta=value>=prev?value-prev:(value<=prev*0.1?value:0);if(delta>0)sum+=delta;}prev=value;}
  return sum;
 }
 async _load(){
  if(!this._hass)return;this._lastLoad=Date.now();
  try{
   const todayKey=this._key(new Date()),monthPrefix=todayKey.slice(0,7);
   const lts=await this._hass.callWS({type:'recorder/statistics_during_period',start_time:new Date(Date.now()-33*86400000).toISOString(),statistic_ids:[this.config.energy_entity],period:'day',types:['change']});
   let monthKwh=0;
   for(const row of (lts?.[this.config.energy_entity]||[])){if(row.change==null)continue;const k=this._key(new Date(row.start));if(k.startsWith(monthPrefix)&&k!==todayKey)monthKwh+=Math.max(0,row.change);}
   const todayKwh=await this._rawSince(new Date(todayKey+'T00:00:00'));
   const coef=Math.max(0,Number(this._hass.states[this.config.coefficient_entity]?.state||0));
   this._render(todayKwh*coef*1000,(monthKwh+todayKwh)*coef*1000,coef);
  }catch(e){this.innerHTML=`<ha-card><div class="wrap err">Не вдалося порахувати воду</div></ha-card><style>.wrap{padding:16px}.err{color:var(--error-color)}</style>`;}
 }
 _render(today,month,coef){
  const href=this.config.navigation_path||'/sverdlovina-dashboard/well';
  this.innerHTML=`<ha-card><a class="wrap" href="${this._esc(href)}"><div class="head"><ha-icon icon="mdi:water"></ha-icon><b>${this._esc(this.config.title||'Вода свердловини')}</b><ha-icon class="go" icon="mdi:chevron-right"></ha-icon></div><div class="stats"><div><span>Сьогодні</span><strong>${this._num(today)} л</strong></div><div><span>Цього місяця</span><strong>${this._num(month)} л</strong></div></div><small>Розрахунок · ${Math.round(coef*1000).toLocaleString('uk-UA')} л/кВт·год</small></a></ha-card><style>.wrap{display:block;padding:16px;color:var(--primary-text-color);text-decoration:none}.head{display:flex;align-items:center;gap:8px;margin-bottom:14px}.head ha-icon{color:var(--primary-color)}.head .go{margin-left:auto;color:var(--secondary-text-color)}.stats{display:grid;grid-template-columns:1fr 1fr;gap:10px}.stats div{padding:11px;border-radius:11px;background:color-mix(in srgb,var(--primary-color) 10%,transparent)}span,small{display:block;color:var(--secondary-text-color);font-size:12px}strong{display:block;font-size:19px;margin-top:4px;font-variant-numeric:tabular-nums}small{margin-top:10px}</style>`;
 }
};customElements.define(tag,WellWaterOverviewCard);window.customCards=window.customCards||[];window.customCards.push({type:tag,name:'Вода свердловини для огляду',description:'Розрахункова вода сьогодні та за поточний місяць'});})();
