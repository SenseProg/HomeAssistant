(function(){const tag='well-meter-entry-card';if(customElements.get(tag))return;class WellMeterEntryCard extends HTMLElement{
  setConfig(config){this.config=config;if(!config.value_entity||!config.saved_entity||!config.datetime_entity||!config.button_entity)throw new Error('Потрібні entity для форми');this._render();}
  set hass(hass){this._hass=hass;}
  getCardSize(){return 4;}
  _esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  _nowLocal(){const d=new Date(Date.now()-new Date().getTimezoneOffset()*60000);return d.toISOString().slice(0,19);}
  _status(text,kind=''){const el=this.querySelector('.status');if(!el)return;el.textContent=text;el.className='status '+kind;}
  _render(){
    this.innerHTML=`<ha-card><div class="wrap"><h2>${this._esc(this.config.title||'Новий запис')}</h2><label>Показник механічного лічильника, м³<input class="reading" type="text" inputmode="decimal" autocomplete="off" placeholder="Наприклад, 815,667"></label><label>Дата й точний час зняття<input class="taken" type="datetime-local" step="1" value="${this._nowLocal()}"></label><button class="save">Зберегти показник</button><div class="status" role="status"></div></div></ha-card><style>.wrap{padding:16px}h2{font-size:20px;margin:0 0 14px}label{display:block;margin:0 0 14px;color:var(--secondary-text-color);font-size:13px}input{box-sizing:border-box;width:100%;margin-top:7px;padding:12px;border:1px solid var(--divider-color);border-radius:10px;background:var(--card-background-color);color:var(--primary-text-color);font:inherit;font-size:16px}input:focus{outline:2px solid var(--primary-color);border-color:transparent}button{width:100%;padding:12px 16px;border:0;border-radius:10px;background:var(--primary-color);color:var(--text-primary-color,#fff);font:inherit;font-weight:700;cursor:pointer}button:disabled{opacity:.55;cursor:wait}.status{min-height:20px;margin-top:10px;font-size:14px}.status.ok{color:var(--success-color,#2e7d32)}.status.err{color:var(--error-color,#b00020)}</style>`;
    this.querySelector('.save').addEventListener('click',()=>this._save());
    this.querySelector('.reading').addEventListener('keydown',e=>{if(e.key==='Enter')this._save();});
  }
  async _save(){
    if(!this._hass)return this._status('Home Assistant ще завантажується. Спробуйте ще раз.','err');
    const raw=this.querySelector('.reading').value.trim().replace(/\s/g,'').replace(',','.');
    const value=Number(raw),saved=Number(this._hass.states[this.config.saved_entity]?.state);
    let datetime=this.querySelector('.taken').value;
    if(!Number.isFinite(value))return this._status('Введіть числовий показник, наприклад 815,667.','err');
    if(Number.isFinite(saved)&&value<=saved)return this._status('Новий показник має бути більшим за '+saved.toLocaleString('uk-UA',{minimumFractionDigits:3,maximumFractionDigits:3})+' м³.','err');
    if(!datetime)return this._status('Вкажіть дату й час зняття показника.','err');
    if(datetime.length===16)datetime+=':00';
    const btn=this.querySelector('.save');btn.disabled=true;this._status('Зберігаю…');
    try{
      await this._hass.callService('input_number','set_value',{entity_id:this.config.value_entity,value});
      await this._hass.callService('input_datetime','set_datetime',{entity_id:this.config.datetime_entity,datetime:datetime.replace('T',' ')});
      await this._hass.callService('input_button','press',{entity_id:this.config.button_entity});
      let ok=false;
      for(let i=0;i<24;i++){await new Promise(r=>setTimeout(r,250));const current=Number(this._hass.states[this.config.saved_entity]?.state);if(Math.abs(current-value)<0.0005){ok=true;break;}}
      if(!ok)throw new Error('Автоматизація не підтвердила запис');
      this._status('Збережено: '+value.toLocaleString('uk-UA',{minimumFractionDigits:3,maximumFractionDigits:3})+' м³ · '+datetime.replace('T',' '),'ok');
      this.querySelector('.reading').value='';
    }catch(e){this._status('Не вдалося зберегти: '+(e?.message||e),'err');}
    finally{btn.disabled=false;}
  }
};customElements.define(tag,WellMeterEntryCard);window.customCards=window.customCards||[];window.customCards.push({type:tag,name:'Введення показника води',description:'Форма для нового показника механічного лічильника'});})();
