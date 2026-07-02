"use client";
import { useState } from "react";
import Link from "next/link";
import { useCoachSummary, useCoachHealth, useCoachFocus, useCoachProblems } from "@/hooks/useCoach";
import { Card } from "@/components/primitives/Card";

function RiskBadge({ risk }: { risk: string }) {
  const colors: Record<string, string> = {
    low: "text-[var(--color-neon-green)] border-[var(--color-neon-green)]",
    moderate: "text-[var(--color-neon-yellow)] border-[var(--color-neon-yellow)]",
    high: "text-[var(--color-neon-red)] border-[var(--color-neon-red)]",
    unknown: "text-[var(--color-text-3)] border-[var(--color-border)]",
  };
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.2em] ${colors[risk] ?? colors.unknown}`}
    >
      {risk}
    </span>
  );
}

function ModeBadge({ mode }: { mode: "exact" | "fallback" }) {
  const exact = mode === "exact";
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.18em] ${
        exact
          ? "border-[var(--color-neon-cyan)] text-[var(--color-neon-cyan)]"
          : "border-[var(--color-neon-yellow)] text-[var(--color-neon-yellow)]"
      }`}
      title={exact ? "Exact research profile match" : "Fallback coaching from platform activity and research benchmarks"}
    >
      {exact ? "Exact" : "Fallback"}
    </span>
  );
}

const BREAKTHROUGH_PROB: Record<string, number> = {
  low: 70,
  moderate: 45,
  high: 20,
  unknown: 40,
};

