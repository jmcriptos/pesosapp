// Shared UI primitives for the PesosApp prototype
// Exports: Icon, PhoneFrame, StatusBar, ProgressRing, Sparkline, TabBar, formatXCG

const formatXCG = (n) => Math.round(n).toLocaleString('es-ES');

// ─────────────────────────────────────────────────────────────
// Icon library — minimal line icons sized 22
// ─────────────────────────────────────────────────────────────
const Icon = ({ name, size = 22, color = 'currentColor', stroke = 1.8 }) => {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: color, strokeWidth: stroke, strokeLinecap: 'round', strokeLinejoin: 'round' };
  switch (name) {
    case 'home': return <svg {...common}><path d="M3 11l9-7 9 7v10a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/></svg>;
    case 'clipboard': return <svg {...common}><rect x="6" y="4" width="12" height="16" rx="2"/><path d="M9 4v2h6V4M9 10h6M9 14h6M9 18h3"/></svg>;
    case 'chart': return <svg {...common}><path d="M4 19V5M4 19h16M8 16v-6M12 16V8M16 16v-9M20 16v-4"/></svg>;
    case 'users': return <svg {...common}><circle cx="9" cy="8" r="3.5"/><circle cx="17" cy="9" r="2.5"/><path d="M3 20c0-3 3-5 6-5s6 2 6 5M15 20c0-2.5 2-4 4-4"/></svg>;
    case 'package': return <svg {...common}><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5L12 12l8-4.5M12 12v9"/></svg>;
    case 'search': return <svg {...common}><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4-4"/></svg>;
    case 'filter': return <svg {...common}><path d="M3 5h18M6 12h12M10 19h4"/></svg>;
    case 'plus': return <svg {...common}><path d="M12 5v14M5 12h14"/></svg>;
    case 'check': return <svg {...common}><path d="M5 12l5 5L20 7"/></svg>;
    case 'chevron-left': return <svg {...common}><path d="M15 6l-6 6 6 6"/></svg>;
    case 'chevron-right': return <svg {...common}><path d="M9 6l6 6-6 6"/></svg>;
    case 'chevron-down': return <svg {...common}><path d="M6 9l6 6 6-6"/></svg>;
    case 'dots': return <svg {...common}><circle cx="6" cy="12" r="1.2" fill={color} stroke="none"/><circle cx="12" cy="12" r="1.2" fill={color} stroke="none"/><circle cx="18" cy="12" r="1.2" fill={color} stroke="none"/></svg>;
    case 'bell': return <svg {...common}><path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>;
    case 'scan': return <svg {...common}><path d="M4 8V5a1 1 0 0 1 1-1h3M20 8V5a1 1 0 0 0-1-1h-3M4 16v3a1 1 0 0 0 1 1h3M20 16v3a1 1 0 0 1-1 1h-3M7 12h10"/></svg>;
    case 'weight': return <svg {...common}><path d="M5 8h14l-1 12H6z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/></svg>;
    case 'truck': return <svg {...common}><rect x="2" y="7" width="12" height="9" rx="1"/><path d="M14 10h4l3 3v3h-7z"/><circle cx="6" cy="18" r="2"/><circle cx="17" cy="18" r="2"/></svg>;
    case 'clock': return <svg {...common}><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></svg>;
    case 'calendar': return <svg {...common}><rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/></svg>;
    case 'map-pin': return <svg {...common}><path d="M12 22s7-7.5 7-13a7 7 0 1 0-14 0c0 5.5 7 13 7 13z"/><circle cx="12" cy="9" r="2.5"/></svg>;
    case 'user': return <svg {...common}><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 4-6 8-6s8 2 8 6"/></svg>;
    case 'sparkle': return <svg {...common}><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/></svg>;
    case 'arrow-up-right': return <svg {...common}><path d="M7 17L17 7M9 7h8v8"/></svg>;
    case 'arrow-up': return <svg {...common}><path d="M12 19V5M6 11l6-6 6 6"/></svg>;
    case 'arrow-down': return <svg {...common}><path d="M12 5v14M18 13l-6 6-6-6"/></svg>;
    case 'settings': return <svg {...common}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>;
    case 'wand': return <svg {...common}><path d="M15 4v2M19 4v2M17 2v2M21 2v2M13 7L4 16l4 4 9-9M13 7l4 4"/></svg>;
    case 'printer': return <svg {...common}><path d="M6 9V4h12v5M6 18H4v-6h16v6h-2M8 14h8v6H8z"/></svg>;
    case 'qr': return <svg {...common}><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3M17 21v-3M21 14v3M14 21h3"/></svg>;
    case 'layers': return <svg {...common}><path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5M3 18l9 5 9-5"/></svg>;
    case 'eye': return <svg {...common}><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>;
    case 'x': return <svg {...common}><path d="M6 6l12 12M18 6L6 18"/></svg>;
    case 'edit': return <svg {...common}><path d="M4 20h4L20 8l-4-4L4 16v4z"/><path d="M14 6l4 4"/></svg>;
    case 'more': return <svg {...common}><circle cx="12" cy="6" r="1.3" fill={color} stroke="none"/><circle cx="12" cy="12" r="1.3" fill={color} stroke="none"/><circle cx="12" cy="18" r="1.3" fill={color} stroke="none"/></svg>;
    case 'alert': return <svg {...common}><path d="M12 4L2 20h20z"/><path d="M12 10v4M12 17v.5"/></svg>;
    case 'sun': return <svg {...common}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>;
    case 'moon': return <svg {...common}><path d="M20 14a8 8 0 0 1-10.5-10 8 8 0 1 0 10.5 10z"/></svg>;
    default: return null;
  }
};

