#!/usr/bin/env python3
"""
eSSL ADMS Receiver - Listens for attendance logs from eSSL device
and pushes them to Frappe HRMS Employee Checkin doctype
"""

from flask import Flask, request, jsonify
import requests
from datetime import datetime
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ─── Configuration ───────────────────────────────
# For local Docker setup, use docker network DNS or host machine IP
FRAPPE_URL = os.getenv('FRAPPE_URL', 'http://127.0.0.1:8000')
API_KEY = os.getenv('API_KEY', '')
API_SECRET = os.getenv('API_SECRET', '')
DEVICE_ID = os.getenv('DEVICE_ID', 'eSSL-x2008')

# Map device serial numbers to forced log type
# Set IN_DEVICE_SN and OUT_DEVICE_SN in .env or here directly
IN_DEVICE_SN = os.getenv('IN_DEVICE_SN', '')   # e.g. '6426144200014'
OUT_DEVICE_SN = os.getenv('OUT_DEVICE_SN', '')  # e.g. '6426144200099'

# For logging
LOG_FILE = os.getenv('LOG_FILE', '/tmp/essl_sync.log')

def log_message(msg):
    """Log message with timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {msg}"
    print(log_msg)
    with open(LOG_FILE, 'a') as f:
        f.write(log_msg + '\n')

def handle_cdata_get():
    sn = request.args.get('SN', 'unknown')
    log_message(f"Device handshake from SN={sn}")
    # Use today's date as stamp so device only sends records from today
    today_stamp = datetime.now().strftime('%Y-%m-%d') + ' 00:00:00'
    response = (
        f"GET OPTION FROM: {sn}\n"
        f"ATTLOGStamp={today_stamp}\n"
        "OPERLOGStamp=9999\n"
        "ATTPHOTOStamp=0\n"
        "ErrorDelay=30\n"
        "Delay=10\n"
        "TransTimes=00:00;23:59\n"
        "TransInterval=1\n"
        "TransFlag=TransData AttLog\n"
        "Realtime=1\n"
        "Encrypt=None\n"
    )
    return response, 200

def handle_cdata_post():
    table = request.args.get('table', '')
    sn = request.args.get('SN', 'unknown')

    if table != 'ATTLOG':
        log_message(f"Non-attendance POST from SN={sn} table={table}")
        return "OK", 200

    try:
        data = request.data.decode('utf-8')
        lines = [l for l in data.strip().split('\n') if l.strip()]
        log_message(f"Received {len(lines)} attendance record(s) from SN={sn}")

        today = datetime.now().date()
        for line in lines:
            parts = line.strip().split('\t')
            if len(parts) >= 2:
                user_id = parts[0]
                timestamp_str = parts[1]

                dt = None
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%d/%m/%Y %H:%M:%S']:
                    try:
                        dt = datetime.strptime(timestamp_str, fmt)
                        break
                    except ValueError:
                        continue
                if dt is None:
                    dt = datetime.now()

                if dt.date() < today:
                    continue  # skip historical records

                # Determine log type: force based on device SN, else use status code
                if IN_DEVICE_SN and sn == IN_DEVICE_SN:
                    log_type = 'IN'
                elif OUT_DEVICE_SN and sn == OUT_DEVICE_SN:
                    log_type = 'OUT'
                else:
                    status = parts[2] if len(parts) > 2 else '0'
                    log_type = 'OUT' if status in ('1', '5') else 'IN'

                log_message(f"  Record: user={user_id} time={timestamp_str} type={log_type}")
                push_to_frappe(user_id, dt, log_type)

        return "OK", 200

    except Exception as e:
        log_message(f"ERROR in cdata POST: {str(e)}")
        return "ERROR", 500

@app.route('/iclock/cdata', methods=['GET', 'POST'])
@app.route('/iclock/cdata.aspx', methods=['GET', 'POST'])
def receive_attendance():
    if request.method == 'GET':
        return handle_cdata_get()
    return handle_cdata_post()

@app.route('/iclock/getrequest', methods=['GET', 'POST'])
@app.route('/iclock/getrequest.aspx', methods=['GET', 'POST'])
def get_request():
    log_message("Device getrequest received")
    return "OK", 200

@app.route('/iclock/devicecmd', methods=['POST'])
@app.route('/iclock/devicecmd.aspx', methods=['POST'])
def device_cmd():
    log_message("Device command received")
    return "OK", 200

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok"}), 200

def get_employee_by_pin(pin, headers):
    """Look up Frappe Employee name by attendance_device_id (eSSL PIN)"""
    try:
        url = f"{FRAPPE_URL}/api/resource/Employee"
        params = {
            "filters": f'[["attendance_device_id","=","{pin}"]]',
            "fields": '["name","employee_name"]',
            "limit": 1
        }
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json().get('data', [])
            if data:
                return data[0]['name'], data[0]['employee_name']
    except Exception as e:
        log_message(f"ERROR looking up PIN {pin}: {str(e)}")
    return None, None

def push_to_frappe(pin, timestamp, log_type='IN'):
    """
    Push attendance log to Frappe HRMS Employee Checkin doctype
    """
    if not API_KEY or not API_SECRET:
        log_message(f"ERROR: API credentials not configured. Skipping sync for PIN {pin}")
        return False

    headers = {
        "Authorization": f"token {API_KEY}:{API_SECRET}",
        "Content-Type": "application/json"
    }

    employee_id, employee_name = get_employee_by_pin(pin, headers)
    if not employee_id:
        log_message(f"✗ PIN {pin} → No matching Employee found (set attendance_device_id={pin} on the Employee record)")
        return False

    log_message(f"  PIN {pin} → Employee: {employee_id} ({employee_name})")

    payload = {
        "doctype": "Employee Checkin",
        "employee": employee_id,
        "time": timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        "log_type": log_type,
        "device_id": DEVICE_ID
    }
    
    try:
        url = f"{FRAPPE_URL}/api/resource/Employee%20Checkin"
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            log_message(f"✓ PIN {pin} ({employee_name}) {log_type} @ {timestamp} → Frappe (Success)")
            return True
        else:
            log_message(f"✗ PIN {pin} ({employee_id}) → Frappe (HTTP {response.status_code}: {response.text})")
            return False

    except requests.exceptions.RequestException as e:
        log_message(f"✗ PIN {pin} → Frappe (Connection Error: {str(e)})")
        return False
    except Exception as e:
        log_message(f"✗ PIN {pin} → Frappe (Error: {str(e)})")
        return False

if __name__ == '__main__':
    log_message("=" * 60)
    log_message("eSSL ADMS Receiver Started")
    log_message(f"Frappe URL: {FRAPPE_URL}")
    log_message(f"Device ID: {DEVICE_ID}")
    log_message("=" * 60)
    
    # Run Flask app
    app.run(host='0.0.0.0', port=80, debug=False)
