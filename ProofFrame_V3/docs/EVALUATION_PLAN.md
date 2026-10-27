# Evaluation and rollout

This plan defines future measurements. No model accuracy, repair-success rate or savings have been measured by this handoff.

## Baselines

B0: current owner workflow: production output reviewed/repaired with the actual Opus model/settings the owner uses. Record human time, calls, retries, accepted defects and final outcome. Do not call the model's verdict ground truth.

B1: one-pass native-video critique using Meta and a simple report prompt.

B2: the SAME qualified model using structured assertions, fixed evidence and deterministic policy. This tests process improvements without confounding them with model choice.

B3: B2 plus active temporal/spatial evidence refinement and specialist tools.

B4: the full conditional model-routing and repair workflow. Any claimed savings include all verifier, escalation, repair and recheck calls, not just the cheap first pass.

For model comparison, hold evidence and task constant. For system comparison, report each system's evidence strategy and total resources. Record model IDs/revisions, reasoning settings, media encoding, prompts and timeouts.

## Dataset development

Start with 12-18 clearly labeled integration cases; these prove execution only. Expand to an initial pilot of approximately 60 assertion-bearing real-production examples across film, brand and children's content, plus a separate set of deterministic/synthetic mutation cases. These are proposed engineering milestones, not statistical sufficiency claims.

Include real positives, clean negatives and ambiguous cases. Create paired negative controls: lighting change without wardrobe change; visible prop occluded rather than removed; intentional costume transition; permitted dialogue paraphrase; an off-screen action explicitly permitted by the brief; a deliberate long static shot; exact versus semantic approved copy.

Include adversarial failures: wrong reference version, missing beat despite a long duration, duplicated clips, forbidden slow motion, incorrect subtitle with correct narration, correct narration with the wrong visual, contradictory producer 'all fixed' statements, malformed JSON, provider outage, exhausted budget and a repair that hides the defect out of frame.

Human labels must distinguish clearly wrong, clearly compliant and not observable. Preserve source intervals, expected assertions, reference versions and disagreements. The owner or a competent reviewer adjudicates difficult cases. An Opus judgment is useful as a proposal but cannot be the sole truth label used to declare Meta better.

Split by episode/project/brand and generation family where possible, not random frames. All variants of the same source shot stay in the same split. Lock a holdout before prompt/router tuning. Keep development, calibration and final test use separate; never let test labels enter runtime prompts. Document small-sample limitations.

## Metrics

Report per profile, defect class and evidence modality:

- Defect precision/recall with TP/FP/FN counts; deduplicate repeated findings for one root cause.
- Severity-specific false negatives and defect escapes among release-eligible assets.
- Mandatory assertion coverage; NOT_CHECKED/ERROR/UNCERTAIN counts and reasons.
- Selective risk versus automation coverage. Abstention cannot silently improve apparent accuracy.
- Temporal interval IoU and boundary error for localization tasks; distinguish broad contextual intervals from precise defect intervals.
- Evidence provenance validity AND human-rated relevance/sufficiency. A correct timestamp does not imply a correct claim.
- Repair success on frozen requirements, regression count, wasted rerenders, retries and not-comparable outcomes.
- End-to-end median/p95 wall time; cost per verified minute, per accepted asset and per successfully repaired defect; unpriced usage separately.
- Owner review minutes and final acceptance judgment.

Do not pool unrelated scores into a universal quality percentage. A 97/100 score with an unresolved missing disclaimer is not acceptable.

## Ablations

1. Same model: free-form review versus typed assertions and immutable intent.
2. Fixed sampling versus active refinement, at comparable budgets and separately at unconstrained budgets.
3. Native video versus frame representation for temporal checks.
4. With/without tracking on cases that actually benefit from tracking.
5. Blind observation versus expected-answer/producer-report leakage.
6. Cheap candidate-only gating versus mandatory assertion evidence plans; measure missed defects.
7. Full-film re-review versus dependency-aware regression plus mandatory sentinels.
8. Same-model second pass versus new evidence versus genuinely different qualified model.

## Graduation policy

Begin in shadow mode. ProofFrame produces evidence and repair suggestions but cannot publish or trigger unbounded spending. Allow deterministic, reversible local repairs first under an explicit project policy. Generative repairs require a configured budget and either specific approval or an approved narrowly scoped automation policy.

Qualification is task/domain specific. Publish the model/version, data slice, uncertainty, observed error counts and escalation rate. A small sample with zero observed escapes does NOT establish near-zero production risk. Under an independent Bernoulli assumption, zero errors in n trials still gives a one-sided 95% upper bound of `1 - 0.05**(1/n)`; clustered film data are not necessarily independent, so episode-level analysis is also necessary.

No predetermined accuracy or savings promise is a release requirement. Use measured results to decide which checks may automate; otherwise retain review and state the limitation. Requalify after material model, prompt, evidence or domain changes, and audit a random sample of apparently passed cases.

## Hackathon demonstration

Use an owned adult-fiction sequence. Show an explicit requirement, a real localized error and evidence, a machine-readable repair, the external generator's new asset, and regression results that preserve unrelated correct content. Include one ambiguous/hard-negative case to show honest abstention.

A deterministic compositing repair is valid if labeled as such. A prerecorded generation result can be shown as a recorded repair receipt, not as a live autonomous edit. Make the actual Meta roles and call traces visible without exposing keys. Keep public demo assets separate from confidential client material.
