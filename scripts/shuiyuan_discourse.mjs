#!/usr/bin/env node

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { spawnSync } from "node:child_process";
import { constants, createHash, generateKeyPairSync, privateDecrypt, randomBytes, randomUUID } from "node:crypto";
import { pathToFileURL } from "node:url";

const DEFAULT_SITE = "https://shuiyuan.sjtu.edu.cn";
const DEFAULT_TIMEOUT = 15;
const DEFAULT_MAX_READ_LENGTH = 50000;
const DEFAULT_MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const DEFAULT_IMAGE_CACHE_DIR = "./.openclaw-cache/shuiyuan-discourse/image-cache";
const DEFAULT_AUTH_PATH = "~/.openclaw/skills-data/shuiyuan-discourse/auth.json";
const DEFAULT_AUTH_PENDING_PATH = "~/.openclaw/skills-data/shuiyuan-discourse/auth.pending.json";
const AUTH_PENDING_TTL_SECONDS = 1800;

const COMMANDS = new Set([
  "auth",
  "search",
  "latest",
  "topic",
  "post",
  "post-raw",
  "vision-check",
  "categories",
  "filter",
  "image",
]);

const ALLOWED_READ_PREFIXES = [
  "/about.json",
  "/site.json",
  "/latest.json",
  "/search.json",
  "/filter.json",
  "/t/",
  "/posts/",
];

const ALLOWED_IMAGE_PREFIXES = ["/uploads/", "/secure-uploads/", "/user_avatar/", "/optimized/"];
const IMAGE_EXT_RE = /\.(png|jpe?g|gif|webp|bmp|svg|avif)(?:[?#].*)?$/i;

// Removed: environment variable credential sources — only link-based auth is supported.

class SkillError extends Error {
  constructor(message) {
    super(message);
    this.name = "SkillError";
  }
}

class ReadOnlyViolation extends SkillError {
  constructor(message) {
    super(message);
    this.name = "ReadOnlyViolation";
  }
}

class CredentialError extends SkillError {
  constructor(message) {
    super(message);
    this.name = "CredentialError";
  }
}

class HttpRequestError extends SkillError {
  constructor({ status, body, url, runtime }) {
    super(`HTTP ${status} for ${url}`);
    this.name = "HttpRequestError";
    this.status = status;
    this.body = body;
    this.url = url;
    this.runtime = runtime;
  }

  toPayload() {
    const payload = {
      ok: false,
      error_type: "http_error",
      status: this.status,
      url: this.url,
      runtime: this.runtime,
    };
    const parsed = safeJsonParse(this.body);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      payload.response = parsed;
      if ("error_type" in parsed) payload.discourse_error_type = parsed.error_type;
      if ("errors" in parsed) payload.discourse_errors = parsed.errors;
    } else {
      payload.response_text = String(this.body || "").slice(0, 2000);
    }
    return payload;
  }
}

function normalizeRateLimitPayload(err) {
  const payload = err.toPayload();
  const waitSeconds =
    payload?.response?.extras?.wait_seconds ??
    payload?.response?.extras?.waitSeconds ??
    null;
  const timeLeft = payload?.response?.extras?.time_left ?? null;
  return {
    ok: true,
    rate_limited: true,
    status: payload.status,
    url: payload.url,
    runtime: payload.runtime,
    discourse_error_type: payload.discourse_error_type || "rate_limit",
    discourse_errors: payload.discourse_errors || payload.response?.errors || [],
    retry_after_seconds: typeof waitSeconds === "number" ? waitSeconds : null,
    retry_after_human: timeLeft,
    guidance:
      "Shuiyuan occasionally rate-limits read requests. Tell the user this is normal, wait for the suggested interval, then retry the same read operation.",
    response: payload.response,
  };
}

function printJson(payload) {
  process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
}

function normalizeSite(site) {
  return String(site || "").replace(/\/+$/, "");
}

function utcNowIso() {
  return new Date().toISOString();
}

function expandUserPath(p) {
  if (!p) return p;
  if (p === "~") return os.homedir();
  if (p.startsWith("~/")) return path.join(os.homedir(), p.slice(2));
  return p;
}

function resolvePath(p) {
  return path.resolve(expandUserPath(p));
}

function toPreferredReadPath(filePath, baseDir = process.cwd()) {
  const absolute = path.resolve(filePath);
  const base = path.resolve(baseDir);
  const rel = path.relative(base, absolute);
  if (!rel || rel === ".") {
    return null;
  }
  if (rel.startsWith("..") || path.isAbsolute(rel)) {
    return null;
  }
  const normalized = rel.split(path.sep).join("/");
  if (normalized.startsWith("./") || normalized.startsWith("../")) {
    return normalized;
  }
  return `./${normalized}`;
}

function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function encodeUnderscoreForWeChat(value) {
  return encodeURIComponent(String(value)).replace(/_/g, "%5F");
}

function buildWeChatSafeAuthUrl(input) {
  const url = input instanceof URL ? new URL(input.toString()) : new URL(String(input));
  const serialized = [];
  for (const [key, value] of url.searchParams.entries()) {
    serialized.push(`${encodeUnderscoreForWeChat(key)}=${encodeUnderscoreForWeChat(value)}`);
  }
  url.search = serialized.length > 0 ? `?${serialized.join("&")}` : "";
  return url.toString();
}

function normalizeModelInputLabel(input) {
  if (Array.isArray(input)) {
    const parts = input
      .map((item) => String(item || "").trim().toLowerCase())
      .filter(Boolean);
    return parts.length > 0 ? parts.join("+") : "unknown";
  }
  if (typeof input === "string") {
    const trimmed = input.trim().toLowerCase();
    return trimmed || "unknown";
  }
  return "unknown";
}

function supportsVisionInput(input) {
  const label = normalizeModelInputLabel(input);
  return label.split(/[+,\s]+/).includes("image");
}

function runOpenClawJsonCommand(args) {
  const proc = spawnSync("openclaw", args, {
    encoding: "utf8",
    timeout: 10000,
    maxBuffer: 4 * 1024 * 1024,
  });
  if (proc.error) {
    throw new RuntimeError(`openclaw command failed: ${proc.error.message}`);
  }
  if (proc.status !== 0) {
    const stderr = String(proc.stderr || "").trim();
    throw new RuntimeError(
      `openclaw ${args.join(" ")} failed: ${stderr || `exit code ${proc.status}`}`,
    );
  }
  const parsed = safeJsonParse(proc.stdout || "");
  if (!parsed || typeof parsed !== "object") {
    throw new RuntimeError(`openclaw ${args.join(" ")} returned invalid JSON`);
  }
  return parsed;
}

function extractModelRowsFromOpenClawList(payload) {
  const models = Array.isArray(payload?.models) ? payload.models : [];
  const rows = [];
  for (const item of models) {
    if (!item || typeof item !== "object") continue;
    const key = typeof item.key === "string" ? item.key.trim() : "";
    const name = typeof item.name === "string" ? item.name.trim() : "";
    if (!key && !name) continue;
    const input = normalizeModelInputLabel(item.input);
    const tags = Array.isArray(item.tags)
      ? item.tags
          .map((tag) => String(tag || "").trim())
          .filter(Boolean)
      : [];
    rows.push({
      key: key || name,
      name: name || key || null,
      input,
      supports_vision: supportsVisionInput(item.input),
      tags,
    });
  }
  return rows;
}

function extractModelRowsFromConfig(configPath) {
  const raw = readJsonFile(configPath);
  if (!raw || typeof raw !== "object") return [];
  const providers = raw.providers && typeof raw.providers === "object" ? raw.providers : {};
  const rows = [];
  for (const [providerName, providerValue] of Object.entries(providers)) {
    if (!providerValue || typeof providerValue !== "object") continue;
    const models = Array.isArray(providerValue.models) ? providerValue.models : [];
    for (const model of models) {
      if (!model || typeof model !== "object") continue;
      const id = typeof model.id === "string" ? model.id.trim() : "";
      const name = typeof model.name === "string" ? model.name.trim() : "";
      if (!id && !name) continue;
      const key = id ? `${providerName}/${id}` : `${providerName}/${name}`;
      const input = normalizeModelInputLabel(model.input);
      rows.push({
        key,
        name: name || id || null,
        input,
        supports_vision: supportsVisionInput(model.input),
        tags: [],
      });
    }
  }
  return rows;
}

function findModelRow(rows, targetModel) {
  const target = String(targetModel || "").trim();
  if (!target) return null;
  const normalized = target.toLowerCase();

  for (const row of rows) {
    if (String(row.key || "").trim().toLowerCase() === normalized) {
      return row;
    }
  }
  for (const row of rows) {
    if (String(row.name || "").trim().toLowerCase() === normalized) {
      return row;
    }
  }
  for (const row of rows) {
    const tags = Array.isArray(row.tags) ? row.tags : [];
    if (tags.some((tag) => tag.toLowerCase() === `alias:${normalized}`)) {
      return row;
    }
  }
  return null;
}

function readJsonFile(filePath) {
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (err) {
    throw new SkillError(`Invalid JSON file: ${filePath} (${err.message})`);
  }
}

function writeJsonFileSecure(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const tmp = `${filePath}.tmp`;
  fs.writeFileSync(tmp, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  fs.renameSync(tmp, filePath);
  try {
    fs.chmodSync(filePath, 0o600);
  } catch {
    // Best effort on non-POSIX environments.
  }
}

function removeFileQuiet(filePath) {
  try {
    if (fs.existsSync(filePath)) {
      fs.unlinkSync(filePath);
    }
  } catch {
    // Best effort cleanup only.
  }
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function loadPendingAuth(filePath) {
  const raw = readJsonFile(filePath);
  if (!raw) return null;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new SkillError(`Invalid pending auth file structure: ${filePath}`);
  }

  const required = [
    "site",
    "client_id",
    "nonce",
    "private_key_pem",
    "application_name",
    "scopes",
    "created_at",
    "expires_at",
  ];
  for (const field of required) {
    if (typeof raw[field] !== "string" || !raw[field]) {
      throw new SkillError(`Pending auth file missing field '${field}': ${filePath}`);
    }
  }

  return {
    site: normalizeSite(raw.site),
    client_id: raw.client_id,
    nonce: raw.nonce,
    private_key_pem: raw.private_key_pem,
    application_name: raw.application_name,
    scopes: raw.scopes,
    created_at: raw.created_at,
    expires_at: raw.expires_at,
  };
}

function parseEncryptedPayloadInput(payloadInput) {
  const raw = String(payloadInput || "").trim();
  if (!raw) {
    throw new SkillError("No payload provided.");
  }
  const normalizeDecodedValue = (v) => String(v).trim().replace(/ /g, "+");
  const compact = raw.replace(/\s+/g, "");

  const fromJson = safeJsonParse(raw);
  if (fromJson && typeof fromJson === "object" && typeof fromJson.payload === "string") {
    return normalizeDecodedValue(fromJson.payload);
  }

  const tryQueryDecode = (text) => {
    const trimmed = text.startsWith("?") || text.startsWith("#") ? text.slice(1) : text;
    const params = new URLSearchParams(trimmed);
    const p = params.get("payload") || params.get("encrypted_payload");
    return p ? normalizeDecodedValue(p) : null;
  };

  const maybeFromCompactQuery = tryQueryDecode(compact);
  if (maybeFromCompactQuery) return maybeFromCompactQuery;
  const maybeFromQuery = tryQueryDecode(raw);
  if (maybeFromQuery) return maybeFromQuery;

  try {
    const url = new URL(compact);
    const fromQuery = url.searchParams.get("payload") || url.searchParams.get("encrypted_payload");
    if (fromQuery) return normalizeDecodedValue(fromQuery);
    const fromHash = tryQueryDecode(url.hash);
    if (fromHash) return fromHash;
  } catch {
    // Not a compact URL, continue.
  }

  try {
    const url = new URL(raw);
    const fromQuery = url.searchParams.get("payload") || url.searchParams.get("encrypted_payload");
    if (fromQuery) return normalizeDecodedValue(fromQuery);
    const fromHash = tryQueryDecode(url.hash);
    if (fromHash) return fromHash;
  } catch {
    // Not a URL either, continue fallback.
  }

  return raw;
}

function normalizeBase64Payload(payload) {
  let normalized = String(payload).trim().replace(/\s+/g, "");
  normalized = normalized.replace(/-/g, "+").replace(/_/g, "/");
  const mod = normalized.length % 4;
  if (mod) {
    normalized += "=".repeat(4 - mod);
  }
  return normalized;
}

function extractCredentialForSite(raw, site) {
  const target = normalizeSite(site);

  if (
    raw &&
    typeof raw === "object" &&
    typeof raw.site === "string" &&
    typeof raw.user_api_key === "string" &&
    normalizeSite(raw.site) === target
  ) {
    return {
      key: raw.user_api_key,
      client_id:
        raw.user_api_client_id === undefined || raw.user_api_client_id === null
          ? null
          : String(raw.user_api_client_id),
    };
  }

  if (raw && typeof raw === "object" && Array.isArray(raw.auth_pairs)) {
    for (const pair of raw.auth_pairs) {
      if (!pair || typeof pair !== "object") continue;
      if (typeof pair.site !== "string" || typeof pair.user_api_key !== "string") continue;
      if (normalizeSite(pair.site) !== target) continue;
      return {
        key: pair.user_api_key,
        client_id:
          pair.user_api_client_id === undefined || pair.user_api_client_id === null
            ? null
            : String(pair.user_api_client_id),
      };
    }
  }
  return null;
}

// Removed: loadEnvCredential — only link-based auth is supported.

function loadFileCredential(site, filePath, source) {
  const raw = readJsonFile(filePath);
  if (!raw) return null;
  const found = extractCredentialForSite(raw, site);
  if (!found) return null;
  return {
    site: normalizeSite(site),
    user_api_key: found.key,
    user_api_client_id: found.client_id,
    source,
  };
}

function resolveCredential({ site, authFile }) {
  const authCred = loadFileCredential(site, authFile, "auth_file");
  if (authCred) return authCred;

  throw new CredentialError(
    "No credential found. Run 'auth init' to generate an authorization link, open it in browser to authorize, then run 'auth finish --payload <payload>' to complete login.",
  );
}

function buildHeaders(cred) {
  const headers = {
    Accept: "application/json",
    "User-Api-Key": cred.user_api_key,
  };
  if (cred.user_api_client_id) {
    headers["User-Api-Client-Id"] = cred.user_api_client_id;
  }
  return headers;
}

export function ensureReadOnly(method, requestPath) {
  if (String(method).toUpperCase() !== "GET") {
    throw new ReadOnlyViolation(`Blocked non-GET method: ${method}`);
  }
  if (!requestPath.startsWith("/")) {
    throw new ReadOnlyViolation(`Blocked path without absolute prefix: ${requestPath}`);
  }
  const allowed = ALLOWED_READ_PREFIXES.some((prefix) => requestPath.startsWith(prefix));
  if (!allowed) {
    throw new ReadOnlyViolation(`Blocked path outside read allowlist: ${requestPath}`);
  }
}

function composeUrl(site, requestPath, params) {
  const base = `${normalizeSite(site)}/`;
  const url = new URL(requestPath.replace(/^\//, ""), base);
  if (params && typeof params === "object") {
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null) continue;
      if (Array.isArray(v)) {
        for (const one of v) {
          if (one !== undefined && one !== null) {
            url.searchParams.append(k, String(one));
          }
        }
      } else {
        url.searchParams.set(k, String(v));
      }
    }
  }
  return url.toString();
}

async function requestNode(site, requestPath, params, cred, timeout) {
  ensureReadOnly("GET", requestPath);
  const sourceUrl = composeUrl(site, requestPath, params);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), Math.max(1, Math.ceil(timeout * 1000)));

  let response;
  try {
    response = await fetch(sourceUrl, {
      method: "GET",
      headers: buildHeaders(cred),
      signal: controller.signal,
    });
  } catch (err) {
    if (err && err.name === "AbortError") {
      throw new RuntimeError(`node request timeout after ${timeout}s`);
    }
    throw new RuntimeError(`node request failed: ${err?.message || String(err)}`);
  } finally {
    clearTimeout(timer);
  }

  const body = await response.text();
  if (!response.ok) {
    throw new HttpRequestError({
      status: response.status,
      body,
      url: sourceUrl,
      runtime: "node",
    });
  }

  const parsed = safeJsonParse(body);
  if (parsed === null) {
    throw new RuntimeError("node response is not valid JSON");
  }

  return {
    data: parsed,
    source_url: sourceUrl,
    runtime: "node",
    fallback_reason: null,
  };
}

