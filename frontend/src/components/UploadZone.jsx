import { useMemo, useState } from "react";

const ACCEPT = ".docx,.pdf,.txt,.xlsx,.png,.jpg,.jpeg";
const ext = (name) => {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "unknown";
};

export default function UploadZone({ title, files, onFilesChange }) {
  const [isActive, setIsActive] = useState(false);

  const fileNames = useMemo(() => files.map((f) => f.name), [files]);
  const typeCounts = useMemo(() => {
    const counters = {};
    files.forEach((f) => {
      const key = ext(f.name);
      counters[key] = (counters[key] || 0) + 1;
    });
    return counters;
  }, [files]);

  const addFiles = (incoming) => {
    const next = [...files, ...Array.from(incoming)];
    onFilesChange(next);
  };

  const removeFileAt = (indexToRemove) => {
    onFilesChange(files.filter((_, index) => index !== indexToRemove));
  };

  const clearFiles = () => {
    onFilesChange([]);
  };

  return (
    <div className="card p-5">
      <h2 className="font-display text-lg font-semibold">{title}</h2>
      <label
        className={`mt-4 block cursor-pointer rounded-xl border-2 border-dashed p-6 text-center transition ${
          isActive ? "border-cyan-700 bg-cyan-50" : "border-slate-300 bg-slate-50"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setIsActive(true);
        }}
        onDragLeave={() => setIsActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsActive(false);
          addFiles(e.dataTransfer.files);
        }}
      >
        <input
          type="file"
          className="hidden"
          accept={ACCEPT}
          multiple
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <p className="font-medium text-slate-700">Drag and drop or click to upload</p>
        <p className="mt-2 text-sm text-slate-500">Supports DOCX, PDF, TXT, XLSX, PNG, JPG, JPEG</p>
      </label>

      <div className="mt-4 max-h-40 overflow-auto rounded-lg border border-slate-200 bg-white p-3 text-sm">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Selected files: {fileNames.length}
          </p>
          <button
            type="button"
            className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={clearFiles}
            disabled={fileNames.length === 0}
          >
            Cancel All
          </button>
        </div>
        {fileNames.length === 0 && <p className="text-slate-400">No files selected</p>}
        {fileNames.map((name, idx) => (
          <div
            key={`${title}-${name}-${idx}`}
            className="flex items-center justify-between gap-3 py-1 text-slate-700"
          >
            <span className="truncate">{name}</span>
            <button
              type="button"
              className="rounded border border-red-200 px-2 py-0.5 text-xs font-medium text-red-700 hover:bg-red-50"
              onClick={() => removeFileAt(idx)}
            >
              Cancel
            </button>
          </div>
        ))}
      </div>

      <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">File Classification</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {Object.keys(typeCounts).length === 0 && (
            <span className="text-sm text-slate-400">No file types detected</span>
          )}
          {Object.entries(typeCounts).map(([type, count]) => (
            <span
              key={`${title}-${type}`}
              className="rounded-full bg-slate-200 px-2 py-1 text-xs font-semibold text-slate-700"
            >
              {type}: {count}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
