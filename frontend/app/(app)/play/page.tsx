"use client";
import Link from "next/link";
import { useAuth } from "@/stores/auth";
import { HeroBattleCard } from "@/components/dashboard/HeroBattleCard";
import { ProfileMicroCard } from "@/components/dashboard/ProfileMicroCard";
import { ModesGrid } from "@/components/dashboard/ModesGrid";
import { RecentDuelsPanel } from "@/components/dashboard/RecentDuelsPanel";
import { QuestsPanel } from "@/components/dashboard/QuestsPanel";
import { CoachWidget } from "@/components/dashboard/CoachWidget";

export default function PlayPage() {
  const user = useAuth((s) => s.user);

  return (
    <div className="space-y-8">
      <CoachWidget cfHandle={user?.cf_handle ?? null} />

      <section className="grid grid-cols-1 md:grid-cols-[1fr_380px] gap-6">
        <HeroBattleCard />
        <ProfileMicroCard />
      </section>

      <section className="space-y-3.5">
        <div className="font-mono text-[11px] tracking-[0.3em] text-[var(--color-text-3)] uppercase">
          // Choose your mode
        </div>
        <ModesGrid />
      </section>

      <section className="grid grid-cols-1 md:grid-cols-[1fr_360px] gap-6">
        <RecentDuelsPanel />
        <QuestsPanel compact />
      </section>
    </div>
  );
}
