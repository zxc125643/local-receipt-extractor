from io import BytesIO

from openpyxl import load_workbook
from PIL import Image

from backend.app.services.receipt_extractor import (
    build_invoice_record,
    build_payment_rows,
    build_row,
    clean_columns,
    classify_expense,
    classify_expense_detail,
    create_reimbursement_workbook,
    create_workbook,
    extract_invoice_fields,
    extract_known_fields,
    reimbursement_period,
    reimbursement_workbook_title,
    parse_manual_draft,
)


SAMPLE_LINES = [
    "账单",
    "孝昌那些年餐饮服务管理有限公司",
    "-405.00",
    "支付时间",
    "2026年8月23日 19:36:37",
    "商品",
    "孝昌那些年餐饮服务管理有限公司-消费",
    "商户全称",
    "孝昌那些年餐饮服务管理有限公司",
    "交易单号",
    "4200003244202608239077856598",
]


def test_extract_known_fields_from_receipt_lines():
    fields = extract_known_fields(SAMPLE_LINES)

    assert fields["payment_amount"] == "405.00"
    assert fields["payment_time"] == "2026-08-23 19:36:37"
    assert fields["merchant_name"] == "孝昌那些年餐饮服务管理有限公司"
    assert fields["product_name"].endswith("-消费")
    assert fields["transaction_number"] == "4200003244202608239077856598"


def test_extract_known_fields_from_personal_qr_payment():
    fields = extract_known_fields([
        "账单", "扫一扫付款-给福润烟酒店", "-800.00", "转账时间", "2026年8月22日 17:53:15", "转账单号", "100010730120260822006103709", "53101",
    ])

    assert fields == {
        "payment_amount": "800.00",
        "payment_time": "2026-08-22 17:53:15",
        "merchant_name": "福润烟酒店",
        "product_name": "扫一扫付款",
        "transaction_number": "100010730120260822006103709",
    }


def test_extracts_unlabelled_merchant_title_from_wallet_receipt():
    fields = extract_known_fields([
        "账单", "柒柒小厨餐饮", "-12.00", "当前状态", "支付成功", "收单机构", "财付通支付科技有限公司", "支付时间", "2026年8月5日 19:40:34",
    ])

    assert fields["merchant_name"] == "柒柒小厨餐饮"
    assert fields["product_name"] == "柒柒小厨餐饮"


def test_extract_invoice_uses_tax_inclusive_total_from_digital_invoice():
    fields = extract_invoice_fields([
        "电子发票（增值税专用发票）", "发票号码：", "26424000000104330311", "开票日期：", "2026年08月09日",
        "金额 税额", "￥2376.24 ￥23.76", "价税合计（大写） （小写）", "贰仟肆佰圆整 ￥2400.00",
    ])

    assert fields["invoice_amount"] == "2400.00"
    assert fields["invoice_number"] == "26424000000104330311"
    assert fields["invoice_date"] == "2026-08-09"
    assert fields["invoice_merchant"] == ""


def test_invoice_seller_name_is_not_mistaken_for_invoice_item():
    fields = extract_invoice_fields([
        "电子发票", "价税合计", "405.00", "发票号码", "INV123456",
        "销售方信息", "名称：孝昌那些年餐饮服务管理有限公司",
    ])

    assert fields["invoice_merchant"] == "孝昌那些年餐饮服务管理有限公司"
    assert fields["invoice_item"] == ""


def test_invoice_item_extraction_supports_goods_without_service_keyword():
    fields = extract_invoice_fields([
        "电子发票", "项目名称", "办公用品", "价税合计", "120.00",
        "销售方信息", "名称：某某商贸有限公司",
    ])

    assert fields["invoice_item"] == "办公用品"
    assert classify_expense_detail({"_invoice_item": fields["invoice_item"]}).category == "工具/材料费"


def test_build_row_only_includes_requested_columns():
    row = build_row(["付款金额", "付款时间", "商家名称", "备注", "不存在的字段"], SAMPLE_LINES, "receipt.jpg")

    assert row == {
        "源文件": "receipt.jpg",
        "付款金额": "405.00",
        "付款时间": "2026-08-23 19:36:37",
        "商家名称": "孝昌那些年餐饮服务管理有限公司",
        "备注": "孝昌那些年餐饮服务管理有限公司-消费",
        "不存在的字段": "",
    }


