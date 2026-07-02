export interface SkillVector {
  [tag: string]: number;
}

export interface SkillInfo {
  tag: string;
  score: number;
  estimated_gain?: number;
  priority?: number;
  benchmark_gap?: number;
}

export interface LearningPathStep {
  concept: string;
  current_score: number;
  estimated_gain: number;
  prerequisites: string[];
  order: number;
}

export interface PlateauRisk {
  risk: "low" | "moderate" | "high" | "unknown";
  risk_score: number;
  reason: string;
  skill_diversity: number;
}

export interface Milestone {
  next_rating: number;
  gap: number;
  label: string;
}

export interface TrajectoryMilestone {
  milestone: string;
  achieved_at_rating: number;
  days_to_achieve: number | null;
  contests_to_achieve: number | null;
  start_rating: number;
}

export interface PeerInfo {
  handle: string;
  current_rating: number;
  cluster_name: string | null;
}

export interface EliteBenchmarkTag {
  tag: string;
  average_score: number | null;
  gap: number | null;
}

export interface EliteBenchmark {
  sample_size: number;
  target_tags: EliteBenchmarkTag[];
  insight: string;
}

export interface PerformanceSnapshot {
  recent_duel_count: number;
  recent_win_rate: number | null;
  recent_delta_sum: number;
  current_streak: number;
  longest_streak: number;
  trend: "cold-start" | "steady" | "surging" | "slipping";
  recent_results: string[];
}

export interface PracticeStrategy {
  headline: string;
  summary: string;
  target_tags: string[];
  trend: "cold-start" | "steady" | "surging" | "slipping";
}

export interface CoachSummary {
  found: boolean;
  coach_mode: "exact" | "fallback";
  cf_handle: string;
  current_rating: number | null;
  cluster: string | null;
  skill_vector: SkillVector;
  strong_skills: SkillInfo[];
  weak_skills: SkillInfo[];
  recommended_focus: SkillInfo[];
  plateau_risk: PlateauRisk;
  next_milestone: Milestone | null;
  learning_path: LearningPathStep[];
  trajectory_milestones: TrajectoryMilestone[];
  peers: PeerInfo[];
  sample_size: number;
  elite_benchmark: EliteBenchmark;
  performance_snapshot: PerformanceSnapshot;
  practice_strategy: PracticeStrategy;
}

export interface SkillGraphEdge {
  source: string;
  target: string;
  weight: number;
  count: number;
  avg_rating_gain: number;
}

export interface SkillGraph {
  nodes: string[];
  edges: SkillGraphEdge[];
}

export interface ModelInfo {
  id: number;
  task_name: string;
  model_type: string;
  accuracy: number | null;
  f1_score: number | null;
  roc_auc: number | null;
  sample_size: number;
}

export interface ResearchFinding {
  id: number;
  title: string;
  description: string;
  category: string;
  confidence_score: number;
  source_loop: string;
}

export interface ResearchHypothesis {
  id: number;
  question: string;
  status: string;
  priority: number;
  category: string;
  confidence: number | null;
}

export interface ResearchOverview {
  counts: {
    total_findings: number;
    tested_hypotheses: number;
    validated_hypotheses: number;
  };
  recent_findings: ResearchFinding[];
  active_hypotheses: ResearchHypothesis[];
  models: ModelInfo[];
}

export interface PracticeProblem {
  contest_id: number;
  index: string;
  name: string;
  rating: number;
  tags: string[];
  solved_count: number;
  url: string;
}

export interface BreakthroughAnalysis {
  cf_handle: string;
  current_rating: number;
  milestones: TrajectoryMilestone[];
  peers: PeerInfo[];
  plateau_risk: {
    model: string;
    auc: number | null;
    f1: number | null;
    accuracy: number | null;
  } | null;
  breakthrough_prediction: {
    model: string;
    auc: number | null;
    f1: number | null;
    task: string;
  } | null;
}
