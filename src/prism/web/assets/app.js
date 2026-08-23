import { ApiError, api, eventSocketUrl } from "./api.js";

const byId = (id) => document.getElementById(id);
const elements = {
  studio: byId("studio"),
  boot: byId("boot-screen"),
  bootMessage: byId("boot-message"),
  projectName: byId("project-name"),
  revision: byId("revision-status"),
  socket: byId("socket-status"),
  audio: byId("audio-status"),
  tempo: byId("tempo"),
  meter: byId("meter"),
  quantization: byId("quantization"),
  position: byId("position-frame"),
  transportMode: byId("transport-mode"),
  sessionHead: byId("session-head"),
  sessionBody: byId("session-body"),
  sessionFoot: byId("session-foot"),
  sessionSummary: byId("session-summary"),
  mixerList: byId("mixer-list"),
  saving: byId("saving-state"),
  renderForm: byId("render-form"),
  renderScene: byId("render-scene"),
  renderBars: byId("render-bars"),
  renderOutput: byId("render-output"),
  renderSubmit: byId("render-submit"),
  renderStatus: byId("render-status"),
  validationBadge: byId("validation-badge"),
  validationContent: byId("validation-content"),
  activityList: byId("activity-list"),
  toastRegion: byId("toast-region"),
  conflict: byId("conflict-dialog"),
  conflictDescription: byId("conflict-description"),
  conflictLatest: byId("conflict-latest"),
  conflictMine: byId("conflict-mine"),
};

const store = {
  projectId: null,
  project: null,
  snapshot: null,
  validation: null,
  jobs: [],
  hydrated: false,
  eventBuffer: [],
  socket: null,
  reconnectAttempt: 0,
  reconnectTimer: null,
  pendingTracks: new Map(),
  activity: [],
  syncTimer: null,
  syncPromise: null,
  syncAfterCurrent: false,
  mutationQueue: Promise.resolve(),
  activeJobId: null,
  jobPoll: null,
};

function create(tag, options = {}) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = String(options.text);
  if (options.testId) node.dataset.testid = options.testId;
  if (options.type) node.type = options.type;
  if (options.title) node.title = options.title;
  return node;
}

function sorted(items) {
  return [...items].sort((left, right) =>
    left.order - right.order || left.name.localeCompare(right.name) || left.id.localeCompare(right.id),
  );
}

function setStatus(node, label, state) {
  const dot = create("span", { className: "status-dot" });
  dot.setAttribute("aria-hidden", "true");
  node.replaceChildren(dot, document.createTextNode(label));
  node.dataset.state = state;
}

function issueMessage(error) {
  if (error instanceof ApiError && error.issues.length) {
    return error.issues.map((issue) => issue.message).join(" ");
  }
  return error instanceof Error ? error.message : String(error);
}

function toast(message, kind = "info") {
  const item = create("div", { className: `toast ${kind === "error" ? "error" : ""}`, text: message });
  elements.toastRegion.append(item);
  window.setTimeout(() => item.remove(), kind === "error" ? 8000 : 4200);
}

function addActivity(type, detail = "") {
  store.activity.unshift({ type, detail, at: new Date() });
  store.activity = store.activity.slice(0, 24);
  renderActivity();
}

function renderActivity() {
  elements.activityList.replaceChildren();
  if (!store.activity.length) {
    const empty = create("li");
    empty.append(create("time", { text: "—" }), create("span", { text: "No recent activity" }));
    elements.activityList.append(empty);
    return;
  }
  for (const entry of store.activity) {
    const item = create("li");
    const time = create("time", {
      text: entry.at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    });
    const description = create("span");
    description.append(create("strong", { text: entry.type.replaceAll(".", " ") }));
    if (entry.detail) description.append(document.createTextNode(` · ${entry.detail}`));
    item.append(time, description);
    elements.activityList.append(item);
  }
}