def test_create_workbook_uses_requested_headers_and_rows():
    content = create_workbook(["付款金额"], [{"源文件": "a.jpg", "付款金额": "405.00"}])
    workbook = load_workbook(BytesIO(content))
    sheet = workbook.active

    assert list(sheet.values) == [("源文件", "付款金额"), ("a.jpg", "405.00")]


def test_build_payment_rows_requires_amount_and_identity_evidence_to_match_invoice():
    columns, rows = build_payment_rows(
        ["付款金额", "发票金额", "发票号码"],
        [
            ("payment.jpg", SAMPLE_LINES),
            (
                "invoice.jpg",
                [
                    "电子发票",
                    "价税合计",
                    "405.00",
                    "发票号码",
                    "INV123456",
                    "开票日期",
                    "2026年8月23日",
                    "销售方信息",
                    "名称：孝昌那些年餐饮服务管理有限公司",
                ],
            ),
            ("unmatched.jpg", ["电子发票", "价税合计", "99.00", "发票号码", "INV999999"]),
        ],
    )

    assert columns[:4] == ["付款金额", "发票金额", "发票号码", "是否有发票"]
    assert {"费用用途", "分类置信度", "分类依据"}.issubset(columns)
    assert rows[0]["源文件"] == "payment.jpg"
    assert rows[0]["付款金额"] == "405.00"
    assert rows[0]["发票金额"] == "405.00"
    assert rows[0]["发票号码"] == "INV123456"
    assert rows[0]["是否有发票"] == "有（金额匹配）"
    assert rows[0]["_invoice_source"] == "invoice.jpg"
    assert rows[0]["_invoice_date"] == "2026-08-23"
    assert rows[0]["费用用途"] == "餐票"
    assert rows[0]["分类置信度"] == "中"
    assert rows[1]["源文件"] == "unmatched.jpg"
    assert rows[1]["付款金额"] == "99.00"
    assert rows[1]["是否有发票"] == "仅发票（无支付记录）"


def test_same_amount_without_date_or_merchant_evidence_is_not_force_matched():
    columns, rows = build_payment_rows(
        ["付款金额"],
        [
            ("payment.jpg", SAMPLE_LINES),
            ("invoice.jpg", ["电子发票", "价税合计", "405.00", "发票号码", "INV123456"]),
        ],
    )

    assert columns[:3] == ["付款金额", "是否有发票", "核对状态"]
    assert {"费用用途", "分类置信度", "分类依据"}.issubset(columns)
    assert rows[0]["是否有发票"] == "无"
    assert rows[0]["核对状态"] == "需人工核对"
    assert "存在同金额发票，但日期或商家无法确认" in rows[0]["_review_reason"]
    assert "没有足够信息确定费用用途" in rows[0]["_review_reason"]
    assert rows[1]["是否有发票"] == "仅发票（无支付记录）"


def test_payment_missing_date_or_merchant_requires_manual_review():
    columns, rows = build_payment_rows(
        ["付款金额", "付款时间", "商家名称"],
        [("payment.jpg", ["付款金额", "88.00", "支付成功"])],
    )

    assert "核对状态" in columns
    assert rows[0]["核对状态"] == "需人工核对"
    assert "付款时间" in rows[0]["_review_reason"]
    assert "商家名称" in rows[0]["_review_reason"]


def test_invoice_does_not_match_when_date_evidence_is_missing():
    _columns, rows = build_payment_rows(
        ["付款金额", "付款时间", "商家名称", "发票金额"],
        [
            ("payment.jpg", ["付款金额", "550.00", "商户全称", "甲餐饮有限公司"]),
            ("invoice.jpg", ["电子发票", "价税合计", "550.00", "销售方名称", "甲餐饮有限公司"]),
        ],
    )

    assert rows[0]["是否有发票"] == "无"
    assert rows[0]["核对状态"] == "需人工核对"
    assert rows[1]["是否有发票"] == "仅发票（无支付记录）"


def test_same_date_and_amount_do_not_match_weakly_similar_merchants():
    _columns, rows = build_payment_rows(
        ["付款金额", "付款时间", "商家名称"],
        [
            ("payment.jpg", ["付款金额", "550.00", "支付时间", "2026年9月5日 12:00:00", "商户全称", "孝昌甲餐饮有限公司"]),
            ("invoice.jpg", ["电子发票", "价税合计", "550.00", "开票日期", "2026年9月5日", "销售方名称", "孝昌乙餐饮有限公司"]),
        ],
    )

    assert rows[0]["是否有发票"] == "无"
    assert rows[1]["是否有发票"] == "仅发票（无支付记录）"


