"""
Firestore tools and athletic calculators for fitness-coach-agent.
"""

import os
import json
import urllib.request
import urllib.parse
import time
import subprocess
from typing import Optional
import google.auth
from google.oauth2.credentials import Credentials
from google.cloud import firestore
from google.cloud import storage
from google import genai
from google.genai import types
from google.adk.tools import ToolContext

PROJECT_ID = "qwiklabs-gcp-02-22f397fe66a7"
BUCKET_NAME = "fitness-coach-assets-qwiklabs-gcp-02-22f397fe66a7"


def _get_firestore_client() -> firestore.Client:
    """Helper to initialize Firestore client with hardcoded project ID."""
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


def save_user_profile(
    user_id: str = "athlete_default",
    resting_hr: int = 60,
    max_hr: int = 185,
    ftp: int = 200,
    fitness_goal: str = "General Fitness & Base Building",
    days_per_week: int = 4,
    injury_notes: str = "None",
) -> str:
    """Save or update an athlete profile / questionnaire answers in Firestore.

    Args:
        user_id: Unique athlete identifier (defaults to 'athlete_default').
        resting_hr: Resting heart rate in bpm.
        max_hr: Maximum heart rate in bpm.
        ftp: Functional Threshold Power in watts (for cycling/indoor bike).
        fitness_goal: Primary goal (e.g., '5K Race', 'Half Marathon', 'Weight Loss', 'Base Building').
        days_per_week: Number of training days per week available.
        injury_notes: Any active injuries or movement restrictions.

    Returns:
        Confirmation message that the profile was saved.
    """
    db = _get_firestore_client()
    profile_data = {
        "user_id": user_id,
        "resting_hr": int(resting_hr),
        "max_hr": int(max_hr),
        "ftp": int(ftp),
        "fitness_goal": fitness_goal,
        "days_per_week": int(days_per_week),
        "injury_notes": injury_notes,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    db.collection("user_profiles").document(user_id).set(profile_data)
    return f"Successfully saved fitness profile for '{user_id}'!"


def get_user_profile(user_id: str = "athlete_default") -> str:
    """Retrieve an athlete's profile and questionnaire responses from Firestore.

    Args:
        user_id: Unique athlete identifier (defaults to 'athlete_default').

    Returns:
        Formatted summary of the athlete's baseline stats and goals.
    """
    db = _get_firestore_client()
    doc_ref = db.collection("user_profiles").document(user_id)
    doc = doc_ref.get()

    if not doc.exists:
        return f"No fitness profile found for '{user_id}'. Please conduct an initial questionnaire."

    p = doc.to_dict()
    return (
        f"Athlete Profile for '{user_id}':\n"
        f"- Primary Goal: {p.get('fitness_goal')}\n"
        f"- Available Training Days/Week: {p.get('days_per_week')}\n"
        f"- Resting Heart Rate: {p.get('resting_hr')} bpm\n"
        f"- Max Heart Rate: {p.get('max_hr')} bpm\n"
        f"- FTP (Power): {p.get('ftp')} watts\n"
        f"- Injury Notes: {p.get('injury_notes', 'None')}\n"
        f"- Last Updated: {p.get('updated_at')}"
    )


def calculate_training_zones(
    resting_hr: int = 60,
    max_hr: int = 185,
    ftp: int = 0,
) -> str:
    """Calculate personalized Heart Rate (Karvonen formula) and Cycling Power training zones.

    Args:
        resting_hr: Resting heart rate in bpm (e.g. 60).
        max_hr: Maximum heart rate in bpm (e.g. 185).
        ftp: Functional Threshold Power in watts (optional, e.g. 220).

    Returns:
        Structured table of 5-zone HR targets and 7-zone Power targets.
    """
    hrr = max_hr - resting_hr

    z1_min, z1_max = round(resting_hr + 0.50 * hrr), round(resting_hr + 0.60 * hrr)
    z2_min, z2_max = round(resting_hr + 0.60 * hrr), round(resting_hr + 0.70 * hrr)
    z3_min, z3_max = round(resting_hr + 0.70 * hrr), round(resting_hr + 0.80 * hrr)
    z4_min, z4_max = round(resting_hr + 0.80 * hrr), round(resting_hr + 0.90 * hrr)
    z5_min, z5_max = round(resting_hr + 0.90 * hrr), max_hr

    output = [
        f"Physiological Training Zones (Resting HR: {resting_hr} bpm, Max HR: {max_hr} bpm):",
        f"• Zone 1 (Active Recovery): {z1_min} - {z1_max} bpm (50-60% HRR)",
        f"• Zone 2 (Aerobic Base):    {z2_min} - {z2_max} bpm (60-70% HRR)",
        f"• Zone 3 (Tempo / Aerobic): {z3_min} - {z3_max} bpm (70-80% HRR)",
        f"• Zone 4 (Threshold):       {z4_min} - {z4_max} bpm (80-90% HRR)",
        f"• Zone 5 (Anaerobic / VO2): {z5_min} - {z5_max} bpm (90-100% HRR)",
    ]

    if ftp > 0:
        pz1 = f"< {round(ftp * 0.55)}W"
        pz2 = f"{round(ftp * 0.55)} - {round(ftp * 0.75)}W"
        pz3 = f"{round(ftp * 0.76)} - {round(ftp * 0.90)}W"
        pz4 = f"{round(ftp * 0.91)} - {round(ftp * 1.05)}W"
        pz5 = f"{round(ftp * 1.06)} - {round(ftp * 1.20)}W"
        output.extend([
            "",
            f"Cycling Power Zones (FTP: {ftp}W):",
            f"• Zone 1 (Active Recovery): {pz1}",
            f"• Zone 2 (Endurance Base):  {pz2}",
            f"• Zone 3 (Tempo):           {pz3}",
            f"• Zone 4 (Lactate Threshold): {pz4}",
            f"• Zone 5 (VO2 Max):         {pz5}",
        ])

    return "\n".join(output)


def generate_weekly_plan(
    goal: str,
    weeks: int = 4,
    days_per_week: int = 4,
) -> str:
    """Generate a structured multi-week training schedule tailored to athlete goals.

    Args:
        goal: Training goal (e.g. '5K', '10K', 'Half Marathon', 'Marathon', 'Base Building').
        weeks: Duration of training block in weeks (default: 4).
        days_per_week: Number of training days per week (default: 4).

    Returns:
        Structured workout schedule outline.
    """
    plan = [
        f"Custom {weeks}-Week Training Plan for Goal: '{goal}' ({days_per_week} days/week)",
        "=" * 60,
    ]

    for week in range(1, weeks + 1):
        plan.append(f"\nWeek {week}:")
        if "5k" in goal.lower() or "10k" in goal.lower():
            plan.append("  • Day 1: Easy Zone 2 Aerobic Run (30 mins)")
            plan.append("  • Day 2: Interval Speed Workout (5x400m at Zone 4)")
            if days_per_week >= 4:
                plan.append("  • Day 3: Recovery Run or Cross-Training (30 mins)")
            plan.append("  • Day 4: Long Endurance Run (Zone 2, 45-60 mins)")
        elif "marathon" in goal.lower() or "half" in goal.lower():
            plan.append(f"  • Day 1: Easy Aerobic Run (Zone 2, {30 + week * 5} mins)")
            plan.append("  • Day 2: Tempo Run (15 mins Zone 2 + 20 mins Zone 3 + 10 mins cool)")
            if days_per_week >= 4:
                plan.append("  • Day 3: Active Recovery & Strength Session")
            plan.append(f"  • Day 4: Progression Long Run (Zone 2, {60 + week * 10} mins)")
        else:
            plan.append("  • Day 1: Aerobic Base Session (Zone 2, 40 mins)")
            plan.append("  • Day 2: Strength & Core Conditioning (45 mins)")
            if days_per_week >= 4:
                plan.append("  • Day 3: Tempo Workout (Zone 3, 30 mins)")
            plan.append("  • Day 4: Long Aerobic Base Session (Zone 2, 60 mins)")

    return "\n".join(plan)


def list_workout_logs(activity_type: Optional[str] = None) -> str:
    """Fetch and list logged workouts from Firestore.

    Args:
        activity_type: Optional filter by activity type (e.g. 'Running', 'Cycling', 'Strength').

    Returns:
        A text summary of matching logged workouts.
    """
    db = _get_firestore_client()
    docs = db.collection("workout_logs").stream()

    workouts = []
    for doc in docs:
        data = doc.to_dict()
        if activity_type and activity_type.strip():
            if data.get("activity_type", "").lower() != activity_type.strip().lower():
                continue
        workouts.append(data)

    if not workouts:
        filter_msg = f" for '{activity_type}'" if activity_type else ""
        return f"No workout logs found{filter_msg}."

    result = [f"Found {len(workouts)} workout log(s):"]
    for w in workouts:
        result.append(
            f"- ID: {w.get('workout_id')}, Title: {w.get('title')}, Type: {w.get('activity_type')}, "
            f"Date: {w.get('date')}, Duration: {w.get('duration_minutes')} mins, "
            f"Distance: {w.get('distance_miles')} miles, Avg HR: {w.get('avg_heart_rate')} bpm"
        )
    return "\n".join(result)


def get_workout_log(workout_id: str) -> str:
    """Retrieve details for a specific logged workout by ID.

    Args:
        workout_id: The unique document ID of the workout (e.g. 'workout_001').

    Returns:
        Details of the specified workout log.
    """
    db = _get_firestore_client()
    doc_ref = db.collection("workout_logs").document(workout_id)
    doc = doc_ref.get()

    if not doc.exists:
        return f"Workout log with ID '{workout_id}' was not found."

    w = doc.to_dict()
    return (
        f"Workout Log '{workout_id}':\n"
        f"Title: {w.get('title')}\n"
        f"Activity Type: {w.get('activity_type')}\n"
        f"Date: {w.get('date')}\n"
        f"Duration: {w.get('duration_minutes')} minutes\n"
        f"Distance: {w.get('distance_miles')} miles\n"
        f"Avg Heart Rate: {w.get('avg_heart_rate')} bpm\n"
        f"Perceived Exertion (1-10): {w.get('perceived_exertion')}\n"
        f"Notes: {w.get('notes', 'None')}"
    )


def add_workout_log(
    title: str,
    activity_type: str,
    duration_minutes: int,
    distance_miles: float = 0.0,
    avg_heart_rate: int = 0,
    perceived_exertion: int = 5,
    notes: str = "",
) -> str:
    """Log a new workout entry into Firestore.

    Args:
        title: Title/name of the workout (e.g. 'Tempo Run in Park').
        activity_type: Type of activity (e.g. 'Running', 'Cycling', 'Swimming', 'Strength').
        duration_minutes: Workout duration in minutes.
        distance_miles: Distance covered in miles (0.0 for strength/indoor).
        avg_heart_rate: Average heart rate during the workout.
        perceived_exertion: Rating of perceived exertion scale 1-10.
        notes: Optional extra notes or observations.

    Returns:
        Confirmation message with the new workout ID.
    """
    db = _get_firestore_client()
    workout_id = f"workout_{int(time.time())}"
    current_date = time.strftime("%Y-%m-%d")

    workout_data = {
        "workout_id": workout_id,
        "title": title,
        "activity_type": activity_type,
        "date": current_date,
        "duration_minutes": duration_minutes,
        "distance_miles": float(distance_miles),
        "avg_heart_rate": int(avg_heart_rate),
        "perceived_exertion": int(perceived_exertion),
        "notes": notes,
    }

    db.collection("workout_logs").document(workout_id).set(workout_data)
    return f"Successfully logged workout '{title}' with ID '{workout_id}'!"


def analyze_bioimpedance(
    weight_kg: float,
    body_fat_pct: float,
    skeletal_muscle_kg: float,
    total_body_water_pct: float = 60.0,
    visceral_fat_level: int = 5,
    user_id: str = "athlete_default",
) -> str:
    """Analyze Bioelectrical Impedance (BIA) body composition test results to evaluate health status and injury risk prior to suggesting workouts.

    Args:
        weight_kg: Total body weight in kilograms.
        body_fat_pct: Body fat percentage (e.g. 18.5).
        skeletal_muscle_kg: Skeletal muscle mass in kilograms.
        total_body_water_pct: Total body water percentage (default: 60.0%).
        visceral_fat_level: Visceral fat rating scale 1-20 (default: 5).
        user_id: Athlete ID to save assessment to (default: 'athlete_default').

    Returns:
        Bioimpedance analysis summary including injury risk evaluation, readiness tier, and workout safety guidelines.
    """
    muscle_ratio = (skeletal_muscle_kg / weight_kg) * 100.0 if weight_kg > 0 else 0.0

    # Injury risk assessment logic
    risk_factors = []
    if muscle_ratio < 40.0:
        risk_factors.append("Low muscle-to-weight ratio (<40%): Increased risk of joint strain during high-impact running.")
    if body_fat_pct > 28.0:
        risk_factors.append("Elevated body fat percentage (>28%): High orthopedic load on knees/ankles.")
    if total_body_water_pct < 55.0:
        risk_factors.append("Sub-optimal body hydration (<55%): Elevated risk of muscle cramping and heat stress.")
    if visceral_fat_level > 10:
        risk_factors.append("High visceral fat level (>10): Metabolic stress risk during max effort intervals.")

    if not risk_factors:
        risk_tier = "LOW INJURY RISK"
        recommendation = "Excellent body composition profile! Athlete is cleared for high-intensity interval training (HIIT), heavy resistance work, and progression long runs."
    elif len(risk_factors) == 1:
        risk_tier = "MODERATE INJURY RISK"
        recommendation = "Proceed with balanced training. Incorporate 10-15 minutes of dynamic warm-up, core stability, and keep high-intensity sessions capped at 2x per week."
    else:
        risk_tier = "ELEVATED INJURY RISK"
        recommendation = "Prioritize low-impact aerobic base building (cycling/swimming/walking) and progressive strength conditioning before starting high-impact running intervals."

    analysis = [
        f"Bioimpedance Analysis Report for '{user_id}':",
        f"• Body Weight: {weight_kg:.1f} kg",
        f"• Body Fat: {body_fat_pct:.1f}%",
        f"• Skeletal Muscle Mass: {skeletal_muscle_kg:.1f} kg (Muscle Ratio: {muscle_ratio:.1f}%)",
        f"• Total Body Water: {total_body_water_pct:.1f}%",
        f"• Visceral Fat Rating: Level {visceral_fat_level}",
        "",
        f"Injury Risk Level: [{risk_tier}]",
    ]

    if risk_factors:
        analysis.append("Identified Risk Considerations:")
        for rf in risk_factors:
            analysis.append(f"  ⚠️ {rf}")

    analysis.extend([
        "",
        f"Training Recommendation: {recommendation}",
    ])

    try:
        db = _get_firestore_client()
        doc_ref = db.collection("user_profiles").document(user_id)
        doc = doc_ref.get()
        profile_data = doc.to_dict() if doc.exists else {}
        profile_data.update({
            "bioimpedance": {
                "weight_kg": float(weight_kg),
                "body_fat_pct": float(body_fat_pct),
                "skeletal_muscle_kg": float(skeletal_muscle_kg),
                "muscle_ratio": round(muscle_ratio, 1),
                "total_body_water_pct": float(total_body_water_pct),
                "visceral_fat_level": int(visceral_fat_level),
                "risk_tier": risk_tier,
                "tested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        })
        doc_ref.set(profile_data, merge=True)
        analysis.append("\n(Saved bioimpedance assessment results to user profile in Firestore)")
    except Exception:
        pass

    return "\n".join(analysis)


def fetch_outdoor_workout_weather(
    latitude: float = 37.7749,
    longitude: float = -122.4194,
) -> str:
    """Fetch live outdoor weather, humidity, and wind conditions for outdoor workouts from Open-Meteo public API.

    Args:
        latitude: Latitude coordinate (default: 37.7749).
        longitude: Longitude coordinate (default: -122.4194).

    Returns:
        Live weather conditions and athletic pacing/hydration advice.
    """
    api_key = os.environ.get("OPEN_METEO_API_KEY", "").strip()
    key_param = f"&apikey={api_key}" if api_key else ""
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={latitude}&longitude={longitude}"
        f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m"
        f"{key_param}"
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FitnessCoachAgent/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            current = data.get("current", {})
            temp_c = current.get("temperature_2m")
            temp_f = round((temp_c * 9 / 5) + 32, 1) if temp_c is not None else "N/A"
            humidity = current.get("relative_humidity_2m")
            wind_speed = current.get("wind_speed_10m")
            wind_dir = current.get("wind_direction_10m")

            advice = []
            if temp_c is not None and temp_c > 27:
                advice.append("High heat: Increase hydration by 500ml/hr and reduce target heart rate by 5 bpm.")
            elif temp_c is not None and temp_c < 5:
                advice.append("Cold conditions: Wear thermal base layers and spend 10 extra minutes warming up.")

            if humidity is not None and humidity > 80:
                advice.append("High humidity: Sweat evaporation is reduced; monitor perceived exertion closely.")

            if wind_speed is not None and wind_speed > 25:
                advice.append("Strong winds: Plan your route out into the headwind and return with the tailwind.")

            if not advice:
                advice.append("Conditions are ideal for an outdoor session!")

            return (
                f"Outdoor Workout Weather Report (Lat: {latitude}, Lon: {longitude}):\n"
                f"• Temperature: {temp_c}°C ({temp_f}°F)\n"
                f"• Relative Humidity: {humidity}%\n"
                f"• Wind Speed: {wind_speed} km/h (Direction: {wind_dir}°)\n"
                f"• Athletic Advice: {' '.join(advice)}"
            )
    except Exception as e:
        return f"Unable to fetch outdoor weather data: {str(e)}"


def _get_maps_api_key() -> str:
    """Retrieve Google Maps API key from environment variable or local .env file."""
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if key and key != "PASTE_KEY_HERE":
        return key

    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("GOOGLE_MAPS_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
    return key


def geocode_address(address: str) -> str:
    """Convert an address or location name into geographic coordinates using Google Maps Geocoding API.

    Args:
        address: The street address, city, or landmark name to geocode (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA').

    Returns:
        Formatted summary with key fields: address, latitude, longitude, and place_id.
    """
    api_key = _get_maps_api_key()
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    encoded_address = urllib.parse.quote(address)
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FitnessCoachAgent/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            status = data.get("status")

            if status != "OK" or not data.get("results"):
                return f"Geocoding failed for '{address}': Status '{status}'."

            result = data["results"][0]
            formatted_address = result.get("formatted_address")
            location = result.get("geometry", {}).get("location", {})
            lat = location.get("lat")
            lng = location.get("lng")
            place_id = result.get("place_id")

            return (
                f"Geocoding Result for '{address}':\n"
                f"• Address: {formatted_address}\n"
                f"• Location: Latitude {lat}, Longitude {lng}\n"
                f"• Place ID: {place_id}"
            )
    except Exception as e:
        return f"Error during geocoding request: {str(e)}"


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "gym",
    radius_meters: float = 3000.0,
) -> str:
    """Find nearby places of a given type (e.g., gym, park, sports_complex) using Google Places API (New).

    Args:
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.
        place_type: Type of place to search for (e.g. 'gym', 'park', 'sports_complex', 'fitness_center').
        radius_meters: Search radius in meters (default: 3000.0 meters).

    Returns:
        List of nearby places with key fields: name, address, and location coordinates.
    """
    api_key = _get_maps_api_key()
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
    }
    body = {
        "includedTypes": [place_type.lower().strip()],
        "maxResultCount": 5,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                },
                "radius": float(radius_meters),
            }
        },
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            places = data.get("places", [])

            if not places:
                return f"No nearby places found for type '{place_type}' within {radius_meters}m of ({latitude}, {longitude})."

            results = [f"Nearby Places for type '{place_type}' ({len(places)} found):"]
            for idx, p in enumerate(places, 1):
                name = p.get("displayName", {}).get("text", "Unknown Place")
                addr = p.get("formattedAddress", "No address listed")
                loc = p.get("location", {})
                lat = loc.get("latitude")
                lng = loc.get("longitude")
                results.append(
                    f"{idx}. {name}\n"
                    f"   • Address: {addr}\n"
                    f"   • Location: ({lat}, {lng})"
                )

            return "\n".join(results)
    except Exception as e:
        return f"Error searching nearby places: {str(e)}"


def generate_workout_image(
    prompt: str,
    tool_context: Optional[ToolContext] = None,
) -> str:
    """Generate an athletic visualization or motivational workout image using gemini-3.1-flash-lite-image in the global region.
    Saves the generated image as an ADK artifact in the Playground and uploads the image bytes directly to a public Cloud Storage bucket.

    Args:
        prompt: Description of the workout or fitness image to generate (e.g. 'A vibrant marathon training map at sunset').
        tool_context: ADK ToolContext injected automatically by the framework.

    Returns:
        The public Cloud Storage HTTPS URL of the generated image.
    """
    try:
        genai_client = genai.Client(
            vertexai=True,
            project=PROJECT_ID,
            location="global",
        )
        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
        )

        image_bytes = None
        mime_type = "image/jpeg"

        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not image_bytes:
            return f"Error: No image content returned for prompt '{prompt}'."

        timestamp = int(time.time())
        file_ext = "png" if "png" in mime_type.lower() else "jpg"
        filename = f"generated_workout_{timestamp}.{file_ext}"

        # 1. Save artifact in Playground panel via tool_context
        if tool_context:
            try:
                artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                tool_context.save_artifact(
                    filename=filename,
                    artifact=artifact_part,
                )
            except Exception as artifact_err:
                pass

        # 2. Upload image bytes directly to public Cloud Storage bucket
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
        return public_url

    except Exception as e:
        return f"Error generating workout image: {str(e)}"


