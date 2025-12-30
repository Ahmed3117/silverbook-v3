"""
Test script for multi-device login system with device_id support.
Tests: signup, signin, device blocking, and device management.
"""
import requests
import json

BASE_URL = "http://127.0.0.1:9000/accounts"

# Test user credentials
TEST_USER = {
    "username": "01066666666",  # Must be phone number for students
    "password": "TestPass123!",
    "name": "Device Test User 3",
    "phone": "01066666666",
    "governorate": "Cairo",
    "education_type": "general",
    "grade": "first_secondary",
    "user_type": "student"  # Important: must be student for device restrictions
}

# Simulated device IDs (like from mobile app)
DEVICE_1_ID = "android-device-abc123-unique-id-1"
DEVICE_2_ID = "ios-device-xyz789-unique-id-2"
DEVICE_3_ID = "tablet-device-def456-unique-id-3"

def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def print_result(success, message):
    status = "✅" if success else "❌"
    print(f"{status} {message}")

def test_signup_with_device_id():
    """Test 1: Register a new user with device_id"""
    print_header("TEST 1: Signup with device_id")
    
    data = {**TEST_USER, "device_id": DEVICE_1_ID}
    
    response = requests.post(f"{BASE_URL}/signup/", json=data)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 201:
        result = response.json()
        print(f"User created: {result.get('username')}")
        print(f"Access token received: {'Yes' if result.get('access') else 'No'}")
        print_result(True, "Signup with device_id successful")
        return result.get('access'), result.get('refresh')
    else:
        print(f"Response: {response.json()}")
        print_result(False, "Signup failed")
        return None, None

def test_signin_same_device(device_id):
    """Test 2: Login from the same device (should work)"""
    print_header("TEST 2: Signin from SAME device (device_id)")
    
    data = {
        "username": TEST_USER["username"],
        "password": TEST_USER["password"],
        "device_id": device_id
    }
    
    response = requests.post(f"{BASE_URL}/signin/", json=data)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Login successful for: {result.get('username')}")
        print_result(True, "Login from same device works")
        return result.get('access')
    else:
        print(f"Response: {response.json()}")
        print_result(False, "Login failed unexpectedly")
        return None

def test_signin_new_device_under_limit(device_id):
    """Test 3: Login from a NEW device when under limit (should work)"""
    print_header("TEST 3: Signin from NEW device (under limit)")
    
    data = {
        "username": TEST_USER["username"],
        "password": TEST_USER["password"],
        "device_id": device_id
    }
    
    response = requests.post(f"{BASE_URL}/signin/", json=data)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Login successful for: {result.get('username')}")
        print_result(True, "Login from 2nd device works (under limit)")
        return result.get('access')
    else:
        print(f"Response: {response.json()}")
        print_result(False, "Login failed unexpectedly")
        return None

def test_signin_blocked_over_limit(device_id):
    """Test 4: Login from a 3rd device when limit is 2 (should be BLOCKED)"""
    print_header("TEST 4: Signin from 3rd device (SHOULD BE BLOCKED)")
    
    data = {
        "username": TEST_USER["username"],
        "password": TEST_USER["password"],
        "device_id": device_id
    }
    
    response = requests.post(f"{BASE_URL}/signin/", json=data)
    print(f"Status: {response.status_code}")
    
    result = response.json()
    print(f"Response: {result}")
    
    if response.status_code == 403:
        print_result(True, "Login correctly BLOCKED - device limit reached!")
        return True
    else:
        print_result(False, f"Expected 403, got {response.status_code}")
        return False

def test_signin_existing_device_after_limit(device_id):
    """Test 5: Login from an existing registered device (should still work)"""
    print_header("TEST 5: Signin from EXISTING device (after limit reached)")
    
    data = {
        "username": TEST_USER["username"],
        "password": TEST_USER["password"],
        "device_id": device_id
    }
    
    response = requests.post(f"{BASE_URL}/signin/", json=data)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Login successful for existing device")
        print_result(True, "Existing device can still login after limit")
        return result.get('access')
    else:
        print(f"Response: {response.json()}")
        print_result(False, "Existing device should be able to login!")
        return None