def test_invoice_only_missing_identity_fields_requires_manual_review():
    columns, rows = build_payment_rows(
        ["付款金额", "付款时间", "商家名称"],
        [("invoice.jpg", ["电子发票", "价税合计", "88.00", "发票号码", "INV12345678"])],
    )

    assert "核对状态" in columns
    assert rows[0]["核对状态"] == "需人工核对"
    assert "发票日期" in rows[0]["_review_reason"]
    assert "销售方" in rows[0]["_review_reason"]


def test_clean_columns_splits_chinese_enumeration_commas():
    assert clean_columns(["付款金额、付款时间、商家名称、备注"]) == ["付款金额", "付款时间", "商家名称", "备注"]


def test_passenger_ticket_uses_same_invoice_record_for_matching_and_export():
    invoice = build_invoice_record(
        "客运票.jpg",
        [
            "湖北省道路客运发票",
            "发票号码",
            "142002499041",
            "始发站",
            "孝感",
            "到达站",
            "孝昌",
            "班次",
            "6001",
            "乘车日期",
            "2026-09-05",
            "票价",
            "￥10",
        ],
    )

    assert invoice["invoice_amount"] == "10"
    assert invoice["invoice_date"] == "2026-09-05"
    assert invoice["invoice_number"] == "142002499041"
    assert invoice["invoice_merchant"] == "湖北省道路客运"
    assert invoice["invoice_item"] == "客运车票"


def test_reimbursement_export_is_compact_and_prefers_payment_period():
    content = create_reimbursement_workbook(
        [{
            "源文件": "payment.jpg",
            "付款金额": "405.00",
            "付款时间": "2026-05-31 19:36:37",
            "商家名称": "某某餐饮服务有限公司",
            "备注": "晚餐消费",
            "发票金额": "405.00",
            "发票号码": "INV123456",
            "发票日期": "2026-06-30",
            "是否有发票": "有（金额匹配）",
            "_invoice_source": "invoice.jpg",
        }],
        {},
        {},
    )
    workbook = load_workbook(BytesIO(content), data_only=False)
    payment_sheet = workbook["支付明细"]
    invoice_sheet = workbook["发票明细"]

    assert workbook.sheetnames == ["支付明细", "发票明细"]
    assert payment_sheet["A1"].value.endswith("（2026.05.31-2026.05.31）")
    assert list(payment_sheet.values)[2][:7] == (1, "2026-05-31", "19:36:37", "某某餐饮服务有限公司", 405.0, "餐票", "有票")
    assert payment_sheet["A4"].value == "合计"
    assert payment_sheet["E4"].value == "=SUM(E3:E3)"
    assert payment_sheet.max_row == 8
    assert list(invoice_sheet.values)[2][:5] == (1, "405.00", "405.00", "INV123456", "金额匹配")
    assert invoice_sheet.max_row == 3


def test_reimbursement_period_includes_payment_and_invoice_only_rows():
    assert reimbursement_period([
        {"付款时间": "2026-09-01 12:00:00", "发票日期": "2026-09-02"},
        {"_invoice_only": "1", "_invoice_date": "2026-09-05"},
    ]) == "2026.09.01-2026.09.05"


def test_expense_classification_has_requested_categories():
    assert classify_expense({"备注": "酒店住宿"}) == "住宿费"
    assert classify_expense({"商家名称": "五金工具店"}) == "工具/材料费"
    assert classify_expense({"商家名称": "滴滴出行"}) == "交通费"
    assert classify_expense({"商家名称": "某餐饮店"}) == "餐票"
    assert classify_expense({"商家名称": "本地餐厅"}) == "餐票"
    assert classify_expense({"商家名称": "福润烟酒店"}) == "其他"
    assert classify_expense({"商家名称": "未知商户"}) == "其他"


def test_expense_classification_prefers_invoice_item_over_merchant_name():
    detail = classify_expense_detail({
        "商家名称": "某某酒店管理有限公司",
        "_invoice_item": "*金属制品*五金工具",
    })

    assert detail.category == "工具/材料费"
    assert detail.confidence == "高"
    assert detail.review_required is False
    assert "发票项目" in detail.reason


