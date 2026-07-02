"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  CoachSummary,
  SkillGraph,
  BreakthroughAnalysis,
  ResearchOverview,
  ResearchFinding,
  ResearchHypothesis,
  PracticeProblem,
} from "@/types/coach";

export function useCoachSummary(cfHandle: string | null) {
  return useQuery({
    queryKey: ["coach-summary", cfHandle],
    queryFn: async (): Promise<CoachSummary | null> => {
      if (!cfHandle) return null;
      const { data } = await api.get<CoachSummary>(`/coach/${encodeURIComponent(cfHandle)}/summary`);
      return data;
    },
    enabled: !!cfHandle,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

export function useCoachSkills(cfHandle: string | null) {
  return useQuery({
    queryKey: ["coach-skills", cfHandle],
    queryFn: async () => {
      if (!cfHandle) return null;
      const { data } = await api.get(`/coach/${encodeURIComponent(cfHandle)}/skills`);
      return data;
    },
    enabled: !!cfHandle,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

export function useCoachLearningPath(cfHandle: string | null) {
  return useQuery({
    queryKey: ["coach-learning-path", cfHandle],
    queryFn: async () => {
      if (!cfHandle) return null;
      const { data } = await api.get(`/coach/${encodeURIComponent(cfHandle)}/learning-path`);
      return data;
    },
    enabled: !!cfHandle,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

export function useCoachBreakthrough(cfHandle: string | null) {
  return useQuery({
    queryKey: ["coach-breakthrough", cfHandle],
    queryFn: async (): Promise<BreakthroughAnalysis | null> => {
      if (!cfHandle) return null;
      const { data } = await api.get<BreakthroughAnalysis>(`/coach/${encodeURIComponent(cfHandle)}/breakthrough`);
      return data;
    },
    enabled: !!cfHandle,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

export function useSkillGraph(limit = 100) {
  return useQuery({
    queryKey: ["skill-graph", limit],
    queryFn: async (): Promise<SkillGraph> => {
      const { data } = await api.get<SkillGraph>("/coach/skill-graph", { params: { limit } });
      return data;
    },
    staleTime: 30 * 60 * 1000,
  });
}

export function useResearchOverview() {
  return useQuery({
    queryKey: ["research-overview"],
    queryFn: async (): Promise<ResearchOverview> => {
      const { data } = await api.get<ResearchOverview>("/coach/research/overview");
      return data;
    },
    staleTime: 30 * 60 * 1000,
  });
}

export function useResearchFindings(category?: string, limit = 20) {
  return useQuery({
    queryKey: ["research-findings", category, limit],
    queryFn: async (): Promise<ResearchFinding[]> => {
      const params: Record<string, string | number> = { limit };
      if (category) params.category = category;
      const { data } = await api.get<ResearchFinding[]>("/coach/research/findings", { params });
      return data;
    },
    staleTime: 30 * 60 * 1000,
  });
}

export function useCoachFocus(cfHandle: string | null) {
  return useQuery({
    queryKey: ["coach-focus", cfHandle],
    queryFn: async () => {
      if (!cfHandle) return null;
      const { data } = await api.get(`/coach/${encodeURIComponent(cfHandle)}/focus`);
      return data as { cf_handle: string; focus_progress: { tag: string; practice_count: number; last_practiced_at: string | null }[] };
    },
    enabled: !!cfHandle,
    staleTime: 2 * 60 * 1000,
    retry: 1,
  });
}

export function useCoachHealth() {
  return useQuery({
    queryKey: ["coach-health"],
    queryFn: async (): Promise<{
      status: string;
      database: boolean;
      missing_env_vars: string[];
      invalid_env_vars?: string[];
    }> => {
      const { data } = await api.get("/coach/health");
      return data;
    },
    staleTime: 30 * 1000,
    retry: 0,
  });
}

export function useCoachProblems(cfHandle: string | null, count = 5) {
  return useQuery({
    queryKey: ["coach-problems", cfHandle, count],
    queryFn: async () => {
      if (!cfHandle) return null;
      const { data } = await api.get(`/coach/${encodeURIComponent(cfHandle)}/problems`, { params: { count } });
      return data as { cf_handle: string; problems: PracticeProblem[]; focus_tags: string[]; rating_range: { min: number; max: number } };
    },
    enabled: !!cfHandle,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

export function useResearchHypotheses(limit = 20) {
  return useQuery({
    queryKey: ["research-hypotheses", limit],
    queryFn: async (): Promise<ResearchHypothesis[]> => {
      const { data } = await api.get<ResearchHypothesis[]>("/coach/research/hypotheses", { params: { limit } });
      return data;
    },
    staleTime: 30 * 60 * 1000,
  });
}
