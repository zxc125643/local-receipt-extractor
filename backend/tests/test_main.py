import time
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.app import main


class FakeExtractor:
    def read_many(self, images, progress, worker_count=2):
        results = []
        for index, _image in enumerate(images):
            results.append(["-88.00", "支付时间", "2026年9月8日 12:30:00", "商户全称", "本地餐厅"])
            progress(index + 1, len(images), index)
        return results


def _wait(client: TestClient, job_id: str, headers: dict[str, str]):
    for _ in range(100):
        response = client.get(f"/api/status/{job_id}", headers=headers)
        if response.json().get("status") in {"completed", "failed"}:
            return response
        time.sleep(0.01)
    raise AssertionError("OCR job did not finish")


def test_api_requires_token_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("RECEIPT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RECEIPT_ACCESS_TOKEN", "secret")
    with TestClient(main.app) as client:
        response = client.get("/api/history")
    assert response.status_code == 401


def test_standalone_workflow_persists_deduplicates_and_exports(tmp_path, monkeypatch):
    monkeypatch.setenv("RECEIPT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RECEIPT_ACCESS_TOKEN", "secret")
    monkeypatch.setattr(main, "get_extractor", lambda: FakeExtractor())
    main.jobs.clear()
    headers = {"X-Receipt-Token": "secret"}

    with TestClient(main.app) as client:
        started = client.post(
            "/api/process",
            headers=headers,
            data={"columns": '["付款金额", "付款时间", "商家名称"]', "worker_count": "2", "title": "张三费用报销单"},
            files=[
                ("files", ("one.jpg", b"same-image", "image/jpeg")),
                ("files", ("copy.jpg", b"same-image", "image/jpeg")),
            ],
        )
        assert started.status_code == 200
        assert started.json()["total"] == 1
        assert started.json()["duplicate_count"] == 1
        job_id = started.json()["job_id"]
        status = _wait(client, job_id, headers)
        assert status.json()["status"] == "completed"
        assert status.json()["rows"][0]["费用用途"] == "餐票"
        assert status.json()["rows"][0]["分类置信度"] == "中"

        manual = client.put(
            f"/api/history/{job_id}/manual",
            headers=headers,
            json={"manual_entries": [{"金额": "320", "日期": "2026-09-09", "商家": "", "用途": "出差餐补", "备注": ""}], "manual_draft": ""},
        )
        renamed = client.patch(f"/api/history/{job_id}", headers=headers, json={"title": "张三费用报销单"})
        history = client.get("/api/history", headers=headers)
        main.jobs.clear()
        exported = client.post("/api/export", headers=headers, json={"job_id": job_id})

    assert manual.status_code == 200
    assert renamed.status_code == 200
    assert history.json()[0]["manual_entries"][0]["金额"] == "320"
    assert exported.status_code == 200
    assert "2026.09.08-2026.09.09" in exported.headers["content-disposition"]
    workbook = load_workbook(BytesIO(exported.content), data_only=False)
    assert workbook["支付明细"]["E3"].value == 88.0
    assert workbook["支付明细"]["F3"].value == "餐票"
    assert workbook["支付明细"]["E4"].value == 320.0


def test_legacy_history_rows_gain_current_classification():
    saved = main._dedupe_saved({
        "columns": ["付款金额", "商家名称"],
        "rows": [{"源文件": "old.jpg", "付款金额": "800.00", "商家名称": "福润烟酒店"}],
    })
    assert saved["rows"][0]["费用用途"] == "其他"
    assert saved["rows"][0]["分类置信度"] == "中"
    assert "分类依据" in saved["columns"]


def test_manual_text_parser_is_available_through_authenticated_api(tmp_path, monkeypatch):
    monkeypatch.setenv("RECEIPT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RECEIPT_ACCESS_TOKEN", "secret")
    with TestClient(main.app) as client:
        response = client.post(
            "/api/manual/parse",
            headers={"X-Receipt-Token": "secret"},
            json={"manual_draft": "出差餐补320\n车票8+8.43+105+10"},
        )

    assert response.status_code == 200
    assert [entry["金额"] for entry in response.json()["manual_entries"]] == ["320.00", "131.43"]


def test_ocr_identity_deduplication_is_independent_of_selected_columns(tmp_path, monkeypatch):
    monkeypatch.setenv("RECEIPT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RECEIPT_ACCESS_TOKEN", "secret")
    monkeypatch.setattr(main, "get_extractor", lambda: FakeExtractor())
    main.jobs.clear()
    headers = {"X-Receipt-Token": "secret"}

    with TestClient(main.app) as client:
        started = client.post(
            "/api/process",
            headers=headers,
            data={"columns": '["付款金额"]', "worker_count": "2"},
            files=[
                ("files", ("one.jpg", b"first-render", "image/jpeg")),
                ("files", ("same-transaction.jpg", b"second-render", "image/jpeg")),
            ],
        )
        status = _wait(client, started.json()["job_id"], headers)
        history = client.get("/api/history", headers=headers)

    assert started.json()["duplicate_count"] == 0
    assert len(status.json()["rows"]) == 1
    assert status.json()["duplicate_count"] == 1
    assert status.json()["duplicate_files"] == ["same-transaction.jpg"]
    assert history.json()[0]["duplicate_count"] == 1