async function requestCurl(site, requestPath, params, cred, timeout) {
  ensureReadOnly("GET", requestPath);
  const sourceUrl = composeUrl(site, requestPath, params);

  const args = [
    "-sS",
    "-L",
    "--max-time",
    String(Math.max(1, Math.ceil(timeout))),
    "-H",
    "Accept: application/json",
    "-H",
    `User-Api-Key: ${cred.user_api_key}`,
  ];
  if (cred.user_api_client_id) {
    args.push("-H", `User-Api-Client-Id: ${cred.user_api_client_id}`);
  }
  args.push("-w", "\n%{http_code}", sourceUrl);

  const proc = spawnSync("curl", args, { encoding: "utf8" });
  if (proc.status !== 0) {
    throw new RuntimeError(`curl request failed: ${(proc.stderr || "").trim() || "unknown curl error"}`);
  }

  const output = proc.stdout || "";
  const idx = output.lastIndexOf("\n");
  if (idx < 0) {
    throw new RuntimeError("curl output parsing failed: missing HTTP status trailer");
  }

  const body = output.slice(0, idx);
  const statusText = output.slice(idx + 1).trim();
  const status = Number.parseInt(statusText, 10);
  if (!Number.isFinite(status)) {
    throw new RuntimeError(`curl output parsing failed: invalid status '${statusText}'`);
  }

  if (status < 200 || status >= 300) {
    throw new HttpRequestError({
      status,
      body,
      url: sourceUrl,
      runtime: "curl",
    });
  }

  const parsed = safeJsonParse(body);
  if (parsed === null) {
    throw new RuntimeError("curl response is not valid JSON");
  }

  return {
    data: parsed,
    source_url: sourceUrl,
    runtime: "curl",
    fallback_reason: null,
  };
}

async function requestJson(site, requestPath, params, cred, runtime, timeout) {
  if (runtime === "node") {
    return requestNode(site, requestPath, params, cred, timeout);
  }
  if (runtime === "curl") {
    return requestCurl(site, requestPath, params, cred, timeout);
  }
  if (runtime !== "auto") {
    throw new SkillError(`Unsupported runtime mode: ${runtime}`);
  }

  try {
    return await requestNode(site, requestPath, params, cred, timeout);
  } catch (err) {
    if (err instanceof HttpRequestError || err instanceof ReadOnlyViolation) {
      throw err;
    }
    const fallback = await requestCurl(site, requestPath, params, cred, timeout);
    fallback.fallback_reason = err?.message || String(err);
    return fallback;
  }
}

function topicUrl(site, topicId, slug) {
  if (topicId === null || topicId === undefined) return null;
  const safeSlug = slug == null ? String(topicId) : String(slug);
  return `${normalizeSite(site)}/t/${safeSlug}/${topicId}`;
}

function topicPostUrl(site, topicId, slug, postNumber) {
  if (topicId == null || postNumber == null) return null;
  const safeSlug = slug == null ? String(topicId) : String(slug);
  return `${normalizeSite(site)}/t/${safeSlug}/${topicId}/${postNumber}`;
}

