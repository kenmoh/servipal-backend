import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timedelta
from uuid import uuid4
from decimal import Decimal
from typing import Optional, List, Dict, Any


class MockResponse:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class MockUser:
    def __init__(self, id, email, user_metadata=None):
        self.id = str(id)
        self.email = email
        self.user_metadata = user_metadata or {}


class MockSession:
    def __init__(self, user):
        self.user = user
        self.access_token = "mock_access_token"
        self.refresh_token = "mock_refresh_token"
        self.expires_in = 3600
        self.session = self


class MockAuthResponse:
    def __init__(self, user, session=None):
        self.user = user
        self.session = session


class MockRPCBuilder:
    def __init__(self, db, name, params):
        self.db = db
        self.name = name
        self.params = params

    async def execute(self):
        await asyncio.sleep(0)
        if self.name == "get_food_vendors":
            return MockResponse(self.db.get("profiles", []))
        if self.name == "get_laundry_vendors":
            return MockResponse(self.db.get("profiles", []))
        if self.name == "calculate_distance":
            return MockResponse(5.0)
        if self.name == "get_vendor_detail_with_menu":
            vendor_id = self.params.get("vendor_user_id")
            return MockResponse(
                [
                    {
                        "vendor_json": {
                            "id": vendor_id,
                            "store_name": "Test Vendor",
                            "phone_number": "+2348000000000",
                        },
                        "category_json": {"id": str(uuid4()), "name": "Cat 1"},
                        "item_json": {
                            "id": str(uuid4()),
                            "name": "Item 1",
                            "price": 1000,
                            "in_stock": True,
                        },
                    }
                ]
            )
        if self.name == "update_wallet_balance":
            user_id = self.params.get("p_user_id")
            delta = self.params.get("p_delta")
            field = self.params.get("p_field", "balance")
            wallets = self.db.get("wallets", [])
            wallet = next(
                (w for w in wallets if str(w["user_id"]) == str(user_id)), None
            )
            if wallet:
                wallet[field] = float(wallet.get(field, 0)) + float(delta)
            return MockResponse({"status": "success"})

        if self.name == "assign_rider_to_paid_delivery":
            return MockResponse(
                {
                    "success": True,
                    "message": "Rider assigned",
                    "rider_name": "Test Rider",
                    "delivery_status": "ASSIGNED",
                }
            )

        return MockResponse([])


