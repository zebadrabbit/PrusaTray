# PrusaTray v1.0.0

A Windows system tray application for monitoring Prusa 3D printers via PrusaLink or OctoPrint.

## 🎯 For End Users

### Download
Download `PrusaTray.exe` below and run it - no installation needed!

### Requirements
- Windows 10 or Windows 11
- [Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe) (usually already installed)

### First-Time Setup
1. Run `PrusaTray.exe`
2. Right-click the tray icon
3. Select "Configuration..."
4. Enter your printer details:
   - Printer URL (e.g., `http://192.168.1.100`)
   - Select backend type (PrusaLink or OctoPrint)
   - Authentication mode (API Key or Digest)
   - Enter your credentials
5. Click "Test Connection" to verify
6. Click "Save"

### Features
✅ Real-time printer status monitoring  
✅ Visual tray icon showing printer state  
✅ Progress indicator for active prints  
✅ Secure credential storage (Windows Credential Manager)  
✅ Support for both PrusaLink and OctoPrint  
✅ Multiple authentication modes (API Key, Digest)  
✅ Quick access to printer web UI  
✅ Manual refresh capability  

### Troubleshooting
See the [README](https://github.com/zebadrabbit/PrusaTray#troubleshooting) for common issues and solutions.

---

## 👨‍💻 For Developers

### Building from Source
```powershell
git clone https://github.com/zebadrabbit/PrusaTray.git
cd PrusaTray
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\build_windows.ps1
```

### Running from Source
```powershell
python -m tray_prusa
```

See the [README](https://github.com/zebadrabbit/PrusaTray) for full documentation.