async function fetchConsistentData() {
  let mismatch = null;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const [projectEnvelope, snapshot, validation, jobsEnvelope] = await Promise.all([
      api.project(store.projectId),
      api.state(store.projectId),
      api.validation(store.projectId),
      api.jobs(store.projectId),
    ]);
    const project = projectEnvelope.project;
    if (project.revision.number === snapshot.revision) {
      return { project, snapshot, validation, jobs: jobsEnvelope.jobs };
    }
    mismatch = `${project.revision.number}/${snapshot.revision}`;
  }
  throw new Error(`Could not obtain one consistent project revision (${mismatch}).`);
}

function applyData(data) {
  store.project = data.project;
  store.snapshot = data.snapshot;
  store.validation = data.validation;
  store.jobs = data.jobs;
  renderAll();
}

async function fullSync({ announce = false } = {}) {
  if (store.syncPromise) return store.syncPromise;
  store.syncPromise = (async () => {
    const data = await fetchConsistentData();
    applyData(data);
    if (announce) addActivity("session.synced", `revision ${data.project.revision.number}`);
  })();
  try {
    await store.syncPromise;
  } finally {
    store.syncPromise = null;
    if (store.syncAfterCurrent) {
      store.syncAfterCurrent = false;
      scheduleFullSync();
    }
  }
}

function scheduleFullSync() {
  if (store.syncPromise) {
    store.syncAfterCurrent = true;
    return;
  }
  if (store.syncTimer) return;
  store.syncTimer = window.setTimeout(async () => {
    store.syncTimer = null;
    try {
      await fullSync();
    } catch (error) {
      toast(issueMessage(error), "error");
    }
  }, 35);
}

async function refreshState() {
  const snapshot = await api.state(store.projectId);
  if (snapshot.revision !== store.project?.revision.number) {
    scheduleFullSync();
    return;
  }
  store.snapshot = snapshot;
  renderHeader();
  renderTransport();
  renderSession();
}

async function refreshJobs() {
  const response = await api.jobs(store.projectId);
  store.jobs = response.jobs;
  renderJob();
}

function connectEvents() {
  if (!store.projectId) return;
  window.clearTimeout(store.reconnectTimer);
  setStatus(elements.socket, store.reconnectAttempt ? "Reconnecting" : "Connecting", "connecting");
  const socket = new WebSocket(eventSocketUrl(store.projectId));
  store.socket = socket;

  socket.addEventListener("open", () => {
    if (store.socket !== socket) return;
    const wasReconnect = store.reconnectAttempt > 0;
    store.reconnectAttempt = 0;
    setStatus(elements.socket, "Live", "connected");
    addActivity(wasReconnect ? "events.reconnected" : "events.connected");
    if (wasReconnect && store.hydrated) scheduleFullSync();
  });

  socket.addEventListener("message", (message) => {
    let event;
    try {
      event = JSON.parse(message.data);
    } catch {
      return;
    }
    if (!store.hydrated) {
      store.eventBuffer.push(event);
      store.eventBuffer = store.eventBuffer.slice(-256);
      return;
    }
    handleEvent(event);
  });

  socket.addEventListener("close", () => {
    if (store.socket !== socket) return;
    setStatus(elements.socket, "Offline", "disconnected");
    const delay = Math.min(5000, 250 * 2 ** store.reconnectAttempt);
    store.reconnectAttempt += 1;
    store.reconnectTimer = window.setTimeout(connectEvents, delay);
  });

  socket.addEventListener("error", () => socket.close());
}

function handleEvent(event) {
  if (event.project_id !== store.projectId) return;
  const detail = event.payload?.track_id ? `track ${String(event.payload.track_id).slice(0, 8)}` : "";
  addActivity(event.type, detail);

  if (event.type === "project.changed" || event.type.startsWith("project.external_change")) {
    scheduleFullSync();
    if (event.type === "project.external_change") {
      toast("The project changed on disk. Resolve it from the CLI before editing.", "error");
    }
    return;
  }
  if (event.type.startsWith("job.")) {
    refreshJobs().catch((error) => toast(issueMessage(error), "error"));
    return;
  }
  if (
    event.type.startsWith("transport.") ||
    event.type.startsWith("clip.") ||
    event.type.startsWith("audio.")
  ) {
    refreshState().catch((error) => toast(issueMessage(error), "error"));
  }
}

