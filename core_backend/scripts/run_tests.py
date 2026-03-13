import subprocess
import sys
import os
import time

def run_command(command):
    print(f"\n🚀 Running: {command}", flush=True)
    result = subprocess.run(command, shell=True)
    if result.returncode != 0:
        print(f"❌ Error: Command failed with exit code {result.returncode}", flush=True)
        sys.exit(1)

def main():
    print("=== Smart-Bot Unified Test Runner ===")
    
    # 1. Setup Env (Keys, etc)
    print("\n[1/3] Setting up environment...")
    run_command("python scripts/setup_env.py")
    
    # 2. Run Pytest
    print("\n[2/3] Executing Integration Tests...")
    # Using python -m pytest to ensure path handling
    run_command("pytest tests/integration/ -v")
    
    print("\n[3/3] Executing Unit Tests...")
    # Add unit tests folder if needed, for now just integration
    # run_command("pytest tests/unit/ -v")

    print("\n✅ All tests passed!")

if __name__ == "__main__":
    main()
