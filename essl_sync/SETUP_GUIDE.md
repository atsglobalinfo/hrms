# eSSL Device Integration with Frappe HRMS

This guide will help you sync attendance data from your eSSL x2008 biometric device directly to your Frappe HRMS instance.

## 📋 Overview

```
eSSL Device (192.168.1.201:6763)
    ↓ ADMS Push (HTTP)
Flask Receiver (0.0.0.0:8080)
    ↓ REST API
Frappe HRMS API (localhost:8000)
    ↓
Employee Checkin DocType
    ↓
Auto-generated Attendance Records
```

## 🔧 Phase 1: Fix Device Network Configuration

### Issue: Your device currently has:
- Gateway: 0.0.0.0 ❌ (incorrect)
- DNS: 0.0.0.0 ❌ (not set)
- TCP COMM Port: 6763 ✓ (correct)

### Fix on Device:
1. **On the eSSL device**, press Menu
2. Go to: `Comm → Ethernet Settings`
3. Update:
   - **Gateway**: `192.168.1.1` (or your router IP)
   - **DNS**: `8.8.8.8` (or your ISP DNS)
4. Save and reboot device

### Verify:
```bash
# From your server, test connectivity
ping 192.168.1.201
```

## 🚀 Phase 2: Set Up Flask Receiver (Attendance Listener)

### 2.1 Install Dependencies

```bash
cd ~/hrms/essl_sync
chmod +x setup.sh
./setup.sh
```

This will:
- Create Python virtual environment
- Install Flask, requests, gunicorn
- Generate `.env` configuration file

### 2.2 Configure Frappe API Credentials

**In your browser**, log in to Frappe:
1. Go to `http://localhost:8000`
2. Login as Administrator / admin
3. Navigate to: **Settings → My Account**
4. Click **"API Access"**
5. Click **"Generate Keys"**
6. Copy the **API Key** and **API Secret**

**Update `.env` file**:
```bash
cd ~/hrms/essl_sync
nano .env
```

Paste your credentials:
```
FRAPPE_URL=http://127.0.0.1:8000
API_KEY=your_api_key_here
API_SECRET=your_api_secret_here
DEVICE_ID=eSSL-x2008
```

Save (Ctrl+O, Enter, Ctrl+X)

### 2.3 Test Flask Receiver

```bash
cd ~/hrms/essl_sync
source venv/bin/activate
python3 receiver.py
```

You should see:
```
============================================================
eSSL ADMS Receiver Started
Frappe URL: http://127.0.0.1:8000
Device ID: eSSL-x2008
============================================================
 * Running on http://0.0.0.0:8080
```

✓ Keep this terminal running

## 📱 Phase 3: Configure eSSL Device ADMS Push

On the **eSSL device**:

