"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card } from "@/components/primitives/Card";
import { NeonText } from "@/components/primitives/NeonText";
import { TierBadge } from "@/components/cosmetic/TierBadge";
import { tierForElo } from "@/lib/tier";

interface Row {
  rank: number;
  user_id: string;
  username: string;
  elo: number;
  cf_handle?: string | null;
  duel_wins: number;
  duel_losses: number;
}

export default function LeaderboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["leaderboard"],
    queryFn: async () => (await api.get<Row[]>("/leaderboard")).data,
  });

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <div className="mb-2 font-mono text-[11px] tracking-[0.3em] text-[var(--color-neon-pink)]">
        // THE LEADERBOARD
      </div>
      <NeonText as="h1" className="mb-10 text-5xl tracking-[-1px]">
        Top of the arena.
      </NeonText>
      <Card>
        {isLoading && (
          <div className="font-mono text-xs text-[var(--color-text-3)]">loading…</div>
        )}
        {!isLoading && data && data.length === 0 && (
          <div className="font-mono text-xs text-[var(--color-text-3)] py-6 text-center">
            No challengers ranked yet.
          </div>
        )}
        {data &&
          data.map((r) => {
            const t = tierForElo(r.elo);
            return (
              <Link
                key={r.user_id}
                href={`/u/${r.username}`}
                className="grid grid-cols-[40px_44px_1fr_120px_100px] items-center gap-4 border-b border-[var(--color-border)] py-3 last:border-b-0 transition hover:bg-[var(--color-surface-2)]/40 px-2 -mx-2 rounded"
              >
                <div className="font-display text-2xl font-extrabold text-[var(--color-text-3)]">
                  {r.rank}
                </div>
                <TierBadge elo={r.elo} size="sm" showDivision={false} />
                <div>
                  <div className="text-[var(--color-text-1)] font-semibold">
                    {r.username}
                  </div>
                  {r.cf_handle && (
                    <div className="font-mono text-[10px] tracking-[0.15em] text-[var(--color-text-3)]">
                      @{r.cf_handle}
                    </div>
                  )}
                </div>
                <div className="font-mono text-[11px] tracking-[0.2em] text-[var(--color-neon-cyan)]">
                  {t.key}
                </div>
                <div className="font-mono text-[18px] font-bold text-right text-[var(--color-text-1)]">
                  {r.elo}
                </div>
              </Link>
            );
          })}
      </Card>
    </main>
  );
}
