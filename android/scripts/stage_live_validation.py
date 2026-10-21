#!/usr/bin/env python3
"""Stage only this task's new synthetic family's UI login; never prints credentials."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("credentials", type=Path)
    args = parser.parse_args()
    source = args.credentials.resolve()
    if source.stat().st_mode & 0o077 or not source.name.startswith("live-credentials-"):
        parser.error("Use the verifier's private 0600 file.")
    value = json.loads(source.read_text())
    if value.get("verification_owner") != "shinian-android-20261021":
        parser.error("Only this task's isolated synthetic account is accepted.")
    fields = ("verification_owner", "username", "password", "family_id", "person_id")
    payload = {key: value[key] for key in fields}
    adb = Path(os.environ.get("ANDROID_HOME", str(Path.home() / "Library/Android/sdk"))) / "platform-tools/adb"
    command = "run-as cn.shinian.app sh -c 'umask 077; cat > files/live-validation.private.json'"
    result = subprocess.run([str(adb), "shell", command], input=json.dumps(payload).encode(), capture_output=True)
    if result.returncode:
        raise SystemExit("Could not stage fixture. Install the Debug APK on the emulator first.")
    print("Staged the isolated UI validation fixture. No credentials were printed.")


if __name__ == "__main__":
    main()
