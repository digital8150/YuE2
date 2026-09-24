(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  let promptAssistant = null;
  let sessionReloading = false;

  const refs = {
    createView: $("#create-view"),
    libraryView: $("#library-view"),
    composerForm: $("#composer-form"),
    modeOptions: $$('[data-mode-option]'),
    trackTitle: $("#track-title"),
    coverField: $("#cover-field"),
    audioFile: $("#audio-file"),
    dropzone: $("#dropzone"),
    dropzoneTitle: $("#dropzone-title"),
    dropzoneDetail: $("#dropzone-detail"),
    selectedFile: $("#selected-file"),
    selectedFileName: $("#selected-file-name"),
    removeAudio: $("#remove-audio"),
    audioError: $("#audio-error"),
    styleInput: $("#style-input"),
    styleError: $("#style-error"),
    lyricsInput: $("#lyrics-input"),
    instrumentalToggle: $("#instrumental-toggle"),
    advancedPanel: $("#advanced-panel"),
    advancedReset: $("#advanced-reset"),
    durationInput: $("#duration-input"),
    seedInput: $("#seed-input"),
    randomSeed: $("#random-seed"),
    planOptions: $("#plan-options"),
    planToggle: $("#plan-toggle"),
    planFields: $("#plan-fields"),
    formError: $("#form-error"),
    submitButton: $("#submit-button"),
    submitLabel: $(".submit-label"),
    jobsList: $("#jobs-list"),
    jobsError: $("#jobs-error"),
    jobsCount: $("#jobs-count"),
    workspaceSearch: $("#workspace-search"),
    workspaceFilter: $("#workspace-filter"),
    refreshJobs: $("#refresh-jobs"),
    jobsPaginationWrap: $("#jobs-pagination-wrap"),
    jobsLoadMore: $("#jobs-load-more"),
    jobsLoadMoreText: $(".load-more-text", $("#jobs-pagination-wrap")),
    jobsEndMarker: $("#jobs-end-marker"),
    lyricsCount: $("#lyrics-count"),
    player: $("#studio-player"),
    playerTitle: $("#player-title"),
    playerBar: $(".player-bar"),
    playerSubtitle: $("#player-subtitle"),
    playerArt: $("#player-art"),
    playerToggle: $("#player-toggle"),
    playerPrev: $("#player-prev"),
    playerNext: $("#player-next"),
    playerProgress: $("#player-progress"),
    playerElapsed: $("#player-elapsed"),
    playerDuration: $("#player-duration"),
    playerVolume: $("#player-volume"),
    playerVisualizer: $("#player-visualizer"),
    ambientBackdrop: $("#ambient-backdrop"),
    ambientOrb1: $(".ambient-orb-1"),
    ambientOrb2: $(".ambient-orb-2"),
    ambientOrb3: $(".ambient-orb-3"),
    ambientGrain: $("#ambient-grain"),
    librarySearch: $("#library-search"),
    clearSearch: $("#clear-search"),
    libraryFilters: $$('[data-library-mode]'),
    libraryStatus: $("#library-status"),
    libraryGrid: $("#library-grid"),
    libraryContent: $("#library-content"),
    libraryToolbar: $("#library-toolbar"),
    libraryTabs: $$('[data-library-tab]'),
    publishDialog: $("#publish-dialog"),
    publishForm: $("#publish-form"),
    publishTitle: $("#publish-title-input"),
    publishCover: $("#publish-cover-input"),
    publishPreview: $("#publish-cover-preview"),
    publishError: $("#publish-error"),
    publishSubmit: $("#publish-submit"),
    growlRegion: $("#growl-region"),
    toastRegion: $("#toast-region"),
    toast: $("#toast"),
    connectionStatuses: $$(".connection-status"),
    viewLinks: $$('[data-view-link]'),
    viewPanels: $$('[data-view-panel]'),
    navQueueLink: $("#nav-queue-link"),
    navQueueBadge: $("#nav-queue-badge"),
    mobileNavQueue: $("#mobile-nav-queue"),
    queuePipWidget: $("#queue-pip-widget"),
    queuePipPill: $("#queue-pip-pill"),
    queuePipWindow: $("#queue-pip-window"),
    queuePipDot: $("#queue-pip-dot"),
    queuePipPillLabel: $("#queue-pip-pill-label"),
    queuePipPillCount: $("#queue-pip-pill-count"),
    queuePipHeadStat: $("#queue-pip-head-stat"),
    queuePipBtnRefresh: $("#queue-pip-btn-refresh"),
    queuePipBtnMaximize: $("#queue-pip-btn-maximize"),
    queuePipBtnMinimize: $("#queue-pip-btn-minimize"),
    queuePipBtnClose: $("#queue-pip-btn-close"),
    queuePipRunningBox: $("#queue-pip-running-box"),
    queuePipPendingBox: $("#queue-pip-pending-box"),
    queuePipRecentBox: $("#queue-pip-recent-box"),
    queuePipRunningNum: $("#queue-pip-running-num"),
    queuePipPendingNum: $("#queue-pip-pending-num"),
    queuePipDevice: $("#queue-pip-device"),
    queueView: $("#queue-view"),
    queuePageRefresh: $("#queue-page-refresh"),
    queuePageOpenPip: $("#queue-page-open-pip"),
    queuePageEngineStatus: $("#queue-page-engine-status"),
    queuePageBannerLeft: $("#queue-page-banner .queue-banner-left"),
    queuePageCreate: $("#queue-page-create"),
    queuePageGpu: $("#queue-page-gpu"),
    queuePageRunning: $("#queue-page-running"),
    queuePagePending: $("#queue-page-pending"),
    queuePageRecent: $("#queue-page-recent"),
    queuePagePendingCount: $("#queue-page-pending-count"),
    queueWorkers: $("#queue-workers"),
    queueWorkerCount: $("#queue-worker-count"),
    workerContribute: $("#worker-contribute"),
    workerCreateForm: $("#worker-create-form"),
    workerCredential: $("#worker-credential"),
    workerConfig: $("#worker-config"),
    workerCopyConfig: $("#worker-copy-config"),
    workerFormStatus: $("#worker-form-status"),
    myWorkers: $("#my-workers")
  };

  const defaults = {
    original: {
      duration: "120",
      temperature: "1",
      topP: "0.95",
      topK: "100",
      repetitionPenalty: "1.2"
    },
    cover: {
      duration: "360",
      temperature: "1",
      topP: "0.95",
      topK: "100",
      repetitionPenalty: "1.2"
    }
  };
  const composerInputIds = [
    "prompt-idea", "prompt-language", "lyrics-input", "style-input", "track-title",
    "seed-input", "temperature-input", "top-p-input", "top-k-input", "repetition-input",
    "plan-temperature-input", "plan-top-p-input", "plan-top-k-input",
    "plan-repetition-input", "penalty-window-input"
  ];
  const durationByMode = {
    original: defaults.original.duration,
    cover: defaults.cover.duration
  };
  let composerPersistenceReady = false;
  let guestComposerTouched = false;
  let signedInStarted = false;

  const state = {
    view: getViewFromHash(),
    mode: "original",
    instrumental: false,
    vocalLyrics: "",
    seedRandom: true,
    planEnabled: true,
    audioFile: null,
    isSubmitting: false,
    healthReady: false,
    jobs: [],
    jobsLoading: false,
    jobsResyncRequested: false,
    jobsError: "",
    realtimeVersion: 0,
    realtimeChanges: new Map(),
    jobsPagination: {
      offset: 0,
      limit: 20,
      total: 0,
      hasMore: false,
      loadingMore: false
    },
    playerTrack: null,
    playerQueue: [],
    library: {
      items: [],
      loading: false,
      loaded: false,
      error: "",
      query: "",
      mode: "all",
      requestId: 0
    },
    libraryDebounce: null,
    libraryHome: null,
    libraryHomeLoaded: false,
    libraryPageRequestId: 0,
    myAlbums: [],
    myArtists: [],
    albumAfterCreate: false,
    focusTrackId: null,
    publishJobId: null,
    publishPreviewUrl: null,
    toastTimer: null,
    notifiedCutoffTracks: new Set(),
    knownJobStatuses: new Map(),
    queue: {
      running: [],
      pending: [],
      recent: [],
      summary: { running_count: 0, pending_count: 0, total_active: 0 },
      engine: { status: "offline", device: "", vram: "" }
    }
  };

  const terminalStatuses = new Set(["completed", "failed", "cancelled"]);

  function getViewFromHash() {
    const hash = window.location.hash.replace(/^#/, "").split("?")[0];
    if (hash === "library") return "library";
    if (hash === "queue") return "queue";
    if (hash === "backoffice") return "backoffice";
    return "create";
  }

  function safeText(value, fallback = "") {
    if (value === undefined || value === null) return fallback;
    if (typeof value === "string" || typeof value === "number") return String(value);
    return fallback;
  }

  function firstValue(object, keys, fallback = "") {
    if (!object || typeof object !== "object") return fallback;
    for (const key of keys) {
      if (object[key] !== undefined && object[key] !== null && object[key] !== "") {
        return object[key];
      }
    }
    return fallback;
  }

  function extractList(payload, keys) {
    if (Array.isArray(payload)) return payload;
    if (!payload || typeof payload !== "object") return [];
    for (const key of keys) {
      if (Array.isArray(payload[key])) return payload[key];
    }
    if (payload.data && typeof payload.data === "object") {
      for (const key of keys) {
        if (Array.isArray(payload.data[key])) return payload.data[key];
      }
    }
    return [];
  }

  function element(tag, options = {}, children = []) {
    const node = document.createElement(tag);
    if (options.className) node.className = options.className;
    if (options.text !== undefined) node.textContent = options.text;
    if (options.attrs) {
      Object.entries(options.attrs).forEach(([name, value]) => {
        if (value === undefined || value === null || value === false) return;
        if (value === true) node.setAttribute(name, "");
        else node.setAttribute(name, String(value));
      });
    }
    if (options.properties) {
      Object.entries(options.properties).forEach(([name, value]) => {
        node[name] = value;
      });
    }
    if (options.on) {
      Object.entries(options.on).forEach(([eventName, handler]) => node.addEventListener(eventName, handler));
    }
    children.forEach((child) => {
      if (child) node.append(child);
    });
    return node;
  }

  function svgIcon(name, className = "icon") {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    svg.setAttribute("class", className);
    svg.setAttribute("aria-hidden", "true");
    use.setAttribute("href", `#icon-${name}`);
    svg.append(use);
    return svg;
  }

  const BASE_PATH = (() => {
    const path = window.location.pathname;
    return path.endsWith("/") ? path.slice(0, -1) : path;
  })();

  function resolvePath(path) {
    if (!path || typeof path !== "string") return path;
    if (path.startsWith("http://") || path.startsWith("https://") || path.startsWith("blob:")) return path;
    const clean = path.startsWith("/") ? path : `/${path}`;
    return BASE_PATH && !clean.startsWith(BASE_PATH) ? `${BASE_PATH}${clean}` : clean;
  }

  async function fetchJson(url, options = {}) {
    const resolvedUrl = resolvePath(url);
    const response = await fetch(resolvedUrl, {
      credentials: "same-origin",
      ...options,
      headers: { ...(options.headers || {}), ...(options.method && options.method !== "GET" ? { "X-Yue2-CSRF": window.yue2Auth?.csrfToken || "" } : {}) }
    });
    if (response.status === 401 && window.yue2Auth?.ready && !sessionReloading) {
      sessionReloading = true;
      window.location.reload();
    }
    const contentType = response.headers.get("content-type") || "";
    let payload = null;
    if (response.status !== 204) {
      if (contentType.includes("application/json")) {
        payload = await response.json().catch(() => null);
      } else {
        const text = await response.text().catch(() => "");
        if (text) {
          try {
            payload = JSON.parse(text);
          } catch {
            payload = { message: text };
          }
        }
      }
    }
    if (!response.ok) {
      const error = new Error(safeText(payload && (payload.error || payload.message), "요청을 처리하지 못했어요."));
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  function normalizeMode(value) {
    const normalized = safeText(value).toLowerCase();
    return normalized.includes("cover") || normalized === "c" ? "cover" : "original";
  }

  function normalizeStatus(value) {
    const normalized = safeText(value, "queued").toLowerCase().replace(/\s+/g, "_");
    if (["complete", "completed", "success", "succeeded", "done", "finished"].includes(normalized)) return "completed";
    if (["failed", "failure", "error", "errored"].includes(normalized)) return "failed";
    if (["cancelled", "canceled", "stopped"].includes(normalized)) return "cancelled";
    if (["running", "processing", "generating", "in_progress", "in-progress", "uploading"].includes(normalized)) return "processing";
    return "queued";
  }

  function normalizeJob(raw, index) {
    const object = raw && typeof raw === "object" ? raw : {};
    const id = safeText(firstValue(object, ["id", "job_id", "generation_id", "task_id"], `job-${index}`), `job-${index}`);
    const rawSafeError = firstValue(object, ["safe_error", "safeError", "user_message", "userMessage", "error_message", "error"], "");
    const hasSafeError = typeof rawSafeError === "string" && rawSafeError.trim().length > 0;
    return {
      ...normalizeTrack(object, index),
      id,
      title: safeText(firstValue(object, ["title", "name"], "제목 없는 곡"), "제목 없는 곡"),
      mode: normalizeMode(firstValue(object, ["mode", "type", "kind"], "original")),
      status: normalizeStatus(firstValue(object, ["status", "state", "phase"], "queued")),
      progress: object.progress && typeof object.progress === "object" ? object.progress : null,
      createdAt: firstValue(object, ["created_at", "createdAt", "submitted_at", "submittedAt", "timestamp"], ""),
      trackId: safeText(firstValue(object, ["track_id", "trackId", "library_id", "libraryId", "output_id", "outputId"], id), id),
      error: hasSafeError ? rawSafeError.trim().slice(0, 220) : "작업을 완료하지 못했어요. 다시 시도해 주세요."
    };
  }

  function normalizeTrack(raw, index) {
    const object = raw && typeof raw === "object" ? raw : {};
    const id = safeText(firstValue(object, ["id", "track_id", "trackId", "library_id", "libraryId"], `track-${index}`), `track-${index}`);
    return {
      id,
      title: safeText(firstValue(object, ["title", "name"], "제목 없는 곡"), "제목 없는 곡"),
      mode: normalizeMode(firstValue(object, ["mode", "type", "kind"], "original")),
      style: safeText(firstValue(object, ["style", "prompt", "description"], "")),
      audioUrl: safeText(firstValue(object, ["audio_url", "audioUrl", "audio", "url"], "")),
      downloadUrl: safeText(firstValue(object, ["download_url", "downloadUrl", "download"], "")),
      createdAt: firstValue(object, ["created_at", "createdAt", "date", "timestamp"], ""),
      creator: safeText(object.creator, "이전 작업"),
      published: Boolean(object.published),
      coverUrl: safeText(object.cover_url || ""),
      publishedTitle: safeText(object.published_title || ""),
      artistId: object.artist_id == null ? null : String(object.artist_id),
      albumId: safeText(object.album_id || ""),
      playCount: Number(object.play_count) || 0
    };
  }

  function toDate(value) {
    if (value instanceof Date && !Number.isNaN(value.valueOf())) return value;
    if (typeof value === "number" && Number.isFinite(value)) {
      const timestamp = value < 100000000000 ? value * 1000 : value;
      const date = new Date(timestamp);
      return Number.isNaN(date.valueOf()) ? null : date;
    }
    if (typeof value === "string" && value.trim()) {
      const date = new Date(value);
      return Number.isNaN(date.valueOf()) ? null : date;
    }
    return null;
  }

  function formatDate(value) {
    const date = toDate(value);
    if (!date) return "날짜 미상";
    return new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "short", day: "numeric" }).format(date);
  }

  function formatRelative(value) {
    const date = toDate(value);
    if (!date) return "방금 전";
    const diffSeconds = (date.getTime() - Date.now()) / 1000;
    const absolute = Math.abs(diffSeconds);
    const units = [
      ["year", 31536000],
      ["month", 2592000],
      ["week", 604800],
      ["day", 86400],
      ["hour", 3600],
      ["minute", 60]
    ];
    const unit = units.find(([, seconds]) => absolute >= seconds);
    if (!unit) return "방금 전";
    const amount = Math.round(diffSeconds / unit[1]);
    try {
      return new Intl.RelativeTimeFormat("ko", { numeric: "auto" }).format(amount, unit[0]);
    } catch {
      return formatDate(value);
    }
  }

  function statusLabel(status) {
    if (status === "completed") return "완료";
    if (status === "failed") return "실패";
    if (status === "cancelled") return "취소됨";
    if (status === "processing") return "만드는 중";
    return "대기 중";
  }

  function modeLabel(mode) {
    return mode === "cover" ? "커버" : "새 곡";
  }

  function isTerminal(job) {
    return terminalStatuses.has(job.status);
  }

  function setHealthStatus(ready, checked = true) {
    state.healthReady = ready;
    refs.connectionStatuses.forEach((statusNode) => {
      statusNode.hidden = ready || !checked;
      const label = $(".connection-label", statusNode);
      if (label) label.textContent = "지금은 음악을 만들 수 없습니다";
    });
  }

  async function checkHealth() {
    const wasReady = state.healthReady;
    try {
      const payload = await fetchJson("/api/health", { headers: { Accept: "application/json" } });
      const explicitlyUnhealthy = payload && typeof payload === "object"
        && (payload.ok === false || payload.healthy === false || payload.engine !== "online");
      setHealthStatus(!explicitlyUnhealthy);
    } catch {
      setHealthStatus(false);
    }
    if (wasReady !== state.healthReady) QueueManager.refreshSoon();
  }

  function composerStorageKey() {
    const userId = window.yue2Auth?.user?.id;
    return userId == null ? null : `yue2:composer:v1:${userId}`;
  }

  function saveComposer() {
    if (!composerPersistenceReady) return;
    const key = composerStorageKey();
    if (!key) return;
    durationByMode[state.mode] = refs.durationInput.value;
    const values = {};
    composerInputIds.forEach((id) => { values[id] = document.getElementById(id).value; });
    const snapshot = {
      version: 1,
      mode: state.mode,
      instrumental: state.instrumental,
      vocalLyrics: state.vocalLyrics,
      randomSeed: refs.randomSeed.checked,
      planEnabled: state.planEnabled,
      advancedOpen: refs.advancedPanel.open,
      durationByMode,
      values
    };
    try {
      window.localStorage.setItem(key, JSON.stringify(snapshot));
    } catch {
      // The editor still works when local storage is disabled or full.
    }
  }

  function restoreComposer() {
    const key = composerStorageKey();
    if (!key) return;
    let snapshot;
    try {
      snapshot = JSON.parse(window.localStorage.getItem(key));
    } catch {
      return;
    }
    if (!snapshot || snapshot.version !== 1 || typeof snapshot !== "object") return;
    setMode(snapshot.mode);
    for (const mode of ["original", "cover"]) {
      const value = snapshot.durationByMode?.[mode];
      if (typeof value === "string") durationByMode[mode] = value;
    }
    refs.durationInput.value = durationByMode[state.mode];
    if (snapshot.values && typeof snapshot.values === "object") {
      composerInputIds.forEach((id) => {
        const input = document.getElementById(id);
        const value = snapshot.values[id];
        if (typeof value !== "string") return;
        if (input.tagName === "SELECT") {
          if (Array.from(input.options).some((option) => option.value === value)) input.value = value;
        } else {
          input.value = input.maxLength > -1 ? value.slice(0, input.maxLength) : value;
        }
      });
    }
    if (typeof snapshot.randomSeed === "boolean") refs.randomSeed.checked = snapshot.randomSeed;
    syncSeedState();
    if (typeof snapshot.planEnabled === "boolean") {
      refs.planToggle.setAttribute("aria-checked", String(snapshot.planEnabled));
      refs.planToggle.classList.toggle("is-on", snapshot.planEnabled);
    }
    syncPlanState();
    if (typeof snapshot.instrumental === "boolean") {
      const restoredLyrics = refs.lyricsInput.value;
      setInstrumental(snapshot.instrumental);
      if (snapshot.instrumental) {
        refs.lyricsInput.value = restoredLyrics || "[instrumental]";
        state.vocalLyrics = typeof snapshot.vocalLyrics === "string" ? snapshot.vocalLyrics : "";
      }
    }
    if (typeof snapshot.advancedOpen === "boolean") refs.advancedPanel.open = snapshot.advancedOpen;
    updateLyricsCount();
  }

  function setMode(mode) {
    const nextMode = mode === "cover" ? "cover" : "original";
    if (state.mode !== nextMode) durationByMode[state.mode] = refs.durationInput.value;
    state.mode = nextMode;
    refs.modeOptions.forEach((button) => {
      const selected = button.dataset.modeOption === state.mode;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    refs.coverField.hidden = state.mode !== "cover";
    refs.planOptions.hidden = state.mode !== "original";
    refs.durationInput.value = durationByMode[state.mode];
    clearFieldError(refs.audioFile, refs.audioError);
    clearFormError();
    if (promptAssistant) void promptAssistant.checkSupport();
    saveComposer();
  }

  function syncSeedState() {
    state.seedRandom = refs.randomSeed.checked;
    refs.seedInput.disabled = state.seedRandom;
    refs.seedInput.setAttribute("aria-disabled", String(state.seedRandom));
  }

  function resetAdvancedSettings() {
    const values = defaults[state.mode];
    durationByMode.original = defaults.original.duration;
    durationByMode.cover = defaults.cover.duration;
    refs.durationInput.value = values.duration;
    $("#temperature-input").value = values.temperature;
    $("#top-p-input").value = values.topP;
    $("#top-k-input").value = values.topK;
    $("#repetition-input").value = values.repetitionPenalty;
    refs.randomSeed.checked = true;
    refs.seedInput.value = "";
    syncSeedState();
    refs.planToggle.setAttribute("aria-checked", "true");
    refs.planToggle.classList.add("is-on");
    syncPlanState();
    $("#plan-temperature-input").value = "0.7";
    $("#plan-top-p-input").value = "0.9";
    $("#plan-top-k-input").value = "30";
    $("#plan-repetition-input").value = "1.005";
    $("#penalty-window-input").value = "100";

    $$("input", refs.advancedPanel).forEach((input) => {
      input.classList.remove("is-invalid");
    });
    clearFormError();
    saveComposer();

    if (refs.advancedReset) {
      refs.advancedReset.classList.remove("is-spinning");
      void refs.advancedReset.offsetWidth;
      refs.advancedReset.classList.add("is-spinning");
      window.setTimeout(() => refs.advancedReset.classList.remove("is-spinning"), 500);
    }

    showToast("고급 설정을 기본값으로 초기화했습니다.");
  }

  function syncPlanState() {
    state.planEnabled = refs.planToggle.getAttribute("aria-checked") === "true";
    refs.planFields.classList.toggle("is-disabled", !state.planEnabled);
    $$("input", refs.planFields).forEach((input) => {
      input.disabled = !state.planEnabled;
    });
  }

  function setInstrumental(enabled, refreshPromptSupport = true) {
    if (enabled !== state.instrumental) {
      if (enabled) {
        state.vocalLyrics = refs.lyricsInput.value;
        refs.lyricsInput.value = "[instrumental]";
      } else {
        refs.lyricsInput.value = state.vocalLyrics;
      }
    }
    state.instrumental = enabled;
    refs.instrumentalToggle.setAttribute("aria-checked", String(enabled));
    refs.instrumentalToggle.classList.toggle("is-on", enabled);
    refs.lyricsInput.placeholder = enabled ? "[instrumental]\n\n또는 [intro], [verse], [chorus], [outro]를 한 줄씩 입력하세요." : "가사를 입력하세요.";
    document.getElementById("instrumental-hint").hidden = !enabled;
    updateLyricsCount();
    if (promptAssistant && refreshPromptSupport) void promptAssistant.checkSupport();
    saveComposer();
  }

  function updateLyricsCount() {
    refs.lyricsCount.textContent = `${refs.lyricsInput.value.length.toLocaleString("ko-KR")} / 6,000`;
    if (state.instrumental) saveComposer();
  }

  function clearFieldError(input, errorNode) {
    if (input) input.classList.remove("is-invalid");
    if (errorNode) {
      errorNode.hidden = true;
      errorNode.textContent = "";
    }
  }

  function showFieldError(input, errorNode, message) {
    if (input) input.classList.add("is-invalid");
    if (errorNode) {
      errorNode.hidden = false;
      errorNode.textContent = message;
    }
  }

  function clearFormError() {
    refs.formError.hidden = true;
    refs.formError.textContent = "";
  }

  function showFormError(message) {
    refs.formError.hidden = false;
    refs.formError.textContent = message;
  }

  function isAudioFile(file) {
    if (!file) return false;
    return /\.(mp3|wav|m4a|ogg|flac|aac|opus)$/i.test(file.name || "");
  }

  function resetAudioSelection() {
    state.audioFile = null;
    refs.audioFile.value = "";
    refs.selectedFile.hidden = true;
    refs.selectedFileName.textContent = "";
    refs.dropzoneTitle.textContent = "오디오를 올려주세요";
    refs.dropzoneDetail.textContent = "클릭하거나 파일을 이곳에 끌어다 놓으세요.";
    clearFieldError(refs.audioFile, refs.audioError);
  }

  function selectAudioFile(file) {
    if (!file) return;
    if (!isAudioFile(file)) {
      resetAudioSelection();
      showFieldError(refs.audioFile, refs.audioError, "오디오 파일을 선택해 주세요.");
      refs.dropzone.focus();
      return;
    }
    state.audioFile = file;
    refs.selectedFile.hidden = false;
    refs.selectedFileName.textContent = file.name || "선택한 오디오";
    refs.dropzoneTitle.textContent = "오디오가 준비됐어요";
    refs.dropzoneDetail.textContent = "다른 파일을 선택하려면 이 영역을 다시 눌러주세요.";
    clearFieldError(refs.audioFile, refs.audioError);
  }

  function appendSuggestion(suggestion) {
    const current = refs.styleInput.value.trim();
    refs.styleInput.value = current ? `${current}\n${suggestion}` : suggestion;
    clearFieldError(refs.styleInput, refs.styleError);
    refs.styleInput.focus();
    const end = refs.styleInput.value.length;
    refs.styleInput.setSelectionRange(end, end);
    saveComposer();
  }

  function validateForm() {
    clearFormError();
    clearFieldError(refs.styleInput, refs.styleError);
    clearFieldError(refs.audioFile, refs.audioError);
    const style = refs.styleInput.value.trim();
    if (state.instrumental) {
      const plan = refs.lyricsInput.value.trim();
      const lines = plan.replace(/\r\n?/g, "\n").split("\n").map((line) => line.trim()).filter(Boolean);
      const section = /^\[(intro|verse|pre-chorus|chorus|bridge|outro)(?: [1-9]\d*)?(?: (\d+:[0-5]\d)-(\d+:[0-5]\d))?\]$/i;
      let planError = "";
      if (lines.length && !(lines.length === 1 && /^\[instrumental\]$/i.test(lines[0]))) {
        if (lines.length > 32) planError = "연주곡 구조는 구간을 32개 이하로 입력해 주세요.";
        let timed = null;
        let previousEnd = -1;
        for (const line of lines) {
          if (planError) break;
          const match = line.match(section);
          if (!match) {
            planError = "연주곡 구조에는 [instrumental] 또는 구간 태그만 입력해 주세요.";
            break;
          }
          const hasTimes = match[2] !== undefined;
          if (timed !== null && timed !== hasTimes) {
            planError = "연주곡 구간에는 시간 표시가 있는 태그와 없는 태그를 섞을 수 없어요.";
            break;
          }
          timed = hasTimes;
          if (hasTimes) {
            const seconds = (value) => {
              const [minutes, remainder] = value.split(":").map(Number);
              return minutes * 60 + remainder;
            };
            const start = seconds(match[2]);
            const end = seconds(match[3]);
            if (start >= end || start < previousEnd) {
              planError = "연주곡 구간 시간을 시작부터 끝까지 순서대로 입력해 주세요.";
              break;
            }
            previousEnd = end;
          }
        }
      }
      if (planError) {
        showFormError(planError);
        refs.lyricsInput.focus();
        return false;
      }
    }
    if (!style) {
      showFieldError(refs.styleInput, refs.styleError, "사운드 스타일을 적어주세요.");
      refs.styleInput.focus();
      return false;
    }
    if (state.mode === "cover" && !state.audioFile) {
      showFieldError(refs.audioFile, refs.audioError, "커버에 사용할 오디오를 선택해 주세요.");
      refs.dropzone.focus();
      return false;
    }
    const enabledNumbers = $$('input[type="number"]', refs.composerForm).filter((input) => !input.disabled);
    const invalidNumber = enabledNumbers.find((input) => !input.checkValidity());
    if (invalidNumber) {
      showFormError("고급 옵션의 입력 범위를 확인해 주세요.");
      refs.advancedPanel.open = true;
      invalidNumber.focus();
      return false;
    }
    return true;
  }

  function buildGenerationFormData() {
    const formData = new FormData();
    formData.append("mode", state.mode);
    formData.append("title", refs.trackTitle.value.trim());
    formData.append("style", refs.styleInput.value.trim());
    formData.append("lyrics", state.instrumental ? (refs.lyricsInput.value.trim() || "[instrumental]") : refs.lyricsInput.value.trim());
    formData.append("instrumental", String(state.instrumental));
    formData.append("duration", refs.durationInput.value || defaults[state.mode].duration);
    formData.append("random_seed", String(state.seedRandom));
    if (!state.seedRandom && refs.seedInput.value.trim()) formData.append("seed", refs.seedInput.value.trim());
    formData.append("temperature", $("#temperature-input").value || defaults[state.mode].temperature);
    formData.append("top_p", $("#top-p-input").value || defaults[state.mode].topP);
    formData.append("top_k", $("#top-k-input").value || defaults[state.mode].topK);
    formData.append("repetition_penalty", $("#repetition-input").value || defaults[state.mode].repetitionPenalty);
    formData.append("use_plan", String(state.mode === "original" && state.planEnabled));
    if (state.mode === "original" && state.planEnabled) {
      formData.append("plan_temperature", $("#plan-temperature-input").value || "0.7");
      formData.append("plan_top_p", $("#plan-top-p-input").value || "0.9");
      formData.append("plan_top_k", $("#plan-top-k-input").value || "30");
      formData.append("plan_repetition_penalty", $("#plan-repetition-input").value || "1.005");
      formData.append("penalty_window", $("#penalty-window-input").value || "100");
    }
    if (state.mode === "cover" && state.audioFile) {
      formData.append("audio_file", state.audioFile, state.audioFile.name);
    }
    return formData;
  }

  function setSubmitting(isSubmitting) {
    state.isSubmitting = isSubmitting;
    refs.submitButton.disabled = isSubmitting;
    refs.submitButton.classList.toggle("is-loading", isSubmitting);
    refs.submitButton.setAttribute("aria-busy", String(isSubmitting));
    refs.submitLabel.textContent = isSubmitting ? "생성 중…" : "음악 생성하기";
  }

  async function submitGeneration(event) {
    event.preventDefault();
    if (!window.yue2Auth?.ready) {
      window.yue2Auth?.open?.();
      return;
    }
    if (state.isSubmitting || !validateForm()) return;
    setSubmitting(true);
    try {
      const created = await fetchJson("/api/generations", {
        method: "POST",
        body: buildGenerationFormData()
      });
      clearFormError();
      Growl.info({
        title: "음악 생성 시작",
        message: "내 스튜디오에서 진행 상태를 확인할 수 있습니다.",
        duration: 5000
      });
      if (!state.jobs.some((job) => job.id === created.id)) applyJobUpdate(created);
    } catch (error) {
      if (error && error.status === 503) {
        showFormError("지금은 음악을 만들 수 없어요. 잠시 후 다시 시도해 주세요.");
        showToast("잠시 후 다시 시도해 주세요.", "error");
      } else if (error && error.status === 400) {
        showFormError(safeText(error.message, "입력값을 확인해 주세요."));
        showToast("입력값을 확인해 주세요.", "error");
      } else {
        showFormError("요청을 보내지 못했어요. 잠시 후 다시 시도해 주세요.");
        showToast("요청을 보내지 못했어요.", "error");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function loadJobs({ initial = false, reset = true } = {}) {
    if (!window.yue2Auth?.ready) return;
    if (state.jobsLoading) {
      state.jobsResyncRequested = true;
      return;
    }
    state.jobsLoading = true;
    state.realtimeChanges.clear();
    refs.refreshJobs.disabled = true;
    if (initial && state.jobs.length === 0) renderJobs();

    const limit = reset ? 20 : Math.max(state.jobs.length, 20);
    const offset = 0;
    const fetchVersion = state.realtimeVersion;

    try {
      const payload = await fetchJson(`/api/jobs?limit=${limit}&offset=${offset}&paged=1`, {
        headers: { Accept: "application/json" }
      });
      const list = extractList(payload, ["jobs", "items", "generations", "data"]);
      const previousCompleted = new Set(state.jobs.filter((job) => job.status === "completed").map((job) => job.id));
      const freshJobs = list.map(normalizeJob);
      for (const [id, change] of state.realtimeChanges) {
        if (change.version <= fetchVersion) continue;
        const index = freshJobs.findIndex((job) => job.id === id);
        if (index < 0) freshJobs.unshift(change.job);
        else freshJobs[index] = change.job;
      }
      state.jobs = freshJobs;
      state.realtimeChanges.clear();

      const total = typeof payload?.total === "number" ? payload.total : freshJobs.length;
      state.jobsPagination.total = total;
      state.jobsPagination.offset = offset;
      state.jobsPagination.limit = 20;
      state.jobsPagination.hasMore = Boolean(payload?.has_more !== undefined ? payload.has_more : freshJobs.length < total);

      if (!initial) {
        state.jobs.forEach((job) => {
          const prevStatus = state.knownJobStatuses.get(job.id);
          if (prevStatus && prevStatus !== job.status) {
            if (job.status === "completed") {
              Growl.success({
                title: "음악 생성 완료",
                message: `"${job.title}" 생성이 완료되었습니다!`,
                duration: 6500,
                action: {
                  label: "지금 재생",
                  onClick: () => playTrack(job, state.jobs.filter((item) => item.status === "completed"))
                }
              });
            } else if (job.status === "failed") {
              Growl.error({
                title: "음악 생성 실패",
                message: "곡을 만들지 못했습니다. 잠시 후 다시 시도해 주세요.",
                duration: 7000
              });
            }
          }
        });
      }
      state.jobs.forEach((job) => state.knownJobStatuses.set(job.id, job.status));
      if (state.jobs.some((job) => job.status === "completed" && !previousCompleted.has(job.id))) {
        state.library.loaded = false;
        if (state.view === "library") loadLibrary();
      }
      state.jobsError = "";
    } catch {
      state.jobsError = "작업 상태를 불러오지 못했어요.";
    } finally {
      state.jobsLoading = false;
      refs.refreshJobs.disabled = false;
      renderJobs({ preserveScroll: !reset });
      if (state.jobsResyncRequested) {
        state.jobsResyncRequested = false;
        loadJobs({ reset: false });
      }
    }
  }

  function applyJobUpdate(raw) {
    if (!raw || !raw.id) return;
    const job = normalizeJob(raw);
    const index = state.jobs.findIndex((item) => item.id === job.id);
    const current = index < 0 ? null : state.jobs[index];
        if (current && isTerminal(current) && !isTerminal(job)) return;
    if (current && current.status === "processing" && job.status === "queued") {
      job.progress = null;
      pendingProgress.delete(job.id);
    } else if (current && !job.progress && !isTerminal(job) && current.status === job.status) {
      job.progress = current.progress;
    }
    if (isTerminal(job)) pendingProgress.delete(job.id);
    state.realtimeVersion += 1;
    if (state.jobsLoading) state.realtimeChanges.set(job.id, { version: state.realtimeVersion, job });
    const previousStatus = state.knownJobStatuses.get(job.id);
    if (index < 0) {
      state.jobs.unshift(job);
      state.jobsPagination.total += 1;
    } else {
      state.jobs[index] = job;
    }
    if (previousStatus && previousStatus !== job.status) {
      if (job.status === "completed") {
        Growl.success({
          title: "음악 생성 완료",
          message: `"${job.title}" 생성이 완료되었습니다!`,
          duration: 6500,
          action: {
            label: "지금 재생",
            onClick: () => playTrack(job, state.jobs.filter((item) => item.status === "completed"))
          }
        });
      } else if (job.status === "failed") {
        Growl.error({ title: "음악 생성 실패", message: "곡을 만들지 못했습니다. 잠시 후 다시 시도해 주세요.", duration: 7000 });
      }
    }
    state.knownJobStatuses.set(job.id, job.status);
    if (job.status === "completed" && previousStatus !== "completed") {
      state.library.loaded = false;
      if (state.view === "library") loadLibrary();
    }
    renderJobs({ preserveScroll: true });
    if (index < 0 || previousStatus !== job.status) QueueManager.refreshSoon();
  }

  const pendingProgress = new Map();
  let progressFrame = null;

  function applyProgressUpdates(updates) {
    if (!updates || typeof updates !== "object") return;
    for (const [id, progress] of Object.entries(updates)) {
      if (!progress || typeof progress !== "object") continue;
      pendingProgress.set(id, progress);
    }
    if (pendingProgress.size && progressFrame === null) {
      progressFrame = window.requestAnimationFrame(flushProgressUpdates);
    }
  }

  function flushProgressUpdates() {
    progressFrame = null;
    const updates = Array.from(pendingProgress);
    pendingProgress.clear();
    for (const [id, progress] of updates) {
      const job = state.jobs.find((item) => item.id === id);
      if (job && !isTerminal(job)) {
        job.progress = progress;
        const card = Array.from(refs.jobsList.querySelectorAll(".job-card"))
          .find((candidate) => candidate.dataset.trackId === id);
        if (card) syncJobProgress(card, job);
      }
      QueueManager.applyProgress(id, progress);
    }
    if (updates.length) QueueManager.refreshSoon();
  }

  async function loadMoreJobs() {
    if (state.jobsPagination.loadingMore || !state.jobsPagination.hasMore || state.jobsLoading) return;
    state.jobsPagination.loadingMore = true;
    updateJobsPagination();

    const nextOffset = state.jobs.length;
    const limit = 20;

    try {
      const payload = await fetchJson(`/api/jobs?limit=${limit}&offset=${nextOffset}&paged=1`, {
        headers: { Accept: "application/json" }
      });
      const list = extractList(payload, ["jobs", "items", "generations", "data"]);
      const nextBatch = list.map(normalizeJob);
      const existingIds = new Set(state.jobs.map((j) => j.id));
      const freshItems = nextBatch.filter((j) => !existingIds.has(j.id));
      state.jobs = state.jobs.concat(freshItems);

      const total = typeof payload?.total === "number" ? payload.total : state.jobs.length;
      state.jobsPagination.total = total;
      state.jobsPagination.offset = nextOffset;
      state.jobsPagination.hasMore = Boolean(payload?.has_more !== undefined ? payload.has_more : state.jobs.length < total) && freshItems.length > 0;
      freshItems.forEach((job) => state.knownJobStatuses.set(job.id, job.status));
    } catch {
      showToast("이전 작업을 추가로 불러오지 못했습니다.", "error");
    } finally {
      state.jobsPagination.loadingMore = false;
      renderJobs({ preserveScroll: true });
    }
  }

  function updateJobsPagination() {
    if (!refs.jobsPaginationWrap) return;
    const { total, hasMore, loadingMore } = state.jobsPagination;
    const query = refs.workspaceSearch ? refs.workspaceSearch.value.trim() : "";
    const filter = refs.workspaceFilter ? refs.workspaceFilter.value : "all";
    const isFiltered = Boolean(query) || filter !== "all";

    if (state.jobs.length === 0) {
      refs.jobsPaginationWrap.hidden = true;
      return;
    }

    refs.jobsPaginationWrap.hidden = false;
    if (refs.jobsLoadMore) {
      refs.jobsLoadMore.hidden = !hasMore || isFiltered;
      refs.jobsLoadMore.disabled = loadingMore;
      refs.jobsLoadMore.classList.toggle("is-loading", loadingMore);
      const remaining = Math.max(0, total - state.jobs.length);
      if (refs.jobsLoadMoreText) {
        refs.jobsLoadMoreText.textContent = loadingMore
          ? "불러오는 중…"
          : remaining > 0
          ? `이전 작업 20곡 더보기 (${remaining}곡 남음)`
          : "이전 작업 더보기";
      }
    }
    if (refs.jobsEndMarker) {
      refs.jobsEndMarker.hidden = hasMore || isFiltered || state.jobs.length === 0;
      const endText = $(".jobs-end-text", refs.jobsEndMarker);
      if (endText) {
        endText.textContent = `모든 작업 기록을 불러왔습니다 (총 ${total}곡)`;
      }
    }
  }

  let jobsObserver = null;
  function setupJobsInfiniteScroll() {
    if (!("IntersectionObserver" in window) || !refs.jobsPaginationWrap) return;
    if (jobsObserver) jobsObserver.disconnect();
    jobsObserver = new IntersectionObserver((entries) => {
      const entry = entries[0];
      if (entry && entry.isIntersecting && state.jobsPagination.hasMore && !state.jobsPagination.loadingMore && !state.jobsLoading) {
        loadMoreJobs();
      }
    }, {
      root: refs.jobsList,
      rootMargin: "150px 0px"
    });
    jobsObserver.observe(refs.jobsPaginationWrap);
  }

  function renderJobs({ preserveScroll = false } = {}) {
    const query = refs.workspaceSearch.value.trim().toLocaleLowerCase();
    const filter = refs.workspaceFilter.value;
    const jobs = state.jobs.filter((job) => {
      const matchesText = `${job.title} ${job.style}`.toLocaleLowerCase().includes(query);
      const matchesStatus = filter === "all" || (filter === "active" ? !isTerminal(job) : job.status === filter);
      return matchesText && matchesStatus;
    });
    const total = state.jobsPagination.total || state.jobs.length;
    if (total > jobs.length && !query && filter === "all") {
      refs.jobsCount.textContent = `${jobs.length} / 전체 ${total}곡`;
    } else {
      refs.jobsCount.textContent = `${jobs.length}곡`;
    }
    if (state.jobsLoading && state.jobs.length === 0) {
      refs.jobsList.innerHTML = "";
      refs.jobsList.append(
        element("div", { className: "jobs-loading", attrs: { "aria-hidden": "true" } }, [
          element("span", { className: "skeleton-line skeleton-line-wide" }),
          element("span", { className: "skeleton-line" }),
          element("span", { className: "skeleton-line skeleton-line-short" })
        ])
      );
      if (refs.jobsPaginationWrap) refs.jobsPaginationWrap.hidden = true;
    } else if (jobs.length === 0) {
      refs.jobsList.innerHTML = "";
      refs.jobsList.append(
        element("div", { className: "jobs-empty" }, [
          element("strong", { text: query || filter !== "all" ? "조건에 맞는 곡이 없습니다" : "아직 만든 곡이 없습니다" }),
          element("span", { text: query || filter !== "all" ? "검색어나 상태 필터를 바꿔 보세요." : "왼쪽에서 스타일을 입력해 곡을 만들어 보세요." })
        ])
      );
      if (refs.jobsPaginationWrap) refs.jobsPaginationWrap.hidden = true;
    } else {
      const prevScrollTop = preserveScroll ? refs.jobsList.scrollTop : null;
      refs.jobsList.innerHTML = "";
      jobs.forEach((job) => refs.jobsList.append(createJobCard(job)));
      if (refs.jobsPaginationWrap) {
        refs.jobsList.append(refs.jobsPaginationWrap);
      }
      if (prevScrollTop !== null) {
        refs.jobsList.scrollTop = prevScrollTop;
      }
    }
    refs.jobsError.hidden = !state.jobsError;
    refs.jobsError.textContent = state.jobsError;
    updateJobsPagination();
    syncPlayerButtons();
  }

  const progressStageLabels = {
    original: ["ABC", "Music Token Sampling", "KSampler"],
    cover: ["Sheet (Audio to ABC)", "Music Token Sampling", "KSampler"]
  };

  function generationProgress(mode, progress = {}) {
    const phase = progress?.phase;
    const stage = phase === "abc" || phase === "sheet" ? 0 : phase === "music" ? 1 : phase === "rendering" ? 2 : -1;
    const current = Number(progress?.current);
    const total = Number(progress?.total);
    const fraction = Number.isFinite(current) && Number.isFinite(total) && total > 0
      ? Math.max(0, Math.min(1, current / total)) : 0;
    const percent = phase === "finishing" ? 99 : stage < 0 ? 0 : Math.round(stage * 33 + fraction * 33);
    const labels = progressStageLabels[normalizeMode(mode)];
    const status = phase === "finishing" ? "저장 중" : stage < 0 ? "준비 중" : labels[stage];
    return { percent, status, labels };
  }

  function createGenerationProgress(mode, progress, className = "") {
    const section = element("div", { className: `generation-progress ${className}` }, [
      element("div", { className: "generation-progress-head" }, [
        element("span", { className: "generation-progress-status" }),
        element("span", { className: "generation-progress-percent" })
      ]),
      element("div", { className: "generation-progress-segments", attrs: { "aria-hidden": "true" } },
        Array.from({ length: 3 }, () => element("span", { className: "generation-progress-segment" }, [
          element("span", { className: "generation-progress-fill" })
        ]))),
      element("div", { className: "generation-progress-labels", attrs: { "aria-hidden": "true" } },
        Array.from({ length: 3 }, () => element("span")))
    ]);
    updateGenerationProgress(section, mode, progress);
    return section;
  }

  function updateGenerationProgress(section, mode, progress) {
    const display = generationProgress(mode, progress);
    section.setAttribute("role", "progressbar");
    section.setAttribute("aria-label", `음악 생성: ${display.status}`);
    section.setAttribute("aria-valuemin", "0");
    section.setAttribute("aria-valuemax", "100");
    section.setAttribute("aria-valuenow", String(display.percent));
    $(".generation-progress-status", section).textContent = display.status;
    $(".generation-progress-percent", section).textContent = `${display.percent}%`;
    $$(".generation-progress-fill", section).forEach((fill, index) => {
      fill.style.transform = `scaleX(${Math.max(0, Math.min(1, (display.percent - index * 33) / 33))})`;
    });
    $$(".generation-progress-labels span", section).forEach((label, index) => {
      label.textContent = display.labels[index];
      label.classList.toggle("is-current", display.status === display.labels[index]);
    });
  }

  function syncJobProgress(card, job) {
    if (job.status !== "processing") return;
    const copy = $(".job-copy", card);
    if (!copy) return;
    let section = $(".job-progress", copy);
    if (!section) {
      section = createGenerationProgress(job.mode, job.progress, "job-progress");
      copy.append(section);
    } else {
      updateGenerationProgress(section, job.mode, job.progress);
    }
  }

  async function cancelJob(job) {
    if (!job || !job.id) return;
    if (job.status !== "queued") {
      showToast("대기열에 있는 작업만 취소할 수 있습니다.", "error");
      return;
    }
    const title = job.title || "음악";
    const confirmed = window.confirm(`"${title}" 생성을 취소하시겠습니까?`);
    if (!confirmed) return;
    try {
      const updated = await fetchJson(`/api/jobs/${encodeURIComponent(job.id)}/cancel`, {
        method: "POST"
      });
      showToast("대기열에서 취소되었습니다.", "info");
      if (updated) applyJobUpdate(updated);
      if (typeof QueueManager !== "undefined") QueueManager.poll(true);
    } catch (error) {
      showToast(error.message || "취소하지 못했습니다.", "error");
    }
  }

  function createJobCard(job) {
    const statusClass = job.status === "completed" ? "is-complete" : job.status === "failed" ? "is-failed" : job.status === "cancelled" ? "is-cancelled" : "is-working";
    const title = element("h3", { className: "job-title", text: job.title });
    const badge = element("span", { className: `status-badge ${statusClass}`, text: statusLabel(job.status) });
    const playable = job.status === "completed" && safeMediaUrl(job.audioUrl);
    const artwork = element(playable ? "button" : "div", {
      className: "job-art",
      attrs: playable ? { type: "button", "aria-label": `${job.title} 재생`, "data-play-id": job.id } : { "aria-hidden": "true" },
      on: playable ? { click: () => playTrack(job, state.jobs.filter((item) => item.status === "completed")) } : {}
    }, [svgIcon(playable ? "play" : "wave")]);
    applyArtwork(artwork, job.id);
    applyCover(artwork, job);
    const shortStyle = safeText(job.style).split(",").map((part) => part.trim()).filter(Boolean).slice(0, 3).join(" · ");
    const copy = element("div", { className: "job-copy" }, [
      title,
      shortStyle ? element("p", { className: "job-style", text: shortStyle, attrs: { title: job.style } }) : null,
      element("div", { className: "job-card-meta" }, [
        element("span", { text: modeLabel(job.mode) }),
        element("span", { text: "·" }),
        element("span", { text: formatRelative(job.createdAt) })
      ])
    ]);
    const foot = element("div", { className: "job-card-foot" }, [badge]);
    const card = element("article", { className: "job-card", attrs: { "data-track-id": job.id } }, [artwork, copy, foot]);
    syncJobProgress(card, job);

    if (job.status === "failed") {
      copy.append(element("p", { className: "job-error", text: "곡을 만들지 못했습니다. 잠시 후 다시 시도해 주세요." }));
    } else if (job.status === "queued") {
      foot.append(element("button", {
        className: "job-cancel-btn",
        attrs: { type: "button", title: "대기열 취소" },
        text: "대기열 취소",
        on: {
          click: (event) => {
            event.stopPropagation();
            cancelJob(job);
          }
        }
      }));
    } else if (job.status === "completed") {
      const action = element("button", {
        className: "library-action",
        attrs: { type: "button" },
        on: { click: () => openPublishDialog(job) }
      }, [svgIcon("library"), element("span", { text: job.published ? "공개 정보 수정" : "라이브러리에 공개" })]);
      foot.append(action);
      if (job.published) {
        foot.append(element("button", {
          className: "library-action",
          attrs: { type: "button" },
          on: { click: () => unpublishJob(job) }
        }, [element("span", { text: "공개 취소" })]));
      }
    }
    return card;
  }

  function hashString(value) {
    let hash = 2166136261;
    const text = String(value);
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }

  function artworkColors(id) {
    const palettes = [
      ["#e1a17b", "#6b3e58", "#241c37"],
      ["#9ab9db", "#34597c", "#121e36"],
      ["#d9b775", "#786a38", "#293b36"],
      ["#baa6df", "#655393", "#28233d"],
      ["#db868c", "#96394c", "#391d32"],
      ["#77bbbd", "#386975", "#182e40"]
    ];
    return palettes[hashString(id) % palettes.length];
  }

  function applyArtwork(node, id) {
    artworkColors(id).forEach((color, index) => node.style.setProperty(`--art-${"abc"[index]}`, color));
  }

  function applyCover(node, track) {
    const url = safeMediaUrl(track.coverUrl);
    node.classList.toggle("has-custom-cover", Boolean(url));
    node.style.backgroundImage = url ? `url("${url}")` : "";
  }

  function formatTime(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
    return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
  }

  function syncPlayerButtons() {
    const playing = Boolean(state.playerTrack) && !refs.player.paused && !refs.player.ended;
    const hasTrack = Boolean(state.playerTrack);
    refs.playerBar.hidden = !hasTrack;
    refs.playerBar.inert = !playing;
    refs.playerBar.setAttribute("aria-hidden", String(!playing));
    document.body.classList.toggle("is-playing", playing);
    if (playing) {
      AudioVisualizer.start();
    } else {
      AudioVisualizer.pause();
    }
    refs.playerToggle.disabled = !state.playerTrack;
    refs.playerToggle.setAttribute("aria-label", playing ? "일시정지" : "재생");
    $("use", refs.playerToggle).setAttribute("href", playing ? "#icon-pause" : "#icon-play");
    const index = state.playerQueue.findIndex((track) => track.id === state.playerTrack?.id);
    refs.playerPrev.disabled = index <= 0;
    refs.playerNext.disabled = index < 0 || index >= state.playerQueue.length - 1;
    $$('[data-play-id]').forEach((button) => {
      const active = playing && button.dataset.playId === state.playerTrack?.id;
      const title = button.dataset.trackTitle || button.closest(".job-card")?.querySelector(".job-title")?.textContent || "음악";
      button.setAttribute("aria-label", `${title} ${active ? "일시정지" : "재생"}`);
      const iconUse = $("use", button);
      if (iconUse) iconUse.setAttribute("href", active ? "#icon-pause" : "#icon-play");
    });
    $$(".job-card, .track-card").forEach((card) => {
      const isCardActive = playing && (card.dataset.trackId === state.playerTrack?.id || Boolean(card.querySelector(`[data-play-id="${state.playerTrack?.id}"]`)));
      card.classList.toggle("is-playing-card", isCardActive);
    });
  }

  function syncPlayerTime() {
    const duration = refs.player.duration;
    const current = refs.player.currentTime;
    refs.playerElapsed.textContent = formatTime(current);
    refs.playerDuration.textContent = formatTime(duration);
    refs.playerProgress.disabled = !Number.isFinite(duration) || duration <= 0;
    refs.playerProgress.value = refs.playerProgress.disabled ? "0" : String(Math.round(current / duration * 1000));
    refs.playerProgress.setAttribute("aria-valuetext", `${formatTime(current)} / ${formatTime(duration)}`);
    if (Number.isFinite(duration) && duration > 0) {
      checkCutoffEnding(state.playerTrack, duration);
    }
  }

  async function resumePlayer() {
    AudioVisualizer.ensureAudioContext();
    try {
      await refs.player.play();
    } catch (error) {
      if (error.name !== "AbortError") showToast("음악을 재생하지 못했어요. 다시 시도해 주세요.", "error");
    }
    syncPlayerButtons();
  }

  function playTrack(track, queue) {
    const url = safeMediaUrl(track.audioUrl);
    if (!url) return;
    state.playerQueue = queue.filter((item) => safeMediaUrl(item.audioUrl));
    if (state.playerTrack?.id === track.id) {
      if (refs.player.paused) resumePlayer();
      else refs.player.pause();
      syncPlayerButtons();
      return;
    }
    state.playerTrack = track;
    if (track.published && window.yue2Auth?.ready) {
      void fetchJson(`/api/tracks/${encodeURIComponent(track.id)}/play`, { method: "POST" })
        .then(() => { state.libraryHomeLoaded = false; }).catch(() => {});
    }
    const colors = artworkColors(track.id);
    document.body.style.setProperty("--art-a", colors[0]);
    document.body.style.setProperty("--art-b", colors[1]);
    document.body.style.setProperty("--art-c", colors[2]);
    if (refs.ambientBackdrop) {
      refs.ambientBackdrop.style.setProperty("--art-a", colors[0]);
      refs.ambientBackdrop.style.setProperty("--art-b", colors[1]);
      refs.ambientBackdrop.style.setProperty("--art-c", colors[2]);
    }
    refs.player.src = url;
    refs.playerTitle.textContent = track.title;
    refs.playerSubtitle.textContent = track.style || modeLabel(track.mode);
    refs.playerArt.classList.add("has-track");
    applyArtwork(refs.playerArt, track.id);
    applyCover(refs.playerArt, track);
    syncPlayerTime();
    syncPlayerButtons();
    resumePlayer();
    AudioVisualizer.start();
  }

  function stepPlayer(direction) {
    const index = state.playerQueue.findIndex((track) => track.id === state.playerTrack?.id);
    const track = state.playerQueue[index + direction];
    if (index >= 0 && track) playTrack(track, state.playerQueue);
  }

  function safeMediaUrl(value) {
    const raw = safeText(value).trim();
    if (!raw) return "";
    try {
      const resolved = resolvePath(raw);
      const url = new URL(resolved, window.location.origin);
      if (["http:", "https:", "blob:"].includes(url.protocol)) return url.href;
      return "";
    } catch {
      return "";
    }
  }

  function renderLibrarySkeletons() {
    refs.libraryGrid.innerHTML = "";
    for (let index = 0; index < 3; index += 1) {
      refs.libraryGrid.append(element("div", { className: "track-skeleton", attrs: { "aria-hidden": "true" } }));
    }
  }

  function renderEmptyLibrary(isFiltered) {
    refs.libraryGrid.innerHTML = "";
    refs.libraryGrid.append(
      element("div", { className: "empty-state" }, [
        element("div", { className: "empty-state-inner" }, [
          element("span", { className: "empty-state-mark", attrs: { "aria-hidden": "true" } }, [svgIcon(isFiltered ? "search" : "title")]),
          element("h2", { text: isFiltered ? "검색 결과가 없습니다" : "아직 공개된 곡이 없습니다" }),
          element("p", { text: isFiltered ? "검색어나 필터를 바꿔 보세요." : "내 스튜디오에서 완성한 곡을 선택해 공개하세요." }),
          isFiltered ? null : element("a", { className: "new-track-link", text: "내 스튜디오", attrs: { href: "#create" } })
        ])
      ])
    );
  }

  function renderLibrary() {
    if (state.view !== "library" || libraryParams().get("view") !== "all") return;
    const searching = Boolean(state.library.query.trim());
    refs.libraryGrid.hidden = searching;
    refs.libraryContent.hidden = !searching;
    if (state.library.loading) {
      refs.libraryStatus.textContent = "음악을 불러오는 중…";
      if (searching) refs.libraryContent.replaceChildren(element("p", { className: "library-loading", text: "검색 결과를 불러오는 중…" }));
      else renderLibrarySkeletons();
      return;
    }
    if (state.library.error) {
      refs.libraryStatus.textContent = "";
      if (searching) refs.libraryContent.replaceChildren(element("div", { className: "library-landing-empty" }, [
        element("h2", { text: "검색 결과를 불러오지 못했습니다" }),
        element("button", { className: "library-secondary-action", text: "다시 검색", attrs: { type: "button" }, on: { click: () => loadLibrary() } })
      ]));
      if (searching) return;
      refs.libraryGrid.replaceChildren(element("div", { className: "empty-state" }, [
        element("div", { className: "empty-state-inner" }, [
          element("h2", { text: "곡 목록을 불러오지 못했습니다" }),
          element("button", { className: "new-track-link", text: "다시 불러오기", attrs: { type: "button" }, on: { click: () => loadLibrary() } })
        ])
      ]));
      return;
    }
    if (searching) {
      renderLibrarySearchResults();
      return;
    }
    refs.libraryContent.replaceChildren();
    const isFiltered = Boolean(state.library.query.trim()) || state.library.mode !== "all";
    if (state.library.items.length === 0) {
      refs.libraryStatus.textContent = "";
      renderEmptyLibrary(isFiltered);
      return;
    }
    refs.libraryStatus.textContent = `${state.library.items.length}개의 음악`;
    refs.libraryGrid.innerHTML = "";
    state.library.items.forEach((track) => refs.libraryGrid.append(createTrackCard(track)));
    syncPlayerButtons();
    focusLibraryTrack();
  }

  function libraryParams() {
    return new URLSearchParams(window.location.hash.split("?")[1] || "");
  }

  function librarySection(title, subtitle = "") {
    const heading = element("div", { className: "library-section-heading" }, [
      element("h2", { text: title }), subtitle ? element("span", { text: subtitle }) : null
    ]);
    return element("section", { className: "library-section" }, [heading]);
  }

  function releaseTile(item, type = "track") {
    const isAlbum = type === "album";
    const track = isAlbum ? null : item;
    const art = element("div", { className: "release-art" }, [svgIcon(isAlbum ? "library" : "wave")]);
    applyArtwork(art, item.id);
    applyCover(art, { coverUrl: item.cover_url || track?.coverUrl });
    const tile = element("a", {
      className: "release-tile",
      attrs: { href: isAlbum ? `#library?album=${encodeURIComponent(item.id)}` : `#library?single=${encodeURIComponent(track.id)}` }
    }, [art, element("strong", { text: item.title }),
      element("span", { text: isAlbum ? item.artist_name : track.creator }),
      element("small", { text: isAlbum ? `앨범 · ${item.track_count}곡` : track.albumId ? "앨범 수록곡" : "싱글" })]);
    return tile;
  }

  function chartRow(track, rank, queue) {
    const art = element("div", { className: "chart-art" }, [svgIcon("play")]);
    applyArtwork(art, track.id);
    applyCover(art, track);
    return element("div", { className: "chart-row" }, [
      element("span", { className: "chart-rank", text: String(rank) }),
      element("button", { className: "chart-play", attrs: { type: "button", "aria-label": `${track.title} 재생` },
        on: { click: () => playTrack(track, queue) } }, [art]),
      element("div", { className: "chart-copy" }, [
        element("strong", { text: track.title }),
        track.artistId ? element("a", { text: track.creator, attrs: { href: `#library?artist=${encodeURIComponent(track.artistId)}` } })
          : element("span", { text: track.creator })
      ]),
      element("span", { className: "chart-plays", text: `${track.playCount.toLocaleString("ko-KR")}회` }),
      element("button", { className: "chart-remix", text: "가져오기", attrs: { type: "button" },
        on: { click: () => importRecipe(track) } })
    ]);
  }

  function artistTile(artist) {
    const url = safeMediaUrl(artist.avatar_url);
    const art = element("div", { className: "artist-tile-art" },
      url ? [] : [element("span", { text: artist.name.slice(0, 1) })]);
    if (url) art.style.backgroundImage = `url("${url}")`;
    return element("a", { className: "artist-tile", attrs: { href: `#library?artist=${artist.id}` } }, [
      art, element("strong", { text: artist.name }), element("span", { text: `${artist.track_count}곡 공개` })
    ]);
  }

  function renderLibrarySearchResults() {
    const query = state.library.query.trim().toLocaleLowerCase();
    const home = state.libraryHome || {};
    const artists = (home.artists || []).filter((item) => item.name.toLocaleLowerCase().includes(query));
    const albums = (home.albums || []).filter((item) => `${item.title} ${item.artist_name}`.toLocaleLowerCase().includes(query));
    const tracks = state.library.items;
    refs.libraryStatus.textContent = `${tracks.length + artists.length + albums.length}개의 검색 결과`;
    refs.libraryContent.replaceChildren();
    if (tracks.length) {
      const section = librarySection("인기 검색 결과");
      const grid = element("div", { className: "library-search-results" });
      tracks.slice(0, 6).forEach((track) => {
        const art = element("div", { className: "search-result-art" }, [svgIcon("wave")]);
        applyArtwork(art, track.id); applyCover(art, track);
        grid.append(element("a", { className: "search-result", attrs: { href: `#library?single=${encodeURIComponent(track.id)}` } }, [
          art, element("div", { className: "search-result-copy" }, [
            element("strong", { text: track.title }), element("span", { text: `노래 · ${track.creator}` })
          ]), svgIcon("play")
        ]));
      });
      section.append(grid); refs.libraryContent.append(section);
    }
    if (artists.length) {
      const section = librarySection("아티스트");
      const grid = element("div", { className: "artist-grid" });
      artists.forEach((artist) => grid.append(artistTile(artist)));
      section.append(grid); refs.libraryContent.append(section);
    }
    if (albums.length) {
      const section = librarySection("앨범");
      const grid = element("div", { className: "release-grid" });
      albums.forEach((album) => grid.append(releaseTile(album, "album")));
      section.append(grid); refs.libraryContent.append(section);
    }
    if (!tracks.length && !artists.length && !albums.length) {
      refs.libraryContent.append(element("div", { className: "library-landing-empty" }, [
        element("h2", { text: "검색 결과가 없습니다" }),
        element("p", { text: "다른 노래, 앨범 또는 아티스트 이름으로 검색해 보세요." })
      ]));
    }
  }

  function renderLibraryHome(data, page = "discover") {
    const releases = (data.new_releases || []).map(normalizeTrack);
    const thisWeek = (data.this_week || []).map(normalizeTrack);
    const charts = (data.charts || []).map(normalizeTrack);
    const albums = data.albums || [];
    const artists = data.artists || [];
    refs.libraryContent.replaceChildren();
    const featured = librarySection(page === "new" ? "지금 주목할 음악" : "인기 추천곡");
    const featureGrid = element("div", { className: "feature-grid" });
    const featuredItems = [...albums.slice(0, page === "new" ? 1 : 2).map((item) => ({ type: "album", item })),
      ...releases.slice(0, 5).map((item) => ({ type: "track", item }))].slice(0, page === "new" ? 3 : 5);
    featuredItems.forEach(({ type, item }) => featureGrid.append(releaseTile(item, type)));
    if (featuredItems.length) { featured.append(featureGrid); refs.libraryContent.append(featured); }

    if (page === "discover" && releases.length) {
      const section = librarySection("최근 공개된 음악");
      const grid = element("div", { className: "release-grid" });
      releases.slice(0, 6).forEach((track) => grid.append(releaseTile(track)));
      section.append(grid);
      refs.libraryContent.append(section);
    }
    if (charts.length) {
      const section = librarySection(page === "new" ? "인기 신곡" : "인기 곡");
      const list = element("div", { className: "chart-grid" });
      charts.slice(0, 12).forEach((track, index) => list.append(chartRow(track, index + 1, charts)));
      section.append(list);
      refs.libraryContent.append(section);
    }
    if (thisWeek.length && page === "new") {
      const section = librarySection("이번 주 신곡");
      const grid = element("div", { className: "release-grid" });
      thisWeek.slice(0, 8).forEach((track) => grid.append(releaseTile(track)));
      section.append(grid);
      refs.libraryContent.append(section);
    }
    if (albums.length) {
      const section = librarySection("앨범");
      const grid = element("div", { className: "release-grid" });
      albums.slice(0, 8).forEach((album) => grid.append(releaseTile(album, "album")));
      section.append(grid);
      refs.libraryContent.append(section);
    }
    if (artists.length && page === "discover") {
      const section = librarySection("아티스트");
      const grid = element("div", { className: "artist-grid" });
      artists.forEach((artist) => grid.append(artistTile(artist)));
      section.append(grid);
      refs.libraryContent.append(section);
    }
    if (!featuredItems.length && !charts.length && !thisWeek.length && !albums.length && !artists.length) {
      refs.libraryContent.append(element("div", { className: "library-landing-empty" }, [
        element("h2", { text: "아직 공개된 곡이 없습니다" }),
        element("p", { text: "내 스튜디오에서 완성한 곡을 선택해 공개하세요." }),
        element("a", { className: "new-track-link", text: "내 스튜디오", attrs: { href: "#create" } })
      ]));
    }
  }

  function renderLibraryDetail(data, kind) {
    refs.libraryContent.replaceChildren();
    refs.libraryContent.append(element("a", { className: "library-back", text: "‹  라이브러리", attrs: { href: "#library" } }));
    if (kind === "single") {
      const track = normalizeTrack(data);
      const hero = element("div", { className: "album-hero" });
      const art = element("div", { className: "album-hero-art" }, [svgIcon("wave")]);
      applyArtwork(art, track.id); applyCover(art, track);
      hero.append(art, element("div", { className: "album-hero-copy" }, [
        element("h2", { text: track.title }),
        track.artistId ? element("a", { text: track.creator, attrs: { href: `#library?artist=${encodeURIComponent(track.artistId)}` } }) : null,
        element("p", { className: "album-meta", text: "싱글" }),
        element("p", { text: track.style })]));
      refs.libraryContent.append(hero);
      const actions = element("div", { className: "single-actions" }, [
        element("button", { className: "library-play-all", attrs: { type: "button" }, on: { click: () => playTrack(track, [track]) } }, [svgIcon("play"), element("span", { text: "재생" })]),
        element("button", { className: "library-secondary-action", text: "내 스튜디오로 가져오기", attrs: { type: "button" }, on: { click: () => importRecipe(track) } })
      ]);
      refs.libraryContent.append(actions);
      if (data.lyrics) {
        const section = librarySection("가사");
        section.append(element("pre", { className: "single-lyrics", text: data.lyrics }));
        refs.libraryContent.append(section);
      }
      return;
    }
    const tracks = (data.tracks || []).map(normalizeTrack);
    if (kind === "artist") {
      const artist = data.artist;
      const hero = element("div", { className: "artist-hero" });
      const banner = safeMediaUrl(artist.banner_url);
      if (banner) hero.style.backgroundImage = `linear-gradient(0deg,#14121a 2%,transparent),url("${banner}")`;
      const avatar = element("div", { className: "artist-hero-avatar", text: artist.name.slice(0, 1) });
      const avatarUrl = safeMediaUrl(artist.avatar_url);
      if (avatarUrl) { avatar.style.backgroundImage = `url("${avatarUrl}")`; avatar.textContent = ""; }
      hero.append(avatar, element("div", {}, [
        element("h2", { text: artist.name }), artist.bio ? element("p", { text: artist.bio }) : null,
        element("span", { text: `${tracks.length}곡 공개` })]));
      refs.libraryContent.append(hero);
      if (data.albums?.length) {
        const section = librarySection("앨범");
        const grid = element("div", { className: "release-grid" });
        data.albums.forEach((album) => grid.append(releaseTile(album, "album")));
        section.append(grid); refs.libraryContent.append(section);
      }
    } else {
      const album = data.album;
      const hero = element("div", { className: "album-hero" });
      const art = element("div", { className: "album-hero-art" }, [svgIcon("library")]);
      applyArtwork(art, album.id); applyCover(art, { coverUrl: album.cover_url });
      hero.append(art, element("div", { className: "album-hero-copy" }, [
        element("h2", { text: album.title }),
        element("a", { text: album.artist_name, attrs: { href: `#library?artist=${album.artist_id}` } }),
        element("p", { className: "album-meta", text: `앨범 · ${tracks.length}곡` }),
        album.description ? element("p", { text: album.description }) : null,
        tracks.length ? element("div", { className: "album-hero-actions" }, [
          element("button", { className: "library-play-all", attrs: { type: "button" }, on: { click: () => playTrack(tracks[0], tracks) } }, [svgIcon("play"), element("span", { text: "재생" })]),
          element("button", { className: "library-secondary-action", attrs: { type: "button" }, on: { click: () => playTrack(tracks[Math.floor(Math.random() * tracks.length)], tracks) } }, [svgIcon("shuffle"), element("span", { text: "임의 재생" })])
        ]) : null]));
      refs.libraryContent.append(hero);
    }
    const section = librarySection(kind === "artist" ? "공개한 음악" : "수록곡");
    const grid = element("div", { className: kind === "album" ? "album-track-list" : "library-grid" });
    tracks.forEach((track, index) => grid.append(kind === "album" ? element("div", { className: "album-track-row" }, [
      element("span", { className: "album-track-number", text: String(index + 1) }),
      element("button", { className: "album-track-main", attrs: { type: "button", "aria-label": `${track.title} 재생` }, on: { click: () => playTrack(track, tracks) } }, [
        element("strong", { text: track.title }), element("span", { text: track.creator })
      ]),
      element("button", { className: "album-track-remix", attrs: { type: "button", "aria-label": `${track.title} 내 스튜디오로 가져오기` }, on: { click: () => importRecipe(track) } }, [svgIcon("more")])
    ]) : createTrackCard(track)));
    if (!tracks.length) grid.append(element("p", { className: "page-description", text: "공개된 음악이 없습니다." }));
    section.append(grid);
    refs.libraryContent.append(section);
  }

  async function renderLibraryPage() {
    const params = libraryParams();
    const detail = params.has("artist") ? "artist" : params.has("album") ? "album" : params.has("single") ? "single" : "";
    const tab = detail ? "" : params.get("view") || "discover";
    const requestId = ++state.libraryPageRequestId;
    refs.libraryView.classList.toggle("is-detail", Boolean(detail));
    refs.libraryView.classList.toggle("is-album-detail", detail === "album");
    refs.libraryView.classList.toggle("is-new-music", tab === "new");
    $("#library-title").textContent = tab === "new" ? "새로운 음악" : tab === "charts" ? "차트" : tab === "all" ? "검색" : "홈";
    $("#library-description").textContent = tab === "all" ? "공개된 음악을 찾아보세요." : tab === "charts" ? "많이 재생된 음악을 만나보세요." : tab === "new" ? "새로 공개된 음악을 만나보세요." : "공개된 음악을 만나보세요.";
    refs.libraryTabs.forEach((link) => link.classList.toggle("is-selected", link.dataset.libraryTab === tab));
    const all = tab === "all";
    refs.libraryToolbar.hidden = !all;
    refs.libraryStatus.hidden = !all;
    refs.libraryGrid.hidden = !all || Boolean(state.library.query.trim());
    refs.libraryContent.hidden = all && !state.library.query.trim();
    if (all) {
      if (!state.library.loaded && !state.library.loading) loadLibrary();
      else renderLibrary();
      return;
    }
    refs.libraryContent.replaceChildren(element("p", { className: "library-loading", text: "음악을 불러오는 중…" }));
    try {
      if (detail) {
        const id = params.get(detail);
        const data = await fetchJson(detail === "single" ? `/api/library/tracks/${encodeURIComponent(id)}`
          : `/api/${detail === "artist" ? "artists" : "albums"}/${encodeURIComponent(id)}`);
        if (requestId === state.libraryPageRequestId) renderLibraryDetail(data, detail);
      } else if (tab === "charts") {
        const data = await fetchJson("/api/library/charts");
        if (requestId !== state.libraryPageRequestId) return;
        const tracks = data.map(normalizeTrack);
        const section = librarySection("인기 차트", "재생 수 기준");
        const list = element("div", { className: "chart-grid" });
        tracks.forEach((track, index) => list.append(chartRow(track, index + 1, tracks)));
        if (tracks.length) section.append(list);
        else section.append(element("div", { className: "library-landing-empty" }, [
          element("h2", { text: "아직 차트에 표시할 곡이 없습니다" }),
          element("p", { text: "곡이 공개되면 재생 수에 따라 순위가 표시됩니다." }),
          element("a", { className: "new-track-link", text: "내 스튜디오", attrs: { href: "#create" } })
        ]));
        refs.libraryContent.replaceChildren(section);
      } else {
        if (!state.libraryHomeLoaded) {
          state.libraryHome = await fetchJson("/api/library/discover");
          state.libraryHomeLoaded = true;
        }
        if (requestId === state.libraryPageRequestId) renderLibraryHome(state.libraryHome, tab);
      }
    } catch (error) {
      if (requestId === state.libraryPageRequestId) refs.libraryContent.replaceChildren(
        element("div", { className: "library-landing-empty" }, [
          element("h2", { text: "라이브러리를 불러오지 못했습니다" }),
          element("button", { className: "new-track-link", text: "다시 불러오기", attrs: { type: "button" }, on: { click: () => renderLibraryPage() } })
        ])
      );
    }
  }

  function createTrackCard(track) {
    const colors = artworkColors(track.id);
    const artwork = element("div", { className: "artwork" });
    artwork.style.setProperty("--art-a", colors[0]);
    artwork.style.setProperty("--art-b", colors[1]);
    artwork.style.setProperty("--art-c", colors[2]);
    applyCover(artwork, track);
    artwork.append(
      element("div", { className: "artwork-top" }, [
        element("span", { className: "mode-badge", text: modeLabel(track.mode) })
      ])
    );

    const card = element("article", {
      className: "track-card",
      attrs: { tabindex: "-1", "data-track-id": track.id }
    }, [
      artwork,
      element("div", { className: "track-info" }, [
        element("div", { className: "track-info-head" }, [
          element("h2", { className: "track-title" }, [element("a", { text: track.title,
            attrs: { href: `#library?single=${encodeURIComponent(track.id)}` } })]),
          element("time", { className: "track-date", text: formatDate(track.createdAt), attrs: { datetime: toDate(track.createdAt)?.toISOString() || "" } })
        ]),
        element("p", { className: "track-style", text: track.style || "스타일 설명 없음" }),
        track.artistId ? element("a", { className: "track-creator", text: track.creator,
          attrs: { href: `#library?artist=${encodeURIComponent(track.artistId)}` } })
          : element("p", { className: "track-creator", text: track.creator })
      ])
    ]);

    const info = $(".track-info", card);
    const audioUrl = safeMediaUrl(track.audioUrl);
    if (audioUrl) {
      artwork.append(element("button", {
        className: "artwork-play",
        attrs: { type: "button", "aria-label": `${track.title} 재생`, "data-play-id": track.id, "data-track-title": track.title },
        on: { click: () => playTrack(track, state.library.items) }
      }, [svgIcon("play")]));
    } else {
      info.append(element("p", { className: "track-no-audio", text: "미리듣기를 준비 중이에요." }));
    }

    const downloadUrl = safeMediaUrl(track.downloadUrl);
    {
      const slug = track.title.replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "") || "yue-track";
      info.append(element("div", { className: "track-actions" }, [
        downloadUrl ? element("a", {
          className: "download-link",
          attrs: { href: downloadUrl, download: `${slug}.mp3` }
        }, [svgIcon("download"), element("span", { text: "다운로드" })]) : null,
        element("button", {
          className: "download-link remix-link",
          attrs: { type: "button" },
          on: { click: () => importRecipe(track) }
        }, [svgIcon("create"), element("span", { text: "내 스튜디오로 가져오기" })]),
        track.albumId ? element("a", { className: "download-link", text: "앨범", attrs: { href: `#library?album=${encodeURIComponent(track.albumId)}` } }) : null
      ]));
    }
    return card;
  }

  async function loadLibrary() {
    const requestId = ++state.library.requestId;
    state.library.loading = true;
    state.library.error = "";
    renderLibrary();
    const params = new URLSearchParams();
    const search = state.library.query.trim();
    if (search) params.set("q", search);
    if (state.library.mode !== "all") params.set("mode", state.library.mode);
    const query = params.toString();
    try {
      const payload = await fetchJson(`/api/library${query ? `?${query}` : ""}`, { headers: { Accept: "application/json" } });
      if (requestId !== state.library.requestId) return;
      const list = extractList(payload, ["tracks", "items", "library", "data"]);
      state.library.items = list.map(normalizeTrack);
      if (search && !state.libraryHomeLoaded) {
        try {
          state.libraryHome = await fetchJson("/api/library/discover");
          state.libraryHomeLoaded = true;
        } catch { /* Search still works when recommendations are unavailable. */ }
      }
      if (search && state.libraryHome) {
        const term = search.toLocaleLowerCase();
        const seen = new Set(state.library.items.map((track) => track.id));
        for (const raw of [...(state.libraryHome.new_releases || []), ...(state.libraryHome.this_week || []), ...(state.libraryHome.charts || [])]) {
          const track = normalizeTrack(raw);
          if (!seen.has(track.id) && `${track.title} ${track.creator} ${track.style}`.toLocaleLowerCase().includes(term)) {
            state.library.items.push(track);
            seen.add(track.id);
          }
        }
      }
      state.library.loaded = true;
    } catch {
      if (requestId !== state.library.requestId) return;
      state.library.error = "라이브러리를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.";
    } finally {
      if (requestId !== state.library.requestId) return;
      state.library.loading = false;
      renderLibrary();
    }
  }

  function focusLibraryTrack() {
    if (!state.focusTrackId || state.library.loading) return;
    const wanted = String(state.focusTrackId);
    const card = $$(".track-card", refs.libraryGrid).find((candidate) => candidate.dataset.trackId === wanted);
    if (!card) return;
    state.focusTrackId = null;
    card.classList.add("is-focused");
    card.focus({ preventScroll: true });
    const reducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    card.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "center" });
    window.setTimeout(() => card.classList.remove("is-focused"), 2600);
  }

  function openLibrary(trackId = "") {
    state.focusTrackId = trackId ? String(trackId) : null;
    if (trackId) {
      state.library.query = "";
      state.library.mode = "all";
      state.library.loaded = false;
      refs.librarySearch.value = "";
      refs.clearSearch.hidden = true;
      refs.libraryFilters.forEach((button) => {
        const selected = button.dataset.libraryMode === "all";
        button.classList.toggle("is-selected", selected);
        button.setAttribute("aria-pressed", String(selected));
      });
    }
    const target = trackId ? "library?view=all" : "library";
    if (window.location.hash !== `#${target}`) {
      window.location.hash = target;
    } else {
      renderRoute();
      focusLibraryTrack();
    }
  }

  function openPublishDialog(job) {
    state.publishJobId = job.id;
    refs.publishTitle.value = job.publishedTitle || job.title;
    refs.publishCover.value = "";
    refs.publishError.hidden = true;
    refs.publishError.textContent = "";
    if (state.publishPreviewUrl) URL.revokeObjectURL(state.publishPreviewUrl);
    state.publishPreviewUrl = null;
    const url = safeMediaUrl(job.coverUrl);
    refs.publishPreview.style.backgroundImage = url ? `url("${url}")` : "";
    refs.publishPreview.classList.toggle("has-custom-cover", Boolean(url));
    refs.publishSubmit.textContent = job.published ? "공개 정보 저장" : "라이브러리에 공개";
    refs.publishDialog.showModal();
    void loadMyArtists(job.artistId, job.albumId);
    refs.publishTitle.focus();
  }

  async function loadMyArtists(selectedId = "", albumId = "") {
    try {
      state.myArtists = await fetchJson("/api/artists/mine");
      const select = $("#publish-artist");
      select.replaceChildren(...state.myArtists.map((artist) =>
        element("option", { text: artist.name, attrs: { value: artist.id } })));
      select.value = selectedId && state.myArtists.some((artist) => String(artist.id) === String(selectedId))
        ? String(selectedId) : String(window.yue2Auth?.user?.id || state.myArtists[0]?.id || "");
      await loadMyAlbums(albumId);
    } catch {
      refs.publishError.textContent = "아티스트 목록을 불러오지 못했습니다.";
      refs.publishError.hidden = false;
    }
  }

  async function loadMyAlbums(selectedId = "") {
    try {
      state.myAlbums = await fetchJson("/api/albums?mine=1");
      const publishSelect = $("#publish-album");
      publishSelect.replaceChildren(element("option", { text: "싱글로 공개", attrs: { value: "" } }));
      state.myAlbums.forEach((album) => {
        if (String(album.artist_id) === $("#publish-artist").value)
          publishSelect.append(element("option", { text: `앨범 · ${album.title}`, attrs: { value: album.id } }));
      });
      publishSelect.value = selectedId && [...publishSelect.options].some((option) => option.value === selectedId)
        ? selectedId : "";
    } catch {
      showToast("앨범 목록을 불러오지 못했습니다.", "error");
    }
  }

  function closePublishDialog() {
    refs.publishDialog.close();
    state.publishJobId = null;
    if (state.publishPreviewUrl) URL.revokeObjectURL(state.publishPreviewUrl);
    state.publishPreviewUrl = null;
  }

  async function submitPublish(event) {
    event.preventDefault();
    if (!state.publishJobId) return;
    const file = refs.publishCover.files[0];
    if (file && (file.size > 5 * 1024 * 1024 || !["image/png", "image/jpeg", "image/webp"].includes(file.type))) {
      refs.publishError.textContent = "JPG, PNG, WebP 표지를 5MB 이하로 선택해 주세요.";
      refs.publishError.hidden = false;
      return;
    }
    const form = new FormData();
    form.append("title", refs.publishTitle.value.trim());
    form.append("album_id", $("#publish-album").value);
    form.append("artist_id", $("#publish-artist").value);
    if (file) form.append("cover", file, file.name);
    refs.publishSubmit.disabled = true;
    try {
      const updated = await fetchJson(`/api/tracks/${encodeURIComponent(state.publishJobId)}/publish`, { method: "POST", body: form });
      closePublishDialog();
      state.library.loaded = false;
      state.libraryHomeLoaded = false;
      await loadJobs({ reset: false });
      showToast("라이브러리에 공개했습니다.");
      openLibrary(updated.id);
    } catch (error) {
      refs.publishError.textContent = "곡을 공개하지 못했습니다. 입력 내용을 확인하고 다시 시도해 주세요.";
      refs.publishError.hidden = false;
    } finally {
      refs.publishSubmit.disabled = false;
    }
  }

  async function unpublishJob(job) {
    try {
      await fetchJson(`/api/tracks/${encodeURIComponent(job.id)}/publish`, { method: "DELETE" });
      state.library.loaded = false;
      state.libraryHomeLoaded = false;
      if (state.view === "library") loadLibrary();
      await loadJobs({ reset: false });
      showToast("라이브러리 공개를 취소했습니다.");
    } catch (error) {
      showToast("공개를 취소하지 못했습니다. 다시 시도해 주세요.", "error");
    }
  }

  async function importRecipe(track) {
    if (!window.yue2Auth?.ready) {
      window.yue2Auth?.open?.();
      return;
    }
    try {
      const recipe = await fetchJson(`/api/tracks/${encodeURIComponent(track.id)}/recipe`);
      setMode(recipe.mode);
      refs.trackTitle.value = recipe.title || "";
      refs.styleInput.value = recipe.style || "";
      const settings = recipe.settings || {};
      setInstrumental(Boolean(settings.instrumental) || !recipe.lyrics);
      refs.lyricsInput.value = recipe.lyrics || (state.instrumental ? "[instrumental]" : "");
      const values = {
        "duration-input": settings.duration,
        "temperature-input": settings.temperature,
        "top-p-input": settings.top_p,
        "top-k-input": settings.top_k,
        "repetition-input": settings.repetition_penalty,
        "plan-temperature-input": settings.plan_temperature,
        "plan-top-p-input": settings.plan_top_p,
        "plan-top-k-input": settings.plan_top_k,
        "plan-repetition-input": settings.plan_repetition_penalty,
        "penalty-window-input": settings.penalty_window
      };
      Object.entries(values).forEach(([id, value]) => {
        if (value !== undefined && value !== null) document.getElementById(id).value = String(value);
      });
      durationByMode[state.mode] = refs.durationInput.value;
      refs.randomSeed.checked = recipe.seed === null || recipe.seed === undefined;
      refs.seedInput.value = refs.randomSeed.checked ? "" : String(recipe.seed);
      syncSeedState();
      refs.planToggle.setAttribute("aria-checked", String(Boolean(settings.planning_enabled)));
      refs.planToggle.classList.toggle("is-on", Boolean(settings.planning_enabled));
      syncPlanState();
      refs.advancedPanel.open = true;
      if (recipe.mode === "cover") resetAudioSelection();
      updateLyricsCount();
      saveComposer();
      window.location.hash = "create";
      refs.styleInput.focus();
      showToast(recipe.mode === "cover" ? "설정을 가져왔습니다. 커버의 원본 오디오를 선택해 주세요." : "생성 설정을 내 스튜디오로 가져왔습니다.");
    } catch (error) {
      showToast("스타일을 가져오지 못했습니다. 다시 시도해 주세요.", "error");
    }
  }

  function renderRoute() {
    const requestedView = getViewFromHash();
    const view = !window.yue2Auth?.ready && (requestedView === "queue" || requestedView === "backoffice")
      ? "create" : requestedView;
    if (view !== state.view) window.scrollTo({ top: 0, behavior: "instant" });
    state.view = view;
    refs.viewPanels.forEach((panel) => {
      const visible = panel.dataset.viewPanel === view;
      panel.hidden = !visible;
      panel.classList.toggle("is-visible", visible);
    });
    refs.viewLinks.forEach((link) => {
      link.classList.toggle("is-active", link.dataset.viewLink === view);
      if (link.dataset.viewLink === view) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    if (view === "library") renderLibraryPage();
    if (view === "queue" && window.yue2Auth?.ready && typeof QueueManager !== "undefined") QueueManager.poll(true);
  }

  const Growl = {
    show({ type = "info", title = "", message = "", duration = 5000, action = null, onDismiss = null } = {}) {
      if (!refs.growlRegion) return null;

      const card = element("div", { className: `growl-card is-${type}` });

      let iconName = "info";
      if (type === "success") iconName = "check";
      else if (type === "warning") iconName = "alert";
      else if (type === "error") iconName = "close";
      const icon = svgIcon(iconName, "growl-icon");

      const content = element("div", { className: "growl-content" });
      if (title) {
        content.append(element("div", { className: "growl-title", text: title }));
      }
      if (message) {
        content.append(element("div", { className: "growl-message", text: message }));
      }

      const closeBtn = element("button", {
        className: "growl-close",
        attrs: { type: "button", "aria-label": "알림 닫기" },
        on: {
          click: (e) => {
            e.stopPropagation();
            dismiss();
          }
        }
      }, [svgIcon("close")]);

      if (action && action.label && typeof action.onClick === "function") {
        const actionBtn = element("button", {
          className: "growl-action",
          attrs: { type: "button" },
          text: action.label,
          on: {
            click: (e) => {
              e.stopPropagation();
              try {
                action.onClick();
              } finally {
                dismiss();
              }
            }
          }
        });
        content.append(element("div", { className: "growl-actions" }, [actionBtn]));
      }

      card.append(icon, content, closeBtn);

      let progressBar = null;
      if (duration > 0) {
        progressBar = element("div", { className: "growl-progress-bar" });
        card.append(progressBar);
      }

      let timer = null;
      let remaining = duration;
      let startTime = Date.now();

      function startTimer(timeMs) {
        if (timeMs <= 0) return;
        startTime = Date.now();
        remaining = timeMs;
        if (progressBar) {
          progressBar.style.transition = `transform ${remaining}ms linear`;
          progressBar.style.transform = "scaleX(0)";
        }
        timer = window.setTimeout(dismiss, remaining);
      }

      function pauseTimer() {
        if (timer) {
          window.clearTimeout(timer);
          timer = null;
          const elapsed = Date.now() - startTime;
          remaining = Math.max(0, remaining - elapsed);
          if (progressBar) {
            const currentScale = duration > 0 ? remaining / duration : 0;
            progressBar.style.transition = "none";
            progressBar.style.transform = `scaleX(${currentScale})`;
          }
        }
      }

      function resumeTimer() {
        if (remaining > 0 && !timer) {
          startTimer(remaining);
        }
      }

      function dismiss() {
        if (timer) {
          window.clearTimeout(timer);
          timer = null;
        }
        if (card.classList.contains("is-leaving")) return;
        card.classList.add("is-leaving");
        window.setTimeout(() => {
          card.remove();
          if (typeof onDismiss === "function") onDismiss();
        }, 260);
      }

      card.addEventListener("mouseenter", pauseTimer);
      card.addEventListener("mouseleave", resumeTimer);

      refs.growlRegion.prepend(card);

      if (duration > 0 && progressBar) {
        requestAnimationFrame(() => {
          progressBar.style.transform = "scaleX(1)";
          requestAnimationFrame(() => {
            startTimer(duration);
          });
        });
      }

      return { dismiss };
    },
    success(options) { return this.show({ ...options, type: "success" }); },
    warning(options) { return this.show({ ...options, type: "warning" }); },
    error(options) { return this.show({ ...options, type: "error" }); },
    info(options) { return this.show({ ...options, type: "info" }); }
  };

  function checkCutoffEnding(track, actualDuration) {
    if (!track || !actualDuration || actualDuration <= 0) return;
    const trackId = String(track.id);
    if (state.notifiedCutoffTracks.has(trackId)) return;

    const maxBudget = Number(track.settings?.duration || 0);
    if (maxBudget >= 15 && actualDuration >= (maxBudget - 2.5)) {
      state.notifiedCutoffTracks.add(trackId);

      window.setTimeout(() => {
        if (state.playerTrack?.id !== track.id) return;
        Growl.warning({
          title: "최대 생성 길이(버짓 제한) 도달 감지",
          message: `이 곡은 설정된 최대 길이(${Math.round(maxBudget)}초) 버짓을 모두 소진하여, 끝부분이 자연스럽지 않게 끊겼을 수 있습니다. 더 여유로운 곡 마무리를 위해 다음 생성 시 길이를 늘려보세요.`,
          duration: 9000,
          action: {
            label: "길이 +30초 늘리기",
            onClick: () => {
              const curVal = Number(refs.durationInput.value) || 120;
              const nextVal = Math.min(900, curVal + 30);
              refs.durationInput.value = String(nextVal);
              refs.advancedPanel.open = true;
              refs.durationInput.focus();
              refs.durationInput.scrollIntoView({ behavior: "smooth", block: "center" });
              Growl.info({
                title: "설정 변경됨",
                message: `최대 생성 길이가 ${nextVal}초로 늘어났습니다.`,
                duration: 3500
              });
            }
          }
        });
      }, 2500);
    }
  }

  const AudioVisualizer = {
    canvas: null,
    ctx: null,
    audio: null,
    audioCtx: null,
    analyser: null,
    sourceNode: null,
    connected: false,
    animId: null,
    barCount: 32,
    prevLevels: new Float32Array(32),
    peakLevels: new Float32Array(32),
    peakHold: new Float32Array(32),
    freqData: null,
    timeData: null,
    ambientBass: 0,
    ambientDrum: 0,
    drumFloor: 0,
    playbackBlend: 0,
    flowTime: 0,
    lastFrameTime: 0,
    reducedMotion: null,

    init(canvasNode, audioElement) {
      if (!canvasNode) return;
      this.canvas = canvasNode;
      this.ctx = canvasNode.getContext("2d");
      this.audio = audioElement;
      this.reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
      this.prevLevels.fill(2);
      this.peakLevels.fill(2);
      this.peakHold.fill(0);
      this.render = this.render.bind(this);
      this.drawBaseline();
      this.freezeInPlace();
      window.addEventListener("resize", () => {
        if (!this.animId) this.freezeInPlace();
      });
    },

    ensureAudioContext() {
      if (this.connected || !this.audio) return;
      try {
        const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtxClass) return;
        if (!this.audioCtx) {
          this.audioCtx = new AudioCtxClass();
        }
        if (this.audioCtx.state === "suspended") {
          this.audioCtx.resume().catch(() => {});
        }
        if (!this.sourceNode) {
          this.analyser = this.audioCtx.createAnalyser();
          this.analyser.fftSize = 2048;
          this.analyser.smoothingTimeConstant = 0.82;
          this.sourceNode = this.audioCtx.createMediaElementSource(this.audio);
          this.sourceNode.connect(this.analyser);
          this.analyser.connect(this.audioCtx.destination);
          this.connected = true;
          this.freqData = new Uint8Array(this.analyser.frequencyBinCount);
          this.timeData = new Uint8Array(this.analyser.fftSize);
        }
      } catch (err) {
        console.warn("AudioContext init:", err);
      }
    },

    start() {
      this.ensureAudioContext();
      if (this.audioCtx && this.audioCtx.state === "suspended") {
        this.audioCtx.resume().catch(() => {});
      }
      if (this.animId) return;
      this.lastFrameTime = performance.now();
      this.animId = requestAnimationFrame(this.render);
    },

    pause() {
      if (this.animId) {
        // If render loop is active, render() will smoothly decay orbs & EQ bars down in place,
        // then cleanly sleep the loop once baseline/resting state is reached.
        return;
      }
      if (this.playbackBlend > 0.005 || this.ambientBass > 0.005 || this.ambientDrum > 0.005) {
        this.lastFrameTime = performance.now();
        this.animId = requestAnimationFrame(this.render);
      } else {
        this.freezeInPlace();
        this.drawBaseline();
      }
    },

    stop() {
      if (this.animId) {
        cancelAnimationFrame(this.animId);
        this.animId = null;
      }
      this.drawBaseline();
      this.freezeInPlace();
    },

    freezeInPlace() {
      this.ambientBass = 0;
      this.ambientDrum = 0;
      this.drumFloor = 0;
      this.playbackBlend = 0;
      const backdrop = refs.ambientBackdrop;
      if (!backdrop) return;
      const t = this.flowTime;
      const vw = window.innerWidth;
      const vh = window.innerHeight;

      const flowX1 = (Math.sin(t * 0.48) * 0.36 + Math.cos(t * 0.21) * 0.16) * vw;
      const flowY1 = (Math.cos(t * 0.36) * 0.32 + Math.sin(t * 0.17) * 0.14) * vh;

      const flowX2 = (Math.cos(t * 0.40 + 2.2) * 0.36 + Math.sin(t * 0.19) * 0.16) * vw;
      const flowY2 = (Math.sin(t * 0.33 + 1.9) * 0.32 + Math.cos(t * 0.24) * 0.14) * vh;

      const flowX3 = (Math.sin(t * 0.54 + 4.3) * 0.30 + Math.cos(t * 0.28) * 0.14) * vw;
      const flowY3 = (Math.cos(t * 0.44 + 3.6) * 0.28 + Math.sin(t * 0.20) * 0.14) * vh;

      backdrop.style.transform = "scale(0.98)";

      const orb1 = refs.ambientOrb1 || backdrop.querySelector(".ambient-orb-1");
      if (orb1) {
        orb1.style.transform = `translate(-50%, -50%) translate(${flowX1.toFixed(1)}px, ${flowY1.toFixed(1)}px) scale(0.68)`;
        orb1.style.opacity = "0.35";
        orb1.style.filter = "blur(65px)";
      }

      const orb2 = refs.ambientOrb2 || backdrop.querySelector(".ambient-orb-2");
      if (orb2) {
        orb2.style.transform = `translate(-50%, -50%) translate(${flowX2.toFixed(1)}px, ${flowY2.toFixed(1)}px) scale(0.65)`;
        orb2.style.opacity = "0.32";
        orb2.style.filter = "blur(65px)";
      }

      const orb3 = refs.ambientOrb3 || backdrop.querySelector(".ambient-orb-3");
      if (orb3) {
        orb3.style.transform = `translate(-50%, -50%) translate(${flowX3.toFixed(1)}px, ${flowY3.toFixed(1)}px) scale(0.61)`;
        orb3.style.opacity = "0.30";
      }

      const grain = refs.ambientGrain || backdrop.querySelector(".ambient-grain");
      if (grain) {
        grain.style.opacity = "0.25";
      }
    },

    resetAmbient() {
      this.freezeInPlace();
    },

    drawBaseline() {
      if (!this.ctx || !this.canvas) return;
      const w = this.canvas.width;
      const h = this.canvas.height;
      this.ctx.clearRect(0, 0, w, h);
      this.ctx.fillStyle = "rgba(245, 183, 156, 0.22)";
      const barCount = this.barCount;
      const gap = 3;
      const totalGaps = (barCount - 1) * gap;
      const barWidth = Math.floor((w - totalGaps) / barCount);
      const startX = Math.floor((w - (barCount * barWidth + totalGaps)) / 2);

      for (let i = 0; i < barCount; i++) {
        const x = startX + i * (barWidth + gap);
        this.ctx.beginPath();
        if (typeof this.ctx.roundRect === "function") {
          this.ctx.roundRect(x, h - 2, barWidth, 2, 1);
        } else {
          this.ctx.rect(x, h - 2, barWidth, 2);
        }
        this.ctx.fill();
      }
    },

    render() {
      if (!this.ctx || !this.canvas) return;
      const isPlaying = Boolean(state.playerTrack) && !refs.player.paused && !refs.player.ended;
      const now = performance.now();
      const dt = this.lastFrameTime > 0 ? Math.min(0.1, (now - this.lastFrameTime) * 0.001) : 0.016;
      this.lastFrameTime = now;
      const w = this.canvas.width;
      const h = this.canvas.height;
      const barCount = this.barCount;
      const gap = 3;
      const totalGaps = (barCount - 1) * gap;
      const barWidth = Math.floor((w - totalGaps) / barCount);
      const startX = Math.floor((w - (barCount * barWidth + totalGaps)) / 2);

      this.ctx.clearRect(0, 0, w, h);

      if (this.connected && this.analyser) {
        if (!this.freqData || this.freqData.length !== this.analyser.frequencyBinCount) {
          this.freqData = new Uint8Array(this.analyser.frequencyBinCount);
        }
        this.analyser.getByteFrequencyData(this.freqData);
        if (this.timeData) this.analyser.getByteTimeDomainData(this.timeData);
      }

      let hasActiveLevels = false;
      const binCount = this.freqData ? this.freqData.length : 0;
      const binHz = this.audioCtx && this.analyser ? this.audioCtx.sampleRate / this.analyser.fftSize : 0;
      const bandLevel = (minHz, maxHz) => {
        if (!isPlaying || !binHz || !binCount) return 0;
        const first = Math.max(1, Math.ceil(minHz / binHz));
        const last = Math.min(binCount - 1, Math.floor(maxHz / binHz));
        if (last < first) return 0;
        let sum = 0;
        for (let bin = first; bin <= last; bin++) sum += this.freqData[bin];
        return sum / (last - first + 1) / 255;
      };
      const rawBass = bandLevel(35, 140);
      const rawDrum = bandLevel(90, 320);

      // Radiant EQ Gradient: Warm gold/amber at base -> Coral -> Radiant magenta/peach top
      const barGrad = this.ctx.createLinearGradient(0, h, 0, 0);
      barGrad.addColorStop(0, "#e9b77e");
      barGrad.addColorStop(0.45, "#f58e66");
      barGrad.addColorStop(1, "#ff5e78");
      const idleColor = "rgba(245, 183, 156, 0.22)";

      for (let i = 0; i < barCount; i++) {
        let eqEnergy = 0;
        if (isPlaying && binCount > 0) {
          // Logarithmic perceptual grouping across 32 EQ frequency bands
          const minBin = 1;
          const maxBin = Math.min(binCount - 2, Math.floor(12000 / binHz));
          const r0 = Math.pow(i / barCount, 2.0);
          const r1 = Math.pow((i + 1) / barCount, 2.0);
          const startBin = Math.max(0, Math.floor(minBin + r0 * (maxBin - minBin)));
          const endBin = Math.min(binCount - 1, Math.max(startBin + 1, Math.ceil(minBin + r1 * (maxBin - minBin))));

          let sum = 0;
          let count = 0;
          for (let b = startBin; b <= endBin; b++) {
            sum += this.freqData[b];
            count++;
          }
          const avg = count > 0 ? (sum / count) / 255 : 0;
          // Equal loudness compensation curve for EQ visualizer bars ONLY
          const boost = 1.0 + Math.pow(i / barCount, 1.25) * 1.6;
          eqEnergy = Math.min(1.0, avg * boost);

        }

        const targetH = isPlaying ? Math.max(2, eqEnergy * (h - 2.5)) : 2;

        // Snappy attack & silky exponential decay
        if (targetH > this.prevLevels[i]) {
          this.prevLevels[i] = this.prevLevels[i] * 0.2 + targetH * 0.8;
        } else {
          this.prevLevels[i] = Math.max(2, this.prevLevels[i] * 0.83);
        }

        const barH = this.prevLevels[i];
        if (barH > 2.2) hasActiveLevels = true;

        // Classic floating peak cap with gravity fall
        if (barH >= this.peakLevels[i]) {
          this.peakLevels[i] = barH;
          this.peakHold[i] = 10;
        } else {
          if (this.peakHold[i] > 0) {
            this.peakHold[i]--;
          } else {
            this.peakLevels[i] = Math.max(2, this.peakLevels[i] - 0.7);
          }
        }

        const x = startX + i * (barWidth + gap);
        const y = h - barH;

        // Draw EQ bar
        this.ctx.fillStyle = isPlaying && barH > 2.5 ? barGrad : idleColor;
        this.ctx.beginPath();
        if (typeof this.ctx.roundRect === "function") {
          this.ctx.roundRect(x, y, barWidth, barH, [2, 2, 0, 0]);
        } else {
          this.ctx.rect(x, y, barWidth, barH);
        }
        this.ctx.fill();

        // Draw Peak Cap
        if (isPlaying && this.peakLevels[i] > 3.2) {
          const peakY = Math.max(0, h - this.peakLevels[i] - 1);
          this.ctx.fillStyle = "rgba(255, 235, 215, 0.92)";
          this.ctx.fillRect(x, peakY, barWidth, 1.5);
        }
      }

      // Track the sustained low end separately from short kick and drum accents.
      const floorFactor = 1 - Math.exp(-dt / 1.2);
      this.drumFloor += ((isPlaying ? rawDrum : 0) - this.drumFloor) * floorFactor;
      const bassTarget = isPlaying ? Math.pow(Math.min(1, Math.max(0, (rawBass - 0.04) / 0.72)), 1.15) : 0;
      const drumAccent = Math.max(0, rawDrum - this.drumFloor);
      const drumTarget = isPlaying ? Math.pow(Math.min(1, Math.max(0, (rawDrum * 0.82 + drumAccent * 1.1 - 0.035) / 0.75)), 1.15) : 0;
      const bassTime = bassTarget > this.ambientBass ? 0.18 : 0.42;
      const drumTime = drumTarget > this.ambientDrum ? 0.13 : 0.38;
      this.ambientBass += (bassTarget - this.ambientBass) * (1 - Math.exp(-dt / bassTime));
      this.ambientDrum += (drumTarget - this.ambientDrum) * (1 - Math.exp(-dt / drumTime));
      const blendTarget = isPlaying ? 1 : 0;
      this.playbackBlend += (blendTarget - this.playbackBlend) * (1 - Math.exp(-dt / (isPlaying ? 0.4 : 0.7)));

      // Dynamic Ambient BG animation synchronized with music spectrum & beats
      const backdrop = refs.ambientBackdrop;
      if (backdrop) {
        // Flow time advances ONLY while music is playing!
        if (isPlaying && !this.reducedMotion?.matches) {
          const flowSpeed = 0.35 + this.ambientBass * 0.28 + this.ambientDrum * 0.18;
          this.flowTime += dt * flowSpeed;
        }

        const t = this.flowTime;
        const vw = window.innerWidth;
        const vh = window.innerHeight;

        // Free-flowing trajectories sweeping fluidly across the entire screen
        const flowX1 = (Math.sin(t * 0.48) * 0.36 + Math.cos(t * 0.21) * 0.16) * vw;
        const flowY1 = (Math.cos(t * 0.36) * 0.32 + Math.sin(t * 0.17) * 0.14) * vh;

        const flowX2 = (Math.cos(t * 0.40 + 2.2) * 0.36 + Math.sin(t * 0.19) * 0.16) * vw;
        const flowY2 = (Math.sin(t * 0.33 + 1.9) * 0.32 + Math.cos(t * 0.24) * 0.14) * vh;

        const flowX3 = (Math.sin(t * 0.54 + 4.3) * 0.30 + Math.cos(t * 0.28) * 0.14) * vw;
        const flowY3 = (Math.cos(t * 0.44 + 3.6) * 0.28 + Math.sin(t * 0.20) * 0.14) * vh;

        const motionAmount = this.reducedMotion?.matches ? 0.15 : 1;
        const bassDynamic = Math.min(1, this.ambientBass) * this.playbackBlend * motionAmount;
        const drumDynamic = Math.min(1, this.ambientDrum) * this.playbackBlend * motionAmount;
        const lowDynamic = bassDynamic * 0.65 + drumDynamic * 0.35;

        // Keep the backdrop movement subtle so the low end has room to breathe.
        const bgScale = 0.98 + bassDynamic * 0.06;
        backdrop.style.transform = `scale(${bgScale.toFixed(4)})`;

        // Violet follows the sustained bass and 808 range.
        const orb1 = refs.ambientOrb1 || backdrop.querySelector(".ambient-orb-1");
        if (orb1) {
          const s1 = 0.68 + bassDynamic * 0.70;
          const op1 = 0.35 + bassDynamic * 0.48;
          orb1.style.transform = `translate(-50%, -50%) translate(${flowX1.toFixed(1)}px, ${flowY1.toFixed(1)}px) scale(${s1.toFixed(3)})`;
          orb1.style.opacity = Math.min(0.98, op1).toFixed(3);
        }

        // Amber follows the low drum attack.
        const orb2 = refs.ambientOrb2 || backdrop.querySelector(".ambient-orb-2");
        if (orb2) {
          const s2 = 0.65 + drumDynamic * 0.70;
          const op2 = 0.32 + drumDynamic * 0.46;
          orb2.style.transform = `translate(-50%, -50%) translate(${flowX2.toFixed(1)}px, ${flowY2.toFixed(1)}px) scale(${s2.toFixed(3)})`;
          orb2.style.opacity = Math.min(0.98, op2).toFixed(3);
        }

        // The artwork color follows a quieter blend of both low bands.
        const orb3 = refs.ambientOrb3 || backdrop.querySelector(".ambient-orb-3");
        if (orb3) {
          const s3 = 0.61 + lowDynamic * 0.62;
          const op3 = 0.30 + lowDynamic * 0.40;
          orb3.style.transform = `translate(-50%, -50%) translate(${flowX3.toFixed(1)}px, ${flowY3.toFixed(1)}px) scale(${s3.toFixed(3)})`;
          orb3.style.opacity = Math.min(0.95, op3).toFixed(3);
        }

        // Grain stays subdued, with a small accent on drum hits.
        const grain = refs.ambientGrain || backdrop.querySelector(".ambient-grain");
        if (grain) {
          const grainOp = 0.25 + drumDynamic * 0.08;
          grain.style.opacity = Math.min(0.90, grainOp).toFixed(3);
        }
      }

      if (isPlaying || hasActiveLevels || this.playbackBlend > 0.005 || this.ambientBass > 0.005 || this.ambientDrum > 0.005) {
        this.animId = requestAnimationFrame(this.render);
      } else {
        this.animId = null;
        this.drawBaseline();
        this.freezeInPlace();
      }
    }
  };

  function showToast(message, tone = "success") {
    Growl.show({
      type: tone === "error" ? "error" : "success",
      message: message,
      duration: tone === "error" ? 6000 : 4500
    });
  }

  const QueueManager = {
    refreshTimer: null,
    pollTimer: null,
    requestId: 0,
    myWorkers: [],
    mineLoaded: false,

    init() {
      this.bindEvents();
      this.poll(true);
    },

    bindEvents() {
      if (refs.queuePipPill) {
        refs.queuePipPill.addEventListener("click", () => this.togglePip());
      }
      if (refs.queuePipBtnClose) {
        refs.queuePipBtnClose.addEventListener("click", () => this.togglePip(false));
      }
      if (refs.queuePipBtnMinimize) {
        refs.queuePipBtnMinimize.addEventListener("click", () => this.togglePip(false));
      }
      if (refs.queuePipBtnMaximize) {
        refs.queuePipBtnMaximize.addEventListener("click", () => {
          this.togglePip(false);
          window.location.hash = "queue";
        });
      }
      if (refs.queuePipBtnRefresh) {
        refs.queuePipBtnRefresh.addEventListener("click", () => this.poll(true));
      }
      if (refs.queuePageRefresh) {
        refs.queuePageRefresh.addEventListener("click", () => this.poll(true));
      }
      if (refs.queuePageOpenPip) {
        refs.queuePageOpenPip.addEventListener("click", () => {
          this.togglePip(true);
          window.location.hash = "create";
        });
      }
      if (refs.navQueueLink) {
        refs.navQueueLink.addEventListener("click", () => {
          this.togglePip(false);
        });
      }
      if (refs.mobileNavQueue) {
        refs.mobileNavQueue.addEventListener("click", () => {
          this.togglePip(false);
        });
      }
      refs.workerCreateForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = refs.workerCreateForm.querySelector('button[type="submit"]');
        button.disabled = true;
        refs.workerFormStatus.hidden = true;
        try {
          const name = refs.workerCreateForm.elements.name.value.trim();
          const created = await fetchJson("/api/my/workers", {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name })
          });
          refs.workerConfig.textContent = `set "YUE2_SERVER_URL=${window.location.origin}${BASE_PATH}"\nset "YUE2_WORKER_ID=${created.worker_id}"\nset "YUE2_WORKER_TOKEN=${created.token}"`;
          refs.workerCredential.hidden = false;
          refs.workerCreateForm.reset();
          await this.loadMine();
        } catch (error) {
          refs.workerFormStatus.textContent = error.message;
          refs.workerFormStatus.hidden = false;
        } finally {
          button.disabled = false;
        }
      });
      refs.workerCopyConfig?.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(refs.workerConfig.textContent); showToast("워커 설정을 복사했습니다."); }
        catch { showToast("복사할 수 없습니다. 설정을 직접 선택해 복사하세요.", "error"); }
      });
      document.addEventListener("visibilitychange", () => {
        if (!document.hidden) this.poll();
      });
    },

    async loadMine() {
      try {
        const data = await fetchJson("/api/my/workers");
        this.myWorkers = Array.isArray(data.workers) ? data.workers : [];
        this.mineLoaded = true;
        this.renderMine();
      } catch (error) {
        if (refs.myWorkers) refs.myWorkers.textContent = error.message;
      }
    },

    renderMine() {
      if (!refs.myWorkers) return;
      refs.myWorkers.replaceChildren();
      if (!this.myWorkers.length) {
        refs.myWorkers.append(element("p", { text: "아직 등록한 워커가 없습니다." }));
        return;
      }
      const connected = new Map((state.queue.workers || []).map((worker) => [worker.worker_id, worker]));
      this.myWorkers.forEach((record) => {
        const status = connected.get(record.worker_id)?.status || "offline";
        const label = status === "busy" ? "작업 중" : status === "idle" ? "유휴" : "연결 안 됨";
        const revoke = element("button", { text: "연결 해제", attrs: { type: "button" } });
        revoke.addEventListener("click", async () => {
          if (!window.confirm(`${record.name} 워커의 연결 키를 폐기할까요? 실행 중인 작업도 연결이 끊깁니다.`)) return;
          revoke.disabled = true;
          try {
            await fetchJson(`/api/my/workers/${encodeURIComponent(record.worker_id)}`, { method: "DELETE" });
            await this.loadMine();
            await this.poll();
          } catch (error) { showToast(error.message, "error"); revoke.disabled = false; }
        });
        refs.myWorkers.append(element("div", { className: "my-worker-row" }, [
          element("span", { text: `${record.name} · ${label}` }), revoke
        ]));
      });
    },

    renderWorkers(workers) {
      if (refs.queueWorkerCount) refs.queueWorkerCount.textContent = String(workers.length);
      if (!refs.queueWorkers) return;
      refs.queueWorkers.replaceChildren();
      if (!workers.length) {
        refs.queueWorkers.append(element("div", { className: "queue-empty-text", text: "연결된 GPU 워커가 없습니다." }));
        return;
      }
      workers.forEach((worker) => {
        const progress = worker.progress || {};
        const rate = Number(progress.rate);
        let speed = "";
        if (Number.isFinite(rate) && rate > 0) {
          if (progress.phase === "abc" || progress.phase === "music") speed = `${rate.toFixed(1)} tok/s`;
          else if (progress.phase === "rendering") speed = `${(1 / rate).toFixed(2)} s/it`;
        }
        const phase = { abc: "ABC 생성", sheet: "악보 분석", music: "음악 토큰 생성", rendering: "오디오 렌더링", finishing: "마무리", preparing: "준비" }[progress.phase] || "";
        refs.queueWorkers.append(element("div", { className: "queue-worker-row" }, [
          element("div", { className: "queue-worker-main" }, [
            element("strong", { text: worker.name || worker.worker_id || "GPU 워커" }),
            element("small", { text: [worker.device, worker.vram].filter(Boolean).join(" · ") })
          ]),
          element("span", { className: `queue-worker-state ${worker.status === "busy" ? "is-busy" : ""}`,
            text: worker.status === "busy" ? ["작업 중", phase, speed].filter(Boolean).join(" · ") : "유휴" })
        ]));
      });
    },

    togglePip(forceState) {
      if (!refs.queuePipWindow || !refs.queuePipPill) return;
      const isOpen = typeof forceState === "boolean" ? forceState : refs.queuePipWindow.hidden;
      refs.queuePipWindow.hidden = !isOpen;
      refs.queuePipPill.setAttribute("aria-expanded", String(isOpen));
      if (isOpen) {
        this.poll(true);
      }
    },

    refreshSoon() {
      if (this.refreshTimer) window.clearTimeout(this.refreshTimer);
      this.refreshTimer = window.setTimeout(() => {
        this.refreshTimer = null;
        this.poll();
      }, 150);
    },

    schedulePoll() {
      if (this.pollTimer) window.clearTimeout(this.pollTimer);
      const active = (state.queue.summary?.total_active || 0) > 0
        || (state.queue.workers || []).some((worker) => worker.status === "busy");
      const delay = document.hidden ? 30000 : active ? 3000 : 5000;
      this.pollTimer = window.setTimeout(() => {
        this.pollTimer = null;
        this.poll();
      }, delay);
    },

    applyProgress(id, progress) {
      const job = state.queue.running.find((item) => item.id === id);
      if (!job) return;
      job.progress = progress;
      for (const container of [refs.queuePipRunningBox, refs.queuePageRunning]) {
        if (!container) continue;
        const card = Array.from(container.querySelectorAll("[data-job-id]"))
          .find((candidate) => candidate.dataset.jobId === id);
        if (!card) continue;
        const section = $(".generation-progress", card);
        if (section) updateGenerationProgress(section, job.mode, progress);
      }
    },

    async poll() {
      if (!window.yue2Auth?.ready) return;
      if (this.pollTimer) {
        window.clearTimeout(this.pollTimer);
        this.pollTimer = null;
      }
      const requestId = ++this.requestId;
      try {
        const data = await fetchJson("/api/queue");
        if (requestId !== this.requestId) return;
        if (data && typeof data === "object") {
          state.queue = {
            running: Array.isArray(data.running) ? data.running : [],
            pending: Array.isArray(data.pending) ? data.pending : [],
            recent: Array.isArray(data.recent) ? data.recent : [],
            workers: Array.isArray(data.workers) ? data.workers : [],
            workerContributionEnabled: Boolean(data.worker_contribution_enabled),
            summary: data.summary || { running_count: 0, pending_count: 0, total_active: 0 },
            engine: data.engine || { status: "offline", device: "", vram: "" }
          };
          this.render();
          if (state.queue.workerContributionEnabled && !this.mineLoaded) this.loadMine();
        }
      } catch (err) {
        // Keep calm on transient network error
      } finally {
        this.schedulePoll();
      }
    },

    render() {
      const { running, pending, recent, summary, engine, workers = [] } = state.queue;
      if (refs.workerContribute) refs.workerContribute.hidden = !state.queue.workerContributionEnabled;
      this.renderWorkers(workers);
      this.renderMine();
      const totalActive = summary.total_active || 0;
      const runningCount = summary.running_count || 0;
      const pendingCount = summary.pending_count || 0;

      // 1. Sidebar & Mobile Badges
      if (refs.navQueueBadge) {
        refs.navQueueBadge.hidden = totalActive === 0;
        refs.navQueueBadge.textContent = String(totalActive);
      }

      // 2. PIP Pill
      if (refs.queuePipPill) {
        refs.queuePipPill.classList.toggle("has-active", totalActive > 0);
        if (refs.queuePipDot) {
          refs.queuePipDot.classList.toggle("is-active", totalActive > 0);
        }
        if (refs.queuePipPillCount) {
          refs.queuePipPillCount.hidden = totalActive === 0;
          refs.queuePipPillCount.textContent = String(totalActive);
        }
        if (refs.queuePipPillLabel) {
          if (runningCount > 0 && pendingCount > 0) {
            refs.queuePipPillLabel.textContent = `생성 중 ${runningCount} · 대기 ${pendingCount}`;
          } else if (runningCount > 0) {
            refs.queuePipPillLabel.textContent = `생성 중 ${runningCount}건`;
          } else if (pendingCount > 0) {
            refs.queuePipPillLabel.textContent = `대기 중 ${pendingCount}건`;
          } else {
            refs.queuePipPillLabel.textContent = "서버 대기열";
          }
        }
      }

      // 3. PIP Window Head
      if (refs.queuePipHeadStat) {
        if (totalActive === 0) {
          refs.queuePipHeadStat.textContent = "대기열 비어있음 (즉시 생성 가능)";
        } else {
          refs.queuePipHeadStat.textContent = `생성 ${runningCount}건 · 대기 ${pendingCount}건`;
        }
      }

      // 4. Running & Pending counts
      if (refs.queuePipRunningNum) refs.queuePipRunningNum.textContent = String(runningCount);
      if (refs.queuePipPendingNum) refs.queuePipPendingNum.textContent = String(pendingCount);

      // 5. Render Running Box
      if (refs.queuePipRunningBox) {
        refs.queuePipRunningBox.innerHTML = "";
        if (running.length === 0) {
          refs.queuePipRunningBox.append(
            element("div", { className: "queue-empty-text" }, ["현재 실행 중인 작업이 없습니다."])
          );
        } else {
          running.forEach((job) => refs.queuePipRunningBox.append(this.createRunningCard(job)));
        }
      }

      // 6. Render Pending Box
      if (refs.queuePipPendingBox) {
        refs.queuePipPendingBox.innerHTML = "";
        if (pending.length === 0) {
          refs.queuePipPendingBox.append(
            element("div", { className: "queue-empty-text" }, ["대기 중인 요청이 없습니다."])
          );
        } else {
          pending.forEach((job, idx) => refs.queuePipPendingBox.append(this.createPendingRow(job, idx + 1)));
        }
      }

      // 7. Render Recent Box
      if (refs.queuePipRecentBox) {
        refs.queuePipRecentBox.innerHTML = "";
        if (recent.length === 0) {
          refs.queuePipRecentBox.append(
            element("div", { className: "queue-empty-text" }, ["최근 완료된 작업이 없습니다."])
          );
        } else {
          recent.forEach((track) => refs.queuePipRecentBox.append(this.createRecentRow(track)));
        }
      }

      // 8. GPU & Engine Info
      if (refs.queuePipDevice) {
        const engText = engine.status === "busy" ? "엔진 가동 중" : engine.status === "idle" ? "엔진 대기 중" : "엔진 오프라인";
        const devText = engine.device ? ` · ${engine.device}` : "";
        const vramText = engine.vram ? ` (${engine.vram})` : "";
        refs.queuePipDevice.textContent = `${engText}${devText}${vramText}`;
      }

      // 9. Synchronize Dedicated Queue Page (if open or present)
      if (refs.queuePagePendingCount) refs.queuePagePendingCount.textContent = String(pendingCount);
      if (refs.queuePageEngineStatus) {
        refs.queuePageEngineStatus.textContent = engine.status === "busy" ? "음악을 만들고 있습니다" : "지금은 음악을 만들 수 없습니다";
      }
      if (refs.queuePageBannerLeft) refs.queuePageBannerLeft.hidden = engine.status === "idle";
      if (refs.queuePageCreate) refs.queuePageCreate.hidden = engine.status !== "idle";
      if (refs.queuePageGpu) {
        refs.queuePageGpu.textContent = "";
      }
      if (refs.queuePageRunning) {
        refs.queuePageRunning.innerHTML = "";
        if (running.length === 0) {
          refs.queuePageRunning.append(
            element("div", { className: "queue-empty-text" }, ["현재 생성 중인 음악이 없습니다."])
          );
        } else {
          running.forEach((job) => refs.queuePageRunning.append(this.createRunningCard(job)));
        }
      }
      if (refs.queuePagePending) {
        refs.queuePagePending.innerHTML = "";
        if (pending.length === 0) {
          refs.queuePagePending.append(
            element("div", { className: "queue-empty-text" }, ["대기열이 비어 있습니다."])
          );
        } else {
          pending.forEach((job, idx) => refs.queuePagePending.append(this.createPendingRow(job, idx + 1)));
        }
      }
      if (refs.queuePageRecent) {
        refs.queuePageRecent.innerHTML = "";
        if (recent.length === 0) {
          refs.queuePageRecent.append(
            element("div", { className: "queue-empty-text" }, ["최근 완료된 곡이 없습니다."])
          );
        } else {
          recent.forEach((track) => refs.queuePageRecent.append(this.createRecentRow(track)));
        }
      }
    },

    createRunningCard(job) {
      const modeLabel = job.mode === "cover" ? "커버" : "새 곡";

      const card = element("div", { className: "queue-item-card is-active-gen", attrs: { "data-job-id": job.id } }, [
        element("div", { className: "queue-item-top" }, [
          element("strong", { className: "queue-item-title", text: job.title || "새로운 음악" }),
          element("span", { className: "queue-item-mode", text: modeLabel })
        ]),
        element("div", { className: "queue-item-meta" }, [
          element("span", {
            className: `queue-creator-tag ${job.is_mine ? "is-mine" : ""}`,
            text: job.is_mine ? `${job.creator || "나"} (내 요청)` : (job.creator || "익명")
          }),
          element("span", { text: `· ${formatRelative(job.created_at || job.createdAt)}` })
        ]),
        createGenerationProgress(job.mode, job.progress, "queue-generation-progress")
      ]);
      return card;
    },

    createPendingRow(job, position) {
      const modeLabel = job.mode === "cover" ? "커버" : "새 곡";
      const row = element("div", { className: "queue-pending-row" }, [
        element("div", { className: "queue-pending-pos", text: `#${position}` }),
        element("div", { className: "queue-pending-info" }, [
          element("div", { className: "queue-pending-title", text: job.title || "새로운 음악" }),
          element("div", { className: "queue-pending-sub" }, [
            element("span", {
              className: `queue-creator-tag ${job.is_mine ? "is-mine" : ""}`,
              text: job.is_mine ? `${job.creator || "나"} (내 요청)` : (job.creator || "회원")
            }),
            element("span", { text: `· ${modeLabel}` }),
            element("span", { text: `· ${formatRelative(job.created_at || job.createdAt)}` })
          ])
        ])
      ]);
      if (job.is_mine) {
        row.append(
          element("button", {
            className: "queue-pending-cancel-btn",
            attrs: { type: "button", title: "대기열 취소" },
            text: "취소",
            on: {
              click: (event) => {
                event.stopPropagation();
                cancelJob(job);
              }
            }
          })
        );
      }
      return row;
    },

    createRecentRow(track) {
      const isPlayable = Boolean(track.audio_url || track.audioUrl);
      const row = element("div", { className: "queue-recent-item" }, [
        element("span", { className: "queue-recent-title", text: track.title || "완성된 음악" }),
        isPlayable
          ? element("button", {
              className: "queue-recent-play",
              type: "button",
              text: "재생",
              on: {
                click: () => playTrack(normalizeJob(track), state.jobs.filter((j) => j.status === "completed"))
              }
            })
          : element("span", { className: "queue-recent-play", text: track.status === "failed" ? "실패" : "완료" })
      ]);
      return row;
    }
  };

  const Realtime = {
    socket: null,
    reconnectTimer: null,
    attempts: 0,
    connectedOnce: false,
    stopped: false,

    start() {
      this.stopped = false;
      this.connect();
      window.addEventListener("pagehide", () => {
        this.stopped = true;
        if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer);
        if (this.socket) this.socket.close();
      });
    },

    connect() {
      if (this.stopped) return;
      const url = new URL(resolvePath("/api/events"), window.location.href);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      const socket = new WebSocket(url);
      this.socket = socket;
      socket.onopen = () => {
        this.attempts = 0;
        if (this.connectedOnce) {
          loadJobs({ reset: false });
          QueueManager.poll();
        }
        this.connectedOnce = true;
      };
      socket.onmessage = (message) => {
        let payload;
        try { payload = JSON.parse(message.data); } catch { return; }
        if (payload?.type === "job") applyJobUpdate(payload.job);
        else if (payload?.type === "progress") applyProgressUpdates(payload.updates);
      };
      socket.onclose = () => {
        if (this.stopped) return;
        const delay = Math.min(15000, 1000 * 2 ** Math.min(this.attempts++, 4));
        this.reconnectTimer = window.setTimeout(() => this.connect(), delay);
      };
    }
  };

  function bindEvents() {
    $("#publish-artist").addEventListener("change", () => loadMyAlbums());
    refs.publishForm.addEventListener("submit", submitPublish);
    $("#publish-close").addEventListener("click", closePublishDialog);
    $("#publish-cancel").addEventListener("click", closePublishDialog);
    refs.publishDialog.addEventListener("close", () => {
      state.publishJobId = null;
      if (state.publishPreviewUrl) URL.revokeObjectURL(state.publishPreviewUrl);
      state.publishPreviewUrl = null;
    });
    refs.publishCover.addEventListener("change", () => {
      if (state.publishPreviewUrl) URL.revokeObjectURL(state.publishPreviewUrl);
      const file = refs.publishCover.files[0];
      state.publishPreviewUrl = file ? URL.createObjectURL(file) : null;
      refs.publishPreview.style.backgroundImage = state.publishPreviewUrl ? `url("${state.publishPreviewUrl}")` : "";
      refs.publishPreview.classList.toggle("has-custom-cover", Boolean(state.publishPreviewUrl));
    });
    const trackComposerEdit = () => {
      if (!window.yue2Auth?.ready) guestComposerTouched = true;
      saveComposer();
    };
    refs.composerForm.addEventListener("input", trackComposerEdit);
    refs.composerForm.addEventListener("change", trackComposerEdit);
    refs.advancedPanel.addEventListener("toggle", saveComposer);
    window.addEventListener("pagehide", saveComposer);
    refs.workspaceSearch.addEventListener("input", renderJobs);
    refs.workspaceFilter.addEventListener("change", renderJobs);
    refs.refreshJobs.addEventListener("click", () => {
      loadJobs({ reset: true });
      if (typeof QueueManager !== "undefined") QueueManager.poll(true);
    });
    if (refs.jobsLoadMore) {
      refs.jobsLoadMore.addEventListener("click", () => loadMoreJobs());
    }
    refs.lyricsInput.addEventListener("input", updateLyricsCount);
    refs.player.crossOrigin = "anonymous";
    refs.player.volume = Number(refs.playerVolume.value);
    refs.player.addEventListener("play", () => {
      AudioVisualizer.ensureAudioContext();
      AudioVisualizer.start();
    });
    refs.playerToggle.addEventListener("click", () => {
      if (!state.playerTrack) return;
      if (refs.player.paused) resumePlayer();
      else refs.player.pause();
    });
    refs.playerPrev.addEventListener("click", () => stepPlayer(-1));
    refs.playerNext.addEventListener("click", () => stepPlayer(1));
    refs.playerVolume.addEventListener("input", () => { refs.player.volume = Number(refs.playerVolume.value); });
    refs.playerProgress.addEventListener("input", () => {
      if (Number.isFinite(refs.player.duration)) refs.player.currentTime = Number(refs.playerProgress.value) / 1000 * refs.player.duration;
      syncPlayerTime();
    });
    ["play", "pause", "ended"].forEach((event) => refs.player.addEventListener(event, syncPlayerButtons));
    ["timeupdate", "loadedmetadata", "durationchange", "emptied"].forEach((event) => refs.player.addEventListener(event, syncPlayerTime));
    refs.player.addEventListener("ended", () => stepPlayer(1));
    refs.player.addEventListener("error", () => {
      showToast("오디오를 불러오지 못했어요. 연결 상태를 확인하고 다시 시도해 주세요.", "error");
      syncPlayerButtons();
    });
    window.addEventListener("hashchange", renderRoute);
    refs.modeOptions.forEach((button) => button.addEventListener("click", () => setMode(button.dataset.modeOption)));
    refs.composerForm.addEventListener("submit", submitGeneration);
    refs.randomSeed.addEventListener("change", () => {
      syncSeedState();
      saveComposer();
    });
    refs.advancedReset.addEventListener("click", resetAdvancedSettings);
    refs.planToggle.addEventListener("click", () => {
      const enabled = refs.planToggle.getAttribute("aria-checked") !== "true";
      refs.planToggle.setAttribute("aria-checked", String(enabled));
      refs.planToggle.classList.toggle("is-on", enabled);
      syncPlanState();
      saveComposer();
    });
    refs.instrumentalToggle.addEventListener("click", () => setInstrumental(!state.instrumental));
    refs.audioFile.addEventListener("change", () => selectAudioFile(refs.audioFile.files[0]));
    refs.removeAudio.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      resetAudioSelection();
      refs.dropzone.focus();
    });
    refs.dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        refs.audioFile.click();
      }
    });
    ["dragenter", "dragover"].forEach((eventName) => refs.dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      refs.dropzone.classList.add("is-dragging");
    }));
    ["dragleave", "drop"].forEach((eventName) => refs.dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      refs.dropzone.classList.remove("is-dragging");
    }));
    refs.dropzone.addEventListener("drop", (event) => selectAudioFile(event.dataTransfer.files[0]));
    $$("[data-suggestion]").forEach((button) => button.addEventListener("click", () => appendSuggestion(button.dataset.suggestion)));
    refs.librarySearch.addEventListener("input", () => {
      state.library.query = refs.librarySearch.value;
      refs.clearSearch.hidden = !state.library.query;
      if (state.libraryDebounce) window.clearTimeout(state.libraryDebounce);
      state.libraryDebounce = window.setTimeout(() => loadLibrary(), 320);
    });
    refs.clearSearch.addEventListener("click", () => {
      refs.librarySearch.value = "";
      state.library.query = "";
      refs.clearSearch.hidden = true;
      loadLibrary();
      refs.librarySearch.focus();
    });
    refs.libraryFilters.forEach((button) => button.addEventListener("click", () => {
      state.library.mode = button.dataset.libraryMode;
      refs.libraryFilters.forEach((filter) => {
        const selected = filter === button;
        filter.classList.toggle("is-selected", selected);
        filter.setAttribute("aria-pressed", String(selected));
      });
      loadLibrary();
    }));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !refs.toastRegion.hidden) hideToast();
    });
  }

  function init() {
    AudioVisualizer.init(refs.playerVisualizer, refs.player);
    setHealthStatus(false, false);
    setMode("original");
    syncSeedState();
    syncPlanState();
    setInstrumental(false);
    promptAssistant = window.YuE2PromptAssistant?.init({
      getMode: () => state.mode,
      isInstrumental: () => state.instrumental,
      applyDraft: ({ title, style, lyrics, instrumental, maxDurationSeconds }) => {
        setInstrumental(instrumental, false);
        refs.trackTitle.value = title;
        refs.styleInput.value = style;
        refs.lyricsInput.value = lyrics;
        if (maxDurationSeconds !== null && Number.isInteger(maxDurationSeconds) && maxDurationSeconds >= 10 && maxDurationSeconds <= 900) {
          refs.durationInput.value = String(maxDurationSeconds);
          durationByMode[state.mode] = refs.durationInput.value;
        }
        clearFieldError(refs.styleInput, refs.styleError);
        updateLyricsCount();
        saveComposer();
        refs.styleInput.focus();
      }
    });
    bindEvents();
    renderJobs();
    renderRoute();
  }

  function startSignedIn() {
    if (signedInStarted) return;
    signedInStarted = true;
    document.body.classList.add("is-authenticated");
    renderRoute();
    if (!guestComposerTouched) restoreComposer();
    composerPersistenceReady = true;
    if (guestComposerTouched) saveComposer();
    setupJobsInfiniteScroll();
    checkHealth();
    window.setInterval(checkHealth, 15000);
    QueueManager.init();
    loadJobs({ initial: true });
    Realtime.start();
  }

  init();
  if (window.yue2Auth?.ready) startSignedIn();
  else window.addEventListener("yue2-ready", startSignedIn, { once: true });
})();
