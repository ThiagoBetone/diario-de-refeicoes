// Gráfico de barras com escala comum, base zero e valores acessíveis em texto.
(() => {
  const el = id => document.getElementById(id);
  const formatar = n => Number(n).toLocaleString('pt-BR', {maximumFractionDigits: 2});
  const perfilForm = el('perfil-form'), treinoForm = el('treino-form');
  let revisao = 0;
  async function requisitar(url, method = 'GET', dados) {
    const r = await fetch(url, {method, ...(dados ? {headers: {'Content-Type': 'application/json'}, body: JSON.stringify(dados)} : {})});
    if (!r.ok) {
      const erro = await r.json();
      throw new Error(typeof erro.detail === 'string' ? erro.detail : 'Confira os campos informados.');
    }
    return r.status === 204 ? null : r.json();
  }
  function desenhar(b) {
    const container = el('energia-grafico'); container.replaceChildren();
    const series = [
      ['Consumidas', b.consumidas, '#2563a6'],
      ['Referência basal (TMB)', b.perfil?.tmb ?? null, '#21754f'],
      ['Treinos (calorias ativas)', b.calorias_treinos, '#9a6200'],
      ['Referência TMB + treinos', b.referencia, '#7451a0'],
    ];
    const maximo = Math.max(1, ...series.map(s => s[1] ?? 0));
    for (const [titulo, valor, cor] of series) {
      const row = document.createElement('div'); row.className = 'my-3';
      const label = document.createElement('div'); label.className = 'd-flex justify-content-between gap-2 small mb-1';
      const nome = document.createElement('span'); nome.textContent = titulo;
      const numero = document.createElement('strong'); numero.textContent = valor === null ? 'Não definida' : `${formatar(valor)} kcal`;
      label.append(nome, numero);
      const track = document.createElement('div'); track.className = 'progress'; track.style.height = '24px'; track.setAttribute('aria-hidden', 'true');
      const bar = document.createElement('div'); bar.className = 'progress-bar'; bar.style.backgroundColor = cor;
      bar.style.width = `${(valor ?? 0) / maximo * 100}%`;
      track.append(bar); row.append(label, track); container.append(row);
    }
    const delta = valor => valor === 0 ? 'igual à referência' : `${formatar(Math.abs(valor))} kcal ${valor > 0 ? 'acima' : 'abaixo'}`;
    el('energia-comparacao').textContent = b.perfil
      ? `Consumo em relação à TMB: ${delta(b.diferenca_tmb)}. Em relação à TMB + treinos: ${delta(b.diferenca_referencia)}.`
      : 'Salve um perfil válido para esta data para definir sua referência basal.';
    el('energia-aviso').textContent = b.perfil
      ? `Perfil válido desde ${b.perfil.vigente_desde.split('-').reverse().join('/')}. As barras partem de zero e usam a mesma escala.`
      : 'Sem perfil para esta data. Consumo e treinos continuam sendo registrados.';
    const lista = el('treinos-lista'); lista.replaceChildren();
    if (!b.treinos.length) { const li = document.createElement('li'); li.className = 'list-group-item text-body-secondary'; li.textContent = 'Nenhum treino registrado neste dia.'; lista.append(li); }
    for (const treino of b.treinos) {
      const li = document.createElement('li'); li.className = 'list-group-item d-flex justify-content-between align-items-center gap-2';
      const texto = document.createElement('span'); texto.textContent = `${treino.nome} · ${formatar(treino.calorias)} kcal`;
      const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'btn btn-outline-secondary btn-sm'; btn.textContent = 'Excluir'; btn.setAttribute('aria-label', `Excluir treino ${treino.nome}`);
      btn.onclick = async () => {
        btn.disabled = true;
        try { await requisitar(`/treinos/${treino.id}`, 'DELETE'); el('treino-status').textContent = 'Treino excluído.'; await atualizarEnergia(); }
        catch (e) { el('treino-status').textContent = e.message; btn.disabled = false; }
      };
      li.append(texto, btn); lista.append(li);
    }
  }
  async function atualizarEnergia() {
    const atual = ++revisao, data = el('dia').value;
    el('energia-dia').textContent = data ? data.split('-').reverse().join('/') : 'Selecione uma data';
    el('energia-grafico').replaceChildren(); el('energia-comparacao').textContent = '';
    el('treinos-lista').replaceChildren(); el('energia-aviso').textContent = 'Carregando comparação…';
    try {
      if (!data) throw new Error('Selecione uma data válida.');
      const b = await requisitar(`/balanco-diario?data=${encodeURIComponent(data)}`);
      if (atual === revisao) desenhar(b);
    } catch (e) { if (atual === revisao) el('energia-aviso').textContent = `Não foi possível carregar: ${e.message}`; }
  }
  window.atualizarEnergia = atualizarEnergia;
  perfilForm.onsubmit = async e => {
    e.preventDefault(); const btn = perfilForm.querySelector('button'); btn.disabled = true;
    try {
      const dados = Object.fromEntries(new FormData(perfilForm));
      for (const campo of ['idade', 'peso_kg', 'altura_cm']) dados[campo] = Number(dados[campo]);
      const perfil = await requisitar('/perfil', 'PUT', dados);
      el('perfil-status').textContent = `Perfil salvo. TMB estimada: ${formatar(perfil.tmb)} kcal/dia.`;
      await atualizarEnergia();
    } catch (e) { el('perfil-status').textContent = e.message; }
    finally { btn.disabled = false; }
  };
  treinoForm.onsubmit = async e => {
    e.preventDefault(); const btn = treinoForm.querySelector('button'); btn.disabled = true;
    try {
      const data = el('dia').value;
      if (!data) throw new Error('Selecione uma data para o treino.');
      const dados = Object.fromEntries(new FormData(treinoForm)); dados.calorias = Number(dados.calorias); dados.data = data;
      await requisitar('/treinos', 'POST', dados); treinoForm.reset();
      el('treino-status').textContent = `Treino registrado em ${data.split('-').reverse().join('/')}.`;
      await atualizarEnergia();
    } catch (e) { el('treino-status').textContent = e.message; }
    finally { btn.disabled = false; }
  };
  async function carregarPerfil() {
    perfilForm.elements.vigente_desde.value = el('dia').value;
    try {
      const p = await requisitar('/perfil');
      if (!p) { el('perfil-detalhes').open = true; return; }
      for (const campo of ['idade', 'peso_kg', 'altura_cm', 'sexo_formula', 'vigente_desde']) perfilForm.elements.namedItem(campo).value = p[campo];
    } catch (e) { el('perfil-status').textContent = `Não foi possível carregar seu perfil: ${e.message}`; el('perfil-detalhes').open = true; }
  }
  carregarPerfil(); atualizarEnergia();
})();
