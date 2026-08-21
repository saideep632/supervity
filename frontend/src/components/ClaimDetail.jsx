import StatusBadge from './StatusBadge';
import RuleTraceLedger from './RuleTraceLedger';

export default function ClaimDetail({ claim, result, onClose }) {
  if (!claim || !result) return null;

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={`Claim ${claim.claim_id} detail`}>
        <div className="drawer__header">
          <div>
            <div className="eyebrow">Claim {claim.claim_id}</div>
            <h2>{claim.employee}</h2>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div className="drawer__body">
          <section className="drawer__facts">
            <div className="fact"><span>Department</span><strong>{claim.department || '—'}</strong></div>
            <div className="fact"><span>Amount</span><strong className="mono">{claim.amount != null ? `$${claim.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : '—'}</strong></div>
            <div className="fact"><span>Category</span><strong>{claim.category || '—'}</strong></div>
            <div className="fact"><span>Date</span><strong className="mono">{claim.date || '—'}</strong></div>
          </section>
          {claim.description && <p className="drawer__desc">{claim.description}</p>}

          <section className="decision-block">
            <div className="decision-block__top">
              <span className="eyebrow">Decision</span>
              <StatusBadge decision={result.decision} size="lg" />
            </div>
            {result.requires_review && (
              <div className="review-flag">Requires human review</div>
            )}
          </section>

          <section>
            <span className="eyebrow">Why</span>
            <p className="explanation">{result.explanation}</p>
            <p className="explanation-source">
              Generated from evaluation trace only — policy <span className="mono">{result.policy_id}</span>, no free-form claims.
            </p>
          </section>

          <section>
            <span className="eyebrow">Rules evaluated ({result.evaluation_trace.length})</span>
            <RuleTraceLedger result={result} />
          </section>
        </div>
      </aside>
    </div>
  );
}
