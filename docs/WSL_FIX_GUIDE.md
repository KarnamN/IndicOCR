# WSL Catastrophic Failure Fix Guide

## Error
```
Catastrophic failure
Error code: Wsl/Service/E_UNEXPECTED
```

## Quick Fixes (Try in Order)

### Fix 1: Restart WSL Service (Fastest)
Open PowerShell as Administrator and run:

```powershell
# Stop WSL
wsl --shutdown

# Wait 10 seconds
Start-Sleep -Seconds 10

# Start WSL
wsl
```

### Fix 2: Restart LxssManager Service
Open PowerShell as Administrator:

```powershell
# Restart the WSL service
Restart-Service LxssManager

# Try WSL again
wsl
```

### Fix 3: Full WSL Restart
Open PowerShell as Administrator:

```powershell
# Terminate all WSL instances
wsl --shutdown

# Unregister and re-register (WARNING: This may reset your WSL)
# Only do this if above methods fail
wsl --unregister <DistroName>
wsl --install -d <DistroName>
```

### Fix 4: Restart Windows Services
Open PowerShell as Administrator:

```powershell
# Stop services
net stop LxssManager
net stop vmcompute

# Start services
net start LxssManager
net start vmcompute

# Try WSL
wsl
```

### Fix 5: Reboot Computer
Sometimes a simple reboot fixes WSL issues:

```powershell
Restart-Computer
```

## Check WSL Status

```powershell
# List all WSL distributions
wsl --list --verbose

# Check WSL version
wsl --version

# Check if WSL is running
Get-Service LxssManager
```

## Alternative: Run Flask App Directly on Windows

If WSL continues to have issues, you can run the Flask app directly on Windows:

### Option 1: Use Windows Python

```powershell
# Navigate to project directory
cd C:\Workspace\Antigravity_workspace\Latest_OCR\Myocr_New_08-02-2026

# Create virtual environment (if not exists)
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run the app
python src/app.py
```

### Option 2: Use start.bat

```powershell
cd C:\Workspace\Antigravity_workspace\Latest_OCR\Myocr_New_08-02-2026
.\start.bat
```

## Common Causes

1. **Windows Update**: Recent Windows updates can break WSL
2. **Hyper-V Issues**: Virtualization conflicts
3. **Corrupted WSL Installation**: Service files damaged
4. **Antivirus Interference**: Security software blocking WSL
5. **Insufficient Permissions**: Need administrator rights

## Prevention

- Keep Windows updated
- Don't force-shutdown Windows while WSL is running
- Properly shutdown WSL before rebooting: `wsl --shutdown`

## Still Not Working?

If none of the above work:

1. **Reinstall WSL**:
   ```powershell
   wsl --unregister Ubuntu  # or your distro name
   wsl --install
   ```

2. **Check Windows Features**:
   - Open "Turn Windows features on or off"
   - Ensure these are enabled:
     - Windows Subsystem for Linux
     - Virtual Machine Platform

3. **Check Event Viewer**:
   - Open Event Viewer
   - Look under: Windows Logs → Application
   - Search for WSL-related errors

## For Your Flask App

Since your Flask app is already running (based on the logs), you can:

1. **Access it from Windows browser**: `http://127.0.0.1:5001`
2. **The app doesn't need WSL to be accessed** - it's already running
3. **To stop the app**: Find the Python process in Task Manager and end it

## Quick Test

After trying any fix, test with:

```powershell
wsl echo "WSL is working!"
```

If you see "WSL is working!", WSL is fixed!