def test_expense_classification_uses_general_conflict_exclusions():
    assert classify_expense({"商家名称": "福润烟酒店"}) == "其他"
    assert classify_expense({"商家名称": "宏达烟酒商行"}) == "其他"
    assert classify_expense({"商家名称": "华美酒店用品商店"}) == "工具/材料费"
    assert classify_expense({"商家名称": "兴业酒店设备有限公司"}) == "工具/材料费"
    assert classify_expense({"商家名称": "孝昌如家酒店"}) == "住宿费"


def test_expense_classification_distinguishes_passenger_and_freight_transport():
    passenger = classify_expense_detail({"_invoice_item": "*运输服务*旅客运输服务"})
    generic = classify_expense_detail({"_invoice_item": "*运输服务*运输服务"})
    freight = classify_expense_detail({"_invoice_item": "*运输服务*货物运输服务"})

    assert (passenger.category, passenger.confidence, passenger.review_required) == ("车票", "高", False)
    assert (generic.category, generic.confidence, generic.review_required) == ("车票", "中", False)
    assert (freight.category, freight.confidence, freight.review_required) == ("其他", "低", True)


def test_expense_classification_explains_ambiguous_and_unknown_records():
    ambiguous = classify_expense_detail({"商家名称": "某某酒店管理有限公司"})
    unknown = classify_expense_detail({"商家名称": "未知商户"})

    assert (ambiguous.category, ambiguous.confidence, ambiguous.review_required) == ("其他", "低", True)
    assert "不能证明实际住宿" in ambiguous.reason
    assert (unknown.category, unknown.confidence, unknown.review_required) == ("其他", "低", True)


def test_payment_rows_include_explainable_expense_classification():
    columns, rows = build_payment_rows(
        ["付款金额", "商家名称"],
        [("payment.jpg", SAMPLE_LINES)],
    )

    assert "费用用途" in columns
    assert "分类置信度" in columns
    assert "分类依据" in columns
    assert rows[0]["费用用途"] == "餐票"
    assert rows[0]["分类置信度"] == "中"
    assert "商户类型" in rows[0]["分类依据"]


def test_reimbursement_export_keeps_unmatched_invoice_as_standalone_reimbursement():
    image_buffer = BytesIO()
    Image.new("RGB", (20, 20), "white").save(image_buffer, format="PNG")
    content = create_reimbursement_workbook(
        [],
        {},
        {"invoice.png": image_buffer.getvalue()},
        [{"_source": "invoice.png", "invoice_amount": "2400.00", "invoice_number": "26424000000104330311"}],
    )
    workbook = load_workbook(BytesIO(content), data_only=False)

    assert workbook.sheetnames == ["支付明细"]
    assert list(workbook["支付明细"].values)[2][:7] == (1, None, None, None, 2400.0, "其他", "仅发票")
    assert len(workbook["支付明细"]._images) == 1


def test_payment_export_includes_classification_audit_columns():
    content = create_reimbursement_workbook(
        [{
            "源文件": "payment.jpg", "付款金额": "88.00", "商家名称": "本地餐厅",
            "费用用途": "餐票", "分类置信度": "中", "分类依据": "商户类型：餐厅",
            "核对状态": "", "是否有发票": "无",
        }],
        {},
        {},
    )
    workbook = load_workbook(BytesIO(content), data_only=False)
    headers = [cell.value for cell in workbook["支付明细"][2]]

    assert headers[7:11] == ["分类置信度", "分类依据", "核对状态", "付款截图"]


def test_embedded_receipt_image_is_aspect_fitted_and_centered():
    image_buffer = BytesIO()
    Image.new("RGB", (20, 20), "white").save(image_buffer, format="PNG")
    content = create_reimbursement_workbook(
        [{"源文件": "square.png", "付款金额": "10.00", "是否有发票": "无"}],
        {"square.png": image_buffer.getvalue()},
        {},
    )
    workbook = load_workbook(BytesIO(content), data_only=False)
    embedded = workbook["支付明细"]._images[0]

    assert embedded.width == embedded.height
    assert embedded.anchor._from.rowOff > 0


def test_text_pdf_reads_every_page_including_invoice_text():
    import pymupdf
    from backend.app.services.receipt_extractor import LocalReceiptExtractor

    document = pymupdf.open()
    first = document.new_page(); first.insert_text((72, 72), "Invoice 12345678")
    second = document.new_page(); second.insert_text((72, 72), "Total 88.00")
    payload = document.tobytes(); document.close()
    extractor = LocalReceiptExtractor.__new__(LocalReceiptExtractor)

    lines = extractor.read(payload)

    assert any("Invoice" in line for line in lines)
    assert any("Total" in line for line in lines)


