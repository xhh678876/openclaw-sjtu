#!/usr/bin/env python3
"""Read-only Shuiyuan Discourse helper for OpenClaw skill usage."""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

DEFAULT_SITE = "https://shuiyuan.sjtu.edu.cn"
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_READ_LENGTH = 50000
DEFAULT_AUTH_PATH = Path.home() / ".openclaw" / "skills-data" / "shuiyuan-discourse" / "auth.json"

ALLOWED_READ_PREFIXES = (
    "/about.json",
    "/site.json",
    "/latest.json",
    "/search.json",
    "/filter.json",
    "/t/",
    "/posts/",
)

ENV_KEY_NAMES = (
    "SHUIYUAN_USER_API_KEY",
    "DISCOURSE_USER_API_KEY",
    "USER_API_KEY",
)
ENV_CLIENT_ID_NAMES = (
    "SHUIYUAN_USER_API_CLIENT_ID",
    "DISCOURSE_USER_API_CLIENT_ID",
    "USER_API_CLIENT_ID",
)


class SkillError(Exception):
    """Base user-facing skill error."""


class ReadOnlyViolation(SkillError):
    """Raised when a request attempts non-read behavior."""


class CredentialError(SkillError):
    """Raised when no credential can be resolved."""


@dataclass
class Credential:
    site: str
    user_api_key: str
    user_api_client_id: Optional[str]
    source: str


@dataclass
class RequestResult:
    data: Any
    source_url: str
    runtime: str
    fallback_reason: Optional[str]