function normalizeContentUrl(site, rawUrl) {
  if (typeof rawUrl !== "string") return null;
  const value = rawUrl.trim();
  if (!value) return null;
  if (value.startsWith("data:")) return null;
  if (value.startsWith("upload://")) return value;
  if (/^https?:\/\//i.test(value)) return value;
  if (value.startsWith("//")) return `https:${value}`;
  if (value.startsWith("/")) return `${normalizeSite(site)}${value}`;
  if (/^[a-z][a-z0-9+.-]*:/i.test(value)) return value;
  return `${normalizeSite(site)}/${value.replace(/^\.\//, "")}`;
}

function imageLikeHref(href) {
  if (typeof href !== "string") return false;
  const lower = href.toLowerCase();
  if (lower.includes("/uploads/") || lower.includes("/secure-uploads/")) return true;
  return /\.(png|jpe?g|gif|webp|bmp|svg|avif)(?:[?#].*)?$/.test(lower);
}

function extractImageCandidatesFromCooked(cooked) {
  if (typeof cooked !== "string" || !cooked) return [];
  const found = [];

  const imgSrcRegex = /<img\b[^>]*\bsrc=["']([^"']+)["'][^>]*>/gi;
  let m = null;
  while ((m = imgSrcRegex.exec(cooked)) !== null) {
    found.push({ url: m[1], source: "cooked_img_src" });
  }

  const linkHrefRegex = /<a\b[^>]*\bhref=["']([^"']+)["'][^>]*>/gi;
  while ((m = linkHrefRegex.exec(cooked)) !== null) {
    if (imageLikeHref(m[1])) {
      found.push({ url: m[1], source: "cooked_link_href" });
    }
  }

  return found;
}

function extractImageCandidatesFromRaw(raw) {
  if (typeof raw !== "string" || !raw) return [];
  const found = [];
  let m = null;

  const markdownImageRegex = /!\[[^\]]*]\(([^)]+)\)/g;
  while ((m = markdownImageRegex.exec(raw)) !== null) {
    const inside = String(m[1] || "").trim();
    if (!inside) continue;
    const token = inside.split(/\s+/)[0];
    if (token) {
      found.push({ url: token, source: "raw_markdown_image" });
    }
  }

  const bbcodeImageRegex = /\[img(?:=[^\]]+)?]([^\[]+)\[\/img]/gi;
  while ((m = bbcodeImageRegex.exec(raw)) !== null) {
    const token = String(m[1] || "").trim();
    if (token) {
      found.push({ url: token, source: "raw_bbcode_image" });
    }
  }

  const uploadTokenRegex = /upload:\/\/[A-Za-z0-9._-]+/g;
  while ((m = uploadTokenRegex.exec(raw)) !== null) {
    const token = String(m[0] || "").trim();
    if (token) {
      found.push({ url: token, source: "raw_upload_token" });
    }
  }

  return found;
}

function parseUrlPath(url) {
  if (typeof url !== "string" || !url || url.startsWith("upload://")) return null;
  try {
    return new URL(url).pathname || null;
  } catch {
    return null;
  }
}

function looksLikeImagePath(pathname) {
  if (typeof pathname !== "string") return false;
  const lower = pathname.toLowerCase();
  if (ALLOWED_IMAGE_PREFIXES.some((prefix) => lower.startsWith(prefix))) return true;
  return IMAGE_EXT_RE.test(lower);
}

function normalizeForumImageInput(site, rawUrl) {
  const normalized = normalizeContentUrl(site, rawUrl);
  if (!normalized) {
    throw new SkillError("Invalid image URL.");
  }
  if (normalized.startsWith("upload://")) {
    throw new SkillError(
      "Unresolved upload:// token cannot be fetched directly. Use a resolved image URL from post/topic output.",
    );
  }

  const siteUrl = new URL(`${normalizeSite(site)}/`);
  let parsed;
  try {
    parsed = new URL(normalized);
  } catch {
    throw new SkillError(`Invalid normalized image URL: ${normalized}`);
  }

  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new ReadOnlyViolation(`Blocked non-http image URL: ${normalized}`);
  }
  if (parsed.hostname !== siteUrl.hostname) {
    throw new ReadOnlyViolation(`Blocked non-forum image host: ${parsed.hostname}`);
  }
  if (!looksLikeImagePath(parsed.pathname || "")) {
    throw new ReadOnlyViolation(`Blocked non-image path: ${parsed.pathname || "/"}`);
  }

  return parsed.toString();
}

function extractContentTypeHeader(value) {
  const raw = String(value || "").trim();
  if (!raw) return "application/octet-stream";
  const first = raw.split(";", 1)[0].trim().toLowerCase();
  return first || "application/octet-stream";
}

function fileExtFromContentType(contentType) {
  const t = extractContentTypeHeader(contentType);
  if (t === "image/jpeg") return ".jpg";
  if (t === "image/png") return ".png";
  if (t === "image/webp") return ".webp";
  if (t === "image/gif") return ".gif";
  if (t === "image/avif") return ".avif";
  if (t === "image/svg+xml") return ".svg";
  return ".img";
}

async function requestImageNode(site, sourceUrl, cred, timeout, outputMode, maxBytes) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), Math.max(1, Math.ceil(timeout * 1000)));

  let response;
  try {
    response = await fetch(sourceUrl, {
      method: "GET",
      headers: buildHeaders(cred),
      redirect: "follow",
      signal: controller.signal,
    });
  } catch (err) {
    if (err && err.name === "AbortError") {
      throw new RuntimeError(`node image request timeout after ${timeout}s`);
    }
    throw new RuntimeError(`node image request failed: ${err?.message || String(err)}`);
  }

  if (!response.ok) {
    const body = await response.text();
    clearTimeout(timer);
    throw new HttpRequestError({
      status: response.status,
      body,
      url: sourceUrl,
      runtime: "node",
    });
  }

  const finalUrl = response.url || sourceUrl;
  const contentType = extractContentTypeHeader(response.headers.get("content-type"));

  if (outputMode === "meta") {
    try {
      if (response.body && typeof response.body.cancel === "function") {
        await response.body.cancel();
      }
    } catch {
      // Best effort only.
    } finally {
      clearTimeout(timer);
    }
    return {
      runtime: "node",
      source_url: sourceUrl,
      final_url: finalUrl,
      content_type: contentType,
      bytes: null,
      byte_length: null,
      fallback_reason: null,
    };
  }

  let bytes;
  try {
    if (!response.body) {
      bytes = Buffer.from(await response.arrayBuffer());
    } else {
      const chunks = [];
      let total = 0;
      for await (const chunk of response.body) {
        const buf = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
        total += buf.length;
        if (total > maxBytes) {
          try {
            if (typeof response.body.cancel === "function") {
              await response.body.cancel();
            }
          } catch {
            // ignore
          }
          throw new RuntimeError(`Image exceeds --max-bytes (${maxBytes}).`);
        }
        chunks.push(buf);
      }
      bytes = Buffer.concat(chunks, total);
    }
  } catch (err) {
    if (err instanceof RuntimeError) {
      clearTimeout(timer);
      throw err;
    }
    if (err && err.name === "AbortError") {
      clearTimeout(timer);
      throw new RuntimeError(`node image download timeout after ${timeout}s`);
    }
    clearTimeout(timer);
    throw new RuntimeError(`node image download failed: ${err?.message || String(err)}`);
  } finally {
    clearTimeout(timer);
  }

  if (bytes.length > maxBytes) {
    throw new RuntimeError(`Image exceeds --max-bytes (${maxBytes}).`);
  }

  return {
    runtime: "node",
    source_url: sourceUrl,
    final_url: finalUrl,
    content_type: contentType,
    bytes,
    byte_length: bytes.length,
    fallback_reason: null,
  };
}

function requestImageCurl(site, sourceUrl, cred, timeout, outputMode, maxBytes) {
  const marker = "__SY_IMAGE_META__";

  if (outputMode === "meta") {
    const args = [
      "-sS",
      "-L",
      "--max-time",
      String(Math.max(1, Math.ceil(timeout))),
      "-I",
      "-H",
      `User-Api-Key: ${cred.user_api_key}`,
    ];
    if (cred.user_api_client_id) {
      args.push("-H", `User-Api-Client-Id: ${cred.user_api_client_id}`);
    }
    args.push("-w", `${marker}%{http_code}|%{content_type}|%{url_effective}`, sourceUrl);

    const proc = spawnSync("curl", args, { encoding: "utf8" });
    if (proc.status !== 0) {
      throw new RuntimeError(`curl image request failed: ${(proc.stderr || "").trim() || "unknown curl error"}`);
    }
    const output = proc.stdout || "";
    const idx = output.lastIndexOf(marker);
    if (idx < 0) {
      throw new RuntimeError("curl image metadata parsing failed");
    }
    const metaRaw = output.slice(idx + marker.length).trim();
    const [statusText, contentTypeRaw, finalUrl] = metaRaw.split("|", 3);
    const status = Number.parseInt(statusText, 10);
    if (!Number.isFinite(status)) {
      throw new RuntimeError(`curl image metadata parsing failed: status='${statusText || ""}'`);
    }
    if (status < 200 || status >= 300) {
      throw new HttpRequestError({
        status,
        body: output.slice(0, idx),
        url: sourceUrl,
        runtime: "curl",
      });
    }

    return {
      runtime: "curl",
      source_url: sourceUrl,
      final_url: finalUrl || sourceUrl,
      content_type: extractContentTypeHeader(contentTypeRaw),
      bytes: null,
      byte_length: null,
      fallback_reason: null,
    };
  }

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sy-image-"));
  const bodyPath = path.join(tmpDir, "body.bin");
  try {
    const args = [
      "-sS",
      "-L",
      "--max-time",
      String(Math.max(1, Math.ceil(timeout))),
      "--max-filesize",
      String(maxBytes),
      "-H",
      `User-Api-Key: ${cred.user_api_key}`,
    ];
    if (cred.user_api_client_id) {
      args.push("-H", `User-Api-Client-Id: ${cred.user_api_client_id}`);
    }
    args.push("-o", bodyPath, "-w", `${marker}%{http_code}|%{content_type}|%{url_effective}`, sourceUrl);

    const proc = spawnSync("curl", args, { encoding: "utf8" });
    if (proc.status !== 0) {
      const stderr = (proc.stderr || "").trim();
      if (/maximum file size exceeded/i.test(stderr)) {
        throw new RuntimeError(`Image exceeds --max-bytes (${maxBytes}).`);
      }
      throw new RuntimeError(`curl image request failed: ${stderr || "unknown curl error"}`);
    }

    const output = proc.stdout || "";
    const idx = output.lastIndexOf(marker);
    if (idx < 0) {
      throw new RuntimeError("curl image metadata parsing failed");
    }
    const metaRaw = output.slice(idx + marker.length).trim();
    const [statusText, contentTypeRaw, finalUrl] = metaRaw.split("|", 3);
    const status = Number.parseInt(statusText, 10);
    if (!Number.isFinite(status)) {
      throw new RuntimeError(`curl image metadata parsing failed: status='${statusText || ""}'`);
    }

    const body = fs.existsSync(bodyPath) ? fs.readFileSync(bodyPath) : Buffer.alloc(0);
    if (status < 200 || status >= 300) {
      throw new HttpRequestError({
        status,
        body: body.toString("utf8"),
        url: sourceUrl,
        runtime: "curl",
      });
    }
    if (body.length > maxBytes) {
      throw new RuntimeError(`Image exceeds --max-bytes (${maxBytes}).`);
    }

    return {
      runtime: "curl",
      source_url: sourceUrl,
      final_url: finalUrl || sourceUrl,
      content_type: extractContentTypeHeader(contentTypeRaw),
      bytes: body,
      byte_length: body.length,
      fallback_reason: null,
    };
  } finally {
    try {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    } catch {
      // Best effort cleanup only.
    }
  }
}

