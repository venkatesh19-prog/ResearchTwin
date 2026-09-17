import pandas as pd
from sqlalchemy.orm import Session

from ..models import Researcher


def import_researchers(csv_path: str, db: Session) -> int:
    """
    Import researcher data from CSV into the database.
    """

    df = pd.read_csv(csv_path)

    # Remove completely empty rows
    df = df.dropna(how="all")

    # Check required column
    if "name" not in df.columns:
        raise ValueError("CSV must contain a 'name' column")

    imported_count = 0

    for _, row in df.iterrows():

        # Skip rows without a name
        if pd.isna(row["name"]):
            continue

        # Experience
        experience = None

        if "experience" in df.columns:
            if not pd.isna(row["experience"]):
                experience = int(row["experience"])

        researcher = Researcher(
            name=str(row["name"]),

            department=(
                None
                if pd.isna(row.get("department"))
                else str(row["department"])
            ),

            designation=(
                None
                if pd.isna(row.get("designation"))
                else str(row["designation"])
            ),

            experience=experience,

            research_areas=(
                None
                if pd.isna(row.get("research_areas"))
                else str(row["research_areas"])
            ),

            expertise=(
                None
                if pd.isna(row.get("expertise"))
                else str(row["expertise"])
            ),

            skills=(
                None
                if pd.isna(row.get("skills"))
                else str(row["skills"])
            ),

            publications=(
                None
                if pd.isna(row.get("publications"))
                else str(row["publications"])
            ),

            projects=(
                None
                if pd.isna(row.get("projects"))
                else str(row["projects"])
            ),

            profile_url=(
                None
                if pd.isna(row.get("profile_url"))
                else str(row["profile_url"])
            )
        )

        db.add(researcher)
        imported_count += 1

    db.commit()

    return imported_count