function renderAll() {
  if (!store.project || !store.snapshot) return;
  renderHeader();
  renderTransport();
  renderSession();
  renderMixer();
  renderSceneOptions();
  renderJob();
  renderValidation();
}

function renderHeader() {
  elements.projectName.textContent = store.project.name;
  elements.revision.textContent = `REV ${store.project.revision.number}`;
  const audioState = store.snapshot.audio.state ?? "unknown";
  setStatus(elements.audio, `Audio ${audioState}`, audioState === "error" ? "error" : audioState);
}

function renderTransport() {
  const transport = store.project.transport;
  const engine = store.snapshot.engine;
  elements.tempo.textContent = Number(transport.tempo_bpm).toFixed(
    Number.isInteger(transport.tempo_bpm) ? 0 : 1,
  );
  elements.meter.textContent = `${transport.time_signature_numerator}/${transport.time_signature_denominator}`;
  elements.quantization.textContent = transport.quantization;
  elements.position.textContent = Number(engine.position_frame).toLocaleString();
  elements.transportMode.dataset.state = engine.mode;
  elements.transportMode.lastElementChild.textContent = engine.mode;
  for (const button of document.querySelectorAll("[data-transport]")) {
    button.setAttribute("aria-pressed", String(button.dataset.transport === engine.mode));
  }
}

function projectMaps() {
  return {
    clips: new Map(store.project.clips.map((clip) => [clip.id, clip])),
    slots: new Map(
      store.project.clip_slots.map((slot) => [`${slot.track_id}:${slot.scene_id}`, slot]),
    ),
    active: new Map(store.snapshot.engine.active_clip_ids),
  };
}

function clipState(trackId, clipId, active) {
  const pending = store.pendingTracks.get(trackId);
  if (pending?.kind === "launch" && active.get(trackId) === pending.clipId) {
    store.pendingTracks.delete(trackId);
  } else if (pending?.kind === "stop" && !active.has(trackId)) {
    store.pendingTracks.delete(trackId);
  }
  const current = store.pendingTracks.get(trackId);
  if (current?.kind === "launch" && current.clipId === clipId) return ["queued", "Queued"];
  if (current?.kind === "stop" && active.get(trackId) === clipId) return ["queued", "Stop queued"];
  if (active.get(trackId) === clipId) return ["active", "Playing"];
  return ["idle", "Launch"];
}

function renderSession() {
  const tracks = sorted(store.project.tracks);
  const scenes = sorted(store.project.scenes);
  const maps = projectMaps();
  elements.sessionHead.replaceChildren();
  elements.sessionBody.replaceChildren();
  elements.sessionFoot.replaceChildren();

  const header = create("tr");
  const corner = create("th", { text: "Scene / track" });
  corner.scope = "col";
  header.append(corner);
  tracks.forEach((track, index) => {
    const cell = create("th");
    cell.scope = "col";
    const wrap = create("div", { className: "track-heading" });
    wrap.append(create("span", { className: "track-index", text: String(index + 1).padStart(2, "0") }));
    wrap.append(create("span", { text: track.name }));
    cell.append(wrap);
    header.append(cell);
  });
  elements.sessionHead.append(header);

  let populated = 0;
  for (const scene of scenes) {
    const row = create("tr");
    const heading = create("th", { className: "scene-heading", text: scene.name });
    heading.scope = "row";
    row.append(heading);
    tracks.forEach((track, index) => {
      const cell = create("td");
      const slot = maps.slots.get(`${track.id}:${scene.id}`);
      const clip = slot?.clip_id ? maps.clips.get(slot.clip_id) : null;
      if (!clip) {
        const empty = create("button", { className: "empty-slot", text: "·", type: "button" });
        empty.disabled = true;
        empty.setAttribute("aria-label", `${scene.name}, ${track.name}: empty slot`);
        cell.append(empty);
      } else {
        populated += 1;
        const [state, stateLabel] = clipState(track.id, clip.id, maps.active);
        const button = create("button", {
          className: "slot-button",
          type: "button",
          testId: `slot-${track.id}-${scene.id}`,
        });
        button.dataset.state = state;
        button.dataset.trackId = track.id;
        button.dataset.sceneId = scene.id;
        button.dataset.clipId = clip.id;
        button.dataset.color = String(index % 6);
        button.setAttribute("aria-label", `${stateLabel} ${clip.name} on ${track.name}, ${scene.name}`);
        button.append(create("strong", { text: clip.name }), create("small", { text: stateLabel }));
        button.addEventListener("click", () => launchSlot(track.id, scene.id, clip.id, button));
        cell.append(button);
      }
      row.append(cell);
    });
    elements.sessionBody.append(row);
  }

  const footer = create("tr");
  const footerHeading = create("th", { text: "Track stop" });
  footerHeading.scope = "row";
  footer.append(footerHeading);
  tracks.forEach((track) => {
    const cell = create("td");
    const button = create("button", {
      className: "stop-track",
      text: "Stop track",
      type: "button",
      testId: `stop-track-${track.id}`,
    });
    button.addEventListener("click", () => stopTrack(track.id, button));
    cell.append(button);
    footer.append(cell);
  });
  elements.sessionFoot.append(footer);
  elements.sessionSummary.textContent = `${scenes.length} scenes · ${tracks.length} tracks · ${populated} clips`;
}

