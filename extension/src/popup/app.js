import { getDismissed, dismissAssignment } from '../lib/cache.js';
import {
  getCourses,
  getUpcomingAssignments,
  getCourseAssignments,
  setToken,
  clearCache,
  refreshBadge,
} from '../lib/extension-api.js';

// ── DOM Refs ──────────────────────────────────────────────────────────────────

const $upcomingList    = document.getElementById("upcoming-list");
const $loading         = document.getElementById("loading");
const $error           = document.getElementById("error");
const $userInfo        = document.getElementById("user-info");
const $refreshBtn      = document.getElementById("refresh-btn");
const $settingsBtn     = document.getElementById("settings-btn");
const $courseFilter    = document.getElementById("course-filter");
const $filterSection   = document.getElementById("filter-section");
const $cacheBadge      = document.getElementById("cache-badge");
const $assignmentCount = document.getElementById("assignment-count");

const $tabs            = document.querySelectorAll(".tab");
const $viewUpcoming    = document.getElementById("view-upcoming");
const $viewCourses     = document.getElementById("view-courses");
const $viewDetail      = document.getElementById("view-course-detail");
const $coursesList     = document.getElementById("courses-list");
const $coursesLoading  = document.getElementById("courses-loading");
const $coursesError    = document.getElementById("courses-error");
const $backBtn         = document.getElementById("back-btn");
const $detailName      = document.getElementById("detail-course-name");
const $detailList      = document.getElementById("detail-list");
const $detailLoading   = document.getElementById("detail-loading");
const $detailEmpty     = document.getElementById("detail-empty");

// ── State ─────────────────────────────────────────────────────────────────────

let allAssignments = [];
let dismissedIds   = new Set();
let courses        = [];
let activeTab      = "upcoming";

// ── Helpers ───────────────────────────────────────────────────────────────────

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatDue(dateStr) {
  if (!dateStr) return "No due date";
  const dueDate = new Date(dateStr);
  const diff = dueDate - new Date();
  const days  = Math.floor(diff / 86400000);
  const hours = Math.floor(diff / 3600000);
  if (diff < 0)   return "Overdue";
  if (hours < 1)  return "Due in under 1 hour";
  if (hours < 24) return `Due in ${hours}h`;
  if (days === 1) return "Due tomorrow";
  return `Due in ${days} days`;
}

function urgentClass(dateStr) {
  if (!dateStr) return "";
  const diff = new Date(dateStr) - new Date();
  if (diff < 0)         return "overdue";
  if (diff < 86400000)  return "urgent";
  if (diff < 172800000) return "due-soon";
  return "";
}

function getCourseName(item) {
  return item.context_course_name || item.course_name || "Canvas";
}

function getDueDate(item) {
  return item.all_day ? item.start_at : item.due_at;
}

function updateAssignmentCount(count) {
  $assignmentCount.textContent = `${count} item${count === 1 ? "" : "s"}`;
  $assignmentCount.classList.toggle("hidden", !count);
}

function renderEmptyState(message = "No upcoming assignments", detail = "You're caught up for now.") {
  updateAssignmentCount(0);
  $upcomingList.innerHTML = `
    <li class="status-card empty-state">
      <strong>${escapeHtml(message)}</strong>
      <span>${escapeHtml(detail)}</span>
    </li>`;
}

// ── Render: Upcoming ──────────────────────────────────────────────────────────

