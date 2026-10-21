#!/usr/bin/env python3
"""Explicit, disposable-family smoke test for the Android/iOS shared HTTPS API.

Run with --execute to register a fresh test family. Never accepts existing family credentials.
Passwords and tokens are written only to a 0600 private file excluded by artifacts/ in Git.
The JSON report contains statuses, timings, checks, and synthetic-data counts, not credentials.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib


class Failure(RuntimeError):
    pass


def png(seed=0):
    width, height = 96, 72
    rows = b"".join(b"\0" + bytes((190 + seed % 40, 135, 75)) * width for _ in range(height))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


class Validation:
    def __init__(self, base, directory, resume=None, skip_outline=False):
        self.base = base.rstrip("/")
        if not self.base.startswith("https://"):
            raise Failure("Live verification requires HTTPS")
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.run_id = time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + secrets.token_hex(3)
        self.report_path = directory / ("live-backend-" + self.run_id + ".json")
        self.private_path = directory / ("live-credentials-" + self.run_id + ".private.json")
        self.credentials = {"verification_owner": "shinian-android-20261021", "base_url": self.base,
                            "username": "android_" + secrets.token_hex(7), "password": secrets.token_urlsafe(24)}
        self.secrets = [self.credentials["username"], self.credentials["password"]]
        self.report = {"run_id": self.run_id, "base_url": self.base, "synthetic_data_only": True,
                       "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "steps": [], "checks": [], "completed": False}
        self.token = None
        self.family_id = None
        self.person_id = None
        self.extra_people = []
        self.extra_memories = []
        self.kept_memories = []
        self.skip_outline = skip_outline
        if resume is not None:
            resume = resume.resolve()
            if resume.parent != directory.resolve() or not resume.name.startswith("live-credentials-") or resume.stat().st_mode & 0o077:
                raise Failure("Resume accepts only this verifier's private 0600 artifact")
            saved = json.loads(resume.read_text())
            if saved.get("verification_owner") != "shinian-android-20261021" or saved.get("base_url") != self.base or saved.get("memory_ids"):
                raise Failure("Resume is restricted to an unfinished verifier-owned outline, before any saved story")
            self.credentials = saved
            self.private_path = resume
            self.run_id = resume.name.removeprefix("live-credentials-").removesuffix(".private.json")
            self.report_path = directory / ("live-backend-" + self.run_id + ".json")
            self.report = json.loads(self.report_path.read_text())
            previous = self.report.pop("failure", None)
            if previous:
                self.report.setdefault("previous_attempt_failures", []).append(previous)
            self.report["resume_attempts"] = self.report.get("resume_attempts", 0) + 1
            self.token = saved["token"]
            self.family_id = saved["family_id"]
            self.person_id = saved["person_id"]
            self.secrets = [value for key, value in saved.items() if key in ("username", "password", "token", "secondary_token")]
        self.save_private()
        self.save_report()

    def scrub(self, value):
        text = str(value)
        for secret in self.secrets:
            text = text.replace(secret, "[REDACTED]")
        return text

    def save_private(self):
        fd = os.open(self.private_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(self.credentials, handle, ensure_ascii=False, indent=2)

    def save_report(self):
        temporary = self.report_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.report_path)

    def check(self, label, condition):
        self.report["checks"].append({"label": label, "passed": bool(condition)})
        self.save_report()
        if not condition:
            raise Failure(label)

    def call(self, label, method, path, payload=None, query=None, expected=tuple(range(200, 300)), token="current", file=None, raw=False, retry=False):
        url = self.base + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        actual_token = self.token if token == "current" else token
        headers = {"Accept": "application/json", "Cache-Control": "no-store", "User-Agent": "Shinian-Android-Validation/1"}
        if actual_token:
            headers["Authorization"] = "Bearer " + actual_token
        body = None
        if file is not None:
            boundary = "AndroidVerification-" + uuid.uuid4().hex
            body = ("--" + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="memory.png"\r\nContent-Type: image/png\r\n\r\n').encode() + file + ("\r\n--" + boundary + "--\r\n").encode()
            headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
        elif payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json"
        can_retry = retry or method == "GET"
        for attempt in range(2 if can_retry else 1):
            started = time.monotonic()
            status, data = None, b""
            try:
                with urllib.request.urlopen(urllib.request.Request(url, body, headers, method=method), timeout=450) as response:
                    status, data = response.status, response.read()
            except urllib.error.HTTPError as error:
                status, data = error.code, error.read()
            except (OSError, TimeoutError) as error:
                record = {"label": label, "attempt": attempt + 1, "status": "transport_error",
                          "duration_s": round(time.monotonic() - started, 2), "error": self.scrub(type(error).__name__)}
                self.report["steps"].append(record)
                self.save_report()
                print(label + ": transport error", flush=True)
                if can_retry and attempt == 0:
                    time.sleep(1)
                    continue
                raise Failure(label + ": transport error") from None
            record = {"label": label, "attempt": attempt + 1, "http_status": status,
                      "duration_s": round(time.monotonic() - started, 2), "passed": status in expected}
            if status not in expected:
                try:
                    detail = json.loads(data).get("detail")
                    if isinstance(detail, str):
                        record["detail"] = self.scrub(detail)
                    elif isinstance(detail, list):
                        record["detail"] = [str(item.get("msg", "Validation error")) for item in detail]
                except (ValueError, AttributeError):
                    record["detail"] = "Non-JSON error response"
            self.report["steps"].append(record)
            self.save_report()
            print(label + ": HTTP " + str(status) + " (" + str(record["duration_s"]) + "s)", flush=True)
            if status not in expected:
                if can_retry and attempt == 0 and status in (502, 503, 504):
                    time.sleep(1)
                    continue
                raise Failure(label + ": HTTP " + str(status) + " " + str(record.get("detail", "")))
            if raw:
                return data
            return json.loads(data) if data else None

    def dimension(self, status, value):
        return {"status": status, "value": value, "source_message_ids": [], "user_edited": True}

    def open_conversation(self):
        return self.call("open_person_conversation", "POST", "/api/v1/chat/members/" + self.person_id + "/conversation", query={"family_id": self.family_id}, retry=True)

    def life(self, snapshot, action, text=""):
        overview = snapshot["life_overview"]
        body = {"action": action, "expected_version": overview["version"], "client_request_id": str(uuid.uuid4()), "text": text}
        return self.call("life_overview_" + action, "POST", "/api/v1/chat/sessions/" + snapshot["session"]["id"] + "/life-overview/actions", body, retry=True)

    def edit_body(self, memory, **changes):
        information = memory.get("information") or {}
        body = {"family_id": self.family_id, "version": memory["version"], "title": memory["title"],
                "summary": memory.get("summary") or memory["raw_content"],
                "time": information.get("time") or self.dimension("missing", None),
                "place": information.get("place") or self.dimension("missing", None),
                "feeling": information.get("feeling") or self.dimension("missing", None),
                "memory_date": memory.get("memory_date"), "media_ids": [item["id"] for item in memory.get("media_assets", [])]}
        body.update(changes)
        return body

    def complete_outline(self, snapshot):
        overview = snapshot.get("life_overview") or {}
        if overview.get("status") == "not_started":
            snapshot = self.life(snapshot, "begin")
        if snapshot.get("life_overview", {}).get("status") == "collecting":
            question = snapshot["life_overview"].get("question_id")
            snapshot = self.life(snapshot, "pause")
            snapshot = self.life(snapshot, "resume")
            self.check("outline_pause_resume_keeps_question", snapshot["life_overview"].get("question_id") == question)
        answers = {
            "home": "我1945年6月1日出生，小时候主要在苏州乡下长大，和父母、哥哥一起住在有桂花树的院子里。",
            "learning": "我七岁上小学，读完小学后跟母亲学做点心。",
            "early_work": "年轻时我在苏州的纺织厂做工。",
            "later_work": "后来我回到家里开了一间小点心铺，和丈夫一起经营。",
            "family": "我和丈夫一起生活，有一个女儿，后来还有外孙。",
            "changes": "我一直记得家乡通上自来水的变化，挑水的日子终于结束了。",
            "present": "现在我住在苏州，平时种花、做饭、陪外孙，日子过得平静。",
            "SK01": "我1945年6月1日出生。", "SK01b": "我出生在苏州乡下。", "SK01c": "家乡有小河、石桥和种着桂花树的院子。",
            "SK02": "名字是父亲取的，希望我平安长大。", "SK03": "小时候和父母、哥哥一起生活。", "SK03b": "家里靠种田和母亲做点心维持生活。",
            "SK03c": "我有一个哥哥。", "SK03d": "家人相处和睦，遇到困难会一起商量。", "SK04": "父母常教我做人诚实、做事认真。",
            "SK05": "我觉得自己耐心、慢热，也很珍惜家人。", "SK06": "勤恳、平安、家人，是我这一生的关键词。",
        }
        attempts = {}
        for index in range(36):
            overview = snapshot.get("life_overview") or {}
            if overview.get("status") != "collecting":
                break
            topic = overview.get("question_id")
            attempts[topic] = attempts.get(topic, 0) + 1
            if self.skip_outline or attempts[topic] > 1 or "先放" in overview.get("question", ""):
                answer = "跳过这题"
                self.report.setdefault("limitations", []).append("Outline target " + str(topic) + " did not advance after the supplied synthetic answer; explicit supported skip was used.")
            else:
                answer = answers.get(topic, "这部分我暂时记不清。")
            snapshot = self.life(snapshot, "answer", answer)
            if attempts[topic] >= 3 and snapshot.get("life_overview", {}).get("question_id") == topic:
                raise Failure("Supported outline skip did not advance target " + str(topic))
        self.check("outline_reaches_review", snapshot.get("life_overview", {}).get("status") in ("review", "confirmed"))
        if snapshot["life_overview"]["status"] == "review":
            snapshot = self.life(snapshot, "confirm")
        self.check("outline_confirmed", snapshot["life_overview"]["status"] == "confirmed")
        self.report["outline_fields"] = len(snapshot["life_overview"].get("fields", []))
        self.save_report()
        return snapshot

    def run(self):
        health = self.call("health", "GET", "/health", token=None)
        self.check("health_database_and_llm", health.get("status") == "ok" and health.get("database") == "ok" and health.get("llm_configured") is True)
        self.report["health"] = health
        if self.token is None:
            registered = self.call("register_new_isolated_family", "POST", "/api/v1/auth/register", {"username": self.credentials["username"], "password": self.credentials["password"]}, expected=(201,), token=None)
            self.family_id, self.token = registered["family_id"], registered["token"]
            self.secrets.append(self.token)
            self.credentials.update({"account_id": registered["account_id"], "family_id": self.family_id, "token": self.token, "expires_at": registered["expires_at"]})
            self.save_private()
            second = self.call("login_second_device", "POST", "/api/v1/auth/login", {"username": self.credentials["username"], "password": self.credentials["password"]}, token=None)
            self.secrets.append(second["token"])
            self.credentials["secondary_token"] = second["token"]
            self.save_private()
            self.check("two_device_tokens_differ", second["token"] != self.token)
            self.call("first_device_still_valid", "GET", "/api/v1/auth/me")
            self.call("second_device_valid", "GET", "/api/v1/auth/me", token=second["token"])
            self.call("logout_second_device", "POST", "/api/v1/auth/logout", token=second["token"], expected=(204,))
            self.call("second_device_revoked", "GET", "/api/v1/auth/me", token=second["token"], expected=(401,))
            self.call("first_device_survives_other_logout", "GET", "/api/v1/auth/me")
        else:
            identity = self.call("resume_owned_test_family", "GET", "/api/v1/auth/me")
            self.check("resume_identity_matches_verifier", identity["family_id"] == self.family_id and identity["account_id"] == self.credentials["account_id"])
        try:
            people = self.call("new_family_is_empty", "GET", "/api/v1/family-members/", query={"family_id": self.family_id})
        except Failure:
            if self.person_id is None:
                raise
            # Continue other independent checks only for the already-verified test-owned person.
            person = self.call("read_known_verifier_person", "GET", "/api/v1/family-members/" + self.person_id)
            self.check("known_person_belongs_to_verifier_family", person["family_id"] == self.family_id)
            people = [person]
            self.report.setdefault("limitations", []).append("Family-member list returned 503 while the same owned individual, memories, and session reads remained available; remaining independent checks continued through the owned person ID.")
        member_body = {"family_id": self.family_id, "client_request_id": str(uuid.uuid4()), "name": "林秋禾", "relationship": "奶奶", "birth_date": "1945-06-01"}
        if self.person_id is None:
            self.check("writes_only_to_new_empty_family", not people)
            person = self.call("create_demo_person", "POST", "/api/v1/family-members/", member_body, expected=(201,))
            self.person_id = person["id"]
            self.credentials["person_id"] = self.person_id
            self.save_private()
            repeated = self.call("repeat_person_request", "POST", "/api/v1/family-members/", member_body, expected=(200, 201))
            self.check("person_request_is_idempotent", repeated["id"] == self.person_id)
        else:
            self.check("resume_only_existing_verifier_person", len(people) == 1 and people[0]["id"] == self.person_id)
        snapshot = self.complete_outline(self.open_conversation())
        session_id = snapshot["session"]["id"]
        self.call("reject_stale_interview_version", "POST", "/api/v1/chat/sessions/" + session_id + "/interview", {"module": "childhood", "expected_version": snapshot["session"]["version"] + 1000}, expected=(409,))
        snapshot = self.call("select_childhood_module", "POST", "/api/v1/chat/sessions/" + session_id + "/interview", {"module": "childhood", "expected_version": snapshot["session"]["version"]}, retry=True)
        photo_id = self.credentials.get("story_photo_id") or str(uuid.uuid4())
        self.credentials.update({"story_photo_id": photo_id, "session_id": session_id})
        self.save_private()
        photo = self.call("upload_chat_photo", "POST", "/api/v1/chat/sessions/" + session_id + "/media", query={"client_request_id": photo_id}, file=png(), expected=(201,))
        repeat_photo = self.call("repeat_photo_upload", "POST", "/api/v1/chat/sessions/" + session_id + "/media", query={"client_request_id": photo_id}, file=png(), expected=(200, 201))
        self.check("photo_identity_is_stable", photo["id"] == repeat_photo["id"] == photo_id)
        self.call("reject_changed_photo_bytes", "POST", "/api/v1/chat/sessions/" + session_id + "/media", query={"client_request_id": photo_id}, file=png(7), expected=(409,))
        image = self.call("download_private_photo", "GET", photo["url"], raw=True)
        self.check("photo_download_is_jpeg", image.startswith(b"\xff\xd8"))
        narration = "1952年秋天，我七岁，在苏州乡下自家院子里跟母亲学习做桂花糕。母亲先把桂花拌进米粉，再让我一点点加水揉匀。我第一次用力太大，把木模扣歪了，母亲笑着扶住我的手，又示范了一遍。桂花糕蒸好后，哥哥分走了第一块，我尝到第二块，心里甜滋滋的。这是一次虚构的应用验收讲述。"
        message_body = self.credentials.get("story_message") or {"content": narration, "attachment_ids": [photo_id], "client_request_id": str(uuid.uuid4())}
        self.credentials["story_message"] = message_body
        self.save_private()
        snapshot = self.call("send_story_with_photo", "POST", "/api/v1/chat/sessions/" + session_id + "/conversation/messages", message_body, retry=True)
        replay = self.call("replay_same_story_request", "POST", "/api/v1/chat/sessions/" + session_id + "/conversation/messages", message_body, retry=True)
        users = [message for message in replay["messages"] if message["id"] == message_body["client_request_id"]]
        self.check("message_retry_does_not_duplicate", len(users) == 1 and users[0].get("attachments", [{}])[0].get("id") == photo_id)
        if not snapshot.get("can_generate"):
            control = self.credentials.get("save_control") or {"content": "请保存这段回忆。", "attachment_ids": [], "client_request_id": str(uuid.uuid4())}
            self.credentials["save_control"] = control
            self.save_private()
            snapshot = self.call("request_review_and_save", "POST", "/api/v1/chat/sessions/" + session_id + "/conversation/messages", control, retry=True)
        self.check("actual_server_allows_draft", bool(snapshot.get("can_generate")))
        draft = self.call("generate_real_draft", "POST", "/api/v1/chat/sessions/" + session_id + "/draft", retry=True)
        draft = self.call("read_draft", "GET", "/api/v1/memory-drafts/" + draft["id"])
        old_revision = draft["revision"]
        draft = self.call("edit_draft_before_confirm", "PATCH", "/api/v1/memory-drafts/" + draft["id"], {"revision": old_revision, "title": "院子里的桂花香", "summary": draft["memory"].get("summary") or narration})
        self.check("draft_edit_changes_revision", draft["revision"] != old_revision and draft.get("manually_edited") is True)
        self.call("reject_old_draft_revision", "POST", "/api/v1/memory-drafts/" + draft["id"] + "/confirm", {"revision": old_revision}, expected=(409,))
        memory = self.call("confirm_reviewed_draft", "POST", "/api/v1/memory-drafts/" + draft["id"] + "/confirm", {"revision": draft["revision"]})
        repeat_saved = self.call("repeat_draft_confirmation", "POST", "/api/v1/memory-drafts/" + draft["id"] + "/confirm", {"revision": draft["revision"]})
        self.check("confirmation_is_idempotent", repeat_saved["id"] == memory["id"])
        self.kept_memories.append(memory["id"])
        self.credentials["memory_ids"] = self.kept_memories
        self.save_private()
        memory = self.call("read_saved_memory", "GET", "/api/v1/memories/" + memory["id"])
        self.check("saved_memory_retains_story_photo", photo_id in [item["id"] for item in memory.get("media_assets", [])])
        edited_body = self.edit_body(memory, title="院子里的桂花香", time=self.dimension("known", "1952-09-01"), memory_date="1952-09-01")
        edited = self.call("edit_saved_memory", "PATCH", "/api/v1/memories/" + memory["id"], edited_body)
        self.call("reject_stale_memory_version", "PATCH", "/api/v1/memories/" + memory["id"], edited_body, expected=(409,))
        memory = edited
        self.call("preview_time_linkage", "POST", "/api/v1/memories/" + memory["id"] + "/time-preview", {"family_id": self.family_id, "version": memory["version"], "title": memory["title"], "summary": memory.get("summary") or narration, "old_time": self.dimension("known", "1952-09-01"), "new_time": self.dimension("known", "1953-09-01")})
        pending_id = str(uuid.uuid4())
        self.call("upload_pending_memory_photo", "POST", "/api/v1/memories/" + memory["id"] + "/media", query={"family_id": self.family_id, "client_request_id": pending_id}, file=png(12), expected=(201,))
        self.call("discard_pending_memory_photo", "DELETE", "/api/v1/memories/" + memory["id"] + "/media/" + pending_id, query={"family_id": self.family_id}, expected=(204,))
        self.call("discarded_photo_is_gone", "GET", "/api/v1/media/" + pending_id, expected=(404,))
        for title, date, content in [
            ("第一次远行", "1964-05-01", "1964年春天，我第一次坐火车去上海。父亲把煮鸡蛋包在手帕里，叮嘱我到了以后报平安。车窗外的田野缓缓向后退，我第一次觉得世界这样大。这是一则虚构的界面验收回忆。"),
            ("和家人一起过年", "1988-02-16", "1988年除夕，我们一家在苏州的小屋里包饺子。丈夫擀皮，女儿摆碗筷，我在灶边看着锅里的热气。饭桌不大，却坐满了亲近的人。这是一则虚构的界面验收回忆。"),
        ]:
            fixture = self.call("create_synthetic_demo_memory", "POST", "/api/v1/memories/", {"family_id": self.family_id, "person_ids": [self.person_id], "primary_person_id": self.person_id, "title": title, "raw_content": content, "summary": content, "memory_date": date, "location": "苏州", "information": {"time": self.dimension("known", date), "place": self.dimension("known", "苏州")}}, expected=(201,))
            self.kept_memories.append(fixture["id"])
            demo_photo_id = str(uuid.uuid4())
            self.call("upload_demo_memory_photo", "POST", "/api/v1/memories/" + fixture["id"] + "/media", query={"family_id": self.family_id, "client_request_id": demo_photo_id}, file=png(len(self.kept_memories) * 5), expected=(201,))
            self.call("attach_demo_memory_photo", "PATCH", "/api/v1/memories/" + fixture["id"], self.edit_body(fixture, media_ids=[demo_photo_id]))
        memoir_path = "/api/v1/families/" + self.family_id + "/members/" + self.person_id + "/memoir"
        book = self.call("read_memoir", "GET", memoir_path)
        self.check("memoir_contains_three_demo_stories", len(book["stories"]) == 3)
        cover_id = str(uuid.uuid4())
        self.call("upload_memoir_cover", "POST", memoir_path + "/photos", query={"client_request_id": cover_id}, file=png(23), expected=(201,))
        settings = book["settings"]
        settings.update({"title": "秋禾的回忆录", "subtitle": "一册旧时光 · 虚构验收故事", "coverTemplate": "collage", "coverPhotos": [{"id": photo_id, "sourceMemoryId": memory["id"], "x": 0, "y": 0, "zoom": 1}, {"id": cover_id, "sourceMemoryId": None, "x": 0.1, "y": 0, "zoom": 1.1}], "ordering": "manual", "storyOrder": list(reversed(self.kept_memories)), "textSize": 16})
        book_body = {"version": book["version"], "requestId": str(uuid.uuid4()), "settings": settings}
        updated = self.call("save_memoir_settings", "PUT", memoir_path, book_body)
        replay_book = self.call("repeat_memoir_save", "PUT", memoir_path, book_body)
        self.check("memoir_request_is_idempotent", updated["version"] == replay_book["version"])
        self.call("reject_stale_memoir_version", "PUT", memoir_path, {**book_body, "requestId": str(uuid.uuid4())}, expected=(409,))
        extra = self.call("create_deletion_test_person", "POST", "/api/v1/family-members/", {**member_body, "client_request_id": str(uuid.uuid4()), "name": "待清理验证人物"}, expected=(201,))
        self.extra_people.append(extra["id"])
        deletion = self.call("create_deletion_test_memory", "POST", "/api/v1/memories/", {"family_id": self.family_id, "person_ids": [extra["id"]], "primary_person_id": extra["id"], "title": "将删除的测试记录", "raw_content": "仅用于验证删除，不作为演示数据。", "summary": "仅用于验证删除，不作为演示数据。"}, expected=(201,))
        self.extra_memories.append(deletion["id"])
        self.call("reject_stale_delete_version", "DELETE", "/api/v1/memories/" + deletion["id"], query={"family_id": self.family_id, "version": deletion["version"] + 1}, expected=(409,))
        self.call("delete_test_memory", "DELETE", "/api/v1/memories/" + deletion["id"], query={"family_id": self.family_id, "version": deletion["version"]})
        self.extra_memories.remove(deletion["id"])
        self.call("deleted_memory_is_gone", "GET", "/api/v1/memories/" + deletion["id"], expected=(404,))
        self.call("delete_test_person", "DELETE", "/api/v1/family-members/" + extra["id"], expected=(204,))
        self.extra_people.remove(extra["id"])
        people = self.call("final_demo_people", "GET", "/api/v1/family-members/", query={"family_id": self.family_id})
        memories = self.call("final_demo_memories", "GET", "/api/v1/memories/", query={"family_id": self.family_id})
        self.check("only_demo_person_and_three_memories_remain", len(people) == 1 and len(memories) == 3)
        self.report.update({"completed": True, "kept_demo_people": len(people), "kept_demo_memories": len(memories),
                            "ai_generated_memories": 1, "explicit_synthetic_fixtures": 2})
        self.credentials["memory_ids"] = self.kept_memories
        self.save_private()

    def cleanup(self):
        for memory_id in list(self.extra_memories):
            try:
                memory = self.call("cleanup_read_extra_memory", "GET", "/api/v1/memories/" + memory_id)
                self.call("cleanup_delete_extra_memory", "DELETE", "/api/v1/memories/" + memory_id, query={"family_id": self.family_id, "version": memory["version"]})
            except Exception:
                self.report.setdefault("cleanup_failures", []).append("extra_memory")
        for person_id in list(self.extra_people):
            try:
                self.call("cleanup_delete_extra_person", "DELETE", "/api/v1/family-members/" + person_id, expected=(204,))
            except Exception:
                self.report.setdefault("cleanup_failures", []).append("extra_person")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Create one fresh test family and run live validation")
    parser.add_argument("--base-url", default="https://aimemory.47-82-83-74.nip.io")
    parser.add_argument("--artifacts", type=Path, default=Path(__file__).resolve().parents[1] / "artifacts/android-20261021")
    parser.add_argument("--resume-owned-run", type=Path, help="Resume this verifier's unfinished private outline artifact")
    parser.add_argument("--skip-outline", action="store_true", help="Exercise the explicit supported skip branch for synthetic outline targets")
    args = parser.parse_args()
    if not args.execute:
        parser.error("Explicit --execute is required; existing credentials are never accepted")
    validation = Validation(args.base_url, args.artifacts.resolve(), args.resume_owned_run, args.skip_outline)
    print("PRIVATE_CREDENTIAL_FILE=" + str(validation.private_path), flush=True)
    print("REPORT_FILE=" + str(validation.report_path), flush=True)
    try:
        validation.run()
    except KeyboardInterrupt:
        validation.report["failure"] = "Local verifier interrupted; any completed remote operations are retained in the report."
        print("LIVE_VALIDATION_INCOMPLETE: local verifier interrupted", flush=True)
    except Exception as error:
        validation.report["failure"] = validation.scrub(str(error))
        print("LIVE_VALIDATION_INCOMPLETE: " + validation.scrub(str(error)), flush=True)
    finally:
        validation.cleanup()
        validation.report["finished_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        validation.report["all_checks_passed"] = validation.report["completed"] and all(item["passed"] for item in validation.report["checks"])
        validation.save_report()
    print("LIVE_VALIDATION_COMPLETE=" + str(validation.report["completed"]), flush=True)
    print("LIVE_VALIDATION_ALL_CHECKS_PASS=" + str(validation.report["all_checks_passed"]), flush=True)
    return 0 if validation.report["completed"] else 1


if __name__ == "__main__":
    sys.exit(main())
