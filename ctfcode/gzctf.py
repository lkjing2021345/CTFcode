"""GZCTF REST API 客户端。

覆盖：识别实例 -> 登录/Token -> 列比赛 -> 列题目 -> 题目详情 -> 下载附件
      -> 提交 flag -> 查询提交结果。
"""
from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass

import requests

try:
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5, PKCS1_OAEP
    from Crypto.Hash import SHA256

    _HAS_CRYPTO = True
except Exception:  # pycryptodome 未安装
    _HAS_CRYPTO = False


class GZCTFError(Exception):
    pass


@dataclass
class Challenge:
    id: int
    title: str
    category: str = "Misc"
    score: int = 0
    solved_count: int = 0

    @classmethod
    def from_json(cls, d: dict) -> "Challenge":
        return cls(
            id=d.get("id"),
            title=d.get("title", "untitled"),
            category=d.get("category", "Misc") or "Misc",
            score=d.get("score", 0) or 0,
            solved_count=d.get("solvedCount", 0) or 0,
        )


class GZCTFClient:
    def __init__(self, base_url: str, api_token: str | None = None, timeout: int = 20):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "gzctf-agent/0.1 (+ctf)"
        self.api_token = api_token
        if api_token:
            self.s.headers["Authorization"] = f"Bearer {api_token}"
        self.public_key: str | None = None
        self.config: dict = {}

    # ---------------- 底层 ----------------
    def _url(self, path: str) -> str:
        return f"{self.base}{path}"

    def _json(self, method: str, path: str, **kw) -> object:
        kw.setdefault("timeout", self.timeout)
        r = self.s.request(method, self._url(path), **kw)
        if r.status_code == 429:
            raise GZCTFError("触发频率限制(429)，请放慢速度")
        try:
            data = r.json()
        except Exception:
            raise GZCTFError(f"{method} {path} -> {r.status_code} {r.text[:200]}")
        if r.status_code >= 400:
            msg = data.get("title") if isinstance(data, dict) else r.text
            raise GZCTFError(f"{method} {path} -> {r.status_code}: {msg}")
        return data

    # ---------------- 识别 ----------------
    @staticmethod
    def looks_like_gzctf(url: str) -> bool:
        """探测 <url>/api/config 是否具备 GZCTF 特征。"""
        try:
            r = requests.get(url.rstrip("/") + "/api/config", timeout=10)
            if r.status_code != 200:
                return False
            d = r.json()
            if not isinstance(d, dict):
                return False
            keys = set(d.keys())
            return bool(keys & {"globalConfig", "captchaConfig", "apiPublicKey", "title", "logo"})
        except Exception:
            return False

    # ---------------- 认证 ----------------
    def fetch_config(self) -> dict:
        self.config = self._json("GET", "/api/config")  # type: ignore[assignment]
        self.public_key = (
            self.config.get("apiPublicKey")
            or self.config.get("publicKey")
            or (self.config.get("globalConfig") or {}).get("publicKey")
        )
        return self.config

    def _encrypt(self, text: str, padding: str = "oaep") -> str:
        if not self.public_key:
            return text
        if not _HAS_CRYPTO:
            raise GZCTFError("需要 pycryptodome 才能做 RSA 加密：pip install pycryptodome")
        key = RSA.import_key(self.public_key)
        cipher = PKCS1_v1_5.new(key) if padding == "pkcs1" else PKCS1_OAEP.new(key, hashAlgo=SHA256)
        return base64.b64encode(cipher.encrypt(text.encode())).decode()

    def login(self, username: str, password: str, encrypt: bool = False, padding: str = "oaep") -> dict:
        pw = self._encrypt(password, padding) if encrypt else password
        return self._json("POST", "/api/account/login",
                          json={"userName": username, "password": pw})  # type: ignore[return-value]

    # ---------------- 比赛 / 题目 ----------------
    def recent_games(self, count: int = 20) -> list:
        return self._json("GET", f"/api/game/recent?count={count}")  # type: ignore[return-value]

    def games(self, count: int = 50, skip: int = 0) -> dict:
        return self._json("GET", f"/api/game?count={count}&skip={skip}")  # type: ignore[return-value]

    def game_details(self, gid: int) -> dict:
        return self._json("GET", f"/api/game/{gid}/details")  # type: ignore[return-value]

    def challenges(self, gid: int) -> list[Challenge]:
        d = self.game_details(gid)
        return [Challenge.from_json(c) for c in d.get("challenges", [])]

    def challenge_detail(self, gid: int, cid: int) -> dict:
        return self._json("GET", f"/api/game/{gid}/challenges/{cid}")  # type: ignore[return-value]

    # ---------------- 下载 ----------------
    def download(self, url: str, dest: str) -> str:
        if url.startswith("/"):
            url = self.base + url
        r = self.s.get(url, timeout=120, stream=True)
        r.raise_for_status()
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
        return dest

    # ---------------- 提交 ----------------
    def submit(self, gid: int, cid: int, flag: str, encrypt: bool = False, padding: str = "oaep") -> int:
        payload = self._encrypt(flag, padding) if encrypt else flag
        return self._json("POST", f"/api/game/{gid}/challenges/{cid}", json={"flag": payload})  # type: ignore[return-value]

    def status(self, gid: int, cid: int, sid: int) -> str:
        return self._json("GET", f"/api/game/{gid}/challenges/{cid}/status/{sid}")  # type: ignore[return-value]

    def wait_status(self, gid: int, cid: int, sid: int, tries: int = 10, interval: float = 1.0) -> str:
        last = "Unknown"
        for _ in range(tries):
            try:
                last = self.status(gid, cid, sid)
            except GZCTFError:
                pass
            if last in ("Accepted", "WrongAnswer", "CheatDetected"):
                return last
            time.sleep(interval)
        return last

    # ---------------- 容器题（动态靶机） ----------------
    def create_container(self, gid: int, cid: int) -> dict:
        """启动容器实例，返回实例信息（含 instanceEntry / closeTime）。"""
        return self._json("POST", f"/api/game/{gid}/container/{cid}")  # type: ignore[return-value]

    def destroy_container(self, gid: int, cid: int):
        return self._json("DELETE", f"/api/game/{gid}/container/{cid}")

    def extend_container(self, gid: int, cid: int) -> dict:
        return self._json("POST", f"/api/game/{gid}/container/{cid}/extend")  # type: ignore[return-value]

    @staticmethod
    def parse_instance(resp) -> dict:
        """把启动容器的返回统一成 {entry, closeTime} 结构（兼容不同字段名）。"""
        if not isinstance(resp, dict):
            return {"entry": None, "closeTime": None, "raw": resp}
        entry = (
            resp.get("instanceEntry")
            or resp.get("entry")
            or resp.get("entryPoint")
            or resp.get("url")
            or (resp.get("context") or {}).get("instanceEntry")
        )
        close = resp.get("closeTime") or resp.get("closeTimeUtc") or (resp.get("context") or {}).get("closeTime")
        return {"entry": entry, "closeTime": close, "raw": resp}

    def list_local_files(self, detail: dict) -> list[str]:
        """从题目详情里取出可下载的本地附件 URL。"""
        out = []
        for att in detail.get("attachments") or []:
            url = att.get("url")
            if url and (att.get("type") in (None, "Local") or str(url).startswith("/")):
                out.append(url)
        return out