async function requestImage(site, sourceUrl, cred, runtime, timeout, outputMode, maxBytes) {
  if (runtime === "node") {
    return requestImageNode(site, sourceUrl, cred, timeout, outputMode, maxBytes);
  }
  if (runtime === "curl") {
    return requestImageCurl(site, sourceUrl, cred, timeout, outputMode, maxBytes);
  }
  if (runtime !== "auto") {
    throw new SkillError(`Unsupported runtime mode: ${runtime}`);
  }

  try {
    return await requestImageNode(site, sourceUrl, cred, timeout, outputMode, maxBytes);
  } catch (err) {
    if (err instanceof HttpRequestError || err instanceof ReadOnlyViolation) {
      throw err;
    }
    const fallback = requestImageCurl(site, sourceUrl, cred, timeout, outputMode, maxBytes);
    fallback.fallback_reason = err?.message || String(err);
    return fallback;
  }
}

function buildImageRefs(site, raw, cooked) {
  const merged = new Map();
  const candidates = [
    ...extractImageCandidatesFromCooked(cooked),
    ...extractImageCandidatesFromRaw(raw),
  ];

  for (const candidate of candidates) {
    const normalized = normalizeContentUrl(site, candidate.url);
    if (!normalized) continue;
    const existing = merged.get(normalized);
    if (existing) {
      if (!existing.sources.includes(candidate.source)) {
        existing.sources.push(candidate.source);
      }
      continue;
    }
    const path = parseUrlPath(normalized);
    const secureUpload =
      normalized.includes("/secure-uploads/") || (typeof path === "string" && path.includes("/secure-uploads/"));
    merged.set(normalized, {
      url: normalized,
      path,
      secure_upload: secureUpload,
      requires_auth_headers: secureUpload,
      unresolved_upload_token: normalized.startsWith("upload://"),
      sources: [candidate.source],
    });
  }

  const images = Array.from(merged.values());
  const imageUrls = images.map((item) => item.url);
  const hasSecureUploads = images.some((item) => item.secure_upload);

  return {
    image_urls: imageUrls,
    images,
    image_access: {
      secure_upload_requires_auth: hasSecureUploads,
      headers_for_secure_uploads: hasSecureUploads
        ? ["User-Api-Key", "User-Api-Client-Id (optional)"]
        : [],
      note: hasSecureUploads
        ? "Fetch secure-upload image URLs with the same User API auth headers and follow redirects."
        : null,
    },
  };
}

function mergeImageRefsFromPosts(posts) {
  const merged = new Map();
  for (const post of posts) {
    const images = Array.isArray(post?.images) ? post.images : [];
    for (const image of images) {
      if (!image || typeof image.url !== "string") continue;
      const existing = merged.get(image.url);
      if (existing) {
        existing.secure_upload = existing.secure_upload || Boolean(image.secure_upload);
        existing.requires_auth_headers = existing.requires_auth_headers || Boolean(image.requires_auth_headers);
        existing.unresolved_upload_token =
          existing.unresolved_upload_token || Boolean(image.unresolved_upload_token);
        const sources = Array.isArray(image.sources) ? image.sources : [];
        for (const src of sources) {
          if (!existing.sources.includes(src)) existing.sources.push(src);
        }
        continue;
      }
      merged.set(image.url, {
        url: image.url,
        path: image.path ?? null,
        secure_upload: Boolean(image.secure_upload),
        requires_auth_headers: Boolean(image.requires_auth_headers),
        unresolved_upload_token: Boolean(image.unresolved_upload_token),
        sources: Array.isArray(image.sources) ? [...image.sources] : [],
      });
    }
  }

  const images = Array.from(merged.values());
  const imageUrls = images.map((item) => item.url);
  const hasSecureUploads = images.some((item) => item.secure_upload);

  return {
    image_urls: imageUrls,
    images,
    image_access: {
      secure_upload_requires_auth: hasSecureUploads,
      headers_for_secure_uploads: hasSecureUploads
        ? ["User-Api-Key", "User-Api-Client-Id (optional)"]
        : [],
      note: hasSecureUploads
        ? "Fetch secure-upload image URLs with the same User API auth headers and follow redirects."
        : null,
    },
  };
}

function saveRuntimeCredential(filePath, site, key, clientId) {
  writeJsonFileSecure(filePath, {
    site: normalizeSite(site),
    user_api_key: key,
    user_api_client_id: clientId || null,
    updated_at: utcNowIso(),
  });
}

class RuntimeError extends SkillError {
  constructor(message) {
    super(message);
    this.name = "RuntimeError";
  }
}

function withCommonPayload(base, result, cred) {
  const payload = {
    ...base,
    runtime: result.runtime,
    credential_source: cred.source,
    source_url: result.source_url,
  };
  if (result.fallback_reason) {
    payload.fallback_reason = result.fallback_reason;
  }
  return payload;
}

async function handleAuthStatus(ctx) {
  const authCred = loadFileCredential(ctx.site, ctx.authFile, "auth_file");
  const resolved = authCred;

  let pending = null;
  let pendingError = null;
  try {
    pending = loadPendingAuth(ctx.authPendingFile);
  } catch (err) {
    pendingError = err?.message || String(err);
  }

  let pendingExpiresAt = null;
  let pendingExpired = null;
  if (pending && typeof pending.expires_at === "string") {
    pendingExpiresAt = pending.expires_at;
    const expiresTs = Date.parse(pending.expires_at);
    pendingExpired = Number.isFinite(expiresTs) ? expiresTs <= Date.now() : null;
  }

  return {
    ok: true,
    site: ctx.site,
    resolved: {
      found: Boolean(resolved),
      source: resolved ? resolved.source : "none",
      has_user_api_key: Boolean(resolved),
      has_user_api_client_id: Boolean(resolved && resolved.user_api_client_id),
    },
    paths: {
      auth_file: ctx.authFile,
      auth_file_exists: fs.existsSync(ctx.authFile),
      auth_pending_file: ctx.authPendingFile,
      auth_pending_file_exists: fs.existsSync(ctx.authPendingFile),
    },
    pending_auth: {
      exists: Boolean(pending),
      client_id: pending ? pending.client_id : null,
      created_at: pending ? pending.created_at : null,
      expires_at: pendingExpiresAt,
      expired: pendingExpired,
      error: pendingError,
    },
    guidance: resolved
      ? "Credential is available."
      : "No credential found. Run 'auth init' to generate an authorization link, open it in browser, then run 'auth finish --payload <payload>'.",
  };
}

function completeAuthFromPending(ctx, payloadInput) {
  const pending = loadPendingAuth(ctx.authPendingFile);
  if (!pending) {
    throw new SkillError("No pending auth session found. Run 'auth init' first to generate an authorization link.");
  }
  if (normalizeSite(pending.site) !== normalizeSite(ctx.site)) {
    throw new SkillError(
      `Pending auth site mismatch: pending=${pending.site}, current=${normalizeSite(ctx.site)}. Run 'auth init' again.`,
    );
  }

  const expiresTs = Date.parse(pending.expires_at);
  if (!Number.isFinite(expiresTs)) {
    throw new SkillError("Invalid expires_at in pending auth file.");
  }
  if (expiresTs <= Date.now()) {
    removeFileQuiet(ctx.authPendingFile);
    throw new SkillError("Pending auth session expired. Run 'auth init' again.");
  }

  const encodedPayload = normalizeBase64Payload(parseEncryptedPayloadInput(payloadInput));

  let payload;
  try {
    const decrypted = privateDecrypt(
      {
        key: pending.private_key_pem,
        padding: constants.RSA_PKCS1_PADDING,
      },
      Buffer.from(encodedPayload, "base64"),
    );
    payload = JSON.parse(decrypted.toString("utf8"));
  } catch (err) {
    throw new SkillError(`Failed to decrypt/parse payload: ${err?.message || String(err)}`);
  }

  if (!payload || typeof payload.key !== "string" || !payload.key) {
    throw new SkillError("Payload missing field: key");
  }
  if (payload.nonce !== pending.nonce) {
    throw new SkillError("Nonce mismatch in payload");
  }

  saveRuntimeCredential(ctx.authFile, ctx.site, payload.key, pending.client_id);
  removeFileQuiet(ctx.authPendingFile);

  return {
    ok: true,
    site: ctx.site,
    saved: {
      path: ctx.authFile,
      user_api_client_id: pending.client_id,
      updated_at: utcNowIso(),
    },
    auth_session: {
      pending_file: ctx.authPendingFile,
      completed: true,
      completed_at: utcNowIso(),
    },
    note: "Runtime credential saved. Pending auth session cleared.",
  };
}

