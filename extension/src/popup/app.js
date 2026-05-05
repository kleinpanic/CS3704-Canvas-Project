import { getDismissed, dismissAssignment } from '../lib/cache.js';
import {
  getCourses,
  getCourseAssignments,
  getUpcomingAssignments,
  setToken,
  clearCache,
  refreshBadge,
} from '../lib/extension-api.js';

// ── DOM Refs ──────────────────────────────────────────────────────────────────

const $userInfo       = document.getElementById("user-info");
const $cacheBadge     = document.querySelector(".cache-badge");
const $refreshBtn     = document.getElementById("refresh-btn");
const $settingsBtn    = document.getElementById("settings-btn");

// Tabs
const $tabs           = document.querySelectorAll(".tab");
const $viewUpcoming   = document.getElementById("view-upcoming");
const $viewCourses    = document.getElementById("view-courses");
const $viewDetail     = document.getElementById("view-course-detail");

// Upcoming
const $upcomingList   = document.getElementById("upcoming-list");
const $loading        = document.getElementById("loading");
const $error          = document.getElementById("error");
const $filterSection  = document.getElementById("filter-section");
const $courseFilter   = document.getElementById("course-filter");

// Courses
const $coursesList    = document.getElementById("courses-list");
const $coursesLoading = document.getElementById("courses-loading");
const $coursesError   = document.getElementById("courses-error");

// Detail
const $backBtn        = document.getElementById("back-btn");
const $detailName     = document.getElementById("detail-course-name");
const $detailList     = document.getElementById("detail-list");
const $detailLoading  = document.getElementById("detail-loading");
const $detailEmpty    = document.getElementById("detail-empty");

// ── State ─────────────────────────────────────────────────────────────────────

let allAssignments = [];
let dismissedIds   = new Set();
let allCourses     = [];
let activeTab      = "upcoming";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDue(dateStr) {
  if (!dateStr) return "No due date";
  const d = new Date(dateStr);
  const now = new Date();
  const diff = d - now;
  const hours = Math.floor(diff / 3600000);
  const days  = Math.floor(diff / 86400000);
  if (diff < 0)    return "OVERDUE";
  if (hours < 1)   return "Due < 1h";
  if (hours < 24)  return `Due in ${hours}h`;
  if (days === 1)  return "Due tomorrow";
  return `Due in ${days} days`;
}

function urgencyClass(dateStr) {
  if (!dateStr) return "";
  const diff = new Date(dateStr) - new Date();
  if (diff < 0)         return "overdue";
  if (diff < 86400000)  return "urgent";
  if (diff < 172800000) return "due-soon";
  return "";
}

// ── Render: Upcoming ──────────────────────────────────────────────────────────

function renderAssignmentItem(item, { showCourse = true } = {}) {
  const id = String(item.assignment?.id || item.id);
  if (dismissedIds.has(id)) return "";
  const courseName = item.context_course_name || item.course_name || "";
  const dueDate    = item.all_day ? item.start_at : item.due_at;
  const cls        = urgencyClass(dueDate);

  return `
    <li class="assignment-item ${cls}" data-id="${id}">
      <div class="assignment-main">
        ${showCourse && courseName ? `<div class="course-name">${courseName}</div>` : ""}
        <div class="assignment-name">${item.title || item.assignment?.name || "Assignment"}</div>
        <div class="due-date ${cls}">${formatDue(dueDate)}</div>
      </div>
      <div class="assignment-actions">
        <button class="dismiss-btn" data-id="${id}" title="Mark done">✓</button>
        <button class="open-btn" data-url="${item.html_url || ""}" title="Open in Canvas">→</button>
      </div>
    </li>`;
}

function attachItemHandlers(list) {
  list.querySelectorAll(".dismiss-btn").forEach(btn => {
    btn.addEventListener("click", async e => {
      e.stopPropagation();
      const id = btn.dataset.id;
      await dismissAssignment(id);
      dismissedIds.add(id);
      btn.closest(".assignment-item").remove();
      refreshBadge();
    });
  });
  list.querySelectorAll(".open-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const url = btn.dataset.url;
      if (url) window.open(url, "_blank");
    });
  });
}

