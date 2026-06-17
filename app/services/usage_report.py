from datetime import UTC, datetime
from html import escape
from typing import Any

from app.errors import ClientRequestError
from app.repositories.limits import LimitRepository
from app.repositories.usage import UsageRepository
from app.repositories.users import User, UserRepository


class UsageReportService:
    def __init__(
        self,
        usage_repository: UsageRepository,
        limit_repository: LimitRepository,
        user_repository: UserRepository,
        *,
        recent_event_limit: int = 25,
    ) -> None:
        self._usage_repository = usage_repository
        self._limit_repository = limit_repository
        self._user_repository = user_repository
        self._recent_event_limit = recent_event_limit

    def render_user_usage_report(self, user_id: str, *, admin_view: bool = False) -> str:
        return self._render_html(self._build_user_report_data(user_id, admin_view=admin_view))

    def render_admin_user_usage_report(self, admin_user_id: str, target_user_id: str) -> str:
        if not self._user_repository.admin_can_access_user(admin_user_id, target_user_id):
            raise ClientRequestError(
                "Admin is not associated with that user",
                status_code=403,
                error_type="permission_denied",
            )

        return self.render_user_usage_report(target_user_id, admin_view=True)

    def render_admin_usage_report(self, admin_user_id: str) -> str:
        users = self._user_repository.list_users_for_admin(admin_user_id)
        user_reports = [self._build_user_report_data(user.id, user=user) for user in users]
        aggregate = {
            "user_count": len(user_reports),
            "request_count": sum(report["aggregate"]["request_count"] for report in user_reports),
            "prompt_tokens": sum(report["aggregate"]["prompt_tokens"] for report in user_reports),
            "completion_tokens": sum(
                report["aggregate"]["completion_tokens"] for report in user_reports
            ),
            "total_tokens": sum(report["aggregate"]["total_tokens"] for report in user_reports),
        }
        events = self._usage_repository.list_recent_usage_events_for_users(
            [user.id for user in users],
            self._recent_event_limit,
        )
        view_data = {
            "admin_user_id": admin_user_id,
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "aggregate": aggregate,
            "users": user_reports,
            "events": events,
        }
        return self._render_admin_html(view_data)

    def _build_user_report_data(
        self,
        user_id: str,
        *,
        user: User | None = None,
        admin_view: bool = False,
    ) -> dict[str, Any]:
        summary = self._usage_repository.get_usage_summary(user_id)
        limits = self._limit_repository.get_user_limits(user_id)
        events = self._usage_repository.list_recent_usage_events(user_id, self._recent_event_limit)

        return {
            "user_id": user_id,
            "display_name": user.display_name if user is not None else user_id,
            "role": user.role if user is not None else "user",
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "aggregate": summary["aggregate"],
            "limits": {
                "requests_per_minute": limits.requests_per_minute,
                "daily_tokens": limits.daily_tokens,
                "total_tokens": limits.total_tokens,
            },
            "models": summary["models"],
            "events": events,
            "admin_view": admin_view,
        }

    def _render_html(self, report: dict[str, Any]) -> str:
        user_id = escape(str(report["user_id"]))
        generated_at = escape(str(report["generated_at"]))
        title_prefix = "Admin Usage Report" if report["admin_view"] else "Usage Report"
        title = f"{title_prefix}: {user_id}"
        admin_badge = '<span class="view-badge">Admin view</span>' if report["admin_view"] else ""

        aggregate = report["aggregate"]
        limits = report["limits"]
        models = report["models"]
        events = report["events"]

        model_rows = "".join(self._render_model_row(model) for model in models)
        if not model_rows:
            model_rows = '<tr><td colspan="5" class="empty">No model usage yet</td></tr>'

        event_rows = "".join(self._render_event_row(event) for event in events)
        if not event_rows:
            event_rows = '<tr><td colspan="7" class="empty">No recent events yet</td></tr>'

        request_limit_metric = self._render_metric(
            "Requests per minute",
            self._limit_value(limits["requests_per_minute"]),
        )
        daily_limit_metric = self._render_metric(
            "Daily tokens",
            self._limit_value(limits["daily_tokens"]),
        )
        total_limit_metric = self._render_metric(
            "Total tokens",
            self._limit_value(limits["total_tokens"]),
        )

        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #ffffff;
      --text: #202124;
      --muted: #5f6368;
      --line: #dadce0;
      --soft: #f8fafd;
      --success: #137333;
      --failed: #b3261e;
      --reserved: #8f5a00;
      --other: #3c4043;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      margin-bottom: 24px;
      padding-bottom: 16px;
    }}
    h1 {{
      font-size: 28px;
      line-height: 1.2;
      margin: 0 0 8px;
    }}
    h2 {{
      font-size: 18px;
      margin: 28px 0 12px;
    }}
    .meta {{
      color: var(--muted);
      margin: 0;
    }}
    .view-badge {{
      border: 1px solid var(--line);
      border-radius: 4px;
      color: var(--muted);
      display: inline-block;
      font-size: 12px;
      margin-left: 8px;
      padding: 2px 6px;
      vertical-align: middle;
    }}
    .summary {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      margin: 16px 0 24px;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
    }}
    .metric .label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }}
    .metric .value {{
      font-size: 24px;
      font-weight: 650;
      margin-top: 4px;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    table {{
      border-collapse: collapse;
      min-width: 720px;
      width: 100%;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      text-align: left;
      white-space: nowrap;
    }}
    th {{
      background: var(--soft);
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
      text-transform: uppercase;
    }}
    .status {{
      border-radius: 4px;
      display: inline-block;
      font-size: 12px;
      font-weight: 650;
      padding: 2px 6px;
    }}
    .status-success {{
      background: #e6f4ea;
      color: var(--success);
    }}
    .status-failed {{
      background: #fce8e6;
      color: var(--failed);
    }}
    .status-reserved {{
      background: #fef7e0;
      color: var(--reserved);
    }}
    .status-other {{
      background: #f1f3f4;
      color: var(--other);
    }}
    .empty {{
      color: var(--muted);
      text-align: center;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{escape(title_prefix)} for {user_id}{admin_badge}</h1>
      <p class="meta">Generated {generated_at}</p>
    </header>

    <section aria-labelledby="summary-heading">
      <h2 id="summary-heading">Summary</h2>
      <div class="summary">
        {self._render_metric("Requests", aggregate["request_count"])}
        {self._render_metric("Prompt tokens", aggregate["prompt_tokens"])}
        {self._render_metric("Completion tokens", aggregate["completion_tokens"])}
        {self._render_metric("Total tokens", aggregate["total_tokens"])}
      </div>
    </section>

    <section aria-labelledby="limits-heading">
      <h2 id="limits-heading">Configured Limits</h2>
      <div class="summary">
        {request_limit_metric}
        {daily_limit_metric}
        {total_limit_metric}
      </div>
    </section>

    <section aria-labelledby="models-heading">
      <h2 id="models-heading">Per-Model Usage</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>Requests</th>
              <th>Prompt tokens</th>
              <th>Completion tokens</th>
              <th>Total tokens</th>
            </tr>
          </thead>
          <tbody>{model_rows}</tbody>
        </table>
      </div>
    </section>

    <section aria-labelledby="events-heading">
      <h2 id="events-heading">Recent Events</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Model</th>
              <th>Status</th>
              <th>Prompt tokens</th>
              <th>Completion tokens</th>
              <th>Total tokens</th>
              <th>Latency ms</th>
            </tr>
          </thead>
          <tbody>{event_rows}</tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""

    def _render_admin_html(self, report: dict[str, Any]) -> str:
        admin_user_id = escape(str(report["admin_user_id"]))
        generated_at = escape(str(report["generated_at"]))
        aggregate = report["aggregate"]
        users = report["users"]
        events = report["events"]

        user_rows = "".join(self._render_admin_user_row(user_report) for user_report in users)
        if not user_rows:
            user_rows = '<tr><td colspan="10" class="empty">No associated users yet</td></tr>'

        event_rows = "".join(self._render_admin_event_row(event) for event in events)
        if not event_rows:
            event_rows = '<tr><td colspan="8" class="empty">No recent events yet</td></tr>'

        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Admin Usage Report: {admin_user_id}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #ffffff;
      --text: #202124;
      --muted: #5f6368;
      --line: #dadce0;
      --soft: #f8fafd;
      --success: #137333;
      --failed: #b3261e;
      --reserved: #8f5a00;
      --other: #3c4043;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      margin-bottom: 24px;
      padding-bottom: 16px;
    }}
    h1 {{
      font-size: 28px;
      line-height: 1.2;
      margin: 0 0 8px;
    }}
    h2 {{
      font-size: 18px;
      margin: 28px 0 12px;
    }}
    .meta {{
      color: var(--muted);
      margin: 0;
    }}
    .view-badge {{
      border: 1px solid var(--line);
      border-radius: 4px;
      color: var(--muted);
      display: inline-block;
      font-size: 12px;
      margin-left: 8px;
      padding: 2px 6px;
      vertical-align: middle;
    }}
    .summary {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      margin: 16px 0 24px;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
    }}
    .metric .label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }}
    .metric .value {{
      font-size: 24px;
      font-weight: 650;
      margin-top: 4px;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    table {{
      border-collapse: collapse;
      min-width: 900px;
      width: 100%;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      text-align: left;
      white-space: nowrap;
    }}
    th {{
      background: var(--soft);
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
      text-transform: uppercase;
    }}
    .status {{
      border-radius: 4px;
      display: inline-block;
      font-size: 12px;
      font-weight: 650;
      padding: 2px 6px;
    }}
    .status-success {{
      background: #e6f4ea;
      color: var(--success);
    }}
    .status-failed {{
      background: #fce8e6;
      color: var(--failed);
    }}
    .status-reserved {{
      background: #fef7e0;
      color: var(--reserved);
    }}
    .status-other {{
      background: #f1f3f4;
      color: var(--other);
    }}
    .empty {{
      color: var(--muted);
      text-align: center;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Admin Usage Report for {admin_user_id}<span class="view-badge">Admin view</span></h1>
      <p class="meta">Generated {generated_at}</p>
    </header>

    <section aria-labelledby="summary-heading">
      <h2 id="summary-heading">Summary</h2>
      <div class="summary">
        {self._render_metric("Associated users", aggregate["user_count"])}
        {self._render_metric("Requests", aggregate["request_count"])}
        {self._render_metric("Prompt tokens", aggregate["prompt_tokens"])}
        {self._render_metric("Completion tokens", aggregate["completion_tokens"])}
        {self._render_metric("Total tokens", aggregate["total_tokens"])}
      </div>
    </section>

    <section aria-labelledby="users-heading">
      <h2 id="users-heading">Associated Users</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>User ID</th>
              <th>Display name</th>
              <th>Role</th>
              <th>Requests</th>
              <th>Prompt tokens</th>
              <th>Completion tokens</th>
              <th>Total tokens</th>
              <th>RPM limit</th>
              <th>Daily limit</th>
              <th>Total limit</th>
            </tr>
          </thead>
          <tbody>{user_rows}</tbody>
        </table>
      </div>
    </section>

    <section aria-labelledby="events-heading">
      <h2 id="events-heading">Recent Associated User Events</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>User ID</th>
              <th>Model</th>
              <th>Status</th>
              <th>Prompt tokens</th>
              <th>Completion tokens</th>
              <th>Total tokens</th>
              <th>Latency ms</th>
            </tr>
          </thead>
          <tbody>{event_rows}</tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""

    def _render_metric(self, label: str, value: int | str) -> str:
        return (
            '<div class="metric">'
            f'<div class="label">{escape(label)}</div>'
            f'<div class="value">{escape(str(value))}</div>'
            "</div>"
        )

    def _render_model_row(self, model: dict[str, Any]) -> str:
        return (
            "<tr>"
            f"<td>{escape(str(model['model']))}</td>"
            f"<td>{escape(str(model['request_count']))}</td>"
            f"<td>{escape(str(model['prompt_tokens']))}</td>"
            f"<td>{escape(str(model['completion_tokens']))}</td>"
            f"<td>{escape(str(model['total_tokens']))}</td>"
            "</tr>"
        )

    def _render_admin_user_row(self, user_report: dict[str, Any]) -> str:
        aggregate = user_report["aggregate"]
        limits = user_report["limits"]
        return (
            "<tr>"
            f"<td>{escape(str(user_report['user_id']))}</td>"
            f"<td>{escape(str(user_report['display_name']))}</td>"
            f"<td>{escape(str(user_report['role']))}</td>"
            f"<td>{escape(str(aggregate['request_count']))}</td>"
            f"<td>{escape(str(aggregate['prompt_tokens']))}</td>"
            f"<td>{escape(str(aggregate['completion_tokens']))}</td>"
            f"<td>{escape(str(aggregate['total_tokens']))}</td>"
            f"<td>{escape(self._limit_value(limits['requests_per_minute']))}</td>"
            f"<td>{escape(self._limit_value(limits['daily_tokens']))}</td>"
            f"<td>{escape(self._limit_value(limits['total_tokens']))}</td>"
            "</tr>"
        )

    def _render_event_row(self, event: dict[str, Any]) -> str:
        status = str(event["status"])
        status_class = self._status_class(status)
        return (
            "<tr>"
            f"<td>{escape(str(event['timestamp']))}</td>"
            f"<td>{escape(str(event['model']))}</td>"
            f'<td><span class="status {status_class}">{escape(status)}</span></td>'
            f"<td>{escape(str(event['prompt_tokens']))}</td>"
            f"<td>{escape(str(event['completion_tokens']))}</td>"
            f"<td>{escape(str(event['total_tokens']))}</td>"
            f"<td>{escape(self._latency_value(event['latency_ms']))}</td>"
            "</tr>"
        )

    def _render_admin_event_row(self, event: dict[str, Any]) -> str:
        status = str(event["status"])
        status_class = self._status_class(status)
        return (
            "<tr>"
            f"<td>{escape(str(event['timestamp']))}</td>"
            f"<td>{escape(str(event['user_id']))}</td>"
            f"<td>{escape(str(event['model']))}</td>"
            f'<td><span class="status {status_class}">{escape(status)}</span></td>'
            f"<td>{escape(str(event['prompt_tokens']))}</td>"
            f"<td>{escape(str(event['completion_tokens']))}</td>"
            f"<td>{escape(str(event['total_tokens']))}</td>"
            f"<td>{escape(self._latency_value(event['latency_ms']))}</td>"
            "</tr>"
        )

    def _limit_value(self, value: int | None) -> str:
        if value is None:
            return "Not configured"
        return str(value)

    def _latency_value(self, value: Any) -> str:
        if isinstance(value, int | float):
            return f"{float(value):.1f}"
        return str(value)

    def _status_class(self, status: str) -> str:
        if status in {"success", "failed", "reserved"}:
            return f"status-{status}"
        return "status-other"


def render_usage_report_browser_shell() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Usage Report Browser</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f8fafc;
      --panel: #ffffff;
      --text: #202124;
      --muted: #5f6368;
      --line: #dadce0;
      --accent: #1a73e8;
      --error: #b3261e;
    }
    * {
      box-sizing: border-box;
    }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main {
      max-width: 1120px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }
    header {
      margin-bottom: 20px;
    }
    h1 {
      font-size: 28px;
      line-height: 1.2;
      margin: 0 0 8px;
    }
    p {
      color: var(--muted);
      margin: 0;
    }
    form {
      align-items: end;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      display: grid;
      gap: 14px;
      grid-template-columns: minmax(140px, 0.8fr) minmax(220px, 1.4fr) auto;
      margin-bottom: 16px;
      padding: 16px;
    }
    label {
      color: var(--muted);
      display: grid;
      font-size: 12px;
      font-weight: 650;
      gap: 6px;
      text-transform: uppercase;
    }
    input, select {
      border: 1px solid var(--line);
      border-radius: 4px;
      color: var(--text);
      font: inherit;
      min-height: 38px;
      padding: 8px 10px;
      text-transform: none;
      width: 100%;
    }
    input:disabled {
      background: #f1f3f4;
      color: var(--muted);
    }
    button {
      background: var(--accent);
      border: 1px solid var(--accent);
      border-radius: 4px;
      color: #ffffff;
      cursor: pointer;
      font: inherit;
      font-weight: 650;
      min-height: 38px;
      padding: 8px 14px;
      white-space: nowrap;
    }
    button:disabled {
      cursor: wait;
      opacity: 0.72;
    }
    #status {
      min-height: 22px;
      margin: 0 0 12px;
    }
    #status.error {
      color: var(--error);
    }
    #status.loading {
      color: var(--muted);
    }
    #report-frame {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      display: block;
      min-height: 640px;
      width: 100%;
    }
    @media (max-width: 820px) {
      form {
        grid-template-columns: 1fr;
      }
      button {
        width: 100%;
      }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Usage Report Browser</h1>
      <p>Enter a bearer token to load your report or the associated-users admin report.</p>
    </header>

    <form id="report-form">
      <label>
        Mode
        <select id="mode" name="mode">
          <option value="user">User</option>
          <option value="admin">Admin</option>
        </select>
      </label>
      <label>
        Bearer token
        <input id="token" name="token" type="password" autocomplete="off" required>
      </label>
      <button id="load-button" type="submit">Load report</button>
    </form>

    <p id="status" role="status" aria-live="polite"></p>
    <iframe id="report-frame" title="Usage report preview" sandbox=""></iframe>
  </main>

  <script>
    const form = document.getElementById("report-form");
    const modeInput = document.getElementById("mode");
    const tokenInput = document.getElementById("token");
    const statusOutput = document.getElementById("status");
    const frame = document.getElementById("report-frame");
    const loadButton = document.getElementById("load-button");

    function setStatus(message, kind = "") {
      statusOutput.textContent = message;
      statusOutput.className = kind;
    }

    async function errorMessageFor(response) {
      if (response.status === 401) {
        return "Missing or invalid bearer token.";
      }
      if (response.status === 403) {
        return "Admin credentials are required for that report.";
      }
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const payload = await response.json();
        if (payload.detail) {
          return String(payload.detail);
        }
        if (payload.error && payload.error.message) {
          return String(payload.error.message);
        }
      }
      return `Report request failed with HTTP ${response.status}.`;
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const token = tokenInput.value.trim();
      const mode = modeInput.value;

      frame.removeAttribute("srcdoc");
      setStatus("", "");

      if (!token) {
        setStatus("Enter a bearer token.", "error");
        tokenInput.focus();
        return;
      }

      let path = "/usage/report";
      if (mode === "admin") {
        path = "/admin/usage/report";
      }

      loadButton.disabled = true;
      setStatus("Loading report...", "loading");
      try {
        const response = await fetch(path, {
          headers: {
            "Accept": "text/html",
            "Authorization": `Bearer ${token}`,
          },
        });
        if (!response.ok) {
          setStatus(await errorMessageFor(response), "error");
          return;
        }
        frame.srcdoc = await response.text();
        setStatus("Report loaded.", "");
      } catch (error) {
        setStatus(`Could not load report: ${error.message}`, "error");
      } finally {
        loadButton.disabled = false;
      }
    });

  </script>
</body>
</html>
"""