async function handleAuthInit(ctx, args) {
  if (args.payload) {
    return completeAuthFromPending(ctx, args.payload);
  }

  const clientId = args.client_id || randomUUID();
  const nonce = args.nonce || randomBytes(24).toString("base64url");
  const applicationName = args.application_name || "OpenClaw Shuiyuan Skill";
  const scopes = args.scopes || "read";

  const { publicKey, privateKey } = generateKeyPairSync("rsa", {
    modulusLength: 2048,
    publicKeyEncoding: { type: "spki", format: "pem" },
    privateKeyEncoding: { type: "pkcs8", format: "pem" },
  });

  const authUrl = new URL("/user-api-key/new", ctx.site);
  authUrl.searchParams.set("application_name", applicationName);
  authUrl.searchParams.set("client_id", clientId);
  authUrl.searchParams.set("scopes", scopes);
  authUrl.searchParams.set("public_key", publicKey);
  authUrl.searchParams.set("nonce", nonce);
  const safeAuthUrl = buildWeChatSafeAuthUrl(authUrl);
  const createdAt = utcNowIso();
  const expiresAt = new Date(Date.now() + AUTH_PENDING_TTL_SECONDS * 1000).toISOString();
  writeJsonFileSecure(ctx.authPendingFile, {
    site: normalizeSite(ctx.site),
    client_id: clientId,
    nonce,
    private_key_pem: privateKey,
    application_name: applicationName,
    scopes,
    created_at: createdAt,
    expires_at: expiresAt,
  });

  return {
    ok: true,
    site: ctx.site,
    auth_url: safeAuthUrl,
    auth_session: {
      pending_file: ctx.authPendingFile,
      created_at: createdAt,
      expires_at: expiresAt,
      user_api_client_id: clientId,
    },
    transport_hints: {
      wechat:
        "auth_url is already emitted in a WeChat-safe form with %5F in query parameters. When sending it, ask the user whether they also need a QR version.",
      ask_user_if_qr_needed: true,
      qr_recommended: true,
      qr_delivery:
        "If a QR image is generated, reading the image only lets the model inspect it. To actually deliver the QR code to the user on messaging surfaces, send it as media, for example MEDIA:./file.png.",
    },
    next_step: {
      action:
        "Send auth_url, ask whether the user also needs a QR version, and if a QR is generated send it as media rather than only reading it locally. Then ask the user to open the link, approve, and provide the encrypted payload to complete login.",
      complete_with: "auth finish --payload <encrypted_payload>",
    },
  };
}

async function handleAuthFinish(ctx, args) {
  if (!args.payload) {
    throw new SkillError("Missing required argument: --payload");
  }
  return {
    ...completeAuthFromPending(ctx, args.payload),
    source: "auth_finish",
  };
}

// Removed: handleAuthImport — only link-based auth (init + finish) is supported.

function requireCredential(ctx) {
  return resolveCredential({
    site: ctx.site,
    authFile: ctx.authFile,
  });
}

async function handleSearch(ctx, args) {
  const cred = requireCredential(ctx);
  const result = await requestJson(
    ctx.site,
    "/search.json",
    {
      q: args.query,
      page: args.page > 1 ? args.page : null,
    },
    cred,
    ctx.runtime,
    ctx.timeout,
  );
  const topics = Array.isArray(result.data?.topics) ? result.data.topics : [];
  const posts = Array.isArray(result.data?.posts) ? result.data.posts : [];
  const grouped = result.data?.grouped_search_result && typeof result.data.grouped_search_result === "object"
    ? result.data.grouped_search_result
    : null;
  const topicMap = new Map();
  for (const topic of topics) {
    if (topic?.id != null) {
      topicMap.set(topic.id, topic);
    }
  }
  const rows = topics.slice(0, args.max_results).map((topic) => ({
    id: topic?.id ?? null,
    slug: topic?.slug ?? null,
    title: topic?.title ?? null,
    category_id: topic?.category_id ?? null,
    posts_count: topic?.posts_count ?? null,
    views: topic?.views ?? null,
    url: topicUrl(ctx.site, topic?.id, topic?.slug),
  }));
  const postRows = posts.slice(0, args.max_post_results).map((post) => {
    const topic = topicMap.get(post?.topic_id) || post?.topic || null;
    const slug = topic?.slug ?? null;
    return {
      id: post?.id ?? null,
      topic_id: post?.topic_id ?? null,
      post_number: post?.post_number ?? null,
      username: post?.username ?? null,
      name: post?.name ?? null,
      like_count: post?.like_count ?? null,
      score: post?.score ?? null,
      blurb: post?.blurb ?? null,
      created_at: post?.created_at ?? null,
      topic_title: topic?.title ?? null,
      topic_slug: slug,
      category_id: topic?.category_id ?? null,
      topic_url: topicUrl(ctx.site, post?.topic_id, slug),
      url: topicPostUrl(ctx.site, post?.topic_id, slug, post?.post_number),
    };
  });
  const searchOperators = [];
  if (/\btopic:\d+\b/i.test(args.query)) searchOperators.push("topic");
  if (/\border:\w+\b/i.test(args.query)) searchOperators.push("order");
  if (/\bin:title\b/i.test(args.query)) searchOperators.push("in:title");
  if (/\bin:likes\b/i.test(args.query)) searchOperators.push("in:likes");
  if (/\bin:first\b/i.test(args.query)) searchOperators.push("in:first");
  if (/\b(before|after):/i.test(args.query)) searchOperators.push("date");
  if (/\b(tags?|category|categories|status|min_posts|max_posts|min_views|max_views|with|group|user):/i.test(args.query) || /(^|\s)#\S+/.test(args.query) || /(^|\s)@\S+/.test(args.query)) {
    searchOperators.push("advanced_filters");
  }
  const strategyHint = /\btopic:\d+\b/i.test(args.query) && /\border:likes\b/i.test(args.query)
    ? "This query is well suited for finding the most-liked posts inside one topic. Inspect post_results[0] before falling back to full topic traversal."
    : null;

  return withCommonPayload(
    {
      ok: true,
      site: ctx.site,
      query: args.query,
      search_operators_detected: searchOperators,
      strategy_hint: strategyHint,
      results: rows,
      post_results: postRows,
      grouped_search_result: grouped
        ? {
            term: grouped.term ?? null,
            more_posts: grouped.more_posts ?? null,
            more_full_page_results: grouped.more_full_page_results ?? null,
            can_create_topic: grouped.can_create_topic ?? null,
            error: grouped.error ?? null,
          }
        : null,
      meta: {
        page: args.page,
        topics_total: topics.length,
        topics_returned: rows.length,
        posts_total: posts.length,
        posts_returned: postRows.length,
        has_more_topics: topics.length > args.max_results,
        has_more_posts: posts.length > args.max_post_results,
        more_full_page_results: grouped?.more_full_page_results ?? null,
      },
    },
    result,
    cred,
  );
}

async function handleLatest(ctx, args) {
  const cred = requireCredential(ctx);
  const result = await requestJson(
    ctx.site,
    "/latest.json",
    { page: args.page },
    cred,
    ctx.runtime,
    ctx.timeout,
  );

  const topicList = result.data?.topic_list && typeof result.data.topic_list === "object"
    ? result.data.topic_list
    : {};
  const topics = Array.isArray(topicList.topics) ? topicList.topics : [];
  const rows = topics.slice(0, args.max_results).map((topic) => ({
    id: topic?.id ?? null,
    slug: topic?.slug ?? null,
    title: topic?.title ?? null,
    category_id: topic?.category_id ?? null,
    posts_count: topic?.posts_count ?? null,
    views: topic?.views ?? null,
    last_posted_at: topic?.last_posted_at ?? null,
    url: topicUrl(ctx.site, topic?.id, topic?.slug),
  }));

  return withCommonPayload(
    {
      ok: true,
      site: ctx.site,
      results: rows,
      meta: {
        page: args.page,
        total: topics.length,
        returned: rows.length,
        has_more: Boolean(topicList.more_topics_url) || topics.length > args.max_results,
      },
    },
    result,
    cred,
  );
}

async function handleCategories(ctx) {
  const cred = requireCredential(ctx);
  const result = await requestJson(ctx.site, "/site.json", null, cred, ctx.runtime, ctx.timeout);
  const categories = Array.isArray(result.data?.categories) ? result.data.categories : [];

  const rows = categories.map((cat) => ({
    id: cat?.id ?? null,
    name: cat?.name ?? null,
    slug: cat?.slug ?? null,
    parent_category_id: cat?.parent_category_id ?? null,
    read_restricted: Boolean(cat?.read_restricted),
    topic_count: cat?.topic_count ?? null,
    post_count: cat?.post_count ?? null,
    url:
      cat?.id != null && cat?.slug != null
        ? `${normalizeSite(ctx.site)}/c/${cat.slug}/${cat.id}`
        : null,
  }));

  return withCommonPayload(
    {
      ok: true,
      site: ctx.site,
      categories: rows,
      meta: { total: rows.length },
    },
    result,
    cred,
  );
}

async function handleFilter(ctx, args) {
  const cred = requireCredential(ctx);
  const result = await requestJson(
    ctx.site,
    "/filter.json",
    {
      q: args.filter,
      page: args.page,
      per_page: args.per_page,
    },
    cred,
    ctx.runtime,
    ctx.timeout,
  );

  const root = result.data && typeof result.data === "object" ? result.data : {};
  const topicList = root.topic_list && typeof root.topic_list === "object" ? root.topic_list : root;
  const topics = Array.isArray(topicList.topics) ? topicList.topics : [];

  const rows = topics.slice(0, args.per_page).map((topic) => ({
    id: topic?.id ?? null,
    slug: topic?.slug ?? null,
    title: topic?.title ?? topic?.fancy_title ?? null,
    url: topicUrl(ctx.site, topic?.id, topic?.slug),
  }));

  return withCommonPayload(
    {
      ok: true,
      site: ctx.site,
      filter: args.filter,
      results: rows,
      meta: {
        page: args.page,
        limit: args.per_page,
        returned: rows.length,
        has_more:
          Boolean(topicList.more_topics_url || topicList.more_url) || topics.length > args.per_page,
      },
    },
    result,
    cred,
  );
}

