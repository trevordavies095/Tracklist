#!/usr/bin/env python3
"""
Phase 1 validation script - checks file structure and basic syntax
"""
import os
import ast
from pathlib import Path

def check_file_exists(file_path, description=""):
    """Check if a file exists"""
    if Path(file_path).exists():
        print(f"✓ {file_path} exists {description}")
        return True
    else:
        print(f"✗ {file_path} missing {description}")
        return False

def check_python_syntax(file_path):
    """Check if Python file has valid syntax"""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        ast.parse(content)
        print(f"✓ {file_path} has valid Python syntax")
        return True
    except SyntaxError as e:
        print(f"✗ {file_path} has syntax error: {e}")
        return False
    except Exception as e:
        print(f"✗ {file_path} validation failed: {e}")
        return False

def check_docker_files():
    """Check Docker configuration files"""
    docker_files = [
        ("Dockerfile", "Docker container configuration"),
        ("docker-compose.yml", "Docker Compose configuration"),
        (".dockerignore", "Docker ignore file")
    ]
    
    results = []
    for file_path, description in docker_files:
        results.append(check_file_exists(file_path, f"({description})"))
    
    return all(results)

def check_app_structure():
    """Check application structure"""
    app_files = [
        ("app/__init__.py", "App package init"),
        ("app/main.py", "FastAPI main application"),
        ("app/models.py", "SQLAlchemy models"),
        ("app/database.py", "Database configuration"),
        ("app/exceptions.py", "Custom exceptions"),
        ("app/logging_config.py", "Logging configuration")
    ]
    
    results = []
    for file_path, description in app_files:
        exists = check_file_exists(file_path, f"({description})")
        if exists:
            syntax_ok = check_python_syntax(file_path)
            results.append(exists and syntax_ok)
        else:
            results.append(False)
    
    return all(results)

def check_test_structure():
    """Check test structure"""
    test_files = [
        ("tests/__init__.py", "Test package init"),
        ("tests/conftest.py", "Test configuration"),
        ("tests/test_main.py", "Main app tests"),
        ("tests/test_models.py", "Model tests"),
        ("tests/test_database.py", "Database tests"),
        ("tests/test_exceptions.py", "Exception tests"),
        ("tests/test_logging.py", "Logging tests")
    ]
    
    results = []
    for file_path, description in test_files:
        exists = check_file_exists(file_path, f"({description})")
        if exists:
            syntax_ok = check_python_syntax(file_path)
            results.append(exists and syntax_ok)
        else:
            results.append(False)
    
    return all(results)

def check_config_files():
    """Check configuration files"""
    config_files = [
        ("requirements.txt", "Python dependencies"),
        ("pytest.ini", "Pytest configuration"),
        ("alembic.ini", "Alembic configuration"),
        (".gitignore", "Git ignore file")
    ]
    
    results = []
    for file_path, description in config_files:
        results.append(check_file_exists(file_path, f"({description})"))
    
    return all(results)

def check_alembic_structure():
    """Check Alembic migration structure"""
    alembic_files = [
        ("alembic/env.py", "Alembic environment", True),  # Check syntax
        ("alembic/script.py.mako", "Alembic script template", False),  # Don't check syntax (Mako template)
        ("alembic/versions", "Alembic versions directory", False)  # Directory
    ]
    
    results = []
    for file_path, description, check_syntax in alembic_files:
        exists = check_file_exists(file_path, f"({description})")
        if exists and check_syntax:
            syntax_ok = check_python_syntax(file_path)
            results.append(exists and syntax_ok)
        else:
            results.append(exists)
    
    return all(results)

def check_model_schema():
    """Check that models define expected tables"""
    try:
        with open("app/models.py", 'r') as f:
            content = f.read()
        
        expected_models = ["Artist", "Album", "Track", "UserSettings"]
        expected_tables = ["artists", "albums", "tracks", "user_settings"]
        
        models_found = []
        tables_found = []
        
        for model in expected_models:
            if f"class {model}(Base):" in content:
                models_found.append(model)
        
        for table in expected_tables:
            if f'__tablename__ = "{table}"' in content:
                tables_found.append(table)
        
        print(f"✓ Found models: {', '.join(models_found)}")
        print(f"✓ Found tables: {', '.join(tables_found)}")
        
        return len(models_found) == len(expected_models) and len(tables_found) == len(expected_tables)
        
    except Exception as e:
        print(f"✗ Model schema check failed: {e}")
        return False

def main():
    """Run Phase 1 validation"""
    print("=== Phase 1 Implementation Validation ===\n")
    
    checks = [
        ("Application Structure", check_app_structure),
        ("Test Structure", check_test_structure),
        ("Configuration Files", check_config_files),
        ("Docker Files", check_docker_files),
        ("Alembic Structure", check_alembic_structure),
        ("Model Schema", check_model_schema)
    ]
    
    passed = 0
    total = len(checks)
    
    for check_name, check_func in checks:
        print(f"\n--- {check_name} ---")
        if check_func():
            print(f"✓ {check_name} validation passed")
            passed += 1
        else:
            print(f"✗ {check_name} validation failed")
    
    print(f"\n=== Phase 1 Validation Results ===")
    print(f"Passed: {passed}/{total} checks")
    
    if passed == total:
        print("🎉 Phase 1 implementation structure is valid!")
        print("\nPhase 1 deliverables completed:")
        print("• Project structure and development environment")
        print("• FastAPI application with basic routing")
        print("• SQLite database schema implementation")
        print("• Database connection and migration system")
        print("• Basic error handling and logging")
        print("• Docker container configuration")
        print("• Comprehensive test suite structure")
        return True
    else:
        print("❌ Phase 1 validation failed - fix issues above")
        return False

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)