// Screen: Pesar — registro manual de pesos por caja, agrupado por lote
// El trabajador pesa varias cajas del MISMO lote en tanda: captura lote+fechas una vez,
// luego sólo ingresa el peso y toca "+ Caja" para registrar y seguir con la siguiente.

const PesarScreen = ({ pedidoId, onBack }) => {
  const d = window.PESOS_DATA;
  const base = d.pedidos.find(x => x.id === pedidoId) || d.pedidos[0];
  const items = d.detail?.items || [];

  const catColor = {
    RES: '#dc2626', LOM: '#b91c1c', FAL: '#f97316',
    POL: '#eab308', MOL: '#be123c', CER: '#ec4899',
  };

  // ─── Active product ───
  const [activeIdx, setActiveIdx] = React.useState(2); // FAL — pendiente
  const activeItem = items[activeIdx];
  const activeColor = catColor[activeItem?.code] || '#6366f1';

  // ─── Date helpers (ISO YYYY-MM-DD strings internally) ───
  const todayISO = () => {
    const n = new Date();
    return `${n.getFullYear()}-${String(n.getMonth()+1).padStart(2,'0')}-${String(n.getDate()).padStart(2,'0')}`;
  };
  const addYears = (iso, yrs) => {
    const [y,m,da] = iso.split('-').map(Number);
    const nd = new Date(y + yrs, m - 1, da);
    return `${nd.getFullYear()}-${String(nd.getMonth()+1).padStart(2,'0')}-${String(nd.getDate()).padStart(2,'0')}`;
  };
  const formatISO = (iso) => {
    if (!iso) return '';
    const [y,m,d] = iso.split('-');
    return `${d}/${m}/${y}`;
  };

  // ─── Cajas registradas por producto ───
  const [cajas, setCajas] = React.useState(() => {
    const out = {};
    items.forEach((it, i) => {
      out[i] = [];
      if (it.pesado) {
        const per = it.peso / it.cajas;
        const baseLote = `L-${String(2641 + i).padStart(4,'0')}`;
        const elab = '2026-04-15';
        for (let j = 0; j < it.cajas; j++) {
          out[i].push({
            peso: +(per + (Math.random() - 0.5) * 0.6).toFixed(2),
            lote: baseLote,
            fechaElab: elab,
            fechaVenc: addYears(elab, 1),
          });
        }
      }
    });
    return out;
  });

  // ─── Lote activo (sticky) ───
  const [lote, setLote] = React.useState('L-2643');
  const [fechaElab, setFechaElab] = React.useState(todayISO());
  const [fechaVenc, setFechaVenc] = React.useState(addYears(todayISO(), 1));
  const [vencManual, setVencManual] = React.useState(false); // user overrode the +1yr default
  const [loteEditing, setLoteEditing] = React.useState(false);
  const [calendar, setCalendar] = React.useState(null); // 'elab' | 'venc' | null

  // When elab changes, auto-set venc to +1yr unless user manually overrode it
  const setElab = (iso) => {
    setFechaElab(iso);
    if (!vencManual) {
      setFechaVenc(addYears(iso, 1));
    }
  };
  const setVenc = (iso) => {
    setFechaVenc(iso);
    setVencManual(true);
  };

  // ─── Peso que se está capturando ahora ───
  const [peso, setPeso] = React.useState(''); // string in kg, e.g. "12.45"

  const productCajas = cajas[activeIdx] || [];
  const totalCajas = activeItem?.cajasPedidas ?? activeItem?.cajas ?? 0;
  const pesadas = productCajas.length;
  const pendientes = Math.max(0, totalCajas - pesadas);
  const currentBoxNum = pesadas + 1;
  const pesoNum = parseFloat(peso || '0');

  // Group cajas by lote for the summary list
  const lotesAgrupados = React.useMemo(() => {
    const groups = {};
    productCajas.forEach((c, idx) => {
      const key = c.lote;
      if (!groups[key]) groups[key] = { lote: c.lote, fechaElab: c.fechaElab, fechaVenc: c.fechaVenc, cajas: [] };
      groups[key].cajas.push({ ...c, idx });
    });
    return Object.values(groups);
  }, [productCajas]);

  // ─── Keypad handlers ───
  const press = (k) => {
    setPeso(prev => {
      if (k === 'back') return prev.slice(0, -1);
      if (k === 'clear') return '';
      if (k === '.') {
        if (prev.includes('.')) return prev;
        if (prev === '') return '0.';
        return prev + '.';
      }
      // digits
      if (prev === '0') return k;
      // limit: 6 chars, 2 decimals
      if (prev.includes('.')) {
        const [, dec] = prev.split('.');
        if (dec.length >= 2) return prev;
      }
      if (prev.length >= 6) return prev;
      return prev + k;
    });
  };

  const registrarCaja = () => {
    if (!peso || pesoNum <= 0) return;
    if (pendientes <= 0) return;
    setCajas(prev => ({
      ...prev,
      [activeIdx]: [...prev[activeIdx], { peso: pesoNum, lote, fechaElab, fechaVenc }],
    }));
    setPeso('');
  };

  const deshacerUltima = () => {
    if (productCajas.length === 0) return;
    setCajas(prev => ({
      ...prev,
      [activeIdx]: prev[activeIdx].slice(0, -1),
    }));
  };

  const eliminarCaja = (idx) => {
    setCajas(prev => ({
      ...prev,
      [activeIdx]: prev[activeIdx].filter((_, i) => i !== idx),
    }));
  };

  const updateCaja = (idx, patch) => {
    setCajas(prev => ({
      ...prev,
      [activeIdx]: prev[activeIdx].map((c, i) => i === idx ? { ...c, ...patch } : c),
    }));
  };

  // ─── Edit sheet state ───
  const [editingIdx, setEditingIdx] = React.useState(null);

  const nuevoLote = () => {
    // bump the lote number for convenience
    const m = lote.match(/^(.*?)(\d+)$/);
    if (m) {
      const next = String(parseInt(m[2]) + 1).padStart(m[2].length, '0');
      setLote(m[1] + next);
    }
    setLoteEditing(true);
  };

  const totalPesoProducto = productCajas.reduce((a, c) => a + c.peso, 0);
  const totalPesoPedido = Object.values(cajas).flat().reduce((a, c) => a + c.peso, 0);
  const totalCajasPedido = Object.values(cajas).flat().length;
  const cajasEsperadas = items.reduce((a, it) => a + (it.cajasPedidas ?? it.cajas), 0);
  const allDone = items.every((it, i) => (cajas[i] || []).length >= (it.cajasPedidas ?? it.cajas));

  const canRegister = peso && pesoNum > 0 && pendientes > 0 && lote.trim().length > 0;

  return (
    <>
      <StatusBar/>
      <div className="nav-bar">
        <div className="nav-pill-cluster">
          <button className="nav-pill" onClick={onBack} aria-label="Cerrar">
            <Icon name="x" size={18}/>
          </button>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', lineHeight: 1.15, minWidth: 0, flex: 1, padding: '0 8px' }}>
          <div style={{
            fontSize: 13, fontWeight: 700, letterSpacing: '-0.01em',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            maxWidth: '100%', color: 'var(--color-text)',
          }}>
            {base.cliente}
          </div>
          <div style={{
            fontSize: 10, fontWeight: 600, color: 'var(--color-text-muted)',
            fontVariantNumeric: 'tabular-nums', marginTop: 1,
            display: 'inline-flex', alignItems: 'center', gap: 5,
          }}>
            <span style={{ fontWeight: 700, color: 'var(--color-text-subtle)' }}>{base.id}</span>
            <span style={{ color: 'var(--color-text-subtle)' }}>·</span>
            <span>{base.entrega}</span>
          </div>
        </div>
        <div className="nav-pill-cluster">
          <button className="nav-pill" onClick={deshacerUltima} disabled={productCajas.length === 0}
            style={{ opacity: productCajas.length === 0 ? 0.35 : 1 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-15-6.7L3 13"/>
            </svg>
          </button>
        </div>
      </div>

      <div className="screen-body" style={{ paddingTop: 4, paddingBottom: 16, gap: 10 }}>
        {/* ───── Product chips — horizontal scroll ───── */}
        <div style={{
          display: 'flex', gap: 8, overflowX: 'auto', padding: '6px 2px 6px',
          scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch',
        }}>
          {items.map((it, i) => {
            const arr = cajas[i] || [];
            const total = it.cajasPedidas ?? it.cajas;
            const done = arr.length >= total;
            const pend = Math.max(0, total - arr.length);
            const active = i === activeIdx;
            const c = catColor[it.code] || '#6366f1';
            return (
              <button key={i}
                onClick={() => setActiveIdx(i)}
                style={{
                  flex: '0 0 auto',
                  display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 3,
                  padding: '7px 11px', minWidth: 108,
                  borderRadius: 11,
                  border: active ? `1.5px solid ${c}` : '1px solid var(--color-border)',
                  background: active ? `linear-gradient(135deg, ${c}14, ${c}08)` : 'var(--color-bg-elevated)',
                  cursor: 'pointer', fontFamily: 'inherit',
                  textAlign: 'left',
                  boxShadow: active ? `0 0 0 3px ${c}22` : 'none',
                }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 5,
                  fontSize: 9.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
                  color: done ? 'var(--color-success)' : active ? c : 'var(--color-text-muted)',
                }}>
                  <span style={{
                    width: 14, height: 14, borderRadius: 99,
                    background: done ? 'var(--color-success)' : c,
                    display: 'grid', placeItems: 'center', color: 'white',
                  }}>
                    {done
                      ? <Icon name="check" size={9} color="white" stroke={3}/>
                      : <span style={{ fontSize: 8, fontWeight: 800, fontVariantNumeric: 'tabular-nums' }}>{arr.length}/{total}</span>}
                  </span>
                  {done ? 'Listo' : `${pend} pend`}
                </div>
                <div style={{
                  fontSize: 12, fontWeight: 600, letterSpacing: '-0.01em',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  maxWidth: 100, color: active ? 'var(--color-text)' : 'var(--color-text-muted)',
                }}>
                  {it.nombre.split('·')[0].trim()}
                </div>
              </button>
            );
          })}
        </div>

        {/* ───── Active lote card (sticky) ───── */}
        <div style={{
          background: `linear-gradient(145deg, ${activeColor}12, ${activeColor}04 70%)`,
          border: `1px solid ${activeColor}33`,
          borderRadius: 14,
          padding: '10px 12px',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 5,
              fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.06em',
              color: activeColor, fontWeight: 800,
            }}>
              <span style={{ width: 5, height: 5, borderRadius: 99, background: activeColor }}/>
              Lote activo
            </div>
            <button onClick={nuevoLote} style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              fontSize: 11, fontWeight: 700, color: activeColor,
              fontFamily: 'inherit', letterSpacing: '-0.01em',
              display: 'inline-flex', alignItems: 'center', gap: 4, padding: 0,
            }}>
              <Icon name="plus" size={12} stroke={2.5}/> Nuevo lote
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <LoteField
              label="N° Lote"
              value={lote}
              onChange={setLote}
              editing={loteEditing}
              setEditing={setLoteEditing}
              mono autoFocus
            />
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
              <DateField
                label="Elaboración"
                value={fechaElab}
                formatted={formatISO(fechaElab)}
                onClick={() => setCalendar('elab')}
                accent={activeColor}
              />
              <DateField
                label="Vencimiento"
                value={fechaVenc}
                formatted={formatISO(fechaVenc)}
                onClick={() => setCalendar('venc')}
                accent={activeColor}
                warn={isExpiringSoonISO(fechaVenc)}
                auto={!vencManual}
              />
            </div>
          </div>
        </div>

        {/* ───── Weight entry + keypad ───── */}
        <div style={{
          border: '1px solid var(--color-border)',
          borderRadius: 16,
          background: 'var(--color-surface)',
          overflow: 'hidden',
        }}>
          {/* readout */}
          <div style={{
            padding: '14px 16px 10px',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            borderBottom: '1px dashed var(--color-border)',
          }}>
            <div>
              <div style={{ fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--color-text-subtle)', fontWeight: 700 }}>
                Caja {currentBoxNum} de {totalCajas}
              </div>
              <div style={{
                fontSize: 11, color: 'var(--color-text-muted)', marginTop: 2,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 180,
              }}>
                {activeItem.nombre}
              </div>
            </div>
            <div style={{
              display: 'flex', alignItems: 'baseline', gap: 3,
              fontFamily: 'ui-monospace, SF Mono, "JetBrains Mono", monospace',
              fontVariantNumeric: 'tabular-nums',
            }}>
              <span style={{
                fontSize: 48, fontWeight: 700, letterSpacing: '-0.04em',
                lineHeight: 1,
                color: peso ? 'var(--color-text)' : 'var(--color-text-subtle)',
                textShadow: peso ? `0 0 24px ${activeColor}33` : 'none',
                transition: 'color 160ms ease',
              }}>
                {peso || '0'}
              </span>
              <span style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text-muted)' }}>kg</span>
            </div>
          </div>

          {/* keypad */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr) 1fr',
            gap: 0,
          }}>
            {[
              {k:'1'},{k:'2'},{k:'3'},{k:'back', icon:'back', row:0, color:'muted'},
              {k:'4'},{k:'5'},{k:'6'},{k:'clear', label:'C', row:1, color:'muted'},
              {k:'7'},{k:'8'},{k:'9'},{k:'register', label:'+ Caja', row:2, span:2, color:'primary'},
              {k:'0', span:2},{k:'.'},
            ].map((btn, i) => {
              if (btn.k === 'register') {
                return (
                  <button key={i}
                    onClick={registrarCaja}
                    disabled={!canRegister}
                    style={{
                      gridRow: 'span 2',
                      border: 'none',
                      background: canRegister
                        ? `linear-gradient(180deg, var(--indigo-500), var(--violet-500))`
                        : 'var(--color-bg-subtle)',
                      color: canRegister ? 'white' : 'var(--color-text-subtle)',
                      fontSize: 14, fontWeight: 800, letterSpacing: '-0.01em',
                      cursor: canRegister ? 'pointer' : 'not-allowed',
                      fontFamily: 'inherit',
                      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4,
                      boxShadow: canRegister ? 'inset 0 1px 0 rgba(255,255,255,0.25)' : 'none',
                      borderTop: '1px solid var(--color-border-subtle)',
                      borderLeft: '1px solid var(--color-border-subtle)',
                      transition: 'all 140ms ease',
                    }}>
                    <Icon name="plus" size={18} stroke={2.6}/>
                    Caja
                  </button>
                );
              }
              const isOp = btn.color === 'muted';
              return (
                <button key={i}
                  onClick={() => press(btn.k)}
                  style={{
                    gridColumn: btn.span ? `span ${btn.span}` : undefined,
                    height: 54, border: 'none',
                    background: 'var(--color-bg-elevated)',
                    color: isOp ? 'var(--color-text-muted)' : 'var(--color-text)',
                    fontSize: btn.k === '.' ? 22 : 20,
                    fontWeight: 600, letterSpacing: '-0.02em',
                    fontFamily: 'ui-monospace, SF Mono, "JetBrains Mono", monospace',
                    fontVariantNumeric: 'tabular-nums',
                    cursor: 'pointer',
                    borderTop: '1px solid var(--color-border-subtle)',
                    borderLeft: '1px solid var(--color-border-subtle)',
                    display: 'grid', placeItems: 'center',
                    transition: 'background 100ms ease',
                  }}
                  onMouseDown={(e) => e.currentTarget.style.background = 'var(--color-bg-subtle)'}
                  onMouseUp={(e) => e.currentTarget.style.background = 'var(--color-bg-elevated)'}
                  onMouseLeave={(e) => e.currentTarget.style.background = 'var(--color-bg-elevated)'}
                >
                  {btn.k === 'back'
                    ? <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 5H10L3 12l7 7h11a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1z"/><path d="M18 9l-6 6M12 9l6 6"/></svg>
                    : btn.label || btn.k}
                </button>
              );
            })}
          </div>
        </div>

        {/* ───── Registered boxes (grouped by lote) ───── */}
        {productCajas.length > 0 && (
          <>
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
              padding: '6px 2px 0',
            }}>
              <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, color: 'var(--color-text-subtle)' }}>
                Cajas registradas
              </div>
              <div style={{ fontSize: 11, fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: 'var(--color-text-muted)' }}>
                <b style={{ color: 'var(--color-text)' }}>{totalPesoProducto.toFixed(2)} kg</b> · {pesadas}/{totalCajas}
              </div>
            </div>

            {lotesAgrupados.map((g, gi) => (
              <div key={gi} style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: 12, padding: 0, overflow: 'hidden',
              }}>
                <div style={{
                  padding: '8px 12px',
                  background: 'var(--color-bg-subtle)',
                  borderBottom: '1px solid var(--color-border-subtle)',
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  fontSize: 11, fontVariantNumeric: 'tabular-nums',
                }}>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 800, letterSpacing: '-0.01em', color: 'var(--color-text)', fontFamily: 'ui-monospace, SF Mono, monospace' }}>
                      {g.lote}
                    </span>
                    <span style={{ color: 'var(--color-text-muted)' }}>
                      Elab. {formatISO(g.fechaElab)}
                    </span>
                    <span style={{ color: isExpiringSoonISO(g.fechaVenc) ? 'var(--color-warning-soft-fg)' : 'var(--color-text-muted)', fontWeight: isExpiringSoonISO(g.fechaVenc) ? 700 : 400 }}>
                      Venc. {formatISO(g.fechaVenc)}
                    </span>
                  </div>
                  <span style={{ color: 'var(--color-text-muted)', fontWeight: 600 }}>
                    {g.cajas.length} {g.cajas.length === 1 ? 'caja' : 'cajas'}
                  </span>
                </div>
                <div style={{ padding: '8px 12px', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {g.cajas.map((c, ci) => (
                    <button key={ci}
                      onClick={() => setEditingIdx(c.idx)}
                      title="Toca para editar"
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 5,
                        padding: '5px 9px',
                        border: `1px solid ${activeColor}44`,
                        background: `${activeColor}10`,
                        borderRadius: 8, cursor: 'pointer',
                        fontFamily: 'inherit',
                        fontVariantNumeric: 'tabular-nums',
                        transition: 'all 140ms ease',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = `${activeColor}1f`;
                        e.currentTarget.style.borderColor = `${activeColor}88`;
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = `${activeColor}10`;
                        e.currentTarget.style.borderColor = `${activeColor}44`;
                      }}
                    >
                      <span style={{ fontSize: 9, fontWeight: 800, color: activeColor, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                        #{String(c.idx + 1).padStart(2,'0')}
                      </span>
                      <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 3 }}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--color-text)', letterSpacing: '-0.01em' }}>
                          {c.peso.toFixed(2)}
                        </span>
                        <span style={{ fontSize: 9, color: 'var(--color-text-subtle)', fontWeight: 600 }}>kg</span>
                      </span>
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--color-text-subtle)', marginLeft: 1 }}>
                        <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
                      </svg>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </>
        )}

        <div style={{ height: 80 }}/>
      </div>

      {/* Bottom summary */}
      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0,
        padding: '10px 14px calc(10px + env(safe-area-inset-bottom))',
        background: 'var(--color-surface-strong)',
        backdropFilter: 'blur(24px) saturate(1.8)',
        WebkitBackdropFilter: 'blur(24px) saturate(1.8)',
        borderTop: '1px solid var(--color-border)',
        display: 'flex', alignItems: 'center', gap: 10, zIndex: 10,
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, color: 'var(--color-text-subtle)' }}>Total pedido</div>
          <div style={{ fontSize: 14, fontWeight: 700, fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.01em' }}>
            {totalPesoPedido.toFixed(2)}
            <small style={{ fontSize: 10, color: 'var(--color-text-subtle)', fontWeight: 600, marginLeft: 3 }}>kg</small>
            <span style={{ margin: '0 6px', color: 'var(--color-text-subtle)' }}>·</span>
            {totalCajasPedido}/{cajasEsperadas}
            <small style={{ fontSize: 10, color: 'var(--color-text-subtle)', fontWeight: 600, marginLeft: 3 }}>cajas</small>
          </div>
        </div>
        <button
          disabled={!allDone}
          style={{
            height: 44, padding: '0 16px', borderRadius: 12, border: 'none',
            background: allDone
              ? 'linear-gradient(135deg, var(--color-success) 0%, #059669 100%)'
              : 'var(--color-bg-elevated)',
            color: allDone ? 'white' : 'var(--color-text-muted)',
            fontSize: 13, fontWeight: 700,
            cursor: allDone ? 'pointer' : 'not-allowed',
            boxShadow: allDone ? '0 10px 24px -6px rgba(16,185,129,0.4), inset 0 1px 0 rgba(255,255,255,0.25)' : 'none',
            border: allDone ? 'none' : '1px solid var(--color-border)',
            fontFamily: 'inherit', letterSpacing: '-0.01em',
            display: 'inline-flex', alignItems: 'center', gap: 6,
          }}>
          <Icon name="check" size={15} stroke={3}/>
          Finalizar
        </button>
      </div>
      {editingIdx != null && productCajas[editingIdx] && (
        <EditCajaSheet
          caja={productCajas[editingIdx]}
          idx={editingIdx}
          accent={activeColor}
          productName={activeItem.nombre}
          onClose={() => setEditingIdx(null)}
          onSave={(patch) => {
            updateCaja(editingIdx, patch);
            setEditingIdx(null);
          }}
          onDelete={() => {
            eliminarCaja(editingIdx);
            setEditingIdx(null);
          }}
        />
      )}

      {calendar && (
        <DatePickerSheet
          title={calendar === 'elab' ? 'Fecha de elaboración' : 'Fecha de vencimiento'}
          subtitle={calendar === 'venc' && !vencManual
            ? 'Por defecto +1 año desde la elaboración'
            : undefined}
          value={calendar === 'elab' ? fechaElab : fechaVenc}
          accent={activeColor}
          minISO={calendar === 'venc' ? fechaElab : undefined}
          onClose={() => setCalendar(null)}
          onSelect={(iso) => {
            if (calendar === 'elab') setElab(iso);
            else setVenc(iso);
            setCalendar(null);
          }}
          onReset={calendar === 'venc' ? () => {
            setVencManual(false);
            setFechaVenc(addYears(fechaElab, 1));
            setCalendar(null);
          } : undefined}
        />
      )}

    </>
  );
};

