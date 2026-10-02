# CoValue 互值

**HacKU 2026 · FinTech · Problem 2**

CoValue is a prototype for evaluating and structuring exchanges whose value is difficult to express with a single market price — such as time, skills, equipment access, space, trust, urgency, and service quality.

The project explores a simple question:

> When two parties both have something valuable to exchange, but conventional pricing does not describe the trade well, how can a platform make the exchange understandable, negotiable, and fair?

## Problem

Many legitimate economic activities are under-served by conventional marketplaces because:

- the exchanged value is heterogeneous;
- market prices are sparse or unavailable;
- perceived value differs between parties;
- trust, urgency, scarcity, and execution risk matter;
- one side may need a cash top-up instead of a pure barter;
- disputes and early exits are difficult to settle consistently.

CoValue focuses on turning these ambiguous exchanges into structured agreements.

## Our Solution

A user describes what they **offer** and what they **need**. CoValue then:

1. structures both sides of the exchange;
2. estimates an interpretable value range;
3. identifies the major sources of value and risk;
4. checks whether the exchange is balanced;
5. suggests a cash top-up or revised terms when necessary;
6. generates an agreement with milestones and exit rules;
7. supports review when delivery, expectations, or circumstances change.

The goal is not to claim that every activity has one objectively correct price. The goal is to make the assumptions and trade-offs explicit enough for both parties to negotiate.

## How It Works

```text
Offer + Need
    ↓
Structured attributes
    ↓
Value estimation
    ↓
Fairness / feasibility checks
    ↓
Matching & optional cash adjustment
    ↓
Agreement
    ↓
Milestone verification
    ↓
Completion / exit / dispute review
```

## Core Mechanism

The first implementation will use a modular scoring framework rather than a hard-coded universal price.

A candidate value function may include:

```text
V = f(
    time_cost,
    skill_level,
    scarcity,
    urgency,
    resource_cost,
    trust,
    execution_risk,
    quality_requirement,
    outside_option
)
```

The mechanism is intentionally replaceable. During the hackathon we will compare several approaches, including:

- weighted interpretable scoring;
- constrained optimization;
- Nash-product-style bargaining;
- rule-based adjustment for cash top-ups;
- scenario-specific calibration.

The model must expose *why* it produces a result, not only a final score.

## Fairness Rules

Initial fairness principles:

1. **Symmetry of explanation** — both parties can see how their side is evaluated.
2. **No forced equivalence** — a trade may be labelled imbalanced instead of being forced into a 1:1 exchange.
3. **Explicit compensation** — material imbalance can be corrected with cash, scope, duration, or milestone adjustments.
4. **Outside-option awareness** — the platform should not recommend a deal clearly worse than a reasonable alternative.
5. **Consistent exit logic** — partial completion should be settled using the same rules regardless of which party exits.
6. **Reviewability** — users can inspect the inputs and assumptions that drove the recommendation.

These rules are hypotheses to be tested during the hackathon, not claims of universal fairness.

## Edge Cases & Failure Conditions

The prototype must demonstrate how it behaves when:

- one side exaggerates effort or scarcity;
- the parties value the same service very differently;
- no comparable market reference exists;
- a participant exits after partial delivery;
- quality is disputed;
- a cash top-up becomes too large;
- trust or execution risk changes after agreement;
- a powerful participant can systematically impose worse terms;
- the model has insufficient evidence to estimate value confidently.

When confidence is too low, the system should say so rather than fabricate precision.

## System Architecture

Planned stack:

- **Backend:** Python + FastAPI
- **Database:** SQLite / SQLAlchemy
- **Model layer:** NumPy / Pandas, with replaceable valuation and bargaining modules
- **Frontend:** lightweight web prototype
- **API:** REST endpoints for offers, needs, valuation, matching, agreements, and disputes

Planned structure:

```text
backend/app/
├── api/
├── core/
├── models/
├── schemas/
├── services/
└── main.py

frontend/
data/
docs/
```

## Demo Flow

The hackathon demo should show one complete transaction:

1. User A enters an offer.
2. User B enters a need / counter-offer.
3. CoValue structures both sides.
4. The model produces an explainable valuation.
5. The platform identifies imbalance.
6. It proposes revised terms or a cash top-up.
7. Both sides accept an agreement.
8. A milestone is completed.
9. An abnormal case is triggered — exit or dispute.
10. CoValue applies the same settlement rules and shows the reasoning.

## Evaluation Plan

We will test the mechanism on multiple synthetic and manually constructed scenarios.

Key questions:

- Does the same rule behave consistently across cases?
- How sensitive is the result to each variable?
- Can users understand why the value changed?
- Can the mechanism detect obviously unbalanced exchanges?
- Does it avoid extreme recommendations when inputs are noisy?
- What happens when confidence is low?
- Which fairness rule creates the largest trade-off with market efficiency?

Potential metrics include:

- value-gap reduction;
- agreement feasibility;
- minimum participant utility;
- fairness constraint violations;
- sensitivity / robustness;
- explanation consistency;
- dispute settlement consistency.

## Business Model

Possible deployment paths:

- transaction service fee;
- premium verification / trust services;
- institutional SaaS for universities, communities, incubators, and member networks;
- API access for platforms that need value assessment or negotiation support.

The hackathon prototype will prioritize mechanism validity and a working transaction flow over monetization depth.

## Hackathon Deliverables

Target deliverables:

- [ ] Working prototype
- [ ] Publicly accessible demo or demo recording
- [ ] GitHub repository with setup instructions
- [ ] Mathematical / mechanism design explanation
- [ ] Multiple validation scenarios
- [ ] Edge-case demonstration
- [ ] Pitch deck
- [ ] Final submission links

## Team / TODO

Immediate priorities:

- [ ] Lock the exact value dimensions and definitions
- [ ] Implement the baseline valuation function
- [ ] Implement matching / cash-adjustment logic
- [ ] Define fairness constraints
- [ ] Build 5–10 validation scenarios
- [ ] Implement agreement and milestone state machine
- [ ] Implement one dispute / exit flow
- [ ] Build the web demo
- [ ] Prepare evaluation charts
- [ ] Prepare pitch deck

---

Built for **HacKU 2026**.
