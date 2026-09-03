import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { deleteReceiptHistory, downloadReceiptWorkbook, getReceiptHistory, getSavedApiToken, processReceiptImages, renameReceiptHistory, saveApiToken, type ReceiptHistory } from "../api/client";

type Notice = { tone: "success" | "error" | "info"; text: string };
type ReceiptProgress = { completed: number; total: number; currentFile: string; status: string };

function splitColumns(value: string) {
  return value.split(/[，,、\n]/).map((item) => item.trim()).filter(Boolean);
}

export function ReceiptExtractorPage() {
  const fileInput = useRef<HTMLInputElement>(null);
  const [columnsText, setColumnsText] = useState("付款金额、付款时间、商家名称、备注");
  const [files, setFiles] = useState<File[]>([]);
  const [workerCount, setWorkerCount] = useState(2);
  const [token, setToken] = useState(getSavedApiToken());
  const [result, setResult] = useState<{ job_id: string; columns: string[]; rows: Array<Record<string, string>> } | null>(null);
  const [progress, setProgress] = useState<ReceiptProgress | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [history, setHistory] = useState<ReceiptHistory[]>([]);
  useEffect(() => { void getReceiptHistory().then(setHistory).catch(() => undefined); }, []);
  const processMutation = useMutation({
    mutationFn: ({ columns, files, workerCount }: { columns: string[]; files: File[]; workerCount: number }) => processReceiptImages({ columns, files, workerCount }, setProgress),
    onSuccess: (data) => {
      setResult(data);
      void getReceiptHistory().then(setHistory).catch(() => undefined);
      setNotice({ tone: data.duplicate_count ? "info" : "success", text: `已在本机识别 ${data.rows.length} 张图片。${data.duplicate_count ? `发现重复图片 ${data.duplicate_count} 张，已跳过重复计算。` : "未发现重复图片。"} 请核对后导出 Excel。` });
    },
    onError: (error) => setNotice({ tone: "error", text: error instanceof Error ? error.message : "识别失败。" }),
  });

  const columns = splitColumns(columnsText);
  const startProcessing = () => {
    saveApiToken(token);
    if (columns.length === 0) {
      setNotice({ tone: "error", text: "请先填写至少一个要提取的列名。" });
      return;
    }
    if (files.length === 0) {
      setNotice({ tone: "error", text: "请先选择图片。" });
      return;
    }
    setResult(null);
    setProgress({ completed: 0, total: files.length, currentFile: "", status: "queued" });
    setNotice({ tone: "info", text: "正在本机识别，图片不会上传到云端。" });
    processMutation.mutate({ columns, files, workerCount });
  };

  return (
    <section className="page receipt-page">
      <div className="panel receipt-hero">
        <div>
          <p className="eyebrow">离线处理</p>
          <h3>截图提取到 Excel</h3>
          <p className="muted-text">描述要哪几列，批量上传混合截图；识别和文件生成均在 Ubuntu 主机本地完成。</p>
        </div>
        <label className="filter-field receipt-token">
          <span className="field-label">访问口令</span>
          <input className="text-input" type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder="部署时设置的 CORE_GATEWAY_TOKEN" />
        </label>
      </div>

      <div className="panel receipt-form">
        <label className="filter-field">
          <span className="field-label">要提取的列</span>
          <textarea className="text-input receipt-columns" value={columnsText} onChange={(event) => setColumnsText(event.target.value)} />
          <span className="field-hint">用逗号或换行分隔。首版支持：付款金额、付款时间、商家名称、商品名称、备注、交易单号、发票金额、发票号码；系统会自动增加“是否有发票”。</span>
        </label>
        <input ref={fileInput} className="hidden-file-input" accept="image/jpeg,image/png,image/webp,application/pdf" multiple type="file" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} />
        <div className="receipt-actions">
          <button className="secondary-button" type="button" onClick={() => fileInput.current?.click()}>选择图片</button>
          <span className="muted-text">{files.length ? `已选 ${files.length} 个文件` : "支持 JPG、PNG、WEBP、PDF，单次最多 200 个文件"}</span>
          <label className="filter-field receipt-workers"><span className="field-label">识别线程</span><select className="text-input" value={workerCount} onChange={(event) => setWorkerCount(Number(event.target.value))}><option value={1}>1（低占用）</option><option value={2}>2（推荐）</option><option value={3}>3</option><option value={4}>4（较快）</option></select></label>
          <button className="primary-button" disabled={processMutation.isPending} type="button" onClick={startProcessing}>{processMutation.isPending ? "本机识别中…" : "开始提取"}</button>
        </div>
      </div>

      {notice ? <div aria-live="polite" className={`notice notice-${notice.tone}`} data-prefix={notice.tone === "error" ? "!" : "i"}><p>{notice.text}</p></div> : null}

      {processMutation.isPending && progress ? <div aria-live="polite" className="panel receipt-progress">
        <div className="receipt-progress-heading"><strong>正在识别：{progress.completed} / {progress.total} 张</strong><span>{progress.total ? Math.round((progress.completed / progress.total) * 100) : 0}%</span></div>
        <div aria-valuemax={progress.total} aria-valuemin={0} aria-valuenow={progress.completed} className="receipt-progress-track" role="progressbar"><span style={{ width: `${progress.total ? (progress.completed / progress.total) * 100 : 0}%` }} /></div>
        <p className="muted-text">{progress.currentFile ? (progress.completed ? `刚完成：${progress.currentFile}` : `正在识别：${progress.currentFile}`) : "正在准备本地 OCR…"}</p>
      </div> : null}

      {result ? <div className="panel receipt-results">
        <div className="panel-header">
          <div><h3>提取预览</h3><p className="muted-text">空白字段表示本地 OCR 未能可靠定位，请直接核对后导出。</p></div>
          <button className="primary-button" type="button" onClick={() => void downloadReceiptWorkbook(result).catch((error) => setNotice({ tone: "error", text: error instanceof Error ? error.message : "导出失败。" }))}>导出 Excel</button>
        </div>
        <div className="table-shell"><table className="data-table"><thead><tr><th>源文件</th>{result.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{result.rows.map((row, index) => <tr key={`${row["源文件"]}-${index}`}><td>{row["源文件"]}</td>{result.columns.map((column) => <td key={column}>{row[column] || "—"}</td>)}</tr>)}</tbody></table></div>
      </div> : null}
      <div className="panel receipt-history"><div className="panel-header"><div><h3>本地历史记录</h3><p className="muted-text">记录保存在 Ubuntu 本地，不上传云端。</p></div></div>{history.length === 0 ? <p className="muted-text">暂无历史批次</p> : <div className="table-shell"><table className="data-table"><thead><tr><th>名称</th><th>处理时间</th><th>图片数</th><th>结果行数</th><th>操作</th></tr></thead><tbody>{history.map((item) => <tr key={item.job_id}><td>{item.title}</td><td>{new Date(item.created_at).toLocaleString()}</td><td>{item.total}</td><td>{item.rows.length}</td><td><button className="secondary-button" type="button" onClick={() => setResult({ job_id: item.job_id, columns: item.columns, rows: item.rows })}>查看</button> <button className="secondary-button" type="button" onClick={() => { const title = window.prompt("请输入历史记录名称", item.title); if (title?.trim()) void renameReceiptHistory(item.job_id, title.trim()).then(() => setHistory((items) => items.map((x) => x.job_id === item.job_id ? { ...x, title: title.trim() } : x))); }}>重命名</button> <button className="secondary-button" type="button" onClick={() => void deleteReceiptHistory(item.job_id).then(() => setHistory((items) => items.filter((x) => x.job_id !== item.job_id)))}>删除</button></td></tr>)}</tbody></table></div>}</div>
    </section>
  );
}