// ─── DateField — opens calendar on tap ───
function DateField({ label, value, formatted, onClick, accent, warn, auto }) {
  return (
    <button onClick={onClick} style={{
      padding: '7px 10px',
      background: 'var(--color-bg-elevated)',
      border: `1px solid ${warn ? 'var(--color-warning)' : 'var(--color-border-subtle)'}`,
      borderRadius: 10,
      cursor: 'pointer',
      fontFamily: 'inherit',
      textAlign: 'left',
      display: 'flex', flexDirection: 'column', alignItems: 'stretch', gap: 2,
      transition: 'border-color 120ms ease',
    }}
    onMouseEnter={(e) => { if (!warn) e.currentTarget.style.borderColor = accent + '77'; }}
    onMouseLeave={(e) => { if (!warn) e.currentTarget.style.borderColor = 'var(--color-border-subtle)'; }}
    >
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em',
        color: warn ? 'var(--color-warning-soft-fg)' : 'var(--color-text-subtle)',
        fontWeight: 700, marginBottom: 2,
      }}>
        <span>{label}{warn && ' ⚠'}</span>
        {auto && (
          <span style={{
            fontSize: 8, letterSpacing: '0.06em', color: accent,
            background: `${accent}1a`, padding: '1px 5px', borderRadius: 4, fontWeight: 800,
          }}>AUTO</span>
        )}
      </div>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 4,
        fontSize: 13.5, fontWeight: 700, color: 'var(--color-text)',
        fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.01em',
      }}>
        <span>{formatted}</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--color-text-subtle)', flexShrink: 0 }}>
          <rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>
        </svg>
      </div>
    </button>
  );
}

