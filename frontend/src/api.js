const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* no json body */
    }
    const err = new Error(detail || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  health: () => request('/api/health'),

  parsePolicy: (name, text) =>
    request('/api/policies/parse', { method: 'POST', body: JSON.stringify({ name, text }) }),

  createPolicy: (draft) =>
    request('/api/policies', { method: 'POST', body: JSON.stringify(draft) }),

  listPolicies: () => request('/api/policies'),

  updatePolicy: (id, patch) =>
    request(`/api/policies/${id}`, { method: 'PUT', body: JSON.stringify(patch) }),

  deletePolicy: (id) => request(`/api/policies/${id}`, { method: 'DELETE' }),

  listClaims: () => request('/api/claims'),

  evaluateClaims: (policyId) =>
    request(`/api/claims/evaluate${policyId ? `?policy_id=${encodeURIComponent(policyId)}` : ''}`, {
      method: 'POST',
    }),
};
