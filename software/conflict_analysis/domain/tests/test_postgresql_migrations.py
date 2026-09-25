from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PostgreSQLMigrationGateTests(TransactionTestCase):
    def test_clean_test_database_is_at_every_migration_leaf(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL-only migration gate")

        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        self.assertEqual(executor.migration_plan(targets), [])