// ─── DatePickerSheet — bottom-sheet calendar ───
function DatePickerSheet({ title, subtitle, value, onClose, onSelect, onReset, accent = '#6366f1', minISO }) {
  const parse = (iso) => {
    const [y, m, d] = iso.split('-').map(Number);
    return { y, m: m - 1, d };
  };
  const init = parse(value);
  const [viewY, setViewY] = React.useState(init.y);
  const [viewM, setViewM] = React.useState(init.m);

  const monthNames = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
  const dowNames = ['L','M','M','J','V','S','D'];

  const daysInMonth = new Date(viewY, viewM + 1, 0).getDate();
  // Monday-first: JS getDay() is 0=Sun..6=Sat; shift so Monday=0
  const firstDow = (new Date(viewY, viewM, 1).getDay() + 6) % 7;

  const prevMonth = () => {
    if (viewM === 0) { setViewY(viewY - 1); setViewM(11); } else setViewM(viewM - 1);
  };
  const nextMonth = () => {
    if (viewM === 11) { setViewY(viewY + 1); setViewM(0); } else setViewM(viewM + 1);
  };

  const todayP = parse(todayISOStatic());
  const selP = init;
  const minP = minISO ? parse(minISO) : null;

  const cells = [];
  for (let i = 0; i < firstDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  const pad = (n) => String(n).padStart(2, '0');
  const toISO = (y, m, d) => `${y}-${pad(m+1)}-${pad(d)}`;

  return (
    <div style={{
      position: 'absolute', inset: 0, zIndex: 50,
      background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'flex-end',
      animation: 'dp-fade 180ms ease',
    }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: '100%',
        background: 'var(--color-surface)',
        borderTopLeftRadius: 20, borderTopRightRadius: 20,
        padding: '14px 16px calc(16px + env(safe-area-inset-bottom))',
        borderTop: '1px solid var(--color-border)',
        boxShadow: '0 -20px 60px rgba(0,0,0,0.45)',
        animation: 'dp-slide 220ms cubic-bezier(0.2, 0.8, 0.2, 1)',
      }}>
        {/* grab handle */}
        <div style={{
          width: 36, height: 4, borderRadius: 99,
          background: 'var(--color-border)',
          margin: '0 auto 12px',
        }}/>

        {/* header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 800, letterSpacing: '-0.01em' }}>{title}</div>
            {subtitle && <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 2 }}>{subtitle}</div>}
          </div>
          <button onClick={onClose} style={{
            background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)',
            width: 30, height: 30, borderRadius: 8, cursor: 'pointer',
            display: 'grid', placeItems: 'center', color: 'var(--color-text-muted)',
          }}>
            <Icon name="x" size={16}/>
          </button>
        </div>

        {/* month nav */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '4px 0 10px',
        }}>
          <button onClick={prevMonth} style={calNavBtn()}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6"/></svg>
          </button>
          <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: '-0.01em' }}>
            {monthNames[viewM]} {viewY}
          </div>
          <button onClick={nextMonth} style={calNavBtn()}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6"/></svg>
          </button>
        </div>

        {/* dow header */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2, marginBottom: 4 }}>
          {dowNames.map((d, i) => (
            <div key={i} style={{
              textAlign: 'center', fontSize: 10, fontWeight: 700,
              color: 'var(--color-text-subtle)',
              textTransform: 'uppercase', letterSpacing: '0.04em',
              padding: '4px 0',
            }}>{d}</div>
          ))}
        </div>

        {/* day grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2 }}>
          {cells.map((d, i) => {
            if (d === null) return <div key={i}/>;
            const iso = toISO(viewY, viewM, d);
            const isSel = viewY === selP.y && viewM === selP.m && d === selP.d;
            const isToday = viewY === todayP.y && viewM === todayP.m && d === todayP.d;
            const disabled = minP && (
              viewY < minP.y ||
              (viewY === minP.y && viewM < minP.m) ||
              (viewY === minP.y && viewM === minP.m && d < minP.d)
            );
            return (
              <button key={i}
                disabled={disabled}
                onClick={() => onSelect(iso)}
                style={{
                  aspectRatio: '1 / 1',
                  border: 'none', borderRadius: 10,
                  background: isSel
                    ? `linear-gradient(135deg, ${accent}, ${accent}dd)`
                    : isToday
                      ? `${accent}14`
                      : 'transparent',
                  color: isSel
                    ? 'white'
                    : disabled
                      ? 'var(--color-text-subtle)'
                      : isToday
                        ? accent
                        : 'var(--color-text)',
                  fontSize: 13, fontWeight: isSel || isToday ? 700 : 500,
                  fontFamily: 'inherit', fontVariantNumeric: 'tabular-nums',
                  cursor: disabled ? 'not-allowed' : 'pointer',
                  opacity: disabled ? 0.35 : 1,
                  transition: 'background 120ms ease',
                  position: 'relative',
                  boxShadow: isSel ? `0 4px 12px -2px ${accent}55` : 'none',
                }}>
                {d}
                {isToday && !isSel && (
                  <span style={{
                    position: 'absolute', bottom: 4, left: '50%', transform: 'translateX(-50%)',
                    width: 3, height: 3, borderRadius: 99, background: accent,
                  }}/>
                )}
              </button>
            );
          })}
        </div>

        {/* footer actions */}
        <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
          {onReset && (
            <button onClick={onReset} style={{
              flex: 1, height: 44, borderRadius: 12,
              background: 'var(--color-bg-elevated)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text)',
              fontSize: 12, fontWeight: 700, cursor: 'pointer',
              fontFamily: 'inherit', letterSpacing: '-0.01em',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>
              </svg>
              Auto (+1 año)
            </button>
          )}
          <button onClick={() => onSelect(toISO(todayP.y, todayP.m, todayP.d))} style={{
            flex: 1, height: 44, borderRadius: 12,
            background: `linear-gradient(135deg, ${accent}, ${accent}dd)`,
            border: 'none', color: 'white',
            fontSize: 12, fontWeight: 700, cursor: 'pointer',
            fontFamily: 'inherit', letterSpacing: '-0.01em',
            boxShadow: `0 8px 20px -4px ${accent}66, inset 0 1px 0 rgba(255,255,255,0.25)`,
          }}>
            Hoy
          </button>
        </div>
      </div>

      <style dangerouslySetInnerHTML={{__html: `
        @keyframes dp-fade { from { opacity: 0; } to { opacity: 1; } }
        @keyframes dp-slide { from { transform: translateY(100%); } to { transform: translateY(0); } }
      `}}/>
    </div>
  );
}

