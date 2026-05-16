from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql='''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id uuid PRIMARY KEY,
                user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                stripe_subscription_id text UNIQUE,
                stripe_customer_id text,
                status text NOT NULL DEFAULT 'incomplete',
                current_period_start timestamptz,
                current_period_end timestamptz,
                cancel_at_period_end boolean NOT NULL DEFAULT false,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now()
            );

            CREATE INDEX IF NOT EXISTS subscriptions_user_id_idx
                ON subscriptions(user_id);

            CREATE INDEX IF NOT EXISTS subscriptions_status_idx
                ON subscriptions(status);
            ''',
            reverse_sql='''
            DROP TABLE IF EXISTS subscriptions;
            ''',
        ),
    ]
