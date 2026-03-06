import subprocess
import sys
import time
import os

def run_command(command, description, exit_on_fail=True):
    print(f"\n[{time.strftime('%H:%M:%S')}] ⏳ {description}...")
    print(f"    > {command}")
    
    # We use shell=True to allow for cross-platform execution (Windows/Linux)
    process = subprocess.Popen(
        command, 
        shell=True, 
        stdout=sys.stdout,
        stderr=sys.stderr
    )
    process.communicate()
    
    if process.returncode != 0:
        print(f"\n❌ ERROR: '{description}' failed with exit code {process.returncode}.")
        if exit_on_fail:
            sys.exit(process.returncode)
    else:
        print(f"✅ SUCCESS: {description}")

def main():
    print("==================================================")
    print("🚀 Smart-Bot Automated Test Runner (Clean Slate) 🚀")
    print("==================================================\n")
    
    # Ensure we are in the project root
    if not os.path.exists("docker-compose.yml"):
        print("❌ ERROR: Must run this script from the project root (where docker-compose.yml is).")
        sys.exit(1)

    # 1. Teardown
    run_command("docker-compose down -v", "Tearing down existing containers and volumes")
    
    # 2. Rebuild strictly without cache
    run_command("docker-compose build --no-cache", "Rebuilding Docker images without cache")
    
    # 3. Spin up infrastructure + backend in detached mode
    run_command("docker-compose --profile backend up -d", "Spinning up infrastructure (Postgres, Redis, Backend)")
    
    # 4. Wait for Database to be ready (Primitive wait, can be enhanced with tenacity later)
    print("\n⏳ Waiting 15 seconds for PostgreSQL and Redis to initialize...")
    time.sleep(15)
    
    # 5. Run Alembic Migrations
    run_command("docker-compose exec core_backend alembic upgrade head", "Running Alembic Database Migrations")
    
    # 6. Run Database Seeder
    run_command("docker-compose exec core_backend python scripts/seed.py", "Seeding Mock Database (UserProfiles & RAG Vectors)")
    
    # 7. Execute Pytest Suite
    print("\n==================================================")
    print("🧪 Executing Pytest Scenario Suite 🧪")
    print("==================================================")
    run_command("docker-compose exec core_backend pytest -v tests/", "Running Pytest", exit_on_fail=False)
    
    print("\n==================================================")
    print("🏁 Test Run Completed 🏁")
    print("To keep the environment clean, you can run: docker-compose down -v")
    print("==================================================")

if __name__ == "__main__":
    main()