function renderUpcoming(assignments) {
  $loading.classList.add("hidden");
  const filtered = $courseFilter.value
    ? assignments.filter(a => (a.context_course_name || a.course_name) === $courseFilter.value)
    : assignments;

  if (filtered.length === 0) {
    $upcomingList.innerHTML = `<li class="assignment-item"><div class="assignment-main"><div class="assignment-name">No upcoming assignments</div></div></li>`;
    return;
  }

  $upcomingList.innerHTML = filtered.map(a => renderAssignmentItem(a)).join("");
  attachItemHandlers($upcomingList);
}

function populateCourseFilter() {
  const unique = [...new Set(allAssignments.map(a => a.context_course_name || a.course_name).filter(Boolean))].sort();
  if (unique.length === 0) return;
  $filterSection.classList.remove("hidden");
  $courseFilter.innerHTML = `<option value="">All Courses</option>` +
    unique.map(c => `<option value="${c}">${c}</option>`).join("");
}

// ── Render: Courses ───────────────────────────────────────────────────────────

function renderCourses(courses) {
  $coursesLoading.classList.add("hidden");
  if (!courses.length) {
    $coursesError.textContent = "No active courses found.";
    $coursesError.classList.remove("hidden");
    return;
  }

  $coursesList.innerHTML = courses.map(c => `
    <li class="course-card" data-id="${c.id}" data-name="${encodeURIComponent(c.name || c.course_code || "Course")}">
      <span class="course-dot"></span>
      <div class="course-info">
        <div class="course-full-name">${c.name || "Unnamed Course"}</div>
        <div class="course-code">${c.course_code || ""}</div>
      </div>
      <span class="course-arrow">›</span>
    </li>`).join("");

  $coursesList.querySelectorAll(".course-card").forEach(card => {
    card.addEventListener("click", () => {
      const id   = card.dataset.id;
      const name = decodeURIComponent(card.dataset.name);
      openCourseDetail(id, name);
    });
  });
}

// ── Render: Course Detail ─────────────────────────────────────────────────────

async function openCourseDetail(courseId, courseName) {
  $viewCourses.classList.remove("active");
  $viewCourses.classList.add("hidden");
  $viewDetail.classList.remove("hidden");
  $viewDetail.classList.add("active");

  $detailName.textContent = courseName;
  $detailList.innerHTML = "";
  $detailLoading.classList.remove("hidden");
  $detailEmpty.classList.add("hidden");

  try {
    const res = await getCourseAssignments(courseId);
    $detailLoading.classList.add("hidden");

    if (!res.ok) throw new Error(res.error || "Failed");

    const assignments = (res.data || []).filter(a => {
      if (!a.due_at) return false;
      return new Date(a.due_at) > new Date();
    }).sort((a, b) => new Date(a.due_at) - new Date(b.due_at));

    if (!assignments.length) {
      $detailEmpty.classList.remove("hidden");
      return;
    }

    $detailList.innerHTML = assignments.map(a => {
      const cls = urgencyClass(a.due_at);
      return `
        <li class="assignment-item ${cls}" data-id="${a.id}">
          <div class="assignment-main">
            <div class="assignment-name">${a.name || "Assignment"}</div>
            <div class="due-date ${cls}">${formatDue(a.due_at)}</div>
          </div>
          <div class="assignment-actions">
            <button class="open-btn" data-url="${a.html_url || ""}" title="Open in Canvas">→</button>
          </div>
        </li>`;
    }).join("");

    $detailList.querySelectorAll(".open-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const url = btn.dataset.url;
        if (url) window.open(url, "_blank");
      });
    });
  } catch (err) {
    $detailLoading.classList.add("hidden");
    $detailList.innerHTML = `<li class="state-msg error">${err.message}</li>`;
  }
}

// ── Tab Navigation ────────────────────────────────────────────────────────────

