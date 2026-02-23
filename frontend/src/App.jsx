import { useMemo, useState } from "react";
import axios from "axios";
import jsPDF from "jspdf";

import UploadZone from "./components/UploadZone";
import ResultsPanel from "./components/ResultsPanel";

function resolveApiBase() {
  const raw = String(import.meta.env.VITE_API_BASE || "").trim();
  const cleaned = raw.split("#")[0].trim();
  if (!cleaned) {
    return import.meta.env.DEV ? "http://localhost:8000/api" : "";
  }
  if (/^https?:\/\//i.test(cleaned)) {
    try {
      const parsed = new URL(cleaned);
      return parsed.toString().replace(/\/$/, "");
    } catch {
      return "";
    }
  }
  return cleaned.startsWith("/") ? cleaned.replace(/\/$/, "") : "";
}

const API_BASE = resolveApiBase();
const STAGES = ["ingestion", "structural", "lexical", "ocr", "semantic", "risk", "report"];

function downloadBlob(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function App() {
  const [inputFiles, setInputFiles] = useState([]);
  const [outputFiles, setOutputFiles] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [jobId, setJobId] = useState("");
  const [stageProgress, setStageProgress] = useState(
    Object.fromEntries(STAGES.map((s) => [s, 0]))
  );

  const canRun = inputFiles.length > 0 && outputFiles.length > 0 && !loading;
  const overallProgress = useMemo(() => {
    const values = Object.values(stageProgress);
    if (!values.length) return 0;
    return Math.round(values.reduce((a, b) => a + b, 0) / values.length);
  }, [stageProgress]);

  const resetAll = () => {
    if (loading) return;
    setInputFiles([]);
    setOutputFiles([]);
    setResult(null);
    setError("");
    setJobId("");
    setStageProgress(Object.fromEntries(STAGES.map((s) => [s, 0])));
  };

  const pollJob = async (id) => {
    const start = Date.now();
    while (Date.now() - start < 1000 * 60 * 8) {
      const response = await axios.get(`${API_BASE}/compare/jobs/${id}`);
      const payload = response.data;
      if (payload.stage_progress) setStageProgress(payload.stage_progress);
      if (payload.status === "completed") return payload.result;
      if (payload.status === "failed") throw new Error(payload.error || "Comparison failed.");
      await new Promise((resolve) => setTimeout(resolve, 1200));
    }
    throw new Error("Comparison timed out. Try reducing file count/size.");
  };

  const runComparison = async () => {
    if (!API_BASE) {
      setError(
        "Invalid or missing VITE_API_BASE. Set it to a full URL like https://your-backend-host/api and redeploy."
      );
      return;
    }
    setLoading(true);
    setResult(null);
    setError("");
    setStageProgress(Object.fromEntries(STAGES.map((s) => [s, 0])));
    try {
      const form = new FormData();
      inputFiles.forEach((f) => form.append("input_files", f));
      outputFiles.forEach((f) => form.append("output_files", f));
      const create = await axios.post(`${API_BASE}/compare/jobs`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setJobId(create.data.job_id);
      const finalResult = await pollJob(create.data.job_id);
      setResult(finalResult);
      if (finalResult?.stage_progress) setStageProgress(finalResult.stage_progress);
    } catch (err) {
      const isNetwork = err?.code === "ERR_NETWORK" || /network/i.test(err?.message || "");
      if (isNetwork) {
        setError(
          "Network error: backend API is unreachable. Configure VITE_API_BASE to your deployed backend URL and redeploy."
        );
      } else {
        setError(err?.response?.data?.detail || err.message || "Comparison failed.");
      }
    } finally {
      setLoading(false);
    }
  };

  const exportJson = () => {
    if (!result) return;
    downloadBlob("comparison-report.json", JSON.stringify(result, null, 2), "application/json");
  };

  const exportAuditLog = () => {
    if (!result) return;
    downloadBlob("audit-log.txt", (result.audit_log || []).join("\n"), "text/plain");
  };

  const exportPdf = () => {
    if (!result) return;
    const doc = new jsPDF({ unit: "pt", format: "a4" });
    const left = 40;
    const width = 515;
    let y = 48;

    const ensure = (height) => {
      if (y + height <= 800) return;
      doc.addPage();
      y = 42;
    };

    doc.setFillColor(12, 65, 97);
    doc.rect(0, 0, 595, 95, "F");
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(20);
    doc.text("AI Document Intelligence Report", left, 40);
    doc.setFontSize(11);
    doc.text(`Job ID: ${jobId || "N/A"}`, left, 60);
    doc.text(`Generated: ${new Date().toLocaleString()}`, left, 76);

    y = 118;
    doc.setTextColor(23, 33, 43);
    doc.setFontSize(13);
    doc.text("Executive Scores", left, y);
    y += 14;
    doc.setFillColor(241, 246, 252);
    doc.roundedRect(left, y, width, 88, 8, 8, "F");
    y += 20;
    doc.setFontSize(11);
    doc.text(`Overall Similarity: ${result.overall_similarity_score}%`, left + 12, y);
    y += 16;
    doc.text(`Structural Similarity: ${result.structural_similarity}%`, left + 12, y);
    y += 16;
    doc.text(`Semantic Similarity: ${result.semantic_similarity}%`, left + 12, y);
    y += 16;
    doc.text(`Risk Assessment: ${result.risk_assessment}`, left + 12, y);
    y += 24;

    const summaryLines = doc.splitTextToSize(result.summary_explanation || "", width);
    doc.setFontSize(11);
    doc.text(summaryLines, left, y);
    y += summaryLines.length * 14 + 10;

    doc.setFontSize(13);
    doc.text("Critical Changes", left, y);
    y += 12;
    const critical = result.critical_changes?.length ? result.critical_changes : ["No critical changes highlighted."];
    critical.forEach((item) => {
      const lines = doc.splitTextToSize(`- ${item}`, width);
      ensure(lines.length * 14 + 8);
      doc.setFontSize(10);
      doc.text(lines, left, y);
      y += lines.length * 14 + 2;
    });
    y += 8;

    doc.setFontSize(13);
    doc.text("Detailed Findings", left, y);
    y += 12;
    (result.mismatches || []).slice(0, 180).forEach((m, idx) => {
      const block = [
        `${idx + 1}. [${m.layer.toUpperCase()}][${m.risk_level}] ${m.change_type}`,
        `Input: ${m.input_text || "(empty)"}`,
        `Output: ${m.output_text || "(empty)"}`,
        `Location: ${m.location.file} / page ${m.location.page} / paragraph ${m.location.paragraph}`,
        `Confidence: ${(m.confidence_score * 100).toFixed(1)}%`,
        `Context: ${m.context_window || "N/A"}`,
      ];
      const wrapped = block.map((line) => doc.splitTextToSize(line, width - 16));
      const blockHeight = wrapped.reduce((acc, lines) => acc + lines.length * 12, 0) + 18;
      ensure(blockHeight + 10);
      doc.setDrawColor(208, 218, 230);
      doc.setFillColor(250, 252, 255);
      doc.roundedRect(left, y, width, blockHeight, 6, 6, "FD");
      y += 14;
      wrapped.forEach((lines) => {
        doc.setFontSize(9);
        doc.text(lines, left + 8, y);
        y += lines.length * 12;
      });
      y += 8;
    });

    doc.save("ai-document-comparison-report.pdf");
  };

  return (
    <main className="mx-auto max-w-7xl p-6 md:p-10">
      <header className="mb-8">
        <h1 className="font-display text-3xl font-bold text-slate-900 md:text-4xl">
          Enterprise AI Document Intelligence
        </h1>
        <p className="mt-2 max-w-4xl text-slate-600">
          Multi-layer analysis engine compares unified Input vs unified Output using structural, lexical, OCR, semantic, and numeric intelligence.
        </p>
      </header>

      <section className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <UploadZone title="Input Files" files={inputFiles} onFilesChange={setInputFiles} />
        <UploadZone title="Output Files" files={outputFiles} onFilesChange={setOutputFiles} />
      </section>

      <section className="card mt-6 p-5">
        <div className="flex flex-wrap items-center gap-3">
          <button
            className="rounded-lg bg-cyan-800 px-5 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-400"
            onClick={runComparison}
            disabled={!canRun}
          >
            {loading ? "Running AI Analysis..." : "Start Comparison"}
          </button>
          <button
            className="rounded-lg border border-cyan-800 px-5 py-2 font-semibold text-cyan-900 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={exportPdf}
            disabled={!result}
          >
            Export PDF
          </button>
          <button
            className="rounded-lg border border-slate-400 px-5 py-2 font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={exportJson}
            disabled={!result}
          >
            Export JSON
          </button>
          <button
            className="rounded-lg border border-slate-400 px-5 py-2 font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={exportAuditLog}
            disabled={!result}
          >
            Export Audit Log
          </button>
          <button
            className="rounded-lg border border-red-300 px-5 py-2 font-semibold text-red-700 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={resetAll}
            disabled={loading}
          >
            Refresh / New Operation
          </button>
        </div>

        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
          <div className="flex items-center justify-between text-sm">
            <p className="font-semibold text-slate-700">AI Analysis Progress</p>
            <p className="text-slate-600">{overallProgress}%</p>
          </div>
          <div className="mt-2 h-3 overflow-hidden rounded-full bg-slate-200">
            <div className="h-full bg-cyan-700 transition-all" style={{ width: `${overallProgress}%` }} />
          </div>
          <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-4">
            {STAGES.map((stage) => (
              <div key={stage} className="rounded border border-slate-200 bg-white p-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{stage}</p>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-200">
                  <div className="h-full bg-cyan-600 transition-all" style={{ width: `${stageProgress[stage] || 0}%` }} />
                </div>
                <p className="mt-1 text-xs text-slate-600">{stageProgress[stage] || 0}%</p>
              </div>
            ))}
          </div>
          {jobId && <p className="mt-3 text-xs text-slate-500">Active Job ID: {jobId}</p>}
          {error && <p className="mt-3 rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}
        </div>
      </section>

      {result && (
        <section className="card mt-6 p-5">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="rounded border border-slate-200 bg-white p-3">
              <p className="text-xs text-slate-500">Overall Similarity</p>
              <p className="text-xl font-bold text-slate-900">{result.overall_similarity_score}%</p>
            </div>
            <div className="rounded border border-slate-200 bg-white p-3">
              <p className="text-xs text-slate-500">Structural</p>
              <p className="text-xl font-bold text-slate-900">{result.structural_similarity}%</p>
            </div>
            <div className="rounded border border-slate-200 bg-white p-3">
              <p className="text-xs text-slate-500">Semantic</p>
              <p className="text-xl font-bold text-slate-900">{result.semantic_similarity}%</p>
            </div>
            <div className="rounded border border-slate-200 bg-white p-3">
              <p className="text-xs text-slate-500">Total Findings</p>
              <p className="text-xl font-bold text-slate-900">{(result.mismatches || []).length}</p>
            </div>
          </div>
        </section>
      )}

      <ResultsPanel result={result} />
    </main>
  );
}
