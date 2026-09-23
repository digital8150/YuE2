(() => {
  "use strict";

  const auth = window.yue2Auth = { ready: false, csrfToken: "", user: null };
  const gate = document.createElement("div");
  gate.className = "auth-gate";
  gate.innerHTML = `
    <form class="auth-card" id="auth-form">
      <p class="auth-eyebrow">YUE STUDIO · CLUB</p>
      <h1 id="auth-title">동아리 로그인</h1>
      <p class="auth-description">초대 코드로 즉시 가입하여 동아리원들과 작업할 수 있습니다.</p>
      <label class="auth-name-field" hidden>표시 이름<input name="display_name" autocomplete="name" maxlength="40"></label>
      <label class="auth-invite-field" hidden>초대 코드<input name="invite_code" autocomplete="off" placeholder="초대 코드 입력" maxlength="32"></label>
      <label class="auth-code-field" hidden>서버 창의 설정 코드<input name="setup_code" autocomplete="off"></label>
      <label>아이디<input name="username" autocomplete="username" required minlength="3" maxlength="32"></label>
      <label>비밀번호<input name="password" type="password" autocomplete="current-password" required></label>
      <p class="auth-error" role="alert" hidden></p>
      <button class="auth-submit" type="submit">로그인</button>
      <button class="auth-switch" type="button">초대 코드로 가입하기</button>
    </form>`;
  document.body.append(gate);

  const form = gate.querySelector("#auth-form");
  const errorNode = gate.querySelector(".auth-error");
  const nameField = gate.querySelector(".auth-name-field");
  const inviteField = gate.querySelector(".auth-invite-field");
  const codeField = gate.querySelector(".auth-code-field");
  const title = gate.querySelector("#auth-title");
  const submit = gate.querySelector(".auth-submit");
  const switchButton = gate.querySelector(".auth-switch");
  let registering = false;
  let settingUp = false;

  function showError(message) {
    errorNode.textContent = message;
    errorNode.hidden = !message;
  }

  const BASE_PATH = (() => {
    const path = window.location.pathname;
    return path.endsWith("/") ? path.slice(0, -1) : path;
  })();

  function resolvePath(path) {
    if (path.startsWith("http://") || path.startsWith("https://")) return path;
    const clean = path.startsWith("/") ? path : `/${path}`;
    return BASE_PATH && !clean.startsWith(BASE_PATH) ? `${BASE_PATH}${clean}` : clean;
  }

  async function api(path, options = {}) {
    const response = await fetch(resolvePath(path), {
      credentials: "same-origin",
      ...options,
      headers: { ...(options.headers || {}), ...(auth.csrfToken ? { "X-Yue2-CSRF": auth.csrfToken } : {}) }
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || "요청을 처리하지 못했습니다.");
    return body;
  }

  function activate(result) {
    auth.user = result.user;
    auth.csrfToken = result.csrf_token;
    auth.ready = true;
    gate.hidden = true;
    const profile = document.querySelector(".sidebar-footer .profile");
    if (profile) {
      profile.replaceChildren();
      const name = document.createElement("span");
      name.textContent = result.user.display_name;
      const logout = document.createElement("button");
      logout.className = "auth-logout";
      logout.type = "button";
      logout.textContent = "로그아웃";
      logout.addEventListener("click", async () => {
        await api("/api/auth/logout", { method: "POST" });
        location.reload();
      });
      profile.append(name, logout);
      if (result.user.role === "admin") addAdminControls(profile);
    }
    window.dispatchEvent(new Event("yue2-ready"));
  }

  function addAdminControls(profile) {
    const button = document.createElement("button");
    button.className = "auth-admin-button";
    button.type = "button";
    button.textContent = "초대 코드 관리";
    const panel = document.createElement("section");
    panel.className = "auth-admin-panel";
    panel.hidden = true;
    profile.after(panel);
    profile.append(button);

    async function loadInvites() {
      const data = await api("/api/admin/invites");
      const invites = data.invites || [];
      panel.replaceChildren();

      const header = document.createElement("div");
      header.style.display = "flex";
      header.style.justifyContent = "space-between";
      header.style.alignItems = "center";
      header.style.marginBottom = "10px";

      const heading = document.createElement("h2");
      heading.style.margin = "0";
      heading.textContent = `초대 코드 (${invites.length}개)`;
      header.append(heading);

      const createForm = document.createElement("div");
      createForm.className = "auth-new-invite";
      const noteInput = document.createElement("input");
      noteInput.placeholder = "메모 (선택)";
      noteInput.maxLength = 30;
      const usesInput = document.createElement("input");
      usesInput.type = "number";
      usesInput.value = "1";
      usesInput.min = "1";
      usesInput.max = "100";
      usesInput.style.width = "48px";
      usesInput.title = "사용 가능 횟수";
      const createBtn = document.createElement("button");
      createBtn.type = "button";
      createBtn.textContent = "+ 발급";
      createBtn.addEventListener("click", async () => {
        try {
          createBtn.disabled = true;
          const maxUses = parseInt(usesInput.value, 10) || 1;
          await api("/api/admin/invites", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ note: noteInput.value.trim(), max_uses: maxUses })
          });
          noteInput.value = "";
          await loadInvites();
        } catch (error) {
          alert(error.message);
        } finally {
          createBtn.disabled = false;
        }
      });
      createForm.append(noteInput, usesInput, createBtn);

      const list = document.createElement("div");
      list.className = "auth-invite-list";
      list.style.maxHeight = "200px";
      list.style.overflowY = "auto";

      if (invites.length === 0) {
        const empty = document.createElement("p");
        empty.style.color = "#888";
        empty.style.fontSize = "12px";
        empty.textContent = "발급된 초대 코드가 없습니다.";
        list.append(empty);
      } else {
        invites.forEach((inv) => {
          const row = document.createElement("div");
          row.className = "auth-invite-row";

          const info = document.createElement("div");
          info.style.overflow = "hidden";
          info.style.textOverflow = "ellipsis";
          info.style.whiteSpace = "nowrap";

          const codeSpan = document.createElement("span");
          codeSpan.className = "auth-invite-code";
          codeSpan.textContent = inv.code;

          const metaSpan = document.createElement("span");
          metaSpan.className = "auth-invite-meta";
          const remaining = inv.remaining !== undefined ? inv.remaining : (inv.max_uses - inv.uses);
          metaSpan.textContent = ` (${inv.uses}/${inv.max_uses}회${inv.note ? ` · ${inv.note}` : ""})`;
          if (remaining <= 0) {
            codeSpan.style.textDecoration = "line-through";
            codeSpan.style.opacity = "0.5";
            metaSpan.style.opacity = "0.5";
          }

          info.append(codeSpan, metaSpan);

          const copyBtn = document.createElement("button");
          copyBtn.type = "button";
          copyBtn.textContent = "복사";
          copyBtn.addEventListener("click", async () => {
            try {
              await navigator.clipboard.writeText(inv.code);
              copyBtn.textContent = "완료!";
              setTimeout(() => { copyBtn.textContent = "복사"; }, 1500);
            } catch {
              prompt("초대 코드를 복사하세요:", inv.code);
            }
          });

          row.append(info, copyBtn);
          list.append(row);
        });
      }

      panel.append(header, createForm, list);
    }

    button.addEventListener("click", async () => {
      panel.hidden = !panel.hidden;
      if (!panel.hidden) {
        try { await loadInvites(); } catch (error) { alert(error.message); }
      }
    });
  }

  switchButton.addEventListener("click", () => {
    if (settingUp) return;
    registering = !registering;
    title.textContent = registering ? "초대 코드로 가입" : "동아리 로그인";
    nameField.hidden = !registering;
    inviteField.hidden = !registering;
    form.elements.password.autocomplete = registering ? "new-password" : "current-password";
    form.elements.password.minLength = registering ? 12 : 0;
    submit.textContent = registering ? "가입하기" : "로그인";
    switchButton.textContent = registering ? "로그인으로 돌아가기" : "초대 코드로 가입하기";
    showError("");
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    showError("");
    submit.disabled = true;
    const data = new FormData(form);
    try {
      const result = await api(settingUp ? "/api/auth/setup" : registering ? "/api/auth/register" : "/api/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.fromEntries(data))
      });
      activate(result);
    } catch (error) { showError(error.message); }
    finally { submit.disabled = false; }
  });

  api("/api/auth/me").then(activate).catch(async () => {
    gate.hidden = false;
    try {
      const status = await api("/api/auth/setup-status");
      if (status.required) {
        settingUp = true;
        title.textContent = "최초 관리자 설정";
        gate.querySelector(".auth-description").textContent = "서버 창에 표시된 설정 코드를 입력하고 관리자 계정을 만드세요.";
        nameField.hidden = false;
        inviteField.hidden = true;
        codeField.hidden = false;
        submit.textContent = "관리자 만들기";
        switchButton.hidden = true;
        form.elements.password.autocomplete = "new-password";
        form.elements.password.minLength = 12;
      }
    } catch { showError("서버에 연결할 수 없습니다."); }
  });
})();