def generate_exercise_demo_video(
    exercise_name: str,
    tool_context: Optional[ToolContext] = None,
) -> str:
    """Generate a short video demonstrating an exercise posture or movement using Google's Omni model (gemini-omni-flash-preview) in the global region.
    Saves the generated video as an ADK artifact in the Playground and uploads the video bytes directly to a public Cloud Storage bucket.

    Args:
        exercise_name: Name or description of the exercise or movement to demonstrate (e.g. 'bodyweight squat', 'pushups', 'kettlebell swing').
        tool_context: ADK ToolContext injected automatically by the framework.

    Returns:
        The public Cloud Storage HTTPS URL of the generated video.
    """
    try:
        genai_client = genai.Client(
            vertexai=True,
            project=PROJECT_ID,
            location="global",
        )
        prompt = f"Generate a short 5-second exercise demonstration video of an athlete performing {exercise_name} with proper posture in a gym setting."

        interaction = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
            response_modalities=["text", "video"],
        )

        video_bytes = None
        mime_type = "video/mp4"

        out_vid = getattr(interaction, "output_video", None)
        if isinstance(out_vid, dict):
            video_bytes = out_vid.get("data")
            mime_type = out_vid.get("mime_type", "video/mp4") or "video/mp4"
        elif out_vid:
            video_bytes = getattr(out_vid, "data", None)
            mime_type = getattr(out_vid, "mime_type", "video/mp4") or "video/mp4"

        if isinstance(video_bytes, str):
            import base64
            video_bytes = base64.b64decode(video_bytes)

        if not video_bytes:
            return f"Error: No video bytes returned for exercise '{exercise_name}'."

        timestamp = int(time.time())
        filename = f"exercise_demo_{timestamp}.mp4"

        # 1. Save artifact in Playground panel via tool_context
        if tool_context:
            try:
                artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
                tool_context.save_artifact(
                    filename=filename,
                    artifact=artifact_part,
                )
            except Exception as artifact_err:
                pass

        # 2. Upload video bytes directly to public Cloud Storage bucket
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
        return public_url

    except Exception as e:
        return f"Error generating exercise demo video: {str(e)}"





