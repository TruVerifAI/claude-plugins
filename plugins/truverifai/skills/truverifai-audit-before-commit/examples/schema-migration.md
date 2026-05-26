# Example — auditing a database migration

A worked example for migrations that touch populated production tables.

## Scenario

Adding a `marketing_opt_in` boolean column to the `users` table with a NOT NULL constraint. New users default to false; existing users will be backfilled before the constraint is enforced. The migration runs as part of normal deploy.

## The migration (illustrative)

```python
# migrations/0042_user_marketing_opt_in.py
from alembic import op
import sqlalchemy as sa

revision = "0042"
down_revision = "0041"

def upgrade():
    op.add_column(
        "users",
        sa.Column("marketing_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Remove the server_default so future inserts must specify the value
    op.alter_column("users", "marketing_opt_in", server_default=None)

def downgrade():
    op.drop_column("users", "marketing_opt_in")
```

## How to populate the inputs

```python
mcp__truverifai__audit_coding(
    proposed_action=(
        "Adding marketing_opt_in boolean column to users table with NOT NULL "
        "constraint. New users default to false; the server_default handles "
        "backfill of existing rows during the ALTER TABLE, then we strip the "
        "server_default so future inserts must specify the value explicitly. "
        "Goal: comply with email marketing opt-in regulations for new signups."
    ),
    relevant_code=(
        "# migrations/0042_user_marketing_opt_in.py\n"
        "def upgrade():\n"
        "    op.add_column('users', sa.Column('marketing_opt_in', sa.Boolean(), "
        "nullable=False, server_default=sa.false()))\n"
        "    op.alter_column('users', 'marketing_opt_in', server_default=None)\n\n"
        "def downgrade():\n"
        "    op.drop_column('users', 'marketing_opt_in')"
    ),
    tests=(
        "No migration tests exist. The standard test_models tests cover the "
        "User model; they'll be updated to set marketing_opt_in=False in fixtures. "
        "No data-correctness test runs against the production-equivalent dataset."
    ),
    architectural_context=(
        "PostgreSQL 16. users table has approximately 850k rows in production. "
        "Migration framework: Alembic, run as part of deploy via the standard "
        "alembic upgrade head step. We have no separate maintenance-window "
        "process for migrations; everything runs during normal deploys. The "
        "users table is hot — login traffic hits it constantly during business hours."
    ),
    constraints=(
        "Production deploy window is Tuesday 10am Pacific (peak login traffic). "
        "p99 login latency must stay under 500ms during the deploy. Cannot take "
        "the application offline. No DB read replica failover for migrations."
    ),
)
```

## What a good audit response looks like

**Critical findings:**

1. *ALTER TABLE on a 850k-row table during peak traffic with an ACCESS EXCLUSIVE lock.* `op.add_column` with a NOT NULL constraint + server_default in PostgreSQL 11+ is fast (just a metadata update — the column is stored as the default until rewritten) but the SECOND statement (`op.alter_column` to drop the server_default) is also metadata-only and fast. **However**, this assumes PostgreSQL 11+. Verify the production server version. On pre-11, the ADD COLUMN would rewrite every row → multi-minute lock → login outage.

2. *No rollback validation.* The `downgrade()` drops the column, which is destructive — any data captured in `marketing_opt_in` between deploy and rollback is lost. Acceptable for boolean opt-in, but the migration doesn't document this trade-off.

**Minor findings:**

3. *Migration sets the column to false for all existing users.* This is a regulatory choice — opt-in defaults to "no consent" for existing users — which is correct from a legal standpoint but should be documented in the migration message or a linked compliance note. A reviewer looking at this in 6 months should understand WHY the default was false.

4. *No application-level fallback if the migration hasn't run yet.* If the deploy serves the new code before the migration finishes, queries against `User.marketing_opt_in` will fail. Alembic typically runs migrations before code starts serving, but verify your deploy pipeline.

**Preference findings:**

5. The migration filename uses an integer prefix (`0042`); your repo convention is timestamps (`20260520_...`). Cosmetic but worth aligning.

**Response shape:**

```json
{
  "agreement_score": 0.91,
  "action": "proceed_with_caveats",
  "action_basis": "derived",
  "dimensions_of_disagreement": []
}
```

## How to act on this

Action is `proceed_with_caveats` → minor issues to address, then ship.

1. **Verify the PostgreSQL version is 11+.** If yes, the metadata-only optimization applies and the migration is safe during peak traffic. If no, defer the migration to a maintenance window. This is a one-line check against the prod DB — do it before committing.
2. Document the false-default rationale in the migration's docstring (finding 3).
3. Verify the deploy pipeline runs migrations BEFORE serving the new code (finding 4). This is usually true but worth confirming.
4. Align the filename to the timestamp convention if your linter cares (finding 5).
5. After addressing, commit.

The high `agreement_score` (0.91) + `proceed_with_caveats` action means the audit is confident the change is fundamentally sound — the findings are scoping/safety nits, not correctness bugs. This is what a good audit response looks like for routine schema work.
