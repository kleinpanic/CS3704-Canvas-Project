/**
 * Canvas Deadline Tracker — Popup App
 *
 * Features:
 * - Course filter (dropdown to filter by course)
 * - Stale-while-revalidate (instant load from cache, background refresh)
 * - Dismiss/snooze assignments
 * - Quick open in Canvas
 * - Settings panel for token management
 */

import { getDismissed, dismissAssignment } from '../lib/cache.js';
import {
  getCourses,
  getUpcomingAssignments,
  setToken,
  clearCache,
  refreshBadge,
} from '../lib/extension-api.js';

// ── DOM Refs ──────────────────────────────────────────────────────────────────

const $upcomingList = document.getElementById("upcoming-list");
const $loading = document.getElementById("loading");
const $error = document.getElementById("error");
const $userInfo = document.getElementById("user-info");
const $refreshBtn = document.getElementById("refresh-btn");
const $settingsBtn = document.getElementById("settings-btn");
const $courseFilter = document.getElementById("course-filter");
const $filterSection = document.getElementById("filter-section");
const $cacheBadge = document.getElementById("cache-badge");
const $assignmentCount = document.getElementById("assignment-count");

// ── State ─────────────────────────────────────────────────────────────────────

let allAssignments = [];
let dismissedIds = new Set();
let courses = [];
let settingsOpen = false;

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
  const now = new Date();
  const diff = dueDate - now;
  const days = Math.floor(diff / 86400000);
  const hours = Math.floor(diff / 3600000);

  if (diff < 0) return "Overdue";
  if (hours < 1) return "Due in under 1 hour";
  if (hours < 24) return `Due in ${hours}h`;
  if (days === 1) return "Due tomorrow";
  return `Due in ${days} days`;
}

function urgentClass(dateStr) {
  if (!dateStr) return "";
  const dueDate = new Date(dateStr);
  const diff = dueDate - new Date();

  if (diff < 0) return "overdue";
  if (diff < 86400000) return "urgent";
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
  if (!count) {
    $assignmentCount.classList.add("hidden");
    return;
  }

  $assignmentCount.textContent = `${count} item${count === 1 ? "" : "s"}`;
  $assignmentCount.classList.remove("hidden");
}

function renderEmptyState(message = "No upcoming assignments", detail = "You're caught up for now.") {
  updateAssignmentCount(0);
  $upcomingList.innerHTML = `
    <li class="status-card empty-state">
      <strong>${escapeHtml(message)}</strong>
      <span>${escapeHtml(detail)}</span>
    </li>
  `;
}

function renderAssignment(item) {
  if (item.type !== "assignment") return "";

  const id = String(item.assignment?.id || item.id);
  if (dismissedIds.has(id)) return "";

  const courseName = getCourseName(item);
  const dueDate = getDueDate(item);
  const cls = urgentClass(dueDate);
  const dueText = formatDue(dueDate);
  const title = item.title || item.assignment?.name || "Assignment";
  const url = item.html_url || "";

  return `
    <li class="assignment-item ${cls}" data-id="${escapeHtml(id)}">
      <div class="assignment-main">
        <div class="course-name" title="${escapeHtml(courseName)}">${escapeHtml(courseName)}</div>
        <div class="assignment-name">${escapeHtml(title)}</div>
        <div class="due-date ${cls}">${escapeHtml(dueText)}</div>
      </div>
      <div class="assignment-actions">
        <button class="open-btn" data-url="${escapeHtml(url)}" title="Open in Canvas" aria-label="Open in Canvas">↗</button>
        <button class="dismiss-btn" data-id="${escapeHtml(id)}" title="Dismiss" aria-label="Dismiss assignment">✓</button>
      </div>
    </li>
  `;
}

function renderCourseFilter() {
  const uniqueCourses = [...new Set(allAssignments.map(getCourseName).filter(Boolean))].sort();

  if (uniqueCourses.length <= 1) {
    $filterSection.classList.add("hidden");
    return;
  }

  $filterSection.classList.remove("hidden");
  $courseFilter.innerHTML = '<option value="">All Courses</option>' +
    uniqueCourses.map((courseName) => `<option value="${escapeHtml(courseName)}">${escapeHtml(courseName)}</option>`).join("");
}

function applyFilter(assignments) {
  const selectedCourse = $courseFilter.value;
  if (!selectedCourse) return assignments;
  return assignments.filter((assignment) => getCourseName(assignment) === selectedCourse);
}

