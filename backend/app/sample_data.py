"""Mock expense claims. Not real customer data — fully synthetic for the demo."""

from app.models import Claim

SAMPLE_CLAIMS: list[Claim] = [
    Claim(
        claim_id="EXP-101",
        employee="Asha Rao",
        department="Sales",
        amount=250.00,
        category="Client Dinner",
        description="Dinner with prospective client",
        date="2026-07-02",
    ),  # obvious approval
    Claim(
        claim_id="EXP-102",
        employee="Marcus Lee",
        department="Engineering",
        amount=4500.00,
        category="Conference",
        description="Annual security conference travel + ticket",
        date="2026-07-03",
    ),  # obvious escalation
    Claim(
        claim_id="EXP-103",
        employee="Priya Nair",
        department="Marketing",
        amount=120.00,
        category="Prohibited",
        description="Bar tab expensed as team offsite",
        date="2026-07-04",
    ),  # obvious rejection
    Claim(
        claim_id="EXP-104",
        employee="David Chen",
        department="Finance",
        amount=2350.00,
        category="Software",
        description="Annual license renewal",
        date="2026-07-05",
    ),  # escalation over threshold
    Claim(
        claim_id="EXP-105",
        employee="Sara Ibrahim",
        department="Sales",
        amount=500.00,
        category="Travel",
        description="Client site visit — cab fare",
        date="2026-07-06",
    ),  # boundary: exactly $500
    Claim(
        claim_id="EXP-106",
        employee="Tom Walsh",
        department="Operations",
        amount=2000.00,
        category="Equipment",
        description="Replacement laptop charger and dock",
        date="2026-07-06",
    ),  # boundary: exactly $2000
    Claim(
        claim_id="EXP-107",
        employee="Julia Fernandes",
        department="Sales",
        amount=700.00,
        category="Travel",
        description="Flight change fee for client meeting",
        date="2026-07-07",
    ),  # conflicting rules (Sales-under-1000 vs Travel-over-500)
    Claim(
        claim_id="EXP-108",
        employee="Ben Okafor",
        department=None,
        amount=340.00,
        category="Office Supplies",
        description="Standing desk mat",
        date="2026-07-08",
    ),  # missing data (department)
    Claim(
        claim_id="EXP-109",
        employee="Grace Kim",
        department="Legal",
        amount=180.00,
        category="Miscellaneous",
        description="Notary and filing fees — unclear categorization",
        date="2026-07-09",
    ),  # unusual/ambiguous category
    Claim(
        claim_id="EXP-110",
        employee="Ravi Iyer",
        department="Sales",
        amount=499.99,
        category="Client Gift",
        description="Holiday gift basket for long-term client",
        date="2026-07-10",
    ),  # just under boundary
    Claim(
        claim_id="EXP-111",
        employee="Elena Petrova",
        department="Engineering",
        amount=None,
        category="Travel",
        description="Amount pending finance reconciliation",
        date="2026-07-11",
    ),  # missing amount
    Claim(
        claim_id="EXP-112",
        employee="Omar Siddiqui",
        department="Sales",
        amount=1999.99,
        category="Travel",
        description="International client visit — flights + hotel",
        date="2026-07-12",
    ),  # just under escalation threshold, tests priority ordering
]
