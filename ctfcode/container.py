"""容器题（动态靶机）管理：启动 / 续期 / 销毁，并解析实例入口。"""
from __future__ import annotations

from .gzctf import GZCTFClient, GZCTFError


class ContainerManager:
    def __init__(self, client: GZCTFClient):
        self.client = client
        self.cache: dict[tuple[int, int], dict] = {}

    def info_from_detail(self, detail: dict) -> dict:
        ctx = detail.get("context") or {}
        return {"entry": ctx.get("instanceEntry"), "closeTime": ctx.get("closeTime")}

    def ensure(self, gid: int, cid: int, detail: dict | None = None) -> dict:
        """确保容器在运行：优先用详情里已有的入口，否则启动一个新的。"""
        if detail:
            existing = self.info_from_detail(detail)
            if existing.get("entry"):
                self.cache[(gid, cid)] = existing
                return existing
        try:
            resp = self.client.create_container(gid, cid)
            info = GZCTFClient.parse_instance(resp)
            info.setdefault("ok", not isinstance(resp, dict) or "error" not in resp)
            self.cache[(gid, cid)] = info
            return info
        except GZCTFError as e:
            info = {"entry": None, "error": str(e)}
            self.cache[(gid, cid)] = info
            return info

    def extend(self, gid: int, cid: int) -> dict:
        return GZCTFClient.parse_instance(self.client.extend_container(gid, cid))

    def destroy(self, gid: int, cid: int) -> None:
        try:
            self.client.destroy_container(gid, cid)
        finally:
            self.cache.pop((gid, cid), None)