// ─────────────────────────────────────────────────────────────
// Phone frame
// ─────────────────────────────────────────────────────────────
const PhoneFrame = ({ label, children, dark = false }) => (
  <div className="phone-wrap">
    <div className="phone-label">
      <span className="phone-label-dot" />
      {label}
    </div>
    <div className={`phone ${dark ? 'dark' : ''}`}>
      <div className="phone-island" />
      <div className="phone-inner">
        {children}
      </div>
      <div className={`phone-home ${dark ? 'dark' : ''}`} />
    </div>
  </div>
);

// ─────────────────────────────────────────────────────────────
// Status bar
// ─────────────────────────────────────────────────────────────
const StatusBar = () => (
  <div className="status-bar">
    <span style={{ fontVariantNumeric: 'tabular-nums' }}>9:41</span>
    <span className="sb-icons">
      <svg width="17" height="11" viewBox="0 0 17 11">
        <rect x="0" y="7" width="3" height="4" rx="0.6" fill="currentColor"/>
        <rect x="4.5" y="5" width="3" height="6" rx="0.6" fill="currentColor"/>
        <rect x="9" y="2.5" width="3" height="8.5" rx="0.6" fill="currentColor"/>
        <rect x="13.5" y="0" width="3" height="11" rx="0.6" fill="currentColor"/>
      </svg>
      <svg width="15" height="11" viewBox="0 0 15 11" style={{ marginLeft: 2 }}>
        <path d="M7.5 3C9.4 3 11.1 3.7 12.5 5L13.4 4C11.8 2.4 9.8 1.5 7.5 1.5C5.2 1.5 3.2 2.4 1.6 4L2.5 5C3.9 3.7 5.6 3 7.5 3Z" fill="currentColor"/>
        <path d="M7.5 6C8.7 6 9.7 6.4 10.5 7.2L11.4 6.3C10.3 5.3 9 4.6 7.5 4.6C6 4.6 4.7 5.3 3.6 6.3L4.5 7.2C5.3 6.4 6.3 6 7.5 6Z" fill="currentColor"/>
        <circle cx="7.5" cy="9" r="1.3" fill="currentColor"/>
      </svg>
      <svg width="25" height="12" viewBox="0 0 25 12" style={{ marginLeft: 3 }}>
        <rect x="0.5" y="0.5" width="21" height="11" rx="3" stroke="currentColor" strokeOpacity="0.35" fill="none"/>
        <rect x="2" y="2" width="18" height="8" rx="1.5" fill="currentColor"/>
        <path d="M23 4v4c.7-.2 1.3-.9 1.3-2s-.6-1.8-1.3-2z" fill="currentColor" fillOpacity="0.4"/>
      </svg>
    </span>
  </div>
);

