"""InsiderLens detection engine — in-memory graph rules over the ingested bank.

LAW 1 (blindness): nothing here may import repositories/ground_truth or know
what a "scenario" is. The engine sees ONLY transactions/accounts/customers.
LAW 2 (config): every threshold comes from RulesConfig (rules.yaml) — no magic
numbers; tests grep for this.
LAW 3 (evidence): every RuleHit carries machine-checkable evidence.
"""