function formatMixerValue(field, value) {
  if (field === "gain_db") return `${Number(value).toFixed(1)} dB`;
  if (field === "pan") {
    const number = Number(value);
    if (number === 0) return "C";
    return `${number < 0 ? "L" : "R"} ${Math.abs(number).toFixed(2)}`;
  }
  return value ? "On" : "Off";
}

function renderMixer() {
  const tracks = sorted(store.project.tracks);
  elements.mixerList.replaceChildren();
  if (!tracks.length) {
    elements.mixerList.append(create("p", { className: "panel-note", text: "No tracks in this project." }));
    return;
  }
  tracks.forEach((track, index) => {
    const strip = create("article", { className: "mixer-strip", testId: `mixer-${track.id}` });
    const head = create("div", { className: "mixer-strip-head" });
    head.append(create("strong", { text: track.name }));
    const summary = create("span", {
      className: `mixer-value track-color-${index % 6}`,
      text: formatMixerValue("gain_db", track.mixer.gain_db),
    });
    head.append(summary);
    strip.append(head);

    const controls = [
      { field: "gain_db", label: "Gain", min: -60, max: 12, step: 0.5 },
      { field: "pan", label: "Pan", min: -1, max: 1, step: 0.01 },
    ];
    for (const control of controls) {
      const line = create("div", { className: "control-line" });
      const label = create("label", { text: control.label });
      const inputId = `mixer-${track.id}-${control.field}`;
      label.htmlFor = inputId;
      const input = create("input");
      input.id = inputId;
      input.type = "range";
      input.min = control.min;
      input.max = control.max;
      input.step = control.step;
      input.value = track.mixer[control.field];
      input.dataset.testid = inputId;
      const output = create("output", { text: formatMixerValue(control.field, input.value) });
      output.htmlFor = inputId;
      input.addEventListener("input", () => {
        output.textContent = formatMixerValue(control.field, input.value);
        if (control.field === "gain_db") summary.textContent = output.textContent;
      });
      input.addEventListener("change", () => {
        const desired = Number(input.value);
        if (desired !== track.mixer[control.field]) {
          enqueueMixerEdit(track.id, track.name, control.field, track.mixer[control.field], desired);
        }
      });
      line.append(label, input, output);
      strip.append(line);
    }

    const toggles = create("div", { className: "toggle-row" });
    for (const [field, label] of [["muted", "Mute"], ["solo", "Solo"]]) {
      const button = create("button", {
        className: "toggle-button",
        text: label,
        type: "button",
        testId: `mixer-${track.id}-${field}`,
      });
      button.dataset.field = field;
      button.setAttribute("aria-pressed", String(track.mixer[field]));
      button.addEventListener("click", () => {
        const desired = !track.mixer[field];
        button.setAttribute("aria-pressed", String(desired));
        enqueueMixerEdit(track.id, track.name, field, track.mixer[field], desired);
      });
      toggles.append(button);
    }
    strip.append(toggles);
    elements.mixerList.append(strip);
  });
}