function attachHandlers() {
  $upcomingList.querySelectorAll(".dismiss-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      const { id } = btn.dataset;
      await dismissAssignment(id);
      dismissedIds.add(id);
      render(allAssignments);
      refreshBadge();
    });
  });

  $upcomingList.querySelectorAll(".open-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const { url } = btn.dataset;
      if (url) window.open(url, "_blank");
    });
  });
}

function render(assignments) {
  $loading.classList.add("hidden");
  $error.classList.add("hidden");

  const filtered = applyFilter(assignments).filter((item) => !dismissedIds.has(String(item.assignment?.id || item.id)));
  updateAssignmentCount(filtered.length);

  if (filtered.length === 0) {
    const detail = $courseFilter.value
      ? `Nothing upcoming for ${$courseFilter.value}.`
      : "You're caught up for now.";
    renderEmptyState("No upcoming assignments", detail);
    return;
  }

  $upcomingList.innerHTML = filtered.map(renderAssignment).join("");
  attachHandlers();
}

// ── Data Fetch ─────────────────────────────────────────────────────────────────

async function fetchAll() {
  $loading.classList.remove("hidden");
  $error.classList.add("hidden");
  $upcomingList.innerHTML = "";
  $cacheBadge.classList.add("hidden");
  updateAssignmentCount(0);

  try {
    dismissedIds = await getDismissed();

    const coursesRes = await getCourses();
    if (coursesRes.ok && coursesRes.data?.length) {
      courses = coursesRes.data;
      $userInfo.textContent = `${courses.length} course${courses.length === 1 ? "" : "s"}`;
    } else {
      $userInfo.textContent = "Canvas";
    }

    const res = await getUpcomingAssignments();
    if (!res.ok) throw new Error(res.error || "Failed to fetch assignments");

    allAssignments = res.data.filter((entry) => entry.type === "assignment");
    renderCourseFilter();
    render(allAssignments);

    if (res.cached) {
      $cacheBadge.classList.remove("hidden");
    }
  } catch (err) {
    $loading.classList.add("hidden");
    $error.textContent = err.message;
    $error.classList.remove("hidden");
    renderEmptyState("Could not load assignments", "Open Settings to check your token, then refresh.");
  }
}

// ── Settings Panel ────────────────────────────────────────────────────────────

function openSettings() {
  settingsOpen = true;

  const panel = document.createElement("div");
  panel.id = "settings-panel";
  panel.innerHTML = `
    <div class="settings-modal">
      <div class="settings-header">
        <div>
          <h2>Settings</h2>
          <p>Connect the extension to Canvas and refresh when you're ready.</p>
        </div>
        <button id="close-settings" aria-label="Close settings">✕</button>
      </div>
      <div class="settings-body">
        <label for="token-input">Canvas API Token</label>
        <input type="password" id="token-input" placeholder="Paste your Canvas API token..." />
        <small>Get your token from canvas.vt.edu → Account → Settings → New Access Token</small>
        <button id="save-token" class="primary-btn">Save Token</button>
        <div id="token-status"></div>
      </div>
    </div>
  `;

  document.body.appendChild(panel);

  panel.addEventListener("click", (event) => {
    if (event.target === panel) closeSettings();
  });

  document.getElementById("close-settings").onclick = closeSettings;
  document.getElementById("save-token").onclick = async () => {
    const token = document.getElementById("token-input").value.trim();
    const status = document.getElementById("token-status");

    if (!token) {
      status.textContent = "Enter a token first.";
      return;
    }

    status.textContent = "Saving and validating...";
    const res = await setToken(token);
    status.textContent = res.ok
      ? `Connected as ${res.user?.name || res.user?.short_name || 'Canvas user'}.`
      : `Error: ${res.error}`;
    if (res.ok) {
      setTimeout(() => {
        closeSettings();
        fetchAll();
      }, 900);
    }
  };
}

function closeSettings() {
  document.getElementById("settings-panel")?.remove();
  settingsOpen = false;
}

// ── Init ──────────────────────────────────────────────────────────────────────

$refreshBtn.addEventListener("click", async () => {
  await clearCache();
  fetchAll();
});

$settingsBtn.addEventListener("click", () => {
  if (settingsOpen) closeSettings();
  else openSettings();
});

$courseFilter.addEventListener("change", () => render(allAssignments));

fetchAll();
