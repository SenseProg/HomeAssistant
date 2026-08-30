(function(){const tag='well-pump-runs-card';if(customElements.get(tag))return;class WellPumpRunsCard extends HTMLElement{
 setConfig(config){this.config=config;if(!config.entity)throw new Error('Потрібна entity');this._renderLoading();}
 set hass(hass){this._hass=hass;const marker=[hass.states[this.config.entity]?.state||'',hass.states[this.config.entity]?.last_updated||''].join('|');if(marker!==this._marker){this._marker=marker;this._load();}}
 connectedCallback(){if(!this._timer)this._timer=setInterval(()=>this._load(),60000);}
 disconnectedCallback(){if(this._timer){clearInterval(this._timer);this._timer=null;}}
 getCardSize(){return 4;}
 _esc(v){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
 _fmtDuration(ms){const m=Math.round(ms/60000);if(m<60)return m+' хв';const h=Math.floor(m/60),r=m%60;return r?h+' год '+r+' хв':h+' год';}
 _renderLoading(){this.innerHTML=`<ha-card><div class="wrap"><h2>${this._esc(this.config.title||'Запуски насоса')}</h2><p>Завантажую історію…</p></div></ha-card><style>.wrap{padding:16px}h2{margin:0;font-size:20px}p{color:var(--secondary-text-color)}</style>`;}
 async _load(){
  if(!this._hass)return;
  const hours=Number(this.config.hours_to_show||24),end=new Date(),start=new Date(end.getTime()-hours*3600000);
  const path='history/period/'+encodeURIComponent(start.toISOString())+'?filter_entity_id='+encodeURIComponent(this.config.entity)+'&end_time='+encodeURIComponent(end.toISOString())+'&minimal_response';
  try{
   const data=await this._hass.callApi('GET',path),raw=(data&&data[0])||[];
   const pts=raw.map(s=>({state:s.state,time:Date.parse(s.last_changed||s.last_updated||'')})).filter(p=>['on','off'].includes(p.state)&&Number.isFinite(p.time)).sort((a,b)=>a.time-b.time);
   if(!pts.length){const current=this._hass.states[this.config.entity]?.state||'off';pts.push({state:current,time:start.getTime()});}
   if(pts[0].time>start.getTime())pts.unshift({state:pts[0].state,time:start.getTime()});
   const intervals=[];let launches=0,total=0,prevState='off';
   for(let i=0;i<pts.length;i++){const p=pts[i],a=Math.max(start.getTime(),p.time),b=Math.min(end.getTime(),i+1<pts.length?pts[i+1].time:end.getTime());if(p.state==='on'&&b>a){intervals.push([a,b]);total+=b-a;if(prevState!=='on'&&p.time>=start.getTime())launches++;}prevState=p.state;}
   this._render(start,end,intervals,launches,total,hours);
  }catch(e){this.innerHTML=`<ha-card><div class="wrap"><h2>${this._esc(this.config.title||'Запуски насоса')}</h2><p class="err">Не вдалося завантажити історію</p></div></ha-card><style>.wrap{padding:16px}.err{color:var(--error-color)}</style>`;}
 }
 _render(start,end,intervals,launches,total,hours){
  const W=1200,H=190,L=48,R=24,T=56,B=42,PW=W-L-R,barY=72,barH=42,color=this.config.color||'#00bcd4',span=end.getTime()-start.getTime();
  let svg=`<rect x="${L}" y="${barY}" width="${PW}" height="${barH}" rx="8" class="track"/>`;
  for(const [a,b] of intervals){const x=L+(a-start.getTime())/span*PW,w=Math.max(3,(b-a)/span*PW);svg+=`<rect x="${x}" y="${barY}" width="${w}" height="${barH}" rx="4" class="run"><title>${new Date(a).toLocaleString('uk-UA')} — ${new Date(b).toLocaleString('uk-UA')}</title></rect>`;}
  const ticks=hours<=24?6:7;
  for(let i=0;i<=ticks;i++){const t=new Date(start.getTime()+span*i/ticks),x=L+PW*i/ticks,label=hours<=24?t.toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'}):t.toLocaleDateString('uk-UA',{weekday:'short'});svg+=`<line x1="${x}" y1="${barY+barH+4}" x2="${x}" y2="${barY+barH+10}" class="tick"/><text x="${x}" y="${H-12}" text-anchor="middle" class="axis">${this._esc(label)}</text>`;}
  const current=this._hass?.states[this.config.entity]?.state==='on';
  this.innerHTML=`<ha-card><div class="wrap"><div class="head"><div><h2>${this._esc(this.config.title||'Запуски насоса')}</h2><div class="legend"><i></i> Насос працює</div></div><div class="stats"><span>Запусків <b>${launches}</b></span><span>Робота <b>${this._fmtDuration(total)}</b></span></div></div><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Запуски насоса: ${launches}, час роботи ${this._fmtDuration(total)}">${svg}</svg>${current?'<div class="now"><i></i> Насос працює зараз</div>':''}</div></ha-card><style>.wrap{padding:16px}.head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}h2{margin:0 0 6px;font-size:20px}.legend{font-size:13px;color:var(--secondary-text-color)}.legend i,.now i{display:inline-block;width:12px;height:12px;border-radius:3px;background:${color};vertical-align:-2px;margin-right:6px;box-shadow:0 0 10px ${color}}.stats{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.stats span{padding:7px 10px;border-radius:10px;background:color-mix(in srgb,${color} 12%,transparent);color:var(--secondary-text-color);font-size:12px}.stats b{color:var(--primary-text-color);font-size:14px;margin-left:4px}svg{display:block;width:100%;height:auto;margin-top:4px}.track{fill:var(--divider-color);opacity:.35}.run{fill:${color};filter:drop-shadow(0 0 5px ${color});opacity:.95}.tick{stroke:var(--secondary-text-color);stroke-width:1}.axis{fill:var(--secondary-text-color);font:14px sans-serif}.now{margin-top:-6px;color:${color};font-size:13px;font-weight:700}@media(max-width:700px){.head{display:block}.stats{justify-content:flex-start;margin-top:10px}svg{min-width:680px}.wrap{overflow-x:auto}}</style>`;
 }
};customElements.define(tag,WellPumpRunsCard);window.customCards=window.customCards||[];window.customCards.push({type:tag,name:'Кольорова шкала запусків насоса',description:'Запуски та час роботи насоса без сірого стану'});})();
