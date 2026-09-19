import sqlglot
from sqlglot import exp


# --------------------------------------------------
# VALIDATE OPTIMIZED SQL
# --------------------------------------------------

def validate_optimized_query(query):

    if not query or not query.strip():

        return {
            "valid": False,
            "error": "The optimized query is empty."
        }

    try:

        sqlglot.parse_one(
            query,
            read="postgres"
        )

        return {
            "valid": True,
            "error": None
        }

    except Exception as e:

        return {
            "valid": False,
            "error": str(e)
        }


# --------------------------------------------------
# EXTRACT TABLES FROM DATABASE SCHEMA
# --------------------------------------------------

def extract_schema(schema_sql):

    tables = {}

    if not schema_sql or not schema_sql.strip():

        return tables

    try:

        statements = sqlglot.parse(
            schema_sql,
            read="postgres"
        )

        for statement in statements:

            if isinstance(statement, exp.Create):

                table = statement.find(
                    exp.Table
                )

                if not table:
                    continue

                table_name = table.name

                columns = []

                for column in statement.find_all(
                    exp.ColumnDef
                ):

                    columns.append(
                        column.name
                    )

                tables[table_name] = columns

        return tables

    except Exception:

        return {}


# --------------------------------------------------
# VALIDATE TABLE NAMES
# --------------------------------------------------

def validate_tables(query, schema_tables):

    # If no schema was provided,
    # don't perform table validation.

    if not schema_tables:

        return {
            "valid": True,
            "unknown_tables": []
        }

    try:

        tree = sqlglot.parse_one(
            query,
            read="postgres"
        )

        query_tables = {
            table.name
            for table in tree.find_all(
                exp.Table
            )
        }

        unknown_tables = [
            table
            for table in query_tables
            if table not in schema_tables
        ]

        return {
            "valid": len(unknown_tables) == 0,
            "unknown_tables": unknown_tables
        }

    except Exception:

        return {
            "valid": False,
            "unknown_tables": []
        }

