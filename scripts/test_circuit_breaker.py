import asyncio
import logging
import sys
import os

# Set up paths so we can import from core_backend/app
sys.path.append(os.path.join(os.getcwd(), 'core_backend'))

from app.utils.resilience import get_circuit_breaker, CircuitState

# Configure logging to see the circuit transitions
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

async def test_breaker_logic():
    print("--- Starting Circuit Breaker Logic Test ---")
    
    # Initialize a test breaker
    breaker = get_circuit_breaker(
        name="test_breaker", 
        failure_threshold=3, 
        recovery_timeout=2.0
    )

    async def failing_func():
        raise RuntimeError("Service is down!")

    async def success_func():
        return "OK"

    # 1. Test 3 failures to trip the circuit
    print("\n1. Triggering 3 failures...")
    for i in range(3):
        try:
            await breaker.call(failing_func)
        except Exception as e:
            print(f"Call {i+1} failed as expected: {e}")

    print(f"Current State: {breaker.state.value}")
    if breaker.state == CircuitState.OPEN:
        print("PASS: Circuit is OPEN")
    else:
        print("FAIL: Circuit should be OPEN")

    # 2. Verify that calls are blocked immediately in OPEN state
    print("\n2. Verifying blocking in OPEN state...")
    try:
        await breaker.call(success_func)
    except RuntimeError as e:
        print(f"Call blocked as expected: {e}")
        if "open" in str(e).lower():
            print("PASS: Request blocked by Circuit Breaker")

    # 3. Test Recovery (Half-Open)
    print(f"\n3. Waiting {breaker.recovery_timeout}s for recovery...")
    await asyncio.sleep(breaker.recovery_timeout + 0.5)
    
    print(f"Attempting call in potentially HALF_OPEN state...")
    result = await breaker.call(success_func)
    print(f"Result: {result}")
    
    print(f"Final State: {breaker.state.value}")
    if breaker.state == CircuitState.CLOSED:
        print("PASS: Circuit successfully CLOSED after recovery")
    else:
        print(f"FAIL: Circuit should be CLOSED, but is {breaker.state.value}")

if __name__ == "__main__":
    asyncio.run(test_breaker_logic())
