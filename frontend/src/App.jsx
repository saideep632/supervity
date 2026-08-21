import { useEffect, useState, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import Dashboard from './components/Dashboard';
import PolicyBuilder from './components/PolicyBuilder';
import ClaimDetail from './components/ClaimDetail';
import { api } from './api';
import './App.css';

export default function App() {
  const [view, setView] = useState('dashboard');
  const [apiOnline, setApiOnline] = useState(true);

  const [policies, setPolicies] = useState([]);
  const [activePolicy, setActivePolicy] = useState(null);
  const [claims, setClaims] = useState([]);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedClaimId, setSelectedClaimId] = useState(null);

  const refreshPolicies = useCallback(async () => {
    try {
      const list = await api.listPolicies();
      setPolicies(list);
      setApiOnline(true);
      return list;
    } catch (e) {
      setApiOnline(false);
      return [];
    }
  }, []);

  useEffect(() => {
    (async () => {
      const [claimList, policyList] = await Promise.all([
        api.listClaims().catch(() => { setApiOnline(false); return []; }),
        refreshPolicies(),
      ]);
      setClaims(claimList);
      const active = policyList.find((p) => p.active);
      if (active) {
        setActivePolicy(active);
        runEvaluation(active.id, claimList);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runEvaluation(policyId, claimList = claims) {
    setLoading(true);
    setError(null);
    try {
      const evalResults = await api.evaluateClaims(policyId);
      const claimMap = new Map((claimList.length ? claimList : claims).map((c) => [c.claim_id, c]));
      const merged = evalResults.map((r) => ({ ...r, claim: claimMap.get(r.claim_id) || {} }));
      setResults(merged);
      setApiOnline(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handlePolicyCreated(policy) {
    const list = await refreshPolicies();
    setActivePolicy(policy);
    setView('dashboard');
    await runEvaluation(policy.id);
  }

  async function handleActivatePolicy(policy) {
    setActivePolicy(policy);
    setView('dashboard');
    await runEvaluation(policy.id);
  }

  const selectedResult = results.find((r) => r.claim_id === selectedClaimId);

  return (
    <div className="app-shell">
      <Sidebar view={view} onNavigate={setView} apiOnline={apiOnline} />
      <main className="app-main">
        {view === 'dashboard' && (
          <Dashboard
            results={results}
            activePolicy={activePolicy}
            loading={loading}
            error={error}
            onRun={() => runEvaluation(activePolicy?.id)}
            onSelectClaim={setSelectedClaimId}
          />
        )}
        {view === 'policies' && (
          <PolicyBuilder
            policies={policies}
            onPolicyCreated={handlePolicyCreated}
            onActivate={handleActivatePolicy}
          />
        )}
      </main>
      {selectedResult && (
        <ClaimDetail
          claim={selectedResult.claim}
          result={selectedResult}
          onClose={() => setSelectedClaimId(null)}
        />
      )}
    </div>
  );
}
