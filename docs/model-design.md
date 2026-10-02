# Model Design

Status: design skeleton for hackathon implementation.

The model is deliberately modular. We should first ship a transparent baseline, then compare it with a bargaining or optimization formulation if time permits.

## 1. Transaction representation

For each side, represent the offered contribution as a feature vector.

Candidate variables:

| Variable | Meaning | Example |
|---|---|---|
| (T) | time cost | 2 hours |
| (S) | skill / expertise | beginner → expert |
| (C) | direct resource cost | materials, equipment wear |
| (R) | scarcity | number of realistic substitutes |
| (U) | urgency | normal → time-critical |
| (Q) | quality requirement | standard → high precision |
| (K) | trust / verification | unverified → trusted |
| (E) | execution risk | probability / impact of failure |
| (O) | outside option | market or alternative opportunity |
| (P) | preference / subjective utility | party-specific desirability |

Not every scenario should use every feature.

## 2. Baseline interpretable value function

A first baseline can be written as:

[
V_i = sum_j w_j phi_j(x_{ij})
]

where:

- (x_{ij}) is feature (j) for party (i);
- (phi_j) normalizes or transforms the feature;
- (w_j) is an explicit weight.

A practical decomposition:

[
V = V_{effort} + V_{skill} + V_{resource} + V_{scarcity}
  + V_{urgency} + V_{quality} - V_{risk}
]

The exact formula must remain readable enough to explain in the demo.

### Important rule

Do not encode "trust" as a moral worth score. Trust should affect uncertainty, verification cost, or execution risk — not a person's intrinsic value.

## 3. Value range and confidence

Avoid one fake-precise number.

Prefer:

[
V in [V_{low}, V_{high}]
]

with a confidence score based on:

- data completeness;
- availability of comparable cases;
- verification level;
- disagreement between estimation methods;
- sensitivity to uncertain inputs.

Low confidence should weaken or suppress automated compensation recommendations.

## 4. Exchange balance

Let:

- (V_A) = estimated value of A's contribution;
- (V_B) = estimated value of B's contribution.

Define raw gap:

[
G = V_A - V_B
]

Relative imbalance:

[
I = rac{|V_A - V_B|}{max(V_A,V_B,epsilon)}
]

If (I) is below a tolerance (	au), the exchange can be treated as approximately balanced.

If not, recommend an adjustment.

## 5. Cash top-up

A simple baseline:

[
M = lambda (V_A - V_B)
]

where (M) is the cash transfer and (lambda) controls how much of the modeled gap should be compensated monetarily.

Why (lambda) may be less than 1:

- subjective utility may differ;
- some value is non-transferable;
- estimates are uncertain;
- exact monetization may falsely imply objective pricing.

Alternative adjustments:

- reduce scope;
- change duration;
- add a milestone;
- add resource access;
- change delivery time;
- reject the deal.

## 6. Individual rationality

For a proposed agreement (z), require:

[
U_A(z) ge O_A
]

[
U_B(z) ge O_B
]

where (O_i) is the party's outside option.

This prevents the system from calling a deal "fair" when one party is predictably worse off than a realistic alternative.

## 7. Bargaining model candidate

If time allows, compare the baseline with a Nash bargaining formulation:

[
max_z (U_A(z)-O_A)(U_B(z)-O_B)
]

subject to:

- individual rationality;
- resource constraints;
- cash / scope bounds;
- minimum quality;
- timing constraints.

Use this as a comparison model, not as a black-box authority.

## 8. Fairness constraints

Candidate measurable constraints:

### Explanation symmetry

Both parties receive the same feature definitions and adjustment rules.

### Bounded imbalance

[
I le 	au
]

after permitted adjustments.

### Compensation bounds

Prevent absurd cash recommendations:

[
M_{min} le M le M_{max}
]

### Confidence threshold

If:

[
Conf < c_{min}
]

return "insufficient confidence" rather than a strong recommendation.

### Exit consistency

The same completed-milestone rule applies regardless of which party exits.

## 9. Milestone settlement

Suppose an agreement contains milestones (m_1,dots,m_n) with allocation weights (a_k), where:

[
sum_k a_k = 1
]

Completed value:

[
V_{done} = V_{contract} sum_{k in completed} a_k
]

An exit settlement starts from completed value plus explicitly incurred non-refundable costs.

This is preferable to an arbitrary percentage chosen after a dispute.

## 10. Dispute handling

A dispute should not immediately overwrite the original model.

Workflow:

1. identify disputed milestone or variable;
2. collect evidence;
3. classify dispute type;
4. recalculate only affected terms;
5. show old vs revised assumptions;
6. if confidence remains low, require human review.

Potential dispute categories:

- non-delivery;
- partial delivery;
- quality mismatch;
- timing failure;
- unexpected cost;
- scope ambiguity.

## 11. Validation cases

Build at least 5–10 scenarios.

Suggested minimum set:

1. tutoring ↔ photography;
2. equipment access ↔ design work;
3. high urgency with cash top-up;
4. low-trust / high-risk transaction;
5. large imbalance leading to "no deal";
6. partial completion and exit;
7. quality dispute;
8. identical economic inputs but different subjective preference;
9. low-data case with low confidence;
10. deliberately manipulated self-reported inputs.

## 12. Evaluation metrics

Potential metrics:

- post-adjustment imbalance;
- individual-rationality violations;
- confidence calibration;
- result sensitivity to one input;
- number of inconsistent outcomes across analogous cases;
- explanation completeness;
- dispute settlement consistency;
- percentage of cases where mechanism correctly refuses to decide.

## 13. Open decisions

Before locking the implementation, decide:

- exact feature scale;
- weight initialization;
- whether market comparables are used;
- how confidence is calculated;
- tolerance (	au);
- compensation bounds;
- whether subjective preference enters value, utility, or both;
- how agreement milestones are weighted;
- how human review is represented in the demo.

The first working version should favor transparency over complexity.
