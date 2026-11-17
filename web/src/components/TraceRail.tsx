// The signature element (spec §16.5). A vertical spine of pipeline phases:
// completed nodes filled, the active node pulses in accent, pending nodes are
// outlined, and a failed run marks the active node in the critical severity hue.
//
// Steps and the phase→step / agent maps are NOT hardcoded here — they come from
// the backend (`GET /pipeline/trace-rail`, see src/webapi/trace_rail.py). Nested
// agent rows under a step surface vuln/exploit progress without digging logs.

export interface RailPhase {
  key: string;
  label: string;
}

export type AgentRailStatus = "pending" | "active" | "done" | "failed";

export function TraceRail({
  steps,
  activeKey,
  status,
  selected,
  onSelect,
  agentsByStep = {},
  agentStatus = {},
  activeAgent = null,
}: {
  steps: RailPhase[];
  activeKey: string | null;
  status: string;
  selected?: string | null;
  onSelect?: (key: string | null) => void;
  agentsByStep?: Record<string, RailPhase[]>;
  agentStatus?: Record<string, AgentRailStatus>;
  activeAgent?: string | null;
}) {
  const terminalDone = status === "succeeded";
  let activeIdx = steps.findIndex((p) => p.key === activeKey);
  if (terminalDone) activeIdx = steps.length; // all complete
  const failed = status === "failed";

  return (
    <ol className="relative flex flex-col gap-1 pl-1">
      {steps.map((p, i) => {
        const done = i < activeIdx;
        const active = i === activeIdx && !terminalDone;
        const isFailedNode = active && failed;
        const isSelected = selected === p.key;
        const agents = agentsByStep[p.key] ?? [];
        const showAgents = agents.length > 0 && (done || active || terminalDone || selected === p.key
          || agents.some((a) => selected === a.key || agentStatus[a.key]));

        return (
          <li key={p.key} className="relative">
            <button
              type="button"
              onClick={() => onSelect?.(isSelected ? null : p.key)}
              className={[
                "flex w-full items-center gap-3 rounded-md px-2 py-2 text-left transition",
                isSelected ? "bg-canvas" : "hover:bg-canvas",
              ].join(" ")}
              title="Show logs for this step"
            >
              <span className="relative inline-flex h-4 w-4 items-center justify-center">
                {i < steps.length - 1 && (
                  <span
                    className={`absolute left-[7px] top-5 h-5 w-px ${done ? "bg-accent" : "bg-line"}`}
                  />
                )}
                {active && !failed && (
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-50" />
                )}
                <span
                  className={[
                    "relative h-3.5 w-3.5 rounded-full border",
                    isFailedNode
                      ? "border-severity-critical bg-severity-critical"
                      : done || active
                        ? "border-accent bg-accent"
                        : "border-line bg-surface",
                  ].join(" ")}
                />
              </span>
              <span
                className={[
                  "text-sm",
                  isSelected ? "text-accent font-medium" : done || active ? "text-ink font-medium" : "text-slate",
                ].join(" ")}
              >
                {p.label}
              </span>
            </button>

            {showAgents && (
              <ul className="ml-5 mt-0.5 space-y-0.5 border-l border-line pl-3">
                {agents.map((a) => {
                  const st: AgentRailStatus =
                    agentStatus[a.key]
                    ?? (terminalDone ? "done" : "pending");
                  const agentActive = activeAgent === a.key || st === "active";
                  const agentSelected = selected === a.key;
                  const agentFailed = st === "failed";
                  const agentDone = st === "done" || (terminalDone && st !== "failed");
                  return (
                    <li key={a.key}>
                      <button
                        type="button"
                        onClick={() => onSelect?.(agentSelected ? null : a.key)}
                        className={[
                          "flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left transition",
                          agentSelected ? "bg-canvas" : "hover:bg-canvas",
                        ].join(" ")}
                        title={`Show logs for ${a.key}`}
                      >
                        <span className="relative inline-flex h-2.5 w-2.5 items-center justify-center">
                          {agentActive && !agentFailed && (
                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-50" />
                          )}
                          <span
                            className={[
                              "relative h-2 w-2 rounded-full border",
                              agentFailed
                                ? "border-severity-critical bg-severity-critical"
                                : agentDone || agentActive
                                  ? "border-accent bg-accent"
                                  : "border-line bg-surface",
                            ].join(" ")}
                          />
                        </span>
                        <span
                          className={[
                            "truncate text-[11px] leading-tight",
                            agentSelected
                              ? "font-medium text-accent"
                              : agentDone || agentActive
                                ? "text-ink"
                                : "text-slate",
                          ].join(" ")}
                        >
                          {a.label}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </li>
        );
      })}
    </ol>
  );
}
