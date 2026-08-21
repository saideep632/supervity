import { useState } from 'react';
import { api } from '../api';

const EXAMPLE = `Auto-approve expenses under $500 for Sales.
Escalate expenses above $2000.
Reject expenses containing prohibited categories.`;

export default function PolicyBuilder({ policies, onPolicyCreated, onActivate }) {
  const [name, setName] = useState('Standard Expense Policy');
  const [text, setText] = useState(EXAMPLE);
  const [draft, setDraft] = useState(null);
  const [parserUsed, setParserUsed] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  async function handleParse() {
    setLoading(true);
    setError(null);
    setSaved(false);
    try {
      const res = await api.parsePolicy(name, text);
      setDraft(res.policy_draft);
      setParserUsed(res.parser_used);
      setWarnings(res.warnings || []);
    } catch (e) {
      setError(e.message);
      setDraft(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    if (!draft) return;
    setLoading(true);
    setError(null);
    try {
      const policy = await api.createPolicy(draft);
      setSaved(true);
      onPolicyCreated(policy);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="policy-builder">
      <div className="page-header">
        <div>
          <h1>Policy builder</h1>
          <p className="page-sub">
            Business users write the policy in plain English. The system converts it into structured,
            validated rules. The deterministic engine — never the language model — makes every final decision.
          </p>
        </div>
      </div>

      <div className="builder-grid">
        <div className="panel">
          <label className="field-label" htmlFor="policy-name">Policy name</label>
          <input
            id="policy-name"
            className="text-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />

          <label className="field-label" htmlFor="policy-text">Policy, in plain English</label>
          <textarea
            id="policy-text"
            className="textarea"
            rows={8}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="e.g. Auto-approve expenses under $500 for Sales..."
          />

          <div className="builder-actions">
            <button className="btn btn--primary" onClick={handleParse} disabled={loading || !text.trim()}>
              {loading && !draft ? 'Parsing…' : 'Parse policy'}
            </button>
            {draft && (
              <button className="btn btn--secondary" onClick={handleSave} disabled={loading}>
                {saved ? 'Saved ✓' : 'Save & activate'}
              </button>
            )}
          </div>

          {error && <div className="alert alert--error">{error}</div>}
          {warnings.map((w, i) => (
            <div className="alert alert--warning" key={i}>{w}</div>
          ))}
          {saved && (
            <div className="alert alert--success">
              Policy saved. Head to the dashboard to run it against sample claims.
            </div>
          )}
        </div>

        <div className="panel panel--structured">
          <div className="panel__title-row">
            <span className="eyebrow">Structured policy (JSON)</span>
            {parserUsed && (
              <span className={`parser-tag parser-tag--${parserUsed}`}>
                {parserUsed === 'llm' ? 'LLM parser' : 'Heuristic fallback parser'}
              </span>
            )}
          </div>

          {!draft && (
            <div className="empty-state">
              <p>Parse a policy to see the structured rules the engine will actually run.</p>
            </div>
          )}

          {draft && (
            <div className="rule-cards">
              {draft.rules
                .slice()
                .sort((a, b) => a.priority - b.priority)
                .map((r) => (
                  <div className="rule-card" key={r.id}>
                    <div className="rule-card__head">
                      <span className="mono rule-card__id">{r.id}</span>
                      <span className="mono rule-card__priority">priority {r.priority}</span>
                      <span className={`rule-card__action rule-card__action--${r.action.toLowerCase()}`}>{r.action}</span>
                    </div>
                    {r.source_text && <p className="rule-card__source">“{r.source_text}”</p>}
                    <ul className="rule-card__conditions">
                      {r.conditions.map((c, i) => (
                        <li key={i} className="mono">
                          {c.field} {c.operator} {c.value !== undefined && c.value !== null ? JSON.stringify(c.value) : ''}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              <div className="rule-card rule-card--default">
                <span className="mono rule-card__id">DEFAULT</span>
                <span>No rule matches → <strong>{draft.default_action}</strong></span>
              </div>
            </div>
          )}
        </div>
      </div>

      {policies.length > 0 && (
        <div className="panel" style={{ marginTop: 20 }}>
          <span className="eyebrow">Saved policies</span>
          <table className="data-table" style={{ marginTop: 10 }}>
            <thead>
              <tr><th>Name</th><th>Rules</th><th>Status</th><th>Updated</th><th></th></tr>
            </thead>
            <tbody>
              {policies.map((p) => (
                <tr key={p.id}>
                  <td>{p.name}</td>
                  <td className="mono">{p.rules.length}</td>
                  <td>{p.active ? <span className="tag tag--active">Active</span> : <span className="tag">Inactive</span>}</td>
                  <td className="mono">{new Date(p.updated_at).toLocaleDateString()}</td>
                  <td><button className="btn btn--ghost btn--sm" onClick={() => onActivate(p)}>Run this policy</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
