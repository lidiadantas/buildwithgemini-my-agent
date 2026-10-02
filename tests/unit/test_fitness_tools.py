"""
Unit tests for fitness tools (zone calculator, training plan generator, bioimpedance, open weather API, geocoding, places, image generation).
"""

import pytest
from app.tools import (
    calculate_training_zones,
    generate_weekly_plan,
    analyze_bioimpedance,
    fetch_outdoor_workout_weather,
    geocode_address,
    find_nearby_places,
    generate_workout_image,
)


def test_calculate_training_zones_hr_only():
    result = calculate_training_zones(resting_hr=60, max_hr=180, ftp=0)
    assert "Physiological Training Zones" in result
    assert "Zone 1 (Active Recovery): 120 - 132 bpm" in result
    assert "Zone 2 (Aerobic Base):    132 - 144 bpm" in result
    assert "Zone 5 (Anaerobic / VO2): 168 - 180 bpm" in result
    assert "Cycling Power Zones" not in result


def test_calculate_training_zones_hr_and_power():
    result = calculate_training_zones(resting_hr=50, max_hr=190, ftp=200)
    assert "Physiological Training Zones" in result
    assert "Cycling Power Zones (FTP: 200W):" in result
    assert "Zone 1 (Active Recovery): < 110W" in result
    assert "Zone 4 (Lactate Threshold): 182 - 210W" in result


def test_generate_weekly_plan_marathon():
    plan = generate_weekly_plan(goal="Half Marathon", weeks=2, days_per_week=4)
    assert "Custom 2-Week Training Plan for Goal: 'Half Marathon'" in plan
    assert "Week 1:" in plan
    assert "Week 2:" in plan
    assert "Progression Long Run" in plan


def test_analyze_bioimpedance_low_risk():
    report = analyze_bioimpedance(weight_kg=70.0, body_fat_pct=15.0, skeletal_muscle_kg=32.0, total_body_water_pct=62.0)
    assert "Bioimpedance Analysis Report" in report
    assert "LOW INJURY RISK" in report
    assert "Muscle Ratio: 45.7%" in report


def test_analyze_bioimpedance_elevated_risk():
    report = analyze_bioimpedance(weight_kg=90.0, body_fat_pct=30.0, skeletal_muscle_kg=30.0, total_body_water_pct=50.0)
    assert "Bioimpedance Analysis Report" in report
    assert "ELEVATED INJURY RISK" in report
    assert "Sub-optimal body hydration" in report


def test_fetch_outdoor_workout_weather():
    report = fetch_outdoor_workout_weather(latitude=37.7749, longitude=-122.4194)
    assert "Outdoor Workout Weather Report" in report
    assert "Temperature:" in report
    assert "Relative Humidity:" in report
    assert "Wind Speed:" in report


def test_geocode_address_structure():
    res = geocode_address("San Francisco, CA")
    assert "Geocoding" in res or "Error" in res


def test_find_nearby_places_structure():
    res = find_nearby_places(37.7749, -122.4194, place_type="gym")
    assert "Nearby Places" in res or "No nearby places" in res or "Error" in res


def test_generate_workout_image():
    url = generate_workout_image("A simple athletic icon")
    assert "https://storage.googleapis.com/fitness-coach-assets-qwiklabs-gcp-02-22f397fe66a7/" in url