// ─────────────────────────────────────────────────────────────
// Progress ring — SVG, 44px
// ─────────────────────────────────────────────────────────────
const ProgressRing = ({ pct = 0, size = 44, stroke = 4, state = 'neutral', label }) => {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (Math.min(100, Math.max(0, pct)) / 100) * c;
  const colorVar = {
    success: 'var(--color-success)',
    warning: 'var(--color-warning)',
    danger: 'var(--color-danger)',
    neutral: 'var(--color-primary)',
  }[state];
  return (
    <div className="ring-wrap" style={{ width: size, height: size, '--ring-color': colorVar }}>
      <svg width={size} height={size}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(99,102,241,0.15)" strokeWidth={stroke} />
        <circle
          cx={size/2} cy={size/2} r={r}
          fill="none" stroke={colorVar}
          strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={offset}
          style={{
            transform: 'rotate(-90deg)',
            transformOrigin: '50% 50%',
            transition: 'stroke-dashoffset 480ms cubic-bezier(0.25, 1, 0.5, 1)',
          }}
        />
      </svg>
      <div className="ring-label">{label ?? `${Math.round(pct)}%`}</div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// Sparkline — smooth path + gradient fill + dot
// ─────────────────────────────────────────────────────────────
const Sparkline = ({ data, height = 110, color = 'var(--color-primary)', fill = 'url(#spark-grad)' }) => {
  const w = 100, h = 100;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => [
    (i / (data.length - 1)) * w,
    h - ((v - min) / range) * h * 0.85 - h * 0.08,
  ]);
  // smooth with catmull-rom → cubic
  const path = pts.reduce((acc, [x, y], i, arr) => {
    if (i === 0) return `M ${x} ${y}`;
    const [px, py] = arr[i-1];
    const cx1 = px + (x - px) / 2;
    const cy1 = py;
    const cx2 = px + (x - px) / 2;
    const cy2 = y;
    return `${acc} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x} ${y}`;
  }, '');
  const area = `${path} L ${w} ${h} L 0 ${h} Z`;
  const lastPt = pts[pts.length - 1];
  return (
    <svg className="chart-svg" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ height }}>
      <defs>
        <linearGradient id="spark-grad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>
      <path d={area} fill={fill}/>
      <path d={path} fill="none" stroke={color} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke"/>
      <circle cx={lastPt[0]} cy={lastPt[1]} r="2.5" fill={color}/>
      <circle cx={lastPt[0]} cy={lastPt[1]} r="4" fill={color} opacity="0.22"/>
    </svg>
  );
};

// ─────────────────────────────────────────────────────────────
// Tab bar (bottom)
// ─────────────────────────────────────────────────────────────
const TabBar = ({ active, onChange }) => {
  const tabs = [
    { id: 'home', label: 'Inicio', icon: 'home' },
    { id: 'pedidos', label: 'Pedidos', icon: 'clipboard' },
    { id: 'nuevo', label: 'Nuevo', icon: 'plus' },
    { id: 'clientes', label: 'Clientes', icon: 'users' },
    { id: 'mas', label: 'Más', icon: 'dots' },
  ];
  return (
    <div className="tabbar">
      {tabs.map(t => (
        <button
          key={t.id}
          className={`tab ${active === t.id ? 'active' : ''}`}
          onClick={() => onChange?.(t.id)}
        >
          <div className="tab-icon-wrap">
            <Icon name={t.icon} size={20} />
          </div>
          <span>{t.label}</span>
        </button>
      ))}
    </div>
  );
};

Object.assign(window, {
  Icon, PhoneFrame, StatusBar, ProgressRing, Sparkline, TabBar, formatXCG,
});
