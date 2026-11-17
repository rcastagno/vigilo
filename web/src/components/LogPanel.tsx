import { useMemo, type RefObject } from "react";

/** One renderable chunk of the Evidence / logs stream. */
export type LogChunk =
  | { kind: "text"; text: string }
  | { kind: "llm"; agent: string; turn: number; body: string; raw: string };

const LLM_RE =
  /^(\[[^\]]+\])\s+\[([\w-]+)\]\s+\[LLM\]\s+Turn\s+(\d+):\s*(.*)$/;

/** Undo common C/JSON-style escapes used when prompts/responses are flattened into a log line. */
export function unescapeLogText(s: string): string {
  let out = s;
  // Drop a single layer of surrounding quotes when the whole payload is quoted.
  if (
    (out.startsWith('"') && out.endsWith('"') && out.length >= 2) ||
    (out.startsWith("'") && out.endsWith("'") && out.length >= 2)
  ) {
    out = out.slice(1, -1);
  }
  return out.replace(
    /\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|[nrt"'\\/])/g,
    (_m, esc: string) => {
      switch (esc[0]) {
        case "n":
          return "\n";
        case "r":
          return "\r";
        case "t":
          return "\t";
        case '"':
          return '"';
        case "'":
          return "'";
        case "/":
          return "/";
        case "\\":
          return "\\";
        case "u":
          return String.fromCharCode(parseInt(esc.slice(1), 16));
        case "x":
          return String.fromCharCode(parseInt(esc.slice(1), 16));
        default:
          return _m;
      }
    },
  );
}

/** Split log lines into plain text runs and LLM turn blocks. */
export function parseLogChunks(lines: string[]): LogChunk[] {
  const chunks: LogChunk[] = [];
  let buf: string[] = [];

  const flush = () => {
    if (!buf.length) return;
    chunks.push({ kind: "text", text: buf.join("\n") });
    buf = [];
  };

  for (const ln of lines) {
    const m = ln.match(LLM_RE);
    if (m) {
      flush();
      chunks.push({
        kind: "llm",
        agent: m[2],
        turn: Number(m[3]),
        body: unescapeLogText(m[4]),
        raw: ln,
      });
    } else {
      buf.push(ln);
    }
  }
  flush();
  return chunks;
}

function SoftWrapToggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-slate">
      <input
        type="checkbox"
        className="rounded border-line"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      Soft wraps
    </label>
  );
}

function FormatToggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-slate">
      <input
        type="checkbox"
        className="rounded border-line"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      Format prompts / responses
    </label>
  );
}

export function LogPanel({
  lines,
  emptyMessage,
  softWrap,
  onSoftWrapChange,
  formatLlm,
  onFormatLlmChange,
  scrollRef,
}: {
  lines: string[];
  emptyMessage: string;
  softWrap: boolean;
  onSoftWrapChange: (v: boolean) => void;
  formatLlm: boolean;
  onFormatLlmChange: (v: boolean) => void;
  scrollRef: RefObject<HTMLDivElement>;
}) {
  const chunks = useMemo(
    () => (formatLlm ? parseLogChunks(lines) : null),
    [lines, formatLlm],
  );

  const preClass = [
    "mono text-xs leading-relaxed text-ink",
    softWrap ? "whitespace-pre-wrap break-all" : "whitespace-pre",
  ].join(" ");

  return (
    <>
      <div className="flex flex-wrap items-center justify-end gap-3 border-b border-line px-4 py-2">
        <SoftWrapToggle checked={softWrap} onChange={onSoftWrapChange} />
        <FormatToggle checked={formatLlm} onChange={onFormatLlmChange} />
      </div>
      <div
        ref={scrollRef}
        className={[
          "min-h-0 flex-1 overflow-auto bg-ink/[0.015] p-4",
          softWrap ? "" : "overflow-x-auto",
        ].join(" ")}
      >
        {!lines.length ? (
          <pre className={preClass}>{emptyMessage}</pre>
        ) : !formatLlm || !chunks ? (
          <pre className={preClass}>{lines.join("\n")}</pre>
        ) : (
          <div className="space-y-3">
            {chunks.map((c, i) =>
              c.kind === "text" ? (
                <pre key={i} className={preClass}>
                  {c.text}
                </pre>
              ) : (
                <div
                  key={i}
                  className="overflow-hidden rounded-md border border-line bg-surface"
                >
                  <div className="flex items-center justify-between border-b border-line bg-canvas px-3 py-1.5">
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-slate">
                      Response · {c.agent} · turn {c.turn}
                    </span>
                  </div>
                  <pre
                    className={[
                      "mono p-3 text-xs leading-relaxed text-ink",
                      softWrap
                        ? "whitespace-pre-wrap break-words"
                        : "overflow-x-auto whitespace-pre",
                    ].join(" ")}
                  >
                    {c.body}
                  </pre>
                </div>
              ),
            )}
          </div>
        )}
      </div>
    </>
  );
}
