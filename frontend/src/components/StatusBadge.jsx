const LABEL = { APPROVE: 'Approved', REJECT: 'Rejected', ESCALATE: 'Escalated' };

export default function StatusBadge({ decision, size = 'md' }) {
  return (
    <span className={`badge badge--${decision?.toLowerCase()} badge--${size}`}>
      <span className="badge__dot" />
      {LABEL[decision] || decision}
    </span>
  );
}
