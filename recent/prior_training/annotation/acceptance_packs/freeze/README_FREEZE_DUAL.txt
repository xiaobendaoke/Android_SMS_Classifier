Freeze dual-annotation pack
===========================

Files
-----
- freeze_pool.csv          master list (prior_label = old single-annotator label)
- freeze_annotator_A.csv   for annotator_A — fill label + annotator only
- freeze_annotator_B.csv   for annotator_B — fill label + annotator only
- freeze_shortfall.json    cells that could not reach 500/class

Rules
-----
1. A and B must NOT look at each other's sheets or at prior_label while labeling.
2. Legal labels: TRANSACTION | AD | HARASS | FRAUD | NEEDS_REVIEW
3. After both finish, merge: same label → candidate gold; conflict → adjudicator.
4. Only agreed (or adjudicated) four-class rows enter the frozen test SHA.
5. Cells with shortfall>0 in freeze_shortfall.json still need NEW source data
   (especially en TRANSACTION, hi FRAUD/TXN, Devanagari hi).

Sampled now: 4058 rows. Remaining shortfall units: 3942.

This pack is a WORK QUEUE for dual annotation — not yet an acceptance freeze.
