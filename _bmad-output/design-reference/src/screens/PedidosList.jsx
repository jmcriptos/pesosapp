// Screen: Pedidos list
const PedidosList = ({ onBack, onOpen }) => {
  const d = window.PESOS_DATA;
  const [filter, setFilter] = React.useState('todos');
  const [query, setQuery] = React.useState('');

  const counts = {
    todos: d.pedidos.length,
    pendientes: d.pedidos.filter(p => p.estado === 'pendiente').length,
    preparados: d.pedidos.filter(p => p.estado === 'preparado').length,
    facturados: d.pedidos.filter(p => p.estado === 'facturado').length,
  };

  const filtered = d.pedidos.filter(p => {
    if (filter !== 'todos' && !p.estado.startsWith(filter.slice(0, -1))) return false;
    if (query && !(`${p.cliente} ${p.id}`.toLowerCase().includes(query.toLowerCase()))) return false;
    return true;
  });

  const stateCfg = {
    pendiente: { label: 'Pendiente', cls: 'badge-warning', icon: 'clock' },
    preparado: { label: 'Preparado', cls: 'badge-success', icon: 'package' },
    facturado: { label: 'Facturado', cls: 'badge-info', icon: 'check' },
    vencido:   { label: 'Vencido',   cls: 'badge-danger',  icon: 'alert' },
  };

  // Group by day
  const groups = {};
  filtered.forEach(p => { (groups[p.creado] ||= []).push(p); });

  return (
    <>
      <StatusBar/>
      <div className="nav-bar">
        <div className="nav-pill-cluster">
          <button className="nav-pill" onClick={onBack} aria-label="Atrás">
            <Icon name="chevron-left" size={20}/>
          </button>
        </div>
        <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-0.01em' }}>Pedidos</div>
        <div className="nav-pill-cluster">
          <div className="nav-pill"><Icon name="filter" size={17}/></div>
          <div className="nav-pill" style={{ width: 44, background: 'linear-gradient(135deg, var(--indigo-500), var(--violet-500))', color: 'white', boxShadow: '0 8px 20px -6px var(--color-shadow-accent)' }}><Icon name="plus" size={18}/></div>
        </div>
      </div>

      <div className="screen-body" style={{ paddingTop: 12 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px',
          background: 'var(--color-surface)', backdropFilter: 'blur(20px) saturate(1.8)',
          WebkitBackdropFilter: 'blur(20px) saturate(1.8)',
          border: '1px solid var(--color-border)', borderRadius: 14,
          boxShadow: 'var(--shadow-sm)'
        }}>
          <Icon name="search" size={16} className="muted"/>
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Buscar por cliente o folio"
            style={{
              flex: 1, border: 'none', outline: 'none', background: 'transparent',
              fontSize: 14, color: 'var(--color-text)', fontFamily: 'inherit'
            }}
          />
          {query && <button onClick={() => setQuery('')} style={{ border: 'none', background: 'rgba(15,23,42,0.06)', borderRadius: 99, width: 20, height: 20, display: 'grid', placeItems: 'center', cursor: 'pointer', color: 'var(--color-text-muted)' }}><Icon name="x" size={12}/></button>}
        </div>

        <div className="segmented" style={{ marginTop: 12 }}>
          {[
            { id: 'todos', label: 'Todos' },
            { id: 'pendientes', label: 'Pendientes' },
            { id: 'preparados', label: 'Preparados' },
            { id: 'facturados', label: 'Facturados' },
          ].map(t => (
            <button key={t.id} className={filter === t.id ? 'active' : ''} onClick={() => setFilter(t.id)}>
              {t.label} <span style={{ fontVariantNumeric: 'tabular-nums', opacity: 0.7, marginLeft: 2 }}>{counts[t.id]}</span>
            </button>
          ))}
        </div>

        {Object.entries(groups).map(([day, items]) => {
          const total = items.reduce((a, p) => a + p.total, 0);
          return (
            <div key={day}>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                padding: '16px 4px 8px', fontSize: 11, textTransform: 'uppercase',
                letterSpacing: '0.06em', color: 'var(--color-text-subtle)', fontWeight: 700
              }}>
                <span>{day}</span>
                <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {items.length} ped · {formatXCG(total)} XCG
                </span>
              </div>
              <div className="gcard" style={{ padding: '4px 0' }}>
                {items.map((p, idx) => {
                  const cfg = stateCfg[p.vencido ? 'vencido' : p.estado];
                  return (
                    <div key={p.id}
                         onClick={() => onOpen(p.id)}
                         style={{
                           display: 'grid',
                           gridTemplateColumns: '1fr auto',
                           gap: 12,
                           padding: '14px 16px',
                           borderBottom: idx < items.length - 1 ? '1px solid var(--color-border-subtle)' : 'none',
                           cursor: 'pointer',
                           alignItems: 'center'
                         }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                          <span className={`badge ${cfg.cls}`}>
                            <Icon name={cfg.icon} size={10}/>
                            {cfg.label}
                          </span>
                          {p.vencido && <span style={{ fontSize: 10.5, color: 'var(--color-danger)', fontWeight: 700, letterSpacing: '-0.01em' }}>● Vencido</span>}
                        </div>
                        <div style={{ fontSize: 14.5, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', letterSpacing: '-0.01em' }}>
                          {p.cliente}
                        </div>
                        <div style={{ fontSize: 11.5, color: 'var(--color-text-subtle)', marginTop: 4, fontVariantNumeric: 'tabular-nums', display: 'flex', gap: 10 }}>
                          <span>{p.id}</span>
                          <span>·</span>
                          <span>{p.cajas} cajas</span>
                          <span>·</span>
                          <span>{p.peso.toLocaleString('es-ES')} kg</span>
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: 15, fontWeight: 700, fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.01em' }}>
                          {formatXCG(p.total)}
                          <small style={{ fontSize: 9.5, color: 'var(--color-text-subtle)', marginLeft: 3, fontWeight: 600 }}>XCG</small>
                        </div>
                        <Icon name="chevron-right" size={14} className="muted" style={{ display: 'inline-block', marginTop: 4 }}/>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}

        {filtered.length === 0 && (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--color-text-muted)' }}>
            <div style={{ fontSize: 40, marginBottom: 8, opacity: 0.3 }}>∅</div>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Sin resultados</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>Ajusta los filtros o la búsqueda</div>
          </div>
        )}
      </div>

      <TabBar active="pedidos" onChange={(t) => t === 'home' && onBack?.()}/>
    </>
  );
};

window.PedidosList = PedidosList;
