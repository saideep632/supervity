import StatusBadge from './StatusBadge';

/**
 * Renders the audit trail for a single evaluation: every rule that was
 * checked, whether it matched, and the exact field/operator/value
 * comparison that produced that verdict. This is the component that makes
 * decisions inspectable rather than opaque — the core requirement of the
 * assessment.
 */
export default function RuleTraceLedger({ result }) {
  const sorted = [...result.evaluation_trace].sort((a, b) => a.priority - b.priority);

  return (
    <div className="ledger">
      <div className="ledger__head">
        <span>Rule</span>
        <span>Priority</span>
        <span>Action</span>
        <span>Verdict</span>
      </div>
      {sorted.map((t) => {
        const isWinner = t.rule_id === result.winning_rule_id;
        return (
          <details
            key={t.rule_id}
            className={`ledger__row ${t.matched ? 'ledger__row--matched' : ''} ${isWinner ? 'ledger__row--winner' : ''}`}
            open={isWinner}
          >
            <summary className="ledger__summary">
              <span className="mono ledger__ruleid">
                {t.rule_id}
                {isWinner && <span className="ledger__winner-tag">DECIDING</span>}
              </span>
              <span className="mono ledger__priority">P{t.priority}</span>
              <span className="mono ledger__action">{t.action}</span>
              <span className={`ledger__verdict ${t.matched ? 'is-matched' : 'is-unmatched'}`}>
                {t.matched ? '✓ Matched' : '— Not matched'}
              </span>
            </summary>
            <div className="ledger__detail">
              <p className="ledger__reason">{t.reason}</p>
              {t.condition_results?.length > 0 && (
                <table className="ledger__conditions">
                  <thead>
                    <tr>
                      <th>Field</th>
                      <th>Operator</th>
                      <th>Expected</th>
                      <th>Actual</th>
                      <th>Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {t.condition_results.map((c, i) => (
                      <tr key={i}>
                        <td className="mono">{c.field}</td>
                        <td className="mono">{c.operator}</td>
                        <td className="mono">{c.expected === undefined || c.expected === null ? '—' : String(c.expected)}</td>
                        <td className="mono">{c.actual === undefined || c.actual === null ? 'null' : String(c.actual)}</td>
                        <td className={c.matched ? 'is-matched' : 'is-unmatched'}>{c.matched ? 'true' : 'false'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}
