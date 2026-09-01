from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import copy
from collections.abc import Callable, Sequence
from io import BytesIO
from os import getenv
from pathlib import Path
from threading import local

from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Font


OCRLines = Sequence[str]
OcrReader = Callable[[bytes], OCRLines]
AMOUNT_PATTERN = r"\d+(?:,\d{3})*\.\d{2}"


def normalize_column_name(value: str) -> str:
    return re.sub(r"[\s_\-()（）:：]", "", value).lower()


def clean_columns(raw_columns: Sequence[str]) -> list[str]:
    # Accept natural Chinese field lists pasted with commas, enumeration commas, or newlines.
    columns = [part.strip() for column in raw_columns for part in re.split(r"[，,、\n]+", column) if part.strip()]
    if not columns:
        raise ValueError("请至少填写一列。")
    if len(columns) > 20:
        raise ValueError("首版最多支持 20 列。")
    if len(set(columns)) != len(columns):
        raise ValueError("列名不能重复。")
    return columns


def _next_value(lines: OCRLines, labels: set[str]) -> str:
    normalized_labels = {normalize_column_name(label) for label in labels}
    for index, line in enumerate(lines[:-1]):
        if normalize_column_name(line) in normalized_labels:
            for candidate in lines[index + 1 :]:
                value = candidate.strip()
                if value and normalize_column_name(value) not in normalized_labels:
                    return value
    return ""


def _payment_time(text: str) -> str:
    matched = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*(\d{1,2}:\d{2}(?::\d{2})?)?", text)
    if not matched:
        return ""
    year, month, day, clock = matched.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}{f' {clock}' if clock else ''}"


def _personal_payment_title(lines: Sequence[str]) -> tuple[str, str]:
    """Read the payee shown in the large title of personal QR/transfer receipts."""
    for line in lines[:8]:
        compact = re.sub(r"\s+", "", line)
        matched = re.search(r"(?:扫.*?(?:付款|转账)|(?:付款|转账)).*?(?:给|向)(.+)", compact)
        if not matched:
            continue
        payee = matched.group(1).strip("-—－:：")
        description = re.sub(r"[-—－]?(?:给|向).*$", "", compact).strip("-—－:：")
        return payee, description or "个人付款"
    return "", ""


def _unlabelled_merchant_title(lines: Sequence[str]) -> str:
    """Some wallet receipts put the merchant only in the large page title."""
    ignored = ("账单", "支付成功", "收单机构", "支付方式", "交易单号", "经营单号", "当前状态", "账单服务", "收款方")
    for line in lines[:8]:
        compact = re.sub(r"\s+", "", line)
        if any(label in compact for label in ignored) or re.search(r"[-−]?\d[\d,]*\.\d{2}", compact):
            continue
        if len(re.findall(r"[\u4e00-\u9fff]", compact)) >= 2:
            return compact
    return ""


def extract_known_fields(lines: OCRLines) -> dict[str, str]:
    cleaned = [line.strip() for line in lines if line and line.strip()]
    text = "\n".join(cleaned)
    # Require cents to avoid reading a phone status-bar time such as "12:29" as an amount.
    amount_match = re.search(rf"[-−]?\s*[¥￥]?\s*({AMOUNT_PATTERN})", text)
    transaction_match = re.search(r"(?:交易单号|订单号|交易号|转账单号)\s*[:：]?\s*([A-Za-z0-9]{8,})", text)
    personal_payee, personal_description = _personal_payment_title(cleaned)
    title_merchant = _unlabelled_merchant_title(cleaned)

    return {
        "payment_amount": amount_match.group(1).replace(",", "") if amount_match else "",
        "payment_time": _payment_time(text),
        "merchant_name": _next_value(cleaned, {"商户全称", "收款方", "商家名称", "商户"}) or personal_payee or title_merchant,
        "product_name": _next_value(cleaned, {"商品", "商品名称", "订单内容"}) or personal_description or title_merchant,
        "transaction_number": transaction_match.group(1) if transaction_match else "",
    }