async function handlePost(ctx, args) {
  const cred = requireCredential(ctx);
  const result = await requestJson(
    ctx.site,
    `/posts/${args.post_id}.json`,
    { include_raw: "true" },
    cred,
    ctx.runtime,
    ctx.timeout,
  );

  const root = result.data && typeof result.data === "object" ? result.data : {};
  const raw = String(root.raw ?? root.cooked ?? "");
  const cookedHtml = String(root.cooked ?? "");
  const truncated = raw.slice(0, args.max_read_length);
  const imageInfo = buildImageRefs(ctx.site, raw, cookedHtml);
  const postPayload = {
    id: root.id ?? args.post_id,
    topic_id: root.topic_id ?? null,
    topic_slug: root.topic_slug ?? null,
    post_number: root.post_number ?? null,
    username: root.username ?? null,
    created_at: root.created_at ?? null,
    url: topicPostUrl(ctx.site, root.topic_id, root.topic_slug, root.post_number),
    raw: truncated,
    raw_len: raw.length,
    truncated: raw.length > args.max_read_length,
    image_urls: imageInfo.image_urls,
    images: imageInfo.images,
    image_access: imageInfo.image_access,
  };
  if (args.include_html) {
    const cookedTruncated = cookedHtml.slice(0, args.max_read_length);
    postPayload.cooked_html = cookedTruncated;
    postPayload.cooked_html_len = cookedHtml.length;
    postPayload.cooked_truncated = cookedHtml.length > args.max_read_length;
  }

  return withCommonPayload(
    {
      ok: true,
      site: ctx.site,
      post: postPayload,
    },
    result,
    cred,
  );
}

async function handlePostRaw(ctx, args) {
  const cred = requireCredential(ctx);
  const result = await requestJson(
    ctx.site,
    `/posts/${args.post_id}.json`,
    { include_raw: "true" },
    cred,
    ctx.runtime,
    ctx.timeout,
  );

  const root = result.data && typeof result.data === "object" ? result.data : {};

  return withCommonPayload(
    {
      ok: true,
      site: ctx.site,
      post_raw: root,
      meta: {
        mode: "post_raw",
        post_id: root.id ?? args.post_id,
        topic_id: root.topic_id ?? null,
        post_number: root.post_number ?? null,
        includes_full_post_json: true,
        note: "Raw Discourse post JSON is large; use only when concise output lacks required fields.",
      },
    },
    result,
    cred,
  );
}

async function handleVisionCheck(ctx, args) {
  const requestedModel = String(args.model || "").trim() || null;
  let source = "openclaw_cli";
  let resolvedModel = requestedModel;
  let rows = [];
  let statusError = null;

  try {
    const listPayload = runOpenClawJsonCommand(["models", "list", "--json"]);
    rows = extractModelRowsFromOpenClawList(listPayload);
    if (!resolvedModel) {
      const statusPayload = runOpenClawJsonCommand(["models", "status", "--json"]);
      const defaultModel = String(statusPayload?.resolvedDefault || "").trim();
      if (defaultModel) {
        resolvedModel = defaultModel;
      }
    }
  } catch (err) {
    statusError = err?.message || String(err);
  }

  if (rows.length === 0) {
    source = "openclaw_config";
    const configRows = extractModelRowsFromConfig(resolvePath("~/.openclaw/openclaw.json"));
    rows = configRows;
    if (!resolvedModel && configRows.length === 1) {
      resolvedModel = configRows[0].key;
    }
  }

  const visionModels = rows.filter((row) => row.supports_vision).map((row) => row.key);

  if (rows.length === 0) {
    return {
      ok: false,
      error_type: "vision_check_unavailable",
      error:
        "Unable to inspect OpenClaw model capabilities from CLI or config.",
      detail: statusError,
    };
  }

  if (!resolvedModel) {
    return {
      ok: true,
      vision: {
        checked: false,
        source,
        requested_model: requestedModel,
        target_model: null,
        supports_vision: null,
        reason:
          "Target model is unknown. Pass --model <provider/model> or configure a default model.",
        candidate_vision_models: visionModels,
      },
    };
  }

  const row = findModelRow(rows, resolvedModel);
  if (!row) {
    return {
      ok: true,
      vision: {
        checked: false,
        source,
        requested_model: requestedModel,
        target_model: resolvedModel,
        supports_vision: null,
        reason: `Model '${resolvedModel}' not found in discovered model list.`,
        candidate_vision_models: visionModels,
      },
    };
  }

  const supports = Boolean(row.supports_vision);
  const reason = supports
    ? "Model input supports image blocks."
    : `Model input is '${row.input}', which does not include image capability.`;

  return {
    ok: true,
    vision: {
      checked: true,
      source,
      requested_model: requestedModel,
      target_model: row.key,
      resolved_name: row.name,
      input: row.input,
      supports_vision: supports,
      reason,
      user_facing_reason_when_unsupported: supports
        ? null
        : `当前模型 ${row.key} 仅支持文本输入（input=${row.input}），无法读取图片像素内容。请切换到支持 image 输入的模型后再试。`,
      candidate_vision_models: visionModels,
      recommendation: supports
        ? "Current model already supports vision."
        : visionModels.length > 0
        ? `Switch to a vision-capable model, e.g. ${visionModels[0]}.`
        : "No vision-capable model found in current OpenClaw model list.",
    },
  };
}

async function handleTopic(ctx, args) {
  const cred = requireCredential(ctx);
  const start = Math.max(1, args.start_post_number);
  const collected = [];
  const includeHtml = Boolean(args.include_html);
  const runtimes = [];
  let topicMeta = null;
  let sourceUrl = null;
  let fallbackReason = null;
  let current = start;

  for (let i = 0; i < args.max_batches && collected.length < args.post_limit; i += 1) {
    const params = { include_raw: "true" };
    if (current > 1) params.post_number = current;

    const result = await requestJson(
      ctx.site,
      `/t/${args.topic_id}.json`,
      params,
      cred,
      ctx.runtime,
      ctx.timeout,
    );

    runtimes.push(result.runtime);
    if (result.fallback_reason && !fallbackReason) {
      fallbackReason = result.fallback_reason;
    }

    const root = result.data && typeof result.data === "object" ? result.data : {};
    if (!topicMeta) {
      topicMeta = root;
      sourceUrl = result.source_url;
    }

    const postStream = root.post_stream && typeof root.post_stream === "object" ? root.post_stream : {};
    const posts = Array.isArray(postStream.posts) ? postStream.posts : [];

    const sorted = posts
      .filter((p) => p && typeof p === "object")
      .slice()
      .sort((a, b) => Number(a.post_number || 0) - Number(b.post_number || 0));

    const filtered = sorted.filter((p) => Number(p.post_number || 0) >= current);
    if (filtered.length === 0) break;

    for (const post of filtered) {
      if (collected.length >= args.post_limit) break;
      const raw = String(post.raw ?? post.cooked ?? post.excerpt ?? "");
      const cookedHtml = String(post.cooked ?? "");
      const trimmed = raw.slice(0, args.max_read_length);
      const imageInfo = buildImageRefs(ctx.site, raw, cookedHtml);
      const pnum = post.post_number ?? null;
      const postPayload = {
        id: post.id ?? null,
        post_number: pnum,
        username: post.username ?? null,
        created_at: post.created_at ?? null,
        url: topicPostUrl(ctx.site, args.topic_id, root.slug, pnum),
        raw: trimmed,
        raw_len: raw.length,
        truncated: raw.length > args.max_read_length,
        image_urls: imageInfo.image_urls,
        images: imageInfo.images,
        image_access: imageInfo.image_access,
      };
      if (includeHtml) {
        const cookedTrimmed = cookedHtml.slice(0, args.max_read_length);
        postPayload.cooked_html = cookedTrimmed;
        postPayload.cooked_html_len = cookedHtml.length;
        postPayload.cooked_truncated = cookedHtml.length > args.max_read_length;
      }
      collected.push(postPayload);
    }

    const last = filtered[filtered.length - 1];
    current = Number(last.post_number || current) + 1;
  }

  if (!topicMeta) {
    throw new SkillError(`Failed to load topic ${args.topic_id}`);
  }

  const postsCount = Number(topicMeta.posts_count || collected.length);
  const hasMore = postsCount > start + collected.length - 1;
  const topicImages = mergeImageRefsFromPosts(collected);

  const payload = {
    ok: true,
    site: ctx.site,
    runtime: runtimes.length > 0 ? runtimes[runtimes.length - 1] : ctx.runtime,
    runtime_sequence: runtimes,
    credential_source: cred.source,
    source_url: sourceUrl,
    topic: {
      id: topicMeta.id ?? args.topic_id,
      title: topicMeta.title ?? null,
      slug: topicMeta.slug ?? null,
      category_id: topicMeta.category_id ?? null,
      tags: Array.isArray(topicMeta.tags) ? topicMeta.tags : [],
      posts_count: postsCount,
      url: topicUrl(ctx.site, args.topic_id, topicMeta.slug),
      posts: collected,
      image_urls: topicImages.image_urls,
      images: topicImages.images,
      image_access: topicImages.image_access,
    },
    meta: {
      start_post_number: start,
      returned_posts: collected.length,
      has_more: hasMore,
    },
  };

  if (fallbackReason) payload.fallback_reason = fallbackReason;
  return payload;
}

