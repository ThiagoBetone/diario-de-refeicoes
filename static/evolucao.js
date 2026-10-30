(() => {
  const $ = id => document.getElementById(id);
  const fmt = n => n == null ? '—' : Number(n).toLocaleString('pt-BR', {maximumFractionDigits:2});
  const dataBR = s => s.split('-').reverse().join('/');
  const form = $('medidas-form');
  form.elements.data.value = $('dia').value;
  let versao = 0;
  async function api(url, dados) {
    const r = await fetch(url, dados ? {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(dados)} : {});
    const body = await r.json();
    if (!r.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Confira os dados informados.');
    return body;
  }
  function celula(tr, valor) {const td=document.createElement('td');td.textContent=valor;tr.append(td);return td;}
  function medidas(rows) {
    const lista=$('medidas-lista');lista.replaceChildren();
    for (const m of [...rows].reverse()) {
      const tr=document.createElement('tr');celula(tr,dataBR(m.data));celula(tr,fmt(m.peso_kg));celula(tr,fmt(m.cintura_cm));
      const btn=document.createElement('button');btn.type='button';btn.className='btn btn-outline-secondary btn-sm';btn.textContent='Editar';
      btn.setAttribute('aria-label',`Editar medidas de ${dataBR(m.data)}`);
      btn.onclick=()=>{for(const k of ['data','peso_kg','cintura_cm']) form.elements.namedItem(k).value=m[k]??'';form.elements.peso_kg.focus();$('medidas-status').textContent=`Editando ${dataBR(m.data)}. Campos vazios serão removidos deste registro.`;};
      celula(tr,'').append(btn);lista.append(tr);
    }
    $('medidas-variacao').textContent = ['peso_kg','cintura_cm'].map((k,i)=>{
      const r=rows.filter(m=>m[k]!=null);
      if(r.length<2) return `${i?'Cintura':'Peso'}: registre duas medições para comparar.`;
      const dif=r.at(-1)[k]-r[0][k];return `${i?'Cintura':'Peso'}: ${dif>0?'+':''}${fmt(dif)} ${i?'cm':'kg'} entre ${dataBR(r[0].data)} e ${dataBR(r.at(-1).data)}.`;
    }).join(' ');
  }
  function grafico(info) {
    const area=$('evolucao-grafico');area.replaceChildren();
    if(!info.dias.length) return;
    const ns='http://www.w3.org/2000/svg';
    const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 1000 350');svg.style.width='100%';svg.style.minWidth='620px';svg.setAttribute('role','img');svg.setAttribute('aria-label','Evolução diária de calorias consumidas, gasto de referência e TMB atual. Valores detalhados na tabela abaixo.');
    function node(tag,attrs,text){const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));if(text!=null)e.textContent=text;svg.append(e);return e;}
    const dias=info.dias, datas=dias.map(d=>Date.parse(d.data+'T00:00:00Z'));
    const max=Math.max(1,info.tmb_atual??0,...dias.flatMap(d=>[d.consumidas??0,d.gasto_referencia??0]))*1.1;
    const x=i=>datas.length===1?520:70+900*(datas[i]-datas[0])/(datas.at(-1)-datas[0]);
    const y=n=>290-250*n/max;
    for(let i=0;i<=4;i++){const valor=max*i/4;node('line',{x1:70,x2:970,y1:y(valor),y2:y(valor),stroke:'#dde4df'});node('text',{x:62,y:y(valor)+4,'text-anchor':'end','font-size':12,fill:'#52695d'},fmt(Math.round(valor)));}
    node('text',{x:70,y:20,'font-size':13},'kcal');
    if(info.tmb_atual!=null)node('line',{x1:70,x2:970,y1:y(info.tmb_atual),y2:y(info.tmb_atual),stroke:'#21754f','stroke-width':2,'stroke-dasharray':'7 5'});
    for(const [campo,cor,label] of [['consumidas','#2563a6','Consumo'],['gasto_referencia','#7451a0','Gasto de referência']]){
      let segmento=[];
      const flush=()=>{if(segmento.length)node('polyline',{points:segmento.join(' '),fill:'none',stroke:cor,'stroke-width':2});segmento=[];};
      dias.forEach((d,i)=>{if(d[campo]==null){flush();return;}segmento.push(`${x(i)},${y(d[campo])}`);});flush();
      dias.forEach((d,i)=>{if(d[campo]==null)return;const c=node('circle',{cx:x(i),cy:y(d[campo]),r:4,fill:cor});const t=document.createElementNS(ns,'title');t.textContent=`${dataBR(d.data)} · ${label}: ${fmt(d[campo])} kcal`;c.append(t);});
    }
    const indices=new Set([0,dias.length-1]);for(let i=0;i<dias.length;i+=Math.max(1,Math.ceil(dias.length/7)))indices.add(i);
    for(const i of indices)node('text',{x:x(i),y:315,'text-anchor':'middle','font-size':12},dataBR(dias[i].data));
    area.append(svg);
  }
  async function carregar() {
    const atual=++versao;$('evolucao-status').textContent='Carregando histórico…';
    $('evolucao-lista').replaceChildren();$('evolucao-grafico').replaceChildren();$('medidas-lista').replaceChildren();$('medidas-variacao').textContent='';
    try {
      const [m,info]=await Promise.all([api('/perfil/medidas'),api('/evolucao')]);if(atual!==versao)return;
      medidas(m);grafico(info);filtroRefeicoes(info.refeicoes);
      $('evolucao-status').textContent=info.dias.length?`${info.dias.length} dias registrados. ${info.tmb_atual==null?'Cadastre um perfil válido para definir a TMB.':`Linha horizontal: TMB atual de ${fmt(info.tmb_atual)} kcal, válida desde ${dataBR(info.tmb_vigente_desde)}.`}`:'Nenhuma refeição ou treino registrado. Adicione registros na aba Diário.';
      const excluidas=info.refeicoes.filter(r=>r.excluida).length;
      if(excluidas)$('evolucao-status').textContent+=` Filtro ativo: ${excluidas} refeição(ões) excluída(s). Consumo e saldo parciais.`;
      for(const d of info.dias){const tr=document.createElement('tr');for(const v of [dataBR(d.data),d.consumidas==null?'Sem refeições incluídas':fmt(d.consumidas),fmt(d.tmb),fmt(d.treinos),fmt(d.gasto_referencia)])celula(tr,v);
        celula(tr,d.saldo==null?'Sem comparação':d.saldo===0?'Equilíbrio':`${d.saldo<0?'Déficit':'Superávit'}: ${fmt(Math.abs(d.saldo))}`);$('evolucao-lista').append(tr);}
    }catch(e){if(atual===versao)$('evolucao-status').textContent=e.message;}
  }
  function filtroRefeicoes(refeicoes) {
    const lista=$('refeicoes-filtro');lista.replaceChildren();
    if(!refeicoes.length){lista.textContent='Nenhuma refeição registrada.';return;}
    for(const r of refeicoes){
      const label=document.createElement('label');label.className='d-flex align-items-center gap-2 border-bottom py-2';
      const check=document.createElement('input');check.type='checkbox';check.className='form-check-input flex-shrink-0 m-0';check.checked=Boolean(r.excluida);
      const texto=document.createElement('span');texto.textContent=`${dataBR(r.data)} · ${r.horario.slice(0,5)} · ${r.nome} · ${fmt(r.calorias)} kcal`;
      check.onchange=async()=>{const valor=check.checked;check.disabled=true;try{await api(`/evolucao/refeicoes/${r.id}`,{excluida:valor});$('refeicoes-filtro-status').textContent=valor?'Refeição excluída apenas da evolução.':'Refeição incluída novamente na evolução.';await carregar();}catch(e){check.checked=!valor;check.disabled=false;$('refeicoes-filtro-status').textContent=e.message;}};
      label.append(check,texto);lista.append(label);
    }
  }
  function ativar(nome){for(const n of ['diario','evolucao']){const ativo=n===nome;$('painel-'+n).hidden=!ativo;$('aba-'+n).classList.toggle('active',ativo);$('aba-'+n).setAttribute('aria-selected',String(ativo));$('aba-'+n).tabIndex=ativo?0:-1;}if(nome==='evolucao')carregar();}
  for(const n of ['diario','evolucao']){$('aba-'+n).onclick=()=>ativar(n);$('aba-'+n).onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const next=e.key==='Home'?'diario':e.key==='End'?'evolucao':n==='diario'?'evolucao':'diario';ativar(next);$('aba-'+next).focus();}};}
  form.onsubmit=async e=>{e.preventDefault();const btn=form.querySelector('button');btn.disabled=true;try{const dados=Object.fromEntries(new FormData(form));for(const k of ['peso_kg','cintura_cm'])dados[k]=dados[k]?Number(dados[k]):null;await api('/perfil/medidas',dados);$('medidas-status').textContent='Medidas salvas no seu perfil.';await carregar();}catch(e){$('medidas-status').textContent=e.message;}finally{btn.disabled=false;}};
})();
