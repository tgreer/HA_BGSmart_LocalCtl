# Quick Installation Guide

## Prerequisites

- Your BG Smart device is set up in the BG Smart app and connected to the same network as Home Assistant.
- Nothing else — devices are discovered automatically and need no keys or IP addresses. You only need the IP if discovery doesn't work in your setup (see manual setup below).

## Installation Steps

### 1. Install via HACS

#### Add Custom Repository

1. Open **HACS** in your Home Assistant
2. Click the **3 dots** (⋮) in the top right
3. Select **Custom repositories**
4. Enter:
   - **Repository**: `https://github.com/tgreer/HA_BGSmart_LocalCtl`
   - **Category**: `Integration`
5. Click **Add**

#### Install Integration

1. In HACS, click **Integrations**
2. Search for **"BG Smart Local Control"**
3. Click on it
4. Click **Download**
5. **Restart Home Assistant**

### 2. Add Your Devices

#### Automatic (recommended)

After Home Assistant restarts, it listens for BG Smart devices on the network.

1. Go to **Settings** → **Devices & Services**
2. Your device appears under **Discovered** with its name from the BG Smart app (e.g., "Utility Room Smart Socket")
3. Click **Add**, then **Submit** on the confirmation dialog

Repeat for each device. If a device isn't showing, power-cycle it — it announces itself on boot — and give Home Assistant a minute.

#### Manual (if not discovered)

Discovery needs Home Assistant to receive mDNS multicast from the devices. It won't work across VLANs, or in Docker without `--network host`. In that case:

1. Find the device's IP in your router's DHCP client list (look for an "ESP" or "espressif" hostname) or with a scanner app such as Fing
2. Go to **Settings** → **Devices & Services**
3. Click **+ Add Integration** (bottom right)
4. Search for **"BG Smart Local Control"**
5. Enter configuration:

   ```
   Device IP Address: 192.168.1.100    (your device IP)
   Port: 8080                           (pre-filled, don't change)
   ```

6. Click **Submit**

The device's identity (`node_id`) is read from the device itself, so a manually added device still follows IP address changes — no static IP needed.

### 3. Verify Installation

If successful, you'll see:
- ✅ Integration added to Devices & Services
- ✅ Device card showing device name (e.g., "Lounge" or "Utility Room Smart Socket")
- ✅ Light entity created for dimmers (e.g., `light.lounge`)
- ✅ Switch entities created for sockets (power and parental lock per outlet)
- ✅ An **LED indicator** switch (Configuration) and a **Restart** button (Diagnostic) on the device page

### 4. Test Control

1. **Find your light**:
   - Go to **Settings** → **Devices & Services**
   - Click on **BG Smart Local Control**
   - Click on your device name

2. **Test controls**:
   - Toggle On/Off
   - Adjust brightness slider
   - Changes should be instant (<100ms)

## Troubleshooting

### "Cannot Connect to Device"

**Problem**: Integration fails to connect

**Solutions**:

1. **Verify IP address is correct**
   ```bash
   ping 192.168.1.100
   ```
   Should get responses

2. **Check port is 8080**
   - Default is 8080
   - Don't change unless you know it's different

3. **Check network**
   - Device and Home Assistant on same network
   - No VLANs or network isolation
   - Port 8080 not blocked by firewall

### Integration Added But No Entities

**Problem**: Integration succeeds but no light entities appear

**Solution**:
1. Check logs: **Settings** → **System** → **Logs**
2. Filter for: `bg_smart`
3. Look for error messages
4. Try **removing and re-adding** integration

### Brightness Control Not Working

**Problem**: Can turn on/off but brightness slider missing

**Solution**:
1. **Remove integration**
2. **Restart Home Assistant**
3. **Re-add integration**
4. Brightness should now appear

### Getting Help

1. **Check logs** first
2. **Search existing issues**: https://github.com/tgreer/HA_BGSmart_LocalCtl/issues
3. **Open new issue** with:
   - Home Assistant version
   - Integration version
   - Device model
   - Relevant logs (Settings → System → Logs)

## Advanced Configuration

### Static IP (Recommended)

Set a static IP or DHCP reservation for your device:

**Why**: Prevents IP changes requiring reconfiguration

**How**:
1. Log into your router
2. Find DHCP settings
3. Add reservation for device MAC address
4. Assign permanent IP (e.g., `192.168.1.100`)

### Multiple Devices

To add multiple dimmers or sockets:

1. Add integration multiple times
2. Use different IP address for each
3. Each gets its own entity

### Custom Names

Rename entities in Home Assistant:

1. Go to **Settings** → **Devices & Services**
2. Click on device
3. Click on entity
4. Click gear icon (⚙️)
5. Change **Name** and **Entity ID**

## Next Steps

Once installed:

- ✅ Add to Lovelace dashboard
- ✅ Create automations
- ✅ Add to scenes
- ✅ Use with voice assistants (Alexa, Google Home)
- ✅ Integrate with other smart home devices

## Example Dashboard Card

```yaml
type: light
entity: light.lounge
name: Lounge Dimmer
icon: mdi:ceiling-light
```

## Example Automation

```yaml
automation:
  - alias: "Dim lights at sunset"
    trigger:
      - platform: sun
        event: sunset
    action:
      - service: light.turn_on
        target:
          entity_id: light.lounge
        data:
          brightness_pct: 30
```

---

**That's it! Enjoy fast, local control of your BG Smart devices!** 🎉