function renderSceneOptions() {
  const selected = elements.renderScene.value;
  const scenes = sorted(store.project.scenes);
  const populatedSceneIds = new Set(
    store.project.clip_slots.filter((slot) => slot.clip_id).map((slot) => slot.scene_id),
  );
  elements.renderScene.replaceChildren();
  for (const scene of scenes) {
    const option = create("option", { text: scene.name });
    option.value = scene.id;
    elements.renderScene.append(option);
  }
  const fallback = scenes.find((scene) => populatedSceneIds.has(scene.id))?.id ?? scenes[0]?.id ?? "";
  elements.renderScene.value = scenes.some((scene) => scene.id === selected) ? selected : fallback;
  elements.renderSubmit.disabled = !scenes.length;
}

function renderJob() {
  const renderJobs = store.jobs.filter((job) => job.kind === "render");
  const job =
    renderJobs.find((candidate) => candidate.job_id === store.activeJobId) ?? renderJobs[0] ?? null;
  elements.renderStatus.replaceChildren();
  if (!job) {
    elements.renderStatus.className = "job-card empty";
    const icon = create("span", { className: "job-icon", text: "↗" });
    icon.setAttribute("aria-hidden", "true");
    const copy = create("div");
    copy.append(
      create("strong", { text: "No render submitted" }),
      create("p", { text: "Choose a scene to bounce from frame zero." }),
    );
    elements.renderStatus.append(icon, copy);
    return;
  }

  elements.renderStatus.className = "job-card";
  elements.renderStatus.dataset.state = job.state;
  const icons = { completed: "✓", failed: "!", cancelled: "×", running: "↗", queued: "…" };
  const icon = create("span", { className: "job-icon", text: icons[job.state] ?? "↗" });
  icon.setAttribute("aria-hidden", "true");
  const copy = create("div");
  copy.append(create("strong", { text: `Render ${job.state}` }));
  let detail = `${Math.round(job.progress * 100)}% complete`;
  if (job.state === "completed") {
    detail = `${job.output_path} · SHA-256 ${job.output_sha256}`;
  } else if (job.error) {
    detail = job.error.message;
  }
  copy.append(create("p", { text: detail }));
  if (["queued", "running"].includes(job.state)) {
    const progress = create("progress", { className: "job-progress" });
    progress.max = 1;
    progress.value = job.progress;
    progress.textContent = `${Math.round(job.progress * 100)}%`;
    copy.append(progress);
  }
  elements.renderStatus.append(icon, copy);
}

function renderValidation() {
  const report = store.validation;
  elements.validationBadge.textContent = report.ok ? "Valid" : "Needs attention";
  elements.validationBadge.dataset.state = report.ok ? "valid" : "invalid";
  elements.validationContent.replaceChildren();
  const issues = Object.entries(report.stages).flatMap(([stage, result]) =>
    result.issues.map((issue) => ({ ...issue, stage })),
  );
  if (!issues.length) {
    elements.validationContent.append(
      create("p", { text: "All storage, schema, reference, playback, and device checks passed." }),
    );
    return;
  }
  const list = create("ul", { className: "issue-list" });
  for (const issue of issues) {
    const item = create("li");
    item.append(
      create("span", { className: "issue-code", text: issue.code }),
      create("span", { text: `${issue.message}${issue.path ? ` (${issue.path})` : ""}` }),
    );
    list.append(item);
  }
  elements.validationContent.append(list);
}

async function launchSlot(trackId, sceneId, clipId, button) {
  button.disabled = true;
  try {
    const response = await api.launchSlot(store.projectId, trackId, sceneId);
    store.snapshot = response.snapshot;
    if (response.action.changed) store.pendingTracks.set(trackId, { kind: "launch", clipId });
    addActivity("clip.launch_requested", button.querySelector("strong").textContent);
    renderHeader();
    renderTransport();
    renderSession();
  } catch (error) {
    toast(issueMessage(error), "error");
    button.disabled = false;
  }
}

