"""Read-only iiko keg register and two-year usage export.

Credentials are read from the project .env and never written to output.
See docs/keg-catalog.md for the classification and usage definitions.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
MSK = timezone(timedelta(hours=3))
KEG_GROUP_ID = "4a5b2a76-8f86-4365-b8e6-5c9aeecd3323"
ARCHIVE_GROUP_IDS = {"14bc1f9d-e172-1a9d-0196-f2627515aab6",
                     "be375ee4-671f-4c7b-87ae-ab945b1f8edc"}


def save_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def settings():
    values = {}
    for raw in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            value = re.sub(r"\s+#.*$", "", value)
        values[key.strip()] = value
    return lambda key, default=None: os.environ.get(key, values.get(key, default))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class IikoReader:
    """Only auth/logout, reference GETs and read-only OLAP POSTs are used."""

    def __init__(self):
        get = settings()
        host, port = get("IIKO_SERVER", "first-federation.iiko.it"), get("IIKO_PORT", "443")
        if not re.fullmatch(r"[A-Za-z0-9.-]+", host) or not port.isdigit():
            raise ValueError("Invalid server configuration format")
        self.base = f"https://{host}:{port}/resto/api"
        self.login, self.password = get("IIKO_LOGIN"), get("IIKO_PASSWORD")
        if not self.login or not self.password:
            raise ValueError("Missing iiko credentials")
        self.token = None
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, path, params=None, body=None, timeout=60):
        params = dict(params or {})
        if self.token and path != "/auth":
            params["key"] = self.token
        url = self.base + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json, application/xml, text/plain"}
        if data is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(url, data=data, headers=headers)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            # The HTTP error object's URL can include credentials: never print it.
            detail = error.read().decode("utf-8", errors="replace") if path != "/auth" else ""
            for secret in (self.token, self.login, self.password,
                           hashlib.sha1(self.password.encode()).hexdigest()):
                if secret:
                    detail = detail.replace(secret, "[redacted]")
            raise RuntimeError(f"HTTP {error.code} on {path}: {detail[:600]}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise RuntimeError(f"Network failure on {path}: {type(reason).__name__}; "
                               f"errno={getattr(reason, 'errno', None)}") from None

    def json(self, path, params=None, body=None, timeout=60):
        return json.loads(self.request(path, params, body, timeout).decode("utf-8-sig"))

    def __enter__(self):
        raw = self.request("/auth", {"login": self.login,
                           "pass": hashlib.sha1(self.password.encode()).hexdigest()}, timeout=30)
        value = raw.decode("utf-8-sig").strip()
        if value.startswith("<"):
            value = "".join(ET.fromstring(value).itertext()).strip()
        self.token = str(uuid.UUID(value))
        print("Authenticated; credentials and token omitted.", flush=True)
        return self

    def __exit__(self, *args):
        if self.token:
            self.request("/logout", timeout=10)
            self.token = None
            print("Logged out; license slot released.", flush=True)


def download_catalog(output: Path):
    endpoints = [
        ("products", "/v2/entities/products/list", {"includeDeleted": "true"}),
        ("groups", "/v2/entities/products/group/list", {"includeDeleted": "true"}),
        ("units", "/v2/entities/list", {"rootType": "MeasureUnit", "includeDeleted": "true"}),
        ("transaction-columns", "/v2/reports/olap/columns", {"reportType": "TRANSACTIONS"}),
    ]
    manifest = {"retrieved_at": datetime.now(MSK).isoformat(), "source": "live iiko Server API", "files": []}
    with IikoReader() as api:
        for name, path, params in endpoints:
            value = api.json(path, params)
            filename = f"source-{name}.json"
            save_json(output / filename, value)
            manifest["files"].append({"file": filename, "endpoint": path, "parameters": params,
                "sha256": hashlib.sha256((output / filename).read_bytes()).hexdigest()})
            print(f"Downloaded {name}: {len(value)} entries", flush=True)
    save_json(output / "source-manifest.json", manifest)


def candidate_ids(output: Path):
    """Broad audit population; classification is applied after the usage read."""
    products = read_json(output / "source-products.json")
    units = {row["id"]: row["name"] for row in read_json(output / "source-units.json")}
    return sorted(row["id"] for row in products if row["type"] == "GOODS" and
                  (units.get(row.get("mainUnit")) == "л" or
                   "кег" in row["name"].casefold()))


def month_intervals(start: date, end_exclusive: date):
    while start < end_exclusive:
        next_month = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        stop = min(next_month, end_exclusive)
        yield start, stop
        start = stop


def usage_query(ids, start, stop):
    return {
        "reportType": "TRANSACTIONS", "buildSummary": False,
        "groupByRowFields": ["Account.Name", "Product.Id", "Product.Name", "Product.Num",
                             "Product.Type", "Product.MeasureUnit", "DateTime.DateTyped",
                             "TransactionType"],
        "groupByColFields": [], "aggregateFields": ["Amount.In", "Amount.Out"],
        "filters": {
            "DateTime.DateTyped": {"filterType": "DateRange", "periodType": "CUSTOM",
                                  "from": start.isoformat(), "to": stop.isoformat(),
                                  "includeLow": True, "includeHigh": False},
            "Product.Id": {"filterType": "IncludeValues", "values": ids},
            "Account.StoreOrAccount": {"filterType": "IncludeValues", "values": ["STORE"]},
            "TransactionType": {"filterType": "ExcludeValues", "values": ["OPENING_BALANCE"]},
        },
    }


def download_usage(output: Path, start: date, through: date, refresh=False):
    if start > through:
        raise ValueError("Period start must not follow the inclusive end")
    ids = candidate_ids(output)
    columns = read_json(output / "source-transaction-columns.json")
    query_sample = usage_query(ids, start, through + timedelta(days=1))
    required = query_sample["groupByRowFields"] + query_sample["aggregateFields"] + list(query_sample["filters"])
    if any(field not in columns for field in required):
        raise ValueError("A requested field is not supported by the live OLAP columns")
    manifest = {"source": "live iiko Server API; read-only TRANSACTIONS report",
                "periodStart": start.isoformat(), "periodEnd": through.isoformat(),
                "candidateCount": len(ids), "files": []}
    with IikoReader() as api:
        for first, stop in month_intervals(start, through + timedelta(days=1)):
            filename = f"source-usage-{first.isoformat()}-{stop.isoformat()}.json"
            path = output / filename
            query = usage_query(ids, first, stop)
            if path.exists() and not refresh:
                record = read_json(path)
                if record.get("query") != query:
                    raise ValueError(f"Cached query differs: {filename}; use --refresh")
            else:
                value = api.json("/v2/reports/olap", body=query, timeout=60)
                if not isinstance(value, dict) or not isinstance(value.get("data"), list):
                    raise ValueError("Unexpected OLAP response structure")
                record = {"retrievedAt": datetime.now(MSK).isoformat(), "query": query,
                          "response": value}
                save_json(path, record)
            rows = record["response"]["data"]
            manifest["files"].append({"file": filename, "rows": len(rows),
                "retrievedAt": record["retrievedAt"],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            save_json(output / "source-usage-manifest.json", manifest)
            print(f"Usage {first} to {stop} exclusive: {len(rows)} rows", flush=True)
    manifest["complete"] = True
    manifest["completedAt"] = datetime.now(MSK).isoformat()
    save_json(output / "source-usage-manifest.json", manifest)


def group_chain(product, groups):
    chain = []
    current = product.get("parent")
    seen = set()
    while current:
        if current in seen or current not in groups:
            raise ValueError(f"Incomplete/cyclic hierarchy for product {product['id']}")
        seen.add(current)
        chain.insert(0, groups[current])
        current = groups[current].get("parent")
    return chain


def keg_reason(product, chain, unit):
    if product["type"] != "GOODS":
        return None
    if unit == "л":
        if any(group["id"] == KEG_GROUP_ID for group in chain):
            return "Группа кег в iiko, товар в литрах"
        if any(re.search(r"кег|keg", container.get("name", ""), re.I)
               for container in product.get("containers", [])):
            return "Кеговая фасовка в карточке товара"
        if re.search(r"\b(?:кег|keg)", product["name"], re.I):
            return "Кег явно указан в названии; товар в литрах"
    if unit == "шт" and re.search(r"\bпиво\b.*\bкег", product["name"], re.I):
        return "Кег явно указан в названии; учёт в штуках"
    return None


def export_register(output: Path):
    products = read_json(output / "source-products.json")
    groups = {row["id"]: row for row in read_json(output / "source-groups.json")}
    units = {row["id"]: row["name"] for row in read_json(output / "source-units.json")}
    catalog_manifest = read_json(output / "source-manifest.json")
    usage_manifest = read_json(output / "source-usage-manifest.json")
    if not usage_manifest.get("complete"):
        raise ValueError("Usage download is incomplete")
    start, through = (date.fromisoformat(usage_manifest[key]) for key in ("periodStart", "periodEnd"))
    expected = list(month_intervals(start, through + timedelta(days=1)))
    if len(expected) != len(usage_manifest["files"]):
        raise ValueError("Incomplete monthly coverage")
    for entry in catalog_manifest["files"] + usage_manifest["files"]:
        if hashlib.sha256((output / entry["file"]).read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Source checksum mismatch: {entry['file']}")
    catalog = []
    for product in products:
        if product["type"] != "GOODS":
            continue
        unit = units.get(product.get("mainUnit"))
        chain = group_chain(product, groups)
        reason = keg_reason(product, chain, unit)
        if not reason:
            continue
        archived = any(g["id"] in ARCHIVE_GROUP_IDS for g in chain)
        status = "Удалена" if product["deleted"] else "В архиве" if archived else "Актуальная"
        containers = sorted({f"{c['name']}: {c.get('count')} {unit}"
                             for c in product.get("containers", []) if not c.get("deleted")})
        notes = []
        if product["name"].strip() == "1":
            notes.append("Название сорта не установлено; кеговая фасовка подтверждена карточкой")
        if unit == "шт":
            notes.append("Нет надёжного коэффициента перевода в литры; название не использовано для пересчёта")
        catalog.append({"id": product["id"], "article": product["num"], "name": product["name"],
            "group": " / ".join(g["name"] for g in chain), "unit": unit, "status": status,
            "deleted": product["deleted"], "archived": archived, "containers": "; ".join(containers),
            "classification": reason, "notes": "; ".join(notes)})
    ids = {row["id"] for row in catalog}
    audit_ids = candidate_ids(output)
    if len(ids) != len(catalog) or not ids.issubset(set(audit_ids)):
        raise ValueError("Duplicate catalogue GUID or keg missing from queried population")
    movements = {product_id: [] for product_id in ids}
    total_rows = nonzero_rows = 0
    excluded_products = set()
    operation_counts = Counter()
    for entry, (first, stop) in zip(usage_manifest["files"], expected):
        record = read_json(output / entry["file"])
        if record["query"] != usage_query(audit_ids, first, stop):
            raise ValueError("Saved request does not match expected period and filters")
        for raw in record["response"]["data"]:
            total_rows += 1
            day = date.fromisoformat(raw["DateTime.DateTyped"][:10])
            incoming = Decimal(str(raw.get("Amount.In") or 0))
            outgoing = Decimal(str(raw.get("Amount.Out") or 0))
            if not first <= day < stop or raw["TransactionType"] == "OPENING_BALANCE":
                raise ValueError("Report returned an excluded date or opening balance")
            if not incoming.is_finite() or not outgoing.is_finite():
                raise ValueError("Invalid quantity")
            if incoming == 0 and outgoing == 0:
                continue
            product_id = raw["Product.Id"]
            if product_id not in ids:
                excluded_products.add(product_id)
                continue
            nonzero_rows += 1
            operation_counts[raw["TransactionType"]] += 1
            movements[product_id].append((raw, incoming, outgoing))
    for row in catalog:
        activity = movements[row["id"]]
        if any(raw["Product.MeasureUnit"] != row["unit"] for raw, _, _ in activity):
            raise ValueError(f"Mixed units for {row['id']}; no automatic conversion allowed")
        dates = sorted({raw["DateTime.DateTyped"][:10] for raw, _, _ in activity})
        sale_rows = [(raw, inc, out) for raw, inc, out in activity
                     if raw["TransactionType"] == "SESSION_WRITEOFF" and out != 0]
        row.update({
            "usedInPeriod": bool(activity), "soldInPeriod": bool(sale_rows),
            "firstUsed": dates[0] if dates else None, "lastUsed": dates[-1] if dates else None,
            "activityDays": len(dates),
            "incoming": float(sum((inc for _, inc, _ in activity), Decimal(0))),
            "outgoing": float(sum((out for _, _, out in activity), Decimal(0))),
            "salesOut": float(sum((out for _, _, out in sale_rows), Decimal(0))),
            "otherOut": float(sum((out for raw, _, out in activity
                                    if raw["TransactionType"] != "SESSION_WRITEOFF"), Decimal(0))),
            "warehouses": "; ".join(sorted({raw["Account.Name"] for raw, _, _ in activity})),
            "operationTypes": "; ".join(sorted({raw["TransactionType"] for raw, _, _ in activity})),
        })
    catalog.sort(key=lambda row: ({"Актуальная": 0, "В архиве": 1, "Удалена": 2}[row["status"]],
                                  row["name"].casefold(), row["id"]))
    used = [row for row in catalog if row["usedInPeriod"]]
    summary = {"all": len(catalog), "current": sum(r["status"] == "Актуальная" for r in catalog),
               "archived": sum(r["status"] == "В архиве" for r in catalog),
               "deleted": sum(r["deleted"] for r in catalog), "used": len(used),
               "usedCurrent": sum(r["status"] == "Актуальная" for r in used),
               "sold": sum(r["soldInPeriod"] for r in catalog),
               "usedWithoutSales": sum(not r["soldInPeriod"] for r in used),
               "neverMovedInPeriod": len(catalog) - len(used),
               "sourceRows": total_rows, "nonzeroKegRows": nonzero_rows,
               "months": len(expected), "excludedNonKegWithMovement": len(excluded_products),
               "units": dict(Counter(r["unit"] for r in catalog)),
               "operationRows": dict(operation_counts)}
    methodology = [
        {"label": "Источник и время", "text": f"Живой iiko Server API. Справочник: {catalog_manifest['retrieved_at']}. История собрана до {usage_manifest['completedAt']}."},
        {"label": "Период", "text": f"{start:%d.%m.%Y} — {through:%d.%m.%Y} включительно. Последний день содержит проведённые операции на момент выгрузки. Запросы по {len(expected)} непересекающимся месячным интервалам; правая граница исключена."},
        {"label": "Полный реестр", "text": "Внутренние товары GOODS: литровые карточки группы Kеги либо с кеговой фасовкой/явным КЕГ в названии; также две карточки пива в кегах с учётом в штуках. GOODS отделяет складской товар от порционных блюд DISH. Товары поставщиков OUTER не дублируются."},
        {"label": "Статусы", "text": f"{summary['current']} актуальная карточка, {summary['archived']} в архивной группе без отметки удаления, {summary['deleted']} удалённых. Актуальная карточка означает статус справочника, а не наличие остатка сегодня."},
        {"label": "Использовались", "text": "Есть строка складского отчёта с ненулевым приходом Amount.In ИЛИ расходом Amount.Out. Учитываются поставки, продажи, списания, инвентаризации, перемещения и возвраты. Начальные остатки OPENING_BALANCE и бухгалтерские коррсчета исключены."},
        {"label": "Продажи", "text": "Отдельный признак: есть ненулевой расход SESSION_WRITEOFF — складское списание по кассовой смене. Это отдельный критерий, не синоним любого движения."},
        {"label": "Объёмы", "text": "Приход и расход суммируются отдельно в базовой единице карточки, со знаками, которые вернул iiko. Перемещения между складами входят в оба оборота. Списание по продажам — только SESSION_WRITEOFF; прочий расход — остальные типы. Объёмы в штуках не смешиваются с литрами."},
        {"label": "Склады", "text": "Все складские счета сети без ограничения по заведению: Большой пр. В.О, Варшавская, Кременчугская, Лиговский. Первый/последний день и список складов рассчитаны только по ненулевому движению в выбранном периоде."},
        {"label": "Идентичность", "text": "Одна строка — один GUID товара iiko. Названия и артикулы сохранены из текущего справочника. Похожие/одинаковые названия не объединяются. GUID и артикулы — текст; сохраняются начальные нули."},
        {"label": "Особые карточки", "text": "Архивная карточка с названием «1» включена: кеговая фасовка подтверждена iiko, сорт не установлен. Две карточки в штуках не переведены в литры по числу из названия. Примечания приведены в строках."},
        {"label": "Точность", "text": "Суммы рассчитаны Decimal без промежуточного округления. Excel показывает объёмы до 0,001 базовой единицы; исходные значения доступны в JSON. Нулевой итоговый остаток не исключает использование. Строка OLAP агрегирована по дню/товару/складу/типу, не является отдельным документом."},
        {"label": "Воспроизводимость", "text": "Рядом сохранены исходные справочники, запросы и ответы за каждый интервал, контрольные SHA-256 и keg-register.json. Логины, пароли и токены в выгрузку не включены."},
    ]
    def column(key, label, width, kind="text"):
        result = {"key": key, "label": label, "width": width, "type": kind}
        if kind == "number":
            result["format"] = '#,##0.000;[Red](#,##0.000);"—"'
        return result
    identity = [column("article", "Артикул iiko", 17), column("name", "Название кеги в iiko", 60)]
    status = [column("status", "Статус карточки", 19), column("unit", "Ед. учёта", 11)]
    dates = [column("firstUsed", "Первое движение", 19, "date"),
             column("lastUsed", "Последнее движение", 19, "date")]
    tail = [column("id", "GUID товара iiko", 40), column("group", "Группа iiko", 45),
            column("containers", "Фасовки из iiko", 65), column("notes", "Примечание", 65)]
    all_columns = identity + status + [column("usedInPeriod", "Движение за период", 21, "boolean"),
        column("soldInPeriod", "Списание по продажам", 23, "boolean")] + dates + tail
    used_columns = identity + status + [column("soldInPeriod", "Списание по продажам", 23, "boolean")] + dates + [
        column("salesOut", "По продажам, ед.", 21, "number"),
        column("otherOut", "Прочий расход, ед.", 23, "number"),
        column("incoming", "Весь приход, ед.", 22, "number"),
        column("warehouses", "Склады с движением", 60),
        column("operationTypes", "Типы операций iiko", 70)] + tail
    result = {"metadata": {"generatedAt": datetime.now(MSK).isoformat(),
        "periodStart": start.isoformat(), "periodEnd": through.isoformat(),
        "sourceLabel": "Источник: живой справочник и складской OLAP iiko",
        "allTitle": "Полный реестр кег iiko", "usedTitle": "Кеги с движением за последние два года",
        "methodology": methodology}, "summary": summary, "allKegs": catalog, "usedKegs": used,
        "allColumns": all_columns, "usedColumns": used_columns}
    save_json(output / "keg-register.json", result)
    for filename, rows, columns in [("all-kegs.csv", catalog, all_columns), ("used-kegs-2-years.csv", used, used_columns)]:
        with (output / filename).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow([c["label"] for c in columns])
            for row in rows:
                values = [row.get(c["key"]) for c in columns]
                writer.writerow([("Да" if v else "Нет") if isinstance(v, bool) else
                    ("'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v) for v in values])
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["catalog", "usage", "export"], required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "output/kegs-2026-09-20")
    parser.add_argument("--from-date", type=date.fromisoformat, default=date(2024, 9, 20))
    parser.add_argument("--through-date", type=date.fromisoformat, default=date(2026, 9, 20))
    parser.add_argument("--refresh", action="store_true", help="Replace saved usage responses")
    args = parser.parse_args()
    if args.phase == "catalog":
        download_catalog(args.output)
    elif args.phase == "usage":
        download_usage(args.output, args.from_date, args.through_date, args.refresh)
    elif args.phase == "export":
        export_register(args.output)


if __name__ == "__main__":
    main()