def test_get_my_devices(token):
    """Test 6: Get list of my devices"""
    print_header("TEST 6: Get my devices list")
    
    headers = {"Auth": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/my-devices/", headers=headers)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        devices = result.get('devices', [])
        print(f"Total devices: {len(devices)}")
        print(f"Max allowed: {result.get('max_allowed_devices')}")
        print("\nDevices:")
        for d in devices:
            print(f"  - ID: {d['id']}, device_id: {d['device_id']}, IP: {d['ip_address']}, Name: {d['device_name']}")
        print_result(True, f"Found {len(devices)} registered devices")
        return devices
    else:
        print(f"Response: {response.json()}")
        print_result(False, "Failed to get devices")
        return []

def test_signin_without_device_id():
    """Test 7: Login without device_id (uses IP fallback)"""
    print_header("TEST 7: Signin WITHOUT device_id (IP fallback)")
    
    # First, let's try without device_id - should use IP
    data = {
        "username": TEST_USER["username"],
        "password": TEST_USER["password"]
        # No device_id - will use IP address
    }
    
    response = requests.post(f"{BASE_URL}/signin/", json=data)
    print(f"Status: {response.status_code}")
    
    result = response.json()
    if response.status_code == 200:
        print(f"Login successful using IP fallback")
        print_result(True, "IP fallback works for existing IP")
    elif response.status_code == 403:
        print(f"Blocked (IP not in registered devices)")
        print_result(True, "IP fallback correctly blocked (different IP)")
    else:
        print(f"Response: {result}")
    
    return response.status_code

def cleanup_user():
    """Clean up: Delete test user"""
    print_header("CLEANUP: Deleting test user")
    
    # We need admin access for this - skip if not available
    print("(Manual cleanup may be needed via Django admin)")

def run_all_tests():
    print("\n" + "="*60)
    print("  MULTI-DEVICE LOGIN SYSTEM - COMPLETE TEST SUITE")
    print("  Testing with device_id support")
    print("="*60)
    
    # Test 1: Signup with device_id (Device 1)
    token1, refresh1 = test_signup_with_device_id()
    if not token1:
        print("\n⚠️  User might already exist. Trying to login instead...")
        # Try login with device 1
        data = {
            "username": TEST_USER["username"],
            "password": TEST_USER["password"],
            "device_id": DEVICE_1_ID
        }
        response = requests.post(f"{BASE_URL}/signin/", json=data)
        if response.status_code == 200:
            token1 = response.json().get('access')
            print_result(True, "Logged in with existing user")
        else:
            print(f"Login also failed: {response.json()}")
            print("\n❌ Cannot proceed without valid token")
            return
    
    # Test 2: Login again from same device (Device 1)
    test_signin_same_device(DEVICE_1_ID)
    
    # Test 3: Login from new device under limit (Device 2)
    token2 = test_signin_new_device_under_limit(DEVICE_2_ID)
    
    # Test 4: Try login from 3rd device - should be BLOCKED (Device 3)
    test_signin_blocked_over_limit(DEVICE_3_ID)
    
    # Test 5: Login from existing device should still work (Device 1)
    token_existing = test_signin_existing_device_after_limit(DEVICE_1_ID)
    
    # Test 6: Get my devices list
    if token_existing:
        devices = test_get_my_devices(token_existing)
    
    # Test 7: Login without device_id (IP fallback)
    test_signin_without_device_id()
    
    # Summary
    print_header("TEST SUMMARY")
    print("""
Expected Results:
✅ Test 1: Signup with device_id - Creates user + registers device
✅ Test 2: Login same device - Works (device already registered)
✅ Test 3: Login 2nd device - Works (under limit of 2)
✅ Test 4: Login 3rd device - BLOCKED (over limit)
✅ Test 5: Login existing device - Works (already registered)
✅ Test 6: Get my devices - Shows 2 devices
✅ Test 7: IP fallback - Works if same IP registered
    """)

if __name__ == "__main__":
    run_all_tests()
