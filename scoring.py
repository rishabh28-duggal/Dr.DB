def calculate_health_score(issues):

    score = 100

    penalties = {
        "HIGH": 25,
        "MEDIUM": 15,
        "LOW": 5
    }

    for issue in issues:

        severity = issue.get(
            "severity",
            "LOW"
        ).upper()

        score -= penalties.get(
            severity,
            5
        )

    return max(score, 0)

def calculate_impact_score(issues, recommended_indexes):

    score = 0

    severity_scores = {
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1
    }

    # Score detected performance issues
    for issue in issues:

        severity = issue.get(
            "severity",
            "LOW"
        ).upper()

        score += severity_scores.get(
            severity,
            1
        )

    # Index recommendations indicate additional
    # optimization potential
    if recommended_indexes:
        score += min(
            len(recommended_indexes) * 2,
            4
        )

    # Convert numerical score into impact category
    if score >= 6:
        impact = "HIGH"

    elif score >= 3:
        impact = "MEDIUM"

    else:
        impact = "LOW"

    return {
        "score": score,
        "impact": impact
    }