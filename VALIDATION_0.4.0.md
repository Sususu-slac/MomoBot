# MomoBot 0.4.0 validation

Date: 2026-10-27. Entry: Settings → Chat from Anywhere → Telegram.

## Completed

- Native Windows BL62_Studio Python: 53 tests passed (`python -m unittest discover -s tests -p 'test_*.py'`, 10.672 seconds). This includes 15 Telegram-specific checks and the existing 38 conversation/workflow checks.
- Private-account pairing, single-use expiring pairing code, rejection of unpaired users and groups, handling of forwarded/media messages, duplicate/stale update rejection, and persistence of the update watermark across restart.
- Native Windows DPAPI token encryption round trip, absence of the plaintext token in the saved configuration, and removal of old ownership when the bot token changes. HTTP error messages redact tokens.
- Simulated Telegram input reaches the existing scientific worker adapter; no scientific algorithm or production dataset was changed for this integration.
- Remote messages preserve the visible desktop task and unsent draft. Switching/creating remote tasks, reading saved result images, busy handling, and stopping while an LLM request is pending are covered.
- Working status is replaced by the final reply using edits to the same Telegram message. Simulated outgoing transport verifies message sending, editing, stale status coalescing, and a saved image upload.
- Native Windows can reach https://api.telegram.org over HTTPS (HTTP 200). This is connectivity only, not authenticated bot validation.
- Existing source was backed up in backups/momobot_before_telegram_20261027_194342.zip before the integration.

## Requires the user's account

No real bot token has been supplied. Authenticated Telegram polling, actual phone pairing, real delivery/notifications and phone-to-computer scientific execution remain unverified until the user enters the token locally and pairs the phone. No message has been sent to any external Telegram account during development.

Use BotFather to create a dedicated bot, paste its token into the local setup dialog, connect, and send the one-time /start code from the intended phone account. Then send `hello`, `/status`, and `/tasks` to verify the real connection. The setup is permanently available in Settings → Chat from Anywhere.

## Operational limits

- Computer, MomoBot and internet access must remain available. The GUI reconnects enabled credentials at startup; this version does not run as a Windows service.
- Pre-startup messages are ignored to avoid executing stale commands. Model requests are serialized. Additional task requests while it is busy are explicitly rejected with a retry message, not queued.
- Text and paths to files already on the computer are supported. Voice and uploaded files are not imported. Curve/best-image retrieval sends only saved task artifacts.
- Telegram carries messages and requested images. The language model and scientific computation stay local. Credentials are bound to the Windows account through DPAPI; this is not an operating-system sandbox for scientific workers.
- Paired users can request the same supported scientific operations as desktop users. Remote text does not gain shell, arbitrary file deletion, software installation or web tools.

## Token-entry usability correction

The setup now has a persistent Bot token label, a focused 46-pixel password field with a contrasting border, and a Paste token button. A native Qt interaction test confirms the field is visible and the button pastes correctly without making a network request; all 16 Telegram checks passed in 6.810 seconds. The setup can also be opened in an already-running instance with `app.py --telegram-setup`. A live Windows top-level window inspection confirmed both MomoBot and Chat from Anywhere · Telegram are visible in the same process after reload.

## 0.4.1 two-step wizard — 2026-10-29

- Setup now progresses through token entry and phone QR pairing. BotFather instructions are optional collapsed help. Successful pairing shows Phone connected and closes after a short confirmation; reopening shows connection status and Disconnect. Link copying and unpairing remain in Advanced.
- Installed qrcode 8.2 in the native BL62_Studio GUI environment and recorded qrcode>=8.2,<9 in requirements.txt. QR codes are generated locally; no online QR service receives credentials or pairing links. Bot tokens are not included in the QR payload.
- Native Windows full suite: **58 tests passed in 13.844 seconds**, including 20 Telegram checks.
- OpenCV successfully decoded the rendered pairing QR into the exact bot deep link and current nonce. A simulated `/start NONCE` completed owner binding, advanced the wizard and removed the QR. Expired QR regeneration, rejection of the previous nonce, collapsed BotFather help, token pasting and retry after connection failure were checked.
- Three isolated UI states were rendered and visually inspected under test_outputs/telegram_wizard_*.png. These screenshots use a synthetic bot and isolated settings; they are not evidence of real phone pairing.
- A source backup was created before the wizard changes: backups/before_simple_telegram_20261029_141639.zip.
- Actual phone camera scanning, Telegram's mobile Start interaction and live phone-to-computer delivery still require user pairing; no real Telegram message was sent by the tests.
