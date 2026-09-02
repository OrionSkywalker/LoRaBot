# LoRaBot

LoRaBot is a private-channel conversational assistant for Meshtastic. A Raspberry Pi runs a
small local Ollama model, retrieves selected RSS/Atom feeds, and performs web searches when a
question needs current information. A USB-connected Heltec WiFi LoRa 32 V4 is the radio.

This project began as a fork of
[tungstenec-max/ack-news-bot](https://github.com/tungstenec-max/ack-news-bot) and retains its
useful curated-news concept while replacing the single script with a configurable service.

## What it does

- Conversational questions use a local Ollama model and short per-node chat history.
- `news updates` summarizes stories from feeds you select in `sources.json`.
- `news about space` ranks the same curated feeds for a requested topic.
- `search <question>` searches the web and grounds the answer in result snippets.
- Questions containing words such as `current`, `latest`, or `today` automatically use search.
- `sources` returns links from the most recent news briefing or search.
- `forget` clears that node's in-memory conversation and stored links.
- Requests are accepted on the configured Meshtastic channel and in authenticated direct-message
  conversations addressed to the bot.
- Replies are addressed directly to the requesting node on that same channel.

The bot does not give the model unrestricted browser control. Web retrieval supplies a small set
of search snippets as untrusted evidence. This is faster on a Pi, reduces prompt-injection risk,
and makes source handling explicit.

## Target hardware

- Raspberry Pi 4 with 4 GB RAM
- Raspberry Pi OS Lite, 64-bit (Bookworm or newer)
- Heltec WiFi LoRa 32 V4, 902-928 MHz hardware
- Meshtastic radio firmware 2.7.26
- Data-capable USB-A to USB-C cable
- Correct 915 MHz LoRa antenna
- 32 GB or larger high-endurance microSD card recommended

Always attach the LoRa antenna before allowing the Heltec to transmit. The V4 does not use the
V3's CP2102 USB-UART bridge, so Linux commonly exposes it as `/dev/ttyACM0`, not
`/dev/ttyUSB0`. LoRaBot supports automatic detection and stable `/dev/serial/by-id/...` paths.

## How requests flow

```text
Private Meshtastic channel
        |
        +-- "news ..." --------> selected RSS/Atom feeds ----+
        |                                                  |
        +-- "search ..." ------> DDGS web search ----------+--> Ollama --> short direct reply
        |                                                  |
        +-- ordinary message -------------------------------+
```

## Raspberry Pi and Heltec setup

### 1. Prepare the Pi

Use Raspberry Pi Imager to install **Raspberry Pi OS Lite (64-bit)**. In Imager settings, create
your user, configure Wi-Fi, set the hostname, and enable SSH. After the first boot:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y curl git python3-venv
sudo reboot
```

### 2. Flash the Heltec V4

1. Attach the 915 MHz antenna.
2. Connect the Heltec to a desktop computer with a data-capable USB cable.
3. Open the [Meshtastic Web Flasher](https://flasher.meshtastic.org/).
4. Select **Heltec LoRa32 V4** and install Meshtastic firmware **2.7.26**.
5. Reconnect the Heltec to a USB-A port on the Pi.

The Heltec's `2.7.26` number is the embedded radio firmware version. LoRaBot separately installs
the Meshtastic Python client library (verified with Python client `2.7.11`); the two projects have
independent version numbers.

Confirm that Linux sees it:

```bash
ls -l /dev/ttyACM* /dev/serial/by-id/ 2>/dev/null
```

Prefer the `/dev/serial/by-id/...` name in `config.ini`. It remains stable if USB device numbering
changes. If that directory is absent, leave `serial_port = auto` initially.

### 3. Install LoRaBot

```bash
sudo git clone https://github.com/OrionSkywalker/LoRaBot.git /opt/lorabot
sudo python3 -m venv /opt/lorabot/.venv
sudo /opt/lorabot/.venv/bin/python -m pip install --upgrade pip
sudo /opt/lorabot/.venv/bin/python -m pip install /opt/lorabot
```

Create the service account and configuration:

```bash
sudo useradd --system --create-home --home-dir /var/lib/lorabot \
  --shell /usr/sbin/nologin --groups dialout lorabot
sudo install -d -o root -g lorabot -m 0750 /etc/lorabot
sudo install -o root -g lorabot -m 0640 /opt/lorabot/config.example.ini \
  /etc/lorabot/config.ini
sudo install -o root -g lorabot -m 0640 /opt/lorabot/sources.example.json \
  /etc/lorabot/sources.json
```

### 4. Configure the Heltec for US 915 MHz

Replace the example port below with the path found in step 2:

```bash
sudo /opt/lorabot/.venv/bin/meshtastic \
  --port /dev/serial/by-id/usb-EXAMPLE \
  --set lora.region US
```

The region must be set before the node will transmit. Leave the modem preset at `LONG_FAST`
unless every node in your mesh is intentionally using another preset.

### 5. Create a private secondary channel

Keep the ordinary primary channel at index 0. Add a dedicated private channel at index 1:

```bash
sudo /opt/lorabot/.venv/bin/meshtastic \
  --port /dev/serial/by-id/usb-EXAMPLE \
  --ch-add LoRaBot

sudo /opt/lorabot/.venv/bin/meshtastic \
  --port /dev/serial/by-id/usb-EXAMPLE \
  --ch-set psk random \
  --ch-set uplink_enabled false \
  --ch-set downlink_enabled false \
  --ch-index 1
```

Generate the channel URL/QR code:

```bash
sudo /opt/lorabot/.venv/bin/meshtastic \
  --port /dev/serial/by-id/usb-EXAMPLE \
  --qr-all
```

Import that URL or QR code into the Meshtastic client used by your other radio. Treat it as a
password: anyone with the channel URL can read the channel. Do not commit it to this repository.
The random PSK is AES-256; the default and `simple` keys are publicly known and are not private.

If index 1 was already occupied, use the next consecutive secondary index and set the same index
in `/etc/lorabot/config.ini`.

### 6. Install Ollama

Install Ollama's ARM64 build and enable its service:

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull llama3.2:3b
```

The default quantized `llama3.2:3b` download is about 2 GB. It fits on a 4 GB Pi but responses can
take tens of seconds, especially after the model has been unloaded. Raspberry Pi OS Lite, a 2048
token context, and short output limits are already reflected in the example configuration.

If memory pressure or latency is unacceptable, use the smaller model:

```bash
ollama pull llama3.2:1b
sudo sed -i 's/model = llama3.2:3b/model = llama3.2:1b/' /etc/lorabot/config.ini
```

### 7. Select feeds and interests

Edit the private configuration copies, not the example files in Git:

```bash
sudoedit /etc/lorabot/config.ini
sudoedit /etc/lorabot/sources.json
```

In `config.ini`:

- Set `serial_port` to the stable `/dev/serial/by-id/...` path, or leave it as `auto`.
- Keep `channel_index = 1` if the private channel created above is index 1.
- Add comma-separated Meshtastic node IDs to `allowed_node_ids` for an additional allowlist.
- Set `wake_word = lorabot` if the bot should ignore private-channel messages without that prefix.
- Set `require_direct_message = true` only if you want to reject channel broadcasts completely.
- Tune response and radio limits conservatively; each additional chunk consumes mesh airtime.

In `sources.json`, replace or extend the example feeds:

```json
{
  "interests": ["space", "technology", "local government"],
  "feeds": [
    {
      "name": "Example Local News",
      "url": "https://example.org/news.rss",
      "topics": ["local government", "weather"]
    }
  ]
}
```

Only RSS and Atom feeds you list are used by `news ...` requests. General web search is separate
and can be disabled with `enabled = false` in the `[web]` section.

### 8. Validate without the radio

Check the configuration, sources file, and Ollama connection:

```bash
sudo -u lorabot /opt/lorabot/.venv/bin/lorabot \
  --config /etc/lorabot/config.ini --check
```

Test a local-model answer:

```bash
sudo -u lorabot /opt/lorabot/.venv/bin/lorabot \
  --config /etc/lorabot/config.ini --ask "Explain LoRa in two sentences"
```

Test retrieval before using radio airtime:

```bash
sudo -u lorabot /opt/lorabot/.venv/bin/lorabot \
  --config /etc/lorabot/config.ini --ask "news updates"

sudo -u lorabot /opt/lorabot/.venv/bin/lorabot \
  --config /etc/lorabot/config.ini --ask "search current Meshtastic release"
```

### 9. Start at boot

```bash
sudo install -o root -g root -m 0644 /opt/lorabot/systemd/lorabot.service \
  /etc/systemd/system/lorabot.service
sudo systemctl daemon-reload
sudo systemctl enable --now lorabot
sudo systemctl status lorabot --no-pager
```

Follow logs while sending a test message on the private channel:

```bash
sudo journalctl -u lorabot -f
```

Try these messages from your other Meshtastic node:

```text
help
news updates
news about space
Why does LoRa travel farther than Wi-Fi?
search what is the current space weather forecast?
sources
forget
```

## Privacy and security behavior

- Channel privacy comes from the custom random PSK configured on both radios.
- LoRaBot accepts traffic on the configured private channel. It also accepts PKI-encrypted direct
  messages addressed to its node, allowing replies in the app's DM thread to continue the same
  conversation. Other channel indexes and unauthenticated legacy unicasts are ignored.
- Replies use `destinationId`, so they are addressed to the requester rather than broadcast.
- Input broadcasts on the private channel are accepted by default because this is intended to be
  a dedicated two-party channel. Set `require_direct_message = true` to change that.
- Channel uplink/downlink to MQTT is disabled in the setup commands.
- Conversation state is held only in RAM and is keyed by node ID; it disappears on restart.
- Search queries and feed requests leave the Pi over the internet. Ordinary local-model prompts do
  not, unless they contain an automatic freshness term and web search is enabled.
- Search snippets and feed content are marked untrusted in the model prompt. This reduces but does
  not eliminate the risks of malicious retrieved text or model mistakes.

Meshtastic's encrypted channels protect content from people without the key, but radio metadata
and traffic patterns can still be observable. Do not use a general-purpose language model as the
sole authority for medical, legal, emergency, or safety-critical decisions.

## Updating

```bash
sudo systemctl stop lorabot
sudo git -C /opt/lorabot pull --ff-only
sudo /opt/lorabot/.venv/bin/python -m pip install /opt/lorabot
sudo systemctl start lorabot
```

Configuration under `/etc/lorabot` is not overwritten by an update.

## Troubleshooting

**No serial device appears**

```bash
dmesg --follow
lsusb
ls -l /dev/ttyACM* /dev/serial/by-id/ 2>/dev/null
```

Try another data-capable cable and USB-A port. The V4's USB behavior differs from the V3, so do
not assume `/dev/ttyUSB0`.

**Permission denied opening the serial port**

For the shortest path, let the repository helper discover the stable USB name, install a
persistent permission rule for that exact device, update `serial_port`, and test the radio:

```bash
cd /opt/lorabot
sudo git pull --ff-only
sudo bash scripts/setup_serial.sh
```

The helper stops LoRaBot while testing so the service and diagnostic command do not compete for
the port. If several USB serial devices are attached, it prints them and asks you to rerun it with
`--device /dev/serial/by-id/...`. It does not modify channels, PSKs, or `sources.json`.

To inspect or repair the permissions manually instead:

```bash
id lorabot
getent group dialout
sudo usermod -aG dialout lorabot
sudo systemctl restart lorabot
```

**Ollama is unavailable or slow**

```bash
systemctl status ollama --no-pager
journalctl -u ollama -n 100 --no-pager
free -h
ollama list
```

Use `llama3.2:1b` if the 3B model is too slow or the Pi is swapping heavily.

**Bot hears public-channel messages or hears nothing**

Confirm the actual private channel index with:

```bash
sudo /opt/lorabot/.venv/bin/meshtastic \
  --port /dev/serial/by-id/usb-EXAMPLE --info
```

The reported channel index and `config.ini` must match for channel broadcasts. Authenticated PKI
direct messages use Meshtastic's DM path and are accepted separately.

**Web search fails intermittently**

DDGS is a free metasearch library and upstream search providers can rate-limit or change behavior.
The bot reports the failure rather than silently presenting model knowledge as current. Retry
later or disable web search while keeping curated feeds and local conversation.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
ruff check .
ruff format --check .
```

The test suite covers intent routing, per-node history, source recall, configuration validation,
Atom parsing, and UTF-8-safe mesh message splitting.

## License

MIT. See [LICENSE](LICENSE).
