// Screen: Dashboard (Inicio)
const Dashboard = ({ onOpenPedidos, dark }) => {
  const [panel, setPanel] = React.useState('ventas');
  const d = window.PESOS_DATA;
  const k = d.kpis;
  const metaPct = Math.round((k.ventasMes / k.meta) * 100);
  const proyPct = Math.round((k.proyeccion / k.meta) * 100);
  const semanaPct = 18; // week-over-week delta

  return (
    <React.Fragment>
      <StatusBar/>
      <div className="nav-bar">
        <div className="nav-pill-cluster">
          <div className="nav-pill" style={{ width: 'auto', padding: '0 14px 0 6px', color: 'var(--color-text)', fontWeight: 700, fontSize: 13, letterSpacing: '-0.01em', gap: 8 }}>
            <span style={{
              width: 28, height: 28, borderRadius: 8,
              background: 'linear-gradient(135deg, var(--indigo-500) 0%, var(--violet-500) 100%)',
              display: 'grid', placeItems: 'center',
              color: 'white', fontSize: 13, fontWeight: 800,
              boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.3)'
            }}>P</span>
            Pesos
          </div>
        </div>
        <div className="nav-pill-cluster">
          <div className="nav-pill"><Icon name="search" size={18}/></div>
          <div className="nav-pill" style={{ position: 'relative' }}>
            <Icon name="bell" size={18}/>
            <span style={{
              position: 'absolute', top: 6, right: 6,
              width: 8, height: 8, borderRadius: 99,
              background: 'var(--color-danger)',
              border: '1.5px solid var(--color-bg-elevated)'
            }}/>
          </div>
        </div>
      </div>

      <div className="screen-body">
        <div className="hero">
          <div className="hero-kicker">Buenos días, {d.vendedor.split(' ')[0]} ☀</div>
          <h1 className="hero-title">Tu semana va bien.</h1>
          <div className="hero-sub">{d.fecha} · {k.pendientes} pedidos requieren atención</div>
        </div>

        <div className="segmented">
          {[
            { id: 'ventas', label: 'Ventas' },
            { id: 'servicio', label: 'Servicio' },
            { id: 'top', label: 'Top' },
            { id: 'actividad', label: 'Actividad' },
          ].map(t => (
            <button key={t.id} className={panel === t.id ? 'active' : ''} onClick={() => setPanel(t.id)}>{t.label}</button>
          ))}
        </div>

        {panel === 'ventas' && (
          <>
            <div className="kpi-grid">
              <div className="kpi">
                <div className="kpi-top">
                  <div className="kpi-label">Ventas del Mes</div>
                  <ProgressRing pct={metaPct} state={metaPct >= 85 ? 'success' : metaPct >= 70 ? 'warning' : 'danger'} />
                </div>
                <div className="kpi-value">{formatXCG(k.ventasMes)}<small>{d.currency}</small></div>
                <div className="kpi-sub">Meta {formatXCG(k.meta)} · {k.pedidosMes} ped</div>
              </div>

              <div className="kpi">
                <div className="kpi-top">
                  <div className="kpi-label">Proyección</div>
                  <ProgressRing pct={proyPct} state={proyPct >= 100 ? 'success' : proyPct >= 85 ? 'warning' : 'danger'} />
                </div>
                <div className="kpi-value">{formatXCG(k.proyeccion)}<small>{d.currency}</small></div>
                <div className="kpi-sub">{proyPct}% de meta mensual</div>
              </div>

              <div className="kpi">
                <div className="kpi-top">
                  <div className="kpi-label">On-Time Delivery</div>
                  <ProgressRing pct={k.otd} state={k.otd >= 95 ? 'success' : k.otd >= 85 ? 'warning' : 'danger'} />
                </div>
                <div className="kpi-value">{k.otd.toFixed(1)}%</div>
                <div className="kpi-sub">OFR {k.ofr.toFixed(0)}% · ≤2 días</div>
              </div>

              <div className="kpi">
                <div className="kpi-top">
                  <div className="kpi-label">Pendientes</div>
                  <ProgressRing pct={Math.max(0, 100 - k.pendientes * 15)} state={k.pendientes === 0 ? 'success' : k.pendientes <= 3 ? 'warning' : 'danger'} label={k.pendientes} />
                </div>
                <div className="kpi-value" style={{ fontSize: 28 }}>{k.pendientes}</div>
                <div className="kpi-sub">1 vencido · 5 por preparar</div>
              </div>
            </div>

            <div className="sec-head">
              <h3 className="sec-title">Tendencia · últimos 12 meses</h3>
              <a className="sec-action">Ver más <Icon name="chevron-right" size={14}/></a>
            </div>

            <div className="gcard chart-card">
              <div className="chart-head">
                <div>
                  <div className="chart-big">{formatXCG(k.semana)}<small>{d.currency} · esta semana</small></div>
                  <div className="chart-legend">
                    <span className="kpi-trend"><Icon name="arrow-up" size={10}/> +{semanaPct}%</span>
                    <span>vs. semana anterior</span>
                  </div>
                </div>
              </div>
              <Sparkline data={d.sparkline} height={100}/>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--color-text-subtle)', marginTop: 6, padding: '0 2px' }}>
                <span>may</span><span>jul</span><span>sep</span><span>nov</span><span>ene</span><span>abr</span>
              </div>
            </div>

            <div className="sec-head">
              <h3 className="sec-title">Esta semana</h3>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
              {[
                { label: 'Ventas', value: formatXCG(k.semana), unit: 'XCG' },
                { label: 'Pedidos', value: k.pedidosSemana, unit: '' },
                { label: 'Prom/día', value: k.promedioDia.toFixed(1), unit: '' },
              ].map((c, i) => (
                <div key={i} className="gcard" style={{ padding: '12px 10px', textAlign: 'center' }}>
                  <div className="kpi-label" style={{ fontSize: 9 }}>{c.label}</div>
                  <div style={{ fontSize: 16, fontWeight: 700, fontVariantNumeric: 'tabular-nums', marginTop: 4 }}>{c.value} {c.unit && <small style={{ fontSize: 10, color: 'var(--color-text-subtle)' }}>{c.unit}</small>}</div>
                </div>
              ))}
            </div>
          </>
        )}

        {panel === 'servicio' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {[
              { label: 'OTD', full: 'On-Time Delivery', val: k.otd, unit: '%', desc: 'Entregas ≤ 2 días', state: k.otd >= 95 ? 'success' : 'warning' },
              { label: 'OFR', full: 'Order Fill Rate', val: k.ofr, unit: '%', desc: 'Cajas entregadas vs pedidas', state: k.ofr >= 95 ? 'success' : 'warning' },
              { label: 'POR', full: 'Perfect Order Rate', val: k.perfectOrder, unit: '%', desc: 'Entregas perfectas', state: k.perfectOrder >= 95 ? 'success' : 'warning' },
              { label: 'CE',  full: 'Customer Engagement', val: k.customerEngagement, unit: '%', desc: 'Clientes activos del mes', state: k.customerEngagement >= 80 ? 'success' : 'warning' },
              { label: 'LT',  full: 'Lead Time', val: k.leadTime, unit: 'd', desc: 'Promedio de procesamiento', state: k.leadTime <= 2 ? 'success' : 'warning', pct: Math.max(0, 100 - k.leadTime * 20) },
              { label: 'PED', full: 'Pendientes', val: k.pendientes, unit: '', desc: 'Requieren atención', state: k.pendientes <= 3 ? 'warning' : 'danger', pct: Math.max(0, 100 - k.pendientes * 15) },
            ].map((c, i) => (
              <div key={i} className="kpi">
                <div className="kpi-top">
                  <div>
                    <div className="kpi-label">{c.label}</div>
                    <div style={{ fontSize: 9.5, color: 'var(--color-text-subtle)', marginTop: 2 }}>{c.full}</div>
                  </div>
                  <ProgressRing
                    pct={c.pct ?? c.val}
                    state={c.state}
                    label={`${c.val}${c.unit}`}
                  />
                </div>
                <div className="kpi-value" style={{ fontSize: 24 }}>
                  {typeof c.val === 'number' && c.unit === '%' ? c.val.toFixed(1) : c.val}
                  <small style={{ marginLeft: 2 }}>{c.unit}</small>
                </div>
                <div className="kpi-sub">{c.desc}</div>
              </div>
            ))}
          </div>
        )}

        {panel === 'top' && (
          <>
            <div className="sec-head" style={{ paddingTop: 0 }}>
              <h3 className="sec-title">Top Productos</h3>
              <a className="sec-action">Este mes <Icon name="chevron-down" size={14}/></a>
            </div>
            <div className="gcard">
              {(() => {
                const max = d.topProductos[0].ingresos;
                const colors = ['#f59e0b', '#6366f1', '#10b981', '#8b5cf6', '#f43f5e'];
                return d.topProductos.map((p, i) => (
                  <div className="rank" key={i}>
                    <span className="rank-pos" style={{ background: colors[i] }}>{i+1}</span>
                    <div className="rank-body">
                      <div className="rank-name">{p.nombre}</div>
                      <div className="rank-bar"><div className="rank-bar-fill" style={{ width: `${(p.ingresos/max)*100}%`, background: `linear-gradient(90deg, ${colors[i]}aa, ${colors[i]})` }}/></div>
                      <div style={{ fontSize: 10.5, color: 'var(--color-text-subtle)', marginTop: 4, display: 'flex', gap: 10 }}>
                        <span>{p.cajas} cajas</span>
                        <span>{p.peso.toLocaleString('es-ES')} kg</span>
                        <span>{p.pedidos} ped</span>
                      </div>
                    </div>
                    <div className="rank-amt">
                      {formatXCG(p.ingresos)}
                      <small>{d.currency}</small>
                    </div>
                  </div>
                ));
              })()}
            </div>

            <div className="sec-head">
              <h3 className="sec-title">Top Clientes</h3>
              <a className="sec-action">Este mes <Icon name="chevron-down" size={14}/></a>
            </div>
            <div className="gcard">
              {(() => {
                const max = d.topClientes[0].total;
                const colors = ['#f59e0b', '#6366f1', '#10b981', '#8b5cf6', '#f43f5e'];
                return d.topClientes.map((c, i) => (
                  <div className="rank" key={i}>
                    <span className="rank-pos" style={{ background: colors[i] }}>{i+1}</span>
                    <div className="rank-body">
                      <div className="rank-name">{c.nombre}</div>
                      <div className="rank-bar"><div className="rank-bar-fill" style={{ width: `${(c.total/max)*100}%`, background: `linear-gradient(90deg, ${colors[i]}aa, ${colors[i]})` }}/></div>
                      <div style={{ fontSize: 10.5, color: 'var(--color-text-subtle)', marginTop: 4, display: 'flex', gap: 10 }}>
                        <span>{c.pedidos} pedidos</span>
                        <span>Último {c.ultimo}</span>
                      </div>
                    </div>
                    <div className="rank-amt">
                      {formatXCG(c.total)}
                      <small>{d.currency}</small>
                    </div>
                  </div>
                ));
              })()}
            </div>
          </>
        )}

        {panel === 'actividad' && (
          <>
            <div className="sec-head" style={{ paddingTop: 0 }}>
              <h3 className="sec-title">Pedidos recientes</h3>
              <a className="sec-action" onClick={onOpenPedidos} style={{ cursor: 'pointer' }}>Ver todos <Icon name="chevron-right" size={14}/></a>
            </div>
            <div className="gcard" style={{ padding: '4px 0' }}>
              {d.pedidos.slice(0, 5).map(p => (
                <div key={p.id} className="rank" style={{ gridTemplateColumns: '36px 1fr auto', padding: '12px 14px' }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: 10,
                    background: p.estado === 'pendiente' ? 'var(--color-warning-soft)' : p.estado === 'preparado' ? 'var(--color-success-soft)' : 'var(--color-info-soft)',
                    color: p.estado === 'pendiente' ? 'var(--color-warning-soft-fg)' : p.estado === 'preparado' ? 'var(--color-success-soft-fg)' : 'var(--color-info-soft-fg)',
                    display: 'grid', placeItems: 'center',
                  }}>
                    <Icon name={p.estado === 'facturado' ? 'check' : p.estado === 'preparado' ? 'package' : 'clock'} size={18}/>
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13.5, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.cliente}</div>
                    <div style={{ fontSize: 11, color: 'var(--color-text-subtle)', marginTop: 2, fontVariantNumeric: 'tabular-nums' }}>{p.id} · {p.creado}</div>
                  </div>
                  <div className="rank-amt">
                    {formatXCG(p.total)}
                    <small>{d.currency}</small>
                  </div>
                </div>
              ))}
            </div>

            <div className="sec-head">
              <h3 className="sec-title">Estado de pedidos</h3>
              <span style={{ fontSize: 11, color: 'var(--color-text-subtle)' }}>Últimos 30 días</span>
            </div>
            <div className="gcard" style={{ padding: 16 }}>
              {[
                { label: 'Facturados', val: 98, pct: 69, color: 'var(--color-info)' },
                { label: 'Preparados', val: 24, pct: 17, color: 'var(--color-success)' },
                { label: 'Pendientes', val: 14, pct: 10, color: 'var(--color-warning)' },
                { label: 'Vencidos', val: 6, pct: 4, color: 'var(--color-danger)' },
              ].map((s, i) => (
                <div key={i} style={{ marginBottom: i < 3 ? 12 : 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                    <span style={{ fontWeight: 600 }}>{s.label}</span>
                    <span style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--color-text-muted)' }}>
                      <b style={{ color: 'var(--color-text)' }}>{s.val}</b> · {s.pct}%
                    </span>
                  </div>
                  <div style={{ height: 8, borderRadius: 99, background: 'rgba(15,23,42,0.06)', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${s.pct}%`, background: s.color, borderRadius: 99, transition: 'width 600ms cubic-bezier(0.25,1,0.5,1)' }}/>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <TabBar active="home" onChange={(t) => t === 'pedidos' && onOpenPedidos?.()}/>
    </React.Fragment>
  );
};

window.Dashboard = Dashboard;
