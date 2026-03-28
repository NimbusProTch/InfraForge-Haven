/**
 * api-pipeline.ts
 *
 * TypeScript types and helpers for the Haven build/deploy pipeline.
 *
 * Pipeline states (in order):
 *   QUEUED → BUILDING → PUSHING → SYNCING → DEPLOYING → HEALTHY
 *                                                      ↘ FAILED
 *
 * These types mirror the Python `PipelineState` enum in
 * api/app/services/pipeline_state.py and the `DeploymentStatus` model.
 */

// ---------------------------------------------------------------------------
// Pipeline state
// ---------------------------------------------------------------------------

export type PipelineState =
  | "queued"
  | "building"
  | "pushing"
  | "syncing"
  | "deploying"
  | "healthy"
  | "failed";

/** Ordered list of non-terminal pipeline states (for progress visualisation). */
export const PIPELINE_STEPS: PipelineState[] = [
  "queued",
  "building",
  "pushing",
  "syncing",
  "deploying",
  "healthy",
];

/** Human-readable label for each pipeline step. */
export const PIPELINE_STEP_LABELS: Record<PipelineState, string> = {
  queued: "Queued",
  building: "Building",
  pushing: "Pushing image",
  syncing: "Syncing GitOps",
  deploying: "Deploying",
  healthy: "Healthy",
  failed: "Failed",
};

// ---------------------------------------------------------------------------
// SSE event payloads
// ---------------------------------------------------------------------------

/** Emitted as SSE `event: pipeline` when the pipeline transitions state. */
export interface PipelineStateEvent {
  deployment_id: string;
  job_id: string;
  state: PipelineState;
  from_state: PipelineState;
  timestamp: string; // ISO 8601
  message: string;
}

/** Emitted as SSE `event: log` for each build log line. */
export interface PipelineLogEvent {
  event_id: number;
  data: string;
}

/** Union of all pipeline SSE event payloads. */
export type PipelineEventPayload = PipelineStateEvent | PipelineLogEvent;

// ---------------------------------------------------------------------------
// Build timeout config
// ---------------------------------------------------------------------------

export interface BuildTimeoutConfig {
  /** Build timeout in seconds (default 900 = 15m, max 1800 = 30m). */
  timeout_seconds: number;
}

export const DEFAULT_BUILD_TIMEOUT_SECONDS = 15 * 60; // 15 minutes
export const MAX_BUILD_TIMEOUT_SECONDS = 30 * 60;     // 30 minutes

// ---------------------------------------------------------------------------
// Deployment summary
// ---------------------------------------------------------------------------

/**
 * Full deployment record returned by GET /deployments/{id} or
 * included in app detail responses.
 */
export interface DeploymentSummary {
  id: string;
  application_id: string;
  commit_sha: string;
  /** Current pipeline state */
  status: PipelineState;
  build_job_name: string | null;
  image_tag: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Returns true if the state is a terminal (non-retryable) state. */
export function isTerminalState(state: PipelineState): boolean {
  return state === "healthy" || state === "failed";
}

/** Returns the 0-based step index (for progress bar rendering). */
export function stepIndex(state: PipelineState): number {
  const idx = PIPELINE_STEPS.indexOf(state);
  return idx === -1 ? 0 : idx;
}

/**
 * Returns a Tailwind CSS class for the state indicator badge.
 *
 * Usage:
 *   <span className={`${stateBadgeClass(state)} px-2 py-1 rounded text-sm`}>
 *     {PIPELINE_STEP_LABELS[state]}
 *   </span>
 */
export function stateBadgeClass(state: PipelineState): string {
  switch (state) {
    case "healthy":
      return "bg-green-100 text-green-800";
    case "failed":
      return "bg-red-100 text-red-800";
    case "building":
    case "pushing":
      return "bg-yellow-100 text-yellow-800";
    case "syncing":
    case "deploying":
      return "bg-blue-100 text-blue-800";
    case "queued":
    default:
      return "bg-gray-100 text-gray-600";
  }
}

/**
 * Parse the `Last-Event-ID` header value from a reconnecting SSE request.
 * Returns 0 if the header is absent or invalid.
 */
export function parseLastEventId(value: string | null | undefined): number {
  if (!value) return 0;
  const parsed = parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

/**
 * Build an SSE URL for a deployment's log stream.
 *
 * @param baseUrl  API base URL (e.g. "http://localhost:8000")
 * @param deploymentId  UUID of the deployment
 * @param lastEventId   Resume position (from EventSource `lastEventId`)
 */
export function buildLogStreamUrl(
  baseUrl: string,
  deploymentId: string,
  lastEventId = 0
): string {
  const url = new URL(`/api/v1/deployments/${deploymentId}/logs/stream`, baseUrl);
  if (lastEventId > 0) {
    url.searchParams.set("last_event_id", String(lastEventId));
  }
  return url.toString();
}
