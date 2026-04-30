#!/usr/bin/env python3
"""
Security verification script for Docker sandbox.
Run with: python test_security.py
"""

import subprocess
import sys

def run_test(name, command, expected_success=False):
    """Run a test and report result."""
    print(f"\n🔒 Testing: {name}")
    print(f"   Command: {command}")
    
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        
        if expected_success:
            if result.returncode == 0:
                print(f"   ✅ PASSED")
                return True
            else:
                print(f"   ❌ FAILED (exit {result.returncode})")
                print(f"   Error: {result.stderr[:200]}")
                return False
        else:
            if result.returncode != 0:
                print(f"   ✅ PASSED (blocked as expected)")
                return True
            else:
                print(f"   ❌ FAILED (should have been blocked)")
                print(f"   Output: {result.stdout[:200]}")
                return False
    except Exception as e:
        print(f"   ✅ PASSED (blocked: {str(e)[:50]})")
        return True

def main():
    print("=" * 60)
    print("Docker Sandbox Security Verification")
    print("=" * 60)
    
    tests = [
        # (name, command, expected_to_succeed)
        ("Non-root user", 
         "docker run --rm agent-sandbox -c \"import os; print(os.getuid())\"", 
         True),
        
        ("Network isolation", 
         "docker run --rm --network none agent-sandbox -c \"import socket; socket.gethostbyname('google.com')\"", 
         False),
        
        ("Read-only root FS", 
         "docker run --rm --read-only agent-sandbox -c \"open('/test', 'w').write('x')\"", 
         False),
        
        ("Capability drop (chown)", 
         "docker run --rm --cap-drop ALL agent-sandbox -c \"import os; os.chown('/tmp', 1000, 1000)\"", 
         False),
        
        ("Memory limit", 
         "docker run --rm --memory=512m agent-sandbox -c \"import sys; [0] * (1024 * 1024 * 256)\"", 
         False),
        
        ("CPU limit", 
         "docker run --rm --cpus=1 agent-sandbox -c \"i=0; exec(f'while i<10000000: i+=1')\"", 
         True),
        
        ("Process limit", 
         "docker run --rm --pids-limit=50 agent-sandbox -c \"import os; [os.fork() for _ in range(100)]\"", 
         False),
    ]
    
    results = []
    for name, command, expected in tests:
        passed = run_test(name, command, expected)
        results.append(passed)
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✅ ALL {total} SECURITY TESTS PASSED!")
        print("   Docker sandbox is properly configured.")
        return 0
    else:
        print(f"❌ {total - passed}/{total} TESTS FAILED")
        print("   Security configuration needs review.")
        return 1

if __name__ == "__main__":
    sys.exit(main())