#!/usr/bin/env python3
"""Replace only the disposable Android verifier's flat-color review photos.

By default this validates local inputs and prints the plan, without networking.
Use --execute after the verifier/UI flow has stopped. Credentials must be its
private 0600 artifact with verification_owner=shinian-android-20261021. Images
come exclusively from this repository's existing DesignPhoto sample assets.
The private resumable state retains every old/new photo identity and crop.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


OWNER = "shinian-android-20261021"
EXPECTED_BASE = "https://aimemory.47-82-83-74.nip.io"
PHOTO_PLAN = {"院子里的桂花香": "summer", "第一次远行": "bike", "和家人一起过年": "dinner"}


class Failure(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise Failure(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def private_json(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077,
            "Private input must be a regular, user-owned 0600 file")
    return json.loads(path.read_text(encoding="utf-8"))


def save_private(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def jpeg_size(data):
    """Read JPEG SOF dimensions without loading an optional image library."""
    require(data[:2] == b"\xff\xd8", "Expected a JPEG asset")
    offset = 2
    while offset + 4 <= len(data):
        require(data[offset] == 255, "Invalid JPEG marker")
        while offset < len(data) and data[offset] == 255:
            offset += 1
        marker = data[offset]
        offset += 1
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        length = struct.unpack(">H", data[offset:offset + 2])[0]
        require(length >= 2 and offset + length <= len(data), "Invalid JPEG segment")
        if marker in (0xC0, 0xC1, 0xC2):
            height, width = struct.unpack(">HH", data[offset + 3:offset + 7])
            return width, height
        if marker == 0xDA:
            break
        offset += length
    raise Failure("JPEG dimensions were not found")


def story_content(memory):
    return {key: memory.get(key) for key in ("title", "raw_content", "summary", "memory_date", "location", "information",
                                           "family_id", "primary_person_id", "person_ids", "source_session_id")}


def edit_body(memory, media_ids):
    information = memory.get("information") or {}
    dimension = {"status": "missing", "value": None, "source_message_ids": [], "user_edited": False}
    return {"family_id": memory["family_id"], "version": memory["version"], "title": memory["title"],
            "summary": memory.get("summary") or memory["raw_content"],
            **{name: information.get(name) or dimension for name in ("time", "place", "feeling")},
            "memory_date": memory.get("memory_date"), "media_ids": media_ids}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Failure("Refusing a redirect with private authentication")


class ReviewPhotos:
    def __init__(self, credentials_path):
        self.credentials_path = credentials_path.absolute()
        self.credentials = private_json(self.credentials_path)
        c = self.credentials
        require(c.get("verification_owner") == OWNER and c.get("base_url") == EXPECTED_BASE,
                "Only the verifier-owned review family on its original server is accepted")
        self.memories = c.get("memory_ids", [])
        require(len(self.memories) == 3 and len(set(self.memories)) == 3, "Expected exactly three verifier stories")
        for value in [c.get("account_id"), c.get("family_id"), c.get("person_id"), *self.memories]:
            require(str(uuid.UUID(value)) == value, "Invalid verifier ownership identity")
        require(isinstance(c.get("token"), str) and bool(c["token"]), "Verifier token is missing")
        self.base = c["base_url"]
        self.repo = Path(__file__).resolve().parents[2]
        self.sources = {}
        for name in PHOTO_PLAN.values():
            path = self.repo / "ios/AIMemoirs/Assets.xcassets" / ("DesignPhoto-" + name + ".imageset/photo.jpg")
            data = path.read_bytes()
            require(0 < len(data) <= 8 * 1024 * 1024, "Repository sample exceeds upload limit")
            jpeg_size(data)
            self.sources[name] = {"path": str(path.relative_to(self.repo)), "data": data, "sha256": hashlib.sha256(data).hexdigest()}
        stem = self.credentials_path.name.removesuffix(".private.json")
        self.state_path = self.credentials_path.with_name(stem + "-review-photos.private.json")
        self.report_path = self.credentials_path.with_name(stem + "-review-photos.json")
        self.state = None
        self.opener = urllib.request.build_opener(NoRedirect)

    def checkpoint(self):
        save_private(self.state_path, self.state)

    def call(self, label, method, path, payload=None, query=None, image=None, raw=False):
        require(path.startswith("/api/v1/") and "?" not in path, "Unsafe API path")
        url = self.base + path + ("?" + urllib.parse.urlencode(query) if query else "")
        headers = {"Accept": "application/json", "Cache-Control": "no-store", "Authorization": "Bearer " + self.credentials["token"],
                   "User-Agent": "Shinian-Android-Review-Photos/1"}
        body = None
        if image is not None:
            boundary = "ShinianReview" + uuid.uuid4().hex
            headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
            body = ("--" + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="sample.jpg"\r\nContent-Type: image/jpeg\r\n\r\n').encode() + image + ("\r\n--" + boundary + "--\r\n").encode()
        elif payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=False).encode()
        # Writes deliberately do not auto-retry. Stable uploads/settings receipts and
        # re-read story versions allow a later invocation to recover an ambiguous result.
        try:
            with self.opener.open(urllib.request.Request(url, body, headers, method=method), timeout=120) as response:
                status, data = response.status, response.read()
        except urllib.error.HTTPError as error:
            raise Failure(label + ": HTTP " + str(error.code) + "; stopped without overwriting a newer version") from None
        except (OSError, TimeoutError):
            raise Failure(label + ": transport failed; rerun uses the saved private upload identities") from None
        print(label + ": HTTP " + str(status), flush=True)
        return data if raw else json.loads(data)

    def old_fixture(self, photo_id):
        data = self.call("verify_old_flat_color_fixture", "GET", "/api/v1/media/" + photo_id, raw=True)
        # The original verifier creates only 96 x 72 solid-color PNGs; the server
        # stores these as tiny JPEGs. Refuse ordinary existing/user photographs.
        require(jpeg_size(data) == (96, 72) and len(data) < 2000, "Existing photo is not a verifier-size fixture; refusing replacement")
        return hashlib.sha256(data).hexdigest()

    def run(self):
        c = self.credentials
        identity = self.call("validate_verifier_ownership", "GET", "/api/v1/auth/me")
        require(identity.get("account_id") == c["account_id"] and identity.get("family_id") == c["family_id"], "Authenticated account/family differs from verifier artifact")
        memoir_path = "/api/v1/families/" + c["family_id"] + "/members/" + c["person_id"] + "/memoir"
        book = self.call("read_current_review_memoir", "GET", memoir_path)
        stories = {memory["id"]: memory for memory in book["stories"]}
        require(set(stories) == set(self.memories), "Review family no longer contains exactly its three known stories")
        require({memory["title"] for memory in stories.values()} == set(PHOTO_PLAN), "Review story titles changed; refusing to guess")
        for memory in stories.values():
            require(memory["family_id"] == c["family_id"] and memory.get("primary_person_id") == c["person_id"], "Review story ownership mismatch")
        fingerprint = {key: c[key] for key in ("verification_owner", "base_url", "account_id", "family_id", "person_id", "memory_ids")}
        if self.state_path.exists():
            self.state = private_json(self.state_path)
            require(self.state.get("owner") == fingerprint, "Private replacement state belongs to another verifier")
        else:
            entries = {}
            for memory in stories.values():
                old = [photo["id"] for photo in memory.get("media_assets", [])]
                require(len(old) == 1, "Expected one original fixture per story; refusing to remove unknown additions")
                source = PHOTO_PLAN[memory["title"]]
                entries[memory["id"]] = {"title": memory["title"], "source": source,
                    "source_sha256": self.sources[source]["sha256"], "old_ids": old,
                    "old_hashes": {old[0]: self.old_fixture(old[0])}, "new_id": str(uuid.uuid4()),
                    "content_before": story_content(memory), "version_before": memory["version"]}
            # Capture every original crop/order before any story PATCH can remove
            # its old media row. Only tiny verifier-owned standalone covers qualify.
            standalone = {}
            for photo in book["settings"].get("coverPhotos", []):
                if not photo.get("sourceMemoryId"):
                    standalone[photo["id"]] = self.old_fixture(photo["id"])
            self.state = {"owner": fingerprint, "entries": entries, "original_book_version": book["version"],
                          "original_settings": copy.deepcopy(book["settings"]), "standalone_fixture_hashes": standalone,
                          "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "complete": False}
            self.checkpoint()
        entries = self.state["entries"]
        for memory_id, entry in entries.items():
            require(entry["source_sha256"] == self.sources[entry["source"]]["sha256"], "Source sample changed since previous run")
            memory = stories[memory_id]
            require(story_content(memory) == entry["content_before"], "Story content changed; stopping to preserve edits")
            photo_ids = [photo["id"] for photo in memory.get("media_assets", [])]
            if photo_ids != [entry["new_id"]]:
                require(photo_ids == entry["old_ids"], "Story photos changed outside this script; stopping")
                uploaded = self.call("upload_" + entry["source"], "POST", "/api/v1/memories/" + memory_id + "/media",
                    query={"family_id": c["family_id"], "client_request_id": entry["new_id"]}, image=self.sources[entry["source"]]["data"])
                require(uploaded["id"] == entry["new_id"], "Upload identity differs from stable request identity")
                memory = self.call("replace_" + entry["source"] + "_story_photo", "PATCH", "/api/v1/memories/" + memory_id,
                                   payload=edit_body(memory, [entry["new_id"]]))
                require(story_content(memory) == entry["content_before"], "Server altered story content while replacing photo")
                require([p["id"] for p in memory["media_assets"]] == [entry["new_id"]], "Server did not replace story photo")
            entry["version_after"] = memory["version"]
            self.checkpoint()
        mapping = {old: {"id": entry["new_id"], "sourceMemoryId": memory_id} for memory_id, entry in entries.items() for old in entry["old_ids"]}
        settings = copy.deepcopy(self.state["original_settings"])
        used = {mapping.get(p["id"], p)["id"] for p in settings.get("coverPhotos", []) if p["id"] not in self.state["standalone_fixture_hashes"]}
        for photo in settings.get("coverPhotos", []):
            old_id = photo["id"]
            if old_id in self.state["standalone_fixture_hashes"]:
                replacement_id = next((mid for title in ("和家人一起过年", "第一次远行", "院子里的桂花香")
                    for mid, entry in entries.items() if entry["title"] == title and entry["new_id"] not in used), None)
                require(replacement_id is not None, "No distinct replacement for standalone fixture cover")
                mapping[old_id] = {"id": entries[replacement_id]["new_id"], "sourceMemoryId": replacement_id}
                used.add(entries[replacement_id]["new_id"])
            if old_id in mapping:
                photo.update(mapping[old_id])  # x/y/zoom and cover position remain untouched.
        for ids in settings.get("photoOrders", {}).values():
            ids[:] = [mapping.get(value, {"id": value})["id"] for value in ids]
        settings["excludedPhotoIds"] = [mapping.get(value, {"id": value})["id"] for value in settings.get("excludedPhotoIds", [])]
        self.state["photo_id_mapping"] = mapping
        self.state["target_settings"] = settings
        self.checkpoint()
        current = self.call("check_current_memoir_version", "GET", memoir_path)
        if current["settings"] != settings:
            require(current["version"] == self.state["original_book_version"] and current["settings"] == self.state["original_settings"],
                    "Memoir settings changed outside this script; stopping without overwriting")
            body = self.state.setdefault("memoir_request", {"version": current["version"], "requestId": str(uuid.uuid4()), "settings": settings})
            self.checkpoint()
            current = self.call("preserve_memoir_layout_with_new_photo_ids", "PUT", memoir_path, payload=body)
        require(current["settings"] == settings, "Memoir did not retain the intended settings")
        for memory in current["stories"]:
            entry = entries[memory["id"]]
            require(story_content(memory) == entry["content_before"] and [p["id"] for p in memory["media_assets"]] == [entry["new_id"]], "Final story verification failed")
            data = self.call("verify_new_" + entry["source"] + "_photo", "GET", "/api/v1/media/" + entry["new_id"], raw=True)
            require(jpeg_size(data) != (96, 72), "New sample still has fixture dimensions")
        self.state.update({"complete": True, "final_book_version": current["version"], "completed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        self.checkpoint()
        report = {"completed": True, "synthetic_family_only": True, "stories_updated": len(entries),
                  "sample_assets": {title: self.sources[source]["path"] for title, source in PHOTO_PLAN.items()},
                  "story_text_and_interview_unchanged": True, "memoir_order_and_crops_preserved": True,
                  "memoir_version_before": self.state["original_book_version"], "memoir_version_after": current["version"],
                  "media_source": "Existing repository DesignPhoto examples; these are not photos of a real family.",
                  "completed_at_utc": self.state["completed_at_utc"]}
        self.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Completed: 3 review stories; text, interview state, memoir order and crops preserved.")
        print("Private photo ID mapping: " + str(self.state_path))
        print("Sanitized report: " + str(self.report_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", required=True, type=Path, help="Verifier-owned 0600 private credentials artifact")
    parser.add_argument("--execute", action="store_true", help="Write only this verifier's three review-photo replacements")
    args = parser.parse_args()
    try:
        review = ReviewPhotos(args.credentials)
        if args.execute:
            review.run()
        else:
            for title, source in PHOTO_PLAN.items():
                print(title + " -> " + review.sources[source]["path"])
            print("Local plan validated; no network request made. Add --execute only after the live/UI verification has stopped.")
        return 0
    except (Failure, ValueError, KeyError, OSError, TypeError) as error:
        # Never print a response body, credentials object, request URL or token.
        print("Review photos stopped: " + (str(error) if isinstance(error, Failure) else type(error).__name__), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