def extract_invoice_fields(lines: OCRLines) -> dict[str, str]:
    cleaned = [line.strip() for line in lines if line and line.strip()]
    text = "\n".join(cleaned)
    currency_amounts = re.findall(rf"[¥￥]\s*({AMOUNT_PATTERN})", text)
    # Digital VAT invoices commonly show amount, tax, then the tax-inclusive total last.
    amount_match = re.search(rf"({AMOUNT_PATTERN})", currency_amounts[-1]) if len(currency_amounts) >= 2 else None
    if not amount_match:
        amount_match = re.search(rf"(?:价税合计|合计|金额)\s*[:：]?\s*[¥￥]?\s*({AMOUNT_PATTERN})", text)
    if not amount_match and currency_amounts:
        amount_match = re.search(rf"({AMOUNT_PATTERN})", currency_amounts[-1])
    number_match = re.search(r"(?:发票号码|发票号)\s*[:：]?\s*([A-Za-z0-9]{6,})", text)
    invoice_number = number_match.group(1) if number_match else next((line for line in cleaned if re.fullmatch(r"\d{16,24}", line)), "")
    return {
        "invoice_amount": amount_match.group(1).replace(",", "") if amount_match else "",
        "invoice_number": invoice_number,
        "invoice_date": _payment_time(text),
    }


def classify_expense(row: dict[str, str]) -> str:
    """Assign a conservative reimbursement category from merchant and item text."""
    text = " ".join(
        row.get(key, "")
        for key in ("商家名称", "收款方", "商户全称", "商品", "商品名称", "备注")
    ).lower()
    categories = (
        ("住宿费", ("酒店", "宾馆", "旅馆", "民宿", "住宿")),
        ("交通费", ("滴滴", "高德", "打车", "出租", "地铁", "公交", "火车", "动车", "高铁", "机票", "航班", "停车", "加油")),
        ("工具/材料费", ("工具", "材料", "五金", "办公", "文具", "设备", "配件", "耗材", "采购", "商贸", "建材", "电器")),
        ("餐费", ("餐", "饭", "食堂", "餐饮", "美团", "饿了么", "咖啡", "奶茶", "便利店")),
    )
    return next((name for name, words in categories if any(word in text for word in words)), "其他")


def _date_text(value: str) -> tuple[int, int, int] | None:
    matched = re.search(r"(20\d{2})[-./年]\s*(\d{1,2})[-./月]\s*(\d{1,2})", value)
    if not matched:
        return None
    return tuple(map(int, matched.groups()))


def reimbursement_period(rows: Sequence[dict[str, str]]) -> str:
    """Use invoice dates for the title; payment dates are the fallback when no invoice exists."""
    dates = [date for row in rows for date in [_date_text(row.get("发票日期", "") or row.get("_invoice_date", ""))] if date]
    if not dates:
        dates = [date for row in rows for date in [_date_text(row.get("付款时间", ""))] if date]
    if not dates:
        return ""
    first, last = min(dates), max(dates)
    format_date = lambda date: f"{date[0]:04d}.{date[1]:02d}.{date[2]:02d}"
    return f"{format_date(first)}-{format_date(last)}"


def is_invoice(lines: OCRLines) -> bool:
    text = "\n".join(lines)
    return any(marker in text for marker in ("发票", "电子发票", "增值税"))


COLUMN_ALIASES = {
    "付款金额": "payment_amount",
    "支付金额": "payment_amount",
    "交易金额": "payment_amount",
    "金额": "payment_amount",
    "付款时间": "payment_time",
    "支付时间": "payment_time",
    "交易时间": "payment_time",
    "商家名称": "merchant_name",
    "商户名称": "merchant_name",
    "商户全称": "merchant_name",
    "收款方": "merchant_name",
    "商品": "product_name",
    "商品名称": "product_name",
    "备注": "product_name",
    "交易单号": "transaction_number",
    "订单号": "transaction_number",
    "发票金额": "invoice_amount",
    "发票号码": "invoice_number",
    "发票号": "invoice_number",
    "发票日期": "invoice_date",
}


def build_row(columns: Sequence[str], lines: OCRLines, source_name: str) -> dict[str, str]:
    fields = extract_known_fields(lines)
    row = {"源文件": source_name}
    alias_index = {normalize_column_name(name): value for name, value in COLUMN_ALIASES.items()}
    for column in columns:
        key = alias_index.get(normalize_column_name(column))
        row[column] = fields.get(key, "") if key else ""
    return row