function switchTab(tabName) {
  if (tabName === "course-detail") return;
  activeTab = tabName;

  $tabs.forEach(t => t.classList.toggle("active", t.dataset.view === tabName));

  $viewUpcoming.classList.toggle("active",  tabName === "upcoming");
  $viewUpcoming.classList.toggle("hidden",  tabName !== "upcoming");
  $viewCourses.classList.toggle("active",   tabName === "courses");
  $viewCourses.classList.toggle("hidden",   tabName !== "courses");
  $viewDetail.classList.add("hidden");
  $viewDetail.classList.remove("active");

  if (tabName === "courses" && $coursesList.innerHTML === "") {
    loadCourses();
  }
}

$tabs.forEach(tab => {
  tab.addEventListener("click", () => switchTab(tab.dataset.view));
});

$backBtn.addEventListener("click", () => {
  $viewDetail.classList.add("hidden");
  $viewDetail.classList.remove("active");
  $viewCourses.classList.remove("hidden");
  $viewCourses.classList.add("active");
});

// ── Data Loading ──────────────────────────────────────────────────────────────

async function loadUpcoming() {
  $loading.classList.remove("hidden");
  $error.classList.add("hidden");
  $upcomingList.innerHTML = "";

  try {
    dismissedIds = await getDismissed();

    const coursesRes = await getCourses();
    if (coursesRes.ok && coursesRes.data?.length) {
      allCourses = coursesRes.data;
      $userInfo.textContent = `${allCourses.length} courses`;
    }

    const res = await getUpcomingAssignments();
    if (!res.ok) throw new Error(res.error || "Failed to fetch");

    allAssignments = res.data.filter(e => e.type === "assignment");
    populateCourseFilter();
    renderUpcoming(allAssignments);

    if (res.cached) {
      $cacheBadge.classList.remove("hidden");
    } else {
      $cacheBadge.classList.add("hidden");
    }
  } catch (err) {
    $loading.classList.add("hidden");
    $error.textContent = err.message;
    $error.classList.remove("hidden");
  }
}

async function loadCourses() {
  $coursesLoading.classList.remove("hidden");
  $coursesError.classList.add("hidden");
  $coursesList.innerHTML = "";

  try {
    const res = await getCourses();
    if (!res.ok) throw new Error(res.error || "Failed to fetch courses");
    allCourses = res.data || [];
    renderCourses(allCourses);
  } catch (err) {
    $coursesLoading.classList.add("hidden");
    $coursesError.textContent = err.message;
    $coursesError.classList.remove("hidden");
  }
}

// ── Settings Panel ────────────────────────────────────────────────────────────

function openSettings() {
  const panel = document.createElement("div");
  panel.id = "settings-panel";
  panel.innerHTML = `
    <div style="max-width:340px;width:100%">
      <div class="settings-header">
        <h2>Settings</h2>
        <button id="close-settings">✕</button>
      </div>
      <div class="settings-body">
        <label>
          Canvas API Token
          <input type="password" id="token-input" placeholder="Paste your Canvas API token…" />
          <small>canvas.vt.edu → Account → Settings → New Access Token</small>
        </label>
        <button id="save-token" class="primary-btn">Save Token</button>
        <div id="token-status"></div>
      </div>
    </div>`;
  document.body.appendChild(panel);

  document.getElementById("close-settings").onclick = () => panel.remove();
  document.getElementById("save-token").onclick = async () => {
    const token = document.getElementById("token-input").value.trim();
    if (!token) return;
    const status = document.getElementById("token-status");
    status.textContent = "Saving…";
    const res = await setToken(token);
    status.textContent = res.ok ? "Token saved!" : `Error: ${res.error}`;
    if (res.ok) setTimeout(() => panel.remove(), 1000);
  };
}

// ── Init ──────────────────────────────────────────────────────────────────────

$refreshBtn.addEventListener("click", async () => {
  await clearCache();
  if (activeTab === "upcoming") {
    await loadUpcoming();
  } else if (activeTab === "courses") {
    await loadCourses();
  }
});

$settingsBtn.addEventListener("click", () => {
  if (!document.getElementById("settings-panel")) openSettings();
});

$courseFilter.addEventListener("change", () => renderUpcoming(allAssignments));

loadUpcoming();
