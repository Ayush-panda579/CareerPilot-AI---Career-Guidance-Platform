import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const dashboard = document.querySelector("#realtime-dashboard");
const statusLabel = document.querySelector("#live-status");

if (dashboard && statusLabel) {
  const setStatus = (message, isLive = false) => {
    statusLabel.textContent = message;
    const dot = document.querySelector("#live-dot");
    if (dot) dot.style.backgroundColor = isLive ? "#57d7ae" : "#e7b85c";
  };

  const makeIcon = (className) => {
    const icon = document.createElement("i");
    icon.className = className;
    icon.setAttribute("aria-hidden", "true");
    return icon;
  };

  const renderProgress = (items) => {
    const list = document.querySelector("#goal-list");
    const empty = document.querySelector("#goal-empty-state");
    if (!list) return;
    list.replaceChildren();

    for (const item of items) {
      const row = document.createElement("li");
      row.className = `goal-item${item.completed ? " is-complete" : ""}`;

      const content = document.createElement("div");
      content.className = "d-flex align-items-center gap-3 min-w-0";
      const toggleForm = document.createElement("form");
      toggleForm.method = "post";
      toggleForm.action = `/dashboard/progress/${encodeURIComponent(item.id)}/toggle`;
      const completedValue = document.createElement("input");
      completedValue.type = "hidden";
      completedValue.name = "completed";
      completedValue.value = item.completed ? "false" : "true";
      const toggle = document.createElement("button");
      toggle.type = "submit";
      toggle.className = "icon-button";
      toggle.setAttribute("aria-label", `${item.completed ? "Mark incomplete" : "Mark complete"}: ${item.goal}`);
      toggle.append(makeIcon(`bi ${item.completed ? "bi-check-circle-fill text-success" : "bi-circle"}`));
      toggleForm.append(completedValue, toggle);

      const text = document.createElement("span");
      text.className = "goal-text";
      text.textContent = item.goal;
      content.append(toggleForm, text);

      const deleteForm = document.createElement("form");
      deleteForm.method = "post";
      deleteForm.action = `/dashboard/progress/${encodeURIComponent(item.id)}/delete`;
      const remove = document.createElement("button");
      remove.type = "submit";
      remove.className = "icon-button";
      remove.setAttribute("aria-label", `Remove goal: ${item.goal}`);
      remove.append(makeIcon("bi bi-trash3"));
      deleteForm.append(remove);
      row.append(content, deleteForm);
      list.append(row);
    }

    if (empty) empty.hidden = items.length > 0;
    list.hidden = items.length === 0;
  };

  const renderResumes = (items) => {
    const list = document.querySelector("#resume-list");
    const empty = document.querySelector("#resume-empty-state");
    if (!list) return;
    list.replaceChildren();

    for (const item of items) {
      const row = document.createElement("li");
      row.className = "resume-item";
      const file = document.createElement("div");
      file.className = "d-flex align-items-center gap-3 min-w-0";
      file.append(makeIcon("bi bi-file-earmark-pdf fs-4 text-primary"));
      const details = document.createElement("div");
      details.className = "min-w-0";
      const name = document.createElement("div");
      name.className = "text-truncate fw-semibold";
      name.textContent = item.original_filename;
      const date = document.createElement("div");
      date.className = "small text-secondary";
      date.textContent = String(item.created_at || "").slice(0, 10);
      details.append(name, date);
      file.append(details);

      const status = document.createElement("span");
      status.className = `resume-status ${item.status}`;
      status.textContent = item.status.charAt(0).toUpperCase() + item.status.slice(1);
      row.append(file, status);
      list.append(row);
    }

    if (empty) empty.hidden = items.length > 0;
    list.hidden = items.length === 0;
  };

  const refreshDashboard = async () => {
    try {
      const response = await fetch(dashboard.dataset.dashboardUrl, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) throw new Error("Dashboard refresh unavailable");
      const { progress = [], resumes = [] } = await response.json();
      const completed = progress.filter((item) => item.completed).length;
      document.querySelector("#completed-count").textContent = completed;
      document.querySelector("#progress-count").textContent = progress.length;
      document.querySelector("#goal-badge-count").textContent = progress.length;
      document.querySelector("#open-goal-count").textContent = progress.length - completed;
      document.querySelector("#resume-count").textContent = resumes.length;
      renderProgress(progress);
      renderResumes(resumes);
    } catch {
      setStatus("Connected · refresh failed", true);
    }
  };

  try {
    const response = await fetch(dashboard.dataset.sessionUrl, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) throw new Error("Session unavailable");

    const {
      access_token: accessToken,
      user_id: userId,
      supabase_url: url,
      publishable_key: key,
    } = await response.json();
    const supabase = createClient(url, key, {
      auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
    });
    await supabase.realtime.setAuth(accessToken);

    const channel = supabase
      .channel(`careerpilot-dashboard-${userId}`)
      .on("postgres_changes", {
        event: "*",
        schema: "public",
        table: "learning_progress",
        filter: `owner_id=eq.${userId}`,
      }, refreshDashboard)
      .on("postgres_changes", {
        event: "*",
        schema: "public",
        table: "resume_uploads",
        filter: `owner_id=eq.${userId}`,
      }, refreshDashboard)
      .subscribe((state) => {
        if (state === "SUBSCRIBED") setStatus("Live updates connected", true);
        if (state === "CHANNEL_ERROR" || state === "TIMED_OUT") {
          setStatus("Live updates unavailable");
        }
      });

    window.addEventListener("pagehide", () => {
      supabase.removeChannel(channel);
    }, { once: true });
  } catch {
    setStatus("Live updates unavailable");
  }
}
