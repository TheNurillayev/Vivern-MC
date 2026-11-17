// Vivern MC - Mini App Client Logic
(function () {
  const tg = window.Telegram?.WebApp;
  let currentUser = null;
  let authToken = null;
  let originalFile = null;
  let specialFile = null;

  if (tg) {
    tg.ready();
    tg.expand();
    if (tg.setHeaderColor) tg.setHeaderColor("#0f111a");
    if (tg.setBackgroundColor) tg.setBackgroundColor("#0f111a");
  }

  async function initAuth() {
    const rawInitData = tg?.initData || "test_user_8449563084";
    try {
      const response = await fetch("/api/auth/telegram", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ init_data: rawInitData }),
      });

      if (!response.ok) {
        throw new Error("Autentifikatsiya xatosi: " + response.statusText);
      }

      const data = await response.json();
      currentUser = data.user;
      authToken = data.token;
      sessionStorage.setItem("vivern_token", authToken);
      sessionStorage.setItem("vivern_user", JSON.stringify(currentUser));

      renderUserProfile();
    } catch (err) {
      console.error("Auth error:", err);
      showGlobalError("Kirishda xatolik: " + err.message);
    }
  }

  function showGlobalError(msg) {
    const errBox = document.getElementById("global-error");
    if (errBox) {
      errBox.textContent = msg;
      errBox.classList.remove("hidden");
    }
  }

  function renderUserProfile() {
    if (!currentUser) return;

    const nameEl = document.getElementById("user-name");
    const trialEl = document.getElementById("trial-badge");
    const adminTab = document.getElementById("tab-admin");
    const orderPriceEl = document.getElementById("order-price-label");

    if (nameEl) {
      nameEl.textContent = currentUser.first_name || "Foydalanuvchi";
    }

    const remaining = Math.max(0, 5 - (currentUser.trial_count || 0));
    if (trialEl) {
      trialEl.textContent = remaining > 0 ? `${remaining} ta bepul` : "5,000 so'm";
    }

    if (orderPriceEl) {
      orderPriceEl.textContent = remaining > 0 ? `Bepul (${remaining}/5 ta qoldi)` : "5,000 so'm";
    }

    if (currentUser.is_admin && adminTab) {
      adminTab.classList.remove("hidden");
    }

    // Populate Account Page details
    const accName = document.getElementById("acc-name");
    const accUsername = document.getElementById("acc-username");
    const accIdBadge = document.getElementById("acc-id-badge");
    const accTrial = document.getElementById("acc-trial-status");
    const fullName = `${currentUser.first_name || ""} ${currentUser.last_name || ""}`.trim() || "Foydalanuvchi";
    if (accName) accName.textContent = fullName;
    if (accUsername) accUsername.textContent = currentUser.username ? `@${currentUser.username}` : `ID: ${currentUser.id}`;
    if (accIdBadge) accIdBadge.textContent = `Telegram ID: ${currentUser.id}`;
    if (accTrial) accTrial.textContent = remaining > 0 ? `${remaining} ta bepul (5 tadan)` : "Tugagan (Pullik rejim)";
  }

  window.switchTab = function (tabId) {
    document.querySelectorAll(".tab-content").forEach((el) => el.classList.add("hidden"));
    document.querySelectorAll(".tab-btn").forEach((el) => el.classList.remove("active"));

    const target = document.getElementById("page-" + tabId);
    const btn = document.getElementById("tab-" + tabId);

    if (target) target.classList.remove("hidden");
    if (btn) btn.classList.add("active");

    if (tabId === "orders") {
      loadOrders();
    }
  };

  // Setup file listeners
  function setupUploadInputs() {
    const origInput = document.getElementById("input-original");
    const specInput = document.getElementById("input-special");

    if (origInput) {
      origInput.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (file) {
          originalFile = file;
          document.getElementById("filename-original").textContent = `${file.name} (${(file.size / (1024*1024)).toFixed(1)} MB)`;
          document.getElementById("file-info-original").classList.remove("hidden");
        }
      });
    }

    if (specInput) {
      specInput.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (file) {
          specialFile = file;
          document.getElementById("filename-special").textContent = `${file.name} (${(file.size / (1024*1024)).toFixed(1)} MB)`;
          document.getElementById("file-info-special").classList.remove("hidden");
        }
      });
    }
  }

  // Timing settings toggle
  window.toggleTimingSettings = function () {
    const el = document.getElementById("timing-inputs");
    const chevron = document.getElementById("timing-chevron");
    if (!el) return;
    if (el.classList.contains("hidden")) {
      el.classList.remove("hidden");
      if (chevron) chevron.textContent = "(Ixtiyoriy) ▲";
    } else {
      el.classList.add("hidden");
      if (chevron) chevron.textContent = "(Ixtiyoriy) ▼";
    }
  };

  // Confirmation Modal controls
  window.openConfirmModal = function () {
    if (!originalFile) {
      alert("Iltimos, telefon suhbati audiosini tanlang!");
      return;
    }
    if (!specialFile) {
      alert("Iltimos, sevimli musiqa faylini tanlang!");
      return;
    }
    const modal = document.getElementById("modal-confirm");
    if (modal) modal.classList.remove("hidden");
  };

  window.closeConfirmModal = function () {
    const modal = document.getElementById("modal-confirm");
    if (modal) modal.classList.add("hidden");
  };

  window.proceedSubmitAudioOrder = async function () {
    closeConfirmModal();
    await submitAudioOrder();
  };

  function parseTimeStringToSeconds(str) {
    if (!str || !str.trim()) return null;
    str = str.trim();
    if (str.includes(":")) {
      const parts = str.split(":");
      const m = parseFloat(parts[0]) || 0;
      const s = parseFloat(parts[1]) || 0;
      return m * 60 + s;
    }
    const val = parseFloat(str);
    return isNaN(val) ? null : val;
  }

  window.submitAudioOrder = async function () {
    if (!originalFile) {
      alert("Iltimos, telefon suhbati audiosini tanlang!");
      return;
    }
    if (!specialFile) {
      alert("Iltimos, sevimli musiqa faylini tanlang!");
      return;
    }

    const btn = document.getElementById("btn-submit-order");
    const progressContainer = document.getElementById("upload-progress-container");
    const progressText = document.getElementById("upload-progress-text");

    btn.disabled = true;
    btn.style.opacity = "0.5";
    progressContainer.classList.remove("hidden");
    progressText.textContent = "Fayllar yuklanmoqda va tekshirilmoqda...";

    const formData = new FormData();
    formData.append("original_recording", originalFile);
    formData.append("special_music", specialFile);

    // Optional custom timings
    const wStartInput = document.getElementById("input-wishes-start")?.value;
    const wEndInput = document.getElementById("input-wishes-end")?.value;
    const wStart = parseTimeStringToSeconds(wStartInput);
    const wEnd = parseTimeStringToSeconds(wEndInput);
    if (wStart !== null) formData.append("custom_wishes_start_seconds", wStart);
    if (wEnd !== null) formData.append("custom_call_ending_seconds", wEnd);

    try {
      const res = await fetch("/api/orders/create", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${authToken}`
        },
        body: formData
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Buyurtma berishda xatolik");
      }

      // Reset inputs
      originalFile = null;
      specialFile = null;
      document.getElementById("file-info-original").classList.add("hidden");
      document.getElementById("file-info-special").classList.add("hidden");
      document.getElementById("input-original").value = "";
      document.getElementById("input-special").value = "";
      if (document.getElementById("input-wishes-start")) document.getElementById("input-wishes-start").value = "";
      if (document.getElementById("input-wishes-end")) document.getElementById("input-wishes-end").value = "";

      // Switch to orders history
      switchTab("orders");
    } catch (err) {
      alert("Xatolik: " + err.message);
    } finally {
      btn.disabled = false;
      btn.style.opacity = "1";
      progressContainer.classList.add("hidden");
    }
  };

  let pollTimer = null;
  window.loadOrders = async function (isAutoPoll = false) {
    if (pollTimer) clearTimeout(pollTimer);
    const listEl = document.getElementById("orders-list");
    if (!listEl) return;

    if (!isAutoPoll) {
      listEl.innerHTML = '<div style="text-align:center; padding: 25px;"><div class="spinner"></div><div style="margin-top:10px; color:var(--text-muted); font-size:0.85rem;">Buyurtmalar yangilanmoqda...</div></div>';
    }

    try {
      const res = await fetch("/api/orders/my", {
        headers: { "Authorization": `Bearer ${authToken}` }
      });
      if (!res.ok) throw new Error("Buyurtmalarni yuklab bo'lmadi");
      const orders = await res.json();

      const totalOrdersEl = document.getElementById("acc-total-orders");
      if (totalOrdersEl && Array.isArray(orders)) {
        totalOrdersEl.textContent = `${orders.length} ta`;
      }

      if (orders.length === 0) {
        listEl.innerHTML = `
          <div style="text-align: center; padding: 40px 20px; color: var(--text-muted);">
            <div style="font-size: 2.5rem; margin-bottom: 8px;">📭</div>
            <div style="font-weight: 600;">Hozircha buyurtmalar yo'q</div>
            <div style="font-size: 0.8rem; margin-top: 4px;">Birinchi audio montajingizni yarating!</div>
          </div>
        `;
        return;
      }

      let hasActiveOrders = false;

      listEl.innerHTML = orders.map((o) => {
        let statusBadge = '<span class="badge-tag" style="background:var(--accent-blue);">Kutilmoqda</span>';
        if (o.status === "completed") {
          statusBadge = '<span class="badge-tag" style="background:var(--accent-emerald);">✓ Tayyor</span>';
        } else if (o.status === "failed") {
          statusBadge = '<span class="badge-tag" style="background:var(--danger-color);">Xatolik</span>';
        } else if (["queued", "transcribing", "analysing", "rendering"].includes(o.status)) {
          hasActiveOrders = true;
          let stageText = "Tayyorlanmoqda...";
          if (o.status === "transcribing") stageText = "🎙️ Tahlil qilinmoqda...";
          else if (o.status === "analysing") stageText = "🧠 Segmentlar aniqlanmoqda...";
          else if (o.status === "rendering") stageText = "⚡ FFmpeg montaj...";
          statusBadge = `<span class="badge-tag" style="background:var(--accent-gold); color:#111;">${stageText}</span>`;
        }

        const dateStr = new Date(o.created_at).toLocaleString("uz-UZ", {
          month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
        });

        const dlUrl = `/api/orders/${o.id}/download`;

        return `
          <div class="card" style="margin-bottom: 12px; padding: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
              <div>
                <div style="font-weight: 600; font-size: 0.95rem;">Buyurtma #${o.id.substring(0, 8)}</div>
                <div style="font-size: 0.75rem; color: var(--text-muted);">${dateStr}</div>
              </div>
              ${statusBadge}
            </div>
            <div style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 10px;">
              📞 Suhbat: <b>${o.original_recording_name}</b><br>
              🎶 Musiqa: <b>${o.special_music_name}</b>
            </div>
            ${o.status === "completed" ? `
              <div style="margin-top: 10px;">
                <audio controls src="${dlUrl}" style="width:100%; height:36px;"></audio>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px;">
                  <span style="font-size: 0.75rem; color: var(--accent-emerald);">
                    ✓ Telegram botingizga ham yuborildi
                  </span>
                  <a href="${dlUrl}" download="Vivern_MC_${o.id.substring(0,8)}.mp3" class="btn btn-secondary" style="width:auto; padding:6px 12px; font-size:0.8rem; text-decoration:none;">
                    ⬇️ MP3 Yuklab Olish
                  </a>
                </div>
              </div>
            ` : ""}
            ${hasActiveOrders ? `
              <div style="font-size: 0.75rem; color: var(--accent-gold); margin-top: 6px; display:flex; align-items:center; gap:6px;">
                <span class="spinner" style="width:14px; height:14px; border-width:2px;"></span>
                <span>Serverda qayta ishlanmoqda, sahifani yangilash shart emas...</span>
              </div>
            ` : ""}
            ${o.error_message ? `<div style="color:var(--danger-color); font-size:0.75rem; margin-top:6px;">${o.error_message}</div>` : ""}
          </div>
        `;
      }).join("");

      // If any order is still processing, poll again in 2.5 seconds
      if (hasActiveOrders) {
        pollTimer = setTimeout(() => {
          loadOrders(true);
        }, 2500);
      }
    } catch (err) {
      listEl.innerHTML = `<div style="color:var(--danger-color); text-align:center; padding:20px;">${err.message}</div>`;
    }
  };

  document.addEventListener("DOMContentLoaded", () => {
    initAuth();
    setupUploadInputs();
  });
})();