function renderAssignment(item) {
  if (item.type !== "assignment") return "";
  const id         = String(item.assignment?.id || item.id);
  if (dismissedIds.has(id)) return "";
  const courseName = getCourseName(item);
  const dueDate    = getDueDate(item);
  const cls        = urgentClass(dueDate);
  const dueText    = formatDue(dueDate);
  const title      = item.title || item.assignment?.name || "Assignment";
  const url        = item.html_url || "";

  return `
    <li class="assignment-item ${cls}" data-id="${escapeHtml(id)}">
      <div class="assignment-main">
        <div class="course-name" title="${escapeHtml(courseName)}">${escapeHtml(courseName)}</div>
        <div class="assignment-name">${escapeHtml(title)}</div>
        <div class="due-date ${cls}">${escapeHtml(dueText)}</div>
      </div>
      <div class="assignment-actions">
        <button class="dismiss-btn" data-id="${escapeHtml(id)}" title="Mark done">✓</button>
        <button class="open-btn" data-url="${escapeHtml(url)}" title="Open in Canvas">→</button>
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
      refreshBadge().catch(() => {});
    });
  });
  list.querySelectorAll(".open-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const url = btn.dataset.url;
      if (url) window.open(url, "_blank");
    });
  });
}

function renderUpcoming() {
  $loading.classList.add("hidden");
  const filtered = $courseFilter.value
    ? allAssignments.filter(a => getCourseName(a) === $courseFilter.value)
    : allAssignments;

  const visible = filtered.filter(a => !dismissedIds.has(String(a.assignment?.id || a.id)));
  updateAssignmentCount(visible.length);

  if (!visible.length) { renderEmptyState(); return; }

  $upcomingList.innerHTML = visible.map(renderAssignment).join("");
  attachItemHandlers($upcomingList);
}

function populateCourseFilter() {
  const unique = [...new Set(allAssignments.map(getCourseName).filter(Boolean))].sort();
  if (!unique.length) return;
  $filterSection.classList.remove("hidden");
  $courseFilter.innerHTML = `<option value="">All Courses</option>` +
    unique.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
}

// ── Render: Courses ───────────────────────────────────────────────────────────

function renderCourses(courseList) {
  $coursesLoading.classList.add("hidden");
  if (!courseList.length) {
    $coursesError.textContent = "No active courses found.";
    $coursesError.classList.remove("hidden");
    return;
  }

  $coursesList.innerHTML = courseList.map(c => `
    <li class="course-card" data-id="${escapeHtml(String(c.id))}" data-name="${escapeHtml(c.name || c.course_code || "Course")}">
      <span class="course-dot"></span>
      <div class="course-info">
        <div class="course-full-name">${escapeHtml(c.name || "Unnamed Course")}</div>
        <div class="course-code">${escapeHtml(c.course_code || "")}</div>
      </div>
      <span class="course-arrow">›</span>
    </li>`).join("");

  $coursesList.querySelectorAll(".course-card").forEach(card => {
    card.addEventListener("click", () => {
      openCourseDetail(card.dataset.id, card.dataset.name);
    });
  });
}

// ── Course Detail ─────────────────────────────────────────────────────────────

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

    const upcoming = (res.data || [])
      .filter(a => a.due_at && new Date(a.due_at) > new Date())
      .sort((a, b) => new Date(a.due_at) - new Date(b.due_at));

    if (!upcoming.length) { $detailEmpty.classList.remove("hidden"); return; }

    $detailList.innerHTML = upcoming.map(a => {
      const cls = urgentClass(a.due_at);
      return `
        <li class="assignment-item ${cls}">
          <div class="assignment-main">
            <div class="assignment-name">${escapeHtml(a.name || "Assignment")}</div>
            <div class="due-date ${cls}">${escapeHtml(formatDue(a.due_at))}</div>
          </div>
          <div class="assignment-actions">
            <button class="open-btn" data-url="${escapeHtml(a.html_url || "")}" title="Open in Canvas">→</button>
          </div>
        </li>`;
    }).join("");

    $detailList.querySelectorAll(".open-btn").forEach(btn => {
      btn.addEventListener("click", () => { if (btn.dataset.url) window.open(btn.dataset.url, "_blank"); });
    });
  } catch (err) {
    $detailLoading.classList.add("hidden");
    $detailList.innerHTML = `<li class="status-card error">${escapeHtml(err.message)}</li>`;
  }
}

// ── Tab Navigation ────────────────────────────────────────────────────────────

function switchTab(name) {
  activeTab = name;
  $tabs.forEach(t => t.classList.toggle("active", t.dataset.view === name));
  $viewUpcoming.classList.toggle("active", name === "upcoming");
  $viewUpcoming.classList.toggle("hidden", name !== "upcoming");
  $filterSection.classList.toggle("hidden", name !== "upcoming");
  $viewCourses.classList.toggle("active", name === "courses");
  $viewCourses.classList.toggle("hidden", name !== "courses");
  $viewDetail.classList.add("hidden");
  $viewDetail.classList.remove("active");

  if (name === "courses" && !$coursesList.innerHTML) loadCourses();
}

$tabs.forEach(t => t.addEventListener("click", () => switchTab(t.dataset.view)));

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
      courses = coursesRes.data;
      $userInfo.textContent = `${courses.length} courses`;
    }

    const res = await getUpcomingAssignments();
    if (!res.ok) throw new Error(res.error || "Failed to fetch");

    allAssignments = (res.data || []).filter(e => e.type === "assignment");
    if (res.cached) $cacheBadge.classList.remove("hidden");
    else $cacheBadge.classList.add("hidden");

    populateCourseFilter();
    renderUpcoming();
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
    if (!res.ok) throw new Error(res.error || "Failed");
    renderCourses(res.data || []);
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
        <button id="save-token" class="btn btn-primary" style="width:100%;margin-top:8px">Save Token</button>
        <div id="token-status" style="margin-top:8px;font-size:0.78rem;text-align:center"></div>
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
  await clearCache().catch(() => {});
  if (activeTab === "upcoming") await loadUpcoming();
  else if (activeTab === "courses") { $coursesList.innerHTML = ""; await loadCourses(); }
});

$settingsBtn.addEventListener("click", () => {
  if (!document.getElementById("settings-panel")) openSettings();
});

$courseFilter.addEventListener("change", renderUpcoming);

loadUpcoming();
