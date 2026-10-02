"""
Firestore seeding script for fitness-coach-agent.
"""

import time
import subprocess
import google.auth
from google.oauth2.credentials import Credentials
from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-02-22f397fe66a7"

INITIAL_WORKOUTS = [
    {
        "workout_id": "workout_001",
        "title": "Morning Interval Run",
        "activity_type": "Running",
        "date": "2026-09-28",
        "duration_minutes": 45,
        "distance_miles": 5.5,
        "avg_heart_rate": 162,
        "perceived_exertion": 8,
        "notes": "6x800m repeats at threshold pace. Felt strong on final set.",
    },
    {
        "workout_id": "workout_002",
        "title": "Endurance Road Ride",
        "activity_type": "Cycling",
        "date": "2026-09-29",
        "duration_minutes": 90,
        "distance_miles": 24.0,
        "avg_heart_rate": 142,
        "perceived_exertion": 6,
        "notes": "Steady Zone 2 aerobic base ride. Kept cadence high at 90 RPM.",
    },
    {
        "workout_id": "workout_003",
        "title": "Upper Body & Core Strength",
        "activity_type": "Strength",
        "date": "2026-09-30",
        "duration_minutes": 40,
        "distance_miles": 0.0,
        "avg_heart_rate": 128,
        "perceived_exertion": 7,
        "notes": "Bench press, pull-ups, plank holds. Great core stability focus.",
    },
    {
        "workout_id": "workout_004",
        "title": "Tempo Trail Run",
        "activity_type": "Running",
        "date": "2026-10-01",
        "duration_minutes": 50,
        "distance_miles": 6.2,
        "avg_heart_rate": 158,
        "perceived_exertion": 7,
        "notes": "Sustained Zone 3 pace along coastal trail. Mild elevation gain.",
    },
]

INITIAL_PROFILE = {
    "user_id": "athlete_default",
    "resting_hr": 58,
    "max_hr": 188,
    "ftp": 230,
    "fitness_goal": "Half Marathon & Base Aerobic Fitness",
    "days_per_week": 4,
    "injury_notes": "Mild left calf tightness; avoid back-to-back hard interval days.",
    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
}


def get_firestore_client():
    try:
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"], text=True
        ).strip()
        if token:
            return firestore.Client(
                project=PROJECT_ID, credentials=Credentials(token)
            )
    except Exception:
        pass
    return firestore.Client(project=PROJECT_ID)


def seed_firestore():
    print(f"Connecting to Firestore for project '{PROJECT_ID}'...")
    db = get_firestore_client()
    collection_ref = db.collection("workout_logs")

    for workout in INITIAL_WORKOUTS:
        doc_ref = collection_ref.document(workout["workout_id"])
        doc_ref.set(workout)
        print(f"Seeded workout: {workout['workout_id']} - {workout['title']}")

    profile_ref = db.collection("user_profiles").document(INITIAL_PROFILE["user_id"])
    profile_ref.set(INITIAL_PROFILE)
    print(f"Seeded user profile for: {INITIAL_PROFILE['user_id']}")

    print("Seeding complete! Successfully added initial workout logs and user profile.")


if __name__ == "__main__":
    seed_firestore()