@dataclass
class HttpRequestError(SkillError):
    status: int
    body: str
    url: str
    runtime: str

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error_type": "http_error",
            "status": self.status,
            "url": self.url,
            "runtime": self.runtime,
        }
        parsed = _safe_json_loads(self.body)
        if isinstance(parsed, dict):
            payload["response"] = parsed
            if "error_type" in parsed:
                payload["discourse_error_type"] = parsed.get("error_type")
            if "errors" in parsed:
                payload["discourse_errors"] = parsed.get("errors")
        else:
            payload["response_text"] = self.body[:2000]
        return payload


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _json_out(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _normalize_site(site: str) -> str:
    return site.rstrip("/")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _real_path(path_like: str) -> Path:
    return Path(os.path.expanduser(path_like)).resolve()


def _read_json_file(path: Path) -> Optional[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SkillError(f"Invalid JSON file: {path} ({exc})") from exc


def _write_json_file_secure(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def _extract_credential_for_site(raw: dict[str, Any], site: str) -> Optional[tuple[str, Optional[str]]]:
    target = _normalize_site(site)

    if isinstance(raw.get("site"), str) and isinstance(raw.get("user_api_key"), str):
        raw_site = _normalize_site(raw["site"])
        if raw_site == target:
            client_id = raw.get("user_api_client_id")
            if client_id is not None and not isinstance(client_id, str):
                client_id = str(client_id)
            return raw["user_api_key"], client_id

    pairs = raw.get("auth_pairs")
    if isinstance(pairs, list):
        for pair in pairs:
            if not isinstance(pair, dict):
                continue
            pair_site = pair.get("site")
            pair_key = pair.get("user_api_key")
            if not isinstance(pair_site, str) or not isinstance(pair_key, str):
                continue
            if _normalize_site(pair_site) != target:
                continue
            client_id = pair.get("user_api_client_id")
            if client_id is not None and not isinstance(client_id, str):
                client_id = str(client_id)
            return pair_key, client_id
    return None


def _load_env_credential(site: str) -> Optional[Credential]:
    key = None
    for name in ENV_KEY_NAMES:
        value = os.getenv(name)
        if value:
            key = value
            break

    if not key:
        return None

    client_id = None
    for name in ENV_CLIENT_ID_NAMES:
        value = os.getenv(name)
        if value:
            client_id = value
            break

    return Credential(
        site=_normalize_site(site),
        user_api_key=key,
        user_api_client_id=client_id,
        source="env",
    )


def _load_file_credential(site: str, path: Path, source: str) -> Optional[Credential]:
    raw = _read_json_file(path)
    if raw is None:
        return None
    match = _extract_credential_for_site(raw, site)
    if not match:
        return None
    key, client_id = match
    return Credential(
        site=_normalize_site(site),
        user_api_key=key,
        user_api_client_id=client_id,
        source=source,
    )


def resolve_credential(
    site: str,
    auth_path: Path,
) -> Credential:
    env_credential = _load_env_credential(site)
    if env_credential:
        return env_credential

    auth_credential = _load_file_credential(site, auth_path, "auth_file")
    if auth_credential:
        return auth_credential

    raise CredentialError(
        "No User API credential found. Run 'auth init' or 'auth import', or set SHUIYUAN_USER_API_KEY."
    )


def _build_headers(cred: Credential) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Api-Key": cred.user_api_key,
    }
    if cred.user_api_client_id:
        headers["User-Api-Client-Id"] = cred.user_api_client_id
    return headers


def _ensure_read_only(method: str, path: str) -> None:
    if method.upper() != "GET":
        raise ReadOnlyViolation(f"Blocked non-GET method: {method}")
    if not path.startswith("/"):
        raise ReadOnlyViolation(f"Blocked path without absolute prefix: {path}")
    if not any(path.startswith(prefix) for prefix in ALLOWED_READ_PREFIXES):
        raise ReadOnlyViolation(f"Blocked path outside read allowlist: {path}")


def _compose_url(site: str, path: str, params: Optional[dict[str, Any]]) -> str:
    base = _normalize_site(site)
    url = f"{base}{path}"
    if not params:
        return url
    query = urllib.parse.urlencode(params, doseq=True)
    return f"{url}?{query}"


def _request_python(
    site: str,
    path: str,
    params: Optional[dict[str, Any]],
    cred: Credential,
    timeout: float,
) -> RequestResult:
    _ensure_read_only("GET", path)
    url = f"{_normalize_site(site)}{path}"

    # Prefer requests when available, but keep a stdlib path so
    # the skill can run without external Python dependencies.
    if requests is None:
        final_url = _compose_url(site, path, params)
        req = urllib.request.Request(
            final_url,
            method="GET",
            headers=_build_headers(cred),
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.getcode()
                body_bytes = resp.read()
                body = body_bytes.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise HttpRequestError(
                status=exc.code,
                body=err_body,
                url=final_url,
                runtime="python-stdlib",
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"python stdlib request failed: {exc}") from exc

        if status < 200 or status >= 300:
            raise HttpRequestError(
                status=status,
                body=body,
                url=final_url,
                runtime="python-stdlib",
            )

        parsed = _safe_json_loads(body)
        if parsed is None:
            raise RuntimeError("python stdlib response is not valid JSON")
        return RequestResult(
            data=parsed,
            source_url=final_url,
            runtime="python-stdlib",
            fallback_reason=None,
        )

    try:
        response = requests.get(url, params=params, headers=_build_headers(cred), timeout=timeout)
    except requests.RequestException as exc:  # type: ignore[attr-defined]
        raise RuntimeError(f"python request failed: {exc}") from exc

    if response.status_code < 200 or response.status_code >= 300:
        raise HttpRequestError(
            status=response.status_code,
            body=response.text,
            url=response.url,
            runtime="python",
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"python response is not valid JSON: {exc}") from exc

    return RequestResult(data=data, source_url=response.url, runtime="python", fallback_reason=None)


def _request_curl(
    site: str,
    path: str,
    params: Optional[dict[str, Any]],
    cred: Credential,
    timeout: float,
) -> RequestResult:
    _ensure_read_only("GET", path)
    source_url = _compose_url(site, path, params)

    cmd = [
        "curl",
        "-sS",
        "-L",
        "--max-time",
        str(int(timeout)),
        "-H",
        "Accept: application/json",
        "-H",
        f"User-Api-Key: {cred.user_api_key}",
    ]
    if cred.user_api_client_id:
        cmd.extend(["-H", f"User-Api-Client-Id: {cred.user_api_client_id}"])
    cmd.extend(["-w", "\n%{http_code}", source_url])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(f"curl request failed: {stderr or 'unknown curl error'}")

    output = proc.stdout
    if "\n" not in output:
        raise RuntimeError("curl output parsing failed: missing HTTP status trailer")

    body, status_text = output.rsplit("\n", 1)
    try:
        status = int(status_text.strip())
    except ValueError as exc:
        raise RuntimeError(f"curl output parsing failed: invalid status '{status_text}'") from exc

    if status < 200 or status >= 300:
        raise HttpRequestError(status=status, body=body, url=source_url, runtime="curl")

    parsed = _safe_json_loads(body)
    if parsed is None:
        raise RuntimeError("curl response is not valid JSON")

    return RequestResult(data=parsed, source_url=source_url, runtime="curl", fallback_reason=None)


def request_json(
    site: str,
    path: str,
    params: Optional[dict[str, Any]],
    cred: Credential,
    runtime: str,
    timeout: float,
) -> RequestResult:
    if runtime == "python":
        return _request_python(site, path, params, cred, timeout)
    if runtime == "curl":
        return _request_curl(site, path, params, cred, timeout)

    if runtime != "auto":
        raise SkillError(f"Unsupported runtime mode: {runtime}")

    try:
        return _request_python(site, path, params, cred, timeout)
    except RuntimeError as exc:
        fallback_result = _request_curl(site, path, params, cred, timeout)
        fallback_result.fallback_reason = str(exc)
        return fallback_result


def _topic_url(site: str, topic_id: Any, slug: Any) -> Optional[str]:
    if topic_id is None:
        return None
    safe_slug = str(slug) if slug is not None else str(topic_id)
    return f"{_normalize_site(site)}/t/{safe_slug}/{topic_id}"


def _topic_post_url(site: str, topic_id: Any, slug: Any, post_number: Any) -> Optional[str]:
    if topic_id is None or post_number is None:
        return None
    safe_slug = str(slug) if slug is not None else str(topic_id)
    return f"{_normalize_site(site)}/t/{safe_slug}/{topic_id}/{post_number}"


def _save_runtime_credential(path: Path, site: str, key: str, client_id: Optional[str]) -> None:
    payload = {
        "site": _normalize_site(site),
        "user_api_key": key,
        "user_api_client_id": client_id,
        "updated_at": _utc_now_iso(),
    }
    _write_json_file_secure(path, payload)


def cmd_auth_status(args: argparse.Namespace) -> dict[str, Any]:
    auth_path = _real_path(args.auth_file)

    env_credential = _load_env_credential(args.site)
    auth_credential = _load_file_credential(args.site, auth_path, "auth_file")
    resolved = env_credential or auth_credential

    return {
        "ok": True,
        "site": _normalize_site(args.site),
        "resolved": {
            "found": resolved is not None,
            "source": resolved.source if resolved else "none",
            "has_user_api_key": resolved is not None,
            "has_user_api_client_id": bool(resolved and resolved.user_api_client_id),
        },
        "paths": {
            "auth_file": str(auth_path),
            "auth_file_exists": auth_path.exists(),
        },
        "guidance": (
            "Credential is available."
            if resolved
            else "No credential found. Run: auth init (interactive link flow) or auth import."
        ),
    }


def cmd_auth_init(args: argparse.Namespace) -> dict[str, Any]:
    site = _normalize_site(args.site)
    client_id = args.client_id or str(uuid.uuid4())
    nonce = args.nonce or secrets.token_urlsafe(32)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")

    params = {
        "application_name": args.application_name,
        "client_id": client_id,
        "scopes": args.scopes,
        "public_key": public_key_pem,
        "nonce": nonce,
    }
    auth_url = f"{site}/user-api-key/new?{urllib.parse.urlencode(params)}"

    payload_input = args.payload
    if not payload_input:
        print(auth_url)
        payload_input = input("Paste encrypted payload: ").strip()

    if not payload_input:
        raise SkillError("No payload provided.")

    try:
        decrypted = private_key.decrypt(base64.b64decode(payload_input), padding.PKCS1v15())
        payload = json.loads(decrypted.decode("utf-8"))
    except Exception as exc:
        raise SkillError(f"Failed to decrypt/parse payload: {exc}") from exc

    key = payload.get("key")
    payload_nonce = payload.get("nonce")
    if not isinstance(key, str) or not key:
        raise SkillError("Payload missing field: key")
    if payload_nonce != nonce:
        raise SkillError("Nonce mismatch in payload")

    save_path = _real_path(args.auth_file)
    _save_runtime_credential(save_path, site, key, client_id)

    return {
        "ok": True,
        "site": site,
        "auth_url": auth_url,
        "saved": {
            "path": str(save_path),
            "user_api_client_id": client_id,
            "updated_at": _utc_now_iso(),
        },
        "note": "Runtime credential saved. Keep key secret.",
    }


def cmd_auth_import(args: argparse.Namespace) -> dict[str, Any]:
    site = _normalize_site(args.site)
    client_id = args.client_id or None
    save_path = _real_path(args.auth_file)
    _save_runtime_credential(save_path, site, args.user_api_key, client_id)

    return {
        "ok": True,
        "site": site,
        "saved": {
            "path": str(save_path),
            "has_client_id": bool(client_id),
            "updated_at": _utc_now_iso(),
        },
    }


def _require_credential(args: argparse.Namespace) -> Credential:
    return resolve_credential(
        site=args.site,
        auth_path=_real_path(args.auth_file),
    )


def _request_with_common(args: argparse.Namespace, path: str, params: Optional[dict[str, Any]]) -> tuple[Credential, RequestResult]:
    cred = _require_credential(args)
    result = request_json(
        site=args.site,
        path=path,
        params=params,
        cred=cred,
        runtime=args.runtime,
        timeout=args.timeout,
    )
    return cred, result


def cmd_search(args: argparse.Namespace) -> dict[str, Any]:
    cred, result = _request_with_common(args, "/search.json", {"q": args.query})
    topics = result.data.get("topics") if isinstance(result.data, dict) else None
    topics = topics if isinstance(topics, list) else []

    rows = []
    for topic in topics[: args.max_results]:
        topic_id = topic.get("id")
        slug = topic.get("slug")
        rows.append(
            {
                "id": topic_id,
                "slug": slug,
                "title": topic.get("title"),
                "url": _topic_url(args.site, topic_id, slug),
            }
        )

    payload: dict[str, Any] = {
        "ok": True,
        "site": _normalize_site(args.site),
        "runtime": result.runtime,
        "credential_source": cred.source,
        "source_url": result.source_url,
        "query": args.query,
        "results": rows,
        "meta": {
            "total": len(topics),
            "returned": len(rows),
            "has_more": len(topics) > args.max_results,
        },
    }
    if result.fallback_reason:
        payload["fallback_reason"] = result.fallback_reason
    return payload


def cmd_latest(args: argparse.Namespace) -> dict[str, Any]:
    cred, result = _request_with_common(args, "/latest.json", {"page": args.page})
    root = result.data if isinstance(result.data, dict) else {}
    topic_list = root.get("topic_list") if isinstance(root.get("topic_list"), dict) else {}
    topics = topic_list.get("topics") if isinstance(topic_list.get("topics"), list) else []

    rows = []
    for topic in topics[: args.max_results]:
        topic_id = topic.get("id")
        slug = topic.get("slug")
        rows.append(
            {
                "id": topic_id,
                "slug": slug,
                "title": topic.get("title"),
                "category_id": topic.get("category_id"),
                "posts_count": topic.get("posts_count"),
                "views": topic.get("views"),
                "last_posted_at": topic.get("last_posted_at"),
                "url": _topic_url(args.site, topic_id, slug),
            }
        )

    payload: dict[str, Any] = {
        "ok": True,
        "site": _normalize_site(args.site),
        "runtime": result.runtime,
        "credential_source": cred.source,
        "source_url": result.source_url,
        "results": rows,
        "meta": {
            "page": args.page,
            "total": len(topics),
            "returned": len(rows),
            "has_more": bool(topic_list.get("more_topics_url")) or len(topics) > args.max_results,
        },
    }
    if result.fallback_reason:
        payload["fallback_reason"] = result.fallback_reason
    return payload


def cmd_categories(args: argparse.Namespace) -> dict[str, Any]:
    cred, result = _request_with_common(args, "/site.json", None)
    root = result.data if isinstance(result.data, dict) else {}
    categories = root.get("categories") if isinstance(root.get("categories"), list) else []

    rows = []
    for cat in categories:
        cid = cat.get("id")
        slug = cat.get("slug")
        rows.append(
            {
                "id": cid,
                "name": cat.get("name"),
                "slug": slug,
                "parent_category_id": cat.get("parent_category_id"),
                "read_restricted": cat.get("read_restricted"),
                "topic_count": cat.get("topic_count"),
                "post_count": cat.get("post_count"),
                "url": f"{_normalize_site(args.site)}/c/{slug}/{cid}" if cid is not None else None,
            }
        )

    payload: dict[str, Any] = {
        "ok": True,
        "site": _normalize_site(args.site),
        "runtime": result.runtime,
        "credential_source": cred.source,
        "source_url": result.source_url,
        "categories": rows,
        "meta": {"total": len(rows)},
    }
    if result.fallback_reason:
        payload["fallback_reason"] = result.fallback_reason
    return payload


def cmd_filter(args: argparse.Namespace) -> dict[str, Any]:
    params = {
        "q": args.filter,
        "page": args.page,
        "per_page": args.per_page,
    }
    cred, result = _request_with_common(args, "/filter.json", params)

    root = result.data if isinstance(result.data, dict) else {}
    topic_list = root.get("topic_list") if isinstance(root.get("topic_list"), dict) else root
    topics = topic_list.get("topics") if isinstance(topic_list.get("topics"), list) else []

    rows = []
    for topic in topics[: args.per_page]:
        tid = topic.get("id")
        slug = topic.get("slug")
        rows.append(
            {
                "id": tid,
                "slug": slug,
                "title": topic.get("title") or topic.get("fancy_title"),
                "url": _topic_url(args.site, tid, slug),
            }
        )

    payload: dict[str, Any] = {
        "ok": True,
        "site": _normalize_site(args.site),
        "runtime": result.runtime,
        "credential_source": cred.source,
        "source_url": result.source_url,
        "filter": args.filter,
        "results": rows,
        "meta": {
            "page": args.page,
            "limit": args.per_page,
            "returned": len(rows),
            "has_more": bool(topic_list.get("more_topics_url") or topic_list.get("more_url")) or len(topics) > args.per_page,
        },
    }
    if result.fallback_reason:
        payload["fallback_reason"] = result.fallback_reason
    return payload


def cmd_post(args: argparse.Namespace) -> dict[str, Any]:
    cred, result = _request_with_common(args, f"/posts/{args.post_id}.json", {"include_raw": "true"})
    root = result.data if isinstance(result.data, dict) else {}
    raw = root.get("raw") or root.get("cooked") or ""
    raw = str(raw)
    truncated = raw[: args.max_read_length]

    payload: dict[str, Any] = {
        "ok": True,
        "site": _normalize_site(args.site),
        "runtime": result.runtime,
        "credential_source": cred.source,
        "source_url": result.source_url,
        "post": {
            "id": root.get("id", args.post_id),
            "topic_id": root.get("topic_id"),
            "topic_slug": root.get("topic_slug"),
            "post_number": root.get("post_number"),
            "username": root.get("username"),
            "created_at": root.get("created_at"),
            "url": _topic_post_url(
                args.site,
                root.get("topic_id"),
                root.get("topic_slug"),
                root.get("post_number"),
            ),
            "raw": truncated,
            "raw_len": len(raw),
            "truncated": len(raw) > args.max_read_length,
        },
    }
    if result.fallback_reason:
        payload["fallback_reason"] = result.fallback_reason
    return payload


def cmd_topic(args: argparse.Namespace) -> dict[str, Any]:
    cred = _require_credential(args)
    start = max(1, args.start_post_number)
    collected: list[dict[str, Any]] = []
    topic_meta: dict[str, Any] = {}
    runtimes: list[str] = []
    fallback_reason: Optional[str] = None
    current = start

    for _ in range(args.max_batches):
        if len(collected) >= args.post_limit:
            break

        params: dict[str, Any] = {"include_raw": "true"}
        if current > 1:
            params["post_number"] = current

        result = request_json(
            site=args.site,
            path=f"/t/{args.topic_id}.json",
            params=params,
            cred=cred,
            runtime=args.runtime,
            timeout=args.timeout,
        )

        runtimes.append(result.runtime)
        if result.fallback_reason and fallback_reason is None:
            fallback_reason = result.fallback_reason

        root = result.data if isinstance(result.data, dict) else {}
        if not topic_meta:
            topic_meta = root
            api_source_url = result.source_url

        post_stream = root.get("post_stream") if isinstance(root.get("post_stream"), dict) else {}
        posts = post_stream.get("posts") if isinstance(post_stream.get("posts"), list) else []
        posts_sorted = sorted(
            (p for p in posts if isinstance(p, dict)),
            key=lambda p: int(p.get("post_number", 0)),
        )
        posts_filtered = [p for p in posts_sorted if int(p.get("post_number", 0)) >= current]

        if not posts_filtered:
            break

        for post in posts_filtered:
            if len(collected) >= args.post_limit:
                break
            raw = post.get("raw") or post.get("cooked") or post.get("excerpt") or ""
            raw = str(raw)
            truncated = raw[: args.max_read_length]
            pnum = post.get("post_number")
            collected.append(
                {
                    "id": post.get("id"),
                    "post_number": pnum,
                    "username": post.get("username"),
                    "created_at": post.get("created_at"),
                    "url": _topic_post_url(args.site, args.topic_id, root.get("slug"), pnum),
                    "raw": truncated,
                    "raw_len": len(raw),
                    "truncated": len(raw) > args.max_read_length,
                }
            )

        last_post = posts_filtered[-1]
        current = int(last_post.get("post_number", current)) + 1

    if not topic_meta:
        raise SkillError(f"Failed to load topic {args.topic_id}")

    posts_count = int(topic_meta.get("posts_count") or len(collected))
    has_more = posts_count > (start + len(collected) - 1)

    payload: dict[str, Any] = {
        "ok": True,
        "site": _normalize_site(args.site),
        "runtime": runtimes[-1] if runtimes else args.runtime,
        "runtime_sequence": runtimes,
        "credential_source": cred.source,
        "source_url": api_source_url,
        "topic": {
            "id": topic_meta.get("id", args.topic_id),
            "title": topic_meta.get("title"),
            "slug": topic_meta.get("slug"),
            "category_id": topic_meta.get("category_id"),
            "tags": topic_meta.get("tags") if isinstance(topic_meta.get("tags"), list) else [],
            "posts_count": posts_count,
            "url": _topic_url(args.site, args.topic_id, topic_meta.get("slug")),
            "posts": collected,
        },
        "meta": {
            "start_post_number": start,
            "returned_posts": len(collected),
            "has_more": has_more,
        },
    }
    if fallback_reason:
        payload["fallback_reason"] = fallback_reason
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Shuiyuan Discourse helper")
    parser.add_argument("--site", default=DEFAULT_SITE, help="Discourse site URL")
    parser.add_argument(
        "--runtime",
        default="auto",
        choices=("auto", "python", "curl"),
        help="HTTP runtime path",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Request timeout seconds")
    parser.add_argument(
        "--auth-file",
        default=str(DEFAULT_AUTH_PATH),
        help="Runtime credential file path",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    auth = subparsers.add_parser("auth", help="Credential operations")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)

    auth_status = auth_sub.add_parser("status", help="Show credential status")
    auth_status.set_defaults(func=cmd_auth_status)

    auth_init = auth_sub.add_parser("init", help="Generate auth URL and save credential")
    auth_init.add_argument("--application-name", default="OpenClaw Shuiyuan Skill")
    auth_init.add_argument("--client-id", default=None)
    auth_init.add_argument("--scopes", default="read")
    auth_init.add_argument("--nonce", default=None)
    auth_init.add_argument("--payload", default=None, help="Encrypted payload (base64)")
    auth_init.set_defaults(func=cmd_auth_init)

    auth_import = auth_sub.add_parser("import", help="Import an existing User API key")
    auth_import.add_argument("--user-api-key", required=True)
    auth_import.add_argument("--client-id", default=None)
    auth_import.set_defaults(func=cmd_auth_import)

    search = subparsers.add_parser("search", help="Search topics")
    search.add_argument("query", help="Search query")
    search.add_argument("--max-results", type=int, default=10)
    search.set_defaults(func=cmd_search)

    latest = subparsers.add_parser("latest", help="List latest topics")
    latest.add_argument("--page", type=int, default=0)
    latest.add_argument("--max-results", type=int, default=30)
    latest.set_defaults(func=cmd_latest)

    topic = subparsers.add_parser("topic", help="Read one topic and posts")
    topic.add_argument("topic_id", type=int)
    topic.add_argument("--post-limit", type=int, default=5)
    topic.add_argument("--start-post-number", type=int, default=1)
    topic.add_argument("--max-batches", type=int, default=10)
    topic.add_argument("--max-read-length", type=int, default=DEFAULT_MAX_READ_LENGTH)
    topic.set_defaults(func=cmd_topic)

    post = subparsers.add_parser("post", help="Read one post")
    post.add_argument("post_id", type=int)
    post.add_argument("--max-read-length", type=int, default=DEFAULT_MAX_READ_LENGTH)
    post.set_defaults(func=cmd_post)

    categories = subparsers.add_parser("categories", help="List categories")
    categories.set_defaults(func=cmd_categories)

    filter_cmd = subparsers.add_parser("filter", help="Filter topics")
    filter_cmd.add_argument("filter", help="Discourse filter query")
    filter_cmd.add_argument("--page", type=int, default=0)
    filter_cmd.add_argument("--per-page", type=int, default=20)
    filter_cmd.set_defaults(func=cmd_filter)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.site = _normalize_site(args.site)

    try:
        payload = args.func(args)
        if not isinstance(payload, dict):
            payload = {"ok": True, "result": payload}
        _json_out(payload)
        return 0
    except ReadOnlyViolation as exc:
        _json_out({"ok": False, "error_type": "read_only_violation", "error": str(exc)})
        return 2
    except HttpRequestError as exc:
        _json_out(exc.to_payload())
        return 3
    except CredentialError as exc:
        _json_out({"ok": False, "error_type": "credential_error", "error": str(exc)})
        return 4
    except SkillError as exc:
        _json_out({"ok": False, "error_type": "skill_error", "error": str(exc)})
        return 5
    except Exception as exc:  # pragma: no cover
        _json_out({"ok": False, "error_type": "unexpected_error", "error": str(exc)})
        return 9


if __name__ == "__main__":
    raise SystemExit(main())
