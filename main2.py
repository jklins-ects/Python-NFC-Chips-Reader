import time
import json
import threading
from typing import Optional, Tuple

from nfc_portal import NfcPortalManager, PortalState

# Match your reader naming
LEFT_READER_MATCH = "0"
RIGHT_READER_MATCH = "1"


def classify_portal_side(reader_name: str) -> Optional[str]:
    if LEFT_READER_MATCH in reader_name:
        return "left"
    if RIGHT_READER_MATCH in reader_name:
        return "right"
    return None


# -----------------------------
# Non-blocking key input (Windows)
# -----------------------------
try:
    import msvcrt

    def read_key_nonblocking() -> Optional[str]:
        """Return a single key if available; otherwise None."""
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            # normalize Enter keys
            if ch == "\r":
                return "\n"
            return ch
        return None

except Exception:
    msvcrt = None

    def read_key_nonblocking() -> Optional[str]:
        return None


def pretty_json(obj) -> str:
    return json.dumps(obj, indent=4, ensure_ascii=False)


def get_duck_json(state: PortalState) -> Optional[dict]:
    obj = state.first_json()
    return obj if isinstance(obj, dict) else None


def get_pair_key(left: PortalState, right: PortalState) -> str:
    return f"{left.uid_hex}|{right.uid_hex}"


# -----------------------------
# Controller that receives NFC updates
# -----------------------------
class DuckInteractionController:
    def __init__(self):
        self._lock = threading.Lock()
        self.left: Optional[PortalState] = None
        self.right: Optional[PortalState] = None

        self.state_changed = threading.Event()

        # For “resume fight” logic
        # last time we had 2 ducks present
        self.last_full_pair_key: Optional[str] = None

    def on_state_changed(self, old_state: PortalState, new_state: PortalState):
        side = classify_portal_side(new_state.reader_name)
        if side is None:
            return

        with self._lock:
            if side == "left":
                self.left = new_state if new_state.has_tag() else None
            else:
                self.right = new_state if new_state.has_tag() else None

            if self.left and self.right:
                self.last_full_pair_key = get_pair_key(self.left, self.right)

        self.state_changed.set()

    def snapshot(self) -> Tuple[Optional[PortalState], Optional[PortalState], Optional[str]]:
        with self._lock:
            return self.left, self.right, self.last_full_pair_key


# -----------------------------
# UI / game logic
# -----------------------------
def wait_for_both_ducks(controller: DuckInteractionController):
    print("Ready. Put ducks on the portals...\n(CTRL+C to quit)")
    while True:
        left, right, _ = controller.snapshot()
        if left and right:
            return
        controller.state_changed.wait(timeout=0.25)
        controller.state_changed.clear()


def print_menu(left: PortalState, right: PortalState):
    duck1 = left.get_name()
    duck2 = right.get_name()

    print("\n" + "=" * 70)
    print(f"Portal 0: {duck1}   (UID: {left.uid_hex})")
    print(f"Portal 1: {duck2}   (UID: {right.uid_hex})")
    print("-" * 70)
    print("1. Greet each other")
    print("2. Fight")
    print("3. Print current duck stats")
    print("q. Quit")
    print("=" * 70)
    print("Press 1/2/3/q ...")


def prompt_add_back(portal_number: int):
    print(f"\n⚠️  Please add a duck back on portal #{portal_number}...")


def greet(left: PortalState, right: PortalState):
    print(f"\n🦆 {left.get_name()} says hello to {right.get_name()} 👋")


def print_stats(left: PortalState, right: PortalState):
    left_json = get_duck_json(left)
    right_json = get_duck_json(right)

    print("\n--- Duck stats ---")
    print(f"Portal 0: {left.get_name()} (UID: {left.uid_hex})")
    print(pretty_json(left_json) if left_json else "(No JSON found)")

    print("\nPortal 1: {0} (UID: {1})".format(right.get_name(), right.uid_hex))
    print(pretty_json(right_json) if right_json else "(No JSON found)")
    print("------------------\n")


