// Rodar no Chrome com pro.contaazul.com aberto e logado (Financeiro > Contas a receber).
// Usa o mesmo endpoint interno da tela; a sessão vai pelo cookie (withCredentials).
// Depois de rodar, a saída fica em window.__CAOUT[mes] (uma linha por lançamento):
//   nome|centavos|cat|forma|vencimento AAAA-MM-DD|situação|pago AAAA-MM-DD|conjuntos|conta|parcela
//   cat RV/BA/CV/PA(parceiros) · forma B boleto, L link, O outro · situação R/V/L/P/Z(zerada por renegociação)
//   conta C Conta PJ, A espelho ASAAS, S Sicredi · conjuntos r recebido no mês, v venceu no mês
// O javascript_tool do Chrome corta a resposta em ~1000 caracteres: leia em blocos de 15 linhas,
// window.__CAOUT['2026-10'].slice(0,15).join('\n'), slice(15,30)...
async function extrairContaAzul(meses) {
  const post = (body, page) => new Promise((ok, erro) => {
    const x = new XMLHttpRequest();
    x.open('POST', 'https://services.contaazul.com/finance-pro-reader/v1/installment-view?page=' + page + '&page_size=100');
    x.withCredentials = true;
    x.setRequestHeader('Accept', 'application/json');
    x.setRequestHeader('Content-Type', 'application/json');
    x.onload = () => x.status === 200 ? ok(JSON.parse(x.responseText)) : erro(new Error('Conta Azul ' + x.status + ': ' + x.responseText.slice(0, 120)));
    x.onerror = () => erro(new Error('sem conexão'));
    x.send(JSON.stringify(body));
  });
  const base = {quickFilter: 'ALL', search: '', type: 'REVENUE', selectedColumns: ['DUE_DATE', 'PAYMENT_DATE', 'SUMMARY', 'VALUE', 'UNPAID', 'STATUS']};
  const todas = async (f) => { let p = 1, out = [], tot = 1; while (out.length < tot && p < 30) { const j = await post({...base, ...f}, p); tot = j.totalItems; if (!j.items.length) break; out.push(...j.items); p++; } return out; };
  const cat = s => /REVISIONAL/i.test(s) ? 'RV' : /BUSCA/i.test(s) ? 'BA' : /CIVIL/i.test(s) ? 'CV' : /PARCEIR/i.test(s) ? 'PA' : '--';
  window.__CAOUT = window.__CAOUT || {};
  const resumo = {};
  for (const mes of meses) {
    const [a, m] = mes.split('-').map(Number);
    const ini = mes + '-01', fim = new Date(a, m, 0).toISOString().slice(0, 10);
    const V = await todas({dueDateFrom: ini, dueDateTo: fim});
    const P = await todas({paymentDateFrom: ini, paymentDateTo: fim});
    const map = new Map();
    for (const [k, arr] of [['r', P], ['v', V]]) for (const x of arr) { const o = map.get(x.id) || {x, fl: ''}; o.fl += k; map.set(x.id, o); }
    window.__CAOUT[mes] = [...map.values()].map(({x, fl}) => {
      let st = x.status === 'ACQUITTED' ? 'R' : x.status === 'LOST' ? 'L' : x.status === 'OVERDUE' ? 'V' : x.status === 'PENDING' ? 'P' : 'V';
      if (st === 'V' && !x.unpaid && x.renegotiation) st = 'Z';
      const valor = st === 'R' ? (x.valueComposition?.grossValue || x.paid) : st === 'L' ? x.totalNetValue : (x.unpaid || 0);
      const parc = (x.description.match(/^(\d+\/\d+) - Venda/) || [])[1] || (/^Venda/.test(x.description) ? 'U' : /Cobranca recebida/i.test(x.description) ? 'AS' : 'PX');
      const nome = /^RECEBIMENTO PIX/i.test(x.description) ? 'PIX DE PARCEIRO (' + x.description.replace(/^RECEBIMENTO PIX \d+ /i, '').slice(0, 20) + ')' : (x.financialEvent.negotiator?.name || x.description);
      const conta = (x.financialAccount?.name || '?').toUpperCase();
      return [nome.replace(/\s+/g, ' ').trim().slice(0, 40), Math.round(valor * 100), cat(x.financialEvent.categoryDescriptions || ''),
        {BANKING_BILLET: 'B', PAYMENT_LINK: 'L'}[x.paymentMethod] || 'O', x.dueDate, st, (st === 'R' ? x.lastAcquittanceDate : '') || '', fl,
        conta === 'ASAAS' ? 'A' : conta.includes('SICREDI') ? 'S' : 'C', parc].join('|');
    }).sort();
    resumo[mes] = {linhas: window.__CAOUT[mes].length, vencimento: V.length, pagamento: P.length};
  }
  return JSON.stringify(resumo);
}
