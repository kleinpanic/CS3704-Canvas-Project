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

import { getUpcomingAssignments, getCourses, getDismissed, dismissAssignment } from '../lib/cache.js';

// ── DOM Refs ──────────────────────────────────────────────────────────────────

const $upcomingList = document.getElementById("upcoming-list");
const $loading = document.getElementById("loading");
const $error = document.getElementById("error");
const $userInfo = document.getElementById("user-info");
const $refreshBtn = document.getElementById("refresh-btn");
const $settingsBtn = document.getElementById("settings-btn");
const $courseFilter = document.getElementById("course-filter");
const $filterSection = document.getElementById("filter-section");

// ── State ─────────────────────────────────────────────────────────────────────

let allAssignments = [];
let dismissedIds = new Set();
let courses = [];

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDue(dateStr) {
  if (!dateStr) return "No due date";
  const d = new Date(dateStr);
  const now = new Date();
  const diff = d - now;
  const days = Math.floor(diff / 86400000);
  const hours = Math.floor(diff / 3600000);
  if (diff < 0) return "OVERDUE";
  if (hours < 1) return "Due < 1h";
  if (hours < 24) return `Due in ${hours}h`;
  if (days === 1) return "Due tomorrow";
  return `Due in ${days} days`;
}

function urgentClass(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const diff = d - new Date();
  if (diff < 0) return "overdue";
  if (diff < 86400000) return "urgent";
  if (diff < 172800000) return "due-soon";
  return "";
}

function renderAssignment(item) {
  if (item.type !== "assignment") return "";
  const id = String(item.assignment?.id || item.id);
  if (dismissedIds.has(id)) return "";

  const courseName = item.context_course_name || item.course_name || "Canvas";
  const dueDate = item.all_day ? item.start_at : item.due_at;
  const cls = urgentClass(dueDate);
  const dueText = formatDue(dueDate);

  return `
    <li class="assignment-item ${cls}" data-id="${id}">
      <div class="assignment-main">
        <div class="course-name">${courseName}</div>
        <div class="assignment-name">${item.title || item.assignment?.name || "Assignment"}</div>
        <div class="due-date ${cls}">${dueText}</div>
      </div>
      <div class="assignment-actions">
        <button class="dismiss-btn" data-id="${id}" title="Dismiss">✓</button>
        <button class="open-btn" data-url="${item.html_url || ''}" title="Open in Canvas">→</button>
      </div>
    </li>
  `;
}

function renderCourseFilter() {
  const uniqueCourses = [...new Set(allAssignments.map(a => a.context_course_name || a.course_name).filter(Boolean))].sort();
  $filterSection.classList.remove("hidden");
  $courseFilter.innerHTML = `<option value="">All Courses</option>` +
    uniqueCourses.map(c => `<option value="${c}">${c}</option>`).join("");
}

function applyFilter(assignments) {
  const course = $courseFilter.value;
  if (!course) return assignments;
  return assignments.filter(a => (a.context_course_name || a.course_name) === course);
}

function render(assignments) {
  $loading.classList.add("hidden");
  const filtered = applyFilter(assignments);

  if (filtered.length === 0) {
    $upcomingList.innerHTML = `<li class="assignment-item">No upcoming assignments</li>`;
    return;
  }

  $upcomingList.innerHTML = filtered.map(renderAssignment).join("");

  // Attach dismiss handlers
  $upcomingList.querySelectorAll(".dismiss-btn").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const id = btn.dataset.id;
      await dismissAssignment(id);
      dismissedIds.add(id);
      btn.closest(".assignment-item").remove();
      // Refresh badge
      chrome.runtime.sendMessage({ type: "REFRESH_BADGE" });
    });
  });

  // Attach open handlers
  $upcomingList.querySelectorAll(".open-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const url = btn.dataset.url;
      if (url) window.open(url, "_blank");
    });
  });
}

// ── Data Fetch ─────────────────────────────────────────────────────────────────

async function fetchAll() {
  $loading.classList.remove("hidden");
  $error.classList.add("hidden");
  $upcomingList.innerHTML = "";

  try {
    // Load dismissed from IndexedDB
    dismissedIds = await getDismissed();

    // Load courses first (for badge)
    const coursesRes = await chrome.runtime.sendMessage({ type: "GET_COURSES" });
    if (coursesRes.ok && coursesRes.data?.length) {
      courses = coursesRes.data;
      $userInfo.textContent = `${courses.length} courses`;
    }

    // Load upcoming with stale-while-revalidate
    const res = await chrome.runtime.sendMessage({ type: "GET_UPCOMING" });
    if (!res.ok) throw new Error(res.error || "Failed to fetch");

    allAssignments = res.data.filter(e => e.type === "assignment");
    renderCourseFilter();
    render(allAssignments);

    // Show cache indicator
    if (res.cached) {
      const badge = document.createElement("span");
      badge.className = "cache-badge";
      badge.textContent = "cached";
      document.querySelector("header").appendChild(badge);
    }
  } catch (err) {
    $loading.classList.add("hidden");
    $error.textContent = err.message;
    $error.classList.remove("hidden");
  }
}

// ── Settings Panel ────────────────────────────────────────────────────────────

let settingsOpen = false;

function openSettings() {
  const panel = document.createElement("div");
  panel.id = "settings-panel";
  panel.innerHTML = `
    <div class="settings-header">
      <h2>Settings</h2>
      <button id="close-settings">✕</button>
    </div>
    <div class="settings-body">
      <label>
        Canvas API Token
        <input type="password" id="token-input" placeholder="Paste your Canvas API token..." />
        <small>Get your token from canvas.vt.edu → Account → Settings → New Access Token</small>
      </label>
      <button id="save-token" class="primary-btn">Save Token</button>
      <div id="token-status"></div>
    </div>
  `;
  document.body.appendChild(panel);

  document.getElementById("close-settings").onclick = closeSettings;
  document.getElementById("save-token").onclick = async () => {
    const token = document.getElementById("token-input").value.trim();
    if (!token) return;
    const status = document.getElementById("token-status");
    status.textContent = "Saving...";
    const res = await chrome.runtime.sendMessage({ type: "SET_TOKEN", token });
    status.textContent = res.ok ? "✅ Token saved!" : `❌ ${res.error}`;
    if (res.ok) setTimeout(closeSettings, 1000);
  };
}

function closeSettings() {
  document.getElementById("settings-panel")?.remove();
  settingsOpen = false;
}

// ── Init ──────────────────────────────────────────────────────────────────────

$refreshBtn.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "CLEAR_CACHE" }, () => fetchAll());
});
$settingsBtn.addEventListener("click", () => {
  if (settingsOpen) closeSettings();
  else openSettings();
});
$courseFilter.addEventListener("change", () => render(allAssignments));

fetchAll();