def build_payment_rows(columns: Sequence[str], documents: Sequence[tuple[str, OCRLines]]) -> tuple[list[str], list[dict[str, str]]]:
    """Turns a mixed batch into one row per payment, with optional matched invoice fields."""
    result_columns = list(columns)
    if "是否有发票" not in result_columns:
        result_columns.append("是否有发票")

    invoices = [{**extract_invoice_fields(lines), "_source": name} for name, lines in documents if is_invoice(lines)]
    rows: list[dict[str, str]] = []
    for source_name, lines in documents:
        if is_invoice(lines):
            continue
        row = build_row(result_columns, lines, source_name)
        payment_amount = row.get("付款金额") or row.get("支付金额") or row.get("交易金额") or row.get("金额") or ""
        matched = next((invoice for invoice in invoices if payment_amount and invoice["invoice_amount"] == payment_amount), None)
        if matched:
            for column in result_columns:
                alias = COLUMN_ALIASES.get(column)
                if alias in matched:
                    row[column] = matched[alias]
            row["是否有发票"] = "有（金额匹配）"
            row["_invoice_source"] = matched["_source"]
            if matched["invoice_date"]:
                row["_invoice_date"] = matched["invoice_date"]
        else:
            row["是否有发票"] = "无"
        rows.append(row)
    return result_columns, rows


def create_workbook(columns: Sequence[str], rows: Sequence[dict[str, str]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "提取结果"
    headers = ["源文件", *columns]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append([row.get(header, "") for header in headers])
    for column_cells in sheet.columns:
        letter = column_cells[0].column_letter
        sheet.column_dimensions[letter].width = min(40, max(12, max(len(str(cell.value or "")) for cell in column_cells) + 2))
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _add_compact_image(sheet, cell: str, image_bytes: bytes | None, width: int, height: int) -> bool:
    """Bad or unsupported uploads should not prevent the user from exporting the text data."""
    if not image_bytes:
        return False
    try:
        if image_bytes.startswith(b"%PDF"):
            import pymupdf

            document = pymupdf.open(stream=image_bytes, filetype="pdf")
            image_bytes = document[0].get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2), alpha=False).tobytes("png")
            document.close()
        image = ExcelImage(BytesIO(image_bytes))
    except Exception:
        return False
    image.width = width
    image.height = height
    sheet.add_image(image, cell)
    return True


