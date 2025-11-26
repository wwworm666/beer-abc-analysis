#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Простой тест модулей - проверяет импорты Python модулей
"""

import sys
import os

print("=" * 80)
print("Testing Module Imports")
print("=" * 80)

tests_passed = 0
tests_failed = 0

# Test 1: Core config
print("\n[TEST 1] Import core modules...")
try:
    from core.olap_reports import OlapReports
    from core.draft_analysis import DraftAnalysis
    from core.waiter_analysis import WaiterAnalysis
    from core.taps_manager import TapsManager
    print("[OK] Core modules imported successfully")
    tests_passed += 1
except Exception as e:
    print(f"[ERROR] Failed to import core modules: {e}")
    tests_failed += 1

# Test 2: Dashboard modules
print("\n[TEST 2] Import dashboard modules...")
try:
    from dashboardNovaev.dashboard_analysis import DashboardMetrics
    from dashboardNovaev.plans_manager import PlansManager
    from dashboardNovaev.weeks_generator import WeeksGenerator
    print("[OK] Dashboard modules imported successfully")
    tests_passed += 1
except Exception as e:
    print(f"[ERROR] Failed to import dashboard modules: {e}")
    tests_failed += 1

# Test 3: Backend modules
print("\n[TEST 3] Import backend modules...")
try:
    from dashboardNovaev.backend.venues_manager import VenuesManager
    from dashboardNovaev.backend.comparison_calculator import ComparisonCalculator
    from dashboardNovaev.backend.trends_analyzer import TrendsAnalyzer
    from dashboardNovaev.backend.export_manager import ExportManager
    print("[OK] Backend modules imported successfully")
    tests_passed += 1
except Exception as e:
    print(f"[ERROR] Failed to import backend modules: {e}")
    tests_failed += 1

# Test 4: Flask app
print("\n[TEST 4] Import Flask app...")
try:
    from app import app
    print("[OK] Flask app imported successfully")
    tests_passed += 1
except Exception as e:
    print(f"[ERROR] Failed to import Flask app: {e}")
    tests_failed += 1

# Test 5: Check Flask routes
print("\n[TEST 5] Check Flask routes...")
try:
    from app import app
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append(str(rule))

    important_routes = [
        '/api/draft-analyze',
        '/api/venues',
        '/test_modules',
        '/dashboard',
    ]

    found_routes = [r for r in important_routes if any(ir in r for ir in important_routes)]

    print(f"[OK] Found {len(routes)} routes in Flask app")
    print(f"   Important routes present:")
    for route in important_routes:
        if any(route in r for r in routes):
            print(f"      [+] {route}")
        else:
            print(f"      [-] {route} (NOT FOUND)")
    tests_passed += 1
except Exception as e:
    print(f"[ERROR] Failed to check routes: {e}")
    tests_failed += 1

# Test 6: Check data files
print("\n[TEST 6] Check data files...")
try:
    data_files = [
        'data/taps_data.json',
        'data/plansdashboard.json',
        'static/js/dashboard/core/config.js',
        'static/js/dashboard/core/api.js',
        'static/js/dashboard/core/state.js',
    ]

    found = 0
    missing = 0

    for file_path in data_files:
        if os.path.exists(file_path):
            found += 1
            print(f"   [+] {file_path}")
        else:
            missing += 1
            print(f"   [-] {file_path} (MISSING)")

    print(f"[OK] Data files check: {found} found, {missing} missing")
    tests_passed += 1
except Exception as e:
    print(f"[ERROR] Failed to check data files: {e}")
    tests_failed += 1

# Summary
print("\n" + "=" * 80)
print(f"SUMMARY: {tests_passed} passed, {tests_failed} failed")
print("=" * 80)

if tests_failed > 0:
    print("\nWARNING: Some tests failed. Check the errors above.")
    sys.exit(1)
else:
    print("\nAll tests passed! The application is ready to run.")
    sys.exit(0)