def fight_loop(controller: DuckInteractionController, initial_left: PortalState, initial_right: PortalState):
    """
    Fight repeats until user presses 'm' to return to menu.

    Interrupt rules:
    - If either duck is removed -> pause and ask to add back on portal #
    - If same duck returns -> resume fight
    - If different duck returns -> return to menu
    """
    original_pair_key = get_pair_key(initial_left, initial_right)
    expected_left_uid = initial_left.uid_hex
    expected_right_uid = initial_right.uid_hex

    def banner(left_state: Optional[PortalState], right_state: Optional[PortalState], extra_line: Optional[str] = None):
        left_name = left_state.get_name() if left_state else "(missing)"
        right_name = right_state.get_name() if right_state else "(missing)"
        left_uid = left_state.uid_hex if left_state else "—"
        right_uid = right_state.uid_hex if right_state else "—"
        left_status = "OK" if left_state else "MISSING"
        right_status = "OK" if right_state else "MISSING"

        print("\n" + "=" * 70)
        print("🥊 BATTLE STATE")
        print(f"Portal 0: {left_name} | UID: {left_uid} | {left_status}")
        print(f"Portal 1: {right_name} | UID: {right_uid} | {right_status}")
        if extra_line:
            print("-" * 70)
            print(extra_line)
        print("=" * 70 + "\n")

    print(
        f"\n🥊 Fight started: {initial_left.get_name()} vs {initial_right.get_name()}")
    print("Press 'm' at any time to return to the menu.\n")

    round_number = 1

    while True:
        left, right, _ = controller.snapshot()

        # Always show banner at the start of each loop iteration
        banner(left, right)

        # If someone removed, pause
        if left is None or right is None:
            missing_portal = 0 if left is None else 1
            expected_uid = expected_left_uid if missing_portal == 0 else expected_right_uid

            banner(
                left,
                right,
                extra_line=f"⚠️ Portal #{missing_portal} is missing a duck. Expected UID: {expected_uid}\n"
                f"Add the SAME duck back to resume, or a different duck to return to the menu."
            )

            while True:
                key = read_key_nonblocking()
                if key and key.lower() == "m":
                    print("\nReturning to menu.")
                    return

                left2, right2, _ = controller.snapshot()
                if left2 and right2:
                    new_pair_key = get_pair_key(left2, right2)

                    if new_pair_key == original_pair_key:
                        banner(
                            left2, right2, extra_line="✅ Same ducks returned. RESUMING fight...")
                        left, right = left2, right2
                        break
                    else:
                        banner(
                            left2, right2, extra_line="🔁 Different duck detected. CHANGED → returning to menu.")
                        return

                controller.state_changed.wait(timeout=0.20)
                controller.state_changed.clear()

        # If both present but pair changed mid-fight -> return to menu
        current_pair_key = get_pair_key(left, right)
        if current_pair_key != original_pair_key:
            banner(left, right,
                   extra_line="🔁 Ducks changed. CHANGED → returning to menu.")
            return

        duck1 = left.get_name()
        duck2 = right.get_name()

        print(f"Round {round_number}: {duck1} attacks {duck2}")

        # 1 second pause, interruptible
        start = time.time()
        while time.time() - start < 1.0:
            key = read_key_nonblocking()
            if key and key.lower() == "m":
                print("\nReturning to menu.")
                return

            left_chk, right_chk, _ = controller.snapshot()
            if left_chk is None or right_chk is None:
                break
            time.sleep(0.05)

        left_chk, right_chk, _ = controller.snapshot()
        if left_chk is None or right_chk is None:
            continue

        print(f"{duck2} attacks {duck1}")

        start = time.time()
        while time.time() - start < 1.0:
            key = read_key_nonblocking()
            if key and key.lower() == "m":
                print("\nReturning to menu.")
                return

            left_chk, right_chk, _ = controller.snapshot()
            if left_chk is None or right_chk is None:
                break
            time.sleep(0.05)

        left_chk, right_chk, _ = controller.snapshot()
        if left_chk is None or right_chk is None:
            continue

        print("Press Enter to continue, or 'm' to return to menu...")

        while True:
            key = read_key_nonblocking()
            if key == "\n":
                break
            if key and key.lower() == "m":
                print("\nReturning to menu.")
                return

            left_chk, right_chk, _ = controller.snapshot()
            if left_chk is None or right_chk is None:
                break
            time.sleep(0.05)

        round_number += 1


def print_reader_names_once():
    from smartcard.System import readers
    print("Detected readers:")
    for r in readers():
        print(" -", r)
    print()


def main():
    if msvcrt is None:
        print("Note: Non-blocking input requires Windows (msvcrt).")
        print("This script is designed for Windows so interactions can be interrupted cleanly.\n")

    print_reader_names_once()

    controller = DuckInteractionController()

    manager = NfcPortalManager(
        poll_interval_seconds=0.20,
        memory_page_end_inclusive=0x40,
        on_state_changed=controller.on_state_changed,
    )
    manager.start()

    try:
        while True:
            # Wait until both ducks present, then show menu
            wait_for_both_ducks(controller)

            while True:
                left, right, _ = controller.snapshot()
                if not left or not right:
                    # someone removed while in menu loop
                    missing_portal = 0 if not left else 1
                    prompt_add_back(missing_portal)

                    # Wait for both to return
                    while True:
                        key = read_key_nonblocking()
                        if key and key.lower() == "q":
                            raise KeyboardInterrupt

                        left2, right2, _ = controller.snapshot()
                        if left2 and right2:
                            break
                        controller.state_changed.wait(timeout=0.20)
                        controller.state_changed.clear()

                    # When both return, just continue menu with the new pair
                    continue

                print_menu(left, right)

                # Wait for a valid menu key, but stay interruptible
                choice = None
                while choice is None:
                    key = read_key_nonblocking()
                    if key:
                        key = key.lower()
                        if key in ("1", "2", "3", "q"):
                            choice = key
                            break

                    # If a duck gets removed, break back out
                    left_chk, right_chk, _ = controller.snapshot()
                    if left_chk is None or right_chk is None:
                        choice = None
                        break

                    time.sleep(0.05)

                # if removed mid-selection, loop back (it will prompt)
                left, right, _ = controller.snapshot()
                if not left or not right:
                    continue

                if choice == "q":
                    raise KeyboardInterrupt

                if choice == "1":
                    greet(left, right)

                elif choice == "2":
                    fight_loop(controller, left, right)

                elif choice == "3":
                    print_stats(left, right)

                # After any action, if ducks changed/removed, menu will handle on next loop.

    except KeyboardInterrupt:
        manager.stop()
        print("\nStopped.")


if __name__ == "__main__":
    main()