def create_reimbursement_workbook(rows: Sequence[dict[str, str]], payment_images: dict[str, bytes], invoice_images: dict[str, bytes], invoice_rows: Sequence[dict[str, str]] | None = None) -> bytes:
    """Writes a compact, filled-only reimbursement workbook based on the supplied layout."""
    template_path = Path(__file__).resolve().parents[2] / "templates" / "reimbursement-template.xlsx"
    workbook = load_workbook(template_path)
    source_sheet = workbook["支付明细"]
    payment_sheet = workbook.create_sheet("支付明细", 0)
    payment_sheet.sheet_view.showGridLines = False
    payment_sheet.freeze_panes = "A3"
    for letter in "ABCDEFGH":
        payment_sheet.column_dimensions[letter].width = source_sheet.column_dimensions[letter].width
    payment_sheet.column_dimensions["H"].width = 12
    for column in range(1, 9):
        for row_number in (1, 2):
            source = source_sheet.cell(row_number, column)
            target = payment_sheet.cell(row_number, column, source.value)
            target._style = copy(source._style)
            target.number_format = source.number_format
            target.alignment = copy(source.alignment)
            target.font = copy(source.font)
            target.fill = copy(source.fill)
            target.border = copy(source.border)
    payment_sheet.merge_cells("A1:H1")
    payment_sheet.row_dimensions[1].height = source_sheet.row_dimensions[1].height
    payment_sheet.row_dimensions[2].height = source_sheet.row_dimensions[2].height
    prefix = str(source_sheet["A1"].value or "刘生费用报销单").split("（", 1)[0].split("(", 1)[0]
    period = reimbursement_period(rows)
    payment_sheet["A1"] = f"{prefix}（{period}）" if period else prefix

    for index, row in enumerate(rows, start=3):
        amount_text = row.get("付款金额") or row.get("支付金额") or row.get("交易金额") or row.get("金额") or "0"
        try:
            amount = float(amount_text.replace(",", ""))
        except ValueError:
            amount = 0
        date_time = row.get("付款时间", "")
        date_value, _, time_value = date_time.partition(" ")
        values = [index - 2, date_value, time_value, row.get("商家名称") or row.get("收款方") or "", amount, classify_expense(row), "有票" if row.get("是否有发票") == "有（金额匹配）" else "无票"]
        for column, value in enumerate(values, start=1):
            source = source_sheet.cell(3, column)
            target = payment_sheet.cell(index, column, value)
            target._style = copy(source._style)
            target.alignment = copy(source.alignment)
            target.border = copy(source.border)
        payment_sheet.cell(index, 5).number_format = "0.00"
        image_bytes = payment_images.get(row.get("源文件", ""))
        _add_compact_image(payment_sheet, f"H{index}", image_bytes, 72, 108)
        payment_sheet.row_dimensions[index].height = 84

    total_row = len(rows) + 3
    for column in range(1, 9):
        source = source_sheet.cell(193, column)
        target = payment_sheet.cell(total_row, column)
        target._style = copy(source._style)
        target.alignment = copy(source.alignment)
        target.border = copy(source.border)
    payment_sheet.cell(total_row, 1, "合计")
    payment_sheet.cell(total_row, 5, f"=SUM(E3:E{total_row - 1})" if rows else 0)
    payment_sheet.cell(total_row, 5).number_format = "0.00"
    payment_sheet.auto_filter.ref = f"A2:H{total_row - 1}" if rows else "A2:H2"
    payment_sheet.print_area = f"A1:H{total_row}"

    # Remove the completed-example tabs and build a clean invoice tab containing only matched invoices.
    for sheet in list(workbook.worksheets):
        if sheet is not payment_sheet:
            workbook.remove(sheet)
    payment_sheet.title = "支付明细"
    invoice_sheet = workbook.create_sheet("发票明细")
    invoice_sheet.sheet_view.showGridLines = False
    invoice_sheet.append(["序号", "支付金额", "发票金额", "发票号码", "是否匹配", "发票图片"])
    invoice_sheet.freeze_panes = "A2"
    for cell in invoice_sheet[1]:
        cell.font = Font(bold=True)
    for letter, width in {"A": 8, "B": 13, "C": 13, "D": 18, "E": 14, "F": 14}.items():
        invoice_sheet.column_dimensions[letter].width = width
    matched_payments = {row.get("_invoice_source", ""): row for row in rows if row.get("_invoice_source")}
    if invoice_rows is None:
        invoice_rows = [{
            "_source": source,
            "invoice_amount": payment.get("发票金额", ""),
            "invoice_number": payment.get("发票号码", ""),
        } for source, payment in matched_payments.items()]
    invoice_index = 2
    for invoice in invoice_rows:
        source = invoice.get("_source", "")
        payment = matched_payments.get(source)
        invoice_sheet.append([
            invoice_index - 1,
            payment.get("付款金额", "") if payment else "",
            invoice.get("invoice_amount", ""),
            invoice.get("invoice_number", ""),
            "金额匹配" if payment else "未匹配",
        ])
        image_bytes = invoice_images.get(source)
        _add_compact_image(invoice_sheet, f"F{invoice_index}", image_bytes, 80, 120)
        invoice_sheet.row_dimensions[invoice_index].height = 92
        invoice_index += 1
    output = BytesIO(); workbook.save(output); return output.getvalue()


class LocalReceiptExtractor:
    """Reads images locally; OCR model weights are loaded on the host, never sent to an API."""

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        # Keep the server usable during a batch: two OCR sessions with two CPU threads each.
        # Both values can be adjusted at deployment time without a code change.
        thread_count = int(getenv("RECEIPT_OCR_THREADS", "2"))
        self._ocr = RapidOCR(intra_op_num_threads=thread_count, inter_op_num_threads=1)

    def read(self, image_bytes: bytes) -> list[str]:
        if image_bytes.startswith(b"%PDF"):
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(image_bytes))
            return [line.strip() for page in reader.pages for line in (page.extract_text() or "").splitlines() if line.strip()]
        result, _elapsed = self._ocr(image_bytes)
        return [item[1] for item in result or []]

    def read_many(self, images: Sequence[bytes], progress: Callable[[int, int, int], None] | None = None) -> list[list[str]]:
        """Run a small number of independent local OCR sessions concurrently."""
        if len(images) < 2:
            results = [self.read(image) for image in images]
            if images and progress:
                progress(1, 1, 0)
            return results
        worker_count = min(max(1, int(getenv("RECEIPT_OCR_WORKERS", "2"))), len(images))
        readers = local()

        def read_one(image: bytes) -> list[str]:
            if not hasattr(readers, "ocr"):
                readers.ocr = LocalReceiptExtractor()
            return readers.ocr.read(image)

        results: list[list[str] | None] = [None] * len(images)
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="receipt-ocr") as executor:
            futures = {executor.submit(read_one, image): index for index, image in enumerate(images)}
            for completed, future in enumerate(as_completed(futures), start=1):
                index = futures[future]
                results[index] = future.result()
                if progress:
                    progress(completed, len(images), index)
        return [result or [] for result in results]