async function stopTrack(trackId, button) {
  button.disabled = true;
  try {
    const response = await api.stopTrack(store.projectId, trackId);
    store.snapshot = response.snapshot;
    if (response.action.changed) store.pendingTracks.set(trackId, { kind: "stop", clipId: response.clip_id });
    addActivity("clip.stop_requested", `track ${trackId.slice(0, 8)}`);
    renderHeader();
    renderTransport();
    renderSession();
  } catch (error) {
    toast(issueMessage(error), "error");
    button.disabled = false;
  }
}

function findMixerValue(project, trackId, field) {
  const track = project.tracks.find((candidate) => candidate.id === trackId);
  if (!track) throw new Error("The edited track no longer exists.");
  return track.mixer[field];
}

function valuesEqual(left, right) {
  return typeof left === "number" && typeof right === "number"
    ? Math.abs(left - right) < 0.000001
    : left === right;
}

function isResolvableMutationError(error) {
  return (
    (error instanceof ApiError && error.status === 0) ||
    (error instanceof ApiError && error.issues.some((issue) => issue.code === "stale_revision"))
  );
}

function askConflict({ trackName, field, latest, desired }) {
  const label = field.replace("_db", "").replaceAll("_", " ");
  elements.conflictDescription.textContent = `${trackName} ${label} changed after your edit began.`;
  elements.conflictLatest.textContent = formatMixerValue(field, latest);
  elements.conflictMine.textContent = formatMixerValue(field, desired);
  elements.conflict.returnValue = "";
  elements.conflict.showModal();
  return new Promise((resolve) => {
    elements.conflict.addEventListener("close", () => resolve(elements.conflict.returnValue || "latest"), {
      once: true,
    });
  });
}

async function refreshAfterMutation() {
  try {
    await fullSync();
  } catch (error) {
    toast(`The edit was saved, but refresh failed: ${issueMessage(error)}`, "error");
  }
}

async function resolveMixerEdit(edit) {
  const idempotencyKey = crypto.randomUUID();
  const operationId = crypto.randomUUID();
  let baseRevision = edit.baseRevision;
  let baseValue = edit.baseValue;
  let automaticRetryAvailable = true;

  while (true) {
    const request = {
      base_revision: baseRevision,
      operations: [{
        op: "mixer.update",
        op_id: operationId,
        track_id: edit.trackId,
        [edit.field]: edit.desired,
      }],
      idempotency_key: idempotencyKey,
    };
    try {
      const result = await api.commitTransaction(store.projectId, request);
      if (!result.ok) throw new ApiError("The mixer edit was rejected.", { payload: result });
      await refreshAfterMutation();
      addActivity("mixer.updated", `${edit.trackName} ${edit.field.replace("_db", "")}`);
      return;
    } catch (error) {
      if (!isResolvableMutationError(error)) throw error;

      const latestEnvelope = await api.project(store.projectId);
      const latestProject = latestEnvelope.project;
      const latestValue = findMixerValue(latestProject, edit.trackId, edit.field);
      const latestRevision = latestProject.revision.number;
      if (valuesEqual(latestValue, edit.desired)) {
        await refreshAfterMutation();
        return;
      }
      if (valuesEqual(latestValue, baseValue) && automaticRetryAvailable) {
        baseRevision = latestRevision;
        automaticRetryAvailable = false;
        continue;
      }

      const choice = await askConflict({ ...edit, latest: latestValue });
      if (choice !== "mine") {
        await fullSync();
        addActivity("mixer.conflict_kept_latest", edit.trackName);
        return;
      }
      baseRevision = latestRevision;
      baseValue = latestValue;
      automaticRetryAvailable = true;
    }
  }
}

