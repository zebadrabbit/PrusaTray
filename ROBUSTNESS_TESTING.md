# Robustness Testing Checklist

## ✅ Implementation Verified

### Architecture
- **Pattern chosen**: QNetworkAccessManager (async, Qt-native)
- **Rationale**: No manual thread management, automatic signal/slot on main thread, built-in connection pooling
- **UI thread safety**: All network I/O is async, UI updates only via signals on main thread

### Timeouts
- ✅ Transfer timeout: 10 seconds (QNetworkRequest.setTransferTimeout)
- ✅ Safety timeout: 15 seconds (QTimer fallback)
- ✅ Abort mechanism: Pending requests aborted on timeout

### Error Handling
- ✅ Network errors caught and logged
- ✅ Parse errors caught separately
- ✅ Exception handling in poll loop
- ✅ State tracking: `last_ok_timestamp`, `last_error`

### Backoff Strategy
- ✅ **Exponential backoff**: min 3s, max 30s
- ✅ **Jitter**: 0-20% random to prevent thundering herd
- ✅ **Reset on success**: Returns to normal interval immediately
- ✅ **Formula**: `min(3 * 2^(failures-1), 30) + jitter`

### State Management
- ✅ OFFLINE status when network fails
- ✅ Tooltip shows last error (truncated)
- ✅ Tooltip shows time since last successful poll
- ✅ Icon color changes to dark red for offline
- ✅ Demo mode unaffected by network issues

### Unit Testing
- ✅ Pure parsing function: `parse_printer_status(data: Dict) -> PrinterState`
- ✅ No I/O in parsing logic
- ✅ Example tests in test_parser.py

## 🧪 Manual Test Cases

### Test 1: Offline Printer (No Spam Check)
**Steps:**
1. Set `printer_base_url` to unreachable URL (e.g., "http://192.168.1.999")
2. Start app
3. Monitor logs for 2 minutes

**Expected:**
- ✅ First poll at 0s
- ✅ Second poll at ~3s (first backoff)
- ✅ Third poll at ~6s 
- ✅ Fourth poll at ~12s
- ✅ Fifth poll at ~24s
- ✅ Subsequent polls every ~30s (max backoff)
- ❌ Should NOT poll every 3s continuously

**Verify:**
```
grep "Polling http" logs  # Should show increasing intervals
```

### Test 2: Recovery After Offline
**Steps:**
1. Start with offline printer (backoff engaged)
2. Wait until polling is at 30s interval
3. Make printer accessible
4. Wait for next poll

**Expected:**
- ✅ Next successful poll resets backoff
- ✅ Subsequent polls return to 3s interval
- ✅ Tooltip no longer shows "offline"
- ✅ Icon color returns to normal status color
- ✅ `last_ok_timestamp` updates

### Test 3: Intermittent Failures
**Steps:**
1. Printer online, polling normally
2. Disconnect network cable briefly
3. Reconnect after 10 seconds

**Expected:**
- ✅ Failures trigger backoff
- ✅ Recovery resets backoff
- ✅ No duplicate requests during recovery
- ✅ State transitions: PRINTING → OFFLINE → PRINTING

### Test 4: Parse Errors vs Network Errors
**Steps:**
1. Configure printer URL to return invalid JSON
2. Monitor error messages

**Expected:**
- ✅ Parse errors logged separately from network errors
- ✅ Both trigger backoff
- ✅ Tooltip distinguishes error type
- ✅ Still shows OFFLINE status

### Test 5: Demo Mode Unaffected
**Steps:**
1. Run with `printer_base_url: null`
2. Monitor for 5 minutes

**Expected:**
- ✅ Polls every 3s consistently
- ✅ No backoff (no network calls)
- ✅ Simulated state cycles smoothly
- ✅ No error states

## 📊 Backoff Behavior Reference

| Failure # | Base Delay | With 10% Jitter | Cumulative Time |
|-----------|------------|-----------------|-----------------|
| 0         | 3s         | 3.0-3.3s        | 0s              |
| 1         | 3s         | 3.0-3.6s        | ~3s             |
| 2         | 6s         | 6.0-7.2s        | ~9s             |
| 3         | 12s        | 12.0-14.4s      | ~21s            |
| 4         | 24s        | 24.0-28.8s      | ~45s            |
| 5+        | 30s (max)  | 30.0-36.0s      | ~75s+           |

## 🔍 Code Locations

- **Backoff logic**: [tray_prusa/poller.py#L149-162](../tray_prusa/poller.py)
- **Network request**: [tray_prusa/poller.py#L182-197](../tray_prusa/poller.py)
- **Timeout handling**: [tray_prusa/poller.py#L199-206](../tray_prusa/poller.py)
- **Error handling**: [tray_prusa/poller.py#L238-253](../tray_prusa/poller.py)
- **Parse function**: [tray_prusa/poller.py#L17-51](../tray_prusa/poller.py)

## 🐛 Common Issues to Watch For

### ❌ Request Spam (Fixed)
- **Problem**: Polling every 3s even when offline
- **Solution**: Exponential backoff with `_consecutive_failures` counter

### ❌ UI Freeze (Fixed)
- **Problem**: Blocking network calls freeze tray icon
- **Solution**: QNetworkAccessManager async requests, no blocking

### ❌ Timeout Ignored (Fixed)
- **Problem**: Requests hang indefinitely
- **Solution**: Double timeout (QNetworkRequest + QTimer safety)

### ❌ No Recovery (Fixed)
- **Problem**: Stays in backoff mode even when online
- **Solution**: Reset `_consecutive_failures = 0` on success

### ❌ Race Conditions (Fixed)
- **Problem**: Multiple simultaneous requests
- **Solution**: Check `_pending_reply`, skip poll if already pending
