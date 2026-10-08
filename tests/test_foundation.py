import polars as pl, pytest
from fastapi.testclient import TestClient
from backend.api.app import app
from backend.data.ingest import load_file, IngestError
from backend.security.sql_validator import validate_readonly_sql, UnsafeQueryError

@pytest.fixture
def sales_df():
    import random; random.seed(1)
    rows = []
    for i in range(300):
        rows.append({"order_id": i + 1, "order_date": f"2024-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}",
                     "region": ["East", "West", "North"][i % 3], "revenue": round(random.uniform(50, 200), 2),
                     "quantity": random.randint(1, 5)})
    rows.append({"order_id": 301, "order_date": "2024-06-01", "region": "West", "revenue": 99999.0, "quantity": 1})
    return pl.DataFrame(rows)

@pytest.fixture
def csv_path(tmp_path, sales_df):
    p = tmp_path / "sales.csv"; sales_df.write_csv(p); return p

@pytest.fixture
def xlsx_path(tmp_path, sales_df):
    p = tmp_path / "sales.xlsx"
    sales_df.write_excel(p, worksheet="Orders")
    return p

@pytest.mark.parametrize("sql", [
    "DROP TABLE x", "select 1; select 2", "DELETE FROM t", "COPY t TO 'x.csv'",
    "select * from read_csv('/etc/passwd')", "ATTACH 'x.db'", "", "SET threads=1",
    "WITH a AS (select 1) INSERT INTO t select * from a",
])
def test_validator_rejects(sql):
    with pytest.raises(UnsafeQueryError):
        validate_readonly_sql(sql)

def test_validator_allows_select_and_literals():
    validate_readonly_sql("SELECT region, SUM(revenue) FROM sales WHERE note = 'drop; table' GROUP BY 1;")
    validate_readonly_sql("WITH a AS (SELECT 1) SELECT * FROM a")

def test_csv_ingest_and_profile(csv_path):
    c = TestClient(app)
    r = c.post("/datasets/open", json={"path": str(csv_path)}); assert r.status_code == 200, r.text
    did = r.json()["id"]
    prof = c.get(f"/datasets/{did}/profile").json()
    t = prof["tables"][0]
    cols = {x["name"]: x for x in t["columns"]}
    assert t["rows"] == 301
    assert "order_id" in t["primary_key_candidates"]
    assert cols["order_id"]["semantic_role"] == "identifier"
    assert cols["order_date"]["kind"] == "date"
    assert cols["revenue"]["semantic_role"] == "revenue"
    assert cols["region"]["semantic_role"] == "geographic"
    assert cols["revenue"]["stats"]["outliers_iqr"] >= 1   # the injected 99999 order
    assert t["duplicate_rows"] == 0

def test_excel_ingest(xlsx_path):
    tables = load_file(xlsx_path)
    assert tables[0].source_sheet == "Orders" and tables[0].df.height == 301

def test_original_file_is_untouched(csv_path):
    before = csv_path.read_bytes()
    TestClient(app).post("/datasets/open", json={"path": str(csv_path)})
    assert csv_path.read_bytes() == before

def test_query_endpoint(csv_path):
    c = TestClient(app)
    did = c.post("/datasets/open", json={"path": str(csv_path)}).json()["id"]
    r = c.post(f"/datasets/{did}/query", json={"sql": "SELECT region, COUNT(*) n FROM sales GROUP BY 1 ORDER BY 1"})
    assert r.status_code == 200 and r.json()["row_count"] == 3
    assert c.post(f"/datasets/{did}/query", json={"sql": "DROP TABLE sales"}).status_code == 400
    # engine-level lockdown holds even if the validator were bypassed
    ds = __import__("backend.api.app", fromlist=["store"]).store.get(did)
    with pytest.raises(Exception):
        ds.con.execute("SELECT * FROM read_csv('/etc/passwd')")

def test_errors_are_friendly(tmp_path):
    c = TestClient(app)
    bad = tmp_path / "bad.xlsx"; bad.write_bytes(b"not an excel file")
    r = c.post("/datasets/open", json={"path": str(bad)}); assert r.status_code == 422 and "Traceback" not in r.text
    empty = tmp_path / "e.csv"; empty.write_text("")
    assert c.post("/datasets/open", json={"path": str(empty)}).status_code == 422
    hdr = tmp_path / "h.csv"; hdr.write_text("a,b\n")
    assert c.post("/datasets/open", json={"path": str(hdr)}).status_code == 422
    assert c.post("/datasets/open", json={"path": str(tmp_path / "x.xls")}).status_code == 422
    assert c.get("/datasets/nope/profile").status_code == 404

def test_relationship_detection(tmp_path):
    p = tmp_path / "book.xlsx"
    import xlsxwriter
    wb = xlsxwriter.Workbook(p)
    ws = wb.add_worksheet("Orders"); ws.write_row(0, 0, ["order_id", "customer_id", "amt"])
    for i in range(1, 21): ws.write_row(i, 0, [i, (i % 5) + 1, i * 10])
    ws2 = wb.add_worksheet("Customers"); ws2.write_row(0, 0, ["customer_id", "name"])
    for i in range(1, 6): ws2.write_row(i, 0, [i, f"c{i}"])
    wb.close()
    did = TestClient(app).post("/datasets/open", json={"path": str(p)}).json()["id"]
    rels = TestClient(app).get(f"/datasets/{did}/profile").json()["relationships"]
    assert any(r["from"].endswith("orders.customer_id") and r["to"].endswith("customers.customer_id") for r in rels)
