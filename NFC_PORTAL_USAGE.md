# NFC Portal Usage Guide (`nfc_portal.py`)

This guide calls out the **main methods** a calling application will use to build an NFC “portal” app (two readers, duck battles, kiosks, etc.).

---

## Install

```bash
pip install pyscard
```

> You also need the OS smartcard service working (PC/SC). On Windows this is typically already available.

---

## Quick start

```python
from nfc_portal import NfcPortalManager

def on_state_changed(old_state, new_state):
    if new_state.has_tag():
        print("Reader:", new_state.reader_name)
        print("UID:", new_state.uid_hex)
        print("Name:", new_state.get_name())
        print("JSON:", new_state.first_json())
    else:
        print("Tag removed from", new_state.reader_name)

manager = NfcPortalManager(
    poll_interval_seconds=0.20,
    memory_page_end_inclusive=0x40,
    on_state_changed=on_state_changed
)

manager.start()

input("Press Enter to stop...")
manager.stop()
```

---

# Main API surface (what your app will call)

## `NfcPortalManager(...)`

Create the polling manager.

**Parameters you’ll actually use most:**

- `poll_interval_seconds` _(float)_: how often to poll readers (`0.10–0.30` typical)
- `memory_page_end_inclusive` _(int)_: last Type 2 page to read (`0x40` typical; increase for bigger payloads)
- `on_tag_present(state)` _(callback, optional)_
- `on_tag_removed(state)` _(callback, optional)_
- `on_state_changed(old_state, new_state)` _(callback, optional)_

## `manager.start()` / `manager.stop()`

Start/stop polling (runs in a **background thread**).

## `manager.get_current_states() -> dict[str, PortalState]`

Get the latest snapshot per reader (useful for dashboards / web APIs).

---

# `PortalState` methods you’ll use

## `state.has_tag() -> bool`

True if a tag is present (UID read succeeded).

## `state.get_name() -> str`

Best-effort friendly name:

1. JSON `"name"` field (from `first_json()`)
2. first TEXT record
3. URL last path segment (optional heuristic)
4. UID fallback

## `state.first_json() -> Any | None`

Returns the first JSON object found (prefers `application/json` records).  
Also normalizes phone “smart quotes” (`“ ”`) before parsing.

## `state.first_url() -> str | None`

Returns the first URL record value (e.g., your bio link).

## `state.first_text() -> str | None`

Returns the first TEXT record value (notes, labels, etc.).

## `state.ndef_records -> tuple[NdefRecord, ...]`

Iterate through all decoded NDEF records.

---

# `NdefRecord` methods you’ll use

## `record.text_value`

User-friendly decoded text (best-effort).

## `record.payload_bytes`

Raw payload bytes (use for verification/signatures or custom parsing).

## `record.as_utf8(errors="strict") -> str`

Decode payload bytes as UTF-8.

## `record.as_json() -> Any`

Parse payload bytes as JSON (smart quotes normalized).

---

# Common pattern: two portals (left/right)

1. Map `reader_name` to `"left"` / `"right"`
2. Keep latest `PortalState` for each side
3. When both sides have `has_tag() == True`, run your game/menu logic

```python
left_state = None
right_state = None

def on_state_changed(old_state, new_state):
    global left_state, right_state
    if "NFC 0" in new_state.reader_name:
        left_state = new_state if new_state.has_tag() else None
    elif "NFC 1" in new_state.reader_name:
        right_state = new_state if new_state.has_tag() else None

    if left_state and right_state:
        print(left_state.get_name(), "vs", right_state.get_name())
```

---

# Notes / limitations

- This module reads **Type 2 tag memory** (NTAG21x / Ultralight style) using `FF B0 ...`.
- Some readers/tags may not support memory read; in that case you may still get UID but no NDEF.
- Callbacks run on the manager’s background thread—keep them quick; hand work off to your main thread if needed.

---
