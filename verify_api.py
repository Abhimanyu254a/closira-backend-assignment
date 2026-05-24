import urllib.request
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def make_request(method, path, data=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    req_data = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as resp:
            status_code = resp.status
            body = resp.read().decode("utf-8")
            return status_code, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, json.loads(body) if body else str(e)
    except Exception as e:
        return 0, str(e)

def run_tests():
    print("===== STARTING API VERIFICATION =======")
    
    # 1. Health Check
    print("\n--- 1. Testing GET /health ---")
    code, res = make_request("GET", "/health")
    print(f"Status: {code}")
    print(json.dumps(res, indent=2))
    
    # 2. Create Enquiry - SOP Matching Case
    print("\n--- 2. Testing POST /enquiry (Should Match 'booking_enquiry' SOP) ---")
    payload = {
        "channel": "whatsapp",
        "customer_name": "Rahul Sharma",
        "message": "Hi, I want to book an appointment for next Monday."
    }
    code, res = make_request("POST", "/enquiry", payload)
    print(f"Status: {code}")
    print(json.dumps(res, indent=2))
    
    job_id_sop = res.get("job_id") if isinstance(res, dict) else None
    
    # 3. Create Enquiry - Auto-escalation Case (no SOP matching)
    print("\n---===== 3. Testing POST /enquiry (Should Auto-Escalate) ---===")
    payload_escalate = {
        "channel": "email",
        "customer_name": "John Doe",
        "message": "Hello, I am just writing to say hello to everyone."
    }
    code_esc, res_esc = make_request("POST", "/enquiry", payload_escalate)
    print(f"Status: {code_esc}")
    print(json.dumps(res_esc, indent=2))
    
    job_id_esc = res_esc.get("job_id") if isinstance(res_esc, dict) else None

    # Wait for background task execution (FastAPI runs it almost instantly)
    time.sleep(1)
    
    # 4. Check history for SOP Matching enquiry
    if job_id_sop:
        print(f"\n---==== 4. Testing GET /enquiry/{job_id_sop}/history (SOP Case) ---=====")
        code, res = make_request("GET", f"/enquiry/{job_id_sop}/history")
        print(f"Status: {code}")
        print(json.dumps(res, indent=2))
        
        # 5. Schedule a follow-up on SOP matched enquiry
        print(f"\n--- 5. Testing POST /enquiry/{job_id_sop}/follow-up ---")
        followup_payload = {
            "delay_minutes": 30,
            "message_template": "Hi {customer_name}, following up on your appointment request."
        }
        code, res = make_request("POST", f"/enquiry/{job_id_sop}/follow-up", followup_payload)
        print(f"Status: {code}")
        print(json.dumps(res, indent=2))
        
        # Check history again
        print(f"\n====== 6. Testing GET /enquiry/{job_id_sop}/history (After Follow-up) ===")
        code, res = make_request("GET", f"/enquiry/{job_id_sop}/history")
        print(f"Status: {code}")
        print(json.dumps(res, indent=2))
        
    # 6. Check history for auto-escalated enquiry
    if job_id_esc:
        print(f"\n--- 7. Testing GET /enquiry/{job_id_esc}/history (Auto-escalate Case) ---")
        code, res = make_request("GET", f"/enquiry/{job_id_esc}/history")
        print(f"Status: {code}")
        print(json.dumps(res, indent=2))
        
        # 7. Try to schedule follow-up on escalated enquiry (should fail with 400)
        print(f"\n--- 8. Testing POST /enquiry/{job_id_esc}/follow-up (Should fail) ---")
        followup_payload = {
            "delay_minutes": 30,
            "message_template": "Hi {customer_name}, following up on your escalated case."
        }
        code, res = make_request("POST", f"/enquiry/{job_id_esc}/follow-up", followup_payload)
        print(f"Status: {code}")
        print(json.dumps(res, indent=2))

        # 8. Escalate an enquiry manually
        if job_id_sop:
            print(f"\n======--- 9. Testing POST /enquiry/{job_id_sop}/escalate (Manual Escalation) ---======")
            escalate_payload = {
                "reason": "Customer needs highly specialized assistance."
            }
            code, res = make_request("POST", f"/enquiry/{job_id_sop}/escalate", escalate_payload)
            print(f"Status: {code}")
            print(json.dumps(res, indent=2))
            
            # Check history after manual escalation
            print(f"\n===--- 10. Testing GET /enquiry/{job_id_sop}/history (After Manual Escalation) ---===")
            code, res = make_request("GET", f"/enquiry/{job_id_sop}/history")
            print(f"Status: {code}")
            print(json.dumps(res, indent=2))

    print("\n======= VERIFICATION COMPLETE =========")

if __name__ == "__main__":
    run_tests()
