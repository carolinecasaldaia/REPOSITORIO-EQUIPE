/* Calculadora revisional — cola tudo: leitura do PDF, cálculo, cronograma e exportação. */
(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
  const NUM2 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const money = v => (v == null || isNaN(v)) ? '—' : BRL.format(v);
  const pct = v => (v == null || isNaN(v)) ? '—' : NUM2.format(v * 100) + '%';

  function parseNum(s) {
    if (s == null) return null;
    s = String(s).trim().replace(/R\$/gi, '').replace(/\s/g, '');
    if (!s) return null;
    if (s.includes(',')) s = s.replace(/\./g, '').replace(',', '.');
    else if ((s.match(/\./g) || []).length > 1) s = s.replace(/\./g, '');
    const n = parseFloat(s);
    return isNaN(n) ? null : n;
  }
  const parseInt2 = s => { const n = parseNum(s); return n == null ? null : Math.round(n); };

  function parseDate(s) {
    const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(String(s || '').trim());
    if (!m) return null;
    const d = new Date(+m[3], +m[2] - 1, +m[1]);
    return isNaN(d.getTime()) ? null : d;
  }
  const fmtDate = d => d ? String(d.getDate()).padStart(2, '0') + '/' + String(d.getMonth() + 1).padStart(2, '0') + '/' + d.getFullYear() : '—';
  function addMonths(d, n) {
    const dia = d.getDate();
    const x = new Date(d.getFullYear(), d.getMonth() + n, 1);
    x.setDate(Math.min(dia, new Date(x.getFullYear(), x.getMonth() + 1, 0).getDate()));
    return x;
  }

  /* ---------------- estado ---------------- */
  const S = {
    modo: 'pdf',       // 'pdf' = lê o contrato · 'manual' = a equipe digita
    origem: {},        // de onde veio cada campo lido
    escalonado: null,  // blocos de parcelas maiores (contratos com balão discriminado)
    avisos: [],
    arquivo: null,
    bytes: null,
    textoContrato: '',
    atrasoTocado: false,
    acordoTocado: false,
    acordo: null
  };

  const CAMPOS = ['valorBem', 'entrada', 'valorParcela', 'qtdParcelas', 'balao', 'primeiroVencimento', 'banco', 'cliente'];

  function lerFormulario() {
    return {
      baseDireta: $('baseModo').value === 'financiado',
      valorFinanciadoManual: parseNum($('valorFinanciado').value) || 0,
      valorBem: parseNum($('valorBem').value) || 0,
      entrada: parseNum($('entrada').value) || 0,
      valorParcela: parseNum($('valorParcela').value) || 0,
      qtdParcelas: parseInt2($('qtdParcelas').value) || 0,
      balao: parseNum($('balao').value) || 0,
      balaoPago: $('balaoPago').value === 'sim',
      primeiroVencimento: parseDate($('primeiroVencimento').value),
      banco: $('banco').value.trim(),
      cliente: $('cliente').value.trim(),
      pagas: parseInt2($('pagas').value) || 0,
      atraso: parseInt2($('atraso').value) || 0,
      pctAcordo: (parseNum($('pctAcordo').value) || 0) / 100,
      pctHonPrev: (parseNum($('pctHonPrev').value) || 0) / 100,
      pctDeposito: (parseNum($('pctDeposito').value) || 0) / 100
    };
  }

  /* ---------------- cálculo (espelha a planilha do escritório) ---------------- */
  function calcular(d) {
    const qtd = d.qtdParcelas, parc = d.valorParcela;
    const pagas = Math.max(0, Math.min(d.pagas, qtd));
    // sem o contrato o cliente às vezes só sabe quanto financiou; com o contrato
    // vale a fórmula da planilha do escritório: valor do bem menos a entrada
    const financiado = d.baseDireta ? d.valorFinanciadoManual : d.valorBem - d.entrada;
    const totalContrato = qtd * parc + d.balao;
    const pago = pagas * parc + (d.balaoPago ? d.balao : 0);
    const emAberto = qtd - pagas;
    const residualFin = financiado - pago;
    const residualTotal = totalContrato - pago;
    const parcelaEstimada = emAberto > 0 ? residualFin / emAberto : 0;
    const deposito = parcelaEstimada * (1 + d.pctDeposito);
    const previsaoAcordo = residualTotal * d.pctAcordo;
    const honPrev = residualTotal * d.pctHonPrev;
    const acordo = S.acordoTocado && S.acordo != null ? S.acordo : previsaoAcordo;
    const ganhoReal = residualTotal - acordo;
    const pctAcordoReal = residualTotal ? acordo / residualTotal : 0;
    const atraso = Math.max(0, Math.min(d.atraso, emAberto));
    return {
      ...d, pagas, atraso, financiado, totalContrato, pago, emAberto, residualFin, residualTotal,
      parcelaEstimada, deposito, previsaoAcordo, honPrev, acordo, ganhoReal, pctAcordoReal,
      jurosContrato: totalContrato - financiado,
      valorEmAtraso: atraso * parc,
      pctPago: qtd ? pagas / qtd : 0,
      ultimaPaga: d.primeiroVencimento && pagas > 0 ? addMonths(d.primeiroVencimento, pagas - 1) : null,
      valido: qtd > 0 && parc > 0 && financiado > 0
    };
  }

  /* o que ainda falta para o cálculo fechar — vira o texto do painel vazio */
  function faltando(d) {
    const f = [];
    if (d.baseDireta) { if (!(d.valorFinanciadoManual > 0)) f.push('o valor financiado'); }
    else if (!(d.valorBem - d.entrada > 0)) f.push('o valor do veículo');
    if (!(d.valorParcela > 0)) f.push('o valor da parcela');
    if (!(d.qtdParcelas > 0)) f.push('a quantidade de parcelas');
    return f;
  }
  const listar = a => a.length < 2 ? (a[0] || '') : a.slice(0, -1).join(', ') + ' e ' + a[a.length - 1];

  /* ---------------- cronograma ---------------- */
  function valorDaParcela(i, d) {
    if (S.escalonado && S.escalonado.blocks) {
      for (const b of S.escalonado.blocks) if (i >= b.de && i <= b.ate) return b.v;
    }
    return d.valorParcela;
  }

  function cronograma(r) {
    const hoje = new Date(); hoje.setHours(0, 0, 0, 0);
    const linhas = [];
    const base = r.primeiroVencimento;
    for (let i = 1; i <= r.qtdParcelas; i++) {
      const venc = base ? addMonths(base, i - 1) : null;
      const val = valorDaParcela(i, r);
      let status;
      if (i <= r.pagas) status = 'paga';
      else if (venc && venc < hoje) status = 'atraso';
      else if (i === r.pagas + 1) status = 'prox';
      else status = 'futura';
      linhas.push({ i, venc, val, status, balao: val > r.valorParcela + 0.005, deposito: i <= r.pagas ? 0 : r.deposito });
    }
    return linhas;
  }

  function vencidasAteHoje(r) {
    if (!r.primeiroVencimento) return null;
    const hoje = new Date(); hoje.setHours(0, 0, 0, 0);
    let n = 0;
    for (let i = 1; i <= r.qtdParcelas; i++) if (addMonths(r.primeiroVencimento, i - 1) < hoje) n++;
    return n;
  }

  /* ---------------- render ---------------- */
  function badge(id) {
    const el = $('src-' + id);
    if (!el) return;
    const o = S.origem[id];
    el.className = 'src' + (o ? (o.estimado ? ' guess' : ' auto') : '');
    if (!o) { el.textContent = ''; return; }
    if (o.texto === 'exemplo') el.textContent = 'valor de exemplo';
    else if (o.texto === 'você preencheu') el.textContent = 'você preencheu';
    else el.textContent = o.estimado ? '≈ ' + o.texto : 'lido do contrato · ' + o.texto;
  }

  function render() {
    const d = lerFormulario();
    const r = calcular(d);

    // sugestão de parcelas em atraso a partir das datas
    if (!S.atrasoTocado && r.primeiroVencimento && r.qtdParcelas) {
      const venc = vencidasAteHoje(r);
      const sug = Math.max(0, Math.min(venc - r.pagas, r.emAberto));
      if ($('atraso').value === '' || +$('atraso').value !== sug) $('atraso').value = String(sug);
      $('src-atraso').className = 'src auto';
      $('src-atraso').textContent = sug > 0 ? 'sugerido pelas datas do contrato' : 'nenhuma vencida em aberto';
      r.atraso = sug;
      r.valorEmAtraso = sug * r.valorParcela;
    }
    if (r.primeiroVencimento && r.pagas > 0) {
      $('src-pagas').className = 'src';
      $('src-pagas').textContent = 'última paga em ' + fmtDate(r.ultimaPaga);
    }

    if (!r.valido) {
      const falta = faltando(d);
      const vazio = falta.length === 3;
      $('vazia-titulo').textContent = vazio ? 'Nenhum cálculo ainda' : 'Falta pouco';
      $('vazia-msg').textContent = vazio
        ? (S.modo === 'manual'
          ? 'Digite o valor do veículo, o valor da parcela e a quantidade de parcelas. O resto é opcional.'
          : 'Anexe o contrato em PDF — ou, se o cliente não tiver o contrato, use "Não tenho o contrato" e digite os dados.')
        : 'Para fechar a conta ainda falta ' + listar(falta) + '.';
      $('saida').classList.add('hidden');
      $('saida-vazia').classList.remove('hidden');
      return;
    }
    $('saida').classList.remove('hidden');
    $('saida-vazia').classList.add('hidden');

    // KPIs
    $('kpis').innerHTML = [
      kpi('Já pagou ao banco', money(r.pago), r.pagas + ' de ' + r.qtdParcelas + ' parcelas (' + Math.round(r.pctPago * 100) + '%)', 'pos'),
      kpi('Ainda deve', money(r.residualTotal), r.emAberto + ' parcelas em aberto' + (r.atraso ? ' · ' + r.atraso + ' em atraso' : ''), 'neg'),
      kpi('Redução estimada', money(r.ganhoReal), 'ganho real com o acordo', 'acc'),
      kpi('Honorários', money(r.honPrev), NUM2.format(r.pctHonPrev * 100) + '% do valor residual', 'acc')
    ].join('');

    $('resumo-titulo').textContent = (r.cliente || '') + (r.banco ? ' · ' + r.banco : '');

    // planilha
    $('ledger').innerHTML = `
      <div class="subhead">Contrato</div>
      <table class="ledger">
        <tbody>
          ${r.baseDireta
        ? row('Valor financiado', money(r.financiado), 'sum', 'informado pelo cliente, sem o contrato')
        : row('Valor do veículo', money(r.valorBem))
        + row('( − ) Valor da entrada', money(r.entrada))
        + row('( = ) Valor financiado', money(r.financiado), 'sum')}
          ${row('Parcelas contratadas', r.qtdParcelas + '× ' + money(r.valorParcela))}
          ${r.balao ? row('( + ) Parcela balão', money(r.balao), '', r.balaoPago ? 'já paga' : 'em aberto') : ''}
          ${row('( = ) Valor total do contrato', money(r.totalContrato), 'sum')}
          ${row('Juros e encargos embutidos', money(r.jurosContrato), '', 'diferença entre o total do contrato e o valor financiado')}
        </tbody>
      </table>

      <div class="subhead">Situação hoje</div>
      <table class="ledger">
        <tbody>
          ${row('Parcelas pagas', String(r.pagas))}
          ${row('Valor pago do financiamento', money(r.pago), 'sum')}
          ${row('Parcelas em aberto', String(r.emAberto))}
          ${r.atraso ? row('Parcelas em atraso', r.atraso + '× ' + money(r.valorParcela), '', 'total vencido: ' + money(r.valorEmAtraso)) : ''}
          ${row('Valor residual do valor financiado', money(r.residualFin), '', r.residualFin < 0 ? 'o cliente já pagou mais do que o valor financiado' : '')}
          ${row('Valor residual do valor total do contrato', money(r.residualTotal), 'sum')}
        </tbody>
      </table>

      <div class="subhead">Ação revisional</div>
      <table class="ledger">
        <tbody>
          ${row('Valor estimado da parcela', money(r.parcelaEstimada), '', 'residual do financiado ÷ parcelas em aberto')}
          ${row('Valor para depósito judicial', money(r.deposito), 'sum', 'parcela estimada + ' + NUM2.format(r.pctDeposito * 100) + '%')}
        </tbody>
      </table>`;

    // acordo e honorários
    $('acordo').innerHTML = `
      <div class="subhead">Previsão</div>
      <table class="ledger">
        <tbody>
          ${row('Previsão de acordo (' + NUM2.format(r.pctAcordo * 100) + '% do residual)', money(r.previsaoAcordo))}
          ${row('Honorários contratuais (' + NUM2.format(r.pctHonPrev * 100) + '%)', money(r.honPrev))}
        </tbody>
      </table>

      <div class="subhead">Fechamento</div>
      <table class="ledger">
        <tbody>
          ${row('Valor residual do valor total do contrato', money(r.residualTotal))}
          <tr>
            <td>( − ) Valor de acordo<span class="sub">digite o valor fechado com o banco</span></td>
            <td class="n"><input type="text" id="acordoInput" inputmode="decimal" value="${NUM2.format(r.acordo)}"
              style="width:130px;padding:5px 7px;font:600 13.5px var(--mono);text-align:right;border:1px solid var(--line-strong);border-radius:6px;background:var(--surface);color:var(--ink)"></td>
          </tr>
          ${row('Percentual de acordo', pct(r.pctAcordoReal))}
          ${row('( = ) Ganho real', money(r.ganhoReal), 'sum')}
          ${row('Honorários contratuais (' + NUM2.format(r.pctHonPrev * 100) + '%)', money(r.honPrev), 'sum', 'os mesmos ' + NUM2.format(r.pctHonPrev * 100) + '% do valor residual — não muda com o acordo')}
        </tbody>
      </table>`;
    const ai = $('acordoInput');
    ai.addEventListener('input', () => { S.acordoTocado = true; S.acordo = parseNum(ai.value); });
    ai.addEventListener('change', render);
    ai.addEventListener('blur', render);

    // cronograma
    const linhas = cronograma(r);
    const nomes = { paga: 'paga', prox: 'próxima', atraso: 'em atraso', futura: 'a vencer' };
    $('crono').innerHTML = `<table class="crono">
      <thead><tr><th>Nº</th><th>Vencimento</th><th style="text-align:right">Parcela</th><th>Situação</th><th style="text-align:right">Depósito judicial</th></tr></thead>
      <tbody>${linhas.map(l => `<tr class="${l.status === 'atraso' ? 'is-atraso' : (l.status === 'prox' ? 'is-prox' : '')}">
        <td class="num">${l.i}</td>
        <td>${l.venc ? fmtDate(l.venc) : '—'}</td>
        <td class="val">${NUM2.format(l.val)}${l.balao ? ' <span class="pill balao">balão</span>' : ''}</td>
        <td><span class="pill ${l.status}">${nomes[l.status]}</span></td>
        <td class="val">${l.deposito ? NUM2.format(l.deposito) : '—'}</td>
      </tr>`).join('')}</tbody></table>`;
    const atrasadas = linhas.filter(l => l.status === 'atraso').length;
    $('crono-resumo').textContent = r.primeiroVencimento
      ? r.qtdParcelas + ' parcelas · ' + atrasadas + ' vencidas em aberto'
      : 'informe o 1º vencimento para ver as datas';

    $('whats').value = textoWhats(r);
    S.ultimo = r;
    S.ultimasLinhas = linhas;
  }

  const kpi = (k, v, s, cls) => `<div class="kpi ${cls}"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s}</div></div>`;
  const row = (label, val, cls, sub) => `<tr class="${cls || ''}"><td>${label}${sub ? `<span class="sub">${sub}</span>` : ''}</td><td class="n">${val}</td></tr>`;

  /* ---------------- textos ---------------- */
  function textoWhats(r) {
    const L = [];
    L.push('*Análise do seu financiamento*');
    if (r.cliente) L.push('Cliente: ' + r.cliente);
    if (r.banco) L.push('Banco: ' + r.banco);
    L.push('');
    L.push('*O contrato*');
    if (!r.baseDireta) {
      L.push('Valor do veículo: ' + money(r.valorBem));
      L.push('Entrada: ' + money(r.entrada));
    }
    L.push('Valor financiado: ' + money(r.financiado));
    L.push('Parcelas: ' + r.qtdParcelas + 'x de ' + money(r.valorParcela));
    if (r.balao) L.push('Parcela balão: ' + money(r.balao));
    L.push('Total a pagar ao banco: ' + money(r.totalContrato));
    L.push('Juros e encargos embutidos: ' + money(r.jurosContrato));
    L.push('');
    L.push('*Onde você está hoje*');
    L.push('Já pago: ' + money(r.pago) + ' (' + r.pagas + ' de ' + r.qtdParcelas + ' parcelas)');
    L.push('Em aberto: ' + r.emAberto + ' parcelas' + (r.atraso ? ', sendo ' + r.atraso + ' em atraso' : ''));
    L.push('Ainda devido ao banco: ' + money(r.residualTotal));
    L.push('');
    L.push('*Com a ação revisional*');
    L.push('Parcela estimada sem os juros abusivos: ' + money(r.parcelaEstimada));
    L.push('Depósito judicial mensal: ' + money(r.deposito));
    L.push('Previsão de acordo: ' + money(r.previsaoAcordo));
    L.push('Redução estimada: ' + money(r.ganhoReal));
    L.push('Honorários contratuais (' + NUM2.format(r.pctHonPrev * 100) + '%): ' + money(r.honPrev));
    L.push('');
    L.push(r.baseDireta || S.modo === 'manual'
      ? '_Valores estimados a partir das informações prestadas pelo cliente, sujeitos à conferência do contrato, à análise documental e à decisão judicial._'
      : '_Valores estimados a partir do contrato apresentado, sujeitos à análise documental e à decisão judicial._');
    return L.join('\n');
  }

  function textoNumeros(r) {
    const L = [
      ['Cliente', r.cliente], ['Banco', r.banco],
      ['Valor do veículo', r.baseDireta ? '' : money(r.valorBem)],
      ['Entrada', r.baseDireta ? '' : money(r.entrada)],
      ['Valor financiado', money(r.financiado)], ['Quantidade de parcelas', r.qtdParcelas],
      ['Valor da parcela', money(r.valorParcela)], ['Parcela balão', money(r.balao)],
      ['Valor total do contrato', money(r.totalContrato)], ['Juros e encargos', money(r.jurosContrato)],
      ['Parcelas pagas', r.pagas], ['Valor pago', money(r.pago)],
      ['Parcelas em aberto', r.emAberto], ['Parcelas em atraso', r.atraso],
      ['Valor em atraso', money(r.valorEmAtraso)],
      ['Residual do valor financiado', money(r.residualFin)],
      ['Residual do valor total', money(r.residualTotal)],
      ['Valor estimado da parcela', money(r.parcelaEstimada)],
      ['Depósito judicial', money(r.deposito)],
      ['Previsão de acordo', money(r.previsaoAcordo)],
      ['Valor de acordo', money(r.acordo)],
      ['Ganho real', money(r.ganhoReal)],
      ['Honorários contratuais', money(r.honPrev)]
    ];
    return L.filter(x => x[1] !== '' && x[1] != null).map(x => x[0] + ': ' + x[1]).join('\n');
  }

  /* ---------------- planilha .xlsx ---------------- */
  const CRC = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
      t[n] = c >>> 0;
    }
    return t;
  })();
  function crc32(u8) {
    let c = 0xFFFFFFFF;
    for (let i = 0; i < u8.length; i++) c = CRC[(c ^ u8[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }
  const enc = new TextEncoder();

  function zipStore(files) {
    const chunks = [], central = [];
    let offset = 0;
    for (const f of files) {
      const name = enc.encode(f.name);
      const data = f.data;
      const crc = crc32(data);
      const lfh = new Uint8Array(30 + name.length);
      const dv = new DataView(lfh.buffer);
      dv.setUint32(0, 0x04034b50, true); dv.setUint16(4, 20, true); dv.setUint16(6, 0, true);
      dv.setUint16(8, 0, true); dv.setUint16(10, 0, true); dv.setUint16(12, 0x21, true);
      dv.setUint32(14, crc, true); dv.setUint32(18, data.length, true); dv.setUint32(22, data.length, true);
      dv.setUint16(26, name.length, true); dv.setUint16(28, 0, true);
      lfh.set(name, 30);
      chunks.push(lfh, data);
      const cd = new Uint8Array(46 + name.length);
      const cv = new DataView(cd.buffer);
      cv.setUint32(0, 0x02014b50, true); cv.setUint16(4, 20, true); cv.setUint16(6, 20, true);
      cv.setUint16(8, 0, true); cv.setUint16(10, 0, true); cv.setUint16(12, 0, true); cv.setUint16(14, 0x21, true);
      cv.setUint32(16, crc, true); cv.setUint32(20, data.length, true); cv.setUint32(24, data.length, true);
      cv.setUint16(28, name.length, true); cv.setUint32(42, offset, true);
      cd.set(name, 46);
      central.push(cd);
      offset += lfh.length + data.length;
    }
    let csize = 0;
    for (const c of central) csize += c.length;
    const eocd = new Uint8Array(22);
    const ev = new DataView(eocd.buffer);
    ev.setUint32(0, 0x06054b50, true);
    ev.setUint16(8, files.length, true); ev.setUint16(10, files.length, true);
    ev.setUint32(12, csize, true); ev.setUint32(16, offset, true);
    const all = chunks.concat(central, [eocd]);
    let total = 0;
    for (const a of all) total += a.length;
    const out = new Uint8Array(total);
    let o = 0;
    for (const a of all) { out.set(a, o); o += a.length; }
    return out;
  }

  const xesc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const N = v => ({ t: 'n', v });
  const T = (v, s) => ({ t: 's', v, s });
  const TB = v => ({ t: 's', v, s: 1 });
  const M = v => ({ t: 'n', v: Math.round((Number(v) || 0) * 100) / 100, s: 2 });
  const P = v => ({ t: 'n', v, s: 3 });

  function sheetXml(cells) {
    const byRow = new Map();
    for (const ref of Object.keys(cells)) {
      const m = /^([A-Z]+)(\d+)$/.exec(ref);
      if (!m) continue;
      const r = +m[2];
      if (!byRow.has(r)) byRow.set(r, []);
      byRow.get(r).push({ ref, col: m[1], c: cells[ref] });
    }
    const colNum = s => { let n = 0; for (const ch of s) n = n * 26 + (ch.charCodeAt(0) - 64); return n; };
    const rows = [...byRow.keys()].sort((a, b) => a - b).map(r => {
      const cs = byRow.get(r).sort((a, b) => colNum(a.col) - colNum(b.col)).map(({ ref, c }) => {
        const s = c.s ? ` s="${c.s}"` : '';
        if (c.t === 'n') return `<c r="${ref}"${s}><v>${Number(c.v) || 0}</v></c>`;
        return `<c r="${ref}"${s} t="inlineStr"><is><t xml:space="preserve">${xesc(c.v)}</t></is></c>`;
      }).join('');
      return `<row r="${r}">${cs}</row>`;
    }).join('');
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cols><col min="1" max="1" width="42" customWidth="1"/><col min="2" max="2" width="18" customWidth="1"/><col min="3" max="3" width="4" customWidth="1"/><col min="4" max="4" width="40" customWidth="1"/><col min="5" max="5" width="18" customWidth="1"/></cols><sheetData>${rows}</sheetData></worksheet>`;
  }

  function montarXlsx(sheets) {
    const styles = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2"><numFmt numFmtId="164" formatCode="&quot;R$&quot;\\ #,##0.00"/><numFmt numFmtId="165" formatCode="0.00%"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="5">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="164" fontId="1" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1"/>
</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`;

    const wbSheets = sheets.map((s, i) => `<sheet name="${xesc(s.name)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join('');
    const workbook = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>${wbSheets}</sheets></workbook>`;
    const wbRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${sheets.map((s, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join('')}<Relationship Id="rId${sheets.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`;
    const ct = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>${sheets.map((s, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join('')}<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>`;
    const rels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`;

    const files = [
      { name: '[Content_Types].xml', data: enc.encode(ct) },
      { name: '_rels/.rels', data: enc.encode(rels) },
      { name: 'xl/workbook.xml', data: enc.encode(workbook) },
      { name: 'xl/_rels/workbook.xml.rels', data: enc.encode(wbRels) },
      { name: 'xl/styles.xml', data: enc.encode(styles) }
    ];
    sheets.forEach((s, i) => files.push({ name: 'xl/worksheets/sheet' + (i + 1) + '.xml', data: enc.encode(sheetXml(s.cells)) }));
    return zipStore(files);
  }

  function planilhaDoCliente(r, linhas) {
    const calc = {
      B2: TB('Planilha de Cálculo'),
      A6: TB('Informações do Cliente'), A7: T('Nome'), B7: T(r.cliente || ''),
      A11: TB('Dados do Contrato'),
      A12: T('Valor do Bem'), B12: r.baseDireta ? T('não informado') : M(r.valorBem),
      D12: T('Data de Vencimento da Primeira Parcela'), E12: T(fmtDate(r.primeiroVencimento)),
      G12: T('Valor Residual do Valor Financiado'), H12: M(r.residualFin),
      A14: T('Valor da Entrada'), B14: r.baseDireta ? T('não informado') : M(r.entrada),
      D15: T('Data da Última Parcela Paga'), E15: T(r.ultimaPaga ? fmtDate(r.ultimaPaga) : ''),
      G15: T('Valor Residual do Valor Total do Contrato'), H15: M(r.residualTotal),
      A16: T('Valor Financiado'), B16: M(r.financiado),
      A18: T('Parcela Balão'), B18: M(r.balao),
      D18: T('Balão Pago?'), E18: T(r.balaoPago ? 'Sim' : 'Não'),
      A19: T('Quantidade de Parcelas'), B19: N(r.qtdParcelas),
      D19: T('Quantidade de Parcelas Pagas'), E19: N(r.pagas),
      G19: T('Valor para Depósito Judicial'), H19: M(r.deposito),
      J19: T('Valor Estimado da Parcela'), K19: M(r.parcelaEstimada),
      A21: T('Valor da Parcela no Carnê'), B21: M(r.valorParcela),
      D21: T('Quantidade de Parcelas em Aberto'), E21: N(r.emAberto),
      F21: T('Quantidade de Parcelas em Atraso'), G21: N(r.atraso),
      A23: T('Valor Total do Contrato'), B23: M(r.totalContrato),
      D23: T('Valor Pago do Financiamento'), E23: M(r.pago),
      A25: TB('Informações do Serviço'),
      A26: T('Tipo de Serviço'), C26: T('Contratos Bancários de Veículos'),
      A27: T('Instituição Financeira'), C27: T(r.banco || '')
    };

    const acordo = {
      A1: TB('Valor de Previsão de Acordo e Honorários Contratuais'),
      A2: T('Valor de Previsão de Acordo'), B2: M(r.previsaoAcordo),
      D2: T('Valor de Honorários Contratuais'), E2: M(r.honPrev),
      A4: T('Percentual de Previsão de Acordo:'), B4: P(r.pctAcordo),
      A5: T('Percentual de Honorários Contratuais:'), B5: P(r.pctHonPrev),
      A7: TB('Valor de Fechamento de Acordo e Honorários Contratuais'),
      A8: T('Valor da Parcela no Carnê'), B8: M(r.valorParcela),
      A9: T('( x ) Quantidade de Parcelas em Aberto'), B9: N(r.emAberto),
      A10: T('( = ) Valor Residual do Valor Total do Contrato'), B10: M(r.residualTotal),
      A11: T('( − ) Valor de Acordo'), B11: M(r.acordo),
      A12: T('( x ) Percentual de Acordo'), B12: P(r.pctAcordoReal),
      A13: T('( = ) Ganho Real'), B13: M(r.ganhoReal),
      A15: T('Honorários Contratuais'), B15: M(r.honPrev),
      C15: T('(' + NUM2.format(r.pctHonPrev * 100) + '% do valor residual do valor total do contrato)')
    };

    const crono = { A1: TB('N.º Parcela'), B1: TB('Vencimento'), C1: TB('Valor da Parcela'), D1: TB('Situação'), E1: TB('Depósito Judicial') };
    const nomes = { paga: 'Paga', prox: 'Próxima a pagar', atraso: 'Vencida e em aberto', futura: 'A vencer' };
    linhas.forEach((l, i) => {
      const r0 = i + 2;
      crono['A' + r0] = N(l.i);
      crono['B' + r0] = T(l.venc ? fmtDate(l.venc) : '');
      crono['C' + r0] = M(l.val);
      crono['D' + r0] = T(nomes[l.status]);
      crono['E' + r0] = l.deposito ? M(l.deposito) : T('');
    });

    return montarXlsx([
      { name: 'Planilha de Cálculo', cells: calc },
      { name: 'Acordo e Honorários', cells: acordo },
      { name: 'Cronograma', cells: crono }
    ]);
  }

  function csvDoCliente(r, linhas) {
    const q = s => '"' + String(s).replace(/"/g, '""') + '"';
    const L = [['Campo', 'Valor']];
    textoNumeros(r).split('\n').forEach(l => { const i = l.indexOf(': '); L.push([l.slice(0, i), l.slice(i + 2)]); });
    L.push([]);
    L.push(['Nº Parcela', 'Vencimento', 'Valor', 'Situação', 'Depósito judicial']);
    const nomes = { paga: 'Paga', prox: 'Próxima a pagar', atraso: 'Vencida e em aberto', futura: 'A vencer' };
    linhas.forEach(l => L.push([l.i, l.venc ? fmtDate(l.venc) : '', NUM2.format(l.val), nomes[l.status], l.deposito ? NUM2.format(l.deposito) : '']));
    return '﻿' + L.map(r0 => r0.map(q).join(';')).join('\r\n');
  }

  /* ---------------- exportar ---------------- */
  function nomeArquivo(r, ext) {
    const base = (r.cliente || 'calculo-revisional').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^A-Za-z0-9 ]/g, '').trim().replace(/\s+/g, '-').toLowerCase();
    return (base || 'calculo-revisional') + '.' + ext;
  }

  async function salvar(nome, dados) {
    const dl = window.claude && window.claude.downloads;
    if (dl && dl.save) {
      try {
        await dl.save({ filename: nome, data: dados });
        return { ok: true, via: 'claude', nome };
      } catch (e) {
        const code = e && e.code;
        if (code === 'declined') return { ok: false, motivo: 'declined' };
        if (code === 'rate_limited') return { ok: false, motivo: 'rate_limited' };
        return { ok: false, motivo: code || 'erro' };
      }
    }
    return { ok: false, motivo: 'unavailable' };
  }

  function baixarDireto(nome, dados, mime) {
    try {
      const blob = new Blob([dados], { type: mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = nome; a.style.display = 'none';
      document.body.appendChild(a); a.click();
      setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 4000);
      return true;
    } catch (e) { return false; }
  }

  async function exportarPlanilha() {
    const r = S.ultimo, linhas = S.ultimasLinhas;
    if (!r) return;
    const msg = $('dl-msg');
    msg.className = 'notice info';
    msg.textContent = 'Gerando a planilha…';
    const xlsx = planilhaDoCliente(r, linhas);

    // Rodando da pasta do escritório (fora do Artifact) o navegador baixa o
    // .xlsx direto, sem a restrição de formato que existe na versão publicada.
    if (!(window.claude && window.claude.downloads)) {
      if (baixarDireto(nomeArquivo(r, 'xlsx'), xlsx, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')) {
        msg.className = 'notice ok';
        msg.innerHTML = 'Planilha baixada: <b>' + nomeArquivo(r, 'xlsx') + '</b> — três abas, igual à planilha do escritório.';
        return;
      }
    }

    let res = await salvar(nomeArquivo(r, 'xlsx'), xlsx);
    if (res.ok) { msg.className = 'notice ok'; msg.textContent = 'Planilha salva como ' + res.nome + '.'; return; }
    if (res.motivo === 'declined') { msg.className = 'notice info'; msg.textContent = 'Download cancelado.'; return; }

    // .xlsx recusado por aqui: cai para CSV, que o Excel abre igual
    const csv = csvDoCliente(r, linhas);
    res = await salvar(nomeArquivo(r, 'csv'), csv);
    if (res.ok) {
      msg.className = 'notice ok';
      msg.innerHTML = 'Salvo como <b>' + res.nome + '</b> — o Excel abre esse arquivo normalmente (esta página não tem permissão para entregar .xlsx).';
      return;
    }
    if (res.motivo === 'declined') { msg.className = 'notice info'; msg.textContent = 'Download cancelado.'; return; }

    const motivos = {
      rejected_extension: 'a plataforma não aceita este formato de arquivo',
      extension_not_enabled: 'a plataforma não aceita este formato de arquivo',
      unavailable: 'esta página não tem permissão para salvar arquivos',
      not_granted: 'esta página não tem permissão para salvar arquivos',
      capability_disabled: 'esta página não tem permissão para salvar arquivos',
      capability_removed: 'esta página não tem permissão para salvar arquivos',
      rate_limited: 'muitos downloads seguidos — espere alguns segundos',
      too_large: 'o arquivo ficou grande demais',
      bad_request: 'o arquivo saiu inválido'
    };
    const porque = motivos[res.motivo] || ('o navegador recusou: ' + (res.motivo || 'motivo desconhecido'));

    if (baixarDireto(nomeArquivo(r, 'xlsx'), xlsx, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')) {
      await copiar(textoNumeros(r));
      msg.className = 'notice info';
      msg.innerHTML = 'Mandei a planilha para os downloads do navegador. <b>Se ela não aparecer</b>, foi bloqueada ('
        + xesc(porque) + ') — já deixei todos os números copiados para você colar na planilha, '
        + 'e na pasta <b>A - COMERCIAL › CALCULADORA REVISIONAL</b> o download funciona normalmente.';
      return;
    }
    await copiar(textoNumeros(r));
    msg.className = 'notice warn';
    msg.innerHTML = 'Não consegui salvar o arquivo por aqui — ' + xesc(porque)
      + '. Copiei todos os números para a área de transferência, e na pasta '
      + '<b>A - COMERCIAL › CALCULADORA REVISIONAL</b> o download sai em .xlsx normalmente.';
  }

  async function copiar(txt) {
    try {
      await navigator.clipboard.writeText(txt);
      return true;
    } catch (e) {
      const ta = document.createElement('textarea');
      ta.value = txt;
      ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      let ok = false;
      try { ok = document.execCommand('copy'); } catch (e2) { }
      ta.remove();
      return ok;
    }
  }

  let toastT;
  function toast(msg) {
    const t = $('toast');
    t.textContent = msg;
    t.classList.add('on');
    clearTimeout(toastT);
    toastT = setTimeout(() => t.classList.remove('on'), 2200);
  }

  /* ---------------- leitura do contrato ---------------- */
  // atalho oferecido sempre que o PDF não colabora
  const BTN_MANUAL = '<div class="btnrow" style="margin-top:10px"><button type="button" class="ir-manual">Preencher à mão</button></div>';

  function setCampo(id, valor, origem, estimado) {
    const el = $(id);
    if (el && valor != null && valor !== '') {
      el.value = valor;
      if (origem) S.origem[id] = { texto: origem, estimado: !!estimado };
      badge(id);
    }
  }

  function aplicarLeitura(p) {
    S.origem = {};
    S.escalonado = p.escalonado || null;
    // contrato novo, cliente novo: a situação de pagamento anterior não vale mais
    $('pagas').value = '';
    $('atraso').value = '';
    S.atrasoTocado = false;
    S.acordoTocado = false;
    S.acordo = null;
    $('src-pagas').textContent = '';
    $('dl-msg').classList.add('hidden');
    const c = p.campos, o = p.origem;
    // veio contrato com o valor do bem: volta para a fórmula da planilha
    if (c.valorBem != null && $('baseModo').value !== 'bem') { $('baseModo').value = 'bem'; setBase(); }
    const est = k => /estimad|assumid|n[ãa]o localiz/i.test(o[k] || '');
    if (c.valorBem != null) setCampo('valorBem', NUM2.format(c.valorBem), o.valorBem, est('valorBem'));
    if (c.entrada != null) setCampo('entrada', NUM2.format(c.entrada), o.entrada, est('entrada'));
    if (c.valorParcela != null) setCampo('valorParcela', NUM2.format(c.valorParcela), o.valorParcela, est('valorParcela'));
    if (c.qtdParcelas != null) setCampo('qtdParcelas', String(c.qtdParcelas), o.qtdParcelas, est('qtdParcelas'));
    if (c.balao) setCampo('balao', NUM2.format(c.balao), o.balao, est('balao'));
    if (c.primeiroVencimento) setCampo('primeiroVencimento', c.primeiroVencimento, o.primeiroVencimento);
    if (c.banco) setCampo('banco', c.banco, o.banco);
    if (c.cliente) setCampo('cliente', c.cliente, o.cliente);
    CAMPOS.forEach(badge);

    const box = $('leitura');
    box.classList.remove('hidden');
    const achou = ['valorBem', 'valorParcela', 'qtdParcelas'].filter(k => c[k] != null).length;
    const extras = [];
    if (c.valorFinanciado != null) extras.push('Valor financiado no contrato (com IOF e tarifas): <b>' + money(c.valorFinanciado) + '</b>');
    if (c.jurosMes != null) extras.push('Taxa de juros: <b>' + NUM2.format(c.jurosMes) + '% a.m.</b>');
    if (c.cetMes != null) extras.push('CET: <b>' + NUM2.format(c.cetMes) + '% a.m.</b>');
    if (c.totalPagoFinal != null) extras.push('Total pago ao final (contrato): <b>' + money(c.totalPagoFinal) + '</b>');
    if (c.numeroContrato) extras.push('Contrato nº <b>' + c.numeroContrato + '</b>');
    if (c.veiculo) extras.push('Veículo: <b>' + c.veiculo + (c.placa ? ' · ' + c.placa : '') + '</b>');
    if (c.cpf) extras.push('CPF: <b>' + c.cpf + '</b>');

    if (achou === 3) {
      box.className = 'notice ok';
      box.innerHTML = '<b>Contrato lido.</b> Confira os campos ao lado e informe as parcelas pagas.'
        + (p.avisos.length ? '<ul>' + p.avisos.map(a => '<li>' + a + '</li>').join('') + '</ul>' : '')
        + (extras.length ? '<ul>' + extras.map(e => '<li>' + e + '</li>').join('') + '</ul>' : '');
    } else if (achou > 0) {
      box.className = 'notice warn';
      box.innerHTML = '<b>Li o contrato em parte.</b> Faltou: ' + p.faltando.map(f => ({
        valorBem: 'valor do veículo', valorParcela: 'valor da parcela', qtdParcelas: 'quantidade de parcelas'
      })[f]).join(', ') + '. Complete à mão nos campos ao lado.'
        + (extras.length ? '<ul>' + extras.map(e => '<li>' + e + '</li>').join('') + '</ul>' : '');
    } else {
      box.className = 'notice warn';
      box.innerHTML = '<b>Não encontrei os dados do financiamento neste PDF.</b> Se o contrato for digitalizado (foto ou scan), não há texto para ler — preencha os campos ao lado à mão.' + BTN_MANUAL;
    }
    render();
  }

  /* contrato novo que não abriu: apaga o que veio do contrato anterior, para
     ninguém calcular com os números de outro cliente na tela */
  function limparCamposLidos() {
    let apagou = false;
    CAMPOS.forEach(id => {
      if (S.origem[id]) { $(id).value = ''; delete S.origem[id]; badge(id); apagou = true; }
    });
    if (apagou) {
      $('pagas').value = '';
      $('atraso').value = '';
      S.atrasoTocado = false;
      S.acordoTocado = false;
      S.acordo = null;
      S.escalonado = null;
      $('src-pagas').textContent = '';
      $('src-atraso').textContent = '';
      render();
    }
    return apagou;
  }
  const avisoLimpou = apagou => apagou ? ' <br>Apaguei os dados do contrato anterior para não misturar os clientes.' : '';

  async function lerArquivo(file, senha) {
    S.arquivo = file;
    $('file-info').classList.remove('hidden');
    $('file-info').innerHTML = '<div class="filechip"><span class="nm">' + xesc(file.name) + '</span><span class="meta">' + (file.size / 1024).toFixed(0) + ' KB</span></div>';
    const box = $('leitura');
    box.classList.remove('hidden');
    box.className = 'notice info';
    box.textContent = 'Lendo o contrato…';
    $('drop').classList.add('busy');

    try {
      if (!S.bytes || S.arquivoNome !== file.name) {
        S.bytes = new Uint8Array(await file.arrayBuffer());
        S.arquivoNome = file.name;
      }
      const res = await PDFX.extract(S.bytes, { password: senha || '' });
      S.textoContrato = res.text || '';

      if (res.protegido) {
        const limpou = limparCamposLidos();
        if (res.motivo === 'aes256') {
          box.className = 'notice bad';
          box.innerHTML = '<b>PDF com proteção AES-256.</b> Não consigo abrir esse tipo aqui. Abra o contrato no Adobe Reader, salve uma cópia sem senha e anexe de novo — ou preencha os campos à mão.' + avisoLimpou(limpou) + BTN_MANUAL;
          $('senha-box').classList.add('hidden');
        } else {
          box.className = 'notice warn';
          box.innerHTML = (senha
            ? '<b>Senha incorreta.</b> Tente de novo — costuma ser o CPF do cliente (só os números) ou vir no nome do arquivo.'
            : '<b>Este contrato está protegido por senha.</b> Informe a senha abaixo para eu conseguir ler.') + avisoLimpou(limpou);
          $('senha-box').classList.remove('hidden');
          $('senha').focus();
        }
        return;
      }
      $('senha-box').classList.add('hidden');

      if (!res.ok) {
        const limpou = limparCamposLidos();
        box.className = 'notice warn';
        box.innerHTML = '<b>Este PDF não tem texto para ler.</b> Provavelmente é um contrato digitalizado (foto ou scan). Preencha os campos ao lado à mão.' + avisoLimpou(limpou) + BTN_MANUAL;
        return;
      }
      aplicarLeitura(CONTRATO.parse(res));
      const det = document.createElement('details');
      det.className = 'raw';
      det.innerHTML = '<summary>Ver o texto extraído do contrato</summary><pre>' + xesc(res.text.slice(0, 20000)) + '</pre>';
      box.appendChild(det);
    } catch (e) {
      const limpou = limparCamposLidos();
      box.className = 'notice bad';
      box.innerHTML = '<b>Não consegui ler este arquivo.</b> Confira se é mesmo um PDF. Você pode preencher os campos à mão.' + avisoLimpou(limpou) + BTN_MANUAL;
      console.error(e);
    } finally {
      $('drop').classList.remove('busy');
    }
  }

  /* ---------------- modo de entrada ---------------- */
  function setModo(m) {
    S.modo = m;
    const manual = m === 'manual';
    $('card-pdf').classList.toggle('hidden', manual);
    $('card-manual').classList.toggle('hidden', !manual);
    $('modo-pdf').setAttribute('aria-selected', String(!manual));
    $('modo-manual').setAttribute('aria-selected', String(manual));
    $('hint-dados').textContent = manual ? 'digite os dados' : 'confira e corrija';
    if (manual) $('valorBem').focus({ preventScroll: true });
    render();
  }

  /* veículo − entrada (padrão da planilha) ou o valor financiado direto */
  function setBase() {
    const direta = $('baseModo').value === 'financiado';
    $('wrap-valorBem').classList.toggle('hidden', direta);
    $('wrap-entrada').classList.toggle('hidden', direta);
    $('wrap-valorFinanciado').classList.toggle('hidden', !direta);
    render();
  }

  /* ---------------- eventos ---------------- */
  const drop = $('drop'), file = $('file');
  $('modo-pdf').addEventListener('click', () => setModo('pdf'));
  $('modo-manual').addEventListener('click', () => setModo('manual'));
  $('baseModo').addEventListener('change', setBase);
  // botão "preencher à mão" que aparece dentro dos avisos de leitura
  document.addEventListener('click', e => {
    const b = e.target.closest && e.target.closest('.ir-manual');
    if (b) setModo('manual');
  });
  drop.addEventListener('click', () => file.click());
  drop.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); file.click(); } });
  ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', e => {
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) { S.bytes = null; lerArquivo(f, ''); }
  });
  file.addEventListener('change', () => { if (file.files[0]) { S.bytes = null; lerArquivo(file.files[0], ''); } });
  $('btn-senha').addEventListener('click', () => { if (S.arquivo) lerArquivo(S.arquivo, $('senha').value); });
  $('senha').addEventListener('keydown', e => { if (e.key === 'Enter' && S.arquivo) lerArquivo(S.arquivo, $('senha').value); });

  ['valorBem', 'entrada', 'valorFinanciado', 'valorParcela', 'qtdParcelas', 'balao', 'balaoPago', 'primeiroVencimento', 'banco', 'cliente',
    'pagas', 'atraso', 'pctAcordo', 'pctHonPrev', 'pctDeposito'].forEach(id => {
      const el = $(id);
      el.addEventListener('input', () => {
        if (id === 'atraso') S.atrasoTocado = true;
        if (['valorBem', 'entrada', 'valorParcela', 'qtdParcelas', 'balao'].includes(id) && S.origem[id]) {
          S.origem[id] = { texto: 'você preencheu', estimado: false };
          badge(id);
        }
        render();
      });
      el.addEventListener('change', render);
    });

  ['valorBem', 'entrada', 'valorFinanciado', 'valorParcela', 'balao'].forEach(id => {
    $(id).addEventListener('blur', () => {
      const n = parseNum($(id).value);
      if (n != null) $(id).value = NUM2.format(n);
      render();
    });
  });

  $('btn-whats').addEventListener('click', async () => {
    toast(await copiar($('whats').value) ? 'Resumo copiado' : 'Não consegui copiar — selecione o texto');
  });
  $('btn-numeros').addEventListener('click', async () => {
    toast(await copiar(textoNumeros(S.ultimo)) ? 'Números copiados' : 'Não consegui copiar');
  });
  $('btn-xlsx').addEventListener('click', exportarPlanilha);

  /* Relatório em página única, para imprimir fora daqui quando o navegador
     bloqueia a impressão dentro da página publicada. */
  function relatorioHtml(r) {
    const css = `body{font:13px/1.5 -apple-system,"Segoe UI",Roboto,Arial,sans-serif;color:#12171d;margin:32px;max-width:800px}
h1{font:600 22px Georgia,serif;margin:0 0 2px}p.sub{color:#465262;margin:0 0 22px;font-size:13px}
h2{font-size:11.5px;text-transform:uppercase;letter-spacing:.07em;color:#6d7a8a;margin:22px 0 6px;border-top:1px solid #dbe1e9;padding-top:12px}
table{width:100%;border-collapse:collapse;font-size:13px}
td{padding:6px 0;border-top:1px solid #eef1f5;vertical-align:baseline}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;font-family:ui-monospace,Menlo,monospace}
tr.sum td{border-top:1.5px solid #c2cbd7;font-weight:700}
td .sub{display:block;font-size:11px;color:#6d7a8a}
table.crono td,table.crono th{border-bottom:1px solid #eef1f5;border-top:0;padding:4px 8px;text-align:left;font-size:12px}
table.crono th{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:#6d7a8a}
.pill{font-size:10.5px;font-weight:700}
footer{margin-top:26px;border-top:1px solid #dbe1e9;padding-top:10px;font-size:11px;color:#6d7a8a}
@media print{body{margin:14mm}}`;
    const limpar = html => html.replace(/<input[^>]*value="([^"]*)"[^>]*>/g, '$1');
    return '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>'
      + xesc((r.cliente || 'Cálculo revisional')) + '</title><style>' + css + '</style></head><body>'
      + '<h1>Cálculo revisional</h1><p class="sub">'
      + xesc([r.cliente, r.banco].filter(Boolean).join(' · ') || 'Contrato bancário de veículo') + '</p>'
      + limpar($('ledger').innerHTML)
      + '<h2>Acordo e honorários</h2>' + limpar($('acordo').innerHTML)
      + '<h2>Cronograma de parcelas</h2>' + $('crono').innerHTML
      + '<footer>Valores estimados a partir do contrato apresentado, sujeitos à análise documental '
      + 'e à decisão judicial. Caroline Macedo Advocacia.</footer></body></html>';
  }

  $('btn-print').addEventListener('click', () => {
    const msg = $('dl-msg');
    let abriu = false;
    const marcar = () => { abriu = true; };
    window.addEventListener('beforeprint', marcar);
    try { window.print(); } catch (e) { }

    setTimeout(async () => {
      window.removeEventListener('beforeprint', marcar);
      if (abriu) return;
      // a impressão não abriu (a página publicada roda numa moldura restrita):
      // entrega o relatório pronto para imprimir por fora
      const html = relatorioHtml(S.ultimo);
      msg.classList.remove('hidden');
      try {
        const w = window.open('', '_blank');
        if (w && w.document) {
          w.document.write(html);
          w.document.close();
          setTimeout(() => { try { w.focus(); w.print(); } catch (e) { } }, 500);
          msg.className = 'notice ok';
          msg.textContent = 'Abri o relatório numa aba nova — imprima ou salve em PDF por lá (Cmd + P).';
          return;
        }
      } catch (e) { }
      const res = await salvar(nomeArquivo(S.ultimo, 'html'), html);
      if (res.ok) {
        msg.className = 'notice ok';
        msg.innerHTML = 'Esta página não tem permissão para abrir a impressão. Baixei o relatório como <b>'
          + res.nome + '</b> — abra o arquivo e imprima com Cmd + P.';
      } else if (res.motivo === 'declined') {
        msg.className = 'notice info';
        msg.textContent = 'Download cancelado.';
      } else {
        msg.className = 'notice warn';
        msg.innerHTML = 'Esta página não tem permissão para imprimir nem para salvar o arquivo aqui ('
          + xesc(res.motivo || 'bloqueado') + '). Use a versão da pasta <b>A - COMERCIAL › CALCULADORA REVISIONAL</b>, '
          + 'onde a impressão e o download funcionam normalmente.';
      }
    }, 900);
  });

  $('btn-limpar').addEventListener('click', () => {
    ['valorBem', 'entrada', 'valorFinanciado', 'valorParcela', 'qtdParcelas', 'balao', 'primeiroVencimento', 'banco', 'cliente', 'pagas', 'atraso', 'senha'].forEach(id => $(id).value = '');
    $('balaoPago').value = 'nao';
    S.origem = {}; S.escalonado = null; S.atrasoTocado = false; S.acordoTocado = false; S.acordo = null;
    S.arquivo = null; S.bytes = null; S.arquivoNome = null;
    CAMPOS.forEach(badge);
    $('src-atraso').textContent = ''; $('src-pagas').textContent = '';
    $('file-info').classList.add('hidden');
    $('leitura').classList.add('hidden');
    $('senha-box').classList.add('hidden');
    $('dl-msg').classList.add('hidden');
    file.value = '';
    render();
  });

  $('btn-exemplo').addEventListener('click', () => {
    S.origem = {}; S.escalonado = null; S.atrasoTocado = false; S.acordoTocado = false; S.acordo = null;
    if ($('baseModo').value !== 'bem') { $('baseModo').value = 'bem'; setBase(); }
    setCampo('cliente', 'AGENOR ANTONIO PASOLIN', 'exemplo');
    setCampo('banco', 'Banco Volkswagen S.A.', 'exemplo');
    setCampo('valorBem', '70.000,00', 'exemplo');
    setCampo('entrada', '30.000,00', 'exemplo');
    setCampo('valorParcela', '1.428,65', 'exemplo');
    setCampo('qtdParcelas', '48', 'exemplo');
    setCampo('balao', '0,00', 'exemplo');
    setCampo('primeiroVencimento', '23/02/2024', 'exemplo');
    $('pagas').value = '3';
    S.atrasoTocado = false;
    if (S.modo === 'manual') {
      toast('Exemplo carregado');
    } else {
      $('leitura').classList.remove('hidden');
      $('leitura').className = 'notice info';
      $('leitura').innerHTML = '<b>Exemplo carregado</b> — os números do AGENOR ANTONIO PASOLIN, iguais aos da planilha de julho.';
    }
    render();
  });

  render();
  window.__app = { calcular, lerFormulario, planilhaDoCliente, cronograma, S };
})();
