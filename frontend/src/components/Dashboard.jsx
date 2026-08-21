import { useMemo } from 'react';
import StatusBadge from './StatusBadge';

export default function Dashboard({ results, activePolicy, loading, error, onRun, onSelectClaim }) {
  const stats = useMemo(() => {
    const base = { total: results.length, APPROVE: 0, REJECT: 0, ESCALATE: 0, review: 0 };
    for (const r of results) {
      base[r.decision] = (base[r.decision] || 0) + 1;
      if (r.requires_review) base.review += 1;
    }
    return base;
  }, [results]);

  return (
    <div className="dashboard">
      <div className="page-header">
        <div>
          <h1>Claims dashboard</h1>
          <p className="page-sub">
            {activePolicy
              ? <>Evaluating against <strong>{activePolicy.name}</strong> — {activePolicy.rules.length} rule(s), fully deterministic.</>
              : 'No policy selected yet. Build one to evaluate claims.'}
          </p>
        </div>
        <button className="btn btn--primary" onClick={onRun} disabled={loading || !activePolicy}>
          {loading ? 'Evaluating…' : 'Re-run evaluation'}
        </button>
      </div>

      {error && <div className="alert alert--error">{error}</div>}

      <div className="stat-row">
        <StatCard label="Total claims" value={stats.total} />
        <StatCard label="Approved" value={stats.APPROVE} tone="approve" />
        <StatCard label="Rejected" value={stats.REJECT} tone="reject" />
        <StatCard label="Escalated" value={stats.ESCALATE} tone="escalate" />
        <StatCard label="Needs review" value={stats.review} tone="neutral" />
      </div>

      <div className="panel panel--table">
        <div className="panel__title-row">
          <span className="eyebrow">Claims</span>
          <span className="page-sub" style={{ margin: 0 }}>Click a row to inspect the evaluation trace</span>
        </div>

        {results.length === 0 && !loading && (
          <div className="empty-state">
            <p>{activePolicy ? 'No results yet — run the evaluation.' : 'Create and save a policy first, then run it here.'}</p>
          </div>
        )}

        {results.length > 0 && (
          <table className="data-table data-table--clickable">
            <thead>
              <tr>
                <th>Claim ID</th>
                <th>Employee</th>
                <th>Department</th>
                <th>Amount</th>
                <th>Category</th>
                <th>Decision</th>
                <th>Rule</th>
                <th>Review</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.claim_id} onClick={() => onSelectClaim(r.claim_id)}>
                  <td className="mono">{r.claim_id}</td>
                  <td>{r.claim.employee}</td>
                  <td>{r.claim.department || <span className="muted">missing</span>}</td>
                  <td className="mono">{r.claim.amount != null ? `$${r.claim.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : <span className="muted">missing</span>}</td>
                  <td>{r.claim.category || '—'}</td>
                  <td><StatusBadge decision={r.decision} /></td>
                  <td className="mono">{r.winning_rule_id || (r.matched_rules.length ? r.matched_rules.join(', ') : 'default')}</td>
                  <td>{r.requires_review ? <span className="tag tag--review">Review</span> : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, tone = 'default' }) {
  return (
    <div className={`stat-card stat-card--${tone}`}>
      <span className="stat-card__value mono">{value}</span>
      <span className="stat-card__label">{label}</span>
    </div>
  );
}
