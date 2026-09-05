<p align="center">
  <img src="custom_components/bg_smart_local/brand/logo.png" alt="BG Smart Local Control" width="256">
</p>

# BG Smart Local Control for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/tgreer/HA_BGSmart_LocalCtl.svg)](https://github.com/tgreer/HA_BGSmart_LocalCtl/releases)
[![License](https://img.shields.io/github/license/tgreer/HA_BGSmart_LocalCtl.svg)](LICENSE)

Local control integration for BG Smart (Luceco) dimmer switches and smart sockets using the ESP Local Control protocol.

## Features

✅ **100% Local Control** - No cloud dependency, works without internet  
✅ **Fast Response** - 50-100ms latency vs 500ms-2s for cloud  
✅ **Privacy Friendly** - All communication stays on your local network  
✅ **Full Brightness Control** - On/Off and 0-100% dimming  
✅ **Smart Socket Support** - Per-outlet power and parental lock on double sockets  
✅ **Auto-Discovery** - Devices on your network are found automatically via mDNS (see [Auto-Discovery](#auto-discovery))  
✅ **Auto Configuration** - Device name and capabilities are read from the device; no keys to type  
⚠️ **No Authentication** - The device's local API accepts unauthenticated commands from the LAN (see [Security](#security))  

## Supported Devices

- BG Smart Dimmer Switch (DMHCM)
- BG Smart Double Socket (Left/Right outlets with parental lock)
- Luceco Dimmer Controller
- Any ESP32-based BG Smart/Luceco device with local control

### Entities Created

| Device | Entities |
|--------|----------|
| Dimmer | One `light` entity with brightness |
| Double Socket | One device with `switch.<name>_left_socket`, `switch.<name>_right_socket`, and a `... parental lock` switch for each outlet |

## Requirements

- Home Assistant 2024.1.0 or newer
- BG Smart dimmer or smart socket on the same local network
- Home Assistant able to receive mDNS multicast for auto-discovery (otherwise add by IP)

## Installation

### Method 1: HACS (Recommended)

1. **Add Custom Repository**
   - Open HACS in Home Assistant
   - Click the 3 dots in top right → **Custom repositories**
   - Add repository URL: `https://github.com/tgreer/HA_BGSmart_LocalCtl`
   - Category: **Integration**
   - Click **Add**

2. **Install Integration**
   - Search for "BG Smart Local Control" in HACS
   - Click **Download**
   - Restart Home Assistant

3. **Add Integration**
   - Go to **Settings** → **Devices & Services**
   - Click **Add Integration**
   - Search for "BG Smart Local Control"
   - Follow configuration steps below

### Method 2: Manual Installation

1. **Download Files**
   ```bash
   cd /config
   git clone https://github.com/tgreer/HA_BGSmart_LocalCtl.git
   cp -r HA_BGSmart_LocalCtl/custom_components/bg_smart_local custom_components/
   ```

2. **Restart Home Assistant**

3. **Add Integration** (see configuration below)

## Configuration

### Option A: Auto-Discovery (Recommended)

Once the integration is installed and Home Assistant has restarted, BG Smart devices on your network are discovered automatically.

1. Go to **Settings** → **Devices & Services**
2. Look for a **Discovered** card showing your device's name (e.g., "Lounge" or "Utility Room Smart Socket")
3. Click **Add** and confirm

That's it — no IP addresses or keys to enter. Discovered devices are tracked by their `node_id`, not their IP, so DHCP address changes are handled automatically (see [IP address changes](#ip-address-changes)).

### Option B: Manual Setup

Use this if the device isn't discovered (for example, Home Assistant is on a different VLAN or running in Docker without host networking).

1. Find the device's IP address in your router's DHCP client list or with a network scanner. A static IP or DHCP reservation is recommended.
2. Go to **Settings** → **Devices & Services**
3. Click **Add Integration** and search for "BG Smart Local Control"
4. Enter configuration:
   - **Device IP Address**: e.g., `192.168.1.100`
   - **Port**: `8080` (default, pre-filled)
   - **Node ID**: Leave empty

5. Click **Submit**

### Verify

The integration will:
- ✅ Connect to your device
- ✅ Read the device name (e.g., "Lounge" or "Utility Room Smart Socket")
- ✅ Create a light entity for dimmers (e.g., `light.lounge`) or switch entities for sockets
- ✅ Show current on/off state (and brightness for dimmers)

## Usage

### Basic Control

#### Dimmers

The dimmer appears as a standard Home Assistant light entity:

```yaml
# Turn on at 50% brightness
service: light.turn_on
target:
  entity_id: light.lounge
data:
  brightness_pct: 50

# Turn off
service: light.turn_off
target:
  entity_id: light.lounge
```

#### Smart Sockets

A double socket appears as one device with a power switch and a parental lock switch per outlet (called "Parental Lock" in the BG Smart app):

```yaml
# Turn on the left outlet
service: switch.turn_on
target:
  entity_id: switch.utility_room_smart_socket_left_socket

# Enable parental lock on the right outlet
service: switch.turn_on
target:
  entity_id: switch.utility_room_smart_socket_right_socket_parental_lock
```

### Automations

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

  - alias: "Lights off at bedtime"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      - service: light.turn_off
        target:
          entity_id: light.lounge
```

### Scenes

```yaml
scene:
  - name: Movie Time
    entities:
      light.lounge:
        state: on
        brightness_pct: 20
```

### Dashboard Card

```yaml
type: light
entity: light.lounge
name: Lounge Dimmer
```

## Auto-Discovery

BG Smart devices advertise themselves on the local network using mDNS with the service type `_esp_local_ctrl._tcp`. Each advertisement carries a `node_id` that uniquely identifies the device, plus the control endpoint path.

The integration listens for this service and:

- Ignores ESP Local Control devices that don't carry BG Smart markers (any ESP32 project can use the same protocol)
- Connects to the device and reads its friendly name for the discovery card
- Uses the `node_id` as the device's identity; the IP address is only a cached hint
- Upgrades devices that were added manually by IP in earlier versions to the `node_id` identity when they are discovered

### IP address changes

The device's `node_id` doubles as its mDNS hostname (`<node_id>.local`). The integration uses this in two ways so you don't need a static IP or DHCP reservation:

1. **Proactively** — when the device reboots with a new address it re-announces itself, and Home Assistant's discovery updates the cached address in place without reloading the integration.
2. **Reactively** — if a poll fails, the integration resolves `<node_id>.local` through Home Assistant's mDNS resolver, and if the device has moved, switches to the new address and retries before marking anything unavailable.

Manually added devices get the same behaviour if you fill in the **Node ID** field. The node ID is the device's hostname, visible in your router's DHCP client list (a 22-character string such as `C3GNXiRBoiyPb5p5mGzHtZ`). Manually added devices *without* a node ID are tied to their IP address, so give them a DHCP reservation.

**Tested**: double socket. **Expected to work**: dimmers (same firmware family and protocol), but not yet confirmed on hardware — please report your results.

**Requirements for discovery to work:**
- Home Assistant must be able to receive multicast traffic from the devices. Home Assistant OS and Supervised installs work out of the box. Docker installs need `--network host`. Devices on a separate VLAN will not be discovered unless an mDNS reflector is configured.
- If discovery doesn't work in your setup, use [manual setup](#option-b-manual-setup).

To check what your device advertises, run `dns-sd -B _esp_local_ctrl._tcp` on macOS or `avahi-browse -r _esp_local_ctrl._tcp` on Linux.

## Security

The BG Smart devices tested so far accept **unauthenticated, unencrypted** commands on their local control endpoint. The integration sends plain HTTP requests to port 8080 and the device obeys them. Anyone on the same network segment can do the same.

Earlier versions of this integration asked for a PoP (Proof of Possession) key and described the connection as "Sec1 encrypted". That was never true — the key was stored but never sent to the device. The field has been removed.

Espressif's ESP Local Control does support a Sec1 mode (Curve25519 key exchange and AES-CTR encryption keyed with a PoP), and the devices advertise a session endpoint, so BG could enable it in a future firmware. If that happens the integration will need a session handshake implemented; until then, treat the devices as trusting your LAN.

## Troubleshooting

### Cannot Connect to Device

**Check IP Address:**
```bash
ping 192.168.1.100  # Replace with your device IP
```

**Verify Port:**
- Default port is `8080`
- Device must be on same network as Home Assistant

### Device Not Discovered

- Confirm Home Assistant can receive mDNS multicast (see [Auto-Discovery](#auto-discovery))
- Power-cycle the device; it re-announces itself on boot
- Fall back to [manual setup](#option-b-manual-setup) by IP address

### Device Found But No Control

**Check Logs:**
```
Settings → System → Logs → Filter "bg_smart"
```

**Common Issues:**
- Network firewall blocking port 8080
- Device firmware outdated

### Brightness Not Working

**Delete and Re-add:**
1. Remove integration
2. Restart Home Assistant
3. Re-add integration

### Enable Debug Logging

Add to `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.bg_smart_local: debug
```

Restart and check logs.

## Technical Details

### Protocol

- **Base Protocol**: ESP Local Control (Espressif)
- **Transport**: HTTP POST with Protocol Buffers
- **Port**: 8080 (plain HTTP)
- **Discovery**: mDNS `_esp_local_ctrl._tcp` with `node_id` TXT record
- **Security**: None (protocomm security0) — see [Security](#security)

### Communication

```
Home Assistant                    BG Smart Dimmer
      |                                  |
      |--- Get Property Count --------->|
      |<--- Count = 2 -------------------|
      |                                  |
      |--- Get Property Values -------->|
      |<--- Device State ----------------|
      |     (Power: True, Brightness: 48)|
      |                                  |
      |--- Set Property Values -------->|
      |     (Brightness: 75)             |
      |<--- Success --------------------|
```

### Update Frequency

- Polling interval: 30 seconds
- Immediate update on command
- Configurable in future versions

## Comparison: Local vs Cloud

| Feature | Local Control | Cloud API |
|---------|--------------|-----------|
| Latency | 50-100ms | 500ms-2s |
| Internet Required | ❌ No | ✅ Yes |
| Reliability | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| Privacy | ✅ All local | ❌ Data to cloud |
| Setup | Auto-discovered | OAuth + Credentials |
| Works Offline | ✅ Yes | ❌ No |

## FAQ

**Q: Do I need the PoP key / Device ID from the app?**  
A: No. Earlier versions asked for it but never used it. Devices are discovered automatically and need no credentials.

**Q: Can I control multiple devices?**  
A: Yes. Each discovered device appears as its own card; add each one. Manually-added devices are one integration entry per IP address.

**Q: Does this work with BG Smart sockets or other devices?**  
A: Dimmers and double sockets are supported (power and parental lock per outlet). Socket timers, schedules, and scenes are not yet exposed. Other device types may work but are untested.

**Q: Does this interfere with the BG Smart app?**  
A: No, both can be used simultaneously. Changes made in either app or Home Assistant will be reflected in both.

**Q: Can I use this without the BG Smart cloud?**  
A: Yes! This integration works completely independently of BG Smart cloud services.

## Support

- **Issues**: [GitHub Issues](https://github.com/tgreer/HA_BGSmart_LocalCtl/issues)
- **Discussions**: [GitHub Discussions](https://github.com/tgreer/HA_BGSmart_LocalCtl/discussions)
- **Home Assistant Community**: [Community Thread](https://community.home-assistant.io/)

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## Credits

- Maintained by [@tgreer](https://github.com/tgreer)
- Original dimmer integration by [@rrwood](https://github.com/rrwood/HA_BGSmart_LocalCtl); this repository is maintained independently
- Protocol reverse-engineered from BG Smart Android app
- Based on [ESP Local Control](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/protocols/esp_local_ctrl.html) by Espressif

## License

MIT License - See [LICENSE](LICENSE) file for details.

Copyright (c) 2025 rrwood (original dimmer integration) and (c) 2026 tgreer.

## Disclaimer

This integration is not affiliated with, endorsed by, or connected to BG Electrical or Luceco. All product names, logos, and brands are property of their respective owners.

---

**Enjoy fast, local, and private control of your BG Smart devices!** ⚡
