(() => {
  "use strict";

  const auth = window.yue2Auth = { ready: false, csrfToken: "", user: null };
  const gate = document.createElement("dialog");
  gate.className = "auth-gate";
  gate.setAttribute("aria-labelledby", "auth-title");
  gate.setAttribute("aria-describedby", "auth-description");
  gate.innerHTML = `
    <form class="auth-card" id="auth-form">
      <button class="auth-close" type="button" aria-label="로그인 창 닫기">×</button>
      <h1 id="auth-title">동아리 로그인</h1>
      <p class="auth-description" id="auth-description">음악을 만들려면 로그인하거나 초대 코드로 가입해 주세요.</p>
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
  const closeButton = gate.querySelector(".auth-close");
  let registering = false;
  let settingUp = false;
  let authChecked = false;
  let promptRequested = false;
  let restoringPromptFocus = false;

  function openAuth() {
    if (auth.ready) return;
    if (!authChecked) {
      promptRequested = true;
      return;
    }
    if (gate.open) return;
    showError("");
    gate.showModal();
    window.requestAnimationFrame(() => {
      if (gate.open) form.elements.username.focus();
    });
  }

  auth.open = openAuth;
  closeButton.addEventListener("click", () => gate.close());
  gate.addEventListener("close", () => {
    restoringPromptFocus = true;
    window.setTimeout(() => { restoringPromptFocus = false; }, 0);
  });
  gate.addEventListener("click", (event) => {
    if (event.target === gate) gate.close();
  });
  function requestAuth() {
    if (auth.ready || restoringPromptFocus) return;
    openAuth();
  }
  document.querySelectorAll("#prompt-idea, #lyrics-input, #style-input").forEach((input) => {
    input.addEventListener("pointerdown", requestAuth);
    input.addEventListener("focus", requestAuth);
  });
  document.querySelector("#composer-form")?.addEventListener("submit", (event) => {
    if (auth.ready) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    requestAuth();
  }, true);

  function showError(message) {
    errorNode.textContent = message;
    errorNode.hidden = !message;
  }

  const BASE_PATH = (() => {
    const path = window.location.pathname;
    return path.endsWith("/") ? path.slice(0, -1) : path.replace(/\/[^/]*$/, "");
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
    if (!response.ok) {
      const error = new Error("요청을 처리하지 못했습니다.");
      error.status = response.status;
      throw error;
    }
    return response.json();
  }

  function activate(result) {
    auth.user = result.user;
    auth.csrfToken = result.csrf_token;
    auth.ready = true;
    if (gate.open) gate.close();
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
      if (result.user.role === "admin") {
        const adminControls = document.querySelector("#backoffice-admin-controls");
        if (adminControls) addAdminControls(adminControls);
      }
    }
    window.dispatchEvent(new Event("yue2-ready"));
  }

  function addAdminControls(profile) {
    const button = document.createElement("button");
    button.className = "auth-admin-button";
    button.type = "button";
    button.textContent = "초대 코드 관리";
    button.setAttribute("aria-haspopup", "dialog");
    button.setAttribute("aria-expanded", "false");
    const panel = document.createElement("dialog");
    panel.className = "auth-admin-panel";
    panel.setAttribute("aria-labelledby", "auth-admin-title");
    const header = document.createElement("div");
    header.className = "auth-admin-header";
    const heading = document.createElement("h2");
    heading.id = "auth-admin-title";
    heading.textContent = "초대 코드 관리";
    const closeButton = document.createElement("button");
    closeButton.className = "auth-admin-close";
    closeButton.type = "button";
    closeButton.textContent = "닫기";
    closeButton.addEventListener("click", () => panel.close());
    header.append(heading, closeButton);
    const content = document.createElement("div");
    content.className = "auth-admin-content";
    panel.append(header, content);
    document.body.append(panel);
    profile.append(button);
    panel.addEventListener("close", () => {
      button.setAttribute("aria-expanded", "false");
      button.focus();
    });
    panel.addEventListener("click", (event) => {
      if (event.target === panel) panel.close();
    });

    async function loadInvites() {
      const data = await api("/api/admin/invites");
      const invites = data.invites || [];
      content.replaceChildren();
      heading.textContent = `초대 코드 (${invites.length}개)`;

      const createForm = document.createElement("div");
      createForm.className = "auth-new-invite";
      const noteInput = document.createElement("input");
      noteInput.placeholder = "누구에게 줄 코드인가요?";
      noteInput.setAttribute("aria-label", "초대 코드 메모 (선택)");
      noteInput.maxLength = 30;
      const usesInput = document.createElement("input");
      usesInput.type = "number";
      usesInput.value = "1";
      usesInput.min = "1";
      usesInput.max = "100";
      usesInput.title = "사용 가능 횟수";
      usesInput.setAttribute("aria-label", "사용 가능 횟수");
      const noteLabel = document.createElement("label");
      noteLabel.textContent = "메모 (선택)";
      noteLabel.append(noteInput);
      const usesLabel = document.createElement("label");
      usesLabel.textContent = "사용 가능 횟수";
      usesLabel.append(usesInput);
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
          alert("초대 코드를 발급하지 못했습니다. 다시 시도해 주세요.");
        } finally {
          createBtn.disabled = false;
        }
      });
      createForm.append(noteLabel, usesLabel, createBtn);

      const list = document.createElement("div");
      list.className = "auth-invite-list";

      if (invites.length === 0) {
        const empty = document.createElement("p");
        empty.className = "auth-invite-empty";
        empty.textContent = "발급된 초대 코드가 없습니다.";
        list.append(empty);
      } else {
        invites.forEach((inv) => {
          const row = document.createElement("div");
          row.className = "auth-invite-row";

          const info = document.createElement("div");
          info.className = "auth-invite-info";

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

      content.append(createForm, list);
    }

    button.addEventListener("click", async () => {
      if (panel.open) {
        panel.close();
        return;
      }
      panel.showModal();
      button.setAttribute("aria-expanded", "true");
      try {
        await loadInvites();
        content.querySelector(".auth-new-invite input")?.focus();
      } catch (error) {
        alert("초대 코드를 불러오지 못했습니다. 다시 시도해 주세요.");
        panel.close();
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
      const signedIn = await api(settingUp ? "/api/auth/setup" : registering ? "/api/auth/register" : "/api/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.fromEntries(data))
      });
      const result = await api("/api/auth/me");
      if (!result.user || result.user.id !== signedIn.user?.id) {
        throw new Error("로그인 상태를 유지할 수 없습니다. 브라우저 쿠키와 접속 주소를 확인하세요.");
      }
      activate(result);
    } catch (error) {
      const message = error.status === 401 ? "아이디 또는 비밀번호를 확인하세요."
        : error.status === 403 && !registering && !settingUp ? "관리자 승인을 기다리는 계정입니다."
        : error.status === 403 && settingUp ? "설정 코드를 확인하세요."
        : error.status === 400 && registering ? "입력 내용과 초대 코드를 확인하세요."
        : error.status === 400 ? "입력 내용을 확인하세요."
        : error.status === 409 ? "설정이 변경되었습니다. 화면을 새로고침해 주세요."
        : "처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
      showError(message);
    }
    finally { submit.disabled = false; }
  });

  api("/api/auth/me").then((result) => {
    if (result.user) {
      activate(result);
      return;
    }
    return prepareGuest();
  }).catch(prepareGuest);

  async function prepareGuest() {
    if (auth.ready) return;
    try {
      const status = await api("/api/auth/setup-status");
      if (status.required) {
        settingUp = true;
        title.textContent = "최초 관리자 설정";
        gate.querySelector(".auth-description").textContent = "서버 창의 설정 코드를 입력해 관리자 계정을 만드세요.";
        nameField.hidden = false;
        inviteField.hidden = true;
        codeField.hidden = false;
        submit.textContent = "관리자 만들기";
        switchButton.hidden = true;
        form.elements.password.autocomplete = "new-password";
        form.elements.password.minLength = 12;
      }
    } catch { showError("서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."); }
    authChecked = true;
    if (promptRequested) openAuth();
  }
})();