1. Press **Menu** → **Comm → ADMS**
2. Enable: **Domain Name → ON**
3. Set **Server Address**:
   - **For Local Network (Recommended for now)**:
     ```
     192.168.1.XXX:8080
     ```
     (Replace XXX with your server's IP address on the same network)
   
   - **For Remote/Cloud Setup**:
     ```
     yourdomain.com:8080
     ```
     (Requires port forwarding on your router)

4. **Enable Proxy: OFF**
5. **Port: 8080** (or as configured in receiver)
6. Save and Test Connection

### Verify Device Connection:

On your server terminal, when device connects, you'll see:
```
[2024-06-29 10:30:45] Device handshake received
[2024-06-29 10:30:46] Received 1 attendance record(s)
[2024-06-29 10:30:46] ✓ Employee 12 @ 2024-06-29 10:30:45 → Frappe (Success)
```

## 👤 Phase 4: Map Employee IDs in Frappe

For the sync to work, your eSSL device User IDs must match Frappe Employee IDs.

### In Frappe:
1. Navigate to: **HR → Employee List**
2. Open an employee record
3. Go to: **Attendance & Leave Details** section
4. Set **"Attendance Device ID"** to the **User ID** enrolled on the eSSL device
   - Example: If you enrolled employee as "12" on device → set this to "12"

### On eSSL Device:
When enrolling fingerprints:
1. **Menu → User Management → New User**
2. **User ID**: must match Frappe Employee ID
3. **Name**: Employee name
4. Enroll fingerprints

**Mapping Example:**
```
Device User ID: 12    → Frappe Employee ID: 12      ✓
Device User ID: 101   → Frappe Employee ID: EMP-101 ✗ (Won't match - use same format)
```

## 🔄 Phase 5: Automate the Receiver (Production)

### Option A: Systemd Service (Linux)

Create `/etc/systemd/system/essl-receiver.service`:
```ini
[Unit]
Description=eSSL ADMS Receiver
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/izhaar/hrms/essl_sync
Environment="PATH=/home/izhaar/hrms/essl_sync/venv/bin"
ExecStart=/home/izhaar/hrms/essl_sync/venv/bin/python3 receiver.py
Restart=always
RestartSec=10
User=izhaar

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable essl-receiver
sudo systemctl start essl-receiver

# Check status
sudo systemctl status essl-receiver

# View logs
sudo journalctl -u essl-receiver -f
```

### Option B: Screen/Tmux (Simple)

```bash
screen -S essl-receiver
cd ~/hrms/essl_sync && source venv/bin/activate && python3 receiver.py

# Detach: Ctrl+A, then D
# Reattach: screen -r essl-receiver
```

### Option C: Docker Compose

Add to your `docker-compose.yml` in the frappe service:
```yaml
  essl-receiver:
    image: python:3.11-slim
    working_dir: /app
    volumes:
      - ./essl_sync:/app
    environment:
      - FRAPPE_URL=http://frappe:8000
      - API_KEY=${API_KEY}
      - API_SECRET=${API_SECRET}
    ports:
      - "8080:8080"
    command: sh -c "pip install -r requirements.txt && python3 receiver.py"
    depends_on:
      - frappe
```

## ✅ Phase 6: Test End-to-End

### 1. Verify Receiver is Running:
```bash
curl http://localhost:8080/health
# Expected response: {"status":"ok"}
```

### 2. Test Frappe Connection:
Check the receiver logs for successful API calls:
```bash
tail -f /tmp/essl_sync.log
```

### 3. Punch a Finger on Device:
- Go to device: **Time & Attendance → Clock In/Out**
- Place finger on sensor
- Wait for beep

### 4. Check Frappe:
1. Go to `http://localhost:8000/app/employee-checkin`
2. You should see a new **Employee Checkin** record with:
   - Employee ID
   - Timestamp
   - Device ID: eSSL-x2008

### 5. Auto-Generate Attendance:
Enable automatic attendance calculation:
1. Go to: **Settings → HR Settings**
2. Enable: **"Auto Attendance"**
3. Frappe will now auto-mark attendance based on checkins

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Device can't connect | Check Gateway (192.168.1.1) and DNS (8.8.8.8) settings on device |
| No logs appearing | Verify Flask receiver is running on :8080 |
| Connection refused | Check if firewall blocks port 8080 |
| Employee not found | Verify Attendance Device ID matches device User ID exactly |
| Duplicate entries | Device is pushing same log twice - normal, Frappe deduplicates |
| API authentication fails | Regenerate API Key/Secret, verify in .env file |

## 📊 Monitor Integration

View all attendance data:
```bash
# Via Frappe UI
http://localhost:8000/app/employee-checkin

# Via API
curl -H "Authorization: token API_KEY:API_SECRET" \
  http://localhost:8000/api/resource/Employee%20Checkin?filters=[["Employee","=","12"]]
```

## 🔐 Security Notes

- API Keys should be kept secure - never commit `.env` to git
- For production, use HTTPS on your Frappe instance
- Restrict device to internal network only (unless remote required)
- Regularly rotate API keys
- Add firewall rules to restrict port 8080 access

## 📞 Support

If you encounter issues:
1. Check receiver logs: `tail -f /tmp/essl_sync.log`
2. Verify device connectivity: `ping 192.168.1.201`
3. Test API directly:
   ```bash
   curl -X POST http://localhost:8000/api/resource/Employee%20Checkin \
     -H "Authorization: token KEY:SECRET" \
     -H "Content-Type: application/json" \
     -d '{"doctype":"Employee Checkin","employee":"1","time":"2024-06-29 10:30:00"}'
   ```

---

**Last Updated**: June 29, 2024
**Device**: eSSL x2008 (Ver 7.0.3.100)
**Frappe**: HRMS
