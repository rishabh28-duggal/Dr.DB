import sqlglot
from sqlglot import exp


def parse_query(query):
    try:
        tree = sqlglot.parse_one(query, read="postgres")
        return {
            "valid": True,
            "tree": tree,
            "error": None
        }
    except Exception as e:
        return {
            "valid": False,
            "tree": None,
            "error": str(e)
        }


def detect_select_star(tree):
    issues = []

    if list(tree.find_all(exp.Star)):
        issues.append({
            "issue": "SELECT * detected",
            "severity": "MEDIUM",
            "explanation":
                "The query retrieves every column, which can increase data transfer and processing."
        })

    return issues


def detect_distinct(tree):
    issues = []

    if tree.args.get("distinct"):
        issues.append({
            "issue": "DISTINCT detected",
            "severity": "LOW",
            "explanation":
                "DISTINCT can add sorting or deduplication overhead. Check whether duplicate removal is actually required."
        })

    return issues


def detect_leading_wildcard(tree):
    issues = []

    for like in tree.find_all(exp.Like):
        expression = like.expression

        if isinstance(expression, exp.Literal):
            value = expression.this

            if isinstance(value, str) and value.startswith("%"):
                issues.append({
                    "issue": "Leading wildcard LIKE detected",
                    "severity": "HIGH",
                    "explanation":
                        "Patterns such as LIKE '%text' can prevent efficient use of standard B-tree indexes."
                })

    return issues


def detect_correlated_subqueries(tree):
    issues = []

    # Look at each subquery in the query
    for subquery in tree.find_all(exp.Subquery):

        # Collect aliases/tables defined inside the subquery
        local_tables = set()

        for table in subquery.find_all(exp.Table):
            alias = table.alias_or_name

            if alias:
                local_tables.add(alias)

        # Check columns referenced inside the subquery
        for column in subquery.find_all(exp.Column):

            table_name = column.table

            # If a column references a table/alias not defined
            # inside the subquery, it may be referencing
            # the outer query -> correlated subquery
            if table_name and table_name not in local_tables:

                issues.append({
                    "issue": "Possible correlated subquery",
                    "severity": "HIGH",
                    "explanation":
                        "This subquery appears to reference a table from the outer query. "
                        "Correlated subqueries may execute repeatedly for rows from the outer query "
                        "and can sometimes be rewritten using JOINs or aggregations."
                })

                # Only report once per subquery
                break

    return issues
def detect_function_on_filtered_column(tree):
    issues = []

    # Look for WHERE clauses
    for where in tree.find_all(exp.Where):

        # Search for SQL functions inside WHERE
        for func in where.find_all(exp.Func):

            # Check whether the function contains a column reference
            columns = list(func.find_all(exp.Column))

            if columns:
                column_names = [col.sql() for col in columns]

                issues.append({
                    "issue": "Function applied to filtered column",
                    "severity": "MEDIUM",
                    "explanation":
                        f"A function is being applied to {', '.join(column_names)} inside the WHERE clause. "
                        "This can prevent the database from efficiently using a standard index on that column."
                })

    return issues
def detect_in_subquery(tree):
    issues = []

    for in_expr in tree.find_all(exp.In):
        query = in_expr.args.get("query")

        if query is not None:
            issues.append({
                "issue": "IN subquery detected",
                "severity": "MEDIUM",
                "explanation":
                    "This query uses IN with a subquery. Depending on data size and the execution plan, "
                    "a JOIN or EXISTS clause may perform better and should be evaluated."
            })

    return issues
def analyze_query(tree):
    issues = []

    detectors = [
        detect_select_star,
        detect_distinct,
        detect_leading_wildcard,
        detect_correlated_subqueries,
        detect_function_on_filtered_column,
        detect_in_subquery
    ]

    for detector in detectors:
        issues.extend(detector(tree))

    return issues