export function CoachWidget({ cfHandle }: { cfHandle: string | null }) {
  const { data, isLoading } = useCoachSummary(cfHandle);
  const { data: health } = useCoachHealth();
  const { data: focusData } = useCoachFocus(cfHandle);
  const [showProblems, setShowProblems] = useState(false);
  const { data: problemsData } = useCoachProblems(showProblems ? cfHandle : null, 2);

  if (!cfHandle) {
    return (
      <Card className="border-[var(--color-border-hot)] bg-[var(--color-neon-pink)]/[0.08]">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="mb-1 font-mono text-[11px] tracking-[0.25em] text-[var(--color-neon-pink)]">
              // CODEFORCES HANDLE REQUIRED
            </div>
            <div className="text-sm text-[var(--color-text-1)]">
              Link your handle to get a practice lane built around Codeforces tags and rating growth.
            </div>
          </div>
          <Link
            href="/profile/settings"
            className="shrink-0 font-mono text-[12px] uppercase tracking-[0.2em] text-[var(--color-neon-cyan)]"
          >
            {"Link now ->"}
          </Link>
        </div>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card className="flex items-center gap-4">
        <div className="flex-1 space-y-2">
          <div className="h-3 w-20 animate-pulse rounded bg-[var(--color-border)]" />
          <div className="h-4 w-40 animate-pulse rounded bg-[var(--color-border)]" />
        </div>
        <div className="flex items-center gap-3">
          <div className="h-5 w-16 animate-pulse rounded bg-[var(--color-border)]" />
          <div className="h-5 w-14 animate-pulse rounded bg-[var(--color-border)]" />
        </div>
      </Card>
    );
  }

  if (!data || !data.found) {
    const unavailableText =
      health && !health.database
        ? health.status === "unconfigured"
          ? "Coach analytics are not configured on this deployment."
          : "Coach analytics are temporarily unreachable."
        : "Coach data unavailable for this handle.";
    return (
      <Card>
        <div className="font-mono text-[10px] tracking-[0.3em] text-[var(--color-neon-pink)]">
          // COACH
        </div>
        <div className="mt-0.5 font-mono text-xs text-[var(--color-text-3)]">
          {unavailableText}
        </div>
      </Card>
    );
  }

  const focus = data.recommended_focus[0];
  const milestone = data.next_milestone;

  return (
    <div className="space-y-2">
      <Card className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2 shrink-0">
          <div className="font-mono text-[10px] tracking-[0.3em] text-[var(--color-neon-pink)]">
            // COACH
          </div>
          <ModeBadge mode={data.coach_mode} />
          {health && (
            <span
              className={`inline-block h-1.5 w-1.5 rounded-full ${
                health.database ? "bg-[var(--color-neon-green)]" : "bg-[var(--color-neon-red)]"
              }`}
              title={health.database ? "Research database connected" : "Research database unavailable"}
            />
          )}
        </div>

        <div className="flex flex-wrap items-center gap-4 sm:gap-6">
          {milestone && milestone.gap > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-[var(--color-text-3)]">Milestone:</span>
              <span className="text-[11px] font-semibold text-[var(--color-neon-cyan)]">{milestone.label}</span>
              <span className="text-[10px] text-[var(--color-text-3)]">({milestone.gap} pts)</span>
              <span
                className="shrink-0 font-mono text-[10px] text-[var(--color-neon-green)]"
                title="Estimated chance of reaching next milestone based on skill diversity"
              >
                ~{BREAKTHROUGH_PROB[data.plateau_risk.risk] ?? 40}%
              </span>
            </div>
          )}

          {focus && (
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-[var(--color-text-3)]">Focus:</span>
              <span className="text-[11px] font-semibold text-[var(--color-neon-green)]">{focus.tag}</span>
              <span className="text-[10px] text-[var(--color-text-3)]">+{focus.estimated_gain} rating</span>
            </div>
          )}

          {data.practice_strategy.target_tags.length > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-[var(--color-text-3)]">Lane:</span>
              <span className="text-[11px] font-semibold text-[var(--color-neon-cyan)]">
                {data.practice_strategy.target_tags.slice(0, 2).join(", ")}
              </span>
            </div>
          )}

          {focusData && focusData.focus_progress.length > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-[var(--color-text-3)]">Practiced:</span>
              <span className="text-[11px] font-semibold text-[var(--color-neon-yellow)]">
                {focusData.focus_progress.slice(0, 2).map((f) => f.tag).join(", ")}
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={() => setShowProblems((v) => !v)}
            className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-neon-cyan)] transition-opacity hover:opacity-70"
          >
            {showProblems ? "v Problems" : "> Problems"}
          </button>
          <RiskBadge risk={data.plateau_risk.risk} />
          <Link
            href="/profile"
            className="font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--color-neon-cyan)] transition-opacity hover:opacity-70"
          >
            {"Full analysis ->"}
          </Link>
        </div>
      </Card>

      <Card className="px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-3)]">
              {data.practice_strategy.headline}
            </div>
            <div className="mt-1 text-[12px] leading-5 text-[var(--color-text-2)]">
              {data.practice_strategy.summary}
            </div>
            <div className="mt-2 text-[11px] text-[var(--color-text-3)]">
              {data.elite_benchmark.insight}
            </div>
          </div>
          {data.performance_snapshot.recent_duel_count > 0 && (
            <div className="shrink-0 text-right font-mono text-[10px] text-[var(--color-text-3)]">
              <div>{Math.round((data.performance_snapshot.recent_win_rate ?? 0) * 100)}% win rate</div>
              <div>
                {data.performance_snapshot.recent_delta_sum >= 0 ? "+" : ""}
                {data.performance_snapshot.recent_delta_sum} recent elo
              </div>
            </div>
          )}
        </div>
        {data.elite_benchmark.target_tags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {data.elite_benchmark.target_tags.slice(0, 3).map((item) => (
              <span
                key={item.tag}
                className="rounded border border-[var(--color-border)] px-2 py-1 font-mono text-[10px] text-[var(--color-text-2)]"
              >
                {item.tag}
                {typeof item.gap === "number" && item.gap > 0 ? ` gap ${Math.round(item.gap * 100)}%` : ""}
              </span>
            ))}
          </div>
        )}
      </Card>

      {showProblems && problemsData && problemsData.problems.length > 0 && (
        <Card className="px-4 py-3">
          <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-3)]">
            Practice these because they fit your tag lane and rating window.
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {problemsData.problems.map((p) => (
              <a
                key={`${p.contest_id}${p.index}`}
                href={p.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 rounded border border-[var(--color-border)] px-2 py-1 font-mono text-[11px] transition-colors hover:border-[var(--color-neon-cyan)]"
              >
                <span className="text-[var(--color-neon-cyan)]">{p.rating}</span>
                <span className="max-w-[200px] truncate text-[var(--color-text-2)]">{p.name}</span>
                <span className="text-[10px] text-[var(--color-text-3)]">{p.solved_count} solves</span>
              </a>
            ))}
          </div>
        </Card>
      )}
      {showProblems && problemsData && problemsData.problems.length === 0 && (
        <Card className="px-4 py-2.5 font-mono text-xs text-[var(--color-text-3)]">
          No problems found for your focus area.
        </Card>
      )}
    </div>
  );
}
