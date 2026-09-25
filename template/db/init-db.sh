#!/bin/bash
# Initializes a local SQLite database from schema.template.sql.
# Usage: ./init-db.sh [output-db-name]
# Requires sqlite3 to be installed (sqlite3 --version to check).

set -e

DB_NAME="${1:-tool.db}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$DB_NAME" ]; then
    echo "Warning: $DB_NAME already exists. Delete it first if you want a fresh start."
    exit 1
fi

sqlite3 "$DB_NAME" < "$SCRIPT_DIR/schema.template.sql"
echo "Created $DB_NAME"
echo "Open it with: sqlite3 $DB_NAME"
