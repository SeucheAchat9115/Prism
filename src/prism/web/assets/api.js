export class ApiError extends Error {
  constructor(message, { status = 0, payload = null, cause = null } = {}) {
    super(message, { cause });
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
    this.issues = payload?.errors ?? [];
    this.currentRevision = payload?.current_revision ?? null;
  }
}

async function request(path, { method = "GET", body } = {}) {
  const options = {
    method,
    headers: { Accept: "application/json" },
    cache: "no-store",
  };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(path, options);
  } catch (cause) {
    throw new ApiError("The local Prism service could not be reached.", { cause });
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const issue = payload?.errors?.[0];
    throw new ApiError(issue?.message ?? `Request failed with status ${response.status}.`, {
      status: response.status,
      payload,
    });
  }
  return payload;
}

const projectPath = (projectId, suffix = "") =>
  `/api/v1/projects/${encodeURIComponent(projectId)}${suffix}`;

export const api = {
  readiness: () => request("/api/v1/readiness"),
  capabilities: () => request("/api/v1/capabilities"),
  project: (projectId) => request(projectPath(projectId)),
  state: (projectId) => request(projectPath(projectId, "/state")),
  validation: (projectId) => request(projectPath(projectId, "/validation")),
  jobs: (projectId) => request(projectPath(projectId, "/jobs")),
  job: (projectId, jobId) => request(projectPath(projectId, `/jobs/${jobId}`)),
  transport: (projectId, operation) =>
    request(projectPath(projectId, "/transport"), { method: "POST", body: { operation } }),
  launchSlot: (projectId, trackId, sceneId) =>
    request(projectPath(projectId, "/session/launch"), {
      method: "POST",
      body: { track_id: trackId, scene_id: sceneId },
    }),
  stopTrack: (projectId, trackId) =>
    request(projectPath(projectId, "/session/stop"), {
      method: "POST",
      body: { track_id: trackId },
    }),
  commitTransaction: (projectId, body) =>
    request(projectPath(projectId, "/transactions"), { method: "POST", body }),
  previewRender: (projectId, body) =>
    request(projectPath(projectId, "/render-jobs/preview"), { method: "POST", body }),
  submitRender: (projectId, body) =>
    request(projectPath(projectId, "/render-jobs"), { method: "POST", body }),
};

export function eventSocketUrl(projectId) {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const path = projectPath(projectId, "/events");
  return `${protocol}//${location.host}${path}`;
}
