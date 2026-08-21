const NAV = [
  { id: 'dashboard', label: 'Dashboard', hint: 'Evaluate & audit' },
  { id: 'policies', label: 'Policy builder', hint: 'Author & manage' },
];

export default function Sidebar({ view, onNavigate, apiOnline }) {
  return (
    <nav className="sidebar">
      <div className="sidebar__brand">
        <div className="sidebar__mark">PA</div>
        <div>
          <div className="sidebar__title">Policy Agent</div>
          <div className="sidebar__subtitle">Approval Engine</div>
        </div>
      </div>

      <ul className="sidebar__nav">
        {NAV.map((item) => (
          <li key={item.id}>
            <button
              className={`sidebar__link ${view === item.id ? 'is-active' : ''}`}
              onClick={() => onNavigate(item.id)}
            >
              <span>{item.label}</span>
              <span className="sidebar__hint">{item.hint}</span>
            </button>
          </li>
        ))}
      </ul>

      <div className="sidebar__footer">
        <span className={`status-dot ${apiOnline ? 'is-online' : 'is-offline'}`} />
        {apiOnline ? 'API connected' : 'API unreachable'}
      </div>
    </nav>
  );
}
