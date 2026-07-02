"use client";
import { useState, useMemo } from "react";
import { Card } from "@/components/primitives/Card";
import { useCoachSummary, useCoachProblems, useCoachHealth } from "@/hooks/useCoach";
import type { User } from "@/types/user";

function SkillBar({ tag, score }: { tag: string; score: number }) {
  const pct = Math.round(score * 100);
  return (
    <div className="flex items-center gap-2">
      <span className="w-40 shrink-0 truncate font-mono text-[11px] text-[var(--color-text-3)]">
        {tag}
      </span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--color-border)]">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${pct}%`,
            background:
              pct >= 60
                ? "linear-gradient(90deg, var(--color-neon-cyan), var(--color-neon-green))"
                : pct >= 30
                  ? "linear-gradient(90deg, var(--color-neon-yellow), var(--color-neon-orange))"
                  : "linear-gradient(90deg, var(--color-neon-pink), var(--color-neon-red))",
          }}
        />
      </div>
      <span className="w-8 text-right font-mono text-[10px] text-[var(--color-text-3)]">
        {pct}%
      </span>
    </div>
  );
}

function RiskBadge({ risk }: { risk: string }) {
  const colors: Record<string, string> = {
    low: "text-[var(--color-neon-green)] border-[var(--color-neon-green)]",
    moderate: "text-[var(--color-neon-yellow)] border-[var(--color-neon-yellow)]",
    high: "text-[var(--color-neon-red)] border-[var(--color-neon-red)]",
    unknown: "text-[var(--color-text-3)] border-[var(--color-border)]",
  };
  return (
    <span
      className={`inline-block rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.2em] ${colors[risk] ?? colors.unknown}`}
    >
      {risk}
    </span>
  );
}

