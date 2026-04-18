// Screen: Pedido detail
const PedidoDetail = ({ pedidoId, onBack }) => {
  const d = window.PESOS_DATA;
  const base = d.pedidos.find(x => x.id === pedidoId) || d.pedidos[0];
  // Merge base row with detail lineas/notas
  // Category → swatch color (a thin accent strip rather than a noisy 3-letter tile)
  const catColor = {
    RES: '#dc2626', // res — rojo
    LOM: '#b91c1c', // lomo — rojo oscuro
    FAL: '#f97316', // falda — naranja
    POL: '#eab308', // pollo — amarillo
    MOL: '#be123c', // molida — carmín
    CER: '#ec4899', // cerdo — rosa
  };
  const lineas = (d.detail?.items || []).map((it) => {
    const pendingCajas = (it.cajasPedidas ?? it.cajas) - it.cajas;
    return {
      codigo: it.code,
      nombre: it.nombre,
      cajas: it.cajas,
      cajasPedidas: it.cajasPedidas ?? it.cajas,
      pendingCajas,
      peso: it.peso,
      precio: it.precio,
      subtotal: Math.round(it.precio * it.peso),
      pesado: it.pesado,
      color: catColor[it.code] || '#6366f1',
    };
  });
  const p = { ...base, lineas, ruta: base.ruta || 'Ruta Valencia Norte', pago: 'Crédito 30 días', notas: 'Entregar en muelle norte · 7–11am · Preguntar por Carlos.' };
  const [tab, setTab] = React.useState('productos');

  const stateCfg = {
    pendiente: { label: 'Pendiente', cls: 'badge-warning', icon: 'clock' },
    preparado: { label: 'Preparado', cls: 'badge-success', icon: 'package' },
    facturado: { label: 'Facturado', cls: 'badge-info', icon: 'check' },
  };
  const cfg = stateCfg[p.estado];

  // progress timeline
  const steps = ['Recibido', 'Preparado', 'Facturado', 'Entregado'];
  const stepIdx = { pendiente: 0, preparado: 1, facturado: 2 }[p.estado];

  return (
    <>
      <StatusBar/>
      <div className="nav-bar">
        <div className="nav-pill-cluster">
          <button className="nav-pill" onClick={onBack} aria-label="Atrás">
            <Icon name="chevron-left" size={20}/>
          </button>
        </div>
        <div style={{ fontSize: 13, fontWeight: 600, fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.01em' }}>{p.id}</div>
        <div className="nav-pill-cluster">
          <div className="nav-pill"><Icon name="more" size={18}/></div>
        </div>
      </div>

      <div className="screen-body" style={{ paddingTop: 8 }}>
        {/* Hero card */}
        <div className="gcard" style={{ padding: 20, position: 'relative', overflow: 'hidden' }}>
          <div style={{
            position: 'absolute', top: -40, right: -40, width: 180, height: 180,
            background: 'radial-gradient(circle, var(--indigo-300) 0%, transparent 70%)',
            opacity: 0.15, pointerEvents: 'none'
          }}/>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
            <div>
              <span className={`badge ${cfg.cls}`}>
                <Icon name={cfg.icon} size={10}/>
                {cfg.label}
              </span>
              {p.vencido && <span style={{ marginLeft: 6, fontSize: 10.5, color: 'var(--color-danger)', fontWeight: 700 }}>● Vencido</span>}
            </div>
            <div style={{ fontSize: 10.5, color: 'var(--color-text-subtle)', fontVariantNumeric: 'tabular-nums', textAlign: 'right' }}>
              Creado {p.creado}<br/>Entrega {p.entrega}
            </div>
          </div>

          <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.025em', lineHeight: 1.15 }}>{p.cliente}</div>
          <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 4 }}>{p.ruta || 'Ruta sur'} · {p.vendedor || d.vendedor}</div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginTop: 18, paddingTop: 16, borderTop: '1px solid var(--color-border-subtle)' }}>
            <div>
              <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-subtle)', fontWeight: 700 }}>Cajas</div>
              <div style={{ fontSize: 20, fontWeight: 700, fontVariantNumeric: 'tabular-nums', marginTop: 2 }}>{p.cajas}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-subtle)', fontWeight: 700 }}>Peso</div>
              <div style={{ fontSize: 20, fontWeight: 700, fontVariantNumeric: 'tabular-nums', marginTop: 2 }}>{p.peso.toLocaleString('es-ES')}<small style={{ fontSize: 11, color: 'var(--color-text-subtle)', fontWeight: 600, marginLeft: 2 }}>kg</small></div>
            </div>
            <div>
              <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-subtle)', fontWeight: 700 }}>Total</div>
              <div style={{ fontSize: 20, fontWeight: 700, fontVariantNumeric: 'tabular-nums', marginTop: 2, color: 'var(--indigo-500)' }}>{formatXCG(p.total)}<small style={{ fontSize: 11, color: 'var(--color-text-subtle)', fontWeight: 600, marginLeft: 2 }}>XCG</small></div>
            </div>
          </div>
        </div>

        {/* Timeline */}
        <div className="sec-head"><h3 className="sec-title">Progreso</h3></div>
        <div className="gcard" style={{ padding: '20px 16px 16px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${steps.length}, 1fr)`, gap: 0, position: 'relative' }}>
            <div style={{
              position: 'absolute', top: 11, left: `calc(${100/(steps.length*2)}% + 0px)`,
              right: `calc(${100/(steps.length*2)}% + 0px)`, height: 2,
              background: 'var(--color-border)', borderRadius: 99, zIndex: 0
            }}/>
            <div style={{
              position: 'absolute', top: 11, left: `calc(${100/(steps.length*2)}% + 0px)`,
              width: `calc(${(stepIdx / (steps.length-1)) * 100}% * ${(steps.length - 1) / steps.length})`,
              height: 2, background: 'linear-gradient(90deg, var(--indigo-500), var(--violet-500))',
              borderRadius: 99, zIndex: 0,
              transition: 'width 800ms cubic-bezier(0.25,1,0.5,1)'
            }}/>
            {steps.map((s, i) => {
              const done = i <= stepIdx;
              const active = i === stepIdx;
              return (
                <div key={s} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, position: 'relative', zIndex: 1 }}>
                  <div style={{
                    width: 24, height: 24, borderRadius: 99,
                    background: done ? 'linear-gradient(135deg, var(--indigo-500), var(--violet-500))' : 'var(--color-bg-elevated)',
                    border: done ? 'none' : '2px solid var(--color-border)',
                    color: 'white',
                    display: 'grid', placeItems: 'center',
                    boxShadow: active ? '0 0 0 4px var(--color-accent-soft)' : 'none',
                    transition: 'all 300ms ease'
                  }}>
                    {done && <Icon name="check" size={12}/>}
                  </div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: done ? 'var(--color-text)' : 'var(--color-text-subtle)', textAlign: 'center', letterSpacing: '-0.01em' }}>{s}</div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Tabs */}
        <div className="segmented" style={{ marginTop: 12 }}>
          {[
            { id: 'productos', label: 'Productos' },
            { id: 'detalles',  label: 'Detalles' },
            { id: 'historial', label: 'Historial' },
          ].map(t => (
            <button key={t.id} className={tab === t.id ? 'active' : ''} onClick={() => setTab(t.id)}>{t.label}</button>
          ))}
        </div>

        {tab === 'productos' && (
          <>
            {/* Mini summary strip */}
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 0,
              padding: '10px 14px', marginBottom: 8,
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: 12,
              fontSize: 11, color: 'var(--color-text-muted)',
              fontVariantNumeric: 'tabular-nums',
            }}>
              <div><b style={{ color: 'var(--color-text)', fontSize: 13, fontWeight: 700, letterSpacing: '-0.01em' }}>{p.lineas.length}</b> productos</div>
              <div style={{ textAlign: 'center' }}><b style={{ color: 'var(--color-text)', fontSize: 13, fontWeight: 700, letterSpacing: '-0.01em' }}>{p.lineas.filter(l => l.pesado).length}/{p.lineas.length}</b> pesados</div>
              <div style={{ textAlign: 'right' }}><b style={{ color: 'var(--color-text)', fontSize: 13, fontWeight: 700, letterSpacing: '-0.01em' }}>{p.lineas.reduce((a,l) => a+l.peso, 0).toFixed(1)}</b> kg total</div>
            </div>

            <div className="gcard" style={{ padding: 0, overflow: 'hidden' }}>
              {p.lineas.map((l, i) => (
                <div key={i} style={{
                  display: 'grid',
                  gridTemplateColumns: '3px 1fr auto',
                  borderBottom: i < p.lineas.length - 1 ? '1px solid var(--color-border-subtle)' : 'none',
                }}>
                  {/* Color strip */}
                  <div style={{ background: l.color, opacity: 0.85 }}/>

                  {/* Main content */}
                  <div style={{ padding: '12px 14px 12px 12px', minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                      {l.pesado ? (
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 3,
                          fontSize: 9.5, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase',
                          color: 'var(--color-success)',
                        }}>
                          <span style={{
                            width: 12, height: 12, borderRadius: 99,
                            background: 'var(--color-success)',
                            display: 'grid', placeItems: 'center',
                          }}>
                            <Icon name="check" size={8} color="white" stroke={3}/>
                          </span>
                          Pesado
                        </span>
                      ) : (
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 3,
                          fontSize: 9.5, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase',
                          color: 'var(--color-warning-soft-fg)',
                        }}>
                          <span style={{
                            width: 12, height: 12, borderRadius: 99,
                            border: '1.5px dashed var(--color-warning)',
                          }}/>
                          Por pesar
                        </span>
                      )}
                      {l.pendingCajas > 0 && (
                        <span style={{
                          fontSize: 9.5, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase',
                          color: 'var(--color-danger)',
                          padding: '1px 6px', borderRadius: 4,
                          background: 'var(--color-danger-soft)',
                        }}>
                          −{l.pendingCajas} cajas
                        </span>
                      )}
                    </div>

                    <div style={{
                      fontSize: 14, fontWeight: 600, letterSpacing: '-0.01em',
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      lineHeight: 1.25,
                    }}>
                      {l.nombre}
                    </div>

                    <div style={{
                      fontSize: 11, color: 'var(--color-text-subtle)', marginTop: 3,
                      fontVariantNumeric: 'tabular-nums', display: 'flex', gap: 8,
                    }}>
                      <span>{l.cajasPedidas} {l.cajasPedidas === 1 ? 'caja' : 'cajas'}</span>
                      <span>·</span>
                      <span>{formatXCG(l.precio)}/kg</span>
                    </div>
                  </div>

                  {/* Weight + subtotal — the hero numbers */}
                  <div style={{
                    padding: '12px 14px 12px 8px',
                    display: 'flex', flexDirection: 'column', alignItems: 'flex-end',
                    justifyContent: 'center',
                    borderLeft: '1px solid var(--color-border-subtle)',
                    minWidth: 92,
                  }}>
                    <div style={{
                      fontSize: 16, fontWeight: 700, fontVariantNumeric: 'tabular-nums',
                      letterSpacing: '-0.02em', lineHeight: 1,
                      color: l.pesado ? 'var(--color-text)' : 'var(--color-text-muted)',
                    }}>
                      {l.peso.toFixed(1)}
                      <small style={{ fontSize: 10, color: 'var(--color-text-subtle)', fontWeight: 600, marginLeft: 2, letterSpacing: 0 }}>kg</small>
                    </div>
                    <div style={{
                      fontSize: 11, fontWeight: 600, fontVariantNumeric: 'tabular-nums',
                      color: 'var(--color-text-subtle)', marginTop: 4,
                    }}>
                      {formatXCG(l.subtotal)} <small style={{ fontSize: 9, fontWeight: 600 }}>XCG</small>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="gcard" style={{ padding: 16, marginTop: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 8 }}>
                <span style={{ color: 'var(--color-text-muted)' }}>Subtotal</span>
                <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>{formatXCG(p.total * 0.94)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 8 }}>
                <span style={{ color: 'var(--color-text-muted)' }}>Impuestos (6%)</span>
                <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>{formatXCG(p.total * 0.06)}</span>
              </div>
              <div style={{ height: 1, background: 'var(--color-border-subtle)', margin: '10px 0' }}/>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span style={{ fontSize: 13, fontWeight: 700 }}>Total</span>
                <span style={{ fontSize: 22, fontWeight: 700, fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em', color: 'var(--indigo-500)' }}>
                  {formatXCG(p.total)}
                  <small style={{ fontSize: 11, color: 'var(--color-text-subtle)', fontWeight: 600, marginLeft: 4 }}>XCG</small>
                </span>
              </div>
            </div>
          </>
        )}

        {tab === 'detalles' && (
          <div className="gcard" style={{ padding: 0 }}>
            {[
              { k: 'Folio', v: p.id },
              { k: 'Cliente', v: p.cliente },
              { k: 'Vendedor', v: p.vendedor || d.vendedor },
              { k: 'Ruta', v: p.ruta || 'Ruta sur' },
              { k: 'Forma de pago', v: p.pago || 'Crédito 30 días' },
              { k: 'Notas', v: p.notas || 'Entregar en muelle norte, horario 7–11am' },
            ].map((row, i, arr) => (
              <div key={i} style={{
                padding: '14px 16px',
                borderBottom: i < arr.length - 1 ? '1px solid var(--color-border-subtle)' : 'none',
              }}>
                <div style={{ fontSize: 10.5, color: 'var(--color-text-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, marginBottom: 4 }}>{row.k}</div>
                <div style={{ fontSize: 13.5, color: 'var(--color-text)' }}>{row.v}</div>
              </div>
            ))}
          </div>
        )}

        {tab === 'historial' && (
          <div className="gcard" style={{ padding: '14px 16px' }}>
            {[
              { t: 'Pedido creado', d: p.creado + ' · 07:42', u: d.vendedor },
              { t: 'Preparación iniciada', d: p.creado + ' · 09:15', u: 'Almacén' },
              p.estado !== 'pendiente' && { t: 'Cajas preparadas', d: p.creado + ' · 11:08', u: 'Almacén' },
              p.estado === 'facturado' && { t: 'Facturado', d: p.creado + ' · 14:22', u: 'Facturación' },
            ].filter(Boolean).map((ev, i, arr) => (
              <div key={i} style={{ display: 'grid', gridTemplateColumns: '20px 1fr', gap: 12, paddingBottom: i < arr.length - 1 ? 14 : 0 }}>
                <div style={{ position: 'relative' }}>
                  <div style={{ width: 10, height: 10, borderRadius: 99, background: 'linear-gradient(135deg, var(--indigo-500), var(--violet-500))', marginTop: 4, marginLeft: 5 }}/>
                  {i < arr.length - 1 && <div style={{ position: 'absolute', left: 9, top: 16, bottom: -14, width: 2, background: 'var(--color-border)' }}/>}
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{ev.t}</div>
                  <div style={{ fontSize: 11, color: 'var(--color-text-subtle)', marginTop: 2, fontVariantNumeric: 'tabular-nums' }}>{ev.d} · {ev.u}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        <div style={{ height: 20 }}/>
      </div>

      {/* Bottom action bar */}
      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0,
        padding: '12px 16px calc(12px + env(safe-area-inset-bottom))',
        background: 'var(--color-surface-strong)',
        backdropFilter: 'blur(24px) saturate(1.8)',
        WebkitBackdropFilter: 'blur(24px) saturate(1.8)',
        borderTop: '1px solid var(--color-border)',
        display: 'flex', gap: 10, zIndex: 10
      }}>
        <button style={{
          flex: '0 0 auto', padding: '0 16px', height: 48, borderRadius: 14,
          background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)',
          fontSize: 13, fontWeight: 600, color: 'var(--color-text)', cursor: 'pointer',
          fontFamily: 'inherit', letterSpacing: '-0.01em'
        }}>
          <Icon name="edit" size={16} style={{ verticalAlign: -3 }}/>
        </button>
        <button style={{
          flex: 1, height: 48, borderRadius: 14, border: 'none',
          background: 'linear-gradient(135deg, var(--indigo-500) 0%, var(--violet-500) 100%)',
          color: 'white', fontSize: 14, fontWeight: 600, cursor: 'pointer',
          boxShadow: '0 8px 24px -6px var(--color-shadow-accent), inset 0 1px 0 rgba(255,255,255,0.25)',
          fontFamily: 'inherit', letterSpacing: '-0.01em'
        }}>
          {p.estado === 'pendiente' ? 'Marcar como preparado' : p.estado === 'preparado' ? 'Facturar pedido' : 'Ver factura'}
        </button>
      </div>
    </>
  );
};

window.PedidoDetail = PedidoDetail;
