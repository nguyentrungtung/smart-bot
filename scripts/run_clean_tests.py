import subprocess
import sys
import os
import time

def run_command(command, cwd=None):
    """
    Helper to run a system command and print output.
    """
    print(f"\n> Running: {command}", flush=True)
    result = subprocess.run(command, shell=True, cwd=cwd)
    if result.returncode != 0:
        print(f"Error: Command failed with exit code {result.returncode}", flush=True)
        sys.exit(1)

def main():
    """
    Master script to automate Docker teardown, rebuild, and pytest.
    Ensures a clean, reproducible state for integration testing.
    """
    print("=== Smart-Bot Full-Stack Clean Test Suite ===", flush=True)

    # Profiles to include
    profiles = "--profile infra --profile backend --profile tools"

    # 0. Generate JWT Keys if missing
    print("\n[0/5] Ensuring JWT Keypair exists...", flush=True)
    run_command("python scripts/generate_jwt_keys.py")

    # 1. Teardown existing containers and volumes

    print("\n[1/5] Tearing down environment...", flush=True)
    run_command(f"docker-compose {profiles} down -v")

    # 2. Rebuild and Start services in background
    print("\n[2/5] Building and starting services...", flush=True)
    run_command(f"docker-compose {profiles} up --build -d")

    # 3. Wait for DB to be ready
    print("\n[3/5] Waiting for services to initialize (30s)...", flush=True)
    time.sleep(30) # High-quality PG and LiteLLM wait

    # 4. Run Database Seeding
    print("\n[4/5] Seeding database with mock RAG data...", flush=True)
    run_command(f"docker-compose {profiles} exec core_backend python scripts/seed_db.py")

    # 5. Execute Pytest Suites
    print("\n[5/5] Executing automated test suites...", flush=True)
    # Run both unit and scenario tests
    run_command(f"docker-compose {profiles} exec core_backend pytest -v")


    print("\n=== All Tests Passed Successfully! ===", flush=True)

if __name__ == "__main__":
    main()

