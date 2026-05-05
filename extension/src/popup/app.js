/**
 * Canvas Deadline Tracker — Popup App
 *
 * Features:
 * - Tab navigation: Upcoming assignments / All courses / Course detail
 * - Course filter (dropdown to filter by course)
 * - Stale-while-revalidate (instant load from cache, background refresh)
 * - Dismiss/snooze assignments
 * - Quick open in Canvas
 * - Settings panel for token management and preferences (theme, days-ahead)
 */

import { getDismissed, dismissAssignment } from '../lib/cache.js';
import {
  getCourses,
  getCourseAssignments,
  getCourseAnnouncements,
  getCourseModules,
  getUpcomingAssignments,
  setToken,
  clearCache,
  refreshBadge,
  getPreferences,
  savePreferences,
  getRmpRating,
  getCourseGrades,
  getToken,
  agentQuery,
} from '../lib/extension-api.js';

// ── DOM Refs ──────────────────────────────────────────────────────────────────

const $summaryBanner  = document.getElementById("summary-banner");
const $noTokenState   = document.getElementById("no-token-state");
const $userInfo       = document.getElementById("user-info");
const $cacheBadge     = document.querySelector(".cache-badge");
const $refreshBtn     = document.getElementById("refresh-btn");
const $settingsBtn    = document.getElementById("settings-btn");

// Tabs
const $tabs           = document.querySelectorAll(".tab");
const $viewUpcoming   = document.getElementById("view-upcoming");
const $viewCourses    = document.getElementById("view-courses");
const $viewDetail     = document.getElementById("view-course-detail");
const $viewAgent      = document.getElementById("view-agent");

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

// Grades
const $gradesList    = document.getElementById("grades-list");
const $gradesLoading = document.getElementById("grades-loading");
const $gradesError   = document.getElementById("grades-error");
const $viewGrades    = document.getElementById("view-grades");

// Detail
const $backBtn          = document.getElementById("back-btn");
const $detailName       = document.getElementById("detail-course-name");
const $detailList       = document.getElementById("detail-list");
const $detailLoading    = document.getElementById("detail-loading");
const $detailEmpty      = document.getElementById("detail-empty");
const $professorSection = document.getElementById("professor-section");

// Detail Tabs & Sub-views
const $detailTabs           = document.querySelectorAll(".detail-tab");
const $detailAssignments    = document.getElementById("detail-assignments");
const $detailAnnouncements  = document.getElementById("detail-announcements");
const $detailModules        = document.getElementById("detail-modules");
const $announcementsList    = document.getElementById("announcements-list");
const $announcementsEmpty   = document.getElementById("announcements-empty");
const $modulesList          = document.getElementById("modules-list");
const $modulesEmpty         = document.getElementById("modules-empty");

// ── State ─────────────────────────────────────────────────────────────────────

let allAssignments = [];
let dismissedIds   = new Set();
let allCourses     = [];
let activeTab      = "upcoming";
let settingsOpen   = false;
let prefs          = { theme: "light", daysAhead: 7 };
let gradesLoaded   = false;

// ── Helpers ───────────────────────────────────────────────────────────────────

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function showErrorWithRetry($el, message, retryFn) {
  $el.innerHTML = "";
  const msg = document.createElement("span");
  msg.textContent = message;
  const btn = document.createElement("button");
  btn.className = "btn-secondary retry-btn";
  btn.style.cssText = "margin-top:var(--space-sm);font-size:var(--size-xs)";
  btn.textContent = "Try again";
  btn.addEventListener("click", retryFn);
  $el.append(msg, btn);
  $el.classList.remove("hidden");
}

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

function getDueDate(item) {
  return item.all_day ? item.start_at : item.due_at;
}

function applyTheme(theme) {
  document.body.classList.toggle("dark-theme", theme === "dark");
}

// ── Render: Upcoming ──────────────────────────────────────────────────────────

