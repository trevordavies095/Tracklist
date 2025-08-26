#!/usr/bin/env python3
"""
Coverage check script for Tracklist project.
Ensures test coverage meets minimum requirements and tracks critical path coverage.
"""

import subprocess
import sys
import json
import os
from pathlib import Path

# Coverage targets
MINIMUM_OVERALL_COVERAGE = 30.0
CRITICAL_PATH_TARGETS = {
    "app/rating_service.py": 80.0,
    "app/routers/albums.py": 60.0,
    "app/auth.py": 70.0,
    "app/models.py": 50.0,
}


def run_coverage():
    """Run pytest with coverage and generate JSON report."""
    print("Running test coverage analysis...")
    print("-" * 60)
    
    # Run tests with coverage
    cmd = [
        sys.executable, "-m", "pytest",
        "--cov=app",
        "--cov-report=term-missing",
        "--cov-report=json",
        "--cov-report=html",
        "-q"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Print test output
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    return result.returncode == 0


def analyze_coverage():
    """Analyze coverage results from JSON report."""
    coverage_file = Path("coverage.json")
    
    if not coverage_file.exists():
        print("ERROR: coverage.json not found. Run tests first.")
        return False
    
    with open(coverage_file) as f:
        data = json.load(f)
    
    # Get overall coverage
    overall_coverage = data["totals"]["percent_covered"]
    
    print("\n" + "=" * 60)
    print("COVERAGE ANALYSIS RESULTS")
    print("=" * 60)
    
    # Check overall coverage
    print(f"\nOverall Coverage: {overall_coverage:.2f}%")
    print(f"Target: {MINIMUM_OVERALL_COVERAGE}%")
    
    overall_passed = overall_coverage >= MINIMUM_OVERALL_COVERAGE
    if overall_passed:
        print("✅ Overall coverage target met!")
    else:
        print(f"❌ Overall coverage below target (need {MINIMUM_OVERALL_COVERAGE - overall_coverage:.2f}% more)")
    
    # Check critical path coverage
    print("\n" + "-" * 60)
    print("Critical Path Coverage:")
    print("-" * 60)
    
    all_critical_passed = True
    for file_path, target in CRITICAL_PATH_TARGETS.items():
        if file_path in data["files"]:
            file_coverage = data["files"][file_path]["summary"]["percent_covered"]
            passed = file_coverage >= target
            symbol = "✅" if passed else "❌"
            
            print(f"{symbol} {file_path}")
            print(f"   Coverage: {file_coverage:.2f}% / Target: {target}%")
            
            if not passed:
                all_critical_passed = False
                missing = data["files"][file_path]["missing_lines"]
                if missing and len(missing) > 0:
                    # Show first few missing line ranges
                    missing_summary = str(missing[:5])
                    if len(missing) > 5:
                        missing_summary += f"... ({len(missing) - 5} more)"
                    print(f"   Missing lines: {missing_summary}")
        else:
            print(f"⚠️  {file_path} - File not found in coverage report")
            all_critical_passed = False
    
    # Generate coverage trend (if history exists)
    print("\n" + "-" * 60)
    track_coverage_trend(overall_coverage)
    
    # Summary
    print("\n" + "=" * 60)
    print("COVERAGE CHECK SUMMARY")
    print("=" * 60)
    
    if overall_passed:
        print("✅ Overall coverage requirement: PASSED")
    else:
        print("❌ Overall coverage requirement: FAILED")
    
    if all_critical_passed:
        print("✅ Critical path coverage: ALL PASSED")
    else:
        print("❌ Critical path coverage: SOME FAILED")
    
    print("\n📊 HTML coverage report generated at: htmlcov/index.html")
    
    return overall_passed


def track_coverage_trend(current_coverage):
    """Track coverage trend over time."""
    history_file = Path(".coverage_history.json")
    
    # Load existing history
    if history_file.exists():
        with open(history_file) as f:
            history = json.load(f)
    else:
        history = []
    
    # Add current coverage
    from datetime import datetime
    history.append({
        "date": datetime.now().isoformat(),
        "coverage": round(current_coverage, 2)
    })
    
    # Keep only last 10 entries
    history = history[-10:]
    
    # Save updated history
    with open(history_file, "w") as f:
        json.dump(history, f, indent=2)
    
    # Show trend
    if len(history) > 1:
        prev_coverage = history[-2]["coverage"]
        change = current_coverage - prev_coverage
        
        if change > 0:
            print(f"📈 Coverage increased by {change:.2f}% from last run")
        elif change < 0:
            print(f"📉 Coverage decreased by {abs(change):.2f}% from last run")
        else:
            print("➡️  Coverage unchanged from last run")
        
        # Show recent history
        print("\nRecent coverage history:")
        for entry in history[-5:]:
            date = entry["date"].split("T")[0]
            print(f"  {date}: {entry['coverage']:.2f}%")


def main():
    """Main entry point."""
    print("🔍 Tracklist Coverage Check")
    print("=" * 60)
    
    # Change to project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)
    
    # Run tests with coverage
    tests_passed = run_coverage()
    
    if not tests_passed:
        print("\n⚠️  Some tests failed. Coverage may be incomplete.")
    
    # Analyze coverage
    coverage_met = analyze_coverage()
    
    # Exit with appropriate code
    if not coverage_met:
        print("\n❌ Coverage requirements not met. Please add more tests.")
        sys.exit(1)
    else:
        print("\n✅ All coverage requirements met!")
        sys.exit(0)


if __name__ == "__main__":
    main()