function calNavBtn() {
  return {
    width: 32, height: 32, borderRadius: 8,
    background: 'var(--color-bg-elevated)',
    border: '1px solid var(--color-border)',
    display: 'grid', placeItems: 'center', cursor: 'pointer',
    color: 'var(--color-text)', fontFamily: 'inherit',
  };
}

function todayISOStatic() {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth()+1).padStart(2,'0')}-${String(n.getDate()).padStart(2,'0')}`;
}

function isExpiringSoonISO(iso) {
  if (!iso) return false;
  const [y, m, d] = iso.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  const now = new Date();
  const days = (date - now) / (1000 * 60 * 60 * 24);
  return days < 30;
}

// Helper field for lote/fecha — inline editable
function LoteField({ label, value, onChange, placeholder, mono, warn, autoFocus, editing, setEditing }) {
  const inputRef = React.useRef(null);
  React.useEffect(() => { if (editing && inputRef.current) inputRef.current.focus(); }, [editing]);
  return (
    <div style={{
      padding: '7px 10px',
      background: 'var(--color-bg-elevated)',
      border: `1px solid ${warn ? 'var(--color-warning)' : 'var(--color-border-subtle)'}`,
      borderRadius: 10,
    }}>
      <div style={{
        fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em',
        color: warn ? 'var(--color-warning-soft-fg)' : 'var(--color-text-subtle)',
        fontWeight: 700, marginBottom: 2,
      }}>
        {label}{warn && ' ⚠'}
      </div>
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        style={{
          width: '100%', border: 'none', outline: 'none', background: 'transparent',
          fontSize: 13.5, fontWeight: 700, color: 'var(--color-text)',
          fontFamily: mono ? 'ui-monospace, SF Mono, monospace' : 'inherit',
          fontVariantNumeric: 'tabular-nums',
          letterSpacing: '-0.01em',
          padding: 0,
        }}
      />
    </div>
  );
}

function isExpiringSoon_DEPRECATED() { return false; }

// ─── EditCajaSheet — edit a single registered box ───
function EditCajaSheet({ caja, idx, accent, productName, onClose, onSave, onDelete }) {
  const [peso, setPeso] = React.useState(caja.peso.toFixed(2));
  const [lote, setLote] = React.useState(caja.lote);
  const [fechaElab, setFechaElab] = React.useState(caja.fechaElab);
  const [fechaVenc, setFechaVenc] = React.useState(caja.fechaVenc);
  const [calendar, setCalendar] = React.useState(null);
  const [confirmDel, setConfirmDel] = React.useState(false);

  const formatISO = (iso) => {
    if (!iso) return '';
    const [y, m, d] = iso.split('-');
    return `${d}/${m}/${y}`;
  };
  const addYears = (iso, yrs) => {
    const [y, m, da] = iso.split('-').map(Number);
    const nd = new Date(y + yrs, m - 1, da);
    return `${nd.getFullYear()}-${String(nd.getMonth()+1).padStart(2,'0')}-${String(nd.getDate()).padStart(2,'0')}`;
  };

  const pesoNum = parseFloat(peso || '0');
  const pesoChanged = Math.abs(pesoNum - caja.peso) > 0.001;
  const loteChanged = lote !== caja.lote;
  const elabChanged = fechaElab !== caja.fechaElab;
  const vencChanged = fechaVenc !== caja.fechaVenc;
  const anyChange = pesoChanged || loteChanged || elabChanged || vencChanged;
  const canSave = pesoNum > 0 && lote.trim().length > 0 && anyChange;

  const pressPeso = (k) => {
    setPeso(prev => {
      if (k === 'back') return prev.slice(0, -1);
      if (k === 'clear') return '';
      if (k === '.') {
        if (prev.includes('.')) return prev;
        if (prev === '') return '0.';
        return prev + '.';
      }
      if (prev === '0') return k;
      if (prev.includes('.')) {
        const [, dec] = prev.split('.');
        if (dec.length >= 2) return prev;
      }
      if (prev.length >= 6) return prev;
      return prev + k;
    });
  };

  return (
    <div style={{
      position: 'absolute', inset: 0, zIndex: 60,
      background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'flex-end',
      animation: 'dp-fade 180ms ease',
    }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: '100%',
        maxHeight: '92%',
        overflowY: 'auto',
        background: 'var(--color-surface)',
        borderTopLeftRadius: 20, borderTopRightRadius: 20,
        padding: '14px 16px calc(16px + env(safe-area-inset-bottom))',
        borderTop: '1px solid var(--color-border)',
        boxShadow: '0 -20px 60px rgba(0,0,0,0.45)',
        animation: 'dp-slide 220ms cubic-bezier(0.2, 0.8, 0.2, 1)',
      }}>
        {/* grab handle */}
        <div style={{
          width: 36, height: 4, borderRadius: 99,
          background: 'var(--color-border)',
          margin: '0 auto 12px',
        }}/>

        {/* header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14, gap: 10 }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{
              fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.08em',
              color: accent, fontWeight: 800,
              display: 'inline-flex', alignItems: 'center', gap: 5,
            }}>
              <span style={{ width: 5, height: 5, borderRadius: 99, background: accent }}/>
              Editar caja #{String(idx + 1).padStart(2, '0')}
            </div>
            <div style={{
              fontSize: 13, fontWeight: 700, letterSpacing: '-0.01em', marginTop: 3,
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              color: 'var(--color-text)',
            }}>
              {productName}
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)',
            width: 30, height: 30, borderRadius: 8, cursor: 'pointer',
            display: 'grid', placeItems: 'center', color: 'var(--color-text-muted)',
            flexShrink: 0,
          }}>
            <Icon name="x" size={16}/>
          </button>
        </div>

        {/* Peso readout */}
        <div style={{
          padding: '12px 14px',
          border: `1px solid ${accent}33`,
          background: `linear-gradient(145deg, ${accent}12, ${accent}04)`,
          borderRadius: 14,
          marginBottom: 10,
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <div style={{
              fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.08em',
              color: 'var(--color-text-subtle)', fontWeight: 700,
            }}>
              Peso de la caja
            </div>
            {pesoChanged && (
              <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--color-text-muted)', fontVariantNumeric: 'tabular-nums' }}>
                antes: {caja.peso.toFixed(2)} kg
              </div>
            )}
          </div>
          <div style={{
            display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: 4,
            padding: '6px 0 2px',
            fontFamily: 'ui-monospace, SF Mono, monospace',
            fontVariantNumeric: 'tabular-nums',
          }}>
            <span style={{
              fontSize: 40, fontWeight: 700, letterSpacing: '-0.04em', lineHeight: 1,
              color: peso ? 'var(--color-text)' : 'var(--color-text-subtle)',
              textShadow: pesoChanged ? `0 0 20px ${accent}44` : 'none',
            }}>
              {peso || '0'}
            </span>
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text-muted)' }}>kg</span>
          </div>
        </div>

        {/* compact keypad */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 0,
          border: '1px solid var(--color-border)',
          borderRadius: 12,
          overflow: 'hidden',
          marginBottom: 12,
        }}>
          {['1','2','3','back','4','5','6','clear','7','8','9','.','0'].map((k, i) => (
            <button key={i}
              onClick={() => pressPeso(k)}
              style={{
                gridColumn: k === '0' ? 'span 3' : undefined,
                height: 44, border: 'none',
                background: 'var(--color-bg-elevated)',
                color: (k === 'back' || k === 'clear') ? 'var(--color-text-muted)' : 'var(--color-text)',
                fontSize: 17, fontWeight: 600,
                fontFamily: 'ui-monospace, SF Mono, monospace',
                fontVariantNumeric: 'tabular-nums',
                cursor: 'pointer',
                borderTop: i >= 4 ? '1px solid var(--color-border-subtle)' : 'none',
                borderLeft: (i % 4 !== 0 && k !== '0') ? '1px solid var(--color-border-subtle)' : 'none',
                display: 'grid', placeItems: 'center',
              }}
              onMouseDown={(e) => e.currentTarget.style.background = 'var(--color-bg-subtle)'}
              onMouseUp={(e) => e.currentTarget.style.background = 'var(--color-bg-elevated)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'var(--color-bg-elevated)'}
            >
              {k === 'back'
                ? <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 5H10L3 12l7 7h11a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1z"/><path d="M18 9l-6 6M12 9l6 6"/></svg>
                : k === 'clear' ? 'C' : k}
            </button>
          ))}
        </div>

        {/* Lote + fechas */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
          <LoteField
            label="N° Lote"
            value={lote}
            onChange={setLote}
            mono
          />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
            <DateField
              label="Elaboración"
              value={fechaElab}
              formatted={formatISO(fechaElab)}
              onClick={() => setCalendar('elab')}
              accent={accent}
            />
            <DateField
              label="Vencimiento"
              value={fechaVenc}
              formatted={formatISO(fechaVenc)}
              onClick={() => setCalendar('venc')}
              accent={accent}
              warn={isExpiringSoonISO(fechaVenc)}
            />
          </div>
        </div>

        {/* actions */}
        {confirmDel ? (
          <div style={{
            border: '1px solid var(--color-danger)',
            background: 'rgba(239, 68, 68, 0.08)',
            borderRadius: 12, padding: 10,
          }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--color-danger)', marginBottom: 8 }}>
              ¿Eliminar caja #{String(idx + 1).padStart(2, '0')}?
            </div>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 10 }}>
              Las cajas siguientes se renumerarán. Esta acción no se puede deshacer.
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button onClick={() => setConfirmDel(false)} style={{
                flex: 1, height: 40, borderRadius: 10,
                background: 'var(--color-bg-elevated)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-text)',
                fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
              }}>Cancelar</button>
              <button onClick={onDelete} style={{
                flex: 1, height: 40, borderRadius: 10,
                background: 'var(--color-danger)',
                border: 'none', color: 'white',
                fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
                boxShadow: '0 6px 16px -4px rgba(239,68,68,0.5)',
              }}>Eliminar</button>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setConfirmDel(true)} style={{
              width: 48, height: 48, borderRadius: 12,
              background: 'var(--color-bg-elevated)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-danger)',
              cursor: 'pointer', display: 'grid', placeItems: 'center',
              fontFamily: 'inherit', flexShrink: 0,
            }} title="Eliminar">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6"/>
              </svg>
            </button>
            <button
              onClick={() => canSave && onSave({ peso: pesoNum, lote, fechaElab, fechaVenc })}
              disabled={!canSave}
              style={{
                flex: 1, height: 48, borderRadius: 12, border: 'none',
                background: canSave
                  ? `linear-gradient(135deg, ${accent}, ${accent}dd)`
                  : 'var(--color-bg-elevated)',
                color: canSave ? 'white' : 'var(--color-text-muted)',
                fontSize: 13, fontWeight: 700,
                cursor: canSave ? 'pointer' : 'not-allowed',
                boxShadow: canSave ? `0 8px 20px -4px ${accent}66, inset 0 1px 0 rgba(255,255,255,0.25)` : 'none',
                border: canSave ? 'none' : '1px solid var(--color-border)',
                fontFamily: 'inherit', letterSpacing: '-0.01em',
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              }}>
              <Icon name="check" size={16} stroke={3}/>
              {anyChange ? 'Guardar cambios' : 'Sin cambios'}
            </button>
          </div>
        )}
      </div>

      {calendar && (
        <div onClick={(e) => e.stopPropagation()}>
          <DatePickerSheet
            title={calendar === 'elab' ? 'Fecha de elaboración' : 'Fecha de vencimiento'}
            value={calendar === 'elab' ? fechaElab : fechaVenc}
            accent={accent}
            minISO={calendar === 'venc' ? fechaElab : undefined}
            onClose={() => setCalendar(null)}
            onSelect={(iso) => {
              if (calendar === 'elab') {
                setFechaElab(iso);
                // keep venc >= elab
                if (iso > fechaVenc) setFechaVenc(addYears(iso, 1));
              } else {
                setFechaVenc(iso);
              }
              setCalendar(null);
            }}
          />
        </div>
      )}
    </div>
  );
}

window.PesarScreen = PesarScreen;
