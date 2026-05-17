from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0002_create_subscriptions_table'),
    ]

    operations = [
        migrations.RunSQL(
            sql='''
            CREATE INDEX IF NOT EXISTS subscriptions_user_status_period_idx
                ON subscriptions(user_id, status, current_period_end DESC);

            CREATE INDEX IF NOT EXISTS subscriptions_customer_idx
                ON subscriptions(stripe_customer_id);
            ''',
            reverse_sql='''
            DROP INDEX IF EXISTS subscriptions_customer_idx;
            DROP INDEX IF EXISTS subscriptions_user_status_period_idx;
            ''',
        ),
    ]
