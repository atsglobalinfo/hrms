# eSSL Device Attendance Sync

Automatically sync attendance data from your eSSL biometric device to Frappe HRMS.

## Quick Start (5 minutes)

```bash
cd ~/hrms/essl_sync

# 1. Setup
./setup.sh

# 2. Configure (add your API credentials)
nano .env

# 3. Test connection
python3 test_integration.py

# 4. Run receiver
./run.sh
```

## 📚 Files

| File | Purpose |
|------|---------|
| `receiver.py` | Main Flask app that listens for device data |
| `setup.sh` | One-time setup script |
| `run.sh` | Start the receiver |
| `test_integration.py` | Verify everything works |
| `SETUP_GUIDE.md` | Detailed step-by-step guide |
| `.env` | Your configuration (create from `.env.example`) |

## 📋 Prerequisites

Before starting, make sure:
- ✓ Frappe HRMS is running on `localhost:8000`
- ✓ eSSL device is on same network (192.168.1.201)
- ✓ Device Gateway and DNS are configured

## 🔧 Configuration

1. **Get Frappe API Key:**
   - Log in to http://localhost:8000
   - Settings → My Account → API Access → Generate Keys
   - Copy Key and Secret

2. **Update `.env`:**
   ```
   FRAPPE_URL=http://127.0.0.1:8000
   API_KEY=your_key_here
   API_SECRET=your_secret_here
   ```

3. **Map Employee IDs:**
   - In Frappe, for each Employee:
   - Set "Attendance Device ID" = Device User ID
   - Must match exactly

## 🧪 Testing

```bash
# Check receiver status
curl http://localhost:8080/health

# Check integration
python3 test_integration.py

# Monitor logs
tail -f /tmp/essl_sync.log
```

## 📖 Full Guide

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for complete setup including:
- Device network configuration
- Detailed troubleshooting
- Production deployment
- API reference

## 🆘 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| Connection refused | Make sure `./run.sh` is running |
| Employee not found | Check Attendance Device ID in Frappe matches device User ID |
| No logs appearing | Verify device Server Address is set to your IP:8080 |

---

**Device**: eSSL x2008 Ver 7.0.3.100  
**Frappe**: HRMS  
**Status**: Ready to configure