function enqueueMixerEdit(trackId, trackName, field, baseValue, desired) {
  const edit = {
    trackId,
    trackName,
    field,
    baseValue,
    desired,
    baseRevision: store.project.revision.number,
  };
  elements.saving.textContent = "Saving";
  elements.saving.dataset.state = "saving";
  store.mutationQueue = store.mutationQueue
    .then(() => resolveMixerEdit(edit))
    .catch((error) => {
      elements.saving.textContent = "Save failed";
      elements.saving.dataset.state = "error";
      toast(issueMessage(error), "error");
      return fullSync().catch(() => undefined);
    })
    .finally(() => {
      elements.saving.textContent = "Synced";
      elements.saving.dataset.state = "synced";
    });
}

async function submitRender(event) {
  event.preventDefault();
  const sceneId = elements.renderScene.value;
  const bars = Number(elements.renderBars.value);
  const outputPath = elements.renderOutput.value.trim();
  if (!sceneId || !Number.isInteger(bars) || bars < 1 || bars > 64 || !outputPath) return;

  const request = {
    output_path: outputPath,
    bars,
    commands: [{ frame: 0, operation: "launch_scene", scene_id: sceneId }],
    idempotency_key: crypto.randomUUID(),
  };
  elements.renderSubmit.disabled = true;
  elements.renderSubmit.textContent = "Previewing…";
  try {
    const preview = await api.previewRender(store.projectId, request);
    addActivity("render.previewed", preview.output_path);
    elements.renderSubmit.textContent = "Submitting…";
    const response = await api.submitRender(store.projectId, request);
    store.activeJobId = response.job.job_id;
    store.jobs = [response.job, ...store.jobs.filter((job) => job.job_id !== response.job.job_id)];
    renderJob();
    addActivity("render.submitted", `${bars} bars`);
    monitorJob(response.job.job_id);
  } catch (error) {
    toast(issueMessage(error), "error");
    addActivity("render.failed", issueMessage(error));
  } finally {
    elements.renderSubmit.disabled = false;
    elements.renderSubmit.textContent = "Preview & render";
  }
}

function monitorJob(jobId) {
  window.clearInterval(store.jobPoll);
  store.jobPoll = window.setInterval(async () => {
    try {
      const response = await api.job(store.projectId, jobId);
      const index = store.jobs.findIndex((job) => job.job_id === jobId);
      if (index >= 0) store.jobs[index] = response.job;
      else store.jobs.unshift(response.job);
      renderJob();
      if (["completed", "failed", "cancelled"].includes(response.job.state)) {
        window.clearInterval(store.jobPoll);
        store.jobPoll = null;
      }
    } catch (error) {
      window.clearInterval(store.jobPoll);
      store.jobPoll = null;
      toast(issueMessage(error), "error");
    }
  }, 350);
}

async function transport(operation, button) {
  const buttons = document.querySelectorAll("[data-transport]");
  buttons.forEach((item) => { item.disabled = true; });
  try {
    const response = await api.transport(store.projectId, operation);
    store.snapshot = response.snapshot;
    addActivity(`transport.${operation}`);
    renderHeader();
    renderTransport();
    renderSession();
  } catch (error) {
    toast(issueMessage(error), "error");
  } finally {
    buttons.forEach((item) => { item.disabled = false; });
    button.focus();
  }
}

async function boot() {
  try {
    elements.bootMessage.textContent = "Reading project identity…";
    const readiness = await api.readiness();
    store.projectId = readiness.project_id;
    connectEvents();
    elements.bootMessage.textContent = "Synchronizing project and engine state…";
    await fullSync();
    store.hydrated = true;
    const buffered = store.eventBuffer.splice(0);
    buffered.forEach(handleEvent);
    elements.studio.setAttribute("aria-busy", "false");
    elements.boot.hidden = true;
    addActivity("session.ready", `revision ${store.project.revision.number}`);
  } catch (error) {
    elements.boot.querySelector("strong").textContent = "Session unavailable";
    elements.bootMessage.textContent = issueMessage(error);
    setStatus(elements.socket, "Offline", "disconnected");
  }
}

document.querySelectorAll("[data-transport]").forEach((button) => {
  button.addEventListener("click", () => transport(button.dataset.transport, button));
});
elements.renderForm.addEventListener("submit", submitRender);
byId("clear-activity").addEventListener("click", () => {
  store.activity = [];
  renderActivity();
});

renderActivity();
boot();
