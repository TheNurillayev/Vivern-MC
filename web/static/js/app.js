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

    const totalAllowed = 3 + (currentUser.extra_trials || 0);
    const remaining = Math.max(0, totalAllowed - (currentUser.trial_count || 0));
    const isPaused = Boolean(currentUser.save_trials);
    const userCoins = currentUser.coins || 0;

    if (trialEl) {
      if (isPaused) {
        trialEl.textContent = `⏸️ Saqlangan (${remaining} ta)`;
      } else if (remaining > 0) {
        trialEl.textContent = `${remaining} ta bepul`;
      } else {
        trialEl.textContent = `${userCoins} Tanga`;
      }
    }

    // Clean Service Price Display (Images 1 & 2)
    if (orderPriceEl) {
      if (!isPaused && remaining > 0) {
        orderPriceEl.innerHTML = '<span style="color:var(--accent-emerald); font-weight:700;">Bepul</span>';
      } else {
        orderPriceEl.innerHTML = '<span style="color:var(--accent-gold); font-weight:700;">10 Tanga</span>';
      }
    }

    if (currentUser.is_admin && adminTab) {
      adminTab.classList.remove("hidden");
    }

    // Populate Account Page details (Images 4 & 5)
    const accName = document.getElementById("acc-name");
    const accUsername = document.getElementById("acc-username");
    const accCoins = document.getElementById("acc-coins-status");
    const accTrial = document.getElementById("acc-trial-status");
    const accTrialIcon = document.getElementById("acc-trial-icon");
    const accAvatar = document.getElementById("acc-avatar");
    const fullName = `${currentUser.first_name || ""} ${currentUser.last_name || ""}`.trim() || "Foydalanuvchi";

    if (accName) accName.textContent = fullName;
    if (accUsername) accUsername.textContent = currentUser.username ? `@${currentUser.username}` : `ID: ${currentUser.id}`;
    if (accCoins) accCoins.textContent = `${userCoins} Tanga`;

    // Dynamic icon: ⚡ when active, 🔋 when paused/inactive (Image 5)
    if (accTrialIcon) {
      accTrialIcon.textContent = isPaused ? "🔋" : "⚡";
    }

    if (accTrial) {
      accTrial.textContent = remaining > 0 ? `${remaining} ta bepul` : "Tugagan (Pullik rejim)";
    }
    if (accAvatar) {
      if (currentUser.avatar_url) {
        accAvatar.style.backgroundImage = `url("${currentUser.avatar_url}")`;
        accAvatar.textContent = "";
      } else {
        accAvatar.style.backgroundImage = "none";
        accAvatar.textContent = "👤";
      }
    }
  }

  window.toggleProfileEditMenu = function (e) {
    if (e) e.stopPropagation();
    const menu = document.getElementById("profile-edit-menu");
    if (menu) menu.classList.toggle("hidden");
  };

  document.addEventListener("click", (e) => {
    const menu = document.getElementById("profile-edit-menu");
    if (menu && !menu.classList.contains("hidden")) {
      if (!e.target.closest("#profile-edit-menu") && !e.target.closest(".btn-profile-action") && !e.target.closest(".btn-profile-edit")) {
        menu.classList.add("hidden");
      }
    }
  });

  window.openFullProfilePhoto = function () {
    const menu = document.getElementById("profile-edit-menu");
    if (menu) menu.classList.add("hidden");

    if (!currentUser || !currentUser.avatar_url) {
      alert("Siz hali profil rasmi yuklamagansiz. 📷 Rasmni o'zgartirish orqali rasm yuklashingiz mumkin.");
      return;
    }
    const modal = document.getElementById("modal-view-photo");
    const img = document.getElementById("view-photo-img");
    if (img) img.src = currentUser.avatar_url;
    if (modal) modal.classList.remove("hidden");
  };

  window.closeViewPhotoModal = function () {
    const modal = document.getElementById("modal-view-photo");
    if (modal) modal.classList.add("hidden");
  };

  window.openChangeNameModal = function () {
    const menu = document.getElementById("profile-edit-menu");
    if (menu) menu.classList.add("hidden");

    const modal = document.getElementById("modal-change-name");
    const input = document.getElementById("input-change-name");
    if (input) {
      input.value = (currentUser?.first_name || "").trim();
      setTimeout(() => {
        input.focus();
        input.select();
      }, 60);
    }
    if (modal) modal.classList.remove("hidden");
  };

  window.closeChangeNameModal = function () {
    const modal = document.getElementById("modal-change-name");
    if (modal) modal.classList.add("hidden");
  };

  window.submitChangeName = async function () {
    const input = document.getElementById("input-change-name");
    const newName = input.value.trim();
    if (!newName) {
      alert("Iltimos, ismingizni kiriting!");
      return;
    }

    try {
      const activeToken = authToken || sessionStorage.getItem("vivern_token");
      const res = await fetch("/api/auth/profile/name", {
        method: "PATCH",
        headers: {
          "Authorization": `Bearer ${activeToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ first_name: newName })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Ismni o'zgartirib bo'lmadi");

      currentUser.first_name = data.first_name;
      renderUserProfile();
      closeChangeNameModal();
      if (window.Telegram?.WebApp?.showPopup) {
        window.Telegram.WebApp.showPopup({
          title: "Muvaffaqiyatli",
          message: "Ismingiz muvaffaqiyatli saqlandi!",
          buttons: [{ type: "ok" }]
        });
      } else {
        alert("✅ Ismingiz muvaffaqiyatli saqlandi!");
      }
    } catch (err) {
      alert("Xatolik: " + err.message);
    }
  };

  window.triggerProfilePhotoUpload = function () {
    const menu = document.getElementById("profile-edit-menu");
    if (menu) menu.classList.add("hidden");
    const input = document.getElementById("input-profile-photo");
    if (input) input.click();
  };

  window.handleProfilePhotoSelected = async function (event) {
    const file = event.target.files[0];
    if (!file) return;

    if (file.size > 10 * 1024 * 1024) {
      alert("Rasm hajmi 10MB dan oshmasligi kerak!");
      return;
    }

    const accAvatar = document.getElementById("acc-avatar");
    // Instant local preview
    const previewUrl = URL.createObjectURL(file);
    if (accAvatar) {
      accAvatar.style.backgroundImage = `url("${previewUrl}")`;
      accAvatar.textContent = "";
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      const activeToken = authToken || sessionStorage.getItem("vivern_token");
      const res = await fetch("/api/auth/profile/photo", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${activeToken}`
        },
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Rasmni yuklab bo'lmadi");

      currentUser.avatar_url = data.avatar_url;
      if (accAvatar) {
        accAvatar.style.backgroundImage = `url("${data.avatar_url}")`;
        accAvatar.textContent = "";
      }
      if (window.Telegram?.WebApp?.showPopup) {
        window.Telegram.WebApp.showPopup({
          title: "Muvaffaqiyatli",
          message: "Profil rasmingiz muvaffaqiyatli saqlandi!",
          buttons: [{ type: "ok" }]
        });
      } else {
        alert("✅ Profil rasmingiz muvaffaqiyatli saqlandi!");
      }
    } catch (err) {
      alert("Xatolik: " + err.message);
      renderUserProfile();
    } finally {
      event.target.value = "";
    }
  };

  // Modal: Gifts (Image 2)
  window.openUserGiftsModal = async function () {
    const modal = document.getElementById("modal-user-gifts");
    const container = document.getElementById("user-gifts-content");
    if (modal) modal.classList.remove("hidden");
    if (!container) return;

    container.innerHTML = '<div style="text-align:center; padding: 25px;"><div class="spinner"></div><div style="margin-top:10px; color:var(--text-muted); font-size:0.85rem;">Sovg\'alar yuklanmoqda...</div></div>';

    try {
      const activeToken = authToken || sessionStorage.getItem("vivern_token");
      const res = await fetch("/api/auth/profile/gifts", {
        headers: { "Authorization": `Bearer ${activeToken}` }
      });
      const gifts = await res.json();

      if (!Array.isArray(gifts) || gifts.length === 0) {
        container.innerHTML = `
          <div style="text-align: center; padding: 25px 15px; color: var(--text-muted);">
            <div style="font-size: 2.8rem; margin-bottom: 8px;">🎁</div>
            <div style="font-weight: 600; font-size: 0.95rem; color: #fff;">Hozircha sovg'alar yo'q</div>
            <div style="font-size: 0.8rem; margin-top: 6px; line-height: 1.5;">
              Administrator faol foydalanuvchilarga bepul urinishlar va maxsus sovg'alar taqdim etadi. Sovg'a berilganda bu yerda ko'rinadi! 🎉
            </div>
          </div>
        `;
        return;
      }

      container.innerHTML = gifts.map(g => `
        <div style="background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 12px; padding: 12px 14px; margin-bottom: 10px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <b style="color: var(--accent-gold); font-size: 0.92rem;">${escapeHtml(g.title)}</b>
            <span style="font-size: 0.72rem; color: var(--text-muted);">${g.created_at}</span>
          </div>
          <div style="font-size: 0.82rem; color: #e2e8f0; margin-bottom: 4px;">
            ✨ +${g.trials_given} ta bepul urinish
          </div>
          ${g.message ? `<div style="font-size: 0.76rem; color: var(--text-muted); font-style: italic;">"${escapeHtml(g.message)}"</div>` : ''}
        </div>
      `).join("");
    } catch (e) {
      container.innerHTML = `<div style="color:var(--danger-color); font-size:0.85rem; padding:15px; text-align:center;">Sovg'alarni yuklashda xatolik yuz berdi.</div>`;
    }
  };

  window.closeUserGiftsModal = function () {
    const modal = document.getElementById("modal-user-gifts");
    if (modal) modal.classList.add("hidden");
  };

  // Modal: Settings (Image 2)
  window.openUserSettingsModal = function () {
    const modal = document.getElementById("modal-user-settings");
    const notifToggle = document.getElementById("setting-toggle-notifs");
    if (notifToggle) {
      const stored = localStorage.getItem("vivern_notifications_enabled");
      notifToggle.checked = stored === null ? true : stored === "true";
    }
    if (modal) modal.classList.remove("hidden");
  };

  window.closeUserSettingsModal = function () {
    const modal = document.getElementById("modal-user-settings");
    if (modal) modal.classList.add("hidden");
  };

  window.toggleNotificationsSetting = function (e) {
    localStorage.setItem("vivern_notifications_enabled", e.target.checked);
  };

  // Modal: Trial Balance (Image 3)
  window.openTrialBalanceModal = function () {
    const modal = document.getElementById("modal-trial-balance");
    updateTrialModalContent();
    if (modal) modal.classList.remove("hidden");
  };

  window.closeTrialBalanceModal = function () {
    const modal = document.getElementById("modal-trial-balance");
    if (modal) modal.classList.add("hidden");
  };

  function updateTrialModalContent() {
    if (!currentUser) return;
    const totalAllowed = 3 + (currentUser.extra_trials || 0);
    const remaining = Math.max(0, totalAllowed - (currentUser.trial_count || 0));
    const countEl = document.getElementById("modal-trial-count-display");
    const badgeEl = document.getElementById("trial-save-mode-badge");
    const btnEl = document.getElementById("btn-toggle-save-trials");

    if (countEl) {
      countEl.textContent = `${remaining} ta bepul`;
    }

    if (currentUser.save_trials) {
      if (badgeEl) {
        badgeEl.innerHTML = "⏸️ <b>Tejalmoqda</b> (Keyingi buyurtmalar uchun saqlab qo'yilgan)";
        badgeEl.style.borderColor = "rgba(245, 158, 11, 0.5)";
        badgeEl.style.color = "var(--accent-gold)";
      }
      if (btnEl) {
        btnEl.textContent = "▶️ Bepul urinishlarni faollashtirish";
        btnEl.className = "btn btn-primary";
      }
    } else {
      if (badgeEl) {
        badgeEl.innerHTML = "🟢 <b>Faol</b> (Buyurtma berganda bepul urinish ishlatiladi)";
        badgeEl.style.borderColor = "rgba(16, 185, 129, 0.5)";
        badgeEl.style.color = "var(--accent-emerald)";
      }
      if (btnEl) {
        btnEl.textContent = "⏸️ Bepul urinishlarni saqlab qo'yish (Tejash)";
        btnEl.className = "btn btn-secondary";
      }
    }
  }

  window.toggleSaveTrialsAction = async function () {
    const btn = document.getElementById("btn-toggle-save-trials");
    if (btn) btn.disabled = true;

    try {
      const activeToken = authToken || sessionStorage.getItem("vivern_token");
      const res = await fetch("/api/auth/profile/toggle-save-trials", {
        method: "PATCH",
        headers: { "Authorization": `Bearer ${activeToken}` }
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Holatni o'zgartirib bo'lmadi");

      currentUser.save_trials = data.save_trials;
      updateTrialModalContent();
      renderUserProfile();
    } catch (err) {
      alert("Xatolik: " + err.message);
    } finally {
      if (btn) btn.disabled = false;
    }
  };

  // Modal: Price Explanation (Image 3)
  window.openPriceExplanationModal = function () {
    const modal = document.getElementById("modal-price-explanation");
    if (modal) modal.classList.remove("hidden");
  };

  window.closePriceExplanationModal = function () {
    const modal = document.getElementById("modal-price-explanation");
    if (modal) modal.classList.add("hidden");
  };

  // Selected coin package state
  let selectedCoinPackage = { coins: 10, price: 5000, name: "10 Tanga (1 ta buyurtma)" };

  // Modal: Coin Balance & Top-up (Images 1, 4 & 5)
  window.openCoinBalanceModal = function () {
    const modal = document.getElementById("modal-coin-balance");
    const countEl = document.getElementById("modal-coin-count");
    if (countEl) {
      countEl.textContent = `${currentUser?.coins || 0} Tanga`;
    }
    if (modal) modal.classList.remove("hidden");
  };

  window.closeCoinBalanceModal = function () {
    const modal = document.getElementById("modal-coin-balance");
    if (modal) modal.classList.add("hidden");
  };

  window.selectCoinPackage = function (coins, price, name, el) {
    selectedCoinPackage = { coins, price, name };
    document.querySelectorAll(".coin-pkg-card").forEach(c => c.classList.remove("selected"));
    if (el) el.classList.add("selected");

    const selectEl = document.getElementById("receipt-package-select");
    if (selectEl) selectEl.value = String(coins);
  };

  window.onReceiptDropdownChange = function (selectEl) {
    const opt = selectEl.options[selectEl.selectedIndex];
    const coins = parseInt(opt.value, 10);
    const price = parseInt(opt.getAttribute("data-price"), 10);
    const name = opt.getAttribute("data-name");
    selectedCoinPackage = { coins, price, name };

    document.querySelectorAll(".coin-pkg-card").forEach(c => c.classList.remove("selected"));
    const card = document.getElementById("pkg-" + coins);
    if (card) card.classList.add("selected");
  };

  window.copyCardNumber = function () {
    const cardNum = "4097830011461668";
    const copyBtn = document.getElementById("btn-copy-card");
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(cardNum).then(() => {
        if (copyBtn) {
          copyBtn.textContent = "✅ Nusxalandi";
          setTimeout(() => copyBtn.textContent = "📋 Nusxa", 3000);
        }
      }).catch(() => {
        prompt("Karta raqami:", cardNum);
      });
    } else {
      prompt("Karta raqami:", cardNum);
    }
  };

  // Receipt File Attachment & Submission (Image 2 - Item 3)
  let attachedReceiptFile = null;

  window.openReceiptChoiceModal = function () {
    const modal = document.getElementById("modal-receipt-choice");
    if (modal) modal.classList.remove("hidden");
  };

  window.closeReceiptChoiceModal = function () {
    const modal = document.getElementById("modal-receipt-choice");
    if (modal) modal.classList.add("hidden");
  };

  window.triggerReceiptInput = function (type) {
    closeReceiptChoiceModal();
    if (type === "gallery") {
      document.getElementById("input-receipt-gallery")?.click();
    } else if (type === "document") {
      document.getElementById("input-receipt-document")?.click();
    }
  };

  window.handleReceiptSelected = function (e) {
    const file = e.target.files[0];
    if (!file) return;
    attachedReceiptFile = file;

    document.getElementById("receipt-upload-box")?.classList.add("hidden");
    const badge = document.getElementById("receipt-file-badge");
    if (badge) badge.classList.remove("hidden");

    const nameEl = document.getElementById("receipt-file-name");
    const sizeEl = document.getElementById("receipt-file-size");
    if (nameEl) nameEl.textContent = file.name;
    if (sizeEl) {
      const sizeKb = (file.size / 1024).toFixed(0);
      sizeEl.textContent = sizeKb > 1024 ? (sizeKb / 1024).toFixed(1) + " MB" : sizeKb + " KB";
    }

    // Light up submit button
    const btn = document.getElementById("btn-submit-receipt-final");
    if (btn) {
      btn.disabled = false;
      btn.style.opacity = "1";
      btn.style.cursor = "pointer";
      btn.style.boxShadow = "0 4px 15px rgba(245, 158, 11, 0.4)";
    }
  };

  window.removeReceiptFile = function () {
    attachedReceiptFile = null;
    const galInput = document.getElementById("input-receipt-gallery");
    const docInput = document.getElementById("input-receipt-document");
    if (galInput) galInput.value = "";
    if (docInput) docInput.value = "";

    document.getElementById("receipt-file-badge")?.classList.add("hidden");
    document.getElementById("receipt-upload-box")?.classList.remove("hidden");

    const btn = document.getElementById("btn-submit-receipt-final");
    if (btn) {
      btn.disabled = true;
      btn.style.opacity = "0.45";
      btn.style.cursor = "not-allowed";
      btn.style.boxShadow = "none";
    }
  };

  window.submitReceiptToAdmin = async function () {
    if (!attachedReceiptFile) {
      alert("Iltimos, avval to'lov cheki faylini yuklang!");
      return;
    }

    const btn = document.getElementById("btn-submit-receipt-final");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "⏳ Chek yuborilmoqda...";
    }

    try {
      const activeToken = authToken || sessionStorage.getItem("vivern_token");
      const formData = new FormData();
      formData.append("file", attachedReceiptFile);
      formData.append("package_name", selectedCoinPackage.name);
      formData.append("coins", selectedCoinPackage.coins);
      formData.append("amount_som", selectedCoinPackage.price);

      const res = await fetch("/api/auth/coins/submit-receipt", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${activeToken}`
        },
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Chekni yuborib bo'lmadi");

      alert("✅ To'lov chekingiz muvaffaqiyatli adminga yetkazildi!\n\nAdministrator tekshirib, hisobingizga " + selectedCoinPackage.coins + " ta tangani tez orada qo'shib beradi.");
      removeReceiptFile();
      closeCoinBalanceModal();
    } catch (err) {
      alert("Xatolik: " + err.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "🚀 Yuborish";
      }
    }
  };

  // Modal: Completed Orders List (Minimal: Title & Date Only - Item 1)
  window.openCompletedOrdersModal = async function () {
    const modal = document.getElementById("modal-completed-orders-list");
    const content = document.getElementById("completed-orders-modal-content");
    if (modal) modal.classList.remove("hidden");
    if (!content) return;

    content.innerHTML = '<div style="text-align: center; padding: 25px; color: var(--text-muted);"><div class="spinner"></div><div style="margin-top: 8px; font-size: 0.82rem;">Buyurtmalar yuklanmoqda...</div></div>';

    try {
      const activeToken = authToken || sessionStorage.getItem("vivern_token");
      const res = await fetch("/api/orders/my", {
        headers: { "Authorization": `Bearer ${activeToken}` }
      });
      const orders = await res.json();

      const completed = orders.filter(o => o.status === "completed");

      if (completed.length === 0) {
        content.innerHTML = `
          <div style="text-align: center; padding: 30px 15px; color: var(--text-muted);">
            <div style="font-size: 2.5rem; margin-bottom: 8px;">📋</div>
            <div style="font-weight: 600; color: #fff;">Hozircha tayyorlangan buyurtmalar yo'q</div>
            <div style="font-size: 0.8rem; margin-top: 4px;">Birinchi audio montajingizni yarating!</div>
          </div>
        `;
        return;
      }

      // Item 1: Faqatgina nomi va tayyorlangan sanasi
      content.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 8px;">
          ${completed.map((o) => {
            const title = o.audio_title && o.audio_title.trim() ? escapeHtml(o.audio_title) : `Audio #${o.id.substring(0, 8)}`;
            const dateStr = o.completed_at ? new Date(o.completed_at).toLocaleString("uz-UZ", {
              year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
            }) : (o.created_at ? new Date(o.created_at).toLocaleString("uz-UZ", {
              year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
            }) : "Noma'lum");

            return `
              <div style="background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 12px 14px; display: flex; justify-content: space-between; align-items: center;">
                <div style="min-width: 0; flex: 1;">
                  <div style="font-weight: 700; font-size: 0.92rem; color: #fff; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">
                    🎵 ${title}
                  </div>
                  <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 3px;">
                    📅 ${dateStr}
                  </div>
                </div>
                <div style="flex-shrink: 0; margin-left: 10px;">
                  <span style="font-size: 0.72rem; padding: 3px 8px; border-radius: 6px; background: rgba(16, 185, 129, 0.15); color: var(--accent-emerald); font-weight: 600;">✓ Tayyor</span>
                </div>
              </div>
            `;
          }).join("")}
        </div>
      `;
    } catch (e) {
      content.innerHTML = `<div style="color: var(--danger-color); padding: 15px; text-align: center; font-size: 0.85rem;">Buyurtmalarni yuklashda xatolik yuz berdi.</div>`;
    }
  };

  window.closeCompletedOrdersModal = function () {
    const modal = document.getElementById("modal-completed-orders-list");
    if (modal) modal.classList.add("hidden");
  };

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

          // Setup in-app audio preview player
          const audioEl = document.getElementById("audio-preview-original");
          const playerCont = document.getElementById("player-container");
          if (audioEl && playerCont) {
            audioEl.src = URL.createObjectURL(file);
            playerCont.classList.remove("hidden");
            const timingInputs = document.getElementById("timing-inputs");
            if (timingInputs) timingInputs.classList.remove("hidden");
            const chevron = document.getElementById("timing-chevron");
            if (chevron) chevron.textContent = "(Ixtiyoriy) ▲";

            audioEl.ontimeupdate = () => {
              const m = Math.floor(audioEl.currentTime / 60);
              const s = Math.floor(audioEl.currentTime % 60);
              const disp = document.getElementById("player-time-display");
              if (disp) disp.textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
            };
          }
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

  window.markCurrentTimeToWishesStart = function () {
    const audioEl = document.getElementById("audio-preview-original");
    if (!audioEl || isNaN(audioEl.currentTime)) return;
    const m = Math.floor(audioEl.currentTime / 60);
    const s = Math.floor(audioEl.currentTime % 60);
    const val = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    const input = document.getElementById("input-wishes-start");
    if (input) {
      input.value = val;
      input.style.borderColor = "var(--accent-gold)";
    }
  };

  window.markCurrentTimeToWishesEnd = function () {
    const audioEl = document.getElementById("audio-preview-original");
    if (!audioEl || isNaN(audioEl.currentTime)) return;
    const m = Math.floor(audioEl.currentTime / 60);
    const s = Math.floor(audioEl.currentTime % 60);
    const val = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    const input = document.getElementById("input-wishes-end");
    if (input) {
      input.value = val;
      input.style.borderColor = "var(--accent-purple)";
    }
  };

  // Extra settings & tabs controls
  let currentBgPreviewAudio = null;
  let currentPlayingCategory = null;
  let libraryOptionsLoaded = false;

  window.toggleExtraSettings = function () {
    const el = document.getElementById("extra-settings-content");
    const chevron = document.getElementById("extra-settings-chevron");
    if (!el) return;
    if (el.classList.contains("hidden")) {
      el.classList.remove("hidden");
      if (chevron) chevron.textContent = "(Ixtiyoriy) ▲";
      if (!libraryOptionsLoaded) {
        loadLibraryMusicOptions();
      }
    } else {
      el.classList.add("hidden");
      if (chevron) chevron.textContent = "(Ixtiyoriy) ▼";
      if (currentBgPreviewAudio) {
        currentBgPreviewAudio.pause();
        currentPlayingCategory = null;
        document.querySelectorAll("[id^='btn-preview-']").forEach(b => b.textContent = "▶️");
      }
    }
  };
  window.toggleTimingSettings = window.toggleExtraSettings;

  window.switchExtraTab = function (tabName) {
    const btnTiming = document.getElementById("tab-btn-timing");
    const btnBg = document.getElementById("tab-btn-bgmusic");
    const subTiming = document.getElementById("subtab-timing");
    const subBg = document.getElementById("subtab-bgmusic");

    if (tabName === "timing") {
      if (btnTiming) {
        btnTiming.style.background = "var(--accent-purple)";
        btnTiming.style.color = "#fff";
      }
      if (btnBg) {
        btnBg.style.background = "transparent";
        btnBg.style.color = "var(--text-muted)";
      }
      if (subTiming) subTiming.classList.remove("hidden");
      if (subBg) subBg.classList.add("hidden");
      if (currentBgPreviewAudio) {
        currentBgPreviewAudio.pause();
        currentPlayingCategory = null;
        document.querySelectorAll("[id^='btn-preview-']").forEach(b => b.textContent = "▶️");
      }
    } else {
      if (btnBg) {
        btnBg.style.background = "var(--accent-purple)";
        btnBg.style.color = "#fff";
      }
      if (btnTiming) {
        btnTiming.style.background = "transparent";
        btnTiming.style.color = "var(--text-muted)";
      }
      if (subBg) subBg.classList.remove("hidden");
      if (subTiming) subTiming.classList.add("hidden");
      const origAudio = document.getElementById("audio-preview-original");
      if (origAudio) origAudio.pause();
      if (!libraryOptionsLoaded) {
        loadLibraryMusicOptions();
      }
    }
  };

  async function loadLibraryMusicOptions() {
    try {
      const res = await fetch("/api/orders/library-options");
      if (!res.ok) return;
      const data = await res.json();
      libraryOptionsLoaded = true;

      populateBgSelect("select-starter-music", data.starter || []);
      populateBgSelect("select-wishes-music", data.wishes || []);
      populateBgSelect("select-ending-music", data.call_ending || []);
    } catch (e) {
      console.warn("Could not load library options:", e);
    }
  }

  function populateBgSelect(selectId, tracks) {
    const select = document.getElementById(selectId);
    if (!select) return;
    select.innerHTML = "";
    if (!tracks || tracks.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "Standart musiqa";
      select.appendChild(opt);
      return;
    }
    tracks.forEach(t => {
      const opt = document.createElement("option");
      opt.value = t.id;
      const durMin = Math.floor((t.duration_seconds || 0) / 60);
      const durSec = Math.floor((t.duration_seconds || 0) % 60);
      const durStr = `${durMin}:${durSec < 10 ? "0" : ""}${durSec}`;
      opt.textContent = `${t.title} (${durStr})${t.is_active ? " ⭐ (Asosiy)" : ""}`;
      if (t.is_active) opt.selected = true;
      opt.dataset.previewUrl = t.preview_url;
      select.appendChild(opt);
    });
  }

  window.togglePlayBgPreview = function (category) {
    const selectId = category === "starter" ? "select-starter-music" : (category === "wishes" ? "select-wishes-music" : "select-ending-music");
    const btnId = `btn-preview-${category}`;
    const select = document.getElementById(selectId);
    const btn = document.getElementById(btnId);
    if (!select || !btn) return;

    const selectedOpt = select.options[select.selectedIndex];
    const previewUrl = selectedOpt?.dataset?.previewUrl;
    if (!previewUrl) return;

    if (currentBgPreviewAudio && currentPlayingCategory === category && !currentBgPreviewAudio.paused) {
      currentBgPreviewAudio.pause();
      btn.textContent = "▶️";
      currentPlayingCategory = null;
      return;
    }

    if (currentBgPreviewAudio) {
      currentBgPreviewAudio.pause();
      document.querySelectorAll("[id^='btn-preview-']").forEach(b => b.textContent = "▶️");
    }

    const origAudio = document.getElementById("audio-preview-original");
    if (origAudio) origAudio.pause();

    currentBgPreviewAudio = new Audio(previewUrl);
    currentPlayingCategory = category;
    btn.textContent = "⏸️";

    currentBgPreviewAudio.play().catch(e => {
      console.warn("Audio play error:", e);
      btn.textContent = "▶️";
      currentPlayingCategory = null;
    });

    currentBgPreviewAudio.onended = function () {
      btn.textContent = "▶️";
      currentPlayingCategory = null;
    };

    currentBgPreviewAudio.onpause = function () {
      btn.textContent = "▶️";
    };
  };

  window.onBgMusicSelectChange = function (category) {
    if (currentPlayingCategory === category && currentBgPreviewAudio) {
      currentBgPreviewAudio.pause();
      currentPlayingCategory = null;
      const btn = document.getElementById(`btn-preview-${category}`);
      if (btn) btn.textContent = "▶️";
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

    const totalAllowed = 3 + (currentUser?.extra_trials || 0);
    const remaining = Math.max(0, totalAllowed - (currentUser?.trial_count || 0));
    const isPaused = Boolean(currentUser?.save_trials);
    const hasFreeTrial = (!isPaused) && (remaining > 0);
    const userCoins = currentUser?.coins || 0;

    if (!hasFreeTrial && userCoins < 10) {
      openCoinBalanceModal();
      alert("⚠️ Buyurtma berish uchun hisobingizda kamida 10 ta tanga bo'lishi kerak.\n\nSizning balansingiz: " + userCoins + " ta tanga. Iltimos, hisobingizni to'ldiring!");
      return;
    }

    const modalDesc = document.querySelector("#modal-confirm div[style*='color: var(--text-muted)']");
    if (modalDesc) {
      if (hasFreeTrial) {
        modalDesc.innerHTML = `Tanlangan telefon suhbati va musiqa asosida professional audio montaj boshlansinmi?<br><b style="color:var(--accent-emerald);">Narxi: Bepul (Sinov hisobidan)</b>`;
      } else {
        modalDesc.innerHTML = `Tanlangan telefon suhbati va musiqa asosida professional audio montaj boshlansinmi?<br><b style="color:var(--accent-gold);">Narxi: 10 Tanga (Balansingizdan sarflanadi)</b>`;
      }
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
    const audioTitleInput = document.getElementById("input-audio-title")?.value?.trim();
    if (audioTitleInput) formData.append("audio_title", audioTitleInput);

    const wStartInput = document.getElementById("input-wishes-start")?.value;
    const wEndInput = document.getElementById("input-wishes-end")?.value;
    const wStart = parseTimeStringToSeconds(wStartInput);
    const wEnd = parseTimeStringToSeconds(wEndInput);
    if (wStart !== null) formData.append("custom_wishes_start_seconds", wStart);
    if (wEnd !== null) formData.append("custom_call_ending_seconds", wEnd);

    // Optional custom background tracks
    const starterTrack = document.getElementById("select-starter-music")?.value;
    const wishesTrack = document.getElementById("select-wishes-music")?.value;
    const endingTrack = document.getElementById("select-ending-music")?.value;
    if (starterTrack) formData.append("custom_starter_track_id", starterTrack);
    if (wishesTrack) formData.append("custom_wishes_track_id", wishesTrack);
    if (endingTrack) formData.append("custom_ending_track_id", endingTrack);

    if (currentBgPreviewAudio) {
      currentBgPreviewAudio.pause();
      currentPlayingCategory = null;
      document.querySelectorAll("[id^='btn-preview-']").forEach(b => b.textContent = "▶️");
    }

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
      const audioEl = document.getElementById("audio-preview-original");
      if (audioEl) {
        audioEl.pause();
        audioEl.removeAttribute("src");
      }
      const playerCont = document.getElementById("player-container");
      if (playerCont) playerCont.classList.add("hidden");
      const wStartEl = document.getElementById("input-wishes-start");
      const wEndEl = document.getElementById("input-wishes-end");
      if (wStartEl) wStartEl.value = "";
      if (wEndEl) wEndEl.value = "";
      document.getElementById("input-original").value = "";
      document.getElementById("input-special").value = "";
      if (document.getElementById("input-audio-title")) document.getElementById("input-audio-title").value = "";
      if (document.getElementById("input-wishes-start")) document.getElementById("input-wishes-start").value = "";
      if (document.getElementById("input-wishes-end")) document.getElementById("input-wishes-end").value = "";

      // If paid order, deduct 10 coins locally and refresh
      const totalAllowed = 3 + (currentUser?.extra_trials || 0);
      const remaining = Math.max(0, totalAllowed - (currentUser?.trial_count || 0));
      const isPaused = Boolean(currentUser?.save_trials);
      const hasFreeTrial = (!isPaused) && (remaining > 0);

      if (!hasFreeTrial) {
        currentUser.coins = Math.max(0, (currentUser.coins || 0) - 10);
      }
      renderUserProfile();

      // Refresh /api/auth/me in background
      fetch("/api/auth/me", {
        headers: { "Authorization": `Bearer ${authToken}` }
      }).then(r => r.json()).then(u => {
        if (u && u.id) {
          currentUser = u;
          renderUserProfile();
        }
      }).catch(() => {});

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

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  window.downloadOrderAudio = async function (orderId, btnEl, orderTitle = "") {
    const origHtml = btnEl ? btnEl.innerHTML : "";
    if (btnEl) {
      btnEl.innerHTML = "⏳ Yuklanmoqda...";
      btnEl.disabled = true;
    }
    const cleanTitle = (orderTitle && orderTitle.trim())
      ? orderTitle.trim().replace(/[^\w\s-]/g, '').replace(/[-\s]+/g, '_')
      : "";
    const fileName = cleanTitle ? `${cleanTitle}.mp3` : `Vivern_MC_${orderId.substring(0, 8)}.mp3`;
    const dlUrl = `/api/orders/${orderId}/download`;
    const fullUrl = new URL(dlUrl, window.location.origin).href;

    // 1. Try Telegram native downloadFile (Bot API 8.0+)
    if (window.Telegram?.WebApp?.downloadFile) {
      try {
        window.Telegram.WebApp.downloadFile({
          url: fullUrl,
          file_name: fileName
        }, function (accepted) {
          if (btnEl) {
            btnEl.innerHTML = origHtml;
            btnEl.disabled = false;
          }
        });
        return;
      } catch (e) {
        console.warn("Telegram downloadFile fallback", e);
      }
    }

    // 2. Direct Blob Fetch & Download for mobile WebView & browsers
    try {
      const res = await fetch(fullUrl);
      if (!res.ok) throw new Error("Faylni yuklab bo'lmadi");
      const blob = await res.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.style.display = "none";
      a.href = blobUrl;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        window.URL.revokeObjectURL(blobUrl);
        if (a.parentNode) a.parentNode.removeChild(a);
      }, 1500);
    } catch (err) {
      // 3. Fallback: open link externally
      if (window.Telegram?.WebApp?.openLink) {
        window.Telegram.WebApp.openLink(fullUrl);
      } else {
        window.open(fullUrl, "_blank");
      }
    } finally {
      if (btnEl) {
        btnEl.innerHTML = origHtml;
        btnEl.disabled = false;
      }
    }
  };

  let orderPendingDelete = null;

  window.promptDeleteOrder = function (orderId) {
    orderPendingDelete = orderId;
    const modal = document.getElementById("modal-delete-order");
    if (modal) modal.classList.remove("hidden");
  };

  window.closeDeleteOrderModal = function () {
    orderPendingDelete = null;
    const modal = document.getElementById("modal-delete-order");
    if (modal) modal.classList.add("hidden");
  };

  window.confirmDeleteOrder = async function () {
    if (!orderPendingDelete) return;
    const btn = document.getElementById("btn-confirm-delete-order");
    const origText = btn ? btn.textContent : "O'chirish";
    if (btn) {
      btn.disabled = true;
      btn.textContent = "O'chirilmoqda...";
    }

    try {
      const activeToken = authToken || sessionStorage.getItem("vivern_token");
      const res = await fetch(`/api/orders/${orderPendingDelete}`, {
        method: "DELETE",
        headers: { "Authorization": `Bearer ${activeToken}` }
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Buyurtmani o'chirib bo'lmadi");

      closeDeleteOrderModal();
      await loadOrders(false);
      if (typeof loadUserProfile === "function") {
        await loadUserProfile();
      }
    } catch (err) {
      alert("Xatolik: " + err.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = origText;
      }
    }
  };

  window.toggleOrderActionButtons = function (orderId) {
    const row = document.getElementById(`order-actions-${orderId}`);
    if (!row) return;
    if (row.style.display === "none") {
      row.style.display = "flex";
    } else {
      row.style.display = "none";
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
      const activeToken = authToken || sessionStorage.getItem("vivern_token");
      const res = await fetch("/api/orders/my", {
        headers: { "Authorization": `Bearer ${activeToken}` }
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
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <div>
                ${o.audio_title ? `
                  <div style="font-weight: 700; font-size: 0.95rem; color: var(--accent-gold); margin-bottom: 2px;">
                    🏷️ ${escapeHtml(o.audio_title)}
                  </div>
                ` : ''}
                <div style="font-weight: 600; font-size: 0.88rem; color: var(--text-main);">Buyurtma #${o.id.substring(0, 8)}</div>
                <div style="font-size: 0.75rem; color: var(--text-muted);">${dateStr}</div>
              </div>
              ${o.status === "completed" ? `
                <button type="button" class="btn-order-pencil" onclick="toggleOrderActionButtons('${o.id}')" title="Amallar (Yuklab olish / O'chirish)">
                  <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2.3" fill="none" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path>
                  </svg>
                </button>
              ` : statusBadge}
            </div>
            <div style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 10px; width: 100%; overflow: hidden;">
              <div class="order-text-row">
                📞 Suhbat: <b style="color: var(--text-main);">${escapeHtml(o.original_recording_name)}</b>
              </div>
              <div class="order-text-row" style="margin-top: 3px;">
                🎶 Musiqa: <b style="color: var(--text-main);">${escapeHtml(o.special_music_name)}</b>
              </div>
            </div>
            ${o.status === "completed" ? `
              <div style="margin-top: 10px;">
                <audio controls src="${dlUrl}" style="width:100%; height:36px;"></audio>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px;">
                  <span style="font-size: 0.75rem; color: var(--accent-emerald);">
                    ✓ Telegram botingizga ham yuborildi
                  </span>
                  <span class="badge-tag" style="background:var(--accent-emerald); font-size:0.75rem; font-weight:600; padding:2px 8px; border-radius:8px;">
                    ✓ Tayyor
                  </span>
                </div>
                <div id="order-actions-${o.id}" class="order-action-buttons-row" style="display: none; justify-content: space-between; align-items: center; margin-top: 10px; gap: 10px;">
                  <button type="button" onclick="downloadOrderAudio('${o.id}', this, '${escapeHtml(o.audio_title || '')}')" class="btn btn-secondary" style="flex: 1; padding: 8px 12px; font-size: 0.82rem; border-radius: 10px; background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.4); color: #93c5fd; cursor: pointer; text-align: center;">
                    ⬇️ MP3 Yuklab Olish
                  </button>
                  <button type="button" onclick="promptDeleteOrder('${o.id}')" class="btn btn-secondary" style="flex: 1; padding: 8px 12px; font-size: 0.82rem; border-radius: 10px; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #fca5a5; cursor: pointer; text-align: center;">
                    🗑️ O'chirish
                  </button>
                </div>
              </div>
            ` : `
              <div style="display: flex; justify-content: flex-end; margin-top: 8px;">
                <button type="button" onclick="promptDeleteOrder('${o.id}')" class="btn btn-secondary" style="width: auto; padding: 5px 12px; font-size: 0.78rem; border-radius: 8px; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #fca5a5; cursor: pointer;">
                  🗑️ O'chirish
                </button>
              </div>
            `}
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
    loadLibraryMusicOptions();
  });
})();