async function handleImage(ctx, args) {
  const cred = requireCredential(ctx);
  const sourceUrl = normalizeForumImageInput(ctx.site, args.image_url);
  const result = await requestImage(
    ctx.site,
    sourceUrl,
    cred,
    ctx.runtime,
    ctx.timeout,
    args.output,
    args.max_bytes,
  );

  const sourcePath = parseUrlPath(sourceUrl) || "";
  const secureUpload = sourcePath.includes("/secure-uploads/");
  const base = {
    ok: true,
    site: ctx.site,
    image: {
      input_url: args.image_url,
      source_url: sourceUrl,
      final_url: result.final_url,
      output: args.output,
      content_type: result.content_type,
      secure_upload: secureUpload,
      requires_auth_headers: secureUpload,
      max_bytes: args.max_bytes,
      cache_dir: args.output === "media-path" ? ctx.imageCacheDir : null,
      vision_input: {
        type: "image_url",
        image_url: {
          url: args.output === "data-url" ? null : result.final_url,
        },
      },
      note:
        args.output === "data-url"
          ? "Inline data URL returned for direct multimodal model input."
          : args.output === "media-path"
          ? "Image cached to local file path for native OpenClaw image injection or user media delivery."
          : "Resolved URL returned; secure-upload signed URLs may expire.",
    },
  };

  if (args.output === "data-url") {
    if (!result.bytes) {
      throw new RuntimeError("No image bytes returned in data-url mode.");
    }
    const dataUrl = `data:${result.content_type};base64,${result.bytes.toString("base64")}`;
    base.image.byte_length = result.byte_length;
    base.image.sha256 = createHash("sha256").update(result.bytes).digest("hex");
    base.image.data_url = dataUrl;
    base.image.vision_input.image_url.url = dataUrl;
  } else if (args.output === "media-path") {
    if (!result.bytes) {
      throw new RuntimeError("No image bytes returned in media-path mode.");
    }
    ensureDir(ctx.imageCacheDir);
    const digest = createHash("sha256").update(result.bytes).digest("hex");
    const ext = fileExtFromContentType(result.content_type);
    const filePath = path.join(ctx.imageCacheDir, `${digest}${ext}`);
    fs.writeFileSync(filePath, result.bytes);
    const preferredReadPath = toPreferredReadPath(filePath);
    const preferredTokenPath = preferredReadPath || filePath;
    base.image.byte_length = result.byte_length;
    base.image.sha256 = digest;
    base.image.media_path = filePath;
    base.image.media_path_preferred = preferredTokenPath;
    base.image.media_path_relative = preferredReadPath;
    base.image.read_path_preferred = preferredTokenPath;
    base.image.media_token = `MEDIA:${preferredTokenPath}`;
    base.image.media_token_absolute = `MEDIA:${filePath}`;
    base.image.media_attached_hint =
      preferredReadPath
        ? `[media attached: ${preferredTokenPath} (${result.content_type}) | ${filePath}]`
        : `[media attached: ${filePath} (${result.content_type})]`;
    base.image.read_hint =
      "To let the model see pixels, call OpenClaw read tool on image.read_path_preferred before describing image content.";
    base.image.user_delivery = {
      method: "media",
      path_preferred: preferredTokenPath,
      path_absolute: filePath,
      media_token: `MEDIA:${preferredTokenPath}`,
      media_token_absolute: `MEDIA:${filePath}`,
      hint:
        "To forward this image to the user, send image.user_delivery.media_token through the platform-native media-send path. Do not treat OpenClaw read as user delivery.",
    };
    base.image.vision_input.image_url.url = null;
  }

  return withCommonPayload(base, result, cred);
}

function readOptValue(tokens, i, token, optName) {
  if (token.includes("=")) {
    return { value: token.split("=", 2)[1], nextIndex: i };
  }
  if (i + 1 >= tokens.length) {
    throw new SkillError(`Missing value for ${optName}`);
  }
  return { value: tokens[i + 1], nextIndex: i + 1 };
}

function parseGlobalAndCommand(argv) {
  const global = {
    site: DEFAULT_SITE,
    runtime: "auto",
    timeout: DEFAULT_TIMEOUT,
    authFile: DEFAULT_AUTH_PATH,
    authPendingFile: DEFAULT_AUTH_PENDING_PATH,
    imageCacheDir: DEFAULT_IMAGE_CACHE_DIR,
  };

  let command = null;
  const commandTokens = [];
  let globalHelp = false;

  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];

    if (token === "-h" || token === "--help") {
      if (!command) {
        globalHelp = true;
      } else {
        commandTokens.push(token);
      }
      continue;
    }

    if (
      token.startsWith("--site") ||
      token.startsWith("--runtime") ||
      token.startsWith("--timeout") ||
      token.startsWith("--auth-file") ||
      token.startsWith("--auth-pending-file") ||
      token.startsWith("--image-cache-dir")
    ) {
      if (token.startsWith("--site")) {
        const { value, nextIndex } = readOptValue(argv, i, token, "--site");
        global.site = value;
        i = nextIndex;
      } else if (token.startsWith("--runtime")) {
        const { value, nextIndex } = readOptValue(argv, i, token, "--runtime");
        global.runtime = value;
        i = nextIndex;
      } else if (token.startsWith("--timeout")) {
        const { value, nextIndex } = readOptValue(argv, i, token, "--timeout");
        const parsed = Number(value);
        if (!Number.isFinite(parsed) || parsed <= 0) {
          throw new SkillError(`Invalid --timeout: ${value}`);
        }
        global.timeout = parsed;
        i = nextIndex;
      } else if (token.startsWith("--auth-file")) {
        const { value, nextIndex } = readOptValue(argv, i, token, "--auth-file");
        global.authFile = value;
        i = nextIndex;
      } else if (token.startsWith("--auth-pending-file")) {
        const { value, nextIndex } = readOptValue(argv, i, token, "--auth-pending-file");
        global.authPendingFile = value;
        i = nextIndex;
      } else if (token.startsWith("--image-cache-dir")) {
        const { value, nextIndex } = readOptValue(argv, i, token, "--image-cache-dir");
        global.imageCacheDir = value;
        i = nextIndex;
      }
      continue;
    }

    if (!command && COMMANDS.has(token)) {
      command = token;
      continue;
    }

    if (!command) {
      throw new SkillError(`Unknown command or option: ${token}`);
    }

    commandTokens.push(token);
  }

  if (!command) {
    return { globalHelp: true, global, command: null, commandTokens: [] };
  }

  return { globalHelp, global, command, commandTokens };
}

function parseSubcommandOptions(tokens) {
  const options = {};
  const positionals = [];
  const noValueFlags = new Set(["--include-html"]);
  for (let i = 0; i < tokens.length; i += 1) {
    const token = tokens[i];
    if (token === "-h" || token === "--help") {
      options.help = true;
      continue;
    }
    if (!token.startsWith("--")) {
      positionals.push(token);
      continue;
    }

    if (token.includes("=")) {
      const [key, value] = token.split("=", 2);
      options[key] = value;
      continue;
    }

    if (noValueFlags.has(token)) {
      options[token] = true;
      continue;
    }

    if (i + 1 >= tokens.length) {
      throw new SkillError(`Missing value for ${token}`);
    }
    options[token] = tokens[i + 1];
    i += 1;
  }
  return { options, positionals };
}

function asInt(value, label) {
  const n = Number.parseInt(String(value), 10);
  if (!Number.isFinite(n)) {
    throw new SkillError(`Invalid integer for ${label}: ${value}`);
  }
  return n;
}

function asBool(value, label) {
  if (typeof value === "boolean") return value;
  const s = String(value).trim().toLowerCase();
  if (["1", "true", "yes", "y", "on"].includes(s)) return true;
  if (["0", "false", "no", "n", "off"].includes(s)) return false;
  throw new SkillError(`Invalid boolean for ${label}: ${value}`);
}

