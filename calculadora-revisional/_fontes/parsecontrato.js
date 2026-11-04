/* Heurísticas de leitura de contratos bancários de financiamento de veículo. */
const CONTRATO = (() => {

  const BANCOS = [
    ['Aymoré Crédito, Financiamento e Investimento S.A.', /aymor[ée]/i],
    ['Banco ABN AMRO Real S.A.', /abn\s*amro/i],
    ['Banco BMG S.A.', /banco\s+bmg|\bbmg\b/i],
    ['Banco Bradesco Financiamentos S.A.', /bradesco\s+financiamentos/i],
    ['Banco Bradesco S.A.', /bradesco/i],
    ['Banco do Brasil S.A.', /banco\s+do\s+brasil/i],
    ['Banco GMAC S.A.', /\bgmac\b/i],
    ['Banco Honda S.A.', /banco\s+honda|bancohonda/i],
    ['Banco Hyundai Capital Brasil S.A.', /hyundai\s+capital/i],
    ['Banco Itaú BMG Consignado S.A.', /ita[úu]\s+bmg/i],
    ['Banco Itaucard S.A.', /itaucard/i],
    ['Banco Itauleasing S.A.', /itauleasing|itaú\s*leasing/i],
    ['Banco Itaú Veiculos S.A.', /ita[úu]\s+ve[íi]culos/i],
    ['Banco Pan S.A.', /banco\s+pan|bancopan/i],
    ['Banco PSA Finance Brasil S.A.', /psa\s+finance/i],
    ['Banco RCI Brasil S.A.', /\brci\b/i],
    ['Banco Safra S.A.', /banco\s+safra|safrafinanceira|safra\s+financeira/i],
    ['Banco Santander (Brasil) S.A.', /santander/i],
    ['Banco Toyota do Brasil S.A.', /banco\s+toyota/i],
    ['Banco Volkswagen S.A.', /banco\s+volkswagen|\bbanco\s+vw\b/i],
    ['Banco Votorantim S.A.', /votorantim/i],
    ['Banco Yamaha Motor do Brasil S.A.', /banco\s+yamaha/i],
    ['Bradesco Administradora de Consórcios LTDA.', /bradesco\s+administradora/i],
    ['BV Financeira S.A.', /\bbv\s+financeira\b/i],
    ['Caixa Econômica Federal', /caixa\s+econ[ôo]mica/i],
    ['Consórcio Nacional Honda LTDA.', /cons[óo]rcio\s+nacional\s+honda/i],
    ['Consórcio Nacional Volkswagen - Administradora de Consórcio LTDA.', /cons[óo]rcio\s+nacional\s+volkswagen/i],
    ['Itaú Unibanco S.A.', /ita[úu]\s+unibanco/i],
    ['Portoseg S/A - Crédito, Financiamento e Investimento', /portoseg/i],
    ['Porto Seguro Companhia de Seguros Gerais', /porto\s+seguro/i],
    ['Safra Leasing S.A. Arrendamento Mercantil', /safra\s+leasing/i],
    ['Santander Leasing S.A. Arrendamento Mercantil', /santander\s+leasing/i],
    ['Banco Cetelem S.A.', /cetelem/i],
    ['Banco Daycoval S.A.', /daycoval/i],
    ['Banco Mercedes-Benz do Brasil S.A.', /mercedes[- ]benz/i],
    ['Banco Fidis S.A.', /\bfidis\b/i],
    ['Omni Banco S.A.', /\bomni\b/i],
    ['Banco C6 S.A.', /\bc6\s+(bank|banco)|banco\s+c6/i],
    ['Banco CNH Industrial Capital S.A.', /cnh\s+industrial/i],
    ['Sinosserra / Consórcio', /sinosserra/i],
  ];

  /* ---------- utilitários numéricos ---------- */
  const MONEY = '(?:R\\$\\s*)?(-?\\d{1,3}(?:\\.\\d{3})+,\\d{2}|-?\\d+,\\d{2}|-?\\d{4,})';
  function toNum(s) {
    if (s == null) return null;
    s = String(s).trim().replace(/R\$/gi, '').trim();
    if (!s) return null;
    if (/^\d{1,3}(\.\d{3})+,\d+$/.test(s)) s = s.replace(/\./g, '').replace(',', '.');
    else if (/^\d+,\d+$/.test(s)) s = s.replace(',', '.');
    else if (/^\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, '');
    else s = s.replace(/\s/g, '');
    const n = parseFloat(s);
    return isNaN(n) ? null : n;
  }
  function moneysIn(str) {
    const out = [];
    const re = new RegExp(MONEY, 'g');
    let m;
    while ((m = re.exec(str))) {
      const v = toNum(m[1]);
      if (v != null) out.push({ v, i: m.index, raw: m[1] });
    }
    return out;
  }
  function intsIn(str) {
    const out = [];
    const re = /(?:^|[^\d,.\/-])(\d{1,3})(?![\d,.\/-])/g;
    let m;
    while ((m = re.exec(str))) out.push({ v: parseInt(m[1], 10), i: m.index });
    return out;
  }

  /* ---------- busca por rótulo ---------- */
  function findLabeled(lines, patterns, opts) {
    opts = opts || {};
    const pick = opts.pick || 'money';
    const veto = opts.veto;
    const lookahead = opts.lookahead === undefined ? 2 : opts.lookahead;
    for (let pi = 0; pi < patterns.length; pi++) {
      const pat = patterns[pi];
      for (let li = 0; li < lines.length; li++) {
        const line = lines[li];
        const m = pat.exec(line);
        pat.lastIndex = 0;
        if (!m) continue;
        if (veto && veto.test(line)) continue;
        const after = line.slice(m.index + m[0].length);
        // quantos rótulos "irmãos" aparecem antes deste na mesma linha (layout de 2 colunas)
        let ordinal = 0;
        if (opts.ordinal) {
          const head = line.slice(0, m.index);
          const om = head.match(new RegExp(opts.ordinal.source, 'gi'));
          ordinal = om ? om.length : 0;
        }
        const cands = [];
        const grab = (txt, src, dist) => {
          let items = pick === 'int' ? intsIn(txt) : moneysIn(txt);
          if (opts.zeroOk) {
            const zr = /(?:^|[^\d,.])(0)(?![\d,.])/g;
            let z;
            while ((z = zr.exec(txt))) items.push({ v: 0, i: z.index });
            items.sort((a, b) => a.i - b.i);
          }
          if (dist > 0 && ordinal) items = items.slice(ordinal);
          for (const it of items) cands.push({ v: it.v, dist, src, pos: it.i });
        };
        grab(after, 'linha', 0);
        for (let k = 1; k <= lookahead && li + k < lines.length; k++) {
          if (patterns.some(p => { const r = p.test(lines[li + k]); p.lastIndex = 0; return r; })) break;
          grab(lines[li + k], 'linha+' + k, k);
        }
        if (!cands.length && lookahead > 0) grab(line.slice(0, m.index), 'antes', 3);
        const valid = cands.filter(c => opts.accept ? opts.accept(c.v) : true);
        if (valid.length) {
          valid.sort((a, b) => (a.dist - b.dist) || (a.pos - b.pos));
          return { value: valid[0].v, line, label: m[0].trim(), rank: pi, from: valid[0].src };
        }
        if (opts.defaultIfLabeled !== undefined) {
          return { value: opts.defaultIfLabeled, line, label: m[0].trim(), rank: pi, from: 'linha' };
        }
      }
    }
    return null;
  }

  function findText(lines, patterns, opts) {
    opts = opts || {};
    for (const pat of patterns) {
      for (const line of lines) {
        const m = pat.exec(line);
        pat.lastIndex = 0;
        if (!m) continue;
        let val = (m[1] !== undefined ? m[1] : line.slice(m.index + m[0].length)).trim();
        val = val.replace(/\s{2,}/g, ' ').trim();
        if (opts.stop) val = val.split(opts.stop)[0].trim();
        val = val.replace(/[:\-–—]+$/, '').trim();
        if (val && (!opts.min || val.length >= opts.min)) return { value: val, line };
      }
    }
    return null;
  }

  /* ---------- parcelas variáveis (formato Safra: "001 a 007: R$ 1.104,78 | ...") ---------- */
  function parseEscalonado(str) {
    const re = /(\d{1,3})\s*a\s*(\d{1,3})\s*:?\s*R?\$?\s*([\d.]+,\d{2})/gi;
    const blocks = [];
    let m;
    while ((m = re.exec(str))) {
      const de = parseInt(m[1], 10), ate = parseInt(m[2], 10), v = toNum(m[3]);
      if (v != null && ate >= de) blocks.push({ de, ate, v, n: ate - de + 1 });
    }
    if (blocks.length < 2) return null;
    const tally = new Map();
    for (const b of blocks) tally.set(b.v, (tally.get(b.v) || 0) + b.n);
    const sorted = [...tally.entries()].sort((a, b) => b[1] - a[1]);
    const normal = sorted[0][0];
    const maiores = [...tally.keys()].filter(v => v > normal);
    const balaoVal = maiores.length ? Math.max(...maiores) : 0;
    const qtdBalao = balaoVal ? (tally.get(balaoVal) || 0) : 0;
    const total = Math.max(...blocks.map(b => b.ate));
    return {
      parcela: normal,
      balaoUnit: balaoVal || 0,
      balaoQtd: qtdBalao,
      balaoTotal: balaoVal ? +(balaoVal - normal).toFixed(2) * qtdBalao : 0,
      balaoTotalCheio: balaoVal * qtdBalao,
      qtdParcelas: total,
      blocks
    };
  }

  /* ---------- parser principal ---------- */
  function parse(res) {
    const rawLines = (res.text || '').split('\n').map(l => l.replace(/ /g, ' ').trim()).filter(Boolean);
    const lines = rawLines;
    const all = lines.join('\n');
    const fieldsText = (res.fields || []).map(f => f.name + ': ' + f.value).join('\n');
    const out = { campos: {}, origem: {}, avisos: [], textoLinhas: lines.length };

    const set = (k, r, fmt) => {
      if (!r || r.value == null) return;
      out.campos[k] = fmt ? fmt(r.value) : r.value;
      out.origem[k] = r.label ? (r.label + (r.from && r.from !== 'linha' ? ' (' + r.from + ')' : '')) : (r.line || '').slice(0, 80);
    };

    /* --- escalonamento em campo de formulário (parcela balão do Safra) --- */
    let esc = null;
    for (const f of (res.fields || [])) {
      const e = parseEscalonado(f.value);
      if (e) { esc = e; break; }
    }
    if (!esc) {
      for (const l of lines) { const e = parseEscalonado(l); if (e) { esc = e; break; } }
    }

    /* --- valores --- */
    const posMoney = v => v > 0 && v < 100000000;

    set('valorBem', findLabeled(lines, [
      /valor\s+do\s+ve[íi]culo\s+[àa]\s+vista/i,
      /valor\s+do\s+bem\s*\/\s*ve[íi]culo[^:]*/i,
      /valor\s+total\s+do\(s\)\s*bem\(ns\)/i,
      /valor\s+do\s+bem\b[^:]*/i,
      /valor\s+(?:de\s+)?(?:venda|aquisi[çc][ãa]o)\s+do\s+ve[íi]culo/i,
      /pre[çc]o\s+(?:de\s+venda\s+)?do\s+ve[íi]culo/i,
      /valor\s+do\s+ve[íi]culo/i,
    ], { accept: posMoney }));

    set('entrada', findLabeled(lines, [
      /valor\s+(?:da\s+)?entrada\s*(?:\(\d\))?/i,
      /valor\s+entrada\s*(?:\(\d\))?/i,
      /pagamento\s+inicial\s*\/?\s*entrada/i,
      /entrada\s*\(recursos\s+pr[óo]prios\)/i,
      /valor\s+pago\s+de\s+entrada/i,
    ], { accept: v => v >= 0 && v < 100000000 }));

    set('valorFinanciado', findLabeled(lines, [
      /valor\s+total\s+financiado\s*\(com\s+impostos\)[^R\d]*/i,
      /valor\s+financiado\s*\([^)]*\)\s*:?/i,
      /valor\s+total\s+financiado/i,
      /valor\s+l[íi]quido\s+do\s+cr[ée]dito/i,
      /valor\s+total\s+do\s+cr[ée]dito/i,
      /valor\s+financiado/i,
    ], { accept: posMoney }));

    const parcelaRes = findLabeled(lines, [
      /valor\s+de\s+cada\s+parcela\s+mensal/i,
      /\(i\)\s*valor\s+das\s+parcelas/i,
      /valor\s+de\s+cada\s+presta[çc][ãa]o/i,
      /valor\s+da\s+parcela\s+mensal/i,
      /valor\s+das\s+parcelas\s*:/i,
      /valor\s+da\s+presta[çc][ãa]o/i,
      /valor\s+da\s+parcela/i,
      /valor\s+das\s+presta[çc][õo]es/i,
    ], { accept: posMoney, veto: /intermedi|balão|bal[ãa]o|residual|total\s+das\s+parcelas/i });
    set('valorParcela', parcelaRes);

    set('qtdParcelas', findLabeled(lines, [
      /n[úu]mero\s+de\s+parcelas\s+mensais\s*:?/i,
      /\(ii\)\s*quantidade\s+de\s+parcelas\s*:?/i,
      /quantidade\s+de\s+parcelas\s*:?/i,
      /prazo\s*\(em\s+meses\)\s*:?/i,
      /n[úu]mero\s+de\s+presta[çc][õo]es\s*:?/i,
      /qtde?\.?\s+de\s+parcelas\s*:?/i,
      /prazo\s+(?:total\s+)?(?:da\s+opera[çc][ãa]o\s*)?(?:em\s+)?meses\s*:?/i,
      /n[.º°]?\s*de\s+parcelas\s*:?/i,
      /prazo\s*:?/i,
    ], { pick: 'int', accept: v => v >= 1 && v <= 480, veto: /validade|car[êe]ncia|entrega/i }));

    set('parcelasIntermediarias', findLabeled(lines, [
      /valor\s+total\s+das\s+parcelas\s+intermedi[áa]rias[^:]*:?/i,
      /parcelas?\s+intermedi[áa]rias?[^:]*:?/i,
      /parcela\s+bal[ãa]o[^:]*:?/i,
      /valor\s+residual\s+garantido[^:]*:?/i,
      /\bvrg\b[^:]*:?/i,
    ], { accept: v => v >= 0 && v < 100000000, lookahead: 0, zeroOk: true, defaultIfLabeled: 0 }));

    set('totalPagoFinal', findLabeled(lines, [
      /valor\s+total\s+pago\s+ao\s+final[^R\d]*/i,
      /valor\s+equivalente\s+[àa]\s*\(i\)\s*x\s*\(ii\)\s*:?/i,
      /valor\s+total\s+a\s+pagar/i,
      /montante\s+total\s+devido/i,
    ], { accept: posMoney }));

    set('jurosMes', findLabeled(lines, [
      /taxa\s+de\s+juros\s+efetiva\s*-\s*mensal\s*:?/i,
      /juros\s+remunerat[óo]rios[^%]*?%\s*a\.?\s*m\.?\s*:?/i,
      /taxa\s+de\s+juros[^%]{0,40}%\s*a\.?\s*m\.?\s*:?/i,
      /taxa\s+de\s+juros\s+da\s+opera[çc][ãa]o\s*:?/i,
      /%\s*a\.?\s*m\.?\s*:?/i,
    ], { accept: v => v > 0 && v < 30 }));

    set('cetMes', findLabeled(lines, [
      /cet\s*%\s*a\.?\s*m\.?\s*:?/i,
      /cet[^%]{0,40}%\s*a\.?\s*m\.?\s*:?/i,
      /custo\s+efetivo\s+total[^:]*:?/i,
    ], { accept: v => v > 0 && v < 40 }));

    set('cetAno', findLabeled(lines, [
      /cet\s*%\s*a\.?\s*a\.?\s*:?/i,
      /cet[^%]{0,40}%\s*a\.?\s*a\.?\s*:?/i,
    ], { accept: v => v > 0 && v < 500, ordinal: /%\s*a\.?\s*m\.?/ }));

    /* --- datas e textos --- */
    const dt = findText(lines, [
      /data\s+do\s+1[º°ªo]?\s*vencimento\s*:?\s*(\d{2}\/\d{2}\/\d{4})/i,
      /vencimento\s+da\s+1[ªa]\s*parcela\s*:?\s*(\d{2}\/\d{2}\/\d{4})/i,
      /1[º°ªo]\s*vencimento\s*:?\s*(\d{2}\/\d{2}\/\d{4})/i,
      /primeiro\s+vencimento\s*:?\s*(\d{2}\/\d{2}\/\d{4})/i,
      /vencimento\s+inicial\s*:?\s*(\d{2}\/\d{2}\/\d{4})/i,
    ]);
    if (dt) { out.campos.primeiroVencimento = dt.value; out.origem.primeiroVencimento = 'data do 1º vencimento'; }

    const dc = findText(lines, [
      /data\s+da\s+contrata[çc][ãa]o[^\d]*(\d{2}\/\d{2}\/\d{4})/i,
      /data\s+de\s+emiss[ãa]o[^\d]*(\d{2}\/\d{2}\/\d{4})/i,
    ]);
    if (dc) { out.campos.dataContrato = dc.value; out.origem.dataContrato = 'data da contratação'; }

    const nome = findText(lines, [
      /nome\s*\/\s*raz[ãa]o\s+social\s+do\s+cliente\s*:?\s*(.+)/i,
      /nome\s+do\(a\)\s+consumidor\(a\)\s*:?\s*(.+)/i,
      /nome\s*\/\s*raz[ãa]o\s+social\s*:?\s*(.+)/i,
      /nome\s+do\s+cliente\s*:?\s*(.+)/i,
      /nome\s+do\s+emitente\s*:?\s*(.+)/i,
      /cliente\s*:?\s*([A-ZÁÂÃÉÊÍÓÔÕÚÇ][A-ZÁÂÃÉÊÍÓÔÕÚÇ\s]{8,})/,
    ], { stop: /\s(?:CPF|CNPJ|RG|Endere|E-?mail)/i, min: 5 });
    if (nome) {
      const v = nome.value.replace(/\s+(CPF|CNPJ|RG).*$/i, '').trim();
      const pareceNome = /[A-Za-zÀ-ÿ]{3,}\s+[A-Za-zÀ-ÿ]{2,}/.test(v) &&
        !/^(cpf|cnpj|rg|nome|raz[ãa]o|endere[çc]o|e-?mail)\b/i.test(v);
      if (pareceNome) { out.campos.cliente = v; out.origem.cliente = 'nome do cliente'; }
    }

    const cpf = /(\d{3}\.\d{3}\.\d{3}-\d{2})/.exec(all);
    if (cpf) { out.campos.cpf = cpf[1]; out.origem.cpf = 'CPF no contrato'; }

    const ehData = s => /^\d{2}\/\d{2}\/\d{2,4}$/.test(s);
    let contrato = null;
    for (const pat of [
      /n[º°]\s*(?:do\s*)?contrato\s*:?\s*([0-9][0-9A-Za-z\/.-]{5,30})/i,
      /(?:opera[çc][ãa]o|or[çc]amento|c[ée]dula|contrato)\s*n?[º°.]*\s*:?\s*([0-9][0-9A-Za-z\/.-]{5,30})/i,
    ]) {
      for (const line of lines) {
        if (/data\s+d[aeo]/i.test(line.slice(0, Math.max(0, (pat.exec(line) || { index: 0 }).index)))) { pat.lastIndex = 0; continue; }
        const m = pat.exec(line);
        pat.lastIndex = 0;
        if (!m) continue;
        const v = m[1].replace(/[.,;]$/, '');
        if (ehData(v) || !/\d/.test(v)) continue;
        contrato = v; break;
      }
      if (contrato) break;
    }
    if (!contrato) {
      // layout do PAN: a palavra "Contrato" isolada e o número em uma das linhas seguintes
      const idx = lines.findIndex(l => /^contrato\s*$/i.test(l));
      if (idx >= 0) {
        for (let k = 1; k <= 3 && idx + k < lines.length; k++) {
          const m = /(?:^|\s)(\d{6,20})(?:\s|$)/.exec(lines[idx + k]);
          if (m) { contrato = m[1]; break; }
        }
      }
    }
    if (contrato) {
      out.campos.numeroContrato = contrato;
      out.origem.numeroContrato = 'número da operação/contrato';
    }

    const marca = findText(lines, [
      /ve[íi]culo\s*:?\s*marca\s*:?\s*(.+)/i,
      /ve[íi]culo\s*-\s*marca\s*:?\s*(.+)/i,
      /^marca\s*:?\s*(.+)/i,
      /marca\s*\/\s*modelo\s*:?\s*(.+)/i,
    ], { stop: /\s(?:Combust|Chassi|Ano|Cor)/i, min: 3 });
    if (marca) { out.campos.veiculo = marca.value.replace(/\s+(Modelo:)\s*/i, ' ').trim(); out.origem.veiculo = 'marca/modelo'; }

    const placa = /\b([A-Z]{3}-?\d[A-Z0-9]\d{2})\b/.exec(all);
    if (placa) { out.campos.placa = placa[1]; out.origem.placa = 'placa no contrato'; }
    const renavam = findText(lines, [/renavam\s*:?\s*(\d{9,11})/i]);
    if (renavam) { out.campos.renavam = renavam.value; out.origem.renavam = 'renavam'; }
    const anoM = findText(lines, [/ano\s*\/?\s*modelo\s*:?\s*(\d{4}(?:\/\d{4})?)/i, /ano\.?\s*mod\.?\s*:?\s*(\d{4})/i]);
    if (anoM) { out.campos.anoModelo = anoM.value; out.origem.anoModelo = 'ano/modelo'; }

    for (const [nomeBanco, re] of BANCOS) {
      if (re.test(all) || re.test(fieldsText)) { out.campos.banco = nomeBanco; out.origem.banco = 'instituição citada no contrato'; break; }
    }

    /* --- consolidação do escalonamento --- */
    if (esc) {
      out.escalonado = esc;
      if (!out.campos.valorParcela || Math.abs(out.campos.valorParcela - esc.parcela) > 0.01) {
        out.campos.valorParcela = esc.parcela;
        out.origem.valorParcela = 'quadro de parcelas do contrato';
      }
      if (!out.campos.qtdParcelas) {
        out.campos.qtdParcelas = esc.qtdParcelas;
        out.origem.qtdParcelas = 'quadro de parcelas do contrato';
      }
      if (esc.balaoUnit) {
        out.campos.balaoUnitario = esc.balaoUnit;
        out.campos.balaoQtd = esc.balaoQtd;
        out.campos.balao = +(esc.balaoUnit - esc.parcela).toFixed(2) * esc.balaoQtd;
        out.origem.balao = esc.balaoQtd + '× parcela de ' + esc.balaoUnit.toFixed(2) + ' (acréscimo sobre a parcela normal)';
        out.avisos.push('Contrato com ' + esc.balaoQtd + ' parcelas maiores (R$ ' + esc.balaoUnit.toLocaleString('pt-BR', { minimumFractionDigits: 2 }) + '), tratadas como balão.');
      }
    }
    if (out.campos.balao == null && out.campos.parcelasIntermediarias) {
      out.campos.balao = out.campos.parcelasIntermediarias;
      out.origem.balao = out.origem.parcelasIntermediarias;
    }

    /* --- coerências e complementos --- */
    if (out.campos.valorBem == null && out.campos.valorFinanciado != null) {
      out.campos.valorBem = out.campos.valorFinanciado + (out.campos.entrada || 0);
      out.origem.valorBem = 'estimado: valor financiado + entrada';
      out.avisos.push('O contrato não traz o valor do veículo à vista — usei o valor financiado. Confira.');
    }
    if (out.campos.entrada == null) {
      if (out.campos.valorBem != null && out.campos.valorFinanciado != null && out.campos.valorBem > out.campos.valorFinanciado) {
        out.campos.entrada = +(out.campos.valorBem - out.campos.valorFinanciado).toFixed(2);
        out.origem.entrada = 'estimado: valor do bem − valor financiado';
      } else {
        out.campos.entrada = 0;
        out.origem.entrada = 'não localizada no contrato (assumida como zero)';
      }
    }
    if (out.campos.valorParcela == null && out.campos.totalPagoFinal && out.campos.qtdParcelas) {
      const p = (out.campos.totalPagoFinal - (out.campos.entrada || 0)) / out.campos.qtdParcelas;
      if (p > 0) {
        out.campos.valorParcela = +p.toFixed(2);
        out.origem.valorParcela = 'estimado: (total pago ao final − entrada) ÷ nº de parcelas';
      }
    }

    const faltando = ['valorBem', 'valorParcela', 'qtdParcelas'].filter(k => out.campos[k] == null);
    out.completo = faltando.length === 0;
    out.faltando = faltando;
    return out;
  }

  return { parse, parseEscalonado, toNum, BANCOS };
})();

function parseContrato(res) { try { return CONTRATO.parse(res); } catch (e) { return { erro: String(e && e.stack || e) }; } }
if (typeof module !== 'undefined') module.exports = CONTRATO;
