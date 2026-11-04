/* PDFX — extrator de texto de PDF em JS puro (sem dependências externas).
   Suporta: objetos diretos e em ObjStm, FlateDecode (via DecompressionStream),
   preditor PNG, árvore de páginas, matrizes de texto, ToUnicode CMap,
   Encoding/Differences, Type0 (2 bytes) e campos de formulário AcroForm. */
const PDFX = (() => {
  /* latin1 verdadeiro: TextDecoder('latin1') é apelido de windows-1252 e corromperia
     os bytes 0x80–0x9F, quebrando chaves de criptografia e offsets binários. */
  function bin(u8) {
    let s = '';
    const CH = 0x8000;
    for (let i = 0; i < u8.length; i += CH) s += String.fromCharCode.apply(null, u8.subarray(i, i + CH));
    return s;
  }
  const WS = " \t\r\n\f\0";
  const DELIM = "()<>[]{}/%";
  const isws = c => WS.indexOf(c) >= 0;
  const isdelim = c => DELIM.indexOf(c) >= 0;

  /* ---------------- tokenizer ---------------- */
  class Lexer {
    constructor(s, pos = 0, end = s.length) { this.s = s; this.p = pos; this.end = end; }
    skip() {
      const s = this.s;
      while (this.p < this.end) {
        const c = s[this.p];
        if (isws(c)) this.p++;
        else if (c === '%') { while (this.p < this.end && s[this.p] !== '\n' && s[this.p] !== '\r') this.p++; }
        else break;
      }
    }
    next() {
      this.skip();
      if (this.p >= this.end) return null;
      const s = this.s, c = s[this.p];
      if (c === '/') {
        this.p++; const st = this.p;
        while (this.p < this.end && !isws(s[this.p]) && !isdelim(s[this.p])) this.p++;
        let n = s.slice(st, this.p);
        if (n.indexOf('#') >= 0) n = n.replace(/#([0-9a-fA-F]{2})/g, (m, h) => String.fromCharCode(parseInt(h, 16)));
        return { t: 'name', v: n };
      }
      if (c === '(') return { t: 'str', v: this.litString() };
      if (c === '<') {
        if (s[this.p + 1] === '<') { this.p += 2; return { t: '<<' }; }
        return { t: 'str', v: this.hexString() };
      }
      if (c === '>') { if (s[this.p + 1] === '>') { this.p += 2; return { t: '>>' }; } this.p++; return { t: 'junk' }; }
      if (c === '[') { this.p++; return { t: '[' }; }
      if (c === ']') { this.p++; return { t: ']' }; }
      if (c === '{' || c === '}' || c === ')') { this.p++; return { t: 'junk' }; }
      const st = this.p;
      while (this.p < this.end && !isws(s[this.p]) && !isdelim(s[this.p])) this.p++;
      if (this.p === st) { this.p++; return { t: 'junk' }; }
      const w = s.slice(st, this.p);
      if (/^[+-]?(\d+\.?\d*|\.\d+)$/.test(w)) return { t: 'num', v: parseFloat(w) };
      return { t: 'kw', v: w };
    }
    litString() {
      const s = this.s; this.p++; let depth = 1, out = '';
      while (this.p < this.end) {
        const c = s[this.p++];
        if (c === '\\') {
          const e = s[this.p++];
          if (e === 'n') out += '\n';
          else if (e === 'r') out += '\r';
          else if (e === 't') out += '\t';
          else if (e === 'b') out += '\b';
          else if (e === 'f') out += '\f';
          else if (e >= '0' && e <= '7') {
            let o = e;
            for (let k = 0; k < 2; k++) { const d = s[this.p]; if (d >= '0' && d <= '7') { o += d; this.p++; } else break; }
            out += String.fromCharCode(parseInt(o, 8) & 0xff);
          } else if (e === '\n') { /* continuação */ }
          else if (e === '\r') { if (s[this.p] === '\n') this.p++; }
          else out += e;
        } else if (c === '(') { depth++; out += c; }
        else if (c === ')') { depth--; if (!depth) break; out += c; }
        else out += c;
      }
      return out;
    }
    hexString() {
      const s = this.s; this.p++; let h = '';
      while (this.p < this.end && s[this.p] !== '>') { const c = s[this.p++]; if (/[0-9a-fA-F]/.test(c)) h += c; }
      this.p++;
      if (h.length % 2) h += '0';
      let out = '';
      for (let i = 0; i < h.length; i += 2) out += String.fromCharCode(parseInt(h.substr(i, 2), 16));
      return out;
    }
  }

  function parseObj(lx, tok) {
    if (tok === undefined) tok = lx.next();
    if (tok === null) return null;
    switch (tok.t) {
      case 'num': {
        const save = lx.p, t2 = lx.next();
        if (t2 && t2.t === 'num') {
          const save2 = lx.p, t3 = lx.next();
          if (t3 && t3.t === 'kw' && t3.v === 'R') return { ref: tok.v };
          lx.p = save; return tok.v;
        }
        lx.p = save; return tok.v;
      }
      case 'str': return { str: tok.v };
      case 'name': return { name: tok.v };
      case '[': { const a = []; for (;;) { const t = lx.next(); if (!t || t.t === ']') break; a.push(parseObj(lx, t)); } return a; }
      case '<<': {
        const d = {};
        for (;;) {
          const t = lx.next();
          if (!t || t.t === '>>') break;
          if (t.t !== 'name') continue;
          d[t.v] = parseObj(lx);
        }
        return d;
      }
      case 'kw':
        if (tok.v === 'true') return true;
        if (tok.v === 'false') return false;
        if (tok.v === 'null') return null;
        return { kw: tok.v };
      default: return null;
    }
  }

  /* ---------------- filtros ---------------- */
  async function inflate(u8) {
    const tries = [['deflate', 0], ['deflate-raw', 0], ['deflate', 1], ['deflate-raw', 2]];
    for (const [fmt, off] of tries) {
      try {
        const src = off ? u8.subarray(off) : u8;
        const st = new Blob([src]).stream().pipeThrough(new DecompressionStream(fmt));
        const ab = await new Response(st).arrayBuffer();
        const out = new Uint8Array(ab);
        if (out.length) return out;
      } catch (e) { /* tenta o próximo */ }
    }
    return null;
  }

  function applyPredictor(data, parms, resolve) {
    if (!parms) return data;
    const pred = num(resolve(parms.Predictor), 1);
    if (pred < 2) return data;
    const colors = num(resolve(parms.Colors), 1);
    const bpc = num(resolve(parms.BitsPerComponent), 8);
    const columns = num(resolve(parms.Columns), 1);
    const bpp = Math.ceil(colors * bpc / 8);
    const rowLen = Math.ceil(colors * bpc * columns / 8);
    if (pred === 2) return data; // TIFF: raro em PDFs de texto
    const rows = Math.floor(data.length / (rowLen + 1));
    const out = new Uint8Array(rows * rowLen);
    let prev = new Uint8Array(rowLen);
    for (let r = 0; r < rows; r++) {
      const ft = data[r * (rowLen + 1)];
      const row = data.subarray(r * (rowLen + 1) + 1, (r + 1) * (rowLen + 1));
      const cur = new Uint8Array(rowLen);
      for (let i = 0; i < rowLen; i++) {
        const raw = row[i] || 0;
        const a = i >= bpp ? cur[i - bpp] : 0, b = prev[i], c = i >= bpp ? prev[i - bpp] : 0;
        let v;
        switch (ft) {
          case 0: v = raw; break;
          case 1: v = raw + a; break;
          case 2: v = raw + b; break;
          case 3: v = raw + ((a + b) >> 1); break;
          case 4: {
            const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
            v = raw + (pa <= pb && pa <= pc ? a : (pb <= pc ? b : c)); break;
          }
          default: v = raw;
        }
        cur[i] = v & 0xff;
      }
      out.set(cur, r * rowLen);
      prev = cur;
    }
    return out;
  }

  function ascii85(u8) {
    const s = bin(u8).replace(/\s/g, '').replace(/^<~/, '').replace(/~>$/, '');
    const out = [];
    let tuple = [], i = 0;
    while (i < s.length) {
      const c = s[i++];
      if (c === 'z' && tuple.length === 0) { out.push(0, 0, 0, 0); continue; }
      tuple.push(c.charCodeAt(0) - 33);
      if (tuple.length === 5) {
        let v = 0; for (const t of tuple) v = v * 85 + t;
        out.push((v >>> 24) & 255, (v >>> 16) & 255, (v >>> 8) & 255, v & 255);
        tuple = [];
      }
    }
    if (tuple.length > 1) {
      const n = tuple.length;
      for (let k = n; k < 5; k++) tuple.push(84);
      let v = 0; for (const t of tuple) v = v * 85 + t;
      const bytes = [(v >>> 24) & 255, (v >>> 16) & 255, (v >>> 8) & 255, v & 255];
      for (let k = 0; k < n - 1; k++) out.push(bytes[k]);
    }
    return new Uint8Array(out);
  }

  function asciiHex(u8) {
    const s = bin(u8).replace(/[^0-9a-fA-F>]/g, '').split('>')[0];
    const h = s.length % 2 ? s + '0' : s;
    const out = new Uint8Array(h.length / 2);
    for (let i = 0; i < out.length; i++) out[i] = parseInt(h.substr(i * 2, 2), 16);
    return out;
  }

  const num = (v, d) => (typeof v === 'number' ? v : d);

  /* ---------------- criptografia (handler padrão, R2–R4) ---------------- */
  function md5(bytes) {
    const S = [7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22,
      5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20,
      4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
      6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21];
    const K = new Int32Array(64);
    for (let i = 0; i < 64; i++) K[i] = (Math.abs(Math.sin(i + 1)) * 4294967296) | 0;
    const len = bytes.length;
    const withOne = len + 1;
    const padded = new Uint8Array((((withOne + 8) >> 6) + 1) << 6);
    padded.set(bytes);
    padded[len] = 0x80;
    const bitLen = len * 8;
    const dv = new DataView(padded.buffer);
    dv.setUint32(padded.length - 8, bitLen >>> 0, true);
    dv.setUint32(padded.length - 4, Math.floor(bitLen / 4294967296), true);
    let a0 = 0x67452301, b0 = 0xefcdab89, c0 = 0x98badcfe, d0 = 0x10325476;
    const M = new Int32Array(16);
    for (let off = 0; off < padded.length; off += 64) {
      for (let i = 0; i < 16; i++) M[i] = dv.getInt32(off + i * 4, true);
      let A = a0, B = b0, C = c0, D = d0;
      for (let i = 0; i < 64; i++) {
        let F, g;
        if (i < 16) { F = (B & C) | (~B & D); g = i; }
        else if (i < 32) { F = (D & B) | (~D & C); g = (5 * i + 1) & 15; }
        else if (i < 48) { F = B ^ C ^ D; g = (3 * i + 5) & 15; }
        else { F = C ^ (B | ~D); g = (7 * i) & 15; }
        F = (F + A + K[i] + M[g]) | 0;
        A = D; D = C; C = B;
        B = (B + ((F << S[i]) | (F >>> (32 - S[i])))) | 0;
      }
      a0 = (a0 + A) | 0; b0 = (b0 + B) | 0; c0 = (c0 + C) | 0; d0 = (d0 + D) | 0;
    }
    const out = new Uint8Array(16);
    new DataView(out.buffer).setInt32(0, a0, true);
    new DataView(out.buffer).setInt32(4, b0, true);
    new DataView(out.buffer).setInt32(8, c0, true);
    new DataView(out.buffer).setInt32(12, d0, true);
    return out;
  }

  function rc4(key, data) {
    const S = new Uint8Array(256);
    for (let i = 0; i < 256; i++) S[i] = i;
    let j = 0;
    for (let i = 0; i < 256; i++) {
      j = (j + S[i] + key[i % key.length]) & 255;
      const t = S[i]; S[i] = S[j]; S[j] = t;
    }
    const out = new Uint8Array(data.length);
    let i = 0; j = 0;
    for (let k = 0; k < data.length; k++) {
      i = (i + 1) & 255;
      j = (j + S[i]) & 255;
      const t = S[i]; S[i] = S[j]; S[j] = t;
      out[k] = data[k] ^ S[(S[i] + S[j]) & 255];
    }
    return out;
  }

  const PAD = new Uint8Array([0x28, 0xBF, 0x4E, 0x5E, 0x4E, 0x75, 0x8A, 0x41, 0x64, 0x00, 0x4E, 0x56,
    0xFF, 0xFA, 0x01, 0x08, 0x2E, 0x2E, 0x00, 0xB6, 0xD0, 0x68, 0x3E, 0x80,
    0x2F, 0x0C, 0xA9, 0xFE, 0x64, 0x53, 0x69, 0x7A]);

  function cat() {
    let n = 0;
    for (const a of arguments) n += a.length;
    const out = new Uint8Array(n);
    let o = 0;
    for (const a of arguments) { out.set(a, o); o += a.length; }
    return out;
  }
  function strBytes(s) {
    const o = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) o[i] = s.charCodeAt(i) & 0xff;
    return o;
  }
  function hexBytes(h) {
    h = (h || '').replace(/[^0-9a-fA-F]/g, '');
    const o = new Uint8Array(h.length >> 1);
    for (let i = 0; i < o.length; i++) o[i] = parseInt(h.substr(i * 2, 2), 16);
    return o;
  }

  async function aesCbcDecrypt(key, data) {
    if (data.length <= 16) return new Uint8Array(0);
    const iv = data.subarray(0, 16);
    const body = data.subarray(16);
    if (body.length % 16) return null;
    try {
      const k = await crypto.subtle.importKey('raw', key, 'AES-CBC', false, ['decrypt']);
      const ab = await crypto.subtle.decrypt({ name: 'AES-CBC', iv }, k, body);
      return new Uint8Array(ab);
    } catch (e) {
      // padding inválido: tenta sem checagem, decifrando bloco a bloco
      try {
        const k = await crypto.subtle.importKey('raw', key, 'AES-CBC', false, ['encrypt']);
        const zero = new Uint8Array(16);
        const enc = await crypto.subtle.encrypt({ name: 'AES-CBC', iv: zero }, k, new Uint8Array(16));
        void enc;
      } catch (e2) { }
      return null;
    }
  }

  function sameBytes(a, b) {
    const n = Math.min(a.length, b.length);
    if (!n) return false;
    for (let i = 0; i < n; i++) if (a[i] !== b[i]) return false;
    return true;
  }

  function padPassword(pw) {
    const b = strBytes(pw || '');
    const out = new Uint8Array(32);
    const n = Math.min(32, b.length);
    out.set(b.subarray(0, n));
    out.set(PAD.subarray(0, 32 - n), n);
    return out;
  }


  /* ---------------- documento ---------------- */
  class Doc {
    constructor(bytes) {
      this.bytes = bytes;
      this.raw = bin(bytes);
      this.objs = new Map();     // num -> {start,end} no texto bruto
      this.cache = new Map();    // num -> objeto já parseado
      this.streams = new Map();  // num -> Uint8Array decodificado
      this.notes = [];
    }

    scan() {
      const re = /(?:^|[\s>\]])(\d+)\s+(\d+)\s+obj\b/g;
      let m;
      while ((m = re.exec(this.raw))) {
        const n = parseInt(m[1], 10);
        const start = m.index + m[0].length;
        const end = this.raw.indexOf('endobj', start);
        // versões posteriores do mesmo objeto sobrescrevem as anteriores
        this.objs.set(n, { start, end: end < 0 ? Math.min(start + 200000, this.raw.length) : end, gen: parseInt(m[2], 10) || 0 });
        re.lastIndex = start;
      }
    }

    /* --- criptografia --- */
    encryptInfo() {
      const ms = [...this.raw.matchAll(/\/Encrypt\s+(\d+)\s+(\d+)\s*R/g)];
      if (!ms.length) return null;
      const objn = parseInt(ms[ms.length - 1][1], 10);
      const o = this.get(objn);
      if (!o || !o.val) return null;
      const idm = /\/ID\s*\[\s*<([0-9A-Fa-f\s]*)>/.exec(this.raw);
      return { dict: o.val, objn, id0: idm ? hexBytes(idm[1]) : new Uint8Array(0) };
    }

    async setupCrypto(password) {
      this.crypt = null;
      const info = this.encryptInfo();
      this.encrypted = !!info;
      if (!info) return { encrypted: false, ok: true };
      const d = info.dict;
      this.encryptObjNum = info.objn;
      if (this.nameOf(d.Filter) !== 'Standard') return { encrypted: true, ok: false, reason: 'handler' };
      const V = this.numOf(d.V, 0), R = this.numOf(d.R, 0);
      if (R > 4) return { encrypted: true, ok: false, reason: 'aes256' };
      const O = strBytes(this.strOf(d.O) || '');
      const U = strBytes(this.strOf(d.U) || '');
      const P = this.numOf(d.P, -1);
      let length = this.numOf(d.Length, 40);
      let method = 'rc4';
      if (V >= 4) {
        const cf = this.dictOf(d.CF);
        const stmf = this.nameOf(d.StmF) || 'Identity';
        const c = cf ? this.dictOf(cf[stmf]) : null;
        const cfm = c ? this.nameOf(c.CFM) : null;
        if (cfm === 'AESV2') { method = 'aes'; length = 128; }
        else if (cfm === 'V2') { let L = this.numOf(c.Length, 16); length = L <= 40 ? L * 8 : L; }
        else if (cfm === 'None' || stmf === 'Identity') method = 'none';
      }
      const n = Math.max(5, Math.min(16, Math.floor(length / 8)));
      const mkKey = (pw) => {
        const pb = new Uint8Array(4);
        new DataView(pb.buffer).setInt32(0, P | 0, true);
        let input = cat(padPassword(pw), O.subarray(0, 32), pb, info.id0);
        if (R >= 4 && d.EncryptMetadata === false) input = cat(input, new Uint8Array([255, 255, 255, 255]));
        let key = md5(input).slice(0, n);
        if (R >= 3) for (let i = 0; i < 50; i++) key = md5(key.subarray(0, n)).slice(0, n);
        return key;
      };
      const tryKey = (key) => {
        if (R === 2) return sameBytes(rc4(key, PAD), U.subarray(0, 32));
        let val = rc4(key, md5(cat(PAD, info.id0)));
        for (let i = 1; i <= 19; i++) {
          const k2 = new Uint8Array(key.length);
          for (let j = 0; j < key.length; j++) k2[j] = key[j] ^ i;
          val = rc4(k2, val);
        }
        return sameBytes(val, U.subarray(0, 16));
      };
      let key = mkKey(password);
      if (!tryKey(key)) {
        // talvez a senha informada seja a de proprietário: dela se extrai a de usuário
        let ok = false;
        if (password) {
          // Algoritmo 3: aqui as 50 iterações usam o digest inteiro (16 bytes), só depois trunca
          let h = md5(padPassword(password));
          if (R >= 3) for (let i = 0; i < 50; i++) h = md5(h);
          const ok2 = h.slice(0, n);
          let user = O.slice(0, 32);
          if (R === 2) user = rc4(ok2, user);
          else for (let i = 19; i >= 0; i--) {
            const k2 = new Uint8Array(ok2.length);
            for (let j = 0; j < ok2.length; j++) k2[j] = ok2[j] ^ i;
            user = rc4(k2, user);
          }
          let userPw = '';
          for (let i = 0; i < 32; i++) {
            if (sameBytes(user.subarray(i), PAD.subarray(0, 32 - i))) break;
            userPw += String.fromCharCode(user[i]);
          }
          const k3 = mkKey(userPw);
          if (tryKey(k3)) { key = k3; ok = true; }
        }
        if (!ok) return { encrypted: true, ok: false, reason: 'senha' };
      }
      this.crypt = { key, method, R, n };
      return { encrypted: true, ok: true };
    }

    objKey(objn, gen) {
      const c = this.crypt;
      const ext = new Uint8Array(c.method === 'aes' ? 9 : 5);
      ext[0] = objn & 255; ext[1] = (objn >> 8) & 255; ext[2] = (objn >> 16) & 255;
      ext[3] = gen & 255; ext[4] = (gen >> 8) & 255;
      if (c.method === 'aes') { ext[5] = 0x73; ext[6] = 0x41; ext[7] = 0x6C; ext[8] = 0x54; }
      return md5(cat(c.key, ext)).slice(0, Math.min(c.key.length + 5, 16));
    }

    async decryptBytes(data, objn, gen) {
      const c = this.crypt;
      if (!c || c.method === 'none') return data;
      const k = this.objKey(objn, gen || 0);
      if (c.method === 'aes') { const r = await aesCbcDecrypt(k, data); return r || data; }
      return rc4(k, data);
    }

    parseAt(rec) {
      const lx = new Lexer(this.raw, rec.start, rec.end);
      const val = parseObj(lx);
      let streamRange = null;
      const si = this.raw.indexOf('stream', lx.p);
      if (si >= 0 && si < rec.end && /^[\s]*$/.test(this.raw.slice(lx.p, si))) {
        let ds = si + 6;
        if (this.raw[ds] === '\r') ds++;
        if (this.raw[ds] === '\n') ds++;
        streamRange = { start: ds, dictEnd: si };
      }
      return { val, streamRange, rec };
    }

    get(n) {
      if (this.cache.has(n)) return this.cache.get(n);
      const rec = this.objs.get(n);
      if (!rec) { this.cache.set(n, null); return null; }
      let parsed = null;
      try { parsed = this.parseAt(rec); } catch (e) { parsed = null; }
      this.cache.set(n, parsed);
      return parsed;
    }

    resolve(v) {
      let guard = 0;
      while (v && typeof v === 'object' && 'ref' in v && guard++ < 32) {
        const o = this.get(v.ref);
        v = o ? o.val : null;
      }
      return v;
    }

    dictOf(v) { const r = this.resolve(v); return r && typeof r === 'object' && !Array.isArray(r) ? r : null; }
    nameOf(v) { const r = this.resolve(v); return r && r.name ? r.name : null; }
    strOf(v) { const r = this.resolve(v); return r && typeof r.str === 'string' ? r.str : null; }
    numOf(v, d) { const r = this.resolve(v); return typeof r === 'number' ? r : d; }
    arrOf(v) { const r = this.resolve(v); return Array.isArray(r) ? r : (r == null ? [] : [r]); }
    /* como arrOf, mas preserva referências a streams (ex.: /Contents 22 0 R) */
    refsOf(v) {
      if (Array.isArray(v)) return v;
      if (v && typeof v === 'object' && 'ref' in v) {
        const r = this.resolve(v);
        return Array.isArray(r) ? r : [v];
      }
      return v == null ? [] : [v];
    }

    async streamOf(n) {
      if (this.streams.has(n)) return this.streams.get(n);
      const o = this.get(n);
      let out = null;
      if (o && o.streamRange) {
        const d = o.val || {};
        let len = this.numOf(d.Length, -1);
        let end;
        if (len >= 0 && o.streamRange.start + len <= this.raw.length) {
          end = o.streamRange.start + len;
          const tail = this.raw.slice(end, end + 20);
          if (!/^\s*endstream/.test(tail)) len = -1;
        }
        if (len < 0) {
          const es = this.raw.indexOf('endstream', o.streamRange.start);
          end = es < 0 ? o.rec.end : es;
          while (end > o.streamRange.start && (this.raw[end - 1] === '\n' || this.raw[end - 1] === '\r')) end--;
        } else {
          end = o.streamRange.start + len;
        }
        let data = this.bytes.subarray(o.streamRange.start, end);
        if (this.crypt && n !== this.encryptObjNum && this.nameOf(d.Type) !== 'XRef') {
          try { data = await this.decryptBytes(data, n, (o.rec && o.rec.gen) || 0); } catch (e) { }
        }
        const filters = this.arrOf(d.Filter).map(f => this.nameOf(f)).filter(Boolean);
        const parmsArr = this.arrOf(d.DecodeParms);
        for (let i = 0; i < filters.length; i++) {
          const f = filters[i];
          const parms = this.dictOf(parmsArr[i] !== undefined ? parmsArr[i] : parmsArr[0]);
          if (f === 'FlateDecode' || f === 'Fl') {
            data = await inflate(data);
            if (!data) break;
            data = applyPredictor(data, parms, v => this.resolve(v));
          } else if (f === 'ASCII85Decode' || f === 'A85') {
            data = ascii85(data);
          } else if (f === 'ASCIIHexDecode' || f === 'AHx') {
            data = asciiHex(data);
          } else {
            data = null; break; // DCT/JPX/CCITT/LZW: imagem ou não suportado
          }
        }
        out = data;
      }
      this.streams.set(n, out);
      return out;
    }

    /* objetos comprimidos em ObjStm */
    async loadObjStms() {
      const candidates = [];
      for (const [n] of this.objs) {
        const o = this.get(n);
        if (o && o.val && this.nameOf(o.val.Type) === 'ObjStm') candidates.push(n);
      }
      for (const n of candidates) {
        try {
          const data = await this.streamOf(n);
          if (!data) continue;
          const d = this.get(n).val;
          const count = this.numOf(d.N, 0), first = this.numOf(d.First, 0);
          const s = bin(data);
          const head = new Lexer(s, 0, first);
          const pairs = [];
          for (let i = 0; i < count; i++) {
            const a = head.next(), b = head.next();
            if (!a || !b || a.t !== 'num' || b.t !== 'num') break;
            pairs.push([a.v, b.v]);
          }
          for (let i = 0; i < pairs.length; i++) {
            const [objn, off] = pairs[i];
            if (this.objs.has(objn) && this.cache.get(objn)) continue;
            const start = first + off;
            const end = i + 1 < pairs.length ? first + pairs[i + 1][1] : s.length;
            const lx = new Lexer(s, start, end);
            let val = null;
            try { val = parseObj(lx); } catch (e) { }
            this.cache.set(objn, { val, streamRange: null, rec: null, inObjStm: true });
            if (!this.objs.has(objn)) this.objs.set(objn, { start: 0, end: 0, virtual: true });
          }
        } catch (e) { this.notes.push('ObjStm ' + n + ': ' + e.message); }
      }
    }

    findByType(type) {
      const out = [];
      for (const [n] of this.objs) {
        const o = this.get(n);
        if (o && o.val && !Array.isArray(o.val) && typeof o.val === 'object' && this.nameOf(o.val.Type) === type) out.push(n);
      }
      return out;
    }

    pages() {
      const cats = this.findByType('Catalog');
      const seen = new Set();
      const out = [];
      const walk = (node, depth, inherited) => {
        if (!node || depth > 64) return;
        const d = this.dictOf(node);
        if (!d) return;
        const inh = {
          Resources: d.Resources !== undefined ? d.Resources : inherited.Resources,
          MediaBox: d.MediaBox !== undefined ? d.MediaBox : inherited.MediaBox,
        };
        const t = this.nameOf(d.Type);
        if (t === 'Page' || (!d.Kids && d.Contents)) {
          out.push({ dict: d, inh });
          return;
        }
        for (const k of this.arrOf(d.Kids)) {
          const key = k && k.ref !== undefined ? 'r' + k.ref : null;
          if (key) { if (seen.has(key)) continue; seen.add(key); }
          walk(k, depth + 1, inh);
        }
      };
      for (const c of cats) {
        const cat = this.get(c).val;
        if (cat && cat.Pages) walk(cat.Pages, 0, {});
      }
      if (!out.length) {
        for (const n of this.findByType('Page')) out.push({ dict: this.get(n).val, inh: {} });
      }
      return out;
    }
  }

  /* ---------------- fontes ---------------- */
  const WIN_HI = {
    128: '€', 130: '‚', 131: 'ƒ', 132: '„', 133: '…', 134: '†', 135: '‡',
    136: 'ˆ', 137: '‰', 138: 'Š', 139: '‹', 140: 'Œ', 142: 'Ž', 145: '‘',
    146: '’', 147: '“', 148: '”', 149: '•', 150: '–', 151: '—', 152: '˜',
    153: '™', 154: 'š', 155: '›', 156: 'œ', 158: 'ž', 159: 'Ÿ'
  };
  const GLYPHS = {
    space: ' ', exclam: '!', quotedbl: '"', numbersign: '#', dollar: '$', percent: '%', ampersand: '&',
    quotesingle: "'", parenleft: '(', parenright: ')', asterisk: '*', plus: '+', comma: ',', hyphen: '-',
    period: '.', slash: '/', zero: '0', one: '1', two: '2', three: '3', four: '4', five: '5', six: '6',
    seven: '7', eight: '8', nine: '9', colon: ':', semicolon: ';', less: '<', equal: '=', greater: '>',
    question: '?', at: '@', bracketleft: '[', backslash: '\\', bracketright: ']', asciicircum: '^',
    underscore: '_', grave: '`', braceleft: '{', bar: '|', braceright: '}', asciitilde: '~',
    aacute: 'á', agrave: 'à', acircumflex: 'â', atilde: 'ã', adieresis: 'ä', aring: 'å', ae: 'æ',
    ccedilla: 'ç', eacute: 'é', egrave: 'è', ecircumflex: 'ê', edieresis: 'ë', iacute: 'í', igrave: 'ì',
    icircumflex: 'î', idieresis: 'ï', ntilde: 'ñ', oacute: 'ó', ograve: 'ò', ocircumflex: 'ô', otilde: 'õ',
    odieresis: 'ö', uacute: 'ú', ugrave: 'ù', ucircumflex: 'û', udieresis: 'ü', ydieresis: 'ÿ',
    Aacute: 'Á', Agrave: 'À', Acircumflex: 'Â', Atilde: 'Ã', Adieresis: 'Ä', Ccedilla: 'Ç', Eacute: 'É',
    Egrave: 'È', Ecircumflex: 'Ê', Edieresis: 'Ë', Iacute: 'Í', Igrave: 'Ì', Icircumflex: 'Î',
    Idieresis: 'Ï', Ntilde: 'Ñ', Oacute: 'Ó', Ograve: 'Ò', Ocircumflex: 'Ô', Otilde: 'Õ', Odieresis: 'Ö',
    Uacute: 'Ú', Ugrave: 'Ù', Ucircumflex: 'Û', Udieresis: 'Ü', ordfeminine: 'ª', ordmasculine: 'º',
    degree: '°', bullet: '•', endash: '–', emdash: '—', quoteleft: '‘',
    quoteright: '’', quotedblleft: '“', quotedblright: '”', ellipsis: '…',
    Euro: '€', sterling: '£', cent: '¢', section: '§', paragraph: '¶', copyright: '©',
    registered: '®', plusminus: '±', mu: 'µ', onequarter: '¼', onehalf: '½', threequarters: '¾',
    questiondown: '¿', exclamdown: '¡', guillemotleft: '«', guillemotright: '»'
  };
  function glyphToChar(name) {
    if (!name) return '';
    if (GLYPHS[name]) return GLYPHS[name];
    let m = /^uni([0-9A-Fa-f]{4})$/.exec(name);
    if (m) return String.fromCharCode(parseInt(m[1], 16));
    m = /^u([0-9A-Fa-f]{4,6})$/.exec(name);
    if (m) return String.fromCodePoint(parseInt(m[1], 16));
    m = /^(?:g|cid|c|G)(\d+)$/.exec(name);
    if (m) return '';
    return name.length === 1 ? name : '';
  }

  function parseCMap(text) {
    const map = new Map();
    let re = /beginbfchar([\s\S]*?)endbfchar/g, m;
    const hexToStr = h => {
      let s = '';
      for (let i = 0; i + 3 < h.length + 1 && i < h.length; i += 4) {
        const cu = parseInt(h.substr(i, 4), 16);
        if (!isNaN(cu)) s += String.fromCharCode(cu);
      }
      return s.replace(/ /g, '');
    };
    while ((m = re.exec(text))) {
      const body = m[1];
      const pr = /<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>/g;
      let p;
      while ((p = pr.exec(body))) map.set(parseInt(p[1], 16), hexToStr(p[2]));
    }
    re = /beginbfrange([\s\S]*?)endbfrange/g;
    while ((m = re.exec(text))) {
      const body = m[1];
      const pr = /<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(?:<([0-9A-Fa-f]*)>|\[([\s\S]*?)\])/g;
      let p;
      while ((p = pr.exec(body))) {
        const lo = parseInt(p[1], 16), hi = parseInt(p[2], 16);
        if (p[3] !== undefined) {
          const base = p[3];
          const tail = parseInt(base.slice(-4), 16);
          const head = base.slice(0, -4);
          for (let c = lo; c <= hi && c - lo < 65536; c++) {
            const h = head + (tail + (c - lo)).toString(16).padStart(4, '0');
            map.set(c, hexToStr(h));
          }
        } else if (p[4] !== undefined) {
          const items = p[4].match(/<([0-9A-Fa-f]*)>/g) || [];
          items.forEach((it, i) => map.set(lo + i, hexToStr(it.slice(1, -1))));
        }
      }
    }
    return map;
  }

  async function buildFont(doc, fdictRef) {
    const f = doc.dictOf(fdictRef);
    const font = { two: false, toUni: null, diff: null, widths: null, dw: 500, firstChar: 0 };
    if (!f) return font;
    const sub = doc.nameOf(f.Subtype);
    if (sub === 'Type0') font.two = true;
    if (f.ToUnicode && f.ToUnicode.ref !== undefined) {
      const data = await doc.streamOf(f.ToUnicode.ref);
      if (data) { try { font.toUni = parseCMap(bin(data)); } catch (e) { } }
    }
    const enc = doc.resolve(f.Encoding);
    if (enc && enc.name && /Identity/.test(enc.name)) font.two = true;
    if (enc && typeof enc === 'object' && enc.Differences) {
      const arr = doc.arrOf(enc.Differences);
      const d = {};
      let code = 0;
      for (const it of arr) {
        const v = doc.resolve(it);
        if (typeof v === 'number') code = v;
        else if (v && v.name) d[code++] = v.name;
      }
      font.diff = d;
    }
    // larguras (para estimar espaços)
    if (!font.two && f.Widths) {
      font.firstChar = doc.numOf(f.FirstChar, 0);
      font.widths = doc.arrOf(f.Widths).map(w => doc.numOf(w, 0));
    } else if (font.two) {
      const desc = doc.arrOf(f.DescendantFonts)[0];
      const dd = doc.dictOf(desc);
      if (dd) {
        font.dw = doc.numOf(dd.DW, 1000);
        const W = doc.arrOf(dd.W);
        const wmap = new Map();
        for (let i = 0; i < W.length;) {
          const a = doc.resolve(W[i]);
          const b = doc.resolve(W[i + 1]);
          if (Array.isArray(b)) {
            b.forEach((w, k) => wmap.set(a + k, doc.numOf(doc.resolve(w), 0)));
            i += 2;
          } else {
            const w = doc.numOf(doc.resolve(W[i + 2]), 0);
            for (let c = a; c <= b && c - a < 65536; c++) wmap.set(c, w);
            i += 3;
          }
        }
        font.wmap = wmap;
      }
    }
    return font;
  }

  function decodeString(font, s) {
    const out = [];
    if (font.two) {
      for (let i = 0; i + 1 < s.length; i += 2) {
        const code = (s.charCodeAt(i) << 8) | s.charCodeAt(i + 1);
        let ch = font.toUni ? font.toUni.get(code) : undefined;
        if (ch === undefined) ch = code >= 32 && code < 0xd800 ? String.fromCharCode(code) : '';
        out.push({ code, ch });
      }
    } else {
      for (let i = 0; i < s.length; i++) {
        const code = s.charCodeAt(i) & 0xff;
        let ch;
        if (font.toUni && font.toUni.has(code)) ch = font.toUni.get(code);
        else if (font.diff && font.diff[code]) ch = glyphToChar(font.diff[code]);
        else if (code >= 128 && code < 160) ch = WIN_HI[code] || '';
        else ch = String.fromCharCode(code);
        out.push({ code, ch });
      }
    }
    return out;
  }

  function glyphWidth(font, code) {
    if (font.two) {
      if (font.wmap && font.wmap.has(code)) return font.wmap.get(code);
      return font.dw;
    }
    if (font.widths) {
      const i = code - font.firstChar;
      if (i >= 0 && i < font.widths.length && font.widths[i]) return font.widths[i];
    }
    return 500;
  }

  const mul = (m, n) => [
    m[0] * n[0] + m[1] * n[2], m[0] * n[1] + m[1] * n[3],
    m[2] * n[0] + m[3] * n[2], m[2] * n[1] + m[3] * n[3],
    m[4] * n[0] + m[5] * n[2] + n[4], m[4] * n[1] + m[5] * n[3] + n[5]
  ];

  /* ---------------- extração de uma página ---------------- */
  async function pageItems(doc, page) {
    const res = doc.dictOf(page.dict.Resources) || doc.dictOf(page.inh.Resources) || {};
    const fontsDict = doc.dictOf(res.Font) || {};
    const fonts = {};
    for (const k of Object.keys(fontsDict)) {
      try { fonts[k] = await buildFont(doc, fontsDict[k]); } catch (e) { fonts[k] = { two: false }; }
    }
    const xobjs = doc.dictOf(res.XObject) || {};

    let content = '';
    const parts = doc.refsOf(page.dict.Contents);
    for (const c of parts) {
      if (c && c.ref !== undefined) {
        const data = await doc.streamOf(c.ref);
        if (data) content += bin(data) + '\n';
      }
    }
    const items = [];
    await runContent(doc, content, fonts, xobjs, items, [1, 0, 0, 1, 0, 0], 0);
    return items;
  }

  async function runContent(doc, content, fonts, xobjs, items, baseCTM, depth) {
    if (depth > 6) return;
    const lx = new Lexer(content);
    let ctm = baseCTM.slice();
    const stack = [];
    let tm = null, tlm = null;
    let font = { two: false }, fs = 12, tc = 0, tw = 0, tz = 100, tl = 0, ts = 0;
    let operands = [];
    const pending = [];

    const show = (raw) => {
      if (!tm) return;
      const glyphs = decodeString(font, raw);
      const startTm = tm.slice();
      let text = '';
      let adv = 0;
      for (const g of glyphs) {
        text += g.ch;
        const w = glyphWidth(font, g.code) / 1000;
        adv += (w * fs + tc + (!font.two && g.code === 32 ? tw : 0)) * (tz / 100);
      }
      const m = mul(mul([fs * (tz / 100), 0, 0, fs, 0, ts], startTm), ctm);
      const x = m[4], y = m[5];
      const scale = Math.hypot(m[0], m[1]) || fs;
      if (text.trim() || text === ' ') items.push({ x, y, w: adv * Math.hypot(startTm[0], startTm[1]) || adv, s: text, fs: scale });
      tm = mul([1, 0, 0, 1, adv, 0], tm);
    };
    const showTJ = (arr) => {
      if (!tm) return;
      for (const el of arr) {
        if (typeof el === 'number') {
          const shift = -el / 1000 * fs * (tz / 100);
          if (el <= -120) { /* espaço implícito */ items.push({ x: mul(tm, ctm)[4], y: mul(tm, ctm)[5], w: 0, s: ' ', fs, gap: true }); }
          tm = mul([1, 0, 0, 1, shift, 0], tm);
        } else if (el && typeof el.str === 'string') show(el.str);
      }
    };

    for (;;) {
      const t = lx.next();
      if (!t) break;
      if (t.t === 'kw') {
        const op = t.v;
        const n = operands.map(o => (o && typeof o === 'object' && 'num' in o) ? o.num : o);
        try {
          switch (op) {
            case 'q': stack.push({ ctm: ctm.slice() }); break;
            case 'Q': { const s = stack.pop(); if (s) ctm = s.ctm; break; }
            case 'cm': if (n.length >= 6) ctm = mul(n.slice(-6), ctm); break;
            case 'BT': tm = [1, 0, 0, 1, 0, 0]; tlm = tm.slice(); break;
            case 'ET': tm = null; tlm = null; break;
            case 'Tf': {
              const nm = n[n.length - 2];
              fs = typeof n[n.length - 1] === 'number' ? n[n.length - 1] : 12;
              const key = nm && nm.name;
              font = (key && fonts[key]) || { two: false };
              break;
            }
            case 'Td': if (tlm) { tlm = mul([1, 0, 0, 1, n[0] || 0, n[1] || 0], tlm); tm = tlm.slice(); } break;
            case 'TD': if (tlm) { tl = -(n[1] || 0); tlm = mul([1, 0, 0, 1, n[0] || 0, n[1] || 0], tlm); tm = tlm.slice(); } break;
            case 'Tm': if (n.length >= 6) { tlm = n.slice(-6); tm = tlm.slice(); } break;
            case 'T*': if (tlm) { tlm = mul([1, 0, 0, 1, 0, -tl], tlm); tm = tlm.slice(); } break;
            case 'TL': tl = n[0] || 0; break;
            case 'Tc': tc = n[0] || 0; break;
            case 'Tw': tw = n[0] || 0; break;
            case 'Tz': tz = n[0] || 100; break;
            case 'Ts': ts = n[0] || 0; break;
            case 'Tj': { const s = n[n.length - 1]; if (s && typeof s.str === 'string') show(s.str); break; }
            case "'": if (tlm) { tlm = mul([1, 0, 0, 1, 0, -tl], tlm); tm = tlm.slice(); const s = n[n.length - 1]; if (s && s.str !== undefined) show(s.str); } break;
            case '"': if (tlm) { tw = n[0] || 0; tc = n[1] || 0; tlm = mul([1, 0, 0, 1, 0, -tl], tlm); tm = tlm.slice(); const s = n[n.length - 1]; if (s && s.str !== undefined) show(s.str); } break;
            case 'TJ': { const a = n[n.length - 1]; if (Array.isArray(a)) showTJ(a); break; }
            case 'Do': {
              const nm = n[n.length - 1];
              if (nm && nm.name && xobjs[nm.name] && xobjs[nm.name].ref !== undefined) {
                pending.push({ ref: xobjs[nm.name].ref, ctm: ctm.slice() });
              }
              break;
            }
          }
        } catch (e) { /* segue */ }
        operands = [];
      } else {
        if (operands.length > 64) operands = [];
        operands.push(parseObj(lx, t));
      }
    }

    for (const p of pending) {
      const o = doc.get(p.ref);
      if (!o || !o.val) continue;
      if (doc.nameOf(o.val.Subtype) !== 'Form') continue;
      const data = await doc.streamOf(p.ref);
      if (!data) continue;
      const res2 = doc.dictOf(o.val.Resources) || {};
      const fd = doc.dictOf(res2.Font) || {};
      const f2 = {};
      for (const k of Object.keys(fd)) { try { f2[k] = await buildFont(doc, fd[k]); } catch (e) { } }
      const x2 = doc.dictOf(res2.XObject) || {};
      let m = p.ctm;
      const mtx = doc.arrOf(o.val.Matrix).map(v => doc.numOf(v, 0));
      if (mtx.length === 6) m = mul(mtx, m);
      await runContent(doc, bin(data), Object.keys(f2).length ? f2 : fonts, x2, items, m, depth + 1);
    }
  }

  function itemsToLines(items) {
    const real = items.filter(i => i.s !== undefined);
    if (!real.length) return [];
    real.sort((a, b) => (b.y - a.y) || (a.x - b.x));
    const lines = [];
    let cur = null;
    for (const it of real) {
      const tol = Math.max(1.5, (it.fs || 10) * 0.5);
      if (!cur || Math.abs(cur.y - it.y) > tol) {
        cur = { y: it.y, parts: [] };
        lines.push(cur);
      }
      cur.parts.push(it);
    }
    return lines.map(l => {
      l.parts.sort((a, b) => a.x - b.x);
      let s = '';
      let prev = null;
      for (const p of l.parts) {
        if (prev) {
          const gap = p.x - (prev.x + (prev.w || 0));
          const fsz = Math.max(prev.fs || 8, 4);
          if (gap > fsz * 0.18) s += ' ';
          else if (gap < -fsz * 0.6) s += ' ';
        }
        s += p.s;
        prev = p;
      }
      return s.replace(/[ \t]+/g, ' ').trim();
    }).filter(s => s.length);
  }

  /* ---------------- campos de formulário ---------------- */
  function decodePdfText(s) {
    if (s == null) return '';
    if (s.charCodeAt(0) === 0xFE && s.charCodeAt(1) === 0xFF) {
      let o = '';
      for (let i = 2; i + 1 < s.length; i += 2) o += String.fromCharCode((s.charCodeAt(i) << 8) | s.charCodeAt(i + 1));
      return o;
    }
    let o = '';
    for (let i = 0; i < s.length; i++) {
      const c = s.charCodeAt(i);
      o += (c >= 128 && c < 160) ? (WIN_HI[c] || '') : s[i];
    }
    return o;
  }

  async function acroFields(doc) {
    const out = [];
    const raws = [];
    const cats = doc.findByType('Catalog');
    const roots = [];
    for (const c of cats) {
      const cat = doc.get(c).val;
      const af = doc.dictOf(cat && cat.AcroForm);
      if (af) for (const f of doc.arrOf(af.Fields)) roots.push(f);
    }
    const seen = new Set();
    const walk = (ref, prefix, depth, owner) => {
      if (depth > 24) return;
      if (ref && ref.ref !== undefined) {
        if (seen.has(ref.ref)) return;
        seen.add(ref.ref);
        owner = ref.ref;
      }
      const d = doc.dictOf(ref);
      if (!d) return;
      const t = doc.strOf(d.T);
      const name = t ? (prefix ? prefix + '.' + decodePdfText(t) : decodePdfText(t)) : prefix;
      const kids = doc.arrOf(d.Kids);
      if (kids.length) { for (const k of kids) walk(k, name, depth + 1, owner); }
      const v = d.V !== undefined ? doc.resolve(d.V) : null;
      if (v && typeof v.str === 'string') raws.push({ name: name || '?', raw: v.str, owner });
      else if (v && v.name) out.push({ name: name || '?', value: v.name });
      else if (typeof v === 'number') out.push({ name: name || '?', value: String(v) });
    };
    for (const r of roots) walk(r, '', 0, null);
    for (const r of raws) {
      let s = r.raw;
      if (doc.crypt && r.owner != null) {
        const entry = doc.cache.get(r.owner);
        if (!entry || !entry.inObjStm) {
          try {
            const rec = doc.objs.get(r.owner);
            const dec = await doc.decryptBytes(strBytes(s), r.owner, (rec && rec.gen) || 0);
            if (dec) s = bin(dec);
          } catch (e) { }
        }
      }
      const val = decodePdfText(s).trim();
      if (val && val !== 'Off') out.push({ name: r.name, value: val });
    }
    for (let i = out.length - 1; i >= 0; i--) {
      const v = String(out[i].value).trim();
      if (!v || v === 'Off') out.splice(i, 1);
    }
    if (!out.length) {
      // fallback: qualquer widget com /FT e /V
      for (const [n] of doc.objs) {
        const o = doc.get(n);
        const d = o && o.val;
        if (!d || typeof d !== 'object' || Array.isArray(d)) continue;
        if (d.FT === undefined || d.V === undefined) continue;
        const v = doc.resolve(d.V);
        const t = doc.strOf(d.T);
        let val = v && typeof v.str === 'string' ? decodePdfText(v.str) : (v && v.name ? v.name : null);
        if (val && val.trim() && val.trim() !== 'Off') out.push({ name: t ? decodePdfText(t) : 'campo' + n, value: val.trim() });
      }
    }
    return out;
  }

  /* ---------------- API ---------------- */
  async function extract(bytes, opts) {
    opts = opts || {};
    const doc = new Doc(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes));
    doc.scan();
    let cripto = { encrypted: false, ok: true };
    try { cripto = await doc.setupCrypto(opts.password || ''); } catch (e) { cripto = { encrypted: true, ok: false, reason: 'erro' }; }
    if (cripto.encrypted && !cripto.ok) {
      return {
        text: '', pages: [], pageCount: 0, fields: [], letters: 0, ok: false,
        protegido: true, motivo: cripto.reason, notes: doc.notes
      };
    }
    await doc.loadObjStms();
    const pages = doc.pages();
    const pageTexts = [];
    const maxPages = Math.min(pages.length, opts.maxPages || 25);
    for (let i = 0; i < maxPages; i++) {
      try {
        const items = await pageItems(doc, pages[i]);
        pageTexts.push(itemsToLines(items).join('\n'));
      } catch (e) {
        pageTexts.push('');
      }
    }
    let fields = [];
    try { fields = await acroFields(doc); } catch (e) { }
    const text = pageTexts.join('\n');
    const letters = (text.match(/[A-Za-zÀ-ÿ]/g) || []).length;
    return {
      text,
      pages: pageTexts,
      pageCount: pages.length,
      fields,
      letters,
      ok: letters > 120 || fields.length > 0,
      protegido: false,
      criptografado: !!cripto.encrypted,
      notes: doc.notes
    };
  }

  return { extract, Doc, Lexer, parseObj };
})();

if (typeof module !== 'undefined') module.exports = PDFX;