function parseCommand(command, commandTokens) {
  if (command === "auth") {
    if (commandTokens.length === 0 || commandTokens[0] === "--help" || commandTokens[0] === "-h") {
      return { kind: "help", command: "auth" };
    }
    const sub = commandTokens[0];
    const { options, positionals } = parseSubcommandOptions(commandTokens.slice(1));

    if (sub === "status") {
      return { kind: "auth_status" };
    }

    if (sub === "init") {
      return {
        kind: "auth_init",
        args: {
          application_name: options["--application-name"] || "OpenClaw Shuiyuan Skill",
          client_id: options["--client-id"] || null,
          scopes: options["--scopes"] || "read",
          nonce: options["--nonce"] || null,
          payload: options["--payload"] || null,
        },
      };
    }

    if (sub === "import") {
      throw new SkillError("'auth import' is no longer supported. Use 'auth init' to generate a link, then 'auth finish --payload <payload>'.");
    }

    if (sub === "finish" || sub === "complete") {
      const payload = options["--payload"] || (positionals.length > 0 ? positionals[0] : null);
      return {
        kind: "auth_finish",
        args: {
          payload,
        },
      };
    }

    throw new SkillError(`Unknown auth subcommand: ${sub}`);
  }

  if (command === "search") {
    const { options, positionals } = parseSubcommandOptions(commandTokens);
    if (options.help) return { kind: "help", command: "search" };
    const query = positionals.join(" ").trim();
    if (!query) throw new SkillError("Missing required argument: query");
    return {
      kind: "search",
      args: {
        query,
        page: options["--page"] ? Math.max(1, asInt(options["--page"], "--page")) : 1,
        max_results: options["--max-results"] ? asInt(options["--max-results"], "--max-results") : 10,
        max_post_results: options["--max-post-results"]
          ? Math.max(0, asInt(options["--max-post-results"], "--max-post-results"))
          : 10,
      },
    };
  }

  if (command === "latest") {
    const { options } = parseSubcommandOptions(commandTokens);
    if (options.help) return { kind: "help", command: "latest" };
    return {
      kind: "latest",
      args: {
        page: options["--page"] ? asInt(options["--page"], "--page") : 0,
        max_results: options["--max-results"] ? asInt(options["--max-results"], "--max-results") : 30,
      },
    };
  }

  if (command === "categories") {
    const { options } = parseSubcommandOptions(commandTokens);
    if (options.help) return { kind: "help", command: "categories" };
    return { kind: "categories" };
  }

  if (command === "filter") {
    const { options, positionals } = parseSubcommandOptions(commandTokens);
    if (options.help) return { kind: "help", command: "filter" };
    const filter = positionals.join(" ").trim();
    if (!filter) throw new SkillError("Missing required argument: filter");
    return {
      kind: "filter",
      args: {
        filter,
        page: options["--page"] ? asInt(options["--page"], "--page") : 0,
        per_page: options["--per-page"] ? asInt(options["--per-page"], "--per-page") : 20,
      },
    };
  }

  if (command === "post") {
    const { options, positionals } = parseSubcommandOptions(commandTokens);
    if (options.help) return { kind: "help", command: "post" };
    if (positionals.length === 0) throw new SkillError("Missing required argument: post_id");
    const includeHtml = options["--include-html"] === undefined
      ? false
      : asBool(options["--include-html"], "--include-html");
    return {
      kind: "post",
      args: {
        post_id: asInt(positionals[0], "post_id"),
        max_read_length: options["--max-read-length"]
          ? asInt(options["--max-read-length"], "--max-read-length")
          : DEFAULT_MAX_READ_LENGTH,
        include_html: includeHtml,
      },
    };
  }

  if (command === "post-raw") {
    const { options, positionals } = parseSubcommandOptions(commandTokens);
    if (options.help) return { kind: "help", command: "post-raw" };
    if (positionals.length === 0) throw new SkillError("Missing required argument: post_id");
    return {
      kind: "post_raw",
      args: {
        post_id: asInt(positionals[0], "post_id"),
      },
    };
  }

  if (command === "vision-check") {
    const { options } = parseSubcommandOptions(commandTokens);
    if (options.help) return { kind: "help", command: "vision-check" };
    const model = options["--model"] ? String(options["--model"]).trim() : null;
    return {
      kind: "vision_check",
      args: {
        model: model || null,
      },
    };
  }

  if (command === "topic") {
    const { options, positionals } = parseSubcommandOptions(commandTokens);
    if (options.help) return { kind: "help", command: "topic" };
    if (positionals.length === 0) throw new SkillError("Missing required argument: topic_id");
    const includeHtml = options["--include-html"] === undefined
      ? false
      : asBool(options["--include-html"], "--include-html");
    return {
      kind: "topic",
      args: {
        topic_id: asInt(positionals[0], "topic_id"),
        post_limit: options["--post-limit"] ? asInt(options["--post-limit"], "--post-limit") : 5,
        start_post_number: options["--start-post-number"]
          ? asInt(options["--start-post-number"], "--start-post-number")
          : 1,
        max_batches: options["--max-batches"] ? asInt(options["--max-batches"], "--max-batches") : 10,
        max_read_length: options["--max-read-length"]
          ? asInt(options["--max-read-length"], "--max-read-length")
          : DEFAULT_MAX_READ_LENGTH,
        include_html: includeHtml,
      },
    };
  }

  if (command === "image") {
    const { options, positionals } = parseSubcommandOptions(commandTokens);
    if (options.help) return { kind: "help", command: "image" };
    if (positionals.length === 0) throw new SkillError("Missing required argument: image_url");
    const output = String(options["--output"] || "meta").trim().toLowerCase();
    if (!["meta", "data-url", "media-path"].includes(output)) {
      throw new SkillError(`Invalid --output: ${output} (expected meta|data-url|media-path)`);
    }
    const maxBytes = options["--max-bytes"]
      ? asInt(options["--max-bytes"], "--max-bytes")
      : DEFAULT_MAX_IMAGE_BYTES;
    if (maxBytes <= 0) {
      throw new SkillError(`Invalid --max-bytes: ${maxBytes}`);
    }
    return {
      kind: "image",
      args: {
        image_url: positionals[0],
        output,
        max_bytes: maxBytes,
      },
    };
  }

  throw new SkillError(`Unsupported command: ${command}`);
}

function getGlobalHelp() {
  return `Usage: shuiyuan_discourse.mjs [global-options] <command> [command-options]\n\nCommands:\n  auth          Credential operations (status|init|finish)\n  search        Search topics and posts\n  latest        List latest topics\n  topic         Read one topic and posts\n  post          Read one post (concise)\n  post-raw      Read one post (full raw JSON)\n  vision-check  Check whether model supports image input\n  categories    List categories\n  filter        Filter topics\n  image         Resolve/fetch one forum image for multimodal input\n\nGlobal options:\n  --site <url>                Discourse site URL (default: ${DEFAULT_SITE})\n  --runtime <auto|node|curl>  HTTP runtime (default: auto)\n  --timeout <seconds>         Request timeout (default: ${DEFAULT_TIMEOUT})\n  --auth-file <path>          Runtime credential file\n  --auth-pending-file <path>  Pending auth-session file\n  --image-cache-dir <path>    Local image cache directory`;
}

function getCommandHelp(command) {
  const helps = {
    auth: `Usage: shuiyuan_discourse.mjs auth <status|init|finish> [options]\n\nOnly link-based authorization is supported.\n\ninit options:\n  --application-name <name>\n  --client-id <id>\n  --scopes <csv>\n  --nonce <nonce>\n\nfinish options:\n  --payload <encrypted_payload> (required)\n\nWorkflow:\n  1. Run 'auth init' to get an authorization link\n  2. Open the link in browser and approve\n  3. Copy the encrypted payload from the page\n  4. Run 'auth finish --payload <payload>' to complete`,
    search:
      "Usage: shuiyuan_discourse.mjs search <query> [--page <n>] [--max-results <n>] [--max-post-results <n>]",
    latest: "Usage: shuiyuan_discourse.mjs latest [--page <n>] [--max-results <n>]",
    topic:
      "Usage: shuiyuan_discourse.mjs topic <topic_id> [--post-limit <n>] [--start-post-number <n>] [--max-batches <n>] [--max-read-length <n>] [--include-html]",
    post: "Usage: shuiyuan_discourse.mjs post <post_id> [--max-read-length <n>] [--include-html]",
    "post-raw": "Usage: shuiyuan_discourse.mjs post-raw <post_id>",
    "vision-check": "Usage: shuiyuan_discourse.mjs vision-check [--model <provider/model_or_alias>]",
    categories: "Usage: shuiyuan_discourse.mjs categories",
    filter: "Usage: shuiyuan_discourse.mjs filter <query> [--page <n>] [--per-page <n>]",
    image:
      "Usage: shuiyuan_discourse.mjs image <image_url_or_path> [--output <meta|data-url|media-path>] [--max-bytes <n>]",
  };
  return helps[command] || getGlobalHelp();
}

async function execute(ctx, parsedCommand) {
  switch (parsedCommand.kind) {
    case "auth_status":
      return handleAuthStatus(ctx);
    case "auth_init":
      return handleAuthInit(ctx, parsedCommand.args);
    case "auth_import":
      throw new SkillError("'auth import' is no longer supported. Use 'auth init' + 'auth finish'.");
    case "auth_finish":
      return handleAuthFinish(ctx, parsedCommand.args);
    case "search":
      return handleSearch(ctx, parsedCommand.args);
    case "latest":
      return handleLatest(ctx, parsedCommand.args);
    case "categories":
      return handleCategories(ctx);
    case "filter":
      return handleFilter(ctx, parsedCommand.args);
    case "post":
      return handlePost(ctx, parsedCommand.args);
    case "post_raw":
      return handlePostRaw(ctx, parsedCommand.args);
    case "vision_check":
      return handleVisionCheck(ctx, parsedCommand.args);
    case "topic":
      return handleTopic(ctx, parsedCommand.args);
    case "image":
      return handleImage(ctx, parsedCommand.args);
    default:
      throw new SkillError(`Unknown parsed command kind: ${parsedCommand.kind}`);
  }
}

async function main() {
  const parsed = parseGlobalAndCommand(process.argv.slice(2));

  if (parsed.globalHelp) {
    process.stdout.write(`${getGlobalHelp()}\n`);
    return 0;
  }

  const ctx = {
    site: normalizeSite(parsed.global.site),
    runtime: parsed.global.runtime,
    timeout: parsed.global.timeout,
    authFile: resolvePath(parsed.global.authFile),
    authPendingFile: resolvePath(parsed.global.authPendingFile),
    imageCacheDir: resolvePath(parsed.global.imageCacheDir),
  };

  if (!["auto", "node", "curl"].includes(ctx.runtime)) {
    throw new SkillError(`Invalid --runtime: ${ctx.runtime}`);
  }

  const parsedCommand = parseCommand(parsed.command, parsed.commandTokens);
  if (parsedCommand.kind === "help") {
    process.stdout.write(`${getCommandHelp(parsedCommand.command)}\n`);
    return 0;
  }

  const payload = await execute(ctx, parsedCommand);
  printJson(payload);
  return 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main()
    .then((code) => {
      if (typeof code === "number") {
        process.exit(code);
      }
      process.exit(0);
    })
    .catch((err) => {
      if (err instanceof ReadOnlyViolation) {
        printJson({ ok: false, error_type: "read_only_violation", error: err.message });
        process.exit(2);
      }
      if (err instanceof HttpRequestError) {
        const payload = err.toPayload();
        if (err.status === 429 || payload.discourse_error_type === "rate_limit") {
          printJson(normalizeRateLimitPayload(err));
          process.exit(0);
        }
        printJson(err.toPayload());
        process.exit(3);
      }
      if (err instanceof CredentialError) {
        printJson({ ok: false, error_type: "credential_error", error: err.message });
        process.exit(4);
      }
      if (err instanceof SkillError || err instanceof Error) {
        printJson({ ok: false, error_type: "skill_error", error: err.message || String(err) });
        process.exit(5);
      }
      printJson({ ok: false, error_type: "unexpected_error", error: String(err) });
      process.exit(9);
    });
}
