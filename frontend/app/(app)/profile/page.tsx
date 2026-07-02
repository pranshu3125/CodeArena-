"use client";
import Link from "next/link";
import { useAuth } from "@/stores/auth";
import { Card } from "@/components/primitives/Card";
import { StatTile } from "@/components/primitives/StatTile";
import { NeonText } from "@/components/primitives/NeonText";
import { TierBadge } from "@/components/cosmetic/TierBadge";
import { tierForElo, divisionForElo } from "@/lib/tier";
import { Button } from "@/components/primitives/Button";
import { EloSparkline } from "@/components/profile/EloSparkline";
import { RecentDuelsList } from "@/components/profile/RecentDuelsList";
import { CoachCard } from "@/components/profile/CoachCard";

export default function ProfilePage() {
  const user = useAuth((s) => s.user);
  if (!user) return null;
  const elo = user.elo ?? 1200;
  const t = tierForElo(elo);
  const div = divisionForElo(elo);
  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-6">
        <div className="flex items-start gap-5">
          <TierBadge elo={elo} size="lg" />
          <div>
            <div className="font-mono text-[11px] tracking-[0.3em] text-[var(--color-neon-pink)] mb-1">
              // PROFILE
            </div>
            <NeonText as="h1" className="text-4xl tracking-[-1px]">
              {user.username}
            </NeonText>
            <div className="mt-1 font-mono text-[12px] tracking-[0.2em] text-[var(--color-neon-cyan)]">
              {t.key}
              {div ? ` ${div}` : ""}
            </div>
            {user.cf_handle && (
              <div className="mt-1 font-mono text-[11px] text-[var(--color-text-3)]">
                @{user.cf_handle}
              </div>
            )}
          </div>
        </div>
        <Link href="/profile/settings">
          <Button variant="ghost">Settings</Button>
        </Link>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatTile label="ELO" value={elo} />
        <StatTile label="Wins" value={user.duel_wins ?? 0} />
        <StatTile label="Losses" value={user.duel_losses ?? 0} />
        <StatTile label="XP" value={user.xp ?? 0} />
      </div>

      <CoachCard user={user} />

      <Card>
        <div className="font-mono text-[11px] tracking-[0.3em] text-[var(--color-text-3)] uppercase mb-3">
          ELO history
        </div>
        <EloSparkline />
      </Card>

      <Card>
        <div className="font-mono text-[11px] tracking-[0.3em] text-[var(--color-text-3)] uppercase mb-3">
          Recent duels
        </div>
        <RecentDuelsList />
      </Card>
    </div>
  );
}