class MockQueryBuilder:
    def __init__(self, table_name, db):
        self.table_name = table_name
        self.db = db
        self.query_filters = []
        self.limit_val = None
        self.order_val = None
        self.is_single = False
        self.select_cols = "*"
        self.range_val = None
        self.count_mode = None

    def select(self, columns="*", count=None):
        self.select_cols = columns
        self.count_mode = count
        return self

    def insert(self, data):
        self.operation = "insert"
        self.data_payload = data
        return self

    def update(self, data):
        self.operation = "update"
        self.data_payload = data
        return self

    def upsert(self, data):
        self.operation = "upsert"
        self.data_payload = data
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def eq(self, column, value):
        self.query_filters.append((column, "eq", str(value)))
        return self

    def neq(self, column, value):
        self.query_filters.append((column, "neq", str(value)))
        return self

    def lt(self, column, value):
        self.query_filters.append((column, "lt", value))
        return self

    def gt(self, column, value):
        self.query_filters.append((column, "gt", value))
        return self

    def gte(self, column, value):
        self.query_filters.append((column, "gte", value))
        return self

    def lte(self, column, value):
        self.query_filters.append((column, "lte", value))
        return self

    def in_(self, column, values):
        self.query_filters.append((column, "in", [str(v) for v in values]))
        return self

    def or_(self, criteria):
        self.query_filters.append(("OR", "or", criteria))
        return self

    def order(self, column, desc=False):
        self.order_val = (column, desc)
        return self

    def limit(self, count):
        self.limit_val = count
        return self

    def range(self, start, end):
        self.range_val = (start, end)
        return self

    def single(self):
        self.is_single = True
        return self

    def _add_defaults(self, item):
        if self.table_name == "profiles":
            defaults = {
                "email": None,
                "phone_number": "+2348000000000",
                "full_name": None,
                "user_type": "CUSTOMER",
                "store_name": None,
                "business_name": None,
                "profile_image_url": None,
                "backdrop_image_url": None,
                "is_online": False,
                "is_verified": False,
                "is_blocked": False,
                "account_status": "ACTIVE",
                "last_seen_at": None,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "dispatcher_id": None,
                "bike_number": None,
                "business_address": None,
                "state": None,
                "can_pickup_and_dropoff": False,
                "pickup_and_delivery_charge": 0.0,
                "total_deliveries": 0,
                "average_rating": 0.0,
                "review_count": 0,
                "total_distance_travelled": 0.0,
                "has_delivery": False,
                "order_cancel_count": 0,
                "rider_is_suspended_for_order_cancel": False,
            }
        elif self.table_name == "disputes":
            defaults = {
                "resolution_notes": None,
                "resolved_by_id": None,
                "resolved_at": None,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
        else:
            defaults = {
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

        for k, v in defaults.items():
            if k not in item:
                item[k] = v
        return item

    async def execute(self):
        await asyncio.sleep(0)
        if self.table_name not in self.db:
            self.db[self.table_name] = []
        table_data = self.db[self.table_name]

        if hasattr(self, "operation"):
            if self.operation == "insert":
                payloads = (
                    self.data_payload
                    if isinstance(self.data_payload, list)
                    else [self.data_payload]
                )
                to_return = []
                for item in payloads:
                    new_item = item.copy()
                    if "id" not in new_item:
                        new_item["id"] = str(uuid4())
                    self._add_defaults(new_item)
                    if self.table_name == "transactions" and "tx_ref" not in new_item:
                        new_item["tx_ref"] = f"TX-{uuid4().hex[:8].upper()}"
                    table_data.append(new_item)
                    to_return.append(new_item)
                return MockResponse(to_return)

            elif self.operation == "update":
                filtered = self._apply_filters(table_data)
                updated_items = []
                for item in filtered:
                    item.update(self.data_payload)
                    updated_items.append(item)
                return MockResponse(updated_items)

            elif self.operation == "upsert":
                payloads = (
                    self.data_payload
                    if isinstance(self.data_payload, list)
                    else [self.data_payload]
                )
                upserted = []
                for p in payloads:
                    new_item = p.copy()
                    idx = None
                    if "id" in new_item:
                        idx = next(
                            (
                                i
                                for i, d in enumerate(table_data)
                                if str(d["id"]) == str(new_item["id"])
                            ),
                            None,
                        )

                    if idx is not None:
                        table_data[idx].update(new_item)
                        upserted.append(table_data[idx])
                    else:
                        if "id" not in new_item:
                            new_item["id"] = str(uuid4())
                        self._add_defaults(new_item)
                        if (
                            self.table_name == "transactions"
                            and "tx_ref" not in new_item
                        ):
                            new_item["tx_ref"] = f"TX-{uuid4().hex[:8].upper()}"
                        table_data.append(new_item)
                        upserted.append(new_item)
                return MockResponse(upserted)

            elif self.operation == "delete":
                candidates = self._apply_filters(table_data)
                candidate_ids = [c.get("id") for c in candidates]
                self.db[self.table_name] = [
                    row for row in table_data if row.get("id") not in candidate_ids
                ]
                return MockResponse(candidates)

        results = self._apply_filters(table_data)

        if self.order_val:
            col, desc = self.order_val
            results.sort(key=lambda x: str(x.get(col, "")), reverse=desc)

        if self.range_val:
            start, end = self.range_val
            results = results[start : end + 1]
        elif self.limit_val:
            results = results[: self.limit_val]

        if self.is_single:
            if not results:
                return MockResponse(None)
            return MockResponse(results[0])

        return MockResponse(results, count=len(results))

    def _apply_filters(self, data):
        filtered = list(data)
        for col, op, val in self.query_filters:
            if op == "eq":
                filtered = [r for r in filtered if str(r.get(col)) == str(val)]
            elif op == "neq":
                filtered = [r for r in filtered if str(r.get(col)) != str(val)]
            elif op == "lt":
                filtered = [
                    r for r in filtered if r.get(col) is not None and r.get(col) < val
                ]
            elif op == "gt":
                filtered = [
                    r for r in filtered if r.get(col) is not None and r.get(col) > val
                ]
            elif op == "gte":
                filtered = [
                    r
                    for r in filtered
                    if r.get(col) is not None and str(r.get(col)) >= str(val)
                ]
            elif op == "lte":
                filtered = [
                    r
                    for r in filtered
                    if r.get(col) is not None and str(r.get(col)) <= str(val)
                ]
            elif op == "in":
                filtered = [
                    r for r in filtered if str(r.get(col)) in [str(v) for v in val]
                ]
            elif op == "or":
                if "," in val:
                    conditions = val.split(",")
                    or_results = []
                    for c in conditions:
                        parts = c.split(".")
                        if len(parts) == 3 and parts[1] == "eq":
                            c_col, _, c_val = parts
                            or_results.extend(
                                [r for r in data if str(r.get(c_col)) == str(c_val)]
                            )
                    seen = set()
                    unique_res = []
                    for r in or_results:
                        if id(r) not in seen:
                            seen.add(id(r))
                            unique_res.append(r)
                    filtered = unique_res
        return filtered


class MockSupabaseAuth:
    def __init__(self, db):
        self.db = db
        self.users = {}

    async def sign_up(self, credentials):
        email = credentials.get("email")
        metadata = credentials.get("options", {}).get("data", {})
        if email not in self.users:
            user_id = str(uuid4())
            self.users[email] = MockUser(user_id, email, metadata)
            profile_data = {
                "id": user_id,
                "email": email,
                "full_name": metadata.get("full_name"),
                "phone_number": metadata.get("phone", "+2348000000000"),
                "user_type": metadata.get("user_type", "CUSTOMER"),
            }
            builder = MockQueryBuilder("profiles", self.db)
            builder._add_defaults(profile_data)
            self.db["profiles"].append(profile_data)
        return MockAuthResponse(self.users[email], MockSession(self.users[email]))

    async def sign_in_with_password(self, credentials):
        email = credentials.get("email")
        if email not in self.users:
            user_id = str(uuid4())
            self.users[email] = MockUser(user_id, email)
            profile_data = {"id": user_id, "email": email}
            builder = MockQueryBuilder("profiles", self.db)
            builder._add_defaults(profile_data)
            self.db["profiles"].append(profile_data)
        return MockAuthResponse(self.users[email], MockSession(self.users[email]))

    class Admin:
        def __init__(self, parent):
            self.parent = parent

        async def create_user(self, attributes):
            email = attributes.get("email")
            user = MockUser(str(uuid4()), email, attributes.get("user_metadata"))
            self.parent.users[email] = user
            return MockAuthResponse(user)

        async def update_user_by_id(self, user_id, attributes):
            return {"id": user_id, "status": "updated"}

    @property
    def admin(self):
        return self.Admin(self)


class MockSupabaseClient:
    def __init__(self):
        self._data = {
            "disputes": [],
            "dispute_messages": [],
            "profiles": [],
            "users": [],
            "wallets": [],
            "transactions": [],
            "product_items": [],
            "product_orders": [],
            "delivery_orders": [],
            "reviews": [],
            "food_vendors": [],
            "laundry_vendors": [],
            "charges_and_commissions": [
                {"base_delivery_fee": 500, "delivery_fee_per_km": 100}
            ],
            "profile_images": [],
            "food_orders": [],
            "laundry_orders": [],
            "menu_items": [],
            "laundry_services": [],
            "fcm_tokens": [],
            "audit_logs": [],
        }
        self.auth = MockSupabaseAuth(self._data)

    def table(self, name):
        return MockQueryBuilder(name, self._data)

    def rpc(self, name, params=None):
        return MockRPCBuilder(self._data, name, params or {})


@pytest.fixture
def mock_supabase():
    return MockSupabaseClient()