def test_corrupted_invoice_pdf_text_layer_falls_back_to_page_ocr(monkeypatch):
    from backend.app.services.receipt_extractor import LocalReceiptExtractor

    class FakeTextPage:
        def extract_text(self):
            return "电子发票\n开票日期：\n2025/7/4 15:52 localhost:63342/template\n\x00\x01"

    class FakePixmap:
        def tobytes(self, _format):
            return b"not-a-real-png"

    class FakeRenderedPage:
        def get_pixmap(self, **_kwargs):
            return FakePixmap()

    class FakeDocument:
        def __iter__(self):
            return iter([FakeRenderedPage()])

        def close(self):
            return None

    monkeypatch.setattr("pypdf.PdfReader", lambda _stream: type("Reader", (), {"pages": [FakeTextPage()]})())
    monkeypatch.setattr("pymupdf.open", lambda **_kwargs: FakeDocument())
    extractor = LocalReceiptExtractor.__new__(LocalReceiptExtractor)
    extractor.engine = "rapidocr"
    extractor._ocr = lambda _image: ([(None, "开票日期：2026年09月05日", 1.0)], 0.1)

    lines = extractor.read(b"%PDF fake")

    assert lines == ["开票日期：2026年09月05日"]


def test_invoice_only_payment_summary_uses_classified_expense_not_raw_tax_item():
    content = create_reimbursement_workbook(
        [{
            "源文件": "invoice.pdf",
            "是否有发票": "仅发票（无支付记录）",
            "_invoice_amount": "88.00",
            "_invoice_item": "*生产生活服务*餐饮服务",
            "_invoice_source": "invoice.pdf",
            "_invoice_only": "1",
        }],
        {},
        {},
    )
    workbook = load_workbook(BytesIO(content), data_only=False)

    assert workbook["支付明细"]["F3"].value == "餐票"


def test_reimbursement_export_totals_manual_only_entries():
    content = create_reimbursement_workbook(
        [],
        {},
        {},
        manual_entries=[
            {"金额": "320", "日期": "", "商家": "", "用途": "出差餐补", "备注": ""},
            {"金额": "131.43", "日期": "", "商家": "", "用途": "车票", "备注": ""},
        ],
    )
    workbook = load_workbook(BytesIO(content), data_only=False)
    sheet = workbook["支付明细"]

    assert list(sheet.values)[2][:7] == (1, None, None, None, 320.0, "出差餐补", "无票无支付记录")
    assert list(sheet.values)[3][:7] == (2, None, None, None, 131.43, "车票", "无票无支付记录")
    assert sheet["E5"].value == "=SUM(E3:E4)"
    assert sheet["B8"].value == "=E5"


def test_manual_entry_dates_are_appended_to_workbook_and_download_title():
    manual_entries = [
        {"金额": "8", "日期": "2026-09-02", "商家": "", "用途": "车票", "备注": ""},
        {"金额": "320", "日期": "2026-09-05", "商家": "", "用途": "出差餐补", "备注": ""},
    ]
    content = create_reimbursement_workbook([], {}, {}, title_override="张三费用报销单", manual_entries=manual_entries)
    workbook = load_workbook(BytesIO(content), data_only=False)

    assert workbook["支付明细"]["A1"].value == "张三费用报销单（2026.09.02-2026.09.05）"
    assert reimbursement_workbook_title([], "张三费用报销单", manual_entries) == "张三费用报销单（2026.09.02-2026.09.05）"


def test_manual_draft_parses_compact_amount_expressions_exactly():
    entries, errors = parse_manual_draft("出差餐补320\n车票8+8.43+105+10")

    assert errors == []
    assert [(entry["用途"], entry["金额"], entry["类型"]) for entry in entries] == [
        ("出差餐补", "320.00", "无票无支付记录"),
        ("车票", "131.43", "无票无支付记录"),
    ]
    assert entries[1]["备注"] == "8+8.43+105+10=131.43"


def test_manual_draft_rejects_uncertain_lines_instead_of_guessing():
    entries, errors = parse_manual_draft("车票金额待定")

    assert entries == []
    assert errors == ["第 1 行无法确认用途或金额：车票金额待定"]
