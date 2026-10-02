# Problem Statement Mapping

## Official challenge direction

HacKU 2026 FinTech Problem 2 asks teams to identify a form of value that existing processes do not handle well and build a product that supports legitimate financial or economic activity around that value.

The challenge emphasizes mechanism design rather than tokenization. A strong solution should make clear:

- what is being exchanged;
- who benefits;
- what fairness rule is used;
- how the rule behaves across multiple cases;
- what happens in disputes, exits, or imbalanced situations;
- where the mechanism can fail or create trade-offs.

A blockchain or token is not inherently required.

> This section summarizes the competition requirement. It should be kept separate from the team's own product assumptions.

## CoValue team's interpretation

CoValue focuses on heterogeneous services and resources whose value is difficult to represent with one posted price.

Examples include:

- one hour of advanced technical tutoring;
- access to specialized equipment;
- temporary use of a workspace;
- design / photography / editing services;
- event help;
- trusted introductions;
- urgent assistance;
- bundles that combine time, skill, resource access, and risk.

The common problem is not that these activities have zero value. The problem is that the value is contextual and multi-dimensional.

## What is exchanged?

A transaction may include one or more of:

- time;
- professional or practical skill;
- physical resources;
- access rights;
- service commitments;
- money used as a balancing component.

CoValue does not assume that every transaction is barter. The platform may recommend a mixed exchange such as service + cash.

## Who benefits?

Primary users:

- students;
- campus communities;
- local communities;
- small teams;
- member-based organizations.

Potential institutional users:

- universities;
- incubators;
- associations;
- community operators;
- platforms that already host service exchanges.

## Team fairness hypothesis

The initial fairness rule is:

> A recommended agreement should be individually acceptable to both parties under the model's stated assumptions, and material imbalance should be made explicit rather than hidden.

Operational consequences:

1. both parties see the same valuation dimensions;
2. the mechanism may reject a 1:1 exchange;
3. imbalance can be corrected through cash, scope, duration, timing, or milestone changes;
4. a party's reasonable outside option matters;
5. partial execution is settled consistently;
6. uncertainty is shown rather than converted into false precision.

This is a testable design hypothesis, not a universal definition of fairness.

## Required abnormal cases

The demo should include at least one abnormal flow and the evaluation set should include several:

### Exit

A party exits after partial performance.

Expected handling:
- identify completed milestones;
- value completed work under the same agreed rule;
- calculate remaining obligations;
- settle only the completed / incurred portion where appropriate.

### Dispute

A party claims delivered quality differs from the agreement.

Expected handling:
- compare against explicit milestone criteria;
- surface evidence and disputed variables;
- recalculate only when the disputed input is relevant;
- route low-confidence cases to review instead of pretending certainty.

### Large imbalance

One side offers much more economic value than the other.

Expected handling:
- flag imbalance;
- suggest cash top-up or changed scope;
- allow "no viable agreement" as a valid result.

### Model uncertainty

Insufficient comparables or unreliable inputs.

Expected handling:
- widen the estimate / confidence interval;
- explain missing evidence;
- avoid overly precise compensation recommendations.

## What the hackathon prototype must prove

The prototype does not need to prove that CoValue has discovered the objective price of human activity.

It should prove that:

1. ambiguous value can be represented in a structured way;
2. the same mechanism can run across different transactions;
3. recommendations can be explained;
4. fairness rules can be made explicit;
5. abnormal outcomes can be handled consistently;
6. the mechanism's limitations can be demonstrated rather than hidden.
