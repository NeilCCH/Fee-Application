# -*- coding: utf-8 -*-
"""
Supabase 草稿存取層：出差明細（一趟＝一列）與一般費用項次，各自先存起來，
送件時才挑選要用哪幾筆組成一張請款單。成功產出後即刪除已使用的草稿列
（資料本來就設計成短命，不需要久放）。
"""
import os
from typing import Any

TRIP_LEGS_TABLE = "feeapp_trip_legs"
EXPENSE_ITEMS_TABLE = "feeapp_expense_items"

_client = None


class DbNotConfigured(Exception):
    pass


def get_client():
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise DbNotConfigured("伺服器尚未設定 SUPABASE_URL / SUPABASE_SERVICE_KEY，草稿功能無法使用")
        from supabase import create_client

        _client = create_client(url, key)
    return _client


def create_trip_leg(owner_name: str, leg: dict[str, Any]) -> dict[str, Any]:
    row = {
        "owner_name": owner_name,
        "date_from": leg.get("日期起", ""),
        "date_to": leg.get("日期迄", ""),
        "loc_from": leg.get("地點起", ""),
        "loc_to": leg.get("地點迄", ""),
        "amounts": leg.get("amounts", {}),
        "note": leg.get("摘要", ""),
    }
    resp = get_client().table(TRIP_LEGS_TABLE).insert(row).execute()
    return resp.data[0]


def create_expense_item(owner_name: str, item: dict[str, Any]) -> dict[str, Any]:
    row = {
        "owner_name": owner_name,
        "category": item.get("類別", "其他"),
        "item_date": item.get("日期", ""),
        "description": item.get("說明", ""),
        "amount": item.get("金額", 0) or 0,
    }
    resp = get_client().table(EXPENSE_ITEMS_TABLE).insert(row).execute()
    return resp.data[0]


def list_drafts(owner_name: str) -> dict[str, list]:
    client = get_client()
    legs = (
        client.table(TRIP_LEGS_TABLE)
        .select("*")
        .eq("owner_name", owner_name)
        .order("created_at")
        .execute()
    )
    items = (
        client.table(EXPENSE_ITEMS_TABLE)
        .select("*")
        .eq("owner_name", owner_name)
        .order("created_at")
        .execute()
    )
    return {"trip_legs": legs.data, "expense_items": items.data}


def get_trip_legs_by_ids(ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    resp = get_client().table(TRIP_LEGS_TABLE).select("*").in_("id", ids).execute()
    return resp.data


def get_expense_items_by_ids(ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    resp = get_client().table(EXPENSE_ITEMS_TABLE).select("*").in_("id", ids).execute()
    return resp.data


def delete_trip_leg(leg_id: str) -> None:
    get_client().table(TRIP_LEGS_TABLE).delete().eq("id", leg_id).execute()


def delete_expense_item(item_id: str) -> None:
    get_client().table(EXPENSE_ITEMS_TABLE).delete().eq("id", item_id).execute()


def delete_drafts(trip_leg_ids: list[str], expense_item_ids: list[str]) -> None:
    client = get_client()
    if trip_leg_ids:
        client.table(TRIP_LEGS_TABLE).delete().in_("id", trip_leg_ids).execute()
    if expense_item_ids:
        client.table(EXPENSE_ITEMS_TABLE).delete().in_("id", expense_item_ids).execute()
