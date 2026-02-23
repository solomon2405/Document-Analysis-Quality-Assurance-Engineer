import { useMemo, useState } from "react";

const layerColors = {
  lexical: "bg-amber-100 text-amber-800",
  semantic: "bg-blue-100 text-blue-800",
  structural: "bg-purple-100 text-purple-800",
  numeric: "bg-red-100 text-red-800",
  ocr: "bg-emerald-100 text-emerald-800",
};

const riskColors = {
  Low: "bg-emerald-100 text-emerald-800",
  Medium: "bg-amber-100 text-amber-800",
  High: "bg-red-100 text-red-800",
};

export default function ResultsPanel({ result }) {
  const [riskFilter, setRiskFilter] = useState("All");
  const [layerFilter, setLayerFilter] = useState("All");
  const [selected, setSelected] = useState(null);

  const filtered = useMemo(() => {
    if (!result) return [];
    return result.mismatches.filter((m) => {
      const riskMatch = riskFilter === "All" || m.risk_level === riskFilter;
      const layerMatch = layerFilter === "All" || m.layer === layerFilter;
      return riskMatch && layerMatch;
    });
  }, [result, riskFilter, layerFilter]);

  if (!result) return null;

  return (
    <section className="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-3">
      <div className="card p-5 xl:col-span-1">
        <h3 className="font-display text-lg font-semibold">Risk Panel</h3>
        <div className={`mt-3 inline-block rounded px-3 py-1 text-sm font-semibold ${riskColors[result.risk_assessment] || "bg-slate-100 text-slate-700"}`}>
          {result.risk_assessment} Risk
        </div>
        <p className="mt-3 text-sm text-slate-700">{result.summary_explanation}</p>
        <div className="mt-4 space-y-2">
          {(result.critical_changes || []).slice(0, 8).map((item, idx) => (
            <p key={`critical-${idx}`} className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-800">
              {item}
            </p>
          ))}
          {(!result.critical_changes || result.critical_changes.length === 0) && (
            <p className="rounded border border-slate-200 bg-slate-50 p-2 text-xs text-slate-500">No critical changes flagged.</p>
          )}
        </div>
      </div>

      <div className="card p-5 xl:col-span-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-display text-lg font-semibold">Change Explorer</h3>
          <div className="flex flex-wrap gap-2">
            <select
              className="rounded border border-slate-300 px-2 py-1 text-sm"
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value)}
            >
              <option>All</option>
              <option>Low</option>
              <option>Medium</option>
              <option>High</option>
            </select>
            <select
              className="rounded border border-slate-300 px-2 py-1 text-sm"
              value={layerFilter}
              onChange={(e) => setLayerFilter(e.target.value)}
            >
              <option>All</option>
              <option>lexical</option>
              <option>semantic</option>
              <option>structural</option>
              <option>numeric</option>
              <option>ocr</option>
            </select>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="max-h-[28rem] overflow-auto rounded-lg border border-slate-200 bg-white p-3">
            {filtered.length === 0 && <p className="text-sm text-slate-500">No findings for selected filter.</p>}
            {filtered.map((m, idx) => (
              <button
                key={`${m.layer}-${idx}`}
                className="mb-2 block w-full rounded-lg border border-slate-200 p-2 text-left hover:bg-slate-50"
                onClick={() => setSelected(m)}
                type="button"
              >
                <div className="flex items-center gap-2">
                  <span className={`rounded px-2 py-0.5 text-xs font-semibold ${layerColors[m.layer] || "bg-slate-100 text-slate-700"}`}>
                    {m.layer}
                  </span>
                  <span className={`rounded px-2 py-0.5 text-xs font-semibold ${riskColors[m.risk_level] || "bg-slate-100 text-slate-700"}`}>
                    {m.risk_level}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-700">{m.change_type}</p>
                <p className="mt-1 truncate text-sm font-medium text-slate-900">
                  {m.input_text || "(empty)"} {m.output_text ? `-> ${m.output_text}` : ""}
                </p>
              </button>
            ))}
          </div>

          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Side-by-Side Viewer</p>
            {!selected && <p className="mt-3 text-sm text-slate-500">Select a finding to inspect detail.</p>}
            {selected && (
              <div className="mt-2 space-y-3 text-sm">
                <p>
                  <span className="font-semibold">Layer:</span> {selected.layer}
                </p>
                <p>
                  <span className="font-semibold">Type:</span> {selected.change_type}
                </p>
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  <div className="rounded border border-slate-200 bg-white p-2">
                    <p className="text-xs font-semibold text-slate-500">Input</p>
                    <p className="mt-1 text-slate-900">{selected.input_text || "(empty)"}</p>
                  </div>
                  <div className="rounded border border-slate-200 bg-white p-2">
                    <p className="text-xs font-semibold text-slate-500">Output</p>
                    <p className="mt-1 text-slate-900">{selected.output_text || "(empty)"}</p>
                  </div>
                </div>
                <p>
                  <span className="font-semibold">Location:</span> {selected.location.file} | page {selected.location.page} | paragraph {selected.location.paragraph}
                </p>
                <p>
                  <span className="font-semibold">Context:</span> {selected.context_window}
                </p>
                <p>
                  <span className="font-semibold">Confidence:</span> {(selected.confidence_score * 100).toFixed(1)}%
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
