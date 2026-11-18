const CONFIG_FIELDS = [
  { key: "executor", label: "Executor (claude / codex / opencode)" },
  { key: "model_small", label: "Model — small" },
  { key: "model_medium", label: "Model — medium" },
  { key: "model_large", label: "Model — large" },
  {
    key: "max_concurrent_pipelines",
    label: "Max concurrent vuln pipelines",
    placeholder: "8 (default); use 1 to serialize",
  },
] as const;

export type PipelineConfigValues = Record<string, string>;

export function PipelineConfigFields({
  values,
  onChange,
  title = "Pipeline config",
  helper,
  idPrefix = "cfg",
}: {
  values: PipelineConfigValues;
  onChange: (next: PipelineConfigValues) => void;
  title?: string;
  helper?: string;
  idPrefix?: string;
}) {
  return (
    <section className="mb-6">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate">
        {title}
      </h3>
      {helper && <p className="mb-3 text-xs text-slate">{helper}</p>}
      {CONFIG_FIELDS.map((f) => (
        <div key={f.key} className="mb-3">
          <label htmlFor={`${idPrefix}-${f.key}`} className="mb-1 block text-sm text-slate">
            {f.label}
          </label>
          <input
            id={`${idPrefix}-${f.key}`}
            className="field"
            placeholder={"placeholder" in f ? f.placeholder : "(use default)"}
            value={values[f.key] ?? ""}
            onChange={(e) => onChange({ ...values, [f.key]: e.target.value })}
          />
        </div>
      ))}
    </section>
  );
}

export function cleanPipelineConfig(o: PipelineConfigValues): Record<string, string> {
  return Object.fromEntries(Object.entries(o).filter(([, v]) => v.trim() !== ""));
}