function renderAssignmentItem(item, { showCourse = true } = {}) {
  const id = String(item.assignment?.id || item.id);
  if (dismissedIds.has(id)) return "";
  const courseName = item.context_course_name || item.course_name || "";
  const dueDate    = getDueDate(item);
  const cls        = urgencyClass(dueDate);

  return `
    <li class="assignment-item ${cls}" data-id="${id}">
      <div class="assignment-main">
        ${showCourse && courseName ? `<div class="course-name">${esc(courseName)}</div>` : ""}
        <div class="assignment-name">${esc(item.title || item.assignment?.name || "Assignment")}</div>
        <div class="due-date ${cls}">${formatDue(dueDate)}</div>
      </div>
      <div class="assignment-actions">
        <button class="dismiss-btn" data-id="${esc(id)}" title="Mark done" aria-label="Mark done">✓</button>
        <button class="open-btn" data-url="${esc(item.html_url || "")}" title="Open in Canvas" aria-label="Open in Canvas">→</button>
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

  // Summary banner
  const urgentCount = filtered.filter(a => {
    const d = getDueDate(a);
    if (!d) return false;
    const diff = new Date(d) - new Date();
    return diff < 86400000;
  }).length;

  if (filtered.length > 0) {
    $summaryBanner.classList.remove("hidden");
    if (urgentCount > 0) {
      $summaryBanner.className = "summary-banner urgent";
      $summaryBanner.textContent = `⚠️ ${urgentCount} due within 24h`;
    } else {
      $summaryBanner.className = "summary-banner ok";
      $summaryBanner.textContent = "✓ No urgent deadlines";
    }
  } else {
    $summaryBanner.classList.add("hidden");
  }

  if (filtered.length === 0) {
    $upcomingList.innerHTML = `<li class="assignment-item"><div class="assignment-main"><div class="assignment-name">📚 All caught up! No upcoming assignments.</div></div></li>`;
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
    $coursesError.innerHTML = `🎓 No active courses found.`;
    $coursesError.classList.remove("hidden");
    return;
  }

  $coursesList.innerHTML = courses.map(c => {
    const teacher = c.teachers?.[0]?.display_name || "";
    return `
      <li class="course-card" data-id="${c.id}" data-name="${encodeURIComponent(c.name || c.course_code || "Course")}">
        <span class="course-dot"></span>
        <div class="course-info">
          <div class="course-full-name">${esc(c.name || "Unnamed Course")}</div>
          <div class="course-meta">
            <span class="course-code">${esc(c.course_code || "")}</span>
            ${teacher ? `<span class="course-teacher" data-prof="${esc(teacher)}"> • ${esc(teacher)}</span>` : ""}
          </div>
        </div>
        <span class="course-arrow">›</span>
      </li>`;
  }).join("");

  // Fetch ratings for each teacher
  $coursesList.querySelectorAll(".course-teacher").forEach(span => {
    const profName = span.dataset.prof;
    getRmpRating(profName).then(rmp => {
      if (rmp?.ok && rmp.rating != null) {
        span.innerHTML += ` <span class="rating-badge">${rmp.rating.toFixed(1)}</span>`;
      }
    }).catch(() => {});
  });

  $coursesList.querySelectorAll(".course-card").forEach(card => {
    card.addEventListener("click", () => {
      const id   = card.dataset.id;
      const name = decodeURIComponent(card.dataset.name);
      openCourseDetail(id, name);
    });
  });
}

function renderStars(rating) {
  const full  = Math.floor(rating);
  const half  = rating - full >= 0.5 ? 1 : 0;
  const empty = 5 - full - half;
  return '★'.repeat(full) + (half ? '½' : '') + '☆'.repeat(empty);
}

function switchDetailTab(tabName) {
  $detailTabs.forEach(t => t.classList.toggle("active", t.dataset.detailView === tabName));
  $detailAssignments.classList.toggle("hidden", tabName !== "assignments");
  $detailAnnouncements.classList.toggle("hidden", tabName !== "announcements");
  $detailModules.classList.toggle("hidden", tabName !== "modules");
}

$detailTabs.forEach(tab => {
  tab.addEventListener("click", () => switchDetailTab(tab.dataset.detailView));
});

// ── Render: Course Detail ─────────────────────────────────────────────────────

async function openCourseDetail(courseId, courseName) {
  $viewCourses.classList.remove("active");
  $viewCourses.classList.add("hidden");
  $viewDetail.classList.remove("hidden");
  $viewDetail.classList.add("active");

  $detailName.textContent = courseName;
  $detailList.innerHTML = "";
  $announcementsList.innerHTML = "";
  $modulesList.innerHTML = "";
  
  $detailLoading.classList.remove("hidden");
  $detailEmpty.classList.add("hidden");
  $announcementsEmpty.classList.add("hidden");
  $modulesEmpty.classList.add("hidden");
  $professorSection.classList.add("hidden");
  $professorSection.innerHTML = "";

  // Reset to assignments tab
  switchDetailTab("assignments");

  const course = allCourses.find(c => String(c.id) === String(courseId));
  const teacherName = course?.teachers?.[0]?.display_name || null;

  if (teacherName) {
    $professorSection.classList.remove("hidden");
    $professorSection.innerHTML = `<div class="professor-section"><span class="prof-name">${esc(teacherName)}</span><span class="prof-rating">Loading rating…</span></div>`;
    getRmpRating(teacherName).then(rmp => {
      if (!rmp?.ok) return;
      const { rating, difficulty, numRatings } = rmp;
      if (rating == null) {
        $professorSection.innerHTML = `<div class="professor-section"><span class="prof-name">${esc(teacherName)}</span><span class="prof-rating">No RMP rating found</span></div>`;
        return;
      }
      const stars = renderStars(rating);
      $professorSection.innerHTML = `
        <div class="professor-section">
          <span class="prof-name">${esc(teacherName)}</span>
          <span class="prof-stars">${stars}</span>
          <span class="prof-rating">${rating.toFixed(1)} / 5.0 · Difficulty ${difficulty?.toFixed(1) ?? '—'} · ${numRatings} rating${numRatings !== 1 ? 's' : ''}</span>
        </div>`;
    }).catch(() => {
      $professorSection.innerHTML = `<div class="professor-section"><span class="prof-name">${esc(teacherName)}</span><span class="prof-rating">Rating unavailable</span></div>`;
    });
  }

  try {
    const [assignmentsRes, announcementsRes, modulesRes] = await Promise.all([
      getCourseAssignments(courseId),
      getCourseAnnouncements(courseId),
      getCourseModules(courseId)
    ]);

    $detailLoading.classList.add("hidden");

    // Render Assignments
    if (assignmentsRes.ok) {
      const assignments = (assignmentsRes.data || []).filter(a => {
        if (!a.due_at) return false;
        return new Date(a.due_at) > new Date();
      }).sort((a, b) => new Date(a.due_at) - new Date(b.due_at));

      if (!assignments.length) {
        $detailEmpty.classList.remove("hidden");
      } else {
        $detailList.innerHTML = assignments.map(a => {
          const cls = urgencyClass(a.due_at);
          return `
            <li class="assignment-item ${cls}" data-id="${a.id}">
              <div class="assignment-main">
                <div class="assignment-name">${esc(a.name || "Assignment")}</div>
                <div class="due-date ${cls}">${formatDue(a.due_at)}</div>
              </div>
              <div class="assignment-actions">
                <button class="open-btn" data-url="${esc(a.html_url || "")}" title="Open in Canvas" aria-label="Open in Canvas">→</button>
              </div>
            </li>`;
        }).join("");
      }
    }

    // Render Announcements
    if (announcementsRes.ok) {
      const announcements = announcementsRes.data || [];
      if (!announcements.length) {
        $announcementsEmpty.classList.remove("hidden");
      } else {
        $announcementsList.innerHTML = announcements.map(a => `
          <li class="assignment-item">
            <div class="assignment-main">
              <div class="assignment-name">${esc(a.title || "Announcement")}</div>
              <div class="due-date">${new Date(a.posted_at || a.created_at).toLocaleDateString()}</div>
            </div>
            <div class="assignment-actions">
              <button class="open-btn" data-url="${esc(a.html_url || "")}" title="Open in Canvas" aria-label="Open in Canvas">→</button>
            </div>
          </li>`).join("");
      }
    }

    // Render Modules
    if (modulesRes.ok) {
      const modules = modulesRes.data || [];
      if (!modules.length) {
        $modulesEmpty.classList.remove("hidden");
      } else {
        $modulesList.innerHTML = modules.map(m => `
          <li class="assignment-item">
            <div class="assignment-main">
              <div class="assignment-name">${esc(m.name || "Module")}</div>
              <div class="due-date">${m.items_count || 0} items</div>
            </div>
          </li>`).join("");
      }
    }

    $viewDetail.querySelectorAll(".open-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const url = btn.dataset.url;
        if (url) window.open(url, "_blank");
      });
    });

  } catch (err) {
    $detailLoading.classList.add("hidden");
    const li = document.createElement("li");
    li.className = "state-msg error";
    li.textContent = err.message;
    $detailList.appendChild(li);
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
  $viewGrades.classList.toggle("active",    tabName === "grades");
  $viewGrades.classList.toggle("hidden",    tabName !== "grades");
  $viewAgent.classList.toggle("active",     tabName === "agent");
  $viewAgent.classList.toggle("hidden",     tabName !== "agent");
  $viewDetail.classList.add("hidden");
  $viewDetail.classList.remove("active");

  if (tabName === "courses" && $coursesList.innerHTML === "") {
    loadCourses();
  }

  if (tabName === "grades" && !gradesLoaded) {
    gradesLoaded = true;
    loadGrades();
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
  $noTokenState.classList.add("hidden");
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

    const cutoff = Date.now() + prefs.daysAhead * 86400000;
    allAssignments = (res.data || [])
      .filter(e => e.type === "assignment")
      .filter(e => { const d = getDueDate(e); return !d || new Date(d) <= cutoff; });

    populateCourseFilter();
    renderUpcoming(allAssignments);

    if (res.cached) {
      $cacheBadge.classList.remove("hidden");
    } else {
      $cacheBadge.classList.add("hidden");
    }
  } catch (err) {
    $loading.classList.add("hidden");
    showErrorWithRetry($error, "Could not load assignments. Check your connection.", loadUpcoming);
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
    showErrorWithRetry($coursesError, "Could not load courses. Check your connection.", loadCourses);
  }
}

// ── Render: Grades ────────────────────────────────────────────────────────────

function gradeClass(score) {
  if (score == null) return "grade-none";
  if (score >= 90)   return "grade-a";
  if (score >= 80)   return "grade-b";
  if (score >= 70)   return "grade-c";
  if (score >= 60)   return "grade-d";
  return "grade-f";
}

function renderGrades(courses, gradesData) {
  $gradesLoading.classList.add("hidden");
  if (!courses.length) {
    $gradesError.innerHTML = `📊 No grade data available yet.`;
    $gradesError.classList.remove("hidden");
    return;
  }

  const hasAnyGrade = gradesData.some(g => (g?.data || []).length > 0);
  if (!hasAnyGrade) {
    $gradesError.innerHTML = `📊 No grade data available yet.`;
    $gradesError.classList.remove("hidden");
    return;
  }

  $gradesList.innerHTML = courses.map((course, index) => {
    const enrollments = gradesData[index]?.data || [];
    const enrollment  = enrollments[0] || null;
    const grades      = enrollment?.grades || {};
    const score       = grades.current_score != null ? grades.current_score : null;
    const letter      = grades.current_grade || null;
    const scoreLabel  = score != null ? `${score.toFixed(1)}%` : "—";
    const barWidth    = score != null ? Math.min(100, Math.max(0, score)) : 0;
    const cls         = gradeClass(score);
    const numGraded   = enrollment?.unread_count ?? null;

    return `
      <li class="grade-card ${cls}">
        <div class="grade-card-header">
          <span class="grade-course-name">${esc(course.name || "Unnamed Course")}</span>
          <div class="grade-scores">
            <span class="grade-score">${scoreLabel}</span>
            ${letter ? `<span class="grade-letter">${esc(letter)}</span>` : ""}
          </div>
        </div>
        ${numGraded != null ? `<div class="grade-meta">${numGraded} assignments graded</div>` : ""}
        <div class="grade-bar-track">
          <div class="grade-bar-fill" style="width:${barWidth}%"></div>
        </div>
      </li>`;
  }).join("");
}

async function loadGrades() {
  $gradesLoading.classList.remove("hidden");
  $gradesError.classList.add("hidden");
  $gradesList.innerHTML = "";

  try {
    // Ensure courses are loaded
    if (!allCourses.length) {
      const res = await getCourses();
      if (!res.ok) throw new Error(res.error || "Failed to fetch courses");
      allCourses = res.data || [];
    }

    const gradesData = await Promise.all(
      allCourses.map(c => getCourseGrades(c.id).catch(() => ({ ok: false, data: [] })))
    );

    renderGrades(allCourses, gradesData);
  } catch (err) {
    $gradesLoading.classList.add("hidden");
    showErrorWithRetry($gradesError, "Could not load grades. Check your connection.", () => {
      gradesLoaded = false;
      loadGrades();
    });
  }
}

// ── Settings Panel ────────────────────────────────────────────────────────────

function openSettings() {
  settingsOpen = true;

  const panel = document.createElement("div");
  panel.id = "settings-panel";
  panel.innerHTML = `
    <div class="settings-container">
      <div class="settings-header">
        <div>
          <h2>Settings</h2>
          <p class="header-sub" style="color:var(--text-muted);opacity:1">Canvas Tracker Preferences</p>
        </div>
        <button id="close-settings" aria-label="Close settings">✕</button>
      </div>
      <div class="settings-body">
        <div class="settings-group">
          <label for="token-input">Canvas API Token</label>
          <input type="password" id="token-input" placeholder="Paste your Canvas API token…" />
          <small>canvas.vt.edu → Account → Settings → New Access Token</small>
        </div>
        
        <button id="save-token" class="btn-primary" style="width:100%">Save Token</button>
        <div id="token-status"></div>

        <hr style="border:0;border-top:1px solid var(--border);margin:var(--space-lg) 0" />

        <div class="settings-group">
          <label>Appearance</label>
          <div class="settings-row">
            <span class="settings-row-label">Theme</span>
            <div class="theme-toggle">
              <button class="theme-opt ${prefs.theme === "light" ? "active" : ""}" data-theme="light">Light</button>
              <button class="theme-opt ${prefs.theme === "dark" ? "active" : ""}" data-theme="dark">Dark</button>
            </div>
          </div>
        </div>

        <div class="settings-group">
          <label for="days-ahead-input">Lookahead Window</label>
          <div style="display:flex;align-items:center;gap:var(--space-sm)">
            <input type="number" id="days-ahead-input" min="1" max="90" value="${prefs.daysAhead}" style="width:80px" />
            <span style="font-size:var(--size-sm)">days</span>
          </div>
          <small>Hide assignments due beyond this window.</small>
        </div>

        <button id="save-prefs" class="btn-secondary" style="width:100%;margin-top:var(--space-sm)">Save Preferences</button>
        <div id="prefs-status"></div>
      </div>
    </div>`;

  document.body.appendChild(panel);

  panel.addEventListener("click", (event) => {
    if (event.target === panel) closeSettings();
  });

  document.getElementById("close-settings").onclick = closeSettings;

  document.getElementById("save-token").onclick = async () => {
    const token = document.getElementById("token-input").value.trim();
    if (!token) return;
    const status = document.getElementById("token-status");
    status.textContent = "Saving…";
    const res = await setToken(token);
    status.textContent = res.ok ? "Token saved!" : `Error: ${res.error}`;
    if (res.ok) setTimeout(() => closeSettings(), 1000);
  };

  // Theme toggle
  panel.querySelectorAll(".theme-opt").forEach((btn) => {
    btn.addEventListener("click", () => {
      panel.querySelectorAll(".theme-opt").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });

  // Prefs save
  document.getElementById("save-prefs").onclick = async () => {
    const activeThemeBtn = panel.querySelector(".theme-opt.active");
    const newTheme = activeThemeBtn ? activeThemeBtn.dataset.theme : prefs.theme;
    const daysInput = document.getElementById("days-ahead-input");
    const newDays = Math.max(1, Math.min(90, parseInt(daysInput.value, 10) || 7));

    const status = document.getElementById("prefs-status");
    status.textContent = "Saving...";
    const res = await savePreferences({ theme: newTheme, daysAhead: newDays });
    if (res.ok) {
      prefs.theme = newTheme;
      prefs.daysAhead = newDays;
      applyTheme(newTheme);
      status.textContent = "Saved!";
      setTimeout(() => closeSettings(), 800);
    } else {
      status.textContent = `Error: ${res.error}`;
    }
  };
}

function closeSettings() {
  document.getElementById("settings-panel")?.remove();
  settingsOpen = false;
}

// ── Event Wiring ──────────────────────────────────────────────────────────────

$refreshBtn.addEventListener("click", async () => {
  $refreshBtn.disabled = true;
  try {
    await clearCache();
    if (activeTab === "upcoming") {
      await loadUpcoming();
    } else if (activeTab === "courses") {
      await loadCourses();
    } else if (activeTab === "grades") {
      gradesLoaded = false;
      await loadGrades();
      gradesLoaded = true;
    }
  } finally {
    $refreshBtn.disabled = false;
  }
});

$settingsBtn.addEventListener("click", () => {
  if (settingsOpen) closeSettings();
  else openSettings();
});

$courseFilter.addEventListener("change", () => renderUpcoming(allAssignments));

// ── Agent View ────────────────────────────────────────────────────────────────

function renderMarkdown(text) {
  return esc(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/_(.+?)_/g, '<em>$1</em>')
    .replace(/\n/g, '<br>');
}

function appendAgentMessage(role, content) {
  const $msgs = document.getElementById("agent-messages");
  const div = document.createElement("div");
  div.className = `agent-msg agent-msg--${role}`;
  const bubble = document.createElement("div");
  bubble.className = "agent-bubble";
  if (role === "user") {
    bubble.textContent = content;
  } else {
    bubble.innerHTML = renderMarkdown(content);
  }
  div.appendChild(bubble);
  $msgs.appendChild(div);
  $msgs.scrollTop = $msgs.scrollHeight;
  return bubble;
}

function showThinking() {
  const $msgs = document.getElementById("agent-messages");
  const div = document.createElement("div");
  div.id = "agent-thinking";
  div.className = "agent-msg agent-msg--agent";
  div.innerHTML = `<div class="agent-bubble agent-bubble--thinking">
    <div class="agent-thinking-dots">
      <span></span><span></span><span></span>
    </div>
    <span>Thinking…</span>
  </div>`;
  $msgs.appendChild(div);
  $msgs.scrollTop = $msgs.scrollHeight;
}

function hideThinking() {
  document.getElementById("agent-thinking")?.remove();
}

function showToolTrace(toolCalls) {
  const $trace = document.getElementById("agent-trace");
  if (!toolCalls?.length) { $trace.classList.add("hidden"); return; }
  $trace.classList.remove("hidden");
  $trace.innerHTML = `<div class="agent-trace-title">Tools used</div>` +
    toolCalls.map(tc => `
      <div class="agent-tool-item">
        <span class="agent-tool-icon">✓</span>
        <span class="agent-tool-name">${esc(tc.tool)}</span>
        <span class="agent-tool-label">— ${esc(tc.label || '')}</span>
      </div>`).join('');
}

async function sendAgentQuery(query) {
  if (!query.trim()) return;

  const $input = document.getElementById("agent-input");
  const $send  = document.getElementById("agent-send");
  const $msgs  = document.getElementById("agent-messages");
  const $trace = document.getElementById("agent-trace");

  // Stateless: wipe previous result so context never accumulates across queries
  $msgs.innerHTML = "";
  $trace.classList.add("hidden");
  $input.value = "";
  $input.disabled = true;
  $send.disabled = true;

  // Show query label above the result
  const $queryLabel = document.createElement("div");
  $queryLabel.className = "agent-query-label";
  $queryLabel.textContent = query;
  $msgs.appendChild($queryLabel);

  showThinking();

  try {
    const res = await agentQuery(query);
    hideThinking();
    if (res?.ok) {
      showToolTrace(res.toolCalls);
      appendAgentMessage("agent", res.answer || "No response.");
    } else {
      appendAgentMessage("agent", `Error: ${res?.error || "Unknown error"}`);
    }
  } catch (err) {
    hideThinking();
    appendAgentMessage("agent", `Failed to reach agent: ${err.message}`);
  } finally {
    $input.disabled = false;
    $send.disabled = false;
    $input.focus();
  }
}

document.getElementById("agent-send")?.addEventListener("click", () => {
  sendAgentQuery(document.getElementById("agent-input")?.value || "");
});

document.getElementById("agent-input")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendAgentQuery(e.target.value);
  }
});

document.querySelectorAll(".agent-tool-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    switchTab("agent");
    const $input = document.getElementById("agent-input");
    if ($input) $input.value = btn.dataset.query || "";
    sendAgentQuery(btn.dataset.query || "");
  });
});

// ── Init ──────────────────────────────────────────────���───────────────────────

async function initApp() {
  try {
    const p = await getPreferences();
    prefs = p;
    applyTheme(prefs.theme);
  } catch (_) {
    // use defaults
  }

  try {
    const tokenRes = await getToken();
    const hasToken = tokenRes?.ok && tokenRes?.data;
    if (!hasToken) {
      $loading.classList.add("hidden");
      $noTokenState.classList.remove("hidden");
      return;
    }
  } catch (_) {
    $loading.classList.add("hidden");
    $noTokenState.classList.remove("hidden");
    return;
  }

  loadUpcoming();
}

document.getElementById("open-settings-btn")?.addEventListener("click", () => {
  openSettings();
});

initApp();