function ModeBadge({ mode }: { mode: "exact" | "fallback" }) {
  const exact = mode === "exact";
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.18em] ${
        exact
          ? "border-[var(--color-neon-cyan)] text-[var(--color-neon-cyan)]"
          : "border-[var(--color-neon-yellow)] text-[var(--color-neon-yellow)]"
      }`}
    >
      {exact ? "Exact" : "Fallback"}
    </span>
  );
}

export function CoachCard({ user }: { user: User }) {
  const cfHandle = user.cf_handle ?? null;
  const { data, isLoading, error } = useCoachSummary(cfHandle);
  const { data: health } = useCoachHealth();

  if (!cfHandle) {
    return (
      <Card>
        <div className="mb-1 font-mono text-[11px] tracking-[0.3em] text-[var(--color-neon-pink)]">
          // COACH
        </div>
        <div className="py-6 text-center font-mono text-xs text-[var(--color-text-3)]">
          Link a Codeforces handle in Settings to unlock personalized coaching.
        </div>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card>
        <div className="mb-1 font-mono text-[11px] tracking-[0.3em] text-[var(--color-neon-pink)]">
          // COACH
        </div>
        <div className="py-6 text-center font-mono text-xs text-[var(--color-text-3)]">
          Loading coach analysis...
        </div>
      </Card>
    );
  }

  if (error || !data || !data.found) {
    const unavailableText =
      health && !health.database
        ? health.status === "unconfigured"
          ? "Coach analytics are not configured on this deployment yet."
          : "Coach analytics are temporarily unreachable."
        : "Coach data unavailable for this handle.";
    return (
      <Card>
        <div className="mb-1 font-mono text-[11px] tracking-[0.3em] text-[var(--color-neon-pink)]">
          // COACH
        </div>
        <div className="py-6 text-center font-mono text-xs text-[var(--color-text-3)]">
          {unavailableText}
        </div>
      </Card>
    );
  }

  return (
    <Card className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="font-mono text-[11px] tracking-[0.3em] text-[var(--color-neon-pink)]">
            // COACH
          </div>
          <ModeBadge mode={data.coach_mode} />
        </div>
        <div className="flex items-center gap-3">
          {data.cluster && (
            <span className="font-mono text-[10px] text-[var(--color-text-3)]">
              {data.cluster}
            </span>
          )}
          <RiskBadge risk={data.plateau_risk.risk} />
        </div>
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]/50 p-4">
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-3)]">
          {data.practice_strategy.headline}
        </div>
        <div className="mt-1 text-sm leading-6 text-[var(--color-text-2)]">
          {data.practice_strategy.summary}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {data.practice_strategy.target_tags.map((tag) => (
            <span
              key={tag}
              className="rounded border border-[var(--color-border)] px-2 py-1 font-mono text-[10px] text-[var(--color-neon-cyan)]"
            >
              {tag}
            </span>
          ))}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-[var(--color-border)] px-3 py-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-3)]">
            Coach mode
          </div>
          <div className="mt-1 text-sm text-[var(--color-text-1)]">
            {data.coach_mode === "exact" ? "Research DB profile matched" : "Platform signals + research benchmark"}
          </div>
        </div>
        <div className="rounded-lg border border-[var(--color-border)] px-3 py-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-3)]">
            Recent form
          </div>
          <div className="mt-1 text-sm text-[var(--color-text-1)]">
            {data.performance_snapshot.recent_duel_count > 0
              ? `${Math.round((data.performance_snapshot.recent_win_rate ?? 0) * 100)}% win rate`
              : "No duel history yet"}
          </div>
          {data.performance_snapshot.recent_duel_count > 0 && (
            <div className="font-mono text-[10px] text-[var(--color-text-3)]">
              {data.performance_snapshot.recent_delta_sum >= 0 ? "+" : ""}
              {data.performance_snapshot.recent_delta_sum} elo over last {data.performance_snapshot.recent_duel_count}
            </div>
          )}
        </div>
        <div className="rounded-lg border border-[var(--color-border)] px-3 py-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-3)]">
            Streak state
          </div>
          <div className="mt-1 text-sm text-[var(--color-text-1)]">
            {data.performance_snapshot.current_streak} active
          </div>
          <div className="font-mono text-[10px] text-[var(--color-text-3)]">
            Best {data.performance_snapshot.longest_streak}
          </div>
        </div>
      </div>

      {data.next_milestone && data.next_milestone.gap > 0 && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]/50 p-4">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-3)]">
            Next milestone
          </div>
          <div className="mt-1 font-mono text-lg text-[var(--color-neon-cyan)]">
            {data.next_milestone.label}
          </div>
          <div className="font-mono text-[11px] text-[var(--color-text-3)]">
            {data.next_milestone.gap} rating points away
          </div>
        </div>
      )}

      {data.trajectory_milestones.length >= 2 && (
        <RatingSparkline milestones={data.trajectory_milestones} />
      )}

      {data.elite_benchmark.target_tags.length > 0 && (
        <div>
          <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-3)]">
            What stronger players at your band do better
          </div>
          <div className="mb-2 text-[12px] leading-5 text-[var(--color-text-2)]">
            {data.elite_benchmark.insight}
          </div>
          <div className="space-y-1.5">
            {data.elite_benchmark.target_tags.slice(0, 4).map((item) => (
              <div key={item.tag} className="flex items-center justify-between font-mono text-[11px]">
                <span className="text-[var(--color-neon-yellow)]">{item.tag}</span>
                <span className="text-[var(--color-text-3)]">
                  {typeof item.gap === "number" && item.gap > 0 ? `gap ${Math.round(item.gap * 100)}%` : "on track"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.strong_skills.length > 0 && (
        <div>
          <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-3)]">
            Strong skills
          </div>
          <div className="space-y-1">
            {data.strong_skills.slice(0, 4).map((s) => (
              <SkillBar key={s.tag} tag={s.tag} score={s.score} />
            ))}
          </div>
        </div>
      )}

      {data.weak_skills.length > 0 && (
        <div>
          <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-3)]">
            Areas to improve
          </div>
          <div className="space-y-1">
            {data.weak_skills.slice(0, 4).map((s) => (
              <SkillBar key={s.tag} tag={s.tag} score={s.score} />
            ))}
          </div>
        </div>
      )}

      {data.recommended_focus.length > 0 && (
        <div>
          <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-3)]">
            Recommended focus
          </div>
          <div className="space-y-1">
            {data.recommended_focus.slice(0, 3).map((r) => (
              <div key={r.tag} className="flex items-center justify-between font-mono text-[12px]">
                <span className="text-[var(--color-neon-green)]">{r.tag}</span>
                <span className="text-[var(--color-text-3)]">
                  +{r.estimated_gain} rating
                  {typeof r.benchmark_gap === "number" && r.benchmark_gap > 0 ? ` | gap ${Math.round(r.benchmark_gap * 100)}%` : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <PracticeProblems cfHandle={cfHandle} />

      {data.learning_path.length > 0 && (
        <div>
          <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-3)]">
            Learning path
          </div>
          <div className="space-y-1">
            {data.learning_path.slice(0, 4).map((step) => (
              <div key={step.concept} className="flex items-center gap-3 font-mono text-[11px]">
                <span className="w-5 text-right text-[var(--color-neon-cyan)]">{step.order}.</span>
                <span className="flex-1 text-[var(--color-text-2)]">{step.concept}</span>
                {step.estimated_gain > 0 && (
                  <span className="text-[var(--color-neon-green)]">+{step.estimated_gain}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {data.peers.length > 0 && (
        <div>
          <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-3)]">
            Similar profile users
          </div>
          <div className="flex flex-wrap gap-2">
            {data.peers.map((p) => (
              <span
                key={p.handle}
                className="rounded border border-[var(--color-border)] px-2 py-1 font-mono text-[11px] text-[var(--color-text-2)]"
              >
                {p.handle}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="text-right font-mono text-[10px] text-[var(--color-text-3)]">
        Based on {data.sample_size.toLocaleString()} analyzed submissions
      </div>
    </Card>
  );
}

function RatingSparkline({ milestones }: { milestones: { achieved_at_rating: number }[] }) {
  const points = useMemo(() => {
    if (milestones.length < 2) return null;
    const ratings = milestones.map((m) => m.achieved_at_rating);
    const minR = Math.min(...ratings) - 50;
    const maxR = Math.max(...ratings) + 50;
    const range = maxR - minR || 1;
    const w = 200;
    const h = 40;
    return {
      path: ratings
        .map((r, i) => {
          const x = (i / (ratings.length - 1)) * w;
          const y = h - ((r - minR) / range) * h;
          return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join(" "),
      w,
      h,
    };
  }, [milestones]);

  if (!points) return null;

  const minR = Math.min(...milestones.map((m) => m.achieved_at_rating)) - 50;
  const maxR = Math.max(...milestones.map((m) => m.achieved_at_rating)) + 50;

  return (
    <div>
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-3)]">
        Rating trajectory
      </div>
      <svg viewBox={`0 0 ${points.w} ${points.h}`} className="h-auto w-full max-w-[200px]">
        <path
          d={points.path}
          fill="none"
          stroke="var(--color-neon-cyan)"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {milestones.map((m, i) => {
          const x = (i / (milestones.length - 1)) * points.w;
          const y = points.h - ((m.achieved_at_rating - minR) / (maxR - minR || 1)) * points.h;
          return <circle key={i} cx={x.toFixed(1)} cy={y.toFixed(1)} r="2" fill="var(--color-neon-cyan)" />;
        })}
      </svg>
    </div>
  );
}

function PracticeProblems({ cfHandle }: { cfHandle: string }) {
  const [showProblems, setShowProblems] = useState(false);
  const { data: problemsData, isLoading, error } = useCoachProblems(showProblems ? cfHandle : null);

  return (
    <div>
      <button
        onClick={() => setShowProblems((v) => !v)}
        className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-neon-cyan)] transition-opacity hover:opacity-70"
      >
        {showProblems ? "v Practice problems" : "> Practice problems"}
      </button>
      {showProblems && isLoading && (
        <div className="mt-2 font-mono text-xs text-[var(--color-text-3)]">
          Loading recommended problems...
        </div>
      )}
      {showProblems && error && (
        <div className="mt-2 font-mono text-xs text-[var(--color-text-3)]">
          Problems unavailable right now.
        </div>
      )}
      {showProblems && problemsData && problemsData.problems.length === 0 && (
        <div className="mt-2 font-mono text-xs text-[var(--color-text-3)]">
          No practice problems found for your focus areas in your rating range.
        </div>
      )}
      {showProblems && problemsData && problemsData.problems.length > 0 && (
        <div className="mt-2 space-y-1.5">
          <div className="text-[11px] text-[var(--color-text-2)]">
            These are aligned to your current tag lane instead of repeating only what you already solved.
          </div>
          {problemsData.problems.map((p) => (
            <a
              key={`${p.contest_id}${p.index}`}
              href={p.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 rounded border border-[var(--color-border)] px-2 py-1.5 font-mono text-[11px] transition-colors hover:border-[var(--color-neon-cyan)]"
            >
              <span className="shrink-0 text-[var(--color-neon-cyan)]">{p.rating}</span>
              <span className="flex-1 truncate text-[var(--color-text-2)]">{p.name}</span>
              <span className="shrink-0 text-[10px] text-[var(--color-text-3)]">{p.solved_count} solves</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
