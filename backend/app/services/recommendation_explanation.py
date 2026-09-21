def explain_match(result: dict) -> dict:
    """
    Generate a human-readable explanation
    from researcher similarity components.
    """

    scores = result["component_scores"]

    explanations = []

    # Research areas
    if scores["research_areas"] >= 0.50:
        explanations.append(
            "Strong alignment in research areas."
        )
    elif scores["research_areas"] >= 0.20:
        explanations.append(
            "Some alignment in research areas."
        )

    # Expertise
    if scores["expertise"] >= 0.50:
        explanations.append(
            "Strong expertise alignment."
        )
    elif scores["expertise"] >= 0.20:
        explanations.append(
            "Relevant expertise overlap."
        )

    # Skills
    if scores["skills"] >= 0.50:
        explanations.append(
            "Strong technical skill alignment."
        )
    elif scores["skills"] >= 0.20:
        explanations.append(
            "Relevant technical skills overlap."
        )

    # Projects
    if scores["projects"] >= 0.50:
        explanations.append(
            "Strong project-domain alignment."
        )
    elif scores["projects"] >= 0.20:
        explanations.append(
            "Related project experience."
        )

    # Publications
    if scores["publications"] >= 0.50:
        explanations.append(
            "Strong publication-topic alignment."
        )
    elif scores["publications"] >= 0.20:
        explanations.append(
            "Related publication topics."
        )

    return {
        "researcher_id": result["researcher_id"],
        "name": result["name"],
        "department": result["department"],
        "match_score": round(
            result["final_score"] * 100,
            2
        ),
        "why_recommended": explanations
    }