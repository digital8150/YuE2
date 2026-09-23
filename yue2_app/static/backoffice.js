(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const state = { artists: [], albums: [], selectedArtistId: null };
  const basePath = location.pathname.endsWith("/")
    ? location.pathname.slice(0, -1) : location.pathname.replace(/\/[^/]*$/, "");

  async function api(path, options = {}) {
    const url = basePath && !path.startsWith(`${basePath}/`) ? `${basePath}${path}` : path;
    const response = await fetch(url, { credentials: "same-origin", ...options,
      headers: { ...(options.headers || {}), ...(options.method ? { "X-Yue2-CSRF": window.yue2Auth?.csrfToken || "" } : {}) } });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(response.status === 404
      ? "아티스트 정보를 찾을 수 없습니다. 화면을 새로고침해 주세요."
      : response.status === 413 ? "이미지 크기를 확인해 주세요. 파일당 최대 5MB입니다."
      : "변경 사항을 저장하지 못했습니다. 입력 내용을 확인하고 다시 시도해 주세요.");
    return data;
  }

  function status(message, error = false) {
    const node = $("#backoffice-status");
    node.textContent = message;
    node.classList.toggle("is-error", error);
    node.hidden = !message;
  }

  function selectedArtist() {
    return state.artists.find((item) => item.id === state.selectedArtistId);
  }

  function renderArtists() {
    const list = $("#artist-list");
    list.replaceChildren();
    for (const artist of state.artists) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `backoffice-artist${artist.id === state.selectedArtistId ? " is-selected" : ""}`;
      const avatar = document.createElement("span");
      avatar.className = "backoffice-avatar";
      avatar.textContent = artist.name.slice(0, 1);
      if (artist.avatar_url) { avatar.style.backgroundImage = `url("${artist.avatar_url}")`; avatar.textContent = ""; }
      const copy = document.createElement("span");
      copy.className = "backoffice-artist-copy";
      const name = document.createElement("strong");
      name.textContent = artist.name;
      const count = document.createElement("small");
      count.textContent = `${artist.track_count}곡 공개`;
      copy.append(name, count);
      button.append(avatar, copy);
      button.addEventListener("click", () => selectArtist(artist.id));
      list.append(button);
    }
  }

  async function selectArtist(id) {
    state.selectedArtistId = id;
    const artist = selectedArtist();
    $("#artist-editor-heading").textContent = artist ? "아티스트 프로필" : "새 아티스트 만들기";
    const form = $("#artist-editor");
    form.reset();
    form.elements.name.value = artist?.name || "";
    form.elements.bio.value = artist?.bio || "";
    const link = $("#artist-public-link");
    link.hidden = !artist;
    if (artist) link.href = `#library?artist=${encodeURIComponent(artist.id)}`;
    renderArtists();
    await loadAlbums();
  }

  async function loadAlbums() {
    state.albums = await api("/api/albums?mine=1");
    const picker = $("#album-picker");
    picker.replaceChildren(new Option("+ 새 앨범", ""));
    for (const album of state.albums.filter((item) => item.artist_id === state.selectedArtistId))
      picker.add(new Option(album.title, album.id));
    picker.value = "";
    fillAlbum();
    $("#album-editor").querySelector("button[type=submit]").disabled = !selectedArtist();
  }

  function fillAlbum() {
    const album = state.albums.find((item) => item.id === $("#album-picker").value);
    const form = $("#album-editor");
    form.reset();
    form.elements.title.value = album?.title || "";
    form.elements.description.value = album?.description || "";
  }

  async function saveArtist(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const id = state.selectedArtistId;
    try {
      const saved = await api(id == null ? "/api/artists" : `/api/artists/${id}`,
        { method: "POST", body: new FormData(form) });
      state.artists = await api("/api/artists/mine");
      await selectArtist(saved.id);
      status(id == null ? "새 아티스트를 만들었습니다." : "프로필을 저장했습니다.");
    } catch (error) { status(error.message, true); }
  }

  async function saveAlbum(event) {
    event.preventDefault();
    const id = $("#album-picker").value;
    const body = new FormData(event.currentTarget);
    body.append("artist_id", String(state.selectedArtistId));
    try {
      const saved = await api(id ? `/api/albums/${encodeURIComponent(id)}` : "/api/albums",
        { method: "POST", body });
      await loadAlbums();
      $("#album-picker").value = saved.id;
      fillAlbum();
      status(id ? "앨범을 수정했습니다." : "앨범을 만들었습니다.");
    } catch (error) { status(error.message, true); }
  }

  let loaded = false;
  async function loadWhenOpen() {
    if (location.hash.split("?")[0] !== "#backoffice" || loaded) return;
    try {
      state.artists = await api("/api/artists/mine");
      await selectArtist(window.yue2Auth.user.id);
      loaded = true;
      status("");
    } catch (error) { status(error.message, true); }
  }

  function init() {
    $("#new-artist").addEventListener("click", () => { void selectArtist(null); });
    $("#album-picker").addEventListener("change", fillAlbum);
    $("#artist-editor").addEventListener("submit", saveArtist);
    $("#album-editor").addEventListener("submit", saveAlbum);
    window.addEventListener("hashchange", loadWhenOpen);
    void loadWhenOpen();
  }

  if (window.yue2Auth?.ready) void init();
  else window.addEventListener("yue2-ready", init, { once: true });
})();
