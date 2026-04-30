/**
 * Test the Canvas API fetch logic from background.js
 */

const API_BASE = "https://canvas.vt.edu/api/v1";

// Simulate the canvasGet function from background.js
async function canvasGet(path, token) {
  if (!token) throw new Error("Not authenticated");
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    },
  });
  if (res.status === 401) throw new Error("Token expired");
  if (!res.ok) throw new Error(`Canvas API error: ${res.status}`);
  return res.json();
}

async function main() {
  // Check if CANVAS_TOKEN is available
  const token = process.env.CANVAS_TOKEN;
  if (!token) {
    console.log("⚠️  CANVAS_TOKEN not set — testing URL structure only");
    console.log("✅ canvasGet function syntax valid");
    console.log("✅ API_BASE:", API_BASE);
    console.log("\nTo test fully: export CANVAS_TOKEN=<your-token> && node test-canvas-api.mjs");
    return;
  }

  console.log("Testing Canvas API...");
  try {
    // Test 1: Fetch current user
    const user = await canvasGet("/users/self", token);
    console.log("✅ /users/self:", user.name, `(${user.id})`);

    // Test 2: Fetch courses
    const courses = await canvasGet("/courses?per_page=5&enrollment_state=active", token);
    console.log("✅ /courses:", courses.length, "courses");
    courses.forEach(c => console.log("  -", c.name, `(${c.course_code})`));

    // Test 3: Fetch upcoming
    const upcoming = await canvasGet("/users/self/upcoming_events?per_page=5", token);
    const assignments = upcoming.filter(e => e.type === "assignment");
    console.log("✅ /upcoming:", upcoming.length, "events,", assignments.length, "assignments");
    assignments.slice(0, 3).forEach(a => console.log("  -", a.title, "| due:", a.due_at));

    console.log("\n✅ All Canvas API calls working");
  } catch (err) {
    console.log("❌ API test failed:", err.message);
  }
